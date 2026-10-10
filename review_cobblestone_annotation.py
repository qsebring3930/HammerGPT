"""Record the user's final Cobblestone boundary approval."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from annotate_cobblestone_boundaries import draw

def run(source,output):
    if output.exists():raise ValueError('Use a new output directory')
    raw=source.read_bytes();result=copy.deepcopy(json.loads(raw));graph=result['source_graph']
    if graph['map']!='Cobblestone' or graph['dataset_role']!='training':raise ValueError('Requires approved Cobblestone')
    for item in result['meetings']+result['chokes']:
        item.update(location_review_status='user_reviewed_first_pass',boundary_review_status='user_reviewed_first_pass',supervision_mask=True)
    result.update(status='reviewed_first_pass_meeting_and_choke_boundaries',training_eligible=True,
                  reviewed_draft_sha256=hashlib.sha256(raw).hexdigest(),
                  user_review={'statement':'thats correct, can we move on to training now','applies_to':'cobblestone-boundaries-v2'},
                  eligible_target_scope='Three meeting footprints and four first-pass choke groups only; no control, timing, sightline or clearance targets.',
                  display_subtitle='Review complete: three meeting areas and four choke groups.',
                  display_notes=['Meeting and choke boundaries reviewed.','Original directed witnesses retained.',
                                 'CT spawn / A coarse overlap unresolved.','No timing or visibility labels inferred.',
                                 'Source topology and elevations preserved.','No source-map changes.'])
    result['limits']=['User approved first-pass meeting/choke locations and extents.',
                      'CT independent-access ambiguity remains outside gameplay labels.',
                      'Reviewed masks do not certify physical clearance, initial control, arrival timing or visibility.']
    targets={'map':'Cobblestone','dataset_role':'training','training_performed':False,
             'source_graph_sha256':result['source_graph_sha256'],'nodes':graph['nodes'],'directed_edges':graph['edges'],
             'nav_polygons':graph['nav_polygons'],'anchors':graph['anchors'],
             'meeting_targets':result['meetings'],'choke_targets':result['chokes'],
             'eligible_target_scope':result['eligible_target_scope']}
    output.mkdir(parents=True);(output/'annotation.json').write_text(json.dumps(result,indent=2))
    (output/'semantic-targets.json').write_text(json.dumps(targets,indent=2));draw(result,output/'overview.png')
    print(json.dumps({'reviewed_meetings':3,'reviewed_choke_groups':4,'training_performed':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
