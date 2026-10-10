"""Review flat graybox floor routes and create a traceable, manually revised proposal.

Distances are four-neighbor grid proxies, not in-game movement times. The floor
audit ignores cover and player hull clearance and must not be called a NAV check.
"""
import argparse
from collections import deque
import copy
import hashlib
import heapq
import json
from pathlib import Path

from connected_geometry import floor_cells, GRID, validate_floor
from export_macro_graybox import manifold_cells

GUIDE = 'https://steamcommunity.com/sharedfiles/filedetails/?id=1110438811'
TERMINALS = ('TSpawn', 'CTSpawn', 'SiteA', 'SiteB')


def distances(cells, start):
    if start not in cells:
        raise ValueError('Route endpoint outside floor')
    result = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for other in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if other in cells and other not in result:
                result[other] = result[x,y] + GRID
                queue.append(other)
    return result


def audit(plan):
    design = plan['design_choices']
    rooms = {r['id']: r for r in design['regions']}
    adjacency = {name: {} for name in rooms}
    for edge in design['connections']:
        a, b = edge['source'], edge['target']
        weight = sum(abs(rooms[a]['center'][i]-rooms[b]['center'][i]) for i in (0,1))
        adjacency[a][b] = adjacency[b][a] = weight
    cells, repairs = manifold_cells(floor_cells(plan))
    validate_floor(cells, lambda x: 0)
    centers = {name: tuple(int(v//GRID) for v in r['center'][:2]) for name,r in rooms.items()}
    routes = []
    for i, a in enumerate(TERMINALS):
        actual = distances(cells, centers[a])
        intended = {a: 0}
        queue = [(0, a)]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != intended[node]:
                continue
            for other, weight in adjacency[node].items():
                if cost+weight < intended.get(other, float('inf')):
                    intended[other] = cost+weight
                    heapq.heappush(queue, (cost+weight, other))
        for b in TERMINALS[i+1:]:
            d = actual.get(centers[b]); g = intended.get(b)
            routes.append({'from': a, 'to': b, 'floor_grid_units': d,
                           'graph_elbow_centerline_units': g,
                           'difference_units': None if d is None or g is None else g-d})
    # Each corridor is rasterized separately. Overlaps between corridors with
    # disjoint endpoints, outside ALL room footprints, are possible junctions.
    room_cells = floor_cells({'design_choices': {**design, 'connections': []}}) if 'floor_cell_override' not in design else set()
    overlaps = []
    if 'floor_cell_override' not in design:
        footprints = []
        for edge in design['connections']:
            pair = [edge['source'], edge['target']]
            small = {'regions': [rooms[n] for n in pair], 'connections': [edge],
                     'corridor_width_units': design['corridor_width_units']}
            footprints.append((pair, floor_cells({'design_choices': small}) - room_cells))
        for i, (pair, footprint) in enumerate(footprints):
            for other, other_footprint in footprints[i+1:]:
                common = footprint & other_footprint
                if set(pair).isdisjoint(other) and common:
                    overlaps.append({'corridor_a': pair, 'corridor_b': other,
                                     'overlap_cells_outside_rooms': len(common),
                                     'sample_world_xy': [v*GRID+GRID/2 for v in sorted(common)[0]]})
    return {'floor_cells': len(cells), 'corner_repairs': len(repairs),
            'nonterminal_graph_leaves': [n for n in rooms if n not in TERMINALS and len(adjacency[n]) <= 1],
            'routes': routes, 'nonincident_corridor_overlaps': overlaps,
            'limits': ['Graph leaves are review flags, not proof of useless space.',
                       'Grid paths ignore cover, player hull, diagonal motion and movement speed.',
                       'Graph/floor distance differences include corner cutting and corridor intersections.',
                       'Overlap list is diagnostic, not a complete extracted navigation graph.',
                       'Timings, battlefronts, sightlines and tactical roles require further review/playtesting.']}


def revise(plan):
    revised = copy.deepcopy(plan)
    design = revised['design_choices']
    if 'floor_cell_override' in design:
        raise ValueError('Revise the original proposal, not an exported floor override')
    if not any(r['id'] == 'Area8' for r in design['regions']):
        raise ValueError('Expected Area8 in original proposal')
    design['regions'] = [r for r in design['regions'] if r['id'] != 'Area8']
    design['connections'] = [e for e in design['connections'] if 'Area8' not in (e['source'], e['target'])]
    revised['preview_title'] = 'HammerGPT: graybox v2 - Area 8 removed'
    revised['preview_subtitle'] = 'Manual design review of learned v1; same model weights. Route audit is a floor-grid proxy.'
    revised['design_review'] = {'guide': GUIDE, 'retraining_performed': False,
        'changes': [{'area': 'Area8', 'action': 'remove room and sole corridor',
                     'reason': 'User identified unused space; no demonstrated tactical function.'}],
        'retained_for_review': {'Area2': 'Graph leaf, but its corridor overlaps another route; do not infer a dead end from the graph alone.'},
        'role_hypotheses_not_training_labels': {
            'Area1': 'A approach', 'Area2': 'Spawn-side cross-connection; usefulness unresolved',
            'Area3': 'T-side distribution', 'Area4': 'B approach', 'Area5': 'B approach split',
            'Area6': 'Alternative B approach', 'Area7': 'Site-to-site connector'},
        'rubric': ['Every non-objective area needs a defensible gameplay purpose.',
                   'Review actual floor junctions before accepting intended route topology.',
                   'Measure arrival and rotation times in game before claiming balance.',
                   'Review approach, post-plant and retake sightlines and cover.',
                   'Use playtest feedback; design heuristics are not universal rules.']}
    return revised


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    raw = args.proposal.read_bytes(); original = json.loads(raw)
    revised = revise(original)
    revised['design_review']['source_sha256'] = hashlib.sha256(raw).hexdigest()
    before, after = audit(original), audit(revised)
    cells_before = manifold_cells(floor_cells(original))[0]
    cells_after = manifold_cells(floor_cells(revised))[0]
    review = {'before': before, 'after': after,
              'removed_floor_cells': len(cells_before-cells_after),
              'added_floor_cells': len(cells_after-cells_before)}
    (args.output/'proposal.json').write_text(json.dumps(revised, indent=2))
    (args.output/'audit.json').write_text(json.dumps(review, indent=2))
    lines = ['# Graybox v2 design review', '',
             'Manual revision of the learned v1 proposal; no retraining or new maps.', '',
             f'Design reference: [Exodus guide]({GUIDE}).', '',
             f"Removed Area8 and its sole corridor: {review['removed_floor_cells']} floor cells removed.",
             'Area2 remains a review flag; corridor overlap means graph degree alone cannot decide its purpose.', '',
             '## Floor route proxies', '',
             '| Route | v1 units | v2 units |', '|---|---:|---:|']
    for a,b in zip(before['routes'], after['routes']):
        lines.append(f"| {a['from']} to {a['to']} | {a['floor_grid_units']} | {b['floor_grid_units']} |")
    lines += ['', f"v2 has {len(after['nonincident_corridor_overlaps'])} pairs of nonincident corridors overlapping outside rooms.",
              'See audit.json for locations. These are potential extra junctions, not automatically design errors.', '',
              'Distances use the exported floor grid before cover, not compiled NAV or real player travel times.',
              'Compilation, collision, sightlines, battlefronts, objective behavior and playtesting remain unverified.']
    (args.output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
