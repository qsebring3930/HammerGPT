"""Spatial route comparison; descriptors, not a gameplay score or training run."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import networkx as nx
from PIL import Image, ImageDraw, ImageFont

MAPS = ('dust2', 'anubis', 'cache', 'train', 'cobblestone')
ANNOTATIONS = {
    'dust2': 'dust2-boundaries-reviewed-v1/boundaries.json',
    'anubis': 'anubis-control-reviewed-v1/initial-control.json',
    'cache': 'cache-reviewed-v1/annotation.json',
    'train': 'train-reviewed-v1/annotation.json',
    'cobblestone': 'cobblestone-reviewed-v1/annotation.json',
}
PAIRS = (('T', 'A'), ('T', 'B'), ('CT', 'A'), ('CT', 'B'), ('A', 'B'), ('B', 'A'))
COLORS = {'T': '#efb04d', 'CT': '#62c9f0', 'A': '#f18098', 'B': '#c391e8'}


def connected_places(net, nodes):
    """Only contract same-label strongly connected components, never remote places."""
    owner, groups = {}, []
    labels = sorted({n.get('label') for n in nodes.values() if n.get('label')})
    for label in labels:
        ids = [k for k, n in nodes.items() if n.get('label') == label]
        for component in sorted(nx.strongly_connected_components(net.subgraph(ids)), key=lambda c: sorted(c)):
            key = f'place_{len(groups)}'
            groups.append({'id': key, 'label': label, 'members': sorted(component)})
            owner.update({k: key for k in component})
    for k in sorted(nodes):
        if k not in owner:
            key = f'place_{len(groups)}'
            groups.append({'id': key, 'label': None, 'members': [k]})
            owner[k] = key
    return owner, groups


def pendant_cycles(net, terminals):
    """Terminal-free cyclic lobes connected through one articulation point."""
    undirected = net.to_undirected()
    rows, seen = [], set()
    for cut in sorted(nx.articulation_points(undirected)):
        remainder = undirected.copy()
        remainder.remove_node(cut)
        original_component = nx.node_connected_component(undirected, cut)
        for component in nx.connected_components(remainder):
            if not component <= original_component or component & terminals:
                continue
            lobe = component | {cut}
            rank = undirected.subgraph(lobe).number_of_edges() - len(lobe) + 1
            signature = tuple(sorted(component))
            if rank > 0 and signature not in seen:
                seen.add(signature)
                rows.append({'attachment': cut, 'members': sorted(component), 'cycle_rank': rank})
    return rows


def best_route(net, starts, ends, excluded=()):
    graph = net.subgraph(set(net) - set(excluded))
    starts = sorted(set(starts) & set(graph))
    if not starts:
        return None
    lengths, paths = nx.multi_source_dijkstra(graph, starts, weight='weight')
    candidates = sorted(set(ends) & set(lengths))
    if not candidates:
        return None
    end = min(candidates, key=lambda n: (lengths[n], n))
    return {'cost_units': lengths[end], 'path': paths[end]}


def site_exchange_symmetry(net, terminals):
    """Exact proposal-topology symmetry; ignores positions, dimensions and lengths."""
    if any(len(ids) != 1 for ids in terminals.values()):
        return None
    original, exchanged = net.to_undirected(), net.to_undirected()
    roles = {ids[0]: key for key, ids in terminals.items()}
    for node in original:
        role = roles.get(node, 'internal')
        original.nodes[node]['terminal_role'] = role
        exchanged.nodes[node]['terminal_role'] = {'A':'B','B':'A'}.get(role,role)
    return nx.is_isomorphic(original, exchanged,
        node_match=nx.algorithms.isomorphism.categorical_node_match('terminal_role',None))


def load(root, name, relative, generated=False):
    source = root / relative
    raw = source.read_bytes()
    data = json.loads(raw)
    if generated:
        design = data['design_choices']
        nodes = {n['id']: {'id': n['id'], 'label': n['id'], 'position': n['center'], **n} for n in design['regions']}
        edges = []
        for edge in design['connections']:
            a, b = edge['source'], edge['target']
            points = edge.get('path_xy')
            cost = sum(math.dist(p, q) for p, q in zip(points, points[1:])) if points else math.dist(nodes[a]['position'], nodes[b]['position'])
            edges.extend([(a, b, cost), (b, a, cost)])
        terminals = {k: [v] for k, v in [('T', 'TSpawn'), ('CT', 'CTSpawn'), ('A', 'SiteA'), ('B', 'SiteB')]}
        surfaces, annotations = [], []
        association = 'authored terminal regions; intended proposal graph, not compiled NAV'
    else:
        if data['dataset_role'] != 'training':
            raise ValueError('Only approved reference maps are allowed')
        nodes = {n['id']: n for n in data['nodes']}
        edges = [(e['source'], e['target'], math.dist(nodes[e['source']]['position'], nodes[e['target']]['position'])) for e in data['edges']]
        terminals = {k: sorted({r for a in data['anchors'] if a['classname'] == cls for r in a['region_ids']})
                     for k, cls in [('T', 'info_player_terrorist'), ('CT', 'info_player_counterterrorist')]}
        for k in ('A', 'B'):
            terminals[k] = sorted({r for a in data['anchors'] if a['classname'] == 'func_bomb_target'
                                   for r in a['region_ids'] if nodes[r]['label'] == f'Bombsite{k}'})
        surfaces = data['nav_polygons']
        ann = json.loads((root / 'output/annotations' / ANNOTATIONS[name]).read_text())
        annotations = sum((ann.get(k, []) for k in ['annotations', 'meetings', 'chokes', 'battlegrounds', 'front_proposals', 'spatial_subdivision_proposals']), [])
        association = 'source spawn/objective NAV associations; some spawn associations are nearest-centroid diagnostics'
    if any(not v for v in terminals.values()):
        raise ValueError(f'{name}: missing terminal association')
    net = nx.DiGraph()
    net.add_nodes_from(nodes)
    net.add_weighted_edges_from(edges)
    owner, groups = connected_places(net, nodes)
    for group in groups:
        points = [nodes[n]['position'] for n in group['members']]
        group['center'] = [sum(p[i] for p in points)/len(points) for i in range(3)]
        group['member_center_bounds'] = {'min':[min(p[i] for p in points) for i in range(3)],
                                         'max':[max(p[i] for p in points) for i in range(3)]}
    quotient_edges = sorted({(owner[a], owner[b]) for a, b in net.edges if owner[a] != owner[b]})
    allterminals = set(sum(terminals.values(), []))
    route_rows = []
    for start, end in PAIRS:
        excluded = terminals['B' if end == 'A' else 'A'] if start in ('T', 'CT') else terminals['T']
        route = best_route(net, terminals[start], terminals[end], excluded)
        unrestricted = best_route(net, terminals[start], terminals[end])
        row = {'from': start, 'to': end, 'excluded_terminal': 'other site' if start in ('T', 'CT') else 'T spawn',
               'route': route, 'unrestricted_route': unrestricted, 'blocked_place_alternatives': []}
        overlap = bool(set(terminals[start]) & (set(terminals[end]) | set(excluded)))
        row['association_ambiguous'] = overlap
        row['status'] = 'ambiguous_terminal_region_overlap' if overlap else 'resolved' if route else 'no_path_with_exclusion'
        if route:
            seq = []
            for n in route['path']:
                if not seq or seq[-1] != owner[n]:
                    seq.append(owner[n])
            group_lookup = {g['id']: g for g in groups}
            route['place_sequence'] = [group_lookup[g]['label'] or 'unlabeled' for g in seq]
            route['place_components'] = seq
            route['center_elevation_change_units'] = sum(abs(nodes[a]['position'][2]-nodes[b]['position'][2]) for a,b in zip(route['path'], route['path'][1:]))
            for group in seq:
                members = set(group_lookup[group]['members'])
                if members & allterminals:
                    continue
                alternate = best_route(net, terminals[start], terminals[end], set(excluded) | members)
                row['blocked_place_alternatives'].append({'place': group_lookup[group]['label'] or 'unlabeled',
                    'component': group, 'alternative_cost_ratio': alternate['cost_units']/max(route['cost_units'], 1) if alternate else None,
                    'alternative_path': alternate['path'] if alternate else None})
        route_rows.append(row)
    if surfaces:
        heights = [c[2] for p in surfaces for c in p['corners']]
    else:
        heights = [n['position'][2] for n in nodes.values()]
    result = {'map': name, 'kind': 'generated_proposal' if generated else 'source_NAV', 'source': str(source.resolve()),
              'source_sha256': hashlib.sha256(raw).hexdigest(), 'terminal_association_basis': association,
              'original_nodes': len(nodes), 'connected_place_components': len(groups),
              'directed_connections': net.number_of_edges(), 'place_components': groups,
              'component_connections': quotient_edges, 'terminal_nodes': terminals, 'routes': route_rows,
              'height_span_units': max(heights)-min(heights),
              'exact_site_exchange_topology_symmetry': site_exchange_symmetry(net,terminals) if generated else None,
              'terminal_free_pendant_cycles': pendant_cycles(net, allterminals),
              'annotation_source': str((root / 'output/annotations' / ANNOTATIONS[name]).resolve()) if not generated else None}
    if not generated:
        result['annotation_sha256'] = hashlib.sha256((root / 'output/annotations' / ANNOTATIONS[name]).read_bytes()).hexdigest()
    return result, nodes, net, surfaces, annotations


def draw_panel(result, nodes, net, surfaces, annotations, output):
    im = Image.new('RGB', (1100, 950), '#101a26')
    pen = ImageDraw.Draw(im)
    font = lambda size: ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
    points = [c for p in surfaces for c in p['corners']] if surfaces else [n['position'] for n in nodes.values()]
    lo = [min(p[i] for p in points) for i in range(2)]
    hi = [max(p[i] for p in points) for i in range(2)]
    scale = min(900/max(hi[0]-lo[0],1), 680/max(hi[1]-lo[1],1))
    def xy(p):
        return 90+(p[0]-lo[0])*scale, 140+(hi[1]-p[1])*scale
    pen.text((30,20), result['map'].replace('_',' ').title(), font=font(32), fill='#f1f5fa')
    pen.text((30,65), 'Source NAV + reviewed contexts' if surfaces else 'Rejected generated proposal: intended connections', font=font(20), fill='#bdcbd9')
    for p in sorted(surfaces, key=lambda p: sum(c[2] for c in p['corners'])/len(p['corners'])):
        pen.polygon([xy(c) for c in p['corners']], fill='#344553')
    if not surfaces:
        for a,b in net.edges:
            pen.line([xy(nodes[a]['position']), xy(nodes[b]['position'])], fill='#526574', width=3)
        for node in nodes.values():
            polygon = node.get('footprint_polygon_xy')
            if polygon:
                pen.polygon([xy(p) for p in polygon],fill='#344553')
            else:
                x,y = xy(node['position']);pen.rectangle((x-8,y-8,x+8,y+8), fill='#344553')
    # Reviewed clipped surfaces remain separate from inferred route lines.
    for ann in annotations:
        pieces = ann.get('surface_pieces', [])
        meeting = ann.get('kind') == 'meeting_area' or ann.get('role') == 'battleground_context'
        if not pieces and ann.get('role') == 'battleground_context':
            pieces = [p for p in surfaces if p['region_id'] in ann['region_ids']]
        for p in pieces:
            if len(p['corners']) >= 3:
                pen.polygon([xy(c) for c in p['corners']], fill='#938440' if meeting else '#955463')
        for edge in ann.get('directed_links', []):
            for witness in edge.get('witnesses', []):
                segment = witness.get('source_edge_endpoints')
                if segment:
                    pen.line([xy(p) for p in segment], fill='#ff7777', width=4)
    for row in result['routes'][:4]:
        route = row['route']
        if route and len(route['path']) > 1:
            pen.line([xy(nodes[n]['position']) for n in route['path']], fill=COLORS[row['from']], width=3)
    for key, ids in result['terminal_nodes'].items():
        p = [sum(nodes[n]['position'][i] for n in ids)/len(ids) for i in range(3)]
        x,y = xy(p)
        pen.ellipse((x-14,y-14,x+14,y+14), fill=COLORS[key], outline='#ffffff', width=2)
        pen.text((x+18,y-13),key,font=font(20),fill='#ffffff',stroke_width=2,stroke_fill='#101a26')
    pen.text((30,845),'Orange: T access   Blue: CT access   Yellow/red: reviewed encounter/choke evidence',font=font(18),fill='#d5dfe8')
    pen.text((30,877),'Lines connect region centers: route proxies, not player trajectories or sightlines.',font=font(18),fill='#b5c4d2')
    pen.text((30,909),f"Height span {result['height_span_units']:.0f} units | original nodes {len(nodes)} | connected place components {result['connected_place_components']}",font=font(18),fill='#b5c4d2')
    im.save(output)


def run(root, output):
    output.mkdir(parents=True, exist_ok=False)
    items = [(name, f'output/coarse-layout-v1/{name}.json', False) for name in MAPS]
    items += [('macro_v3', 'output/macro-graybox-v3/exported-proposal.json', True),
              ('authored_backbone', 'output/gameplay-backbone-v2/proposal.json', True)]
    results = []
    for name, source, generated in items:
        result, nodes, net, surfaces, annotations = load(root, name, source, generated)
        draw_panel(result, nodes, net, surfaces, annotations, output / f'{name}.png')
        results.append(result)
    overview = Image.new('RGB', (2200, 3800), '#101a26')
    for i, result in enumerate(results):
        with Image.open(output / f"{result['map']}.png") as panel:
            overview.paste(panel, ((i % 2)*1100, (i // 2)*950))
    overview.save(output/'overview.png')
    side_by_side = Image.new('RGB',(2200,950),'#101a26')
    for i,name in enumerate(('train','authored_backbone')):
        with Image.open(output/f'{name}.png') as panel:
            side_by_side.paste(panel,(1100*i,0))
    side_by_side.save(output/'train-vs-generated.png')
    limitations = ['Reference costs are coarse-region center distances on recorded directed NAV; generated costs are proposal centerline distances. They are different proxies, not comparable movement times.',
        'Named-component contraction is for route interpretation; routing always uses the original graph. Place names are source metadata, not learned tactical roles.',
        'Deleting a complete place component is a route resilience probe, not a simulated blocked doorway. Unlabeled components have different granularity.',
        'NAV height span includes peripheral surfaces. Ladders are not modeled; reverse-link absence does not establish a usable one-way drop.',
        'Source anchor associations include diagnostic nearest-centroid matches. Topology cannot establish cover, sightlines, clearance, first-contact timing or fun.',
        'Terminal-free pendant cycles cannot offer a simple through-route between these terminals, but may still support fighting or positioning.',
        'Cache annotations are place contexts rather than reviewed exact extents. Anubis control fronts differ from clipped meeting boundaries. Their counts are not comparable.',
        'No new model training, generated maps, source edits, reserved-map access or automated quality/similarity scores.']
    payload = {'task': 'whole_map_structure_comparison', 'model_training_performed': False,
               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'maps': results, 'limitations': limitations}
    (output/'comparison.json').write_text(json.dumps(payload,indent=2), encoding='utf-8')
    lines = ['# Whole-map structure comparison', '', 'Five approved references and two rejected generated proposals. This is a representation audit, not another training result.', '',
             '## What the representation retains', '', 'Original directed graphs, spatial positions, elevation, connected same-name components, six terminal routes, other-site exclusions, route alternatives after blocking a place component, and reviewed annotation overlays. No scalar quality score is assigned.', '',
             '| Map | Coarse/proposal nodes | Connected place components | Height span (units) | CT-A / CT-B route proxy | Pendant cyclic lobes |', '|---|---:|---:|---:|---|---:|']
    for result in results:
        routes = result['routes']
        costs = ['ambiguous' if r['association_ambiguous'] else f"{r['route']['cost_units']:.0f}" if r['route'] else 'unresolved' for r in routes[2:4]]
        lines.append(f"| {result['map']} | {result['original_nodes']} | {result['connected_place_components']} | {result['height_span_units']:.0f} | {' / '.join(costs)} | {len(result['terminal_free_pendant_cycles'])} |")
    lines += ['', 'Counts are descriptive and remain dependent on NAV/name granularity. A higher count is not a better map.', '',
        '## Findings', '',
        '- The authored backbone is exactly symmetric under A/B exchange with T/CT fixed when geometry is ignored. Irregular footprints did not change this connection structure. Symmetry alone is not a universal map defect, but here it substantiates the user feedback about repeated lanes.',
        '- Macro v3 has no intended CT-to-B route after excluding A. Its Junction1/Junction12 cycle connects through Junction3 and contains no terminal: extra cycle count did not create a through-route choice.',
        '- Train has distinct TMain-to-A and upper-to-BackofB-to-B route signatures, with an alternative to the latter after its upper component is removed. Its full NAV height span is 452 units versus 24 in macro v3 and 0 center elevation in the authored backbone. These are spatial evidence, not validated timing or collision.',
        '- Dust2 retains catwalk and upper-tunnel access; Anubis retains canal and ruins access; Cache retains A Main and B Main access; Cobblestone retains underpass/ramp and tunnel/side-door access. The shortest-route signatures differ, but signatures alone do not capture every approach or decision.',
        '- Cobblestone CT associations overlap A at coarse-region level. The CT-to-A zero-distance result and CT-to-B exclusion failure are ambiguous; using them as training quality labels would teach an extraction artifact.',
        '- Real references also contain terminal-free cyclic lobes. Such lobes are diagnostic review flags, not an automatic penalty: local positioning can matter even without a new spawn-to-site route.', '',
        '## Representation decision', '',
        'This audit preserves more useful structure than anonymous room/loop counts, but does not establish a complete planner training representation. Before training a whole-map planner, refine terminal associations to NAV polygons, extract a bounded set of spatially distinct alternative routes, and attach reviewed encounter/choke transitions along those routes. Retain directed spatial/elevation evidence and unknown masks; do not turn source place names into an identity shortcut or fabricated control/timing labels.', '',
        'The local geometry completion model remains a separate module. The next global task should predict route/encounter organization conditioned on terminals and then check its spatial realization. Route diagnostics, geometric validity, user-reviewed quality and diversity must remain distinct.', '',
        '## Route signatures and alternatives', '']
    for result in results:
        lines += [f"### {result['map']}", '', f"![Spatial comparison]({result['map']}.png)", '']
        if result['exact_site_exchange_topology_symmetry'] is not None:
            lines.append(f"Exact topology unchanged when A/B are exchanged while fixing T/CT: {result['exact_site_exchange_topology_symmetry']}. This ignores geometry and is a structural symmetry diagnostic, not a quality verdict.")
        for row in result['routes']:
            route = row['route']
            title = f"{row['from']} -> {row['to']} (exclude {row['excluded_terminal']})"
            if row['association_ambiguous']:
                lines.append(f'- {title}: ambiguous because source/start and objective/exclusion regions overlap. Refine anchor routing before interpreting this result; no map defect inferred.')
                continue
            if not route:
                lines.append(f'- {title}: unresolved in this representation.')
                continue
            mandatory = [b['place'] for b in row['blocked_place_alternatives'] if b['alternative_cost_ratio'] is None]
            lines.append(f"- {title}: {' -> '.join(route['place_sequence'])}. Center/path proxy {route['cost_units']:.0f} units; accumulated center elevation change {route['center_elevation_change_units']:.0f}. Components whose removal disconnects this route: {', '.join(mandatory) or 'none'}.")
        for lobe in result['terminal_free_pendant_cycles']:
            lines.append(f"- Cyclic lobe attached at {lobe['attachment']}: {', '.join(lobe['members'])} (cycle rank {lobe['cycle_rank']}). This supplies no simple through-route between selected terminals.")
        lines.append('')
    lines += ['## Limits', ''] + [f'- {s}' for s in limitations]
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'output': str(output.resolve()), 'maps': len(results), 'training_performed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(Path(__file__).resolve().parent, args.output)
