"""Evidence-first route drafts for approved training maps, without control labels."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import networkx as nx
from PIL import Image, ImageDraw, ImageFont


def build(graph):
    if graph['dataset_role'] != 'training':
        raise ValueError('Reserved evaluation maps must not enter annotation training drafts')
    nodes = {n['id']: n for n in graph['nodes']}
    anchors = graph['anchors']
    def associations(classname):
        return sorted({r for a in anchors if a['classname'] == classname for r in a['region_ids']})
    ct = associations('info_player_counterterrorist')
    t = associations('info_player_terrorist')
    sites = {}
    for label in ['BombsiteA', 'BombsiteB']:
        sites[label] = sorted({r for a in anchors if a['classname'] == 'func_bomb_target'
                               for r in a['region_ids'] if nodes[r]['label'] == label})
    if not ct or not t or any(not v for v in sites.values()):
        raise ValueError('Missing spawn/objective evidence')
    edges = {(e['source'], e['target']): e for e in graph['edges']}
    routes = []
    for title, starts, ends, excluded in [
        ('CT to A without B', ct, sites['BombsiteA'], {'BombsiteB'}),
        ('CT to B without A', ct, sites['BombsiteB'], {'BombsiteA'}),
        ('T to A without B', t, sites['BombsiteA'], {'BombsiteB'}),
        ('T to B without A', t, sites['BombsiteB'], {'BombsiteA'}),
        ('A to B without T spawn', sites['BombsiteA'], sites['BombsiteB'], {'TSpawn'}),
        ('B to A without T spawn', sites['BombsiteB'], sites['BombsiteA'], {'TSpawn'}),
    ]:
        permitted = {key for key, n in nodes.items() if n['label'] not in excluded}
        net = nx.DiGraph()
        net.add_nodes_from(permitted)
        for (a, b), edge in edges.items():
            if a in permitted and b in permitted:
                if not edge['witnesses']:
                    raise ValueError('Missing directed edge evidence')
                net.add_edge(a, b, weight=math.dist(nodes[a]['position'], nodes[b]['position']))
        origins = [r for r in starts if r in permitted]
        lengths, paths = nx.multi_source_dijkstra(net, origins) if origins else ({}, {})
        available = [r for r in ends if r in paths]
        route = {'title': title, 'start_candidates': starts, 'end_candidates': ends,
                 'excluded_place_labels': sorted(excluded), 'review_status': 'pending_purpose_review'}
        if not available:
            route.update(status='unresolved', reason='No directed path with stated place-label exclusions; this is not a map-quality verdict')
            full = nx.DiGraph()
            full.add_nodes_from(nodes)
            for (a,b), edge in edges.items():
                full.add_edge(a,b,weight=math.dist(nodes[a]['position'],nodes[b]['position']))
            unrestricted_lengths, unrestricted_paths = nx.multi_source_dijkstra(full, starts)
            reachable = [r for r in ends if r in unrestricted_paths]
            if reachable:
                target = min(reachable,key=lambda r: unrestricted_lengths[r])
                diagnostic = unrestricted_paths[target]
                route['unrestricted_connectivity_diagnostic'] = {
                    'region_path': diagnostic, 'place_labels': [nodes[r]['label'] for r in diagnostic],
                    'links': [{'source':a,'target':b,'recorded_nav_witness':edges[a,b]['witnesses'][0]}
                              for a,b in zip(diagnostic,diagnostic[1:])],
                    'excluded_place_regions': [r for r in diagnostic if nodes[r]['label'] in excluded],
                    'excluded_origin_regions': [r for r in starts if nodes[r]['label'] in excluded],
                    'interpretation': 'Source place groups may overlap spawn access and plant-volume associations. Resolve at NAV-area scale before judging independent access.'}
        else:
            target = min(available, key=lambda r: lengths[r])
            path = paths[target]
            route.update(status='recorded_directed_route' if len(path)>1 else 'overlapping_anchor_regions', region_path=path,
                         place_labels=[nodes[r]['label'] for r in path],
                         links=[{'source': a, 'target': b, 'recorded_nav_witness': edges[a,b]['witnesses'][0]}
                                for a,b in zip(path,path[1:])])
            if len(path)==1:
                route['reason']='Spawn and objective associations share a coarse region; no traversed link establishes an independent access route.'
        routes.append(route)
    groups = []
    for label in sorted({n['label'] for n in graph['nodes'] if n['label']}):
        ids = [n['id'] for n in graph['nodes'] if n['label'] == label]
        groups.append({'source_place_label': label, 'region_ids': ids,
                       'route_contexts': [r['title'] for r in routes if set(ids)&set(r.get('region_path',[]))],
                       'initial_control_target': None, 'meeting_target': None, 'supervision_mask': False})
    return {'map': graph['map'], 'status': 'pending_gameplay_interpretation_review',
            'training_eligible': False, 'model_training_performed': False,
            'place_groups': groups, 'routes': routes,
            'spawn_anchor_associations': {'CT': ct, 'T': t}, 'objective_associations': sites,
            'anchor_evidence': anchors, 'source_graph': graph,
            'limits': ['Paths minimize coarse centroid edge weights, not travel time or exposure.',
                       'Spawn associations retain source uncertainty; nearest-centroid is diagnostic only.',
                       'A recorded path is one connectivity example, not the only or preferred tactical route.',
                       'No initial-control, staging or battlefront labels are inferred from route membership.',
                       'Place groups must not be contracted into rooms or traversability nodes.']}


def draw(draft, output):
    graph = draft['source_graph']
    im = Image.new('RGB', (1500, 1150), '#101a26')
    pen = ImageDraw.Draw(im)
    def font(size):
        return ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
    points = [p for s in graph['nav_polygons'] for p in s['corners']]
    lo = [min(p[i] for p in points) for i in range(2)]
    hi = [max(p[i] for p in points) for i in range(2)]
    scale = min(875/(hi[0]-lo[0]), 940/(hi[1]-lo[1]))
    def xy(p):
        return 35+(p[0]-lo[0])*scale, 120+(hi[1]-p[1])*scale
    associations = draft['spawn_anchor_associations']
    sites = draft['objective_associations']
    for surface in sorted(graph['nav_polygons'], key=lambda p: sum(c[2] for c in p['corners'])):
        r = surface['region_id']
        color = '#465563'
        if r in associations['CT']: color = '#168cbb'
        if r in associations['T']: color = '#be902e'
        if r in sites['BombsiteA']: color = '#cf727d'
        if r in sites['BombsiteB']: color = '#9c87cc'
        pen.polygon([xy(c) for c in surface['corners']], fill=color)
    for route in draft['routes']:
        color = '#69cbef' if route['title'].startswith('CT') else '#efba51' if route['title'].startswith('T ') else '#dd9bee'
        for link in route.get('links', []):
            pen.line([xy(c) for c in link['recorded_nav_witness']['source_edge_endpoints']], fill=color, width=4)
    representatives = {}
    for n in graph['nodes']:
        label = n['label']
        if label and (label not in representatives or len(n['nav_area_ids']) > len(representatives[label]['nav_area_ids'])):
            representatives[label] = n
    for label, n in representatives.items():
        x,y = xy(n['position'])
        box = pen.textbbox((x,y),label,font=font(14))
        pen.rectangle((box[0]-2,box[1]-1,box[2]+2,box[3]+1),fill='#101a26')
        pen.text((x,y),label,font=font(14),fill='#eef2fa')
    pen.text((30,25),f"{graph['map']}: source places and route evidence",font=font(29),fill='#edf2fa')
    pen.text((30,70),'Colors mark anchor-associated regions and witnessed route interfaces, not initial control.',font=font(18),fill='#becbda')
    y=155
    for title,color in [('CT spawn associations','#168cbb'),('T spawn associations','#be902e'),('A objective associations','#cf727d'),('B objective associations','#9c87cc')]:
        pen.rectangle((960,y,983,y+23),fill=color)
        pen.text((998,y),title,font=font(19),fill='#eef2fa');y+=48
    pen.text((960,385),'Directed route examples',font=font(23),fill='#eef2fa')
    for i,route in enumerate(draft['routes']):
        y=435+i*62
        pen.text((960,y),route['title'],font=font(19),fill='#eef2fa')
        detail=f"{len(route.get('links', []))} witnessed links" if route['status']=='recorded_directed_route' else 'Coarse anchor overlap' if route['status']=='overlapping_anchor_regions' else 'Unresolved'
        pen.text((960,y+26),detail,font=font(16),fill='#becbda')
    for i,line in enumerate(['Grey = source NAV, gameplay role unassigned.', 'Thin colored marks = NAV edge witnesses.',
                             'No route centerlines or arrival times inferred.', 'Control / meeting labels remain unassigned.',
                             f"Source ladders not modeled: {graph['summary'].get('ladders_not_modeled', 'see provenance')}",
                             'No new training or source-map changes.']):
        pen.text((960,845+i*35),line,font=font(16),fill='#becbda')
    im.save(output)


def run(source, output):
    if output.exists(): raise ValueError('Use a new artifact directory')
    raw = source.read_bytes()
    draft = build(json.loads(raw))
    draft.update(source_graph_sha256=hashlib.sha256(raw).hexdigest(),
                 annotator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True)
    (output/'backbone.json').write_text(json.dumps(draft,indent=2))
    draw(draft,output/'overview.png')
    lines = [f"# {draft['map']} evidence-first draft", '',
             'Source spawn/objective associations and directed NAV links are recorded evidence. Initial control, staging and encounter roles remain unassigned.', '',
             '## Route examples', '']
    for r in draft['routes']:
        labels=list(dict.fromkeys(str(x) for x in r.get('place_labels',[])))
        lines.append(f"- {r['title']}: {r['status']}. Places encountered: {', '.join(labels)}.")
        if 'unrestricted_connectivity_diagnostic' in r:
            diag=r['unrestricted_connectivity_diagnostic']
            lines.append('  Unrestricted diagnostic: '+ ' -> '.join(str(s) for s in diag['place_labels'])+'. '+diag['interpretation'])
    lines += ['', '## Limits', '']+[f'- {s}' for s in draft['limits']]
    lines += ['', 'Review can be limited to anything visibly wrong or familiar. An unsure response does not approve tactical labels. Geometry and route evidence can support the prototype while uncertain gameplay labels stay masked.']
    (output/'review.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'map':draft['map'],'routes':[{k:r[k] for k in ['title','status']} for r in draft['routes']], 'training_eligible':False}))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
