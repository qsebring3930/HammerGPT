"""Extract spatially bounded directed layout graphs from approved training NAVs.

These regions are connected spatial bins, not inferred architectural rooms.
Recorded NAV direction and original transition witnesses remain available.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import heapq
import html
import json
import math
from pathlib import Path

from build_routes import center
from training_dataset import SPLITS


def polygon_area(points):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2


def bounds(points):
    return {'min':[min(p[i] for p in points) for i in range(3)],
            'max':[max(p[i] for p in points) for i in range(3)]}


CONTAINMENT_EPSILON = .001


def contains(box, point, epsilon=CONTAINMENT_EPSILON):
    return all(box['min'][i]-epsilon <= point[i] <= box['max'][i]+epsilon for i in range(3))


def strongly_connected(keys, links):
    forward, reverse = defaultdict(list), defaultdict(list)
    for a,b in links:
        forward[a].append(b); reverse[b].append(a)
    seen, order = set(), []
    for seed in sorted(keys):
        if seed in seen: continue
        stack = [(seed,False)]
        while stack:
            key, done = stack.pop()
            if done: order.append(key)
            elif key not in seen:
                seen.add(key); stack.append((key,True))
                stack.extend((n,False) for n in forward[key] if n not in seen)
    seen, groups = set(), []
    for seed in reversed(order):
        if seed in seen: continue
        group, stack = [], [seed]
        while stack:
            key = stack.pop()
            if key not in seen:
                seen.add(key); group.append(key); stack.extend(reverse[key])
        groups.append(sorted(group))
    return sorted(groups,key=lambda g:g[0])


def shortest_route(starts, goals, adjacency, centers):
    distance = {key:0. for key in starts}; previous = {}
    queue = [(0.,key) for key in sorted(starts)]; heapq.heapify(queue)
    while queue:
        cost, key = heapq.heappop(queue)
        if cost != distance[key]: continue
        if key in goals:
            path = [key]
            while path[-1] in previous: path.append(previous[path[-1]])
            return {'nav_area_path':path[::-1], 'centroid_path_distance_units':cost}
        for neighbor in sorted(adjacency[key]):
            candidate = cost+math.dist(centers[key],centers[neighbor])
            if candidate < distance.get(neighbor,math.inf):
                distance[neighbor] = candidate; previous[neighbor] = key
                heapq.heappush(queue,(candidate,neighbor))
    return None


def extract(nav, reference, bin_units=512, height_units=128):
    if bin_units <= 0 or height_units <= 0: raise ValueError('Positive spatial bins required')
    areas = {a['id']:a for a in nav['areas'] if a['hull']==0 and a['movable_mesh_id']==0xffffffff}
    if not areas: raise ValueError('No static hull-0 NAV areas')
    centers = {k:center(a) for k,a in areas.items()}
    anchors = reference['spatial']['gameplay_anchors']
    named = [a for a in anchors if a['classname']=='env_cs_place' and a.get('geometry_bounds')]
    labels, buckets = {}, {}
    for key, p in centers.items():
        names = {a['properties'].get('place_name') for a in named if contains(a['geometry_bounds'],p)}-{None,''}
        labels[key] = next(iter(names)) if len(names)==1 else None
        buckets[key] = (math.floor(p[0]/bin_units),math.floor(p[1]/bin_units),
                        math.floor(p[2]/height_units),labels[key])
    links, excluded = [], []
    for key,a in areas.items():
        for connection in a['connections']:
            if connection['target'] in areas:
                links.append((key,connection['target'],connection))
            else: excluded.append({'source':key,**connection})
    # SCC within each bin prevents contracting a recorded one-way barrier.
    internal = [(a,b) for a,b,_ in links if buckets[a]==buckets[b]]
    groups = strongly_connected(areas,internal)
    region_for, nodes = {}, []
    for group in groups:
        rid = 'region_'+str(group[0])
        for key in group: region_for[key] = rid
        points = [p for key in group for p in areas[key]['corners']]
        weights = [polygon_area(areas[k]['corners']) for k in group]; total = sum(weights)
        position = [sum(centers[k][i]*w for k,w in zip(group,weights))/total if total else
                    sum(centers[k][i] for k in group)/len(group) for i in range(3)]
        box = bounds(points)
        nodes.append({'id':rid,'nav_area_ids':group,'label':labels[group[0]],
                      'spatial_bin':list(buckets[group[0]][:3]),'position':position,'bounds':box,
                      'summed_nav_polygon_area_xy':total,
                      'height_range_units':box['max'][2]-box['min'][2],
                      'span_xy_units':[box['max'][i]-box['min'][i] for i in range(2)],
                      'anchor_ids':[]})
    by_id = {n['id']:n for n in nodes}; transitions = defaultdict(list)
    for a,b,c in links:
        if region_for[a]==region_for[b]: continue
        witness = {'source_nav_area':a,'target_nav_area':b,'centroid_delta':
                   [centers[b][i]-centers[a][i] for i in range(3)]}
        for side,key in (('source',a),('target',b)):
            edge = c.get(side+'_edge'); points = areas[key]['corners']
            if isinstance(edge,int) and 0 <= edge < len(points):
                ends = [points[edge],points[(edge+1)%len(points)]]
                witness[side+'_edge'] = edge; witness[side+'_edge_endpoints'] = ends
                witness[side+'_edge_length_xy'] = math.dist(ends[0][:2],ends[1][:2])
        transitions[region_for[a],region_for[b]].append(witness)
    edges = []
    for (a,b), witnesses in sorted(transitions.items()):
        edges.append({'source':a,'target':b,'reverse_edge_exists':(b,a) in transitions,
                      'witnesses':witnesses,'evidence':'recorded_directed_nav_connection',
                      'source_edge_length_xy_samples':[w['source_edge_length_xy'] for w in witnesses
                                                       if 'source_edge_length_xy' in w]})
    attached = []
    for anchor in anchors:
        classname = anchor['classname']
        if classname=='env_cs_place': continue
        box = anchor.get('geometry_bounds')
        ids = sorted(k for k,p in centers.items() if box and contains(box,p))
        association = 'nav_centroid_inside_anchor_bounds' if ids else 'unassociated'
        position = [(box['min'][i]+box['max'][i])/2 for i in range(3)] if box else anchor['position']
        nearest, distance = None, None
        if classname in ('info_player_terrorist','info_player_counterterrorist'):
            nearest = min(centers,key=lambda k:math.dist(position,centers[k]))
            distance = math.dist(position,centers[nearest])
            if not ids:
                ids = [nearest]; association = 'nearest_nav_centroid_diagnostic_only'
        regions = sorted({region_for[k] for k in ids})
        aid = str(anchor['node_id'])
        for rid in regions: by_id[rid]['anchor_ids'].append(aid)
        attached.append({'id':aid,'classname':classname,'position':position,'bounds':box,
                         'bounds_source':anchor.get('bounds_source'),'properties':anchor['properties'],
                         'nav_area_ids':ids,'region_ids':regions,'association':association,
                         'nearest_nav_area':nearest,'nearest_centroid_distance':distance,
                         'containment_epsilon_units':CONTAINMENT_EPSILON,
                         'strictly_contained_nav_area_count':sum(contains(box,p,0) for p in centers.values()) if box else 0})
        if box and not ids:
            def box_distance(key):
                return math.sqrt(sum(max(box['min'][i]-centers[key][i],0,centers[key][i]-box['max'][i])**2 for i in range(3)))
            attached[-1]['nearby_nav_diagnostic_only'] = [
                {'nav_area_id':k,'position':centers[k],'distance_to_anchor_bounds':box_distance(k)}
                for k in sorted(centers,key=lambda k:(box_distance(k),k))[:5]]
    adjacency = defaultdict(set)
    for a,b,_ in links: adjacency[a].add(b)
    objectives = [a for a in attached if a['classname'] in ('func_bomb_target','func_hostage_rescue','hostage_entity')]
    routes = []
    for team in ('info_player_terrorist','info_player_counterterrorist'):
        starts = {k for a in attached if a['classname']==team for k in a['nav_area_ids']}
        for goal in objectives:
            result = shortest_route(starts,set(goal['nav_area_ids']),adjacency,centers) if starts and goal['nav_area_ids'] else None
            if result:
                result['region_path'] = []
                for k in result['nav_area_path']:
                    if not result['region_path'] or result['region_path'][-1]!=region_for[k]: result['region_path'].append(region_for[k])
            routes.append({'team_classname':team,'objective_anchor_id':goal['id'],
                           'status':('recorded_nav_path' if result else 'missing_spawn_association' if not starts
                                     else 'missing_objective_association' if not goal['nav_area_ids']
                                     else 'unreachable_in_selected_nav'),
                           'route':result,'spawn_association_is_diagnostic':True})
    undirected = {tuple(sorted((e['source'],e['target']))) for e in edges}
    neighbors = defaultdict(set)
    for a,b in undirected: neighbors[a].add(b); neighbors[b].add(a)
    remaining = set(by_id); weak = 0
    while remaining:
        weak += 1; todo = [remaining.pop()]
        while todo:
            for n in neighbors[todo.pop()]:
                if n in remaining: remaining.remove(n); todo.append(n)
    return {'schema_version':1,'task':'whole_map_spatial_navigation_layout','parameters':
            {'xy_bin_units':bin_units,'z_bin_units':height_units,'hull':0,'containment_epsilon_units':CONTAINMENT_EPSILON},
            'nodes':nodes,'edges':edges,'anchors':attached,'spawn_objective_routes':routes,
            'nav_polygons':[{'id':k,'region_id':region_for[k],'corners':a['corners']} for k,a in sorted(areas.items())],
            'excluded_links':excluded,
            'summary':{'nav_areas':len(areas),'regions':len(nodes),'directed_edges':len(edges),
                       'unpaired_directed_edges':sum(not e['reverse_edge_exists'] for e in edges),
                       'weak_components':weak,'undirected_cycle_rank':len(undirected)-len(nodes)+weak,
                       'named_nav_areas':sum(v is not None for v in labels.values()),
                       'ladders_not_modeled':nav.get('ladder_count',0),
                       'anchors':len(attached),'objectives':len(objectives),'available_routes':sum(r['route'] is not None for r in routes)},
            'feature_status':{'directed_connectivity':'recorded NAV', 'elevation':'recorded polygon geometry',
                              'region_size':'summed NAV area and bounds, not room dimensions',
                              'entrance_size':'NAV edge lengths only, not verified traversable clearance',
                              'spawns_and_objectives':'VMAP report with explicitly tagged associations',
                              'architectural_rooms':'not extracted', 'sightlines':'not extracted',
                              'cover':'not extracted', 'player_travel_time':'not measured'},
            'limitations':['Spatially bounded connected bins are not architectural rooms or designer-authored regions.',
                           'Whole-map coordinates retain elevation; the top-down diagram overlaps vertical levels.',
                           'Each contraction is strongly connected within one bin and label; inter-region links retain witnesses.',
                           'NAV edge lengths are not portal overlap, corridor width, collision clearance or sightlines.',
                           'Named labels and objectives use centroid containment in reported axis-aligned entity bounds.',
                           'Containment includes a recorded 0.001-unit numeric tolerance; it does not approximate player-body overlap.',
                           'Spawn nearest-centroid association and centroid-path distance are diagnostics, not walkability or travel time.',
                           'Movable NAV and ladders are excluded; static NAV freshness relative to repaired VMAP is unverified.',
                           'No model training is performed by this extractor.']}


def diagram(graph, name, destination):
    points = [p for a in graph['nav_polygons'] for p in a['corners']]
    box = bounds(points); width,height = 1100,950
    spanx = max(box['max'][0]-box['min'][0],1); spany = max(box['max'][1]-box['min'][1],1)
    scale = min(1000/spanx,780/spany)
    def xy(p): return 50+(p[0]-box['min'][0])*scale,100+(box['max'][1]-p[1])*scale
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="1100" height="950" fill="#111925"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#edf2fa} .edge{stroke:#8999af;stroke-width:1;opacity:.65}</style>',
           '<defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#ffcb70"/></marker></defs>',
           f'<text x="30" y="35" font-size="24">{html.escape(name)}: whole-map navigation layout</text>',
           f'<text x="30" y="62" font-size="15">{len(graph["nodes"])} spatial regions; {len(graph["edges"])} directed links. Hover nodes for details.</text>']
    palette = ['#304d69','#3d6680','#498397','#5d9ba3','#84b3ac','#b2c9b4']
    zmin,zmax = box['min'][2],box['max'][2]
    for a in graph['nav_polygons']:
        z = sum(p[2] for p in a['corners'])/len(a['corners'])
        color = palette[min(5,int((z-zmin)/max(zmax-zmin,1)*5))]
        vertices = ' '.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,a['corners']))
        svg.append(f'<polygon points="{vertices}" fill="{color}" stroke="#172333" stroke-width=".3"/>')
    nodes = {n['id']:n for n in graph['nodes']}; shown = set()
    for edge in graph['edges']:
        pair = tuple(sorted((edge['source'],edge['target'])))
        if edge['reverse_edge_exists'] and pair in shown: continue
        shown.add(pair); x,y = xy(nodes[edge['source']]['position']); u,v = xy(nodes[edge['target']]['position'])
        attrs = 'class="edge"' if edge['reverse_edge_exists'] else 'stroke="#ffcb70" stroke-width="1.4" marker-end="url(#arrow)"'
        svg.append(f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{u:.2f}" y2="{v:.2f}" {attrs}/>')
    for n in graph['nodes']:
        x,y = xy(n['position']); label = n['label'] or 'unnamed'
        title = html.escape(f'{n["id"]}: {label}; {len(n["nav_area_ids"])} NAV polygons; z={n["position"][2]:.0f}')
        svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.5" fill="#e7f1ff"><title>{title}</title></circle>')
    colors = {'info_player_terrorist':'#fa956c','info_player_counterterrorist':'#78b5ff',
              'func_bomb_target':'#ffe17f','hostage_entity':'#c990ff','func_hostage_rescue':'#c990ff'}
    for a in graph['anchors']:
        if a['classname'] not in colors: continue
        x,y = xy(a['position']); title = html.escape(f'{a["classname"]} {a["id"]}: {a["association"]}')
        svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{colors[a["classname"]]}" stroke="#111925"><title>{title}</title></circle>')
    svg += ['<text x="30" y="905" font-size="15">Floor shade = elevation | White nodes = spatial bins | Gold arrows = unpaired recorded direction</text>',
            '<text x="30" y="932" font-size="15">Orange/blue = T/CT spawns | Yellow = bomb targets | Geometry, clearance and NAV freshness remain unverified.</text></svg>']
    destination.write_text('\n'.join(svg),encoding='utf-8')
    # Raster preview of this generated vector diagram, for convenient review.
    import xml.etree.ElementTree as ET
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB',(width,height),'#111925'); draw = ImageDraw.Draw(image)
    for element in ET.fromstring('\n'.join(svg)):
        kind = element.tag.split('}')[-1]
        if kind=='polygon':
            points = [tuple(map(float,p.split(','))) for p in element.get('points').split()]
            draw.polygon(points,fill=element.get('fill'),outline=element.get('stroke'))
        elif kind=='line':
            a = (float(element.get('x1')),float(element.get('y1')))
            b = (float(element.get('x2')),float(element.get('y2')))
            color = element.get('stroke','#8999af'); draw.line([a,b],fill=color,width=1)
            if element.get('marker-end'):
                dx,dy = b[0]-a[0],b[1]-a[1]; length = math.hypot(dx,dy)
                if length:
                    dx,dy = dx/length,dy/length
                    draw.polygon([b,(b[0]-6*dx+3*dy,b[1]-6*dy-3*dx),
                                  (b[0]-6*dx-3*dy,b[1]-6*dy+3*dx)],fill=color)
        elif kind=='circle':
            x,y,r = [float(element.get(k)) for k in ('cx','cy','r')]
            draw.ellipse((x-r,y-r,x+r,y+r),fill=element.get('fill'),outline=element.get('stroke'))
        elif kind=='text':
            size = int(element.get('font-size',15)); font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
            draw.text((float(element.get('x')),float(element.get('y'))-size),element.text,font=font,fill='#edf2fa')
    image.save(destination.with_suffix('.png'))


def build(corpus_path, output):
    if output.exists(): raise ValueError('Choose a new output directory')
    corpus = json.loads(corpus_path.read_text()); approved = {r['name']:r for r in corpus['maps'] if r['user_approved']}
    selected = SPLITS['train']
    for name in selected:
        if name not in approved or not approved[name]['nav_available'] or approved[name].get('dataset_role')=='evaluation_only':
            raise ValueError('Unapproved or unavailable training map: '+name)
    output.mkdir(parents=True); rows = []; issues = []
    for name in selected:
        row = approved[name]; navpath = corpus_path.parent/(name.lower()+'-nav.json')
        refpath = corpus_path.parent/row['reference_report']
        navraw, refraw = navpath.read_bytes(),refpath.read_bytes()
        nav, ref = json.loads(navraw),json.loads(refraw)
        if ref['source'] != row['source']: raise ValueError('Map source mismatch: '+name)
        graph = extract(nav,ref)
        graph['map'] = name; graph['dataset_role'] = 'training'
        graph['provenance'] = {'nav_source':nav['source'],'nav_export':str(navpath.resolve()),
                               'nav_export_sha256':hashlib.sha256(navraw).hexdigest(),
                               'vmap_report':str(refpath.resolve()),'vmap_report_sha256':hashlib.sha256(refraw).hexdigest(),
                               'vmap_source':row['source'],'vmap_source_sha256':hashlib.sha256(Path(row['source']).read_bytes()).hexdigest(),
                               'extractor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        # Every selected area is assigned once; all cross-region witnesses conserve NAV direction.
        members = [k for n in graph['nodes'] for k in n['nav_area_ids']]
        if len(members)!=len(set(members)) or len(members)!=graph['summary']['nav_areas']: raise ValueError('Partition mismatch')
        destination = output/(name.lower()+'.json'); destination.write_text(json.dumps(graph,indent=2),encoding='utf-8')
        diagram(graph,name,destination.with_suffix('.svg'))
        for route in graph['spawn_objective_routes']:
            if route['route'] is None:
                issues.append({'map':name,**route})
        rows.append({'map':name,'graph':destination.name,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),**graph['summary']})
        print(json.dumps(rows[-1]),flush=True)
    manifest = {'schema_version':1,'model_training_performed':False,'training_maps':selected,
                'validation_maps_not_loaded':SPLITS['validation'],'test_maps_not_loaded':SPLITS['test'],
                'evaluation_reservations_not_loaded':True,'maps':rows,
                'ready_for_whole_map_model_training':False,
                'next_step':'Review region granularity and anchor alignment before constructing whole-map learning objectives.'}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'quality-issues.json').write_text(json.dumps(issues,indent=2),encoding='utf-8')
    lines = ['# Whole-map layout extraction','','Six approved training maps only. No new model training.','',
             '| Map | NAV areas | Spatial regions | Directed edges | Weak components | Cycle rank | Objectives | Spawn-objective paths |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in rows:
        lines.append(f'| {r["map"]} | {r["nav_areas"]} | {r["regions"]} | {r["directed_edges"]} | {r["weak_components"]} | {r["undirected_cycle_rank"]} | {r["objectives"]} | {r["available_routes"]} |')
    lines += ['', 'Regions are strongly connected within 512-unit XY bins and 128-unit elevation bins, additionally separated by inferred place labels. Centroid binning does not clip large polygons to the bin bounds. These are spatial navigation segments, not architectural rooms.',
              '', 'Each graph retains all static hull-0 NAV polygons, directed boundary witnesses, elevation, size proxies, spawn/objective bounds and diagnostic routes. Edge lengths do not establish entrance clearance. Routes use NAV centroid distances, not timing.',
              '', 'Cover, sightlines and architectural room boundaries still need geometry extraction. Movable NAV, ladders and NAV freshness are unresolved. Validation, test and reserved evaluation maps were not loaded.',
              '', 'Open the SVG diagrams to review topology and anchor alignment. Preserve map-level splits when creating further training tasks.']
    lines += ['', '## Objective route issues', '']
    lines += [f'- {i["map"]}: {i["team_classname"]} to objective {i["objective_anchor_id"]}: {i["status"]}.' for i in issues]
    lines += ['', 'Missing associations are not proof of an inaccessible site. Unreachable paths apply only to the selected static NAV graph, with ladders omitted. Nearby centroid diagnostics do not create training labels or connections. These graphs are not yet certified whole-map training targets.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); build(args.corpus,args.output)
