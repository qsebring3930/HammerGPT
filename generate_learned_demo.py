"""Export a reproducible local learned completion as editable Hammer surfaces."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import torch

from evaluate_topology import components
from geometric_planner import GeometryPlanner, infer, proposal_plans, rank_cost
from train_conditioned import ConditionedNet, ports
from train_connection_planner import complete
from simplify_section import boundary, signed_area, turn
from surface_geometry import create_surface_blockout, make_surface, validate_topology
from hammergpt import convert, get, parse, positions, serialize, set_value, walk


def footprint(context, prediction):
    result = context[0] >= .5
    result[12:20, 12:20] = prediction[0, 12:20, 12:20] >= .5
    return result


def outline_for(grid):
    groups = components(grid)[1]
    hidden = {(int(r), int(c)) for r, c in zip(*np.where(grid)) if 12 <= r < 20 and 12 <= c < 20}
    # NAV windows often include unrelated nearby islands. Export the component
    # containing ALL predicted hidden floor, leaving that prediction untouched.
    chosen = next((group for group in groups if hidden and hidden <= set(group)), None)
    if chosen is None:
        raise ValueError('Learned patch is disconnected; cannot trim visible context only')
    cells = {(int(c)-16, int(r)-16) for r, c in chosen}
    outline = boundary(cells)
    # Merge collinear boundary edges without moving any corner or floor cell.
    outline = [p for i, p in enumerate(outline)
               if turn(outline[i-1], p, outline[(i+1) % len(outline)]) != 0]
    if signed_area(outline) != len(cells)*64*64:
        raise ValueError('Contour changed the footprint')
    return cells, outline


def preview(context, prediction, target, destination, cells):
    scale = 12
    shown = np.zeros((32,32), dtype=bool)
    for x, y in cells:
        shown[y+16,x+16] = True
    shown[12:20,12:20] = True
    panels = [('Visible input', (context[0] >= .5) & shown),
              ('Learned completion', footprint(context, prediction) & shown),
              ('Recorded reference (comparison only)', (target[0] >= .5) & shown)]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="470" viewBox="0 0 1240 470">',
           '<rect width="1240" height="470" fill="#151b25"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#eef3fa;font-size:16px}</style>']
    for index, (title, grid) in enumerate(panels):
        x0 = 20+index*410
        svg.append(f'<text x="{x0}" y="28">{title}</text>')
        for r, c in zip(*np.where(grid)):
            color = '#edae49' if index == 1 and 12 <= r < 20 and 12 <= c < 20 else '#a3b7cd'
            svg.append(f'<rect x="{x0+c*scale}" y="{48+r*scale}" width="12" height="12" fill="{color}"/>')
        svg.append(f'<rect x="{x0+144}" y="192" width="96" height="96" fill="none" stroke="#edae49" stroke-width="2"/>')
    svg.append('<text x="20" y="458">Gold box: 512 x 512-unit hidden patch. Surrounding footprint is recorded context; walls are added by the exporter.</text></svg>')
    destination.write_text('\n'.join(svg), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cs2', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.artifacts.exists():
        parser.error('Choose new output and artifact paths')
    base = Path(__file__).resolve().parent
    pipeline = json.loads((base/'output/training/planner-v7/development-pipeline.json').read_text())
    for key in ('planner', 'floor'):
        if hashlib.sha256(Path(pipeline[key+'_checkpoint']).read_bytes()).hexdigest() != pipeline[key+'_sha256']:
            raise ValueError('Checkpoint hash mismatch: '+key)
    torch.set_num_threads(4)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    planner = GeometryPlanner().to(device)
    planner.load_state_dict(torch.load(pipeline['planner_checkpoint'], map_location=device, weights_only=True)['state_dict'])
    planner.eval()
    floor = ConditionedNet().to(device)
    floor.load_state_dict(torch.load(pipeline['floor_checkpoint'], map_location=device, weights_only=True)['state_dict'])
    floor.eval()
    with np.load(base/'output/training/planner-v7/validation_predictions.npz') as saved:
        contexts, targets, saved_predictions = [saved[k].copy() for k in ('x', 'y', 'prediction')]
    selected = None
    # This is an explicitly selected inspection example, not a new evaluation.
    # Selection considers predicted display geometry, never the hidden reference.
    for index, (context, saved_prediction) in enumerate(zip(contexts, saved_predictions)):
        if len(ports(context)) < 3 or np.sum(saved_prediction[0, 12:20, 12:20] >= .5) < 8:
            continue
        try:
            cells, outline = outline_for(footprint(context, saved_prediction))
        except ValueError:
            continue
        if len(cells) < 100:
            continue
        matrix = infer(planner, context[None], True, device)[0]
        plans, solver = proposal_plans(matrix)
        predictions = complete(floor, np.repeat(context[None], len(plans), axis=0), plans, device)
        costs = [rank_cost(context, prediction, plan, matrix)
                 for prediction, plan in zip(predictions, plans)]
        winner = min(range(len(plans)), key=lambda i: costs[i]['total'])
        prediction = predictions[winner]
        cells, outline = outline_for(footprint(context, prediction))
        if not np.array_equal(footprint(context, prediction), footprint(context, saved_prediction)):
            raise ValueError('Fresh inference disagrees with archived display footprint')
        selected = index, context, prediction, cells, outline, plans, winner, costs, matrix, solver
        break
    if selected is None:
        raise RuntimeError('No connected, hole-free demonstration found; do not silently repair predictions')
    index, context, prediction, cells, outline, plans, winner, costs, matrix, solver = selected
    lights = []
    for y in (-640, 0, 640):
        for x in (-640, 0, 640):
            if (x//64, y//64) in cells:
                lights.append({'id':f'demo_{len(lights)}', 'center':[x+32, y+32, 0], 'size':[64,64,256]})
    plan = {'design_choices':{'regions':lights, 'connections':[], 'corridor_width_units':128,
                             'floor_cell_override':sorted(map(list, cells)), 'floor_polygon_override':outline}}
    exe = args.cs2/'game/bin/win64/dmxconvert.exe'
    reference = args.cs2/'content/csgo_addons/aitesting/maps/aitesting.vmap'
    with tempfile.TemporaryDirectory(prefix='hammergpt-learned-demo-') as folder:
        folder = Path(folder)
        convert(exe, reference, folder/'source.txt', 'keyvalues2')
        header, roots = parse((folder/'source.txt').read_text(encoding='utf-8-sig'))
        result, meshes, validation = create_surface_blockout(roots, plan)
        root = next(r for r in result if r.kind == 'CMapRootElement')
        world = get(root, 'world'); children = get(world, 'children')
        next_id = max(int(get(n, 'nodeID')) for r in result for n in walk(r) if 'nodeID' in n.attrs)+1
        # A removable thin overhead frame marks the exact generated area.
        strips = [[(-250,-258,288),(250,-258,288),(250,-254,288),(-250,-254,288)],
                  [(-250,254,288),(250,254,288),(250,258,288),(-250,258,288)],
                  [(-258,-250,288),(-254,-250,288),(-254,250,288),(-258,250,288)],
                  [(254,-250,288),(258,-250,288),(258,250,288),(254,250,288)]]
        guide = make_surface(children[0], next_id, strips)
        children.append(guide)
        set_value(world, 'children', children)
        camera = get(root, 'defaultcamera')
        set_value(camera, 'position', '0 -1800 2400'); set_value(camera, 'lookat', '0 0 0')
        (folder/'demo.txt').write_text(serialize(header, result), encoding='utf-8')
        convert(exe, folder/'demo.txt', folder/'demo.vmap', 'binary')
        convert(exe, folder/'demo.vmap', folder/'check.txt', 'keyvalues2')
        _, checked = parse((folder/'check.txt').read_text(encoding='utf-8-sig'))
        before = [n for r in result for n in walk(r) if n.kind == 'CMapMesh']
        after = [n for r in checked for n in walk(r) if n.kind == 'CMapMesh']
        if len(before) != len(after):
            raise ValueError('Round-trip mesh count changed')
        for a, b in zip(before, after):
            validate_topology(b)
            for key in ('edgeVertexIndices','edgeOppositeIndices','edgeNextIndices','edgeFaceIndices','faceEdgeIndices'):
                if get(get(a, 'meshData'), key) != get(get(b, 'meshData'), key):
                    raise ValueError('Round-trip mesh topology changed')
            if get(positions(a), 'data') != get(positions(b), 'data'):
                raise ValueError('Round-trip vertex positions changed')
        args.artifacts.mkdir(parents=True)
        manifest = json.loads((base/'output/training/pilot-v1/manifest.json').read_text())
        record = next(r for r in manifest['examples'] if r['split'] == 'validation' and r['array_index'] == index)
        provenance = {'output':str(args.output.resolve()), 'example':record, 'pipeline':pipeline,
                      'device':str(device), 'candidate_plans':plans, 'chosen_candidate':winner,
                      'candidate_costs':costs, 'pair_scores':matrix.tolist(), 'solver':solver,
                      'floor_validation':validation, 'guide_node_id':next_id,
                      'omitted_unrelated_visible_floor_cells':int(footprint(context,prediction).sum())-len(cells),
                      'learned_bounds':[-256,-256,256,256], 'generated_floor_cells':int(np.sum(prediction[0,12:20,12:20]>=.5)),
                      'exported_floor_cells':len(cells), 'wall_segments':len(outline),
                      'limitations':['Selected Office development example, not a new evaluation or a complete learned map.',
                                     'Visible footprint is recorded context. Model predicts only the central 8x8 cells.',
                                     'Exporter adds flat floors, 256-unit walls, lights and removable overhead guide.',
                                     'Unrelated visible NAV islands are omitted; all predicted hidden floor is preserved.',
                                     'No geometry repairs or contour smoothing; collinear edges are merged exactly.',
                                     'Converter and topology checked; Hammer rendering, compile, collision and gameplay remain unverified.']}
        (args.artifacts/'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
        (args.artifacts/'proposal.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        np.savez_compressed(args.artifacts/'prediction.npz', context=context, prediction=prediction,
                            reference=targets[index])
        preview(context, prediction, targets[index], args.artifacts/'comparison.svg', cells)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as stream:
            stream.write((folder/'demo.vmap').read_bytes())
    print(json.dumps({'output':str(args.output), 'example_index':index, 'ports':len(ports(context)),
                      'floor_cells':len(cells), 'generated_floor_cells':provenance['generated_floor_cells'],
                      'wall_segments':len(outline), 'device':str(device), 'roundtrip':'passed'}))


if __name__ == '__main__':
    main()
