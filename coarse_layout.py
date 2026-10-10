"""Conservatively merge navigation segments into larger connected layout areas.

This is deterministic data preparation, not room recognition or model training.
"""
import argparse
import copy
from collections import defaultdict
import hashlib
import heapq
import json
import math
from pathlib import Path

from whole_map_layout import bounds, diagram


def interface_support(witnesses):
    # Unique source edges prevent repeated neighbor records counting twice.
    # This remains tessellation-dependent support, NOT portal clearance.
    lengths = {}
    for w in witnesses:
        if 'source_edge_length_xy' not in w or 'target_edge_length_xy' not in w: continue
        key = w['source_nav_area'],w['source_edge']
        lengths[key] = max(lengths.get(key,0),min(w['source_edge_length_xy'],w['target_edge_length_xy']))
    return sum(lengths.values())


def coarsen(graph, minimum_support=96, maximum_span=1536, maximum_height=192, maximum_area=750000):
    clusters = {n['id']:{'members':{n['id']},'labels':{n['label']} if n['label'] else set(),
                        'bounds':copy.deepcopy(n['bounds']),'area':n['summed_nav_polygon_area_xy'],
                        'version':0} for n in graph['nodes']}
    interfaces = {(e['source'],e['target']):copy.deepcopy(e['witnesses']) for e in graph['edges']}
    neighbors = defaultdict(set)
    for a,b in interfaces: neighbors[a].add(b); neighbors[b].add(a)
    heap = []; merges = []

    def candidate(a,b):
        if a==b or a not in clusters or b not in clusters: return None
        if (a,b) not in interfaces or (b,a) not in interfaces: return None
        x,y = clusters[a],clusters[b]
        if len(x['labels']|y['labels'])>1: return None
        box = bounds([x['bounds']['min'],x['bounds']['max'],y['bounds']['min'],y['bounds']['max']])
        span = [box['max'][i]-box['min'][i] for i in range(3)]
        if max(span[:2])>maximum_span or span[2]>maximum_height or x['area']+y['area']>maximum_area: return None
        support = min(interface_support(interfaces[a,b]),interface_support(interfaces[b,a]))
        if support < minimum_support: return None
        return support/max(math.sqrt(x['area'])+math.sqrt(y['area']),1),support,box

    def enqueue(a,b):
        a,b = sorted((a,b)); result = candidate(a,b)
        if result: heapq.heappush(heap,(-result[0],a,b,clusters[a]['version'],clusters[b]['version']))

    for a,b in sorted({tuple(sorted(pair)) for pair in interfaces}): enqueue(a,b)
    while heap:
        _,a,b,va,vb = heapq.heappop(heap)
        if a not in clusters or b not in clusters or clusters[a]['version']!=va or clusters[b]['version']!=vb: continue
        result = candidate(a,b)
        if result is None: continue
        x,y = clusters[a],clusters[b]; adjacent = (neighbors[a]|neighbors[b])-{a,b}
        merges.append({'survivor':a,'absorbed':b,'interface_support_units':result[1],
                       'reason':'bidirectional recorded interface; compatible labels; size/elevation caps'})
        for n in adjacent:
            for source,target in ((a,n),(n,a)):
                old = (b,n) if source==a else (n,b)
                other = interfaces.pop(old,[])
                if other: interfaces.setdefault((source,target),[]).extend(other)
            neighbors[n].discard(b); neighbors[n].add(a)
        interfaces.pop((a,b),None); interfaces.pop((b,a),None)
        neighbors[a] = adjacent; neighbors.pop(b,None)
        x['members'] |= y['members']; x['labels'] |= y['labels']; x['area'] += y['area']
        x['bounds'] = result[2]; x['version'] += 1; del clusters[b]
        for n in sorted(adjacent): enqueue(a,n)
    original = {n['id']:n for n in graph['nodes']}; owner = {}; nodes = []
    for rid,c in sorted(clusters.items()):
        members = [original[k] for k in sorted(c['members'])]
        for key in c['members']: owner[key] = rid
        total = c['area']; box = c['bounds']
        position = [sum(n['position'][i]*n['summed_nav_polygon_area_xy'] for n in members)/total
                    if total else sum(n['position'][i] for n in members)/len(members) for i in range(3)]
        nodes.append({'id':rid,'source_region_ids':sorted(c['members']),
                      'nav_area_ids':sorted(k for n in members for k in n['nav_area_ids']),
                      'label':next(iter(c['labels'])) if c['labels'] else None,
                      'position':position,'bounds':box,'summed_nav_polygon_area_xy':total,
                      'span_xy_units':[box['max'][i]-box['min'][i] for i in range(2)],
                      'height_range_units':box['max'][2]-box['min'][2],
                      'anchor_ids':sorted({k for n in members for k in n['anchor_ids']})})
    edges = [{'source':a,'target':b,'witnesses':w,'reverse_edge_exists':(b,a) in interfaces,
              'evidence':'recorded_directed_nav_connection','interface_support_units':interface_support(w)}
             for (a,b),w in sorted(interfaces.items())]
    result = copy.deepcopy(graph); result['nodes'] = nodes; result['edges'] = edges
    for polygon in result['nav_polygons']: polygon['region_id'] = owner[polygon['region_id']]
    for anchor in result['anchors']: anchor['region_ids'] = sorted({owner[r] for r in anchor['region_ids']})
    for route in result['spawn_objective_routes']:
        if route['route']:
            path = []
            for r in route['route']['region_path']:
                if not path or path[-1]!=owner[r]: path.append(owner[r])
            route['route']['region_path'] = path
    result['task'] = 'coarse_whole_map_navigation_layout'
    result['coarsening'] = {'method':'greedy_bidirectional_interface_support','parameters':
                          {'minimum_interface_support_units':minimum_support,'maximum_xy_span_units':maximum_span,
                           'maximum_height_span_units':maximum_height,'maximum_summed_nav_area_xy':maximum_area},
                          'merge_history':merges,'source_region_owner':owner,'architectural_rooms_recognized':False}
    result['summary']['source_regions'] = len(graph['nodes']); result['summary']['regions'] = len(nodes)
    result['summary']['directed_edges'] = len(edges)
    result['summary']['unpaired_directed_edges'] = sum(not e['reverse_edge_exists'] for e in edges)
    # Recompute cycle rank after contraction; preserved old value would be misleading.
    pairs = {tuple(sorted((e['source'],e['target']))) for e in edges}
    result['summary']['undirected_cycle_rank'] = len(pairs)-len(nodes)+graph['summary']['weak_components']
    result['limitations'] += ['Coarse areas merge only through bidirectional recorded interfaces; each resulting area remains strongly connected.',
                              'Merge support sums unique NAV edge samples and is tessellation-dependent; it is not verified corridor or portal width.',
                              'Different inferred place labels are not merged. Unknown regions may inherit a label from an adjacent named region.',
                              'Size caps prevent very broad merges but do not turn navigation areas into architectural rooms.']
    result['feature_status']['region_size'] = 'coarse connected NAV area and bounds, not room dimensions'
    # Partition and every original inter-area transition must survive as either internal or explicit.
    original_ids = {k for n in graph['nodes'] for k in n['nav_area_ids']}
    new_ids = [k for n in nodes for k in n['nav_area_ids']]
    if set(new_ids)!=original_ids or len(new_ids)!=len(original_ids): raise ValueError('Partition conservation failed')
    before = {(w['source_nav_area'],w['target_nav_area'],w.get('source_edge'),w.get('target_edge'))
              for e in graph['edges'] if owner[e['source']]!=owner[e['target']] for w in e['witnesses']}
    after = {(w['source_nav_area'],w['target_nav_area'],w.get('source_edge'),w.get('target_edge'))
             for e in edges for w in e['witnesses']}
    if before!=after: raise ValueError('Directed witness conservation failed')
    return result


def build(source,output):
    if output.exists(): raise ValueError('Choose a new output directory')
    manifest = json.loads((source/'manifest.json').read_text())
    if any(r['map'] not in manifest['training_maps'] for r in manifest['maps']): raise ValueError('Unexpected dataset role')
    output.mkdir(parents=True); records = []
    for row in manifest['maps']:
        path = source/row['graph']; raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']: raise ValueError('Source graph hash mismatch')
        graph = json.loads(raw)
        if graph['dataset_role']!='training': raise ValueError('Only training sources allowed')
        result = coarsen(graph)
        result['coarse_provenance'] = {'source_graph':str(path.resolve()),'source_sha256':row['sha256'],
                                      'coarsener_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        destination = output/path.name
        destination.write_text(json.dumps(result,indent=2),encoding='utf-8')
        diagram(result,row['map']+' (coarse areas)',destination.with_suffix('.svg'))
        record = {'map':row['map'],'graph':destination.name,
                  'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),**result['summary']}
        records.append(record); print(json.dumps(record),flush=True)
    (output/'manifest.json').write_text(json.dumps({'schema_version':1,'training_maps':manifest['training_maps'],
         'maps':records,'model_training_performed':False,'architectural_rooms_recognized':False,
         'validation_test_and_reserved_maps_not_loaded':True,'ready_for_whole_map_model_training':False},indent=2),encoding='utf-8')
    lines = ['# Coarse connected layout areas','','Data preparation only; no new model training.','',
             '| Map | Original segments | Coarse areas | Directed links | Objective routes |',
             '| --- | ---: | ---: | ---: | ---: |']
    for r in records: lines.append(f'| {r["map"]} | {r["source_regions"]} | {r["regions"]} | {r["directed_edges"]} | {r["available_routes"]}/4 |')
    lines += ['', 'The Cache and Cobblestone objective gaps were floating-point boundary artifacts, corrected upstream using an explicit 0.001 Hammer-unit tolerance. All six maps now have recorded static-NAV paths for all four diagnostic team/objective combinations. No new navigation links were created.',
              '', 'Coarse areas merge across broad bidirectional NAV interfaces, retain inferred place-label boundaries, and respect area/elevation/span caps. Every NAV polygon is assigned exactly once and every surviving directed transition retains its original witnesses. This produces larger navigation neighborhoods, not architectural rooms.',
              '', 'Cover, sightlines, architectural boundaries, ladders, movable navigation and NAV freshness remain unresolved. Interface support is not clearance. These constraints must be addressed before claiming a complete whole-map generator.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); build(args.source,args.output)
