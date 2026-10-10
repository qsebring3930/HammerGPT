"""Record the user's approval of Anubis v3, preserving the draft and topology."""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def reviewed(draft):
    result = copy.deepcopy(draft)
    result.update(status='reviewed_first_pass_control_and_boundaries', training_eligible=True,
                  eligible_target_scope='Reviewed initial-control context, meeting subdivisions and access-front locations. No timing, sightline or clearance targets.',
                  user_review={'statement': 'this looks good', 'applies_to': 'anubis-control-v3'},
                  model_training_performed=False)
    for row in result['regions']:
        row['supervision_mask'] = row['initial_control_proposed'] != 'unresolved'
        row['review_status'] = 'reviewed_first_pass_context' if row['supervision_mask'] else 'unresolved'
    for item in result['spatial_subdivision_proposals']:
        item.update(review_status='reviewed_first_pass_boundaries', supervision_mask=True)
    for item in result['front_proposals']:
        item['review_status'] = 'reviewed_first_pass_location'
    # The two automatic direct-contact candidates remain superseded by explicit fronts.
    for route in result['route_evidence']:
        route['review_status'] = 'reviewed_first_pass_purpose'
    return result


def run(source, output):
    if output.exists():
        raise ValueError('Use a new review directory')
    raw = source.read_bytes()
    draft = json.loads(raw)
    graph = draft['source_graph']
    if graph['map'] != 'Anubis' or graph['dataset_role'] != 'training':
        raise ValueError('Requires approved Anubis training reference')
    result = reviewed(draft)
    result['reviewed_draft_sha256'] = hashlib.sha256(raw).hexdigest()
    contexts = {r['region_id']: r for r in result['regions']}
    nodes = []
    for original in graph['nodes']:
        node = copy.deepcopy(original)
        row = contexts[node['id']]
        node.update(initial_control_target=row['initial_control_proposed'],
                    initial_control_supervision_mask=row['supervision_mask'])
        nodes.append(node)
    targets = {'map': 'Anubis', 'dataset_role': 'training', 'training_performed': False,
               'source_graph_sha256': result['source_graph_sha256'], 'nodes': nodes,
               'directed_edges': graph['edges'], 'nav_polygons': graph['nav_polygons'],
               'spatial_targets': result['spatial_subdivision_proposals'],
               'front_contexts': result['front_proposals'], 'route_evidence': result['route_evidence'],
               'eligible_target_scope': result['eligible_target_scope']}
    output.mkdir(parents=True)
    (output/'initial-control.json').write_text(json.dumps(result, indent=2))
    (output/'control-targets.json').write_text(json.dumps(targets, indent=2))
    (output/'review.md').write_text(
        'User approved Anubis v3: "this looks good". Reviewed initial control, meeting subdivisions and access-front locations are eligible for context supervision. '
        'Unresolved whole regions remain masked, including Bridge and Canal, whose reviewed subdivisions are separate spatial targets. '
        'All 159 original nodes and 404 directed edges are preserved. No model training performed. '
        'Timing, sightlines, doorway clearance and permanent control are outside this approval.\n')
    print(json.dumps({'reviewed_context_regions': sum(n['initial_control_supervision_mask'] for n in nodes),
                      'masked_regions': sum(not n['initial_control_supervision_mask'] for n in nodes),
                      'spatial_targets': len(targets['spatial_targets']), 'training_performed': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.source, a.output)
