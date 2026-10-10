"""Record approved Cache choke matches and user-named battleground context."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from annotate_cache_chokes import draw


def run(source,output):
    if output.exists():raise ValueError('Use a new review directory')
    raw=source.read_bytes();draft=json.loads(raw);result=copy.deepcopy(draft);graph=result['source_graph']
    if graph['map']!='Cache' or graph['dataset_role']!='training':raise ValueError('Requires approved Cache training reference')
    result.update(status='reviewed_first_pass_chokes_and_battleground_context',training_eligible=True,
                  reviewed_draft_sha256=hashlib.sha256(raw).hexdigest(),model_training_performed=False,
                  user_review={'statement':'yes this looks correct, the battlegrounds are b main, a main, and mid',
                               'applies_to':'cache-chokes-v1'},
                  eligible_target_scope='Five reviewed choke locations/neighborhoods and three named battleground contexts. No exact meeting footprints, initial-control, timing or heat-density targets.')
    for item in result['annotations']:
        item.update(review_status='reviewed_first_pass_choke_location_and_neighborhood',supervision_mask=True)
    result['battlegrounds']=[]
    for key,title,label in [('M1','A Main','AMain'),('M2','B Main','BMain'),('M3','Mid','Mid')]:
        ids=[n['id'] for n in graph['nodes'] if n['label']==label]
        if not ids:raise ValueError('Missing battleground source context')
        result['battlegrounds'].append({'id':key,'title':title,'source_place_label':label,'region_ids':ids,
                                       'role':'battleground_context','review_status':'user_specified_role_context',
                                       'supervision_mask':True,'exact_meeting_boundary_reviewed':False})
    result['limits']=['User reviewed five choke source matches and their first-pass neighborhoods.',
                      'A Main, B Main and Mid are named battleground contexts; their complete source-place footprints are not precise encounter masks.',
                      'Non-battleground regions have no supervised negative target; their tactical roles remain unassigned.',
                      'Heatmap correspondence and density remain separate, unreviewed evidence. No control or arrival-time labels inferred.',
                      'Preserve all original source nodes/edges; context groups must not be rendered as rectangular rooms. No new model training.']
    membership={r:b['id'] for b in result['battlegrounds'] for r in b['region_ids']};nodes=[]
    for original in graph['nodes']:
        node=copy.deepcopy(original);zone=membership.get(node['id'])
        node.update(battleground_context_id=zone,battleground_context_target=True if zone else None,
                    battleground_context_supervision_mask=bool(zone))
        nodes.append(node)
    targets={'map':'Cache','dataset_role':'training','training_performed':False,'nodes':nodes,
             'directed_edges':graph['edges'],'nav_polygons':graph['nav_polygons'],'anchors':graph['anchors'],
             'battleground_contexts':result['battlegrounds'],'choke_targets':result['annotations'],
             'source_graph_sha256':result['source_graph_sha256'],'eligible_target_scope':result['eligible_target_scope']}
    output.mkdir(parents=True);(output/'annotation.json').write_text(json.dumps(result,indent=2))
    (output/'semantic-targets.json').write_text(json.dumps(targets,indent=2));draw(result,output/'overview.png')
    (output/'review.md').write_text('User approved Cache choke v1 and named B Main, A Main and Mid as battlegrounds. Five choke locations and neighborhoods are recorded as first-pass reviewed targets; three named source-place groups provide battleground context. Exact meeting footprints are not approved or measured. All other regions remain masked, with no supervised negative role inferred. Heatmap density, initial control, timing and sightlines remain outside this review. All source topology remains unchanged. No training performed.\n')
    print(json.dumps({'reviewed_chokes':5,'battleground_contexts':3,'supervised_context_regions':len(membership),'training_performed':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
