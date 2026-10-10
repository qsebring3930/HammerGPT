"""Finalize the user's Train review, removing M5 without changing the source map."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from annotate_cobblestone_boundaries import draw


def run(source,output):
    if output.exists():raise ValueError('Use a new review directory')
    raw=source.read_bytes();draft=json.loads(raw);result=copy.deepcopy(draft);graph=result['source_graph']
    if graph['map']!='Train' or graph['dataset_role']!='training':raise ValueError('Requires approved Train training reference')
    if len([m for m in result['meetings'] if m['id']=='M5'])!=1:raise ValueError('Expected exactly one M5 proposal')
    result['meetings']=[m for m in result['meetings'] if m['id']!='M5']
    for item in result['meetings']+result['chokes']:
        item.update(location_review_status='user_reviewed_first_pass',boundary_review_status='user_reviewed_first_pass',supervision_mask=True)
    result.update(status='reviewed_first_pass_meeting_and_choke_boundaries',training_eligible=True,
        reviewed_draft_sha256=hashlib.sha256(raw).hexdigest(),removed_meeting_ids=['M5'],
        user_review={'statement':'remove m5 and we are finished','applies_to':'train-boundaries-v3'},
        eligible_target_scope='Four reviewed meeting footprints and seven first-pass choke neighborhoods only; no timing, visibility, clearance or initial-control targets.',
        display_subtitle='Review complete: four meeting areas and seven choke contexts. M5 removed.',
        display_notes=['M1: merged outer-yard meeting space.','M2: separate encounter inside Ivy.',
                       'M4: Back of B / T Side Upper drop.','M5 removed; C5 upper B choke retained.',
                       'Popdog ladder approach remains unmodeled.','Reviewed spatial context; no new training.'])
    result['limits']=['Reviewed footprint context does not certify arrival timings, doorway clearance or sightlines.',
                      'M5 removal withdraws that meeting proposal; it does not assert a negative encounter label there.',
                      'C5 upper B entrance remains a reviewed choke, separate from the removed M5 meeting mask.',
                      'Original source regions, edges, elevations and NAV polygons remain preserved.',
                      'Popdog C3 covers the lower exit only; 11 source ladders remain outside the current route model.',
                      'No source-map edits or new model training occurred.']
    targets={'map':'Train','dataset_role':'training','training_performed':False,'source_graph_sha256':result['source_graph_sha256'],
             'nodes':graph['nodes'],'directed_edges':graph['edges'],'nav_polygons':graph['nav_polygons'],'anchors':graph['anchors'],
             'meeting_targets':result['meetings'],'choke_targets':result['chokes'],
             'eligible_target_scope':result['eligible_target_scope'],'removed_meeting_ids':['M5']}
    output.mkdir(parents=True);(output/'annotation.json').write_text(json.dumps(result,indent=2))
    (output/'semantic-targets.json').write_text(json.dumps(targets,indent=2));draw(result,output/'overview.png')
    (output/'review.md').write_text('User finalized Train review: "remove m5 and we are finished". M5 is removed; M1-M4 and C1-C7 are recorded as first-pass reviewed spatial contexts. C5 remains an upper B choke, independently of the withdrawn meeting proposal. Original drafts and source topology are preserved. No negative encounter label is inferred from M5 removal. Timing, visibility, clearance and initial-control labels remain outside review scope. No new training occurred.\n')
    print(json.dumps({'reviewed_meetings':len(result['meetings']),'reviewed_chokes':len(result['chokes']),'removed':['M5'],'training_performed':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
