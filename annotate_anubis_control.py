"""Prepare conservative initial-control context from the user's Anubis diagram.

Source place groups are correspondence proposals, not registered image masks.
Mixed Canal and unnamed regions deliberately remain unresolved.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from annotate_boundaries import select_surfaces
from annotate_layout import trace_route


T_LABELS = {'TSpawn', 'Ruins', 'OutsideLong', 'Street', 'TSideUpper', 'TStairs'}
CT_LABELS = {'BombsiteA', 'BombsiteB', 'BackofB', 'Bricks', 'Alley',
             'CTSpawn', 'CTSideUpper', 'LowerTunnel', 'Tunnel', 'TunnelStairs',
             'PalaceInterior', 'SnipersNest', 'Heaven', 'Fountain', 'Water',
             'Main', 'Walkway', 'Middle', 'MidDoors', 'Connector'}
COLORS = {'t_first': '#be902e', 'ct_first': '#168cbb',
          'meeting': '#ededdf', 'unresolved': '#46525e'}


def build(graph):
    if graph['map'] != 'Anubis' or graph['dataset_role'] != 'training':
        raise ValueError('Requires the approved Anubis training reference')
    rows = []
    for node in graph['nodes']:
        label = node['label']
        context = ('t_first' if label in T_LABELS else
                   'ct_first' if label in CT_LABELS else
                   'unresolved')
        rows.append({'region_id': node['id'], 'source_place_label': label,
                     'initial_control_proposed': context,
                     'review_status': 'pending_source_correspondence_review',
                     'supervision_mask': False})
    contexts = {r['region_id']: r['initial_control_proposed'] for r in rows}
    candidates = []
    for edge in graph['edges']:
        a, b = edge['source'], edge['target']
        if {contexts[a], contexts[b]} == {'t_first', 'ct_first'}:
            if not edge['witnesses']:
                raise ValueError('Transition lacks NAV evidence')
            candidates.append({'source': a, 'target': b,
                               'kind': 'initial_control_choke_candidate',
                               'review_status': 'pending_source_correspondence_review',
                               'directed_nav_witnesses': edge['witnesses']})
    spatial = []
    for context, title, bounds in [
        ('t_first', 'Top Mid portion of source Bridge', [-640,-554,-32,86,-160,96]),
        ('meeting', 'Bridge corridor portion', [-640,-160,-32,86,512,96]),
        ('meeting', 'Central Water portion of source Canal', [-544,0,-220,700,932,0]),
        ('t_first', 'Boat / Headshot portion of source Canal', [700,0,-220,1281,932,0]),
    ]:
        pieces = select_surfaces(graph, ['Canal' if 'Canal' in title else 'Bridge'], bounds)
        if not pieces:
            raise ValueError('Empty spatial subdivision')
        spatial.append({'initial_control_proposed': context, 'title': title,
                        'proposed_roi_xyz': bounds, 'surface_pieces': pieces,
                        'review_status': 'pending_boundary_review', 'supervision_mask': False})
    fronts = []
    for key, title, a, b in [
        ('C1', 'B entrance: Long to site', 'region_1073', 'region_1082'),
        ('C2', 'Mid: north Bridge to Middle', 'region_1', 'region_1306'),
        ('C3', 'A Main: Boat to Main', 'region_209', 'region_1323'),
    ]:
        links = [e for e in graph['edges'] if {e['source'], e['target']} == {a,b}]
        if not links or any(not e['witnesses'] for e in links):
            raise ValueError('Front lacks recorded NAV interface')
        fronts.append({'id': key, 'title': title, 'review_status': 'pending_boundary_review',
                       'directed_links': links,
                       'interpretation': 'Candidate access transition near the diagram front; local width and correspondence await review.'})
    routes = build_routes(graph)
    return {'map': 'Anubis', 'status': 'pending_source_correspondence_review',
            'training_eligible': False, 'model_training_performed': False,
            'user_color_semantics': {'orange': 'T-side controls first',
                                    'blue': 'CT-side controls first',
                                    'white': 'meeting points / battlegrounds',
                                    'blue_orange_contact': 'choke transition'},
            'mapping_basis': 'Conservative source place correspondence; no pixel registration or measured arrival timing.',
            'regions': rows, 'spatial_subdivision_proposals': spatial, 'choke_candidates': candidates,
            'front_proposals': fronts, 'route_evidence': routes,
            'counts': dict(Counter(contexts.values())),
            'unresolved_context': ['Canal Water / Boat split at x=700 is an authored boundary proposal, not image registration.',
                                   'Bridge combines Top Mid and Bridge corridor; spatial split is a review proposal.',
                                   'Unnamed regions remain unresolved.',
                                   'Source Water corresponds to north Beach, not central diagram Water.',
                                   'Source Street corresponds to the southern T approach; source Alley is the western CT approach.'],
            'source_graph': graph}


def build_routes(graph):
    """Use actual anchor associations and directed NAV links; do not certify timing."""
    nodes = {n['id']: n for n in graph['nodes']}
    anchors = graph['anchors']
    def start(team):
        evidence = [a for a in anchors if a['classname'] == team and a['region_ids']]
        counts = Counter(r for a in evidence for r in a['region_ids'])
        if not counts:
            raise ValueError('Missing spawn anchor associations')
        return counts.most_common(1)[0][0], evidence
    ct, ct_evidence = start('info_player_counterterrorist')
    t, t_evidence = start('info_player_terrorist')
    objectives = {}
    for label in ['BombsiteA', 'BombsiteB']:
        matches = [r for a in anchors if a['classname'] == 'func_bomb_target'
                   for r in a['region_ids'] if nodes[r]['label'] == label]
        if not matches:
            raise ValueError('Missing objective anchor association')
        objectives[label] = max(matches, key=lambda r: len(nodes[r]['nav_area_ids']))
    routes = []
    specs = [
        ('CT to A without B', ct, objectives['BombsiteA'], CT_LABELS-{'BombsiteB'}, (), ct_evidence),
        ('CT to B without A', ct, objectives['BombsiteB'], CT_LABELS-{'BombsiteA'}, (), ct_evidence),
        ('T to B via Long', t, objectives['BombsiteB'], T_LABELS|{'BombsiteB'}, ('OutsideLong',), t_evidence),
        ('T to A via Boat and Main', t, objectives['BombsiteA'], T_LABELS|{'Canal','Main','BombsiteA'}, ('Canal','Main'), t_evidence),
        ('B to A defender rotation', objectives['BombsiteB'], objectives['BombsiteA'], CT_LABELS, (), []),
        ('A to B defender rotation', objectives['BombsiteA'], objectives['BombsiteB'], CT_LABELS, (), []),
    ]
    for title, a, b, allowed, required, evidence in specs:
        route = trace_route(graph, a, b, allowed, required)
        route.update(title=title, start_region=a, end_region=b,
                     spawn_anchor_evidence=[{'id':e['id'], 'association':e['association'], 'region_ids':e['region_ids']} for e in evidence],
                     review_status='pending_gameplay_interpretation_review',
                     evidence_scope='Directed coarse NAV connectivity only. Spawn association can be nearest-centroid diagnostic; no arrival-time or exposure inference.')
        routes.append(route)
    return routes


def draw(graph, draft, output):
    im = Image.new('RGB', (1450, 1100), '#101a26')
    pen = ImageDraw.Draw(im)
    def font(size):
        return ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
    points = [p for polygon in graph['nav_polygons'] for p in polygon['corners']]
    minx, maxx = min(p[0] for p in points), max(p[0] for p in points)
    miny, maxy = min(p[1] for p in points), max(p[1] for p in points)
    scale = min(820 / (maxx-minx), 930 / (maxy-miny))
    def xy(p):
        return (45+(p[0]-minx)*scale, 115+(maxy-p[1])*scale)
    contexts = {r['region_id']: r['initial_control_proposed'] for r in draft['regions']}
    for poly in sorted(graph['nav_polygons'], key=lambda p: sum(c[2] for c in p['corners'])):
        pen.polygon([xy(c) for c in poly['corners']], fill=COLORS[contexts[poly['region_id']]])
    for item in draft['spatial_subdivision_proposals']:
        for poly in item['surface_pieces']:
            pen.polygon([xy(c) for c in poly['corners']], fill=COLORS[item['initial_control_proposed']])
    for edge in draft['choke_candidates']:
        for witness in edge['directed_nav_witnesses']:
            pen.line([xy(c) for c in witness['source_edge_endpoints']], fill='#ff6666', width=3)
    for front in draft['front_proposals']:
        coordinates = []
        for link in front['directed_links']:
            for witness in link['witnesses']:
                coords = [xy(c) for c in witness['source_edge_endpoints']]
                pen.line(coords, fill='#ff6666', width=4)
                coordinates.extend(coords)
        x = sum(c[0] for c in coordinates)/len(coordinates)
        y = sum(c[1] for c in coordinates)/len(coordinates)
        pen.rectangle((x-16,y-24,x+16,y-5), fill='#101a26', outline='#ff6666')
        pen.text((x-12,y-23),front['id'],font=font(14),fill='#ff9999')
    # Label the largest region per place to keep the review legible.
    representatives = {}
    for node in graph['nodes']:
        label = node['label']
        if label and (label not in representatives or len(node['nav_area_ids']) > len(representatives[label]['nav_area_ids'])):
            representatives[label] = node
    for label, node in representatives.items():
        x, y = xy(node['position'])
        text = label
        box = pen.textbbox((x, y), text, font=font(13))
        pen.rectangle((box[0]-2, box[1]-1, box[2]+2, box[3]+1), fill='#101a26')
        pen.text((x, y), text, font=font(13), fill='#f0f4fa')
    pen.text((30, 24), 'Anubis: initial control correspondence draft', font=font(29), fill='#edf2fa')
    pen.text((30, 68), 'Source NAV footprint. Colors proposed from your diagram; grey remains unresolved.', font=font(18), fill='#bccbda')
    y = 145
    for context, title in [('t_first', 'T first'), ('ct_first', 'CT first'), ('meeting', 'Meeting / battleground'), ('unresolved', 'Unresolved correspondence')]:
        pen.rectangle((945, y, 970, y+25), fill=COLORS[context])
        pen.text((985, y), title, font=font(20), fill='#edf2fa')
        count_text = ('Bridge + central Water proposals' if context == 'meeting' else
                      f"{draft['counts'].get(context, 0)} whole source regions")
        pen.text((985, y+30), count_text, font=font(16), fill='#bccbda')
        y += 88
    notes = ['Red C1-C3: witnessed access fronts', 'Water / Boat split remains a proposal.',
             'Source Water = north Beach.', 'Source Street = southern T approach.',
             'Source Alley = western CT approach.', 'Grey does not mean neutral territory.',
             'Initial control is not permanent control.',
             f"Routes recorded: {sum(r['status']=='recorded_directed_route' for r in draft['route_evidence'])}/6",
             'No training performed from this draft.']
    for i, text in enumerate(notes):
        pen.text((945, 540+i*40), text, font=font(17), fill='#bccbda')
    im.save(output)


def run(source, image, output):
    if output.exists():
        raise ValueError('Use a new artifact directory')
    raw = source.read_bytes()
    graph = json.loads(raw)
    draft = build(graph)
    draft.update(source_graph_sha256=hashlib.sha256(raw).hexdigest(),
                 reference_image=str(image.resolve()),
                 reference_image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                 annotator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True)
    (output/'initial-control.json').write_text(json.dumps(draft, indent=2))
    draw(graph, draft, output/'overview.png')
    review = (
        '# Anubis initial-control draft\n\n'
        'Your color meanings are recorded as supplied. Mapping those meanings to this repaired reference remains a review proposal. '
        'All original source nodes, directed edges, anchors and NAV polygons are preserved. No region is enabled for supervision yet.\n\n'
        'The source Bridge group spans both T-controlled Top Mid and the white Bridge corridor. Two authored NAV-clipped subdivisions propose this separation; their shared boundary awaits review. '
        'Canal receives separate NAV-clipped Water meeting and Boat T-control proposals, divided at world x=700. The exact boundary awaits review. Whole Canal nodes remain unsupervised.\n\n'
        'Source naming differs: Water is Beach; Street is the southern T approach; Alley is the western CT approach. '
        'Red lines are witnessed directed NAV links between proposed T-first and CT-first groups, not certified door widths. '
        'This is a correspondence draft, not a timing, sightline or gameplay-quality result.\n\n'
        '## Directed route evidence\n\n')
    for route in draft['route_evidence']:
        review += f"- {route['title']}: {route['status']}. "
        review += ' -> '.join(str(x) for x in route.get('place_labels', []))+'\n'
    review += ('\nSpawn associations retain their original diagnostic scope. CT spawn entities associate with CTSideUpper, rather than the region named CTSpawn. '
               'Routes preserve directed edge witnesses, but coarse connectivity does not certify a tactical route.\n\n'
               '## Focused review\n\nDoes the white Water area extend far enough toward Boat? '
               'Is C2 at the intended north Bridge / Mid-door transition? '
               'Other source place correspondences remain proposals.\n')
    (output/'review.md').write_text(review)
    print(json.dumps({'counts': draft['counts'], 'directed_choke_candidates': len(draft['choke_candidates']), 'training_eligible': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--reference-image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.reference_image, args.output)
