"""Aggregate recorded NAV connections into a directed graph of map regions."""
import argparse
from collections import Counter, defaultdict
import hashlib
import heapq
import json
import math
from pathlib import Path


def center(area):
    return [sum(p[i] for p in area['corners']) / len(area['corners']) for i in range(3)]


def build_graph(nav, reference, hull=0):
    areas = {a['id']: a for a in nav['areas'] if a['hull'] == hull and a['movable_mesh_id'] == 0xffffffff}
    if not areas:
        raise ValueError(f'No static navigation areas for hull {hull}')
    volumes = [a for a in reference['spatial']['gameplay_anchors'] if a['classname'] == 'env_cs_place' and a['geometry_bounds']]
    labels, assignments = {}, []
    centers = {key: center(a) for key, a in areas.items()}
    for key, point in centers.items():
        candidates = [a for a in volumes if all(a['geometry_bounds']['min'][i] <= point[i] <= a['geometry_bounds']['max'][i] for i in range(3))]
        names = {a['properties'].get('place_name') for a in candidates}
        names.discard(None)
        # Conflicting overlaps stay unknown rather than making a naming decision.
        labels[key] = next(iter(names)) if len(names) == 1 else None
        assignments.append({'area_id': key, 'label': labels[key], 'candidate_labels': sorted(names), 'position': point})
    dangling, links = [], []
    for key, area in areas.items():
        for connection in area['connections']:
            target = connection['target']
            if target not in areas:
                dangling.append({'source': key, 'target': target})
                continue
            links.append((key, target))
    # Collapse only strongly connected areas, so a region cannot hide a one-way barrier.
    forward, reverse = defaultdict(list), defaultdict(list)
    for source, target in links:
        if labels[source] == labels[target]:
            forward[source].append(target)
            reverse[target].append(source)
    visited, order = set(), []
    for seed in sorted(areas):
        if seed in visited:
            continue
        stack = [(seed, False)]
        while stack:
            key, done = stack.pop()
            if done:
                order.append(key)
            elif key not in visited:
                visited.add(key)
                stack.append((key, True))
                stack.extend((n, False) for n in forward[key] if n not in visited)
    visited, components = set(), {}
    for seed in reversed(order):
        if seed in visited:
            continue
        members, stack = [], [seed]
        while stack:
            key = stack.pop()
            if key not in visited:
                visited.add(key)
                members.append(key)
                stack.extend(reverse[key])
        components[min(members)] = members
    region_for, nodes = {}, []
    label_instances = Counter()
    for root, members in sorted(components.items()):
        label = labels[members[0]]
        base = label or 'Unlabeled'
        label_instances[base] += 1
        region = f'{base}:{label_instances[base]}'
        for key in members:
            region_for[key] = region
        nodes.append({'id': region, 'label': label, 'nav_area_ids': sorted(members),
                      'position': [sum(centers[k][i] for k in members) / len(members) for i in range(3)]})
    grouped = defaultdict(list)
    for source, target in set(links):
        a, b = region_for[source], region_for[target]
        if a != b:
            grouped[a, b].append([source, target])
    edges = [{'source': a, 'target': b, 'nav_connection_count': len(witnesses), 'witness_nav_pairs': sorted(witnesses),
              'evidence': 'recorded_nav_connection', 'reverse_edge_exists': (b, a) in grouped}
             for (a, b), witnesses in sorted(grouped.items())]
    spawns = []
    for anchor in reference['spatial']['gameplay_anchors']:
        if anchor['classname'] not in ('info_player_terrorist', 'info_player_counterterrorist'):
            continue
        key = min(centers, key=lambda k: math.dist(anchor['position'], centers[k]))
        distance = math.dist(anchor['position'], centers[key])
        spawns.append({'node_id': anchor['node_id'], 'classname': anchor['classname'], 'nearest_nav_area': key,
                       'nearest_region': region_for[key], 'center_distance': distance, 'association': 'nearest_centroid_diagnostic_only'})
    named = sum(label is not None for label in labels.values())
    adjacency = defaultdict(set)
    for source, target in links:
        adjacency[source].add(target)
    examples = []
    for start_name in ('TSpawn', 'CTSpawn'):
        seeds = [key for key in areas if labels[key] == start_name]
        if not seeds:
            continue
        average = [sum(centers[k][i] for k in seeds) / len(seeds) for i in range(3)]
        seed = min(seeds, key=lambda k: math.dist(centers[k], average))
        for target_name in ('BombsiteA', 'BombsiteB'):
            distance, previous, queue = {seed: 0}, {}, [(0, seed)]
            found = None
            while queue:
                cost, key = heapq.heappop(queue)
                if cost != distance[key]:
                    continue
                if labels[key] == target_name:
                    found = key
                    break
                for neighbor in sorted(adjacency[key]):
                    candidate = cost + math.dist(centers[key], centers[neighbor])
                    if candidate < distance.get(neighbor, math.inf):
                        distance[neighbor], previous[neighbor] = candidate, key
                        heapq.heappush(queue, (candidate, neighbor))
            if found is not None:
                path = [found]
                while path[-1] != seed:
                    path.append(previous[path[-1]])
                path.reverse()
                sequence = []
                for key in path:
                    region = region_for[key]
                    if not sequence or sequence[-1] != region:
                        sequence.append(region)
                examples.append({'start': start_name, 'goal': target_name, 'nav_area_path': path, 'region_path': sequence,
                                 'center_distance_units': round(distance[found], 2), 'method': 'Dijkstra on recorded directed NAV edges; polygon-centroid distances; representative start area'})
    return {'schema_version': 1, 'hull': hull,
            'limitations': ['Region names are assigned by NAV polygon centroid containment in map area bounding boxes; these are inferred labels.',
                            'Regions group strongly connected NAV areas with the same label; no same-label one-way barriers are contracted.',
                            'Edges retain direction and original NAV-area witnesses. Unlabeled regions are retained; proximity does not create edges.',
                            'Movable navigation and ladder traversal are not represented. This graph does not evaluate cover, sightlines, timing, or balance.',
                            'The supplied NAV may predate edits to the repaired VMAP. Geometric alignment diagnostics are not proof of freshness.'],
            'summary': {'nav_areas_used': len(areas), 'nav_areas_labeled': named, 'label_coverage_percent': round(named / len(areas) * 100, 2),
                        'regions': len(nodes), 'directed_region_edges': len(edges), 'distinct_named_areas': len({n['label'] for n in nodes if n['label']}),
                        'links_outside_selected_static_hull': len(dangling), 'ladders_not_modeled': nav['ladder_count']},
            'nodes': nodes, 'edges': edges, 'area_assignments': assignments, 'spawn_alignment': spawns, 'excluded_links': dangling, 'example_routes': examples}


def report(graph):
    lines = ['# Map region connection graph', '',
             'Connections come from the supplied navigation mesh. Area names are inferred from the repaired map\'s named-area volume bounds.', '',
             '| Measurement | Value |', '| --- | ---: |']
    lines.extend(f'| {k} | {v} |' for k, v in graph['summary'].items())
    lines.extend(['', '## Recorded region links', '', '| Source | Target | NAV connections | Reverse edge |', '| --- | --- | ---: | --- |'])
    lines.extend(f"| {e['source']} | {e['target']} | {e['nav_connection_count']} | {'yes' if e['reverse_edge_exists'] else 'no'} |" for e in graph['edges'])
    lines.extend(['', '## Example paths', '', 'These are recorded NAV paths from representative spawn-area polygons. Distances use polygon centers, not player travel time or tactical quality.', ''])
    lines.extend(f"- {r['start']} → {r['goal']}: {' → '.join(r['region_path'])} ({r['center_distance_units']} approximate Hammer units)." for r in graph['example_routes'])
    lines.extend(['', '## Limits', ''])
    lines.extend('- ' + item for item in graph['limitations'])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nav-json', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--hull', type=int, default=0)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.suffix != '.json' or args.output.exists() or args.output.with_suffix('.md').exists():
        parser.error('Choose a new .json output path')
    nav = json.loads(args.nav_json.read_text(encoding='utf-8'))
    reference = json.loads(args.reference.read_text(encoding='utf-8'))
    graph = build_graph(nav, reference, args.hull)
    graph['provenance'] = {'nav_export': str(args.nav_json), 'nav_source': nav['source'], 'parser': nav['parser'], 'nav_version': nav['version'],
                           'map_reference': str(args.reference), 'map_source': reference['source'],
                           'reference_sha256': hashlib.sha256(args.reference.read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(graph, indent=2), encoding='utf-8')
    args.output.with_suffix('.md').write_text(report(graph), encoding='utf-8')
    print(json.dumps(graph['summary']))


if __name__ == '__main__':
    main()
