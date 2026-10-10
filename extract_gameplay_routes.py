"""Auditable alternative-route targets on original directed NAV polygons.

No whole-map quality labels, arrival times, inferred control, or model training.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import textwrap

import networkx as nx
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from build_routes import center
from compare_gameplay_structure import MAPS, ANNOTATIONS, PAIRS


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def triangle_distances(point, triangles):
    """Distance to triangle surfaces, including edge projection outside a face."""
    point = np.asarray(point, dtype=float)
    triangles = np.asarray(triangles, dtype=float)
    a, b, c = triangles[:,0], triangles[:,1], triangles[:,2]
    u, v, w = b-a, c-a, point-a
    uu, uv, vv = (u*u).sum(1), (u*v).sum(1), (v*v).sum(1)
    wu, wv = (w*u).sum(1), (w*v).sum(1)
    denominator = uu*vv-uv*uv
    good = denominator > 1e-12
    safe = np.where(good, denominator, 1)
    s, t = (wu*vv-wv*uv)/safe, (wv*uu-wu*uv)/safe
    projected = a+s[:,None]*u+t[:,None]*v
    inside = good & (s >= -1e-9) & (t >= -1e-9) & (s+t <= 1+1e-9)
    distance = np.where(inside, np.linalg.norm(projected-point,axis=1), np.inf)
    for start, end in ((a,b),(b,c),(c,a)):
        delta = end-start
        length2 = (delta*delta).sum(1)
        factor = np.clip(((point-start)*delta).sum(1)/np.maximum(length2,1e-12),0,1)
        nearest = start+factor[:,None]*delta
        distance = np.minimum(distance,np.linalg.norm(nearest-point,axis=1))
    return distance


def triangulate(areas):
    triangles, owners = [], []
    for key, area in sorted(areas.items()):
        points = area['corners']
        for i in range(1,len(points)-1):
            triangles.append([points[0],points[i],points[i+1]])
            owners.append(key)
    return np.asarray(triangles), np.asarray(owners)


def associations(graph, areas, centers, labels, tolerance):
    triangles, owners = triangulate(areas)
    terminals, audit = {}, {'spawn_projections':[], 'objectives':[]}
    for role, classname in [('T','info_player_terrorist'),('CT','info_player_counterterrorist')]:
        eligible = []
        for anchor in graph['anchors']:
            if anchor['classname'] != classname or str(anchor['properties'].get('enabled','1')) == '0':
                continue
            distances = triangle_distances(anchor['position'],triangles)
            i = int(np.argmin(distances))
            key, distance = int(owners[i]), float(distances[i])
            row = {'anchor_id':anchor['id'], 'role':role, 'position':anchor['position'],
                   'nav_area_id':key, 'surface_distance_units':distance,
                   'within_association_tolerance':distance <= tolerance,
                   'previous_coarse_regions':anchor['region_ids']}
            audit['spawn_projections'].append(row)
            if distance <= tolerance:
                eligible.append(row)
        if not eligible:
            raise ValueError(f'No supported {role} spawn projections')
        midpoint = np.median([a['position'] for a in eligible],axis=0)
        representative = min(eligible,key=lambda a:(math.dist(a['position'],midpoint),a['anchor_id']))
        terminals[role] = {'nav_area_ids':sorted({a['nav_area_id'] for a in eligible}),
                           'representative_nav_area':representative['nav_area_id'],
                           'representative_anchor_id':representative['anchor_id'],
                           'basis':'nearest original NAV polygon surface; tolerance is association uncertainty, not clearance'}
    for anchor in graph['anchors']:
        if anchor['classname'] != 'func_bomb_target':
            continue
        bounds = anchor['bounds']
        if not bounds:
            raise ValueError('Missing objective volume bounds')
        keys = sorted(k for k,p in centers.items() if all(bounds['min'][i]-.001 <= p[i] <= bounds['max'][i]+.001 for i in range(3)))
        votes = Counter(labels[k] for k in keys if labels[k] in ('BombsiteA','BombsiteB'))
        identity_basis = 'original source place labels inside objective bounds'
        if not votes:
            coarse_labels={k:n['label'] for n in graph['nodes'] for k in n['nav_area_ids']}
            votes=Counter(coarse_labels[k] for k in keys if coarse_labels[k] in ('BombsiteA','BombsiteB'))
            identity_basis='existing coarse place association inside objective bounds; original labels unknown'
        if not votes:
            objective_anchors=[a for a in graph['anchors'] if a['classname']=='func_bomb_target']
            designations={str(a['properties'].get('bomb_site_designation')) for a in objective_anchors}
            # Use explicit source designations only when the two sites carry
            # distinct 0/1 values; repeated decompiler defaults stay ambiguous.
            if len(objective_anchors)==2 and designations=={'0','1'}:
                label='BombsiteA' if str(anchor['properties']['bomb_site_designation'])=='0' else 'BombsiteB'
                votes=Counter({label:len(keys)})
                identity_basis='distinct source bomb_site_designation values; no place annotation required'
        if not keys or not votes or len(votes)>1:
            raise ValueError('Ambiguous objective identity or empty original NAV association')
        role = next(iter(votes))[-1]
        if role in terminals:
            raise ValueError('Multiple objective volumes for one site need explicit handling')
        midpoint = [(bounds['min'][i]+bounds['max'][i])/2 for i in range(3)]
        representative = min(keys,key=lambda k:(math.dist(centers[k],midpoint),k))
        terminals[role] = {'nav_area_ids':keys, 'representative_nav_area':representative,
                           'objective_anchor_id':anchor['id'], 'bounds':bounds,
                           'basis':'NAV centroids inside source objective AABB', 'identity_basis':identity_basis}
        audit['objectives'].append({'anchor_id':anchor['id'],'site':role,'nav_areas':len(keys),
                                   'identity_label_votes':dict(votes),'identity_basis':identity_basis,'bounds_source':anchor.get('bounds_source')})
    if set(terminals) != {'T','CT','A','B'}:
        raise ValueError('Missing objective')
    audit['terminal_overlaps'] = {f'{a}/{b}':sorted(set(terminals[a]['nav_area_ids'])&set(terminals[b]['nav_area_ids']))
                                 for a,b in [('T','A'),('T','B'),('CT','A'),('CT','B'),('A','B')]}
    if audit['terminal_overlaps']['A/B']:
        raise ValueError('Objective volumes overlap; site identity is ambiguous')
    for row in audit['spawn_projections']:
        row['position_inside_objective_AABBs'] = [site for site in ('A','B') if all(
            terminals[site]['bounds']['min'][i] <= row['position'][i] <= terminals[site]['bounds']['max'][i]
            for i in range(3))]
    return terminals, audit


def witness_pairs(value):
    pairs = set()
    if isinstance(value,dict):
        if 'source_nav_area' in value and 'target_nav_area' in value:
            pairs.add((value['source_nav_area'],value['target_nav_area']))
        for item in value.values():
            pairs |= witness_pairs(item)
    elif isinstance(value,list):
        for item in value:
            pairs |= witness_pairs(item)
    return pairs


def contexts(annotation, graph, centers):
    region_members = {n['id']: n['nav_area_ids'] for n in graph['nodes']}
    meetings, chokes = [], []
    entries = sum((annotation.get(k,[]) for k in ['annotations','meetings','chokes','battlegrounds','front_proposals']),[])
    entries += [a for a in annotation.get('spatial_subdivision_proposals',[]) if a.get('initial_control_proposed')=='meeting' and a.get('supervision_mask')]
    entries += [a for a in annotation.get('regions',[]) if a.get('initial_control_proposed')=='meeting' and a.get('supervision_mask')]
    for index, entry in enumerate(entries):
        pairs = witness_pairs(entry)
        pieces = entry.get('surface_pieces',[])
        role = entry.get('kind') == 'meeting_area' or entry.get('role') == 'battleground_context' or entry.get('initial_control_proposed') == 'meeting'
        row = {'id':entry.get('id',f'Mcontext{index}'), 'title':entry.get('title',entry.get('source_place_label','Reviewed context')),
               'review_status':entry.get('review_status',entry.get('location_review_status')), 'supervision_scope':'context_only'}
        if role:
            ids = {p.get('nav_area_id',p.get('id')) for p in pieces}
            if not pieces:
                ids |= {k for region in entry.get('region_ids',[entry.get('region_id')]) for k in region_members.get(region,[])}
            ids &= set(centers)
            # Partial polygons do not imply that an entire NAV area is reviewed.
            exact = set()
            for piece in pieces:
                key = piece.get('nav_area_id',piece.get('id'))
                if key in centers:
                    triangles = np.asarray([[piece['corners'][0],piece['corners'][i],piece['corners'][i+1]] for i in range(1,len(piece['corners'])-1)])
                    if len(triangles) and min(triangle_distances(centers[key],triangles)) <= .01:
                        exact.add(key)
            row.update(nav_area_ids=sorted(ids), centroid_supported_nav_ids=sorted(exact if pieces else ids),
                       supervision_scope='reviewed_clipped_surface_centroids' if pieces else 'reviewed_place_context',
                       surface_pieces=pieces)
            if ids:
                meetings.append(row)
        elif pairs:
            row.update(directed_nav_pairs=sorted(pairs),supervision_scope='reviewed_recorded_transition_location')
            chokes.append(row)
    return meetings,chokes


def combine_paths(prefix, suffix):
    path = prefix + suffix[1:]
    return path if len(path)==len(set(path)) else None


def path_cells(path, centers, xy=128, z=64):
    """Sample spatial route support; NAV tessellation alone does not create novelty."""
    cells = set()
    for a,b in zip(path,path[1:]):
        p,q=np.asarray(centers[a]),np.asarray(centers[b])
        count=max(1,int(math.ceil(math.dist(p,q)/min(xy,z))))
        for t in np.linspace(0,1,count+1):
            s=p+t*(q-p)
            cells.add((math.floor(s[0]/xy),math.floor(s[1]/xy),math.floor(s[2]/z)))
    if len(path)==1:
        p=centers[path[0]];cells.add((math.floor(p[0]/xy),math.floor(p[1]/xy),math.floor(p[2]/z)))
    return cells


def diversity_select(candidates, centers, maximum=6, novelty=.35, cell_xy=128, cost_ratio=2):
    """Extraction deduplication only; thresholds are not map-quality criteria."""
    if not candidates:
        return []
    ordered = sorted(candidates,key=lambda c:(c['cost_units'],c['path']))
    supports = {tuple(c['path']):path_cells(c['path'],centers,xy=cell_xy) for c in ordered}
    selected=[ordered.pop(0)]
    while ordered and len(selected)<maximum:
        def score(candidate):
            support=supports[tuple(candidate['path'])]
            return min(1-len(support & supports[tuple(s['path'])])/max(len(support | supports[tuple(s['path'])]),1) for s in selected)
        candidate=ordered.pop(0)
        if candidate['cost_units']<=cost_ratio*max(selected[0]['cost_units'],1) and score(candidate)>=novelty:
            selected.append(candidate)
    return selected


def route_graph(net,start,excluded):
    excluded=set(excluded)
    if start not in excluded:
        return net.subgraph(set(net)-excluded)
    # Allow initial departure from the other site, but prohibit re-entry.
    graph=net.copy()
    graph.remove_edges_from([(a,b) for a,b in graph.edges if a not in excluded and b in excluded])
    return graph


def candidate_routes(net, start, goals, excluded, groups, meetings, chokes):
    graph = route_graph(net,start,excluded)
    if start not in graph:
        return []
    distance, prefix = nx.single_source_dijkstra(graph,start,weight='weight')
    goals=sorted(set(goals)&set(graph))
    if not goals:
        return []
    remaining,suffix=nx.multi_source_dijkstra(graph.reverse(copy=False),goals,weight='weight')
    pool={}
    def add(path,basis):
        if path and len(path)==len(set(path)) and not set(path[:-1])&set(goals):
            key=tuple(path)
            if key not in pool:
                pool[key]={'path':path,'cost_units':sum(graph[a][b]['weight'] for a,b in zip(path,path[1:])), 'candidate_bases':[]}
            if basis not in pool[key]['candidate_bases']:
                pool[key]['candidate_bases'].append(basis)
    available=[g for g in goals if g in distance]
    if not available:
        return []
    goal=min(available,key=lambda k:(distance[k],k));base=prefix[goal]
    add(base,'shortest_original_NAV_route')
    for title,members in groups:
        possible=set(members)&set(distance)&set(remaining)
        if possible:
            waypoint=min(possible,key=lambda k:(distance[k]+remaining[k],k))
            add(combine_paths(prefix[waypoint],list(reversed(suffix[waypoint]))),f'via:{title}')
    for context in meetings:
        possible=set(context['centroid_supported_nav_ids'])&set(distance)&set(remaining)
        if possible:
            waypoint=min(possible,key=lambda k:(distance[k]+remaining[k],k))
            add(combine_paths(prefix[waypoint],list(reversed(suffix[waypoint]))),f'meeting:{context["id"]}')
    for context in chokes:
        for a,b in context['directed_nav_pairs']:
            if a in prefix and b in suffix and graph.has_edge(a,b):
                add(prefix[a]+list(reversed(suffix[b])),f'choke:{context["id"]}')
    # Blocking entire coarse components is a proposal mechanism, not a quality label.
    for title,members in groups:
        blocked=set(members)
        if start in blocked or blocked&set(goals) or not blocked&set(base):
            continue
        alternative=graph.subgraph(set(graph)-blocked)
        d,p=nx.single_source_dijkstra(alternative,start,weight='weight')
        ends=set(goals)&set(d)
        if ends:
            goal=min(ends,key=lambda k:(d[k],k));add(p[goal],f'avoid:{title}')
    return list(pool.values())


def summarize_route(candidate, centers, labels, meetings, chokes, net):
    path=candidate['path'];seq=[]
    for k in path:
        label=labels[k] or 'unlabeled'
        if not seq or seq[-1]!=label:
            seq.append(label)
    events=[]
    for context in meetings:
        indices=[i for i,k in enumerate(path) if k in set(context['centroid_supported_nav_ids'])]
        if indices:
            events.append({'kind':'meeting_context','id':context['id'],'title':context['title'],
                           'first_path_index':indices[0],'path_indices':indices,'scope':context['supervision_scope']})
    for context in chokes:
        pairs=set(map(tuple,context['directed_nav_pairs']))
        indices=[i for i,pair in enumerate(zip(path,path[1:])) if pair in pairs]
        if indices:
            events.append({'kind':'choke_transition','id':context['id'],'title':context['title'],
                           'first_path_index':indices[0],'path_indices':indices,'scope':context['supervision_scope']})
    heights=[centers[k][2] for k in path]
    return {**candidate,'place_sequence':seq, 'centerline_xyz':[centers[k] for k in path],
            'height_span_units':max(heights)-min(heights),
            'accumulated_center_elevation_change_units':sum(abs(a-b) for a,b in zip(heights,heights[1:])),
            'unpaired_directed_nav_pairs':[[a,b] for a,b in zip(path,path[1:]) if not net.has_edge(b,a)],
            'reviewed_events':sorted(events,key=lambda e:(e['first_path_index'],e['id']))}


def route_family(path,labels,target,chokes):
    """Diagnostic approach family: stop at first target-site place context.

    Source names guide deduplication, not planner features or tactical approval.
    """
    stop=next((i for i,k in enumerate(path) if labels[k]==f'Bombsite{target}'),len(path)-1)
    sequence=[]
    for k in path[:stop+1]:
        label=labels[k]
        if label and (not sequence or sequence[-1]!=label):sequence.append(label)
    transitions=[]
    for i,pair in enumerate(zip(path,path[1:])):
        if i>=stop:break
        for choke in chokes:
            if pair in set(map(tuple,choke['directed_nav_pairs'])) and (not transitions or transitions[-1]!=choke['id']):
                transitions.append(choke['id'])
    return tuple(sequence),tuple(transitions)


def apply_purpose_reviews(result,reviews):
    for row in result['route_sets']:
        for route in row['routes']:
            path_hash=hashlib.sha256(json.dumps(route['path'],separators=(',',':')).encode()).hexdigest()
            route['ordered_nav_path_sha256']=path_hash
            route['tactical_role']='unknown'
            route['tactical_role_supervision_mask']=False
            route['opening_attack_target']=None
            matches=[r for r in reviews if r['map']==result['map'] and r['source_nav_sha256']==result['nav_sha256'] and r['ordered_nav_path_sha256']==path_hash]
            if len(matches)>1:raise ValueError('Conflicting route purpose reviews')
            if matches:
                review=matches[0]
                route['tactical_role']=review['tactical_role']
                route['tactical_role_supervision_mask']=True
                route['opening_attack_target']=review['opening_attack_target']
                route['role_condition']=review.get('condition')
                route['user_review_evidence']=review['evidence']
                route['review_scope']='tactical purpose only, not exact player trajectory'


def draw(result,areas,centers,output):
    width,height=1800,1250
    im=Image.new('RGB',(width,height),'#101a26');pen=ImageDraw.Draw(im)
    font=lambda size:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    pen.text((30,20),f"{result['map'].title()}: alternative routes on original NAV",font=font(30),fill='#eef4fb')
    pen.text((30,65),'Colored paths = route candidates, not all opening attacks. Yellow = reviewed encounter context; grey = source NAV.',font=font(18),fill='#b7c6d6')
    points=[p for a in areas.values() for p in a['corners']]
    lo=[min(p[i] for p in points) for i in range(2)];hi=[max(p[i] for p in points) for i in range(2)]
    colors=['#f0b349','#65cbef','#d096e8','#81deae','#ed7f94','#b0c4ff']
    for index,route_set in enumerate(result['route_sets'][:4]):
        ox,oy=30+(index%2)*890,110+(index//2)*555
        scale=min(750/(hi[0]-lo[0]),400/(hi[1]-lo[1]))
        def xy(p):return ox+30+(p[0]-lo[0])*scale,oy+60+(hi[1]-p[1])*scale
        pen.text((ox,oy),f"{route_set['from']} -> {route_set['to']}: {len(route_set['routes'])} displayed candidates",font=font(23),fill='#eef4fb')
        for area in sorted(areas.values(),key=lambda a:center(a)[2]):
            pen.polygon([xy(p) for p in area['corners']],fill='#344653')
        for context in result['meeting_contexts']:
            if context['surface_pieces']:
                pieces=context['surface_pieces']
            else:pieces=[areas[k] for k in context['nav_area_ids']]
            for piece in pieces:
                pen.polygon([xy(p) for p in piece['corners']],fill='#83783d')
        for i,route in enumerate(reversed(route_set['routes'])):
            color=colors[len(route_set['routes'])-1-i]
            if len(route['path'])>1:
                pen.line([xy(centers[k]) for k in route['path']],fill=color,width=3)
        for key in (route_set['from'],route_set['to']):
            p=centers[result['terminals'][key]['representative_nav_area']];x,y=xy(p)
            pen.ellipse((x-7,y-7,x+7,y+7),fill='#ffffff')
            pen.text((x+10,y-10),key,font=font(18),fill='#ffffff',stroke_width=2,stroke_fill='#101a26')
        ly=oy+60
        for i,route in enumerate(route_set['routes']):
            pen.line((ox+520,ly+10,ox+546,ly+10),fill=colors[i],width=4)
            pen.text((ox+557,ly),route['id'],font=font(18),fill=colors[i]);ly+=24
            role=route.get('tactical_role','unknown')
            detail='Conditional later flank' if role=='conditional_later_flank' else 'Purpose not reviewed'
            pen.text((ox+557,ly),detail,font=font(16),fill='#c5d2de');ly+=21
            if role=='conditional_later_flank':
                for line in textwrap.wrap(route['role_condition'],width=29):
                    pen.text((ox+557,ly),line,font=font(15),fill='#c5d2de');ly+=19
            ly+=16
        pen.text((ox,oy+480),' / '.join(f"{i+1}: {route['cost_units']:.0f}u" for i,route in enumerate(route_set['routes'])),font=font(17),fill='#b7c6d6')
    pen.text((30,1230),'Distances follow NAV centroids; no movement times, clearance, sightlines or gameplay-quality ranking inferred.',font=font(17),fill='#b7c6d6')
    im.save(output)


def extract(root,name,tolerance=64,source_graph=None):
    gp=Path(source_graph) if source_graph else root/f'output/coarse-layout-v1/{name}.json';graph=json.loads(gp.read_text())
    npth=root/f'output/{name}-nav.json'
    if digest(npth)!=graph['provenance']['nav_export_sha256']:
        raise ValueError('NAV provenance mismatch')
    nav=json.loads(npth.read_text())
    areas={a['id']:a for a in nav['areas'] if a['hull']==0 and a['movable_mesh_id']==0xffffffff}
    centers={k:center(a) for k,a in areas.items()}
    original_path=Path(graph['coarse_provenance']['source_graph'])
    if digest(original_path)!=graph['coarse_provenance']['source_sha256']:
        raise ValueError('Original spatial NAV graph hash mismatch')
    original=json.loads(original_path.read_text())
    labels={k:n['label'] for n in original['nodes'] for k in n['nav_area_ids']}
    if set(centers)!=set(labels):raise ValueError('NAV partition mismatch')
    net=nx.DiGraph();net.add_nodes_from(areas)
    for key,area in areas.items():
        for connection in area['connections']:
            other=connection['target']
            if other in areas:net.add_edge(key,other,weight=math.dist(centers[key],centers[other]))
    terminals,audit=associations(graph,areas,centers,labels,tolerance)
    annotation_path=root/'output/annotations'/ANNOTATIONS[name] if name in ANNOTATIONS else None
    annotation=json.loads(annotation_path.read_text()) if annotation_path else {}
    meetings,chokes=contexts(annotation,graph,centers)
    # Coarse cells bound waypoint candidates without treating place names as roles.
    groups=[(n['id'],n['nav_area_ids']) for n in graph['nodes']]
    route_sets=[]
    for source,target in PAIRS:
        other_site='B' if target=='A' else 'A'
        # A small trigger alone would admit paths through the other site's yard.
        if source=='T':
            excluded=sorted({k for k,label in labels.items() if label==f'Bombsite{other_site}'} | set(terminals[other_site]['nav_area_ids']))
            exclusion_scope='other objective AABB plus original named site context'
        elif source=='CT':
            excluded=terminals[other_site]['nav_area_ids']
            exclusion_scope='other objective AABB; adjoining defender courtyard remains available'
        else:
            excluded=sorted({k for k,label in labels.items() if label=='TSpawn'} | set(terminals['T']['nav_area_ids']))
            exclusion_scope='source T spawn place context and supported spawn polygons'
        start=terminals[source]['representative_nav_area'];goals=terminals[target]['nav_area_ids']
        candidates=candidate_routes(net,start,goals,excluded,groups,meetings,chokes)
        families={}
        for candidate in sorted(candidates,key=lambda c:(c['cost_units'],c['path'])):
            family=route_family(candidate['path'],labels,target,chokes)
            if not family[0] and not family[1]:
                family=('unlabeled_spatial_candidate',tuple(candidate['path']))
            if family not in families:families[family]=candidate
        family_candidates=list(families.values())
        selected=diversity_select(family_candidates,centers)
        routes=[summarize_route(c,centers,labels,meetings,chokes,net) for c in selected]
        for i,route in enumerate(routes):route['id']=f'{source}-{target}-{i+1}'
        sensitivity=[{'cell_xy_units':cell,'minimum_spatial_difference':novelty,
                      'selected_count':len(diversity_select(family_candidates,centers,novelty=novelty,cell_xy=cell))}
                     for cell in (128,256) for novelty in (.2,.35,.5)]
        route_sets.append({'from':source,'to':target,'fixed_start_nav_area':start,'goal_nav_areas':goals,
                           'excluded_nav_areas':excluded,'initial_excluded_context_exit_allowed':start in excluded,
                           'exclusion_scope':exclusion_scope,'candidate_count':len(candidates),'candidates':candidates,'diagnostic_route_family_count':len(families),'routes':routes,
                           'extraction_sensitivity':sensitivity,'status':'routes_extracted' if routes else 'unresolved'})
    result={'map':name,'task':'original_NAV_alternative_route_targets','model_training_performed':False,
            'whole_map_planner_training_ready':False,'terminals':terminals,'association_audit':audit,
            'meeting_contexts':meetings,'choke_contexts':chokes,'route_sets':route_sets,
            'nav_area_count':len(areas),'directed_nav_connections':net.number_of_edges(),'ladders_not_modeled':nav['ladder_count'],
            'source_graph':str(gp.resolve()),'source_graph_sha256':digest(gp),'nav_export':str(npth.resolve()),'nav_sha256':digest(npth),
            'annotation_source':str(annotation_path.resolve()) if annotation_path else None,'annotation_sha256':digest(annotation_path) if annotation_path else None,
            'original_spatial_graph':str(original_path.resolve()),'original_spatial_graph_sha256':digest(original_path),
            'parameters':{'spawn_surface_association_tolerance_units':tolerance,'route_spatial_xy_units':128,
                          'route_spatial_z_units':64,'minimum_pairwise_Jaccard_difference':.35,'maximum_routes_per_pair':6,'maximum_shortest_route_cost_ratio':2},
            'source_place_names_are_diagnostic_not_model_inputs':True}
    return result,areas,centers,net


def run(root,output):
    output.mkdir(parents=True,exist_ok=False)
    review_path=root/'route-purpose-reviews.json'
    reviews=json.loads(review_path.read_text())['reviews'] if review_path.exists() else []
    results=[]
    lines=['# Original NAV alternative-route extraction','','No model training. Five approved maps only; reserved evaluation maps were not loaded.','',
           'Spawn positions are associated with original polygon surfaces. Objective association uses source volume bounds and polygon centroids, rather than broad coarse place regions.', '',
           '| Map | T-A | T-B | CT-A | CT-B | A-B | B-A | Max spawn-to-surface distance |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in MAPS:
        result,areas,centers,net=extract(root,name)
        apply_purpose_reviews(result,reviews)
        # Every stored transition must be recorded and each path must be simple.
        for row in result['route_sets']:
            for route in row['routes']:
                path=route['path']
                assert len(path)==len(set(path)) and path[0]==row['fixed_start_nav_area'] and path[-1] in row['goal_nav_areas']
                excluded=set(row['excluded_nav_areas'])
                if row['initial_excluded_context_exit_allowed']:
                    exited=False
                    for k in path:
                        if k not in excluded:exited=True
                        assert not (exited and k in excluded)
                else:assert not set(path)&excluded
                assert not set(path[:-1])&set(row['goal_nav_areas'])
                assert all(net.has_edge(a,b) for a,b in zip(path,path[1:]))
                assert math.isclose(route['cost_units'],sum(net[a][b]['weight'] for a,b in zip(path,path[1:])))
        (output/f'{name}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        draw(result,areas,centers,output/f'{name}.png')
        counts=[len(row['routes']) for row in result['route_sets']]
        maximum=max(a['surface_distance_units'] for a in result['association_audit']['spawn_projections'])
        lines.append(f"| {name} | {' | '.join(map(str,counts))} | {maximum:.2f} units |")
        results.append(result)
        print(json.dumps({'map':name,'selected_route_counts':counts,'maximum_spawn_surface_distance':maximum}),flush=True)
    lines += ['', 'Counts are bounded extraction candidates, not the true number of tactical options or a quality score. The cap and spatial deduplication settings are explicitly stored; sensitivity checks accompany every pair.', '',
        '## What changed', '',
        'Cobblestone CT spawn and A are no longer conflated simply because they share a coarse region. Some source CT spawns actually lie inside the A objective AABB; these legitimate overlaps are preserved and audited. If a defender starts inside the excluded other-site context, departure is allowed but re-entry is prohibited. Route starts remain fixed across each pair so changing spawn positions cannot masquerade as an alternative route. Goal areas are inside the actual objective AABB.', '',
        'Candidates include shortest routes, routes through coarse spatial waypoints, reviewed meeting contexts and exact reviewed directed choke witnesses, plus bypasses after blocking an intersected coarse component. Repeated-node detours and paths continuing after reaching their objective are rejected. T approaches exclude the other site context; CT access excludes its objective AABB while allowing adjoining defensive courtyards. Original pre-coarsening place labels avoid inherited-label artifacts. Candidates sharing the same named approach and reviewed choke sequence before first target-site context are deduplicated, then sampled spatial support and a documented length budget limit variants. These are diagnostic extraction settings, not map-quality rules or planner input labels.', '',
        'Meeting hits use NAV centroids inside reviewed clipped surfaces where available; place-only review remains context-only. Choke hits require an exact reviewed directed NAV pair. Partial surface membership is not expanded into full-area supervision.', '',
        '## Reviewable route signatures', '']
    for result in results:
        lines += [f"### {result['map']}", '', f"![Alternative routes]({result['map']}.png)", '']
        for row in result['route_sets']:
            lines.append(f"**{row['from']} -> {row['to']}**: {row['candidate_count']} simple candidate paths; {len(row['routes'])} spatially distinct displayed targets.")
            for route in row['routes']:
                events='; '.join(f"{e['id']} {e['title']} ({e['scope']})" for e in route['reviewed_events']) or 'no reviewed context intersected'
                purpose=route['tactical_role']+(f"; {route['role_condition']}" if route.get('role_condition') else '')
                lines.append(f"- {route['id']}: {' -> '.join(route['place_sequence'])}; {route['cost_units']:.0f} centroid-distance units; height span {route['height_span_units']:.0f}. Tactical role: {purpose}. Context evidence: {events}.")
            lines.append('')
    lines += ['## Limits and training gate', '',
        '- This is a bounded candidate extractor, not an exhaustive search or human-approved ranking of useful routes. Distinct paths can still represent flanks, retakes or unreasonable opening approaches; their purpose is not inferred.',
        '- Original NAV centroid paths preserve directed adjacency but do not establish physical doorway clearance, collision, movement time, arrival fronts or sightlines. Source NAV freshness relative to repaired VMAP remains unverified. Ladders are excluded.',
        '- Fan triangulation assumes convex NAV polygons. Objective AABB containment is a volume proxy, not exact trigger brush geometry. Spawn projections within tolerance do not certify player reachability.',
        '- Source place names and map identities remain diagnostic text, not planner input features. Five maps are not a broad generalization dataset.',
        '- Unannotated space is unknown; absence of an event is not a negative tactical label. Reviewed spatial contexts do not become round-dependent first-control/timing labels.',
        '- The Train Ivy-to-CT-side-to-B route is user-reviewed as a conditional later flank when A is too dangerous from Ivy, not an opening B attack target. This correction is matched by original NAV and ordered route hashes; other route purposes remain unknown.',
        '- Whole-map planner training is gated on reviewing the extracted route organizations and separating opening access, alternative attacks, rotations and local positioning. No new training run or generated Hammer map was produced.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (output/'manifest.json').write_text(json.dumps({'maps':list(MAPS),'model_training_performed':False,
        'planner_training_ready':False,'extractor_sha256':digest(Path(__file__)),
        'route_purpose_review_source':str(review_path.resolve()) if review_path.exists() else None,
        'route_purpose_review_sha256':digest(review_path) if review_path.exists() else None,
        'map_targets':[{'map':r['map'],'file':f"{r['map']}.json",'sha256':digest(output/f"{r['map']}.json")} for r in results]},indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(Path(__file__).resolve().parent,args.output)
