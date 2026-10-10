"""Bounded procedural strategic-search prototype; not a trained model or VMAP.

Room polygons and buffered paths are actual proposed walkable geometry. Search
rejects unintended crossings and evaluates a player-radius-eroded floor raster.
The radar is a rendering of that saved geometry, never an imagegen illustration.
"""
import argparse
from collections import Counter
import hashlib
import heapq
import json
import math
from pathlib import Path
import random

import networkx as nx
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import Delaunay
from shapely import contains_xy
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
SPEED = 250.0  # Explicit constant-speed geometric proxy, not an in-game timing.
CELL = 32
RADIUS = 16


def save(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def source_context():
    """Use reviewed evidence without treating NAV neighborhoods as door widths."""
    paths = ['output/annotations/dust2-boundaries-reviewed-v1/boundaries.json',
             'route-purpose-reviews.json']
    result = []
    for name in paths:
        path = ROOT / name
        data = json.loads(path.read_text(encoding='utf-8'))
        result.append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'status': data.get('status', data.get('scope'))})
    return {'sources': result,
            'used_for': 'Role vocabulary, encounter/choke distinction, conditional flank distinction.',
            'not_used_for': 'No physical width, timing or learned shape prior inferred from NAV ROIs.',
            'train_ivy': 'Conditional later flank to B if A is too dangerous from Ivy; not opening B.'}


def room_polygon(x, y, rng, terminal=False):
    profile = 'court' if terminal else rng.choice(['court','gallery','transition','transition'])
    sizes={'court':(rng.uniform(760,1040),rng.uniform(700,960)),
           'gallery':(rng.uniform(400,550),rng.uniform(850,1100)),
           'transition':(rng.uniform(350,500),rng.uniform(350,500))}
    w,h=sizes[profile]
    # Architectural footprint with a corner recess, rather than display glyphs.
    cutx, cuty = w * rng.uniform(.18, .35), h * rng.uniform(.18, .35)
    p = Polygon([(-w/2, -h/2), (w/2, -h/2), (w/2, h/2-cuty),
                 (w/2-cutx, h/2-cuty), (w/2-cutx, h/2), (-w/2, h/2)])
    from shapely.affinity import rotate, translate
    return translate(rotate(p, rng.choice([0, 90, 180, 270])), x, y)


def propose(seed):
    rng = random.Random(seed)
    count = rng.randint(15, 19)
    points = []
    for _ in range(1600):
        p = (rng.uniform(-3200, 3200), rng.uniform(-3000, 3000))
        if (p[0]/3400)**2 + (p[1]/3250)**2 > 1:
            continue
        if all(math.dist(p, q) > 1120 for q in points):
            points.append(p)
            if len(points) == count:
                break
    if len(points) != count:
        raise ValueError('placement_count')
    t = min(range(count), key=lambda i: points[i][1])
    ct = max(range(count), key=lambda i: points[i][1])
    choices = [i for i in range(count) if i not in (t, ct)
               and math.dist(points[i], points[ct]) < 2600
               and math.dist(points[i], points[t]) > 2700]
    if len(choices) < 2:
        raise ValueError('site_distribution')
    a, b = max(((i, j) for i in choices for j in choices if i < j),
               key=lambda ij: math.dist(points[ij[0]], points[ij[1]]))
    if math.dist(points[a], points[b]) < 2100:
        raise ValueError('site_separation')
    roles = {t: 'T', ct: 'CT', a: 'A', b: 'B'}
    rooms = [room_polygon(*p, rng, terminal=i in roles) for i,p in enumerate(points)]
    if any(rooms[i].distance(rooms[j]) < 110 for i in range(count) for j in range(i)):
        raise ValueError('room_separation')
    options = set()
    for tri in Delaunay(points).simplices:
        options.update(tuple(sorted((int(tri[i]), int(tri[j]))))
                       for i, j in [(0, 1), (1, 2), (0, 2)])
    corridors = {}
    for u, v in sorted(options):
        if math.dist(points[u], points[v]) > 2600:
            continue
        p, q = points[u], points[v]
        mid = ((p[0]+q[0])/2, (p[1]+q[1])/2)
        dx, dy = q[0]-p[0], q[1]-p[1]
        length = math.hypot(dx, dy)
        bend = rng.choice([-1, 1]) * rng.uniform(70, 160)
        via = (mid[0] - dy/length*bend, mid[1] + dx/length*bend)
        trials = [[p, via, q], [p, (p[0], q[1]), q], [p, (q[0], p[1]), q]]
        if rng.random()<.65:
            orthogonal=[coords for coords in trials[1:] if LineString(coords).length<length*1.32]
            trials=orthogonal+trials
        for coords in trials:
            line = LineString(coords)
            width = rng.choice([288, 352, 416, 480])
            poly = line.buffer(width/2, cap_style=2, join_style=2)
            if any(poly.intersection(room).area > 1 for i, room in enumerate(rooms)
                   if i not in (u, v)):
                continue
            corridors[u, v] = {'line': line, 'polygon': poly, 'width': width}
            break
    graph = nx.Graph()
    graph.add_nodes_from(range(count))
    edges = list(corridors)
    rng.shuffle(edges)
    # No authored site-route skeleton: an embedded candidate-edge set is sampled.
    for edge in edges:
        if rng.random() > rng.uniform(.72, .9):
            continue
        if any(graph.degree(i) >= 4 for i in edge):
            continue
        overlap = False
        for other in graph.edges:
            common = set(edge) & set(other)
            intersection = corridors[edge]['polygon'].intersection(
                corridors[tuple(sorted(other))]['polygon'])
            if common:
                # Shared incident passages form a continuous local junction.
                # Permit that merge only inside a declared 240-unit apron.
                intersection = intersection.difference(unary_union([rooms[i].buffer(240) for i in common]))
            if intersection.area > 1:
                overlap = True
                break
        if not overlap:
            graph.add_edge(*edge, length=corridors[edge]['line'].length)
    if not nx.is_connected(graph):
        raise ValueError('disconnected_strategy')
    if min(dict(graph.degree()).values()) < 2:
        raise ValueError('dangling_place')
    if graph.number_of_edges()>count+6:
        raise ValueError('excess_macro_connections')
    if list(nx.articulation_points(graph)):
        raise ValueError('single_attachment_loop_or_front')
    for site, other in [(a, b), (b, a)]:
        allowed = graph.copy()
        allowed.remove_nodes_from([other, ct])
        if nx.node_connectivity(allowed, t, site) < 2:
            raise ValueError('no_attack_alternative')
        allowed = graph.copy()
        allowed.remove_nodes_from([other, t])
        if not nx.has_path(allowed, ct, site):
            raise ValueError('no_independent_defender_distribution')
    return points, rooms, graph, corridors, roles


def rasterize(floor):
    bounds = floor.bounds
    origin = (math.floor(bounds[0]/CELL)*CELL-CELL, math.floor(bounds[1]/CELL)*CELL-CELL)
    xs = np.arange(origin[0], bounds[2]+CELL*2, CELL)
    ys = np.arange(origin[1], bounds[3]+CELL*2, CELL)
    xx, yy = np.meshgrid(xs, ys)
    # Conservative local model: a disk radius and centerline between cell centers.
    safe = floor.buffer(-RADIUS)
    mask = contains_xy(safe, xx, yy)
    def index(p):
        return (int(round((p[1]-origin[1])/CELL)), int(round((p[0]-origin[0])/CELL)))
    return safe, mask, xs, ys, index


def distances(mask, start):
    if not (0 <= start[0] < mask.shape[0] and 0 <= start[1] < mask.shape[1]
            and mask[start]):
        raise ValueError('spawn_or_terminal_off_floor')
    dist = {start: 0.0}
    prev = {}
    queue = [(0., start)]
    while queue:
        d, (y, x) = heapq.heappop(queue)
        if d != dist[y, x]:
            continue
        for dy, dx in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            yy, xx = y+dy, x+dx
            if not (0 <= yy < mask.shape[0] and 0 <= xx < mask.shape[1] and mask[yy,xx]):
                continue
            if dy and dx and not (mask[y,xx] and mask[yy,x]):
                continue
            nd = d + CELL * math.hypot(dx, dy)
            if nd < dist.get((yy,xx), math.inf):
                dist[yy,xx] = nd
                prev[yy,xx] = (y,x)
                heapq.heappush(queue, (nd, (yy,xx)))
    return dist, prev


def validate_raster_paths(safe, mask, xs, ys):
    # Endpoints alone can miss narrow slits; require each admitted raster edge
    # to fit the eroded polygon. Remove problematic endpoints conservatively.
    for dy, dx in [(0,1),(1,0),(1,1),(1,-1)]:
        for y, x in zip(*np.nonzero(mask)):
            yy, xx = y+dy, x+dx
            if 0 <= yy < len(ys) and 0 <= xx < len(xs) and mask[yy,xx]:
                if not safe.covers(LineString([(xs[x],ys[y]),(xs[xx],ys[yy])])):
                    mask[y,x] = False
    return mask


def route_signature(graph, path, roles):
    # Explicitly a coarse decision signature, not full tactical equivalence.
    return [roles.get(n, f'junction{graph.degree(n)}') for n in path]


def canonical_strategy(graph, roles):
    """Suppress degree-two connector subdivisions, retain parallel alternatives.

    Treat A/B as interchangeable objectives for duplicate detection. This is a
    structural equivalence check; timing/exposure equivalence is not claimed.
    """
    reduced=nx.MultiGraph(graph)
    while True:
        removable=[i for i in reduced if i not in roles and reduced.degree(i)==2
                   and not reduced.has_edge(i,i)]
        if not removable:break
        i=removable[0];neighbors=list(reduced.neighbors(i))
        if len(neighbors)!=2:break
        reduced.remove_node(i);reduced.add_edge(*neighbors)
    result=nx.Graph()
    for i in reduced:
        role=roles.get(i,'connector')
        result.add_node(('place',i),role='site' if role in ('A','B') else role)
    for j,(u,v) in enumerate(reduced.edges()):
        result.add_node(('link',j),role='link')
        result.add_edge(('place',u),('link',j));result.add_edge(('link',j),('place',v))
    return result


def realize(seed, removed_edges=None):
    from semantic_pipeline import check_generation_policy
    check_generation_policy(legacy=True)
    points, rooms, graph, corridors, roles = propose(seed)
    if removed_edges:
        for edge in removed_edges:
            if not graph.has_edge(*edge):raise ValueError('intervention_edge_missing')
        graph.remove_edges_from(removed_edges)
        if not nx.is_connected(graph) or min(dict(graph.degree()).values())<2 or list(nx.articulation_points(graph)):
            raise ValueError('intervention_breaks_backbone')
        terminals={r:i for i,r in roles.items()}
        for site,other in [('A','B'),('B','A')]:
            attack=graph.copy();attack.remove_nodes_from([terminals[other],terminals['CT']])
            if nx.node_connectivity(attack,terminals['T'],terminals[site])<2:
                raise ValueError('intervention_removes_distinct_site_approach')
            defense=graph.copy();defense.remove_nodes_from([terminals[other],terminals['T']])
            if not nx.has_path(defense,terminals['CT'],terminals[site]):
                raise ValueError('intervention_breaks_defender_access')
    selected = {tuple(sorted(edge)): corridors[tuple(sorted(edge))] for edge in graph.edges}
    role_nodes = {role: i for i, role in roles.items()}
    route_records = []
    for team in ('T','CT'):
        for site, other in [('A','B'),('B','A')]:
            allowed = graph.copy()
            allowed.remove_nodes_from([role_nodes[other], role_nodes['CT' if team=='T' else 'T']])
            if team=='T':
                paths=sorted(nx.node_disjoint_paths(allowed,role_nodes[team],role_nodes[site]),
                    key=lambda p:sum(allowed[u][v]['length'] for u,v in zip(p,p[1:])))
            else:
                paths=[nx.shortest_path(allowed,role_nodes[team],role_nodes[site],weight='length')]
            for j, path in zip(range(2 if team=='T' else 1), paths):
                route_records.append({'id': f'{team}-{site}-{j+1}', 'team': team, 'target': site,
                                      'phase': 'opening' if team=='T' else 'defender_distribution',
                                      'places': path, 'decision_signature': route_signature(graph,path,roles)})
    for record in route_records:
        coords=[]
        for u,v in zip(record['places'],record['places'][1:]):
            section=list(selected[tuple(sorted((u,v)))]['line'].coords)
            if u>v:section.reverse()
            coords.extend(section if not coords else section[1:])
        record['physical_centerline_xy']=list(map(list,coords))
        record['seconds_centerline_proxy']=round(LineString(coords).length/SPEED,1)
    protected = unary_union([c['line'].buffer(112) for c in selected.values()])
    rng = random.Random(seed+900000)
    cover = []
    for i, room in enumerate(rooms):
        x,y = points[i]
        for _ in range(20):
            cx,cy = x+rng.uniform(-320,320), y+rng.uniform(-320,320)
            obstacle = box(cx-64,cy-96,cx+64,cy+96)
            if room.buffer(-100).covers(obstacle) and obstacle.distance(protected)>16:
                cover.append(obstacle)
                break
    floor = unary_union(rooms + [c['polygon'] for c in selected.values()]).difference(unary_union(cover))
    if floor.geom_type != 'Polygon' or not floor.is_valid:
        raise ValueError('floor_disconnected_or_invalid')
    safe, mask, xs, ys, index = rasterize(floor)
    mask = validate_raster_paths(safe, mask, xs, ys)
    fields = {}
    timings = {}
    spawns = {}
    for team in ('T','CT'):
        x,y = points[role_nodes[team]]
        spawns[team] = [[x+dx,y+dy,0] for dx,dy in [(-64,-64),(64,-64),(0,0),(-64,64),(64,64)]]
        for j, p in enumerate(spawns[team]):
            dist, prev = distances(mask, index(p))
            if any(index(points[n]) not in dist for n in range(len(points))):
                raise ValueError('physical_access_from_spawn')
            if j==2:
                fields[team] = dist, prev
        for site, other in [('A','B'),('B','A')]:
            # Actual raster access must survive removal of the other site floor.
            forbidden = contains_xy(rooms[role_nodes[other]], *np.meshgrid(xs,ys))
            forbidden |= contains_xy(rooms[role_nodes['CT' if team=='T' else 'T']], *np.meshgrid(xs,ys))
            blocked = mask & ~forbidden
            dist,prev = distances(blocked,index(spawns[team][2]))
            end = index(points[role_nodes[site]])
            if end not in dist:
                raise ValueError('physical_independent_distribution')
            path = [end]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            path.reverse()
            worldpath = [[float(xs[x]),float(ys[y])] for y,x in path]
            if not safe.covers(LineString(worldpath)):
                raise ValueError('raster_route_outside_clearance')
            timings[f'{team}-{site}'] = {'seconds_proxy': round(dist[end]/SPEED,1),
                                         'path_xy': worldpath}
    # Verify every planned corridor centerline and construct real entry portals.
    portals=[]
    for (u,v), c in selected.items():
        if not floor.covers(c['line']):
            raise ValueError('planned_path_obstructed')
        for roomid in (u,v):
            crosses = c['line'].intersection(rooms[roomid].boundary)
            hits = list(crosses.geoms) if hasattr(crosses,'geoms') else [crosses]
            hits = [p for p in hits if p.geom_type=='Point']
            if len(hits)!=1:
                raise ValueError('ambiguous_room_entry')
            p=hits[0]; s=c['line'].project(p)
            before,after=c['line'].interpolate(max(0,s-1)),c['line'].interpolate(min(c['line'].length,s+1))
            dx,dy=after.x-before.x,after.y-before.y
            norm=math.hypot(dx,dy)
            w=c['width']/2-RADIUS
            segment=LineString([(p.x-dy/norm*w,p.y+dx/norm*w),(p.x+dy/norm*w,p.y-dx/norm*w)])
            if not floor.covers(segment):
                raise ValueError('entrance_width')
            portals.append({'edge':[u,v],'room':roomid,'segment_xy':list(map(list,segment.coords)),
                            'clear_width_proxy':segment.length,'z':0,'movement':'walk_bidirectional'})
    tpaths=[r['places'] for r in route_records if r['team']=='T' and r['id'].endswith('-1')]
    # Share of first-approach intermediate decision places, excluding endpoints.
    left,right=map(lambda p:set(p[1:-1]),tpaths)
    sharing=len(left&right)/max(1,len(left|right))
    rotation=graph.copy(); rotation.remove_nodes_from([role_nodes['T'],role_nodes['CT']])
    if not nx.has_path(rotation,role_nodes['A'],role_nodes['B']):
        raise ValueError('no_spawn_independent_rotation')
    rotpath=nx.shortest_path(rotation,role_nodes['A'],role_nodes['B'],weight='length')
    rotation_proxy=sum(graph[u][v]['length'] for u,v in zip(rotpath,rotpath[1:]))/SPEED
    rotation_mask=mask.copy()
    for role in ('T','CT'):
        rotation_mask &= ~contains_xy(rooms[role_nodes[role]],*np.meshgrid(xs,ys))
    rd,rp=distances(rotation_mask,index(points[role_nodes['A']]))
    endpoint=index(points[role_nodes['B']])
    if endpoint not in rd:raise ValueError('physical_rotation_blocked')
    rotation_raster=rd[endpoint]/SPEED
    rotation_cells=[endpoint]
    while rotation_cells[-1] in rp:rotation_cells.append(rp[rotation_cells[-1]])
    rotation_cells.reverse()
    rotation_xy=[[float(xs[x]),float(ys[y])] for y,x in rotation_cells]
    distribution=sum(timings[f'CT-{s}']['seconds_proxy'] for s in ('A','B'))/2
    mid=min((i for i in graph if i not in roles), key=lambda i: math.hypot(*points[i]))
    meetings=[]
    for i in graph:
        if i in roles: continue
        td=fields['T'][0][index(points[i])]/SPEED
        cd=fields['CT'][0][index(points[i])]/SPEED
        if abs(td-cd)<3.5:
            meetings.append({'place':i,'T_proxy':round(td,1),'CT_proxy':round(cd,1)})
    if not meetings:
        raise ValueError('no_estimated_contest')
    nodes=[{'id':i,'role':roles.get(i,'connector'),'center':[float(x),float(y),0],
            'floor':mapping(rooms[i]),'initial_control':'estimated_contested' if any(m['place']==i for m in meetings)
            else ('T_proxy' if fields['T'][0][index((x,y))]<fields['CT'][0][index((x,y))] else 'CT_proxy')}
           for i,(x,y) in enumerate(points)]
    candidate={'schema':1,'seed':seed,'generator':'procedural constrained search, no neural weights',
        'nodes':nodes,'edges':[{'places':[u,v],'centerline':list(map(list,c['line'].coords)),
            'width':c['width'],'floor':mapping(c['polygon'])} for (u,v),c in selected.items()],
        'floor':mapping(floor),'cover':[mapping(p) for p in cover],'portals':portals,
        'spawns':spawns,'routes':route_records,'timings':timings,'rotation_places':rotpath,
        'rotation_seconds_centerline_proxy':round(rotation_proxy,1),'mid':mid,'estimated_contests':meetings,
        'rotation_seconds_raster_proxy':round(rotation_raster,1),'rotation_path_xy':rotation_xy,
        'descriptors':{'opening_sharing':sharing,'rotation_ratio':rotation_raster/distribution},
        'validations':{'connected_polygon':True,'all_ten_spawn_points_access_every_place':True,
            'site_access_without_other_site_or_opposing_spawn':True,'planned_paths_preserved':True,
            'unintended_nonincident_corridor_crossings':0,'min_clear_portal_width_proxy':min(p['clear_width_proxy'] for p in portals),
            'player_radius_proxy':RADIUS,'raster_cell_units':CELL},
        'repairs':[], 'height_scope':'single level at z=0; no stairs, drops or stacked floors generated',
        'junction_merge_apron_units':240,
        'unverified':['CS2 collision/headroom','in-game timing','utility/sound','visibility balance','playtest quality'],
        'timing_model':f'Geometric raster shortest paths / {SPEED:g} units/s; no acceleration or combat.'}
    for n in candidate['nodes']:
        n['strategic_roles']=[n['role']]
        if n['id'] in graph.neighbors(role_nodes['T']):n['strategic_roles'].append('attacker_staging')
        if n['id'] in graph.neighbors(role_nodes['CT']):n['strategic_roles'].append('defender_distribution')
        if n['id']==mid:n['strategic_roles'].append('mid')
        if any(m['place']==n['id'] for m in meetings):n['strategic_roles'].append('estimated_encounter')
    candidate['divergence_convergence']={
        'primary_opening_shared_intermediate_places':sorted(left&right),
        'A_opening_alternatives':[r['places'] for r in route_records if r['team']=='T' and r['target']=='A'],
        'B_opening_alternatives':[r['places'] for r in route_records if r['team']=='T' and r['target']=='B']}
    canonical=canonical_strategy(graph,roles)
    candidate['coarse_equivalence_hash']=nx.weisfeiler_lehman_graph_hash(canonical,node_attr='role')
    candidate['human_guided_removed_edges']=[list(e) for e in (removed_edges or [])]
    candidate['visibility_center_pairs_proxy']=[[u,v] for u in graph for v in graph if u<v
        and floor.covers(LineString([points[u],points[v]]))]
    return candidate, canonical


def audit_saved(candidate):
    """Independently verify saved geometric provenance and basic access."""
    rooms=[shape(n['floor']) for n in candidate['nodes']]
    passages=[shape(e['floor']) for e in candidate['edges']]
    obstacles=[shape(p) for p in candidate['cover']]
    expected=unary_union(rooms+passages).difference(unary_union(obstacles))
    floor=shape(candidate['floor'])
    if floor.symmetric_difference(expected).area>1e-5:
        raise ValueError('saved_floor_not_component_union')
    if not floor.is_valid or floor.geom_type!='Polygon':raise ValueError('saved_floor_invalid')
    safe,mask,xs,ys,index=rasterize(floor)
    mask=validate_raster_paths(safe,mask,xs,ys)
    for team,spawns in candidate['spawns'].items():
        for p in spawns:
            d,_=distances(mask,index(p))
            if any(index(n['center']) not in d for n in candidate['nodes']):
                raise ValueError('saved_spawn_access_failed')
    for record in candidate['routes']:
        if not safe.covers(LineString(record['physical_centerline_xy'])):
            raise ValueError('saved_planned_route_clearance_failed')
    for record in candidate['timings'].values():
        if not safe.covers(LineString(record['path_xy'])):raise ValueError('saved_raster_route_failed')
    if 'rotation_path_xy' in candidate and not safe.covers(LineString(candidate['rotation_path_xy'])):
        raise ValueError('saved_rotation_route_failed')
    return {'floor_reconstructed_from_components':True,'all_spawn_access':True,
            'all_planned_routes_fit_radius_proxy':True,'all_displayed_routes_on_safe_floor':True}


def draw_polygon(draw, poly, xy, fill, outline=None, width=1):
    if poly.geom_type=='MultiPolygon':
        for part in poly.geoms:draw_polygon(draw,part,xy,fill,outline,width)
        return
    draw.polygon([xy(*p) for p in poly.exterior.coords],fill=fill)
    if outline: draw.line([xy(*p) for p in poly.exterior.coords],fill=outline,width=width)
    for ring in poly.interiors:
        draw.polygon([xy(*p) for p in ring.coords],fill='#080f18')
        if outline:draw.line([xy(*p) for p in ring.coords],fill=outline,width=width)


def render(candidate, path, overlay=False):
    size=1600
    im=Image.new('RGB',(size,size),'#080f18'); draw=ImageDraw.Draw(im)
    floor=shape(candidate['floor']); minx,miny,maxx,maxy=floor.bounds
    scale=min(1320/(maxx-minx),1320/(maxy-miny))
    cx,cy=(minx+maxx)/2,(miny+maxy)/2
    xy=lambda x,y:(round(800+(x-cx)*scale),round(790-(y-cy)*scale))
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n)
    draw_polygon(draw,floor.buffer(36),xy,'#182737')
    draw_polygon(draw,floor,xy,'#6e899e','#b7cbd9',3)
    for n in candidate['nodes']:
        p=shape(n['floor']).intersection(floor)
        color='#819bad' if n['id']%3==0 else '#728ea2'
        draw_polygon(draw,p,xy,color)
    # Redraw all obstacle holes; room color cannot paint over actual cover.
    for ring in floor.interiors:
        p=Polygon(ring)
        draw_polygon(draw,p,xy,'#182532','#adc1cc',2)
    byid={n['id']:n for n in candidate['nodes']}
    if overlay:
        for key,record in candidate['timings'].items():
            color='#ffc76c' if key.startswith('T') else '#67d7ed'
            pts=[xy(*p) for p in record['path_xy']]
            draw.line(pts,fill=color,width=5)
            # Direction arrows distributed along the rendered actual path.
            for k in range(12,len(pts)-3,28):
                p,q=pts[k],pts[k+3]; angle=math.atan2(q[1]-p[1],q[0]-p[0])
                draw.polygon([q,(q[0]-15*math.cos(angle-.5),q[1]-15*math.sin(angle-.5)),
                              (q[0]-15*math.cos(angle+.5),q[1]-15*math.sin(angle+.5))],fill=color)
        for meeting in candidate['estimated_contests']:
            x,y=xy(*byid[meeting['place']]['center'][:2])
            draw.ellipse((x-55,y-55,x+55,y+55),outline='#fff1ab',width=4)
        draw.line([xy(*p) for p in candidate['rotation_path_xy']],fill='#c6a2f5',width=4)
        for portal in candidate['portals']:
            draw.line([xy(*p) for p in portal['segment_xy']],fill='#dcebf2',width=3)
    for n in candidate['nodes']:
        label={'T':'T SPAWN','CT':'CT SPAWN','A':'A','B':'B'}.get(n['role'])
        if label:
            x,y=xy(*n['center'][:2]); f=font(65 if label in ('A','B') else 27)
            color='#f4de99' if label in ('A','B') else ('#ffc76c' if label=='T SPAWN' else '#7cdef0')
            draw.text((x,y),label,font=f,fill=color,anchor='mm',stroke_width=3,stroke_fill='#111d29')
    mid=byid[candidate['mid']];x,y=xy(*mid['center'][:2])
    draw.text((x,y),'MID',font=font(26),fill='#eff5fa',anchor='mm',stroke_width=2,stroke_fill='#172b3e')
    if overlay:
        draw.text((70,42),'Opening access — geometric timing estimates',font=font(32),fill='#eef5fa')
        draw.text((70,1490),'Gold: T   Cyan: CT   Purple: site rotation   Rings: equal-arrival estimates',font=font(24),fill='#d5e3ee')
        timing='   '.join(f"{k}: {v['seconds_proxy']}s" for k,v in candidate['timings'].items())
        draw.text((70,1530),timing,font=font(25),fill='#d5e3ee')
    im.save(path)


def main():
    from semantic_pipeline import check_generation_policy
    check_generation_policy(legacy=True)
    parser=argparse.ArgumentParser();parser.add_argument('--attempts',type=int,default=1400)
    parser.add_argument('--output',default='output/strategic-floorplan-v1')
    args=parser.parse_args();out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
    source=source_context();save(out/'source-context.json',source)
    feasible=[];rejected=Counter();archive={};logs=[]
    matcher=nx.algorithms.isomorphism.categorical_node_match('role','')
    for seed in range(9000,9000+args.attempts):
        try:
            c,g=realize(seed)
        except ValueError as e:
            rejected[str(e)]+=1;logs.append({'seed':seed,'accepted':False,'reason':str(e)})
            continue
        if any(nx.is_isomorphic(g,oldg,node_match=matcher) for _,oldg in feasible):
            rejected['strategic_graph_duplicate']+=1
            logs.append({'seed':seed,'accepted':False,'reason':'strategic_graph_duplicate'})
            continue
        feasible.append((c,g))
        print(f"Valid candidate {len(feasible)} at seed {seed}",flush=True)
        desc=c['descriptors'];binid=(min(3,int(desc['opening_sharing']*4)),min(5,int(desc['rotation_ratio']*2)))
        # Retain shorter max attacker travel within each descriptor cell. Proxy only.
        score=-max(c['timings'][f'T-{s}']['seconds_proxy'] for s in ('A','B'))
        if binid not in archive or score>archive[binid][0]:archive[binid]=(score,c,g)
        logs.append({'seed':seed,'accepted':True,'archive_bin':list(binid)})
        if len(feasible)>=16 and len(archive)>=4:break
    save(out/'search-log.json',logs)
    save(out/'feasible-unedited.json',[c for c,_ in feasible])
    pool=[(c,g) for _,c,g in archive.values()]
    if len(pool)<3:pool=feasible
    selected=[]
    if pool:
        selected.append(min(pool,key=lambda cg:cg[0]['descriptors']['opening_sharing']))
        while len(selected)<min(3,len(pool)):
            remaining=[cg for cg in pool if cg[0]['seed'] not in [v[0]['seed'] for v in selected]]
            def novelty(cg):
                c,g=cg; d=c['descriptors']
                return min(abs(d['opening_sharing']-old['descriptors']['opening_sharing'])*2+
                           abs(d['rotation_ratio']-old['descriptors']['rotation_ratio'])+
                           abs(g.number_of_edges()-og.number_of_edges())*.1 for old,og in selected)
            selected.append(max(remaining,key=novelty))
    summary={'attempted':len(logs),'feasible_distinct_role_graphs':len(feasible),'archive_bins':len(archive),
        'rejection_counts':dict(rejected),'selected_seeds':[c['seed'] for c,_ in selected],
        'repairs':0,'training_performed':False,'source_context':source,
        'acceptance_scope':'2D polygon/raster checks only; no engine collision, headroom or competitive certification.'}
    save(out/'summary.json',summary)
    (out/'prototype-script.py').write_bytes(Path(__file__).read_bytes())
    for i,(c,_) in enumerate(selected,1):
        folder=out/f'candidate-{i}';folder.mkdir(exist_ok=True)
        save(folder/'layout.json',c);render(c,folder/'radar.png');render(c,folder/'routes.png',True)
        save(folder/'independent-audit.json',audit_saved(json.loads((folder/'layout.json').read_text())))
    # Readable side-by-side; each standalone radar remains available at full size.
    if selected:
        canvas=Image.new('RGB',(2400,950),'#080f18');pen=ImageDraw.Draw(canvas)
        f=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',24)
        for i,(c,_) in enumerate(selected,1):
            image=Image.open(out/f'candidate-{i}'/'radar.png').resize((780,780),Image.Resampling.LANCZOS)
            canvas.paste(image,((i-1)*800+10,65))
            pen.text(((i-1)*800+28,20),f"Candidate {i} · seed {c['seed']}",font=f,fill='#e3edf4')
            desc=c['descriptors']
            pen.text(((i-1)*800+28,845),f"Route sharing {desc['opening_sharing']:.0%} · rotation ratio {desc['rotation_ratio']:.2f}",font=f,fill='#baceda')
        pen.text((28,910),'Procedural floorplan prototype · single level · timings and tactical roles require playtesting',font=f,fill='#baceda')
        canvas.save(out/'comparison.png')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
