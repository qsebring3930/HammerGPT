"""Unreviewed Train battlefront guesses grounded in the repaired source NAV."""
import argparse
import hashlib
import json
from pathlib import Path
from annotate_boundaries import select_surfaces
from annotate_cobblestone_boundaries import draw

MEETINGS=[
 ('M1','Merged T Main / Ivy outer yard',[-550,100,-240,1150,670,-150]),
 ('M2','Inside Ivy encounter',[575,650,-240,1631,1742,-140]),
 ('M3','Popdog / west-yard encounter',[-560,-280,-240,100,160,-160]),
 ('M4','Back of B / T upper drop encounter',[-1155,-1080,-330,-570,-430,110]),
 ('M5','Upper B balcony / nearby lanes',[-550,-1810,-360,220,-1150,-120]),
]
CHOKES=[
 ('C1','T Main exit to outer yard','region_307','region_104','initial_attack_front'),
 ('C2','Ivy exit to outer yard','region_1003','region_169','initial_attack_front'),
 ('C3','Popdog lower exit','region_173','region_104','initial_attack_front_vertical_approach_unmodeled'),
 ('C4','Lower B entrance','region_738','region_1587','initial_attack_front'),
 ('C5','Upper B entrance / balcony','region_1843','region_1519','initial_attack_front'),
 ('C6','Connector B-side access','region_156','region_626','rotation_or_retake_candidate'),
 ('C7','Upper Ivy / Alley entrance','region_1038','region_1003','user_specified_choke_context'),
]

def build(graph):
 if graph['map']!='Train' or graph['dataset_role']!='training':raise ValueError('Requires approved Train training reference')
 labels=list({n['label'] for n in graph['nodes']});nodes={n['id']:n for n in graph['nodes']};meetings=[];chokes=[]
 for key,title,bounds in MEETINGS:
  context_labels=['Ivy'] if key=='M2' else labels
  pieces=select_surfaces(graph,context_labels,bounds)
  if not pieces:raise ValueError('Empty meeting proposal '+key)
  meetings.append({'id':key,'title':title,'kind':'meeting_area','location_review_status':'agent_hypothesis',
   'boundary_review_status':'pending_user_review','context_place_labels':context_labels,'proposed_roi_xyz':bounds,'surface_pieces':pieces,'supervision_mask':False})
  if key in ['M1','M2']:
   meetings[-1]['location_review_status']='user_correction_applied'
  if key=='M1':
   meetings[-1]['merged_previous_meeting_ids']=['M1','M2']
 for key,title,a,b,purpose in CHOKES:
  links=[e for e in graph['edges'] if {e['source'],e['target']}=={a,b}]
  if not links or any(not e['witnesses'] for e in links):raise ValueError('Missing access evidence '+key)
  pts=[p for e in links for w in e['witnesses'] for p in w['source_edge_endpoints']]
  bounds=[min(p[i] for p in pts)-(48 if i<2 else 24) for i in range(3)]
  bounds += [max(p[i] for p in pts)+(48 if i<2 else 24) for i in range(3)]
  pieces=select_surfaces(graph,[nodes[a]['label'],nodes[b]['label']],bounds)
  chokes.append({'id':key,'title':title,'kind':'choke_transition','location_review_status':'agent_hypothesis',
   'boundary_review_status':'pending_user_review','supervision_mask':False,'purpose_proposed':purpose,
   'interfaces':[{'sub_id':key,'region_pair':[a,b],'directed_links':links,'proposed_neighborhood_xyz':bounds}], 'surface_pieces':pieces})
 return {'map':'Train','status':'user_corrections_applied_boundaries_pending_review','training_eligible':False,
  'model_training_performed':False,'meetings':meetings,'chokes':chokes,'source_graph':graph,
  'basis':'Source place context, directed local entries, elevation separation and spawn/objective route evidence.',
  'user_corrections':['connect m1 and m2 into one area and then there is a different meeting area inside of ivy, with chokepoint at the top of ivy',
    'yes, move m4 more towards the left into back of b as ct and t meet around that drop down from t side upper into back of b'],
  'prior_draft_review':{'artifact':'train-boundaries-v2','feedback':'yes, move m4 more towards the left into back of b',
    'scope':'Prior draft accepted with requested M4 correction; corrected M4 numerical footprint awaits review.'},
  'display_subtitle':'M4 moved into Back of B around the T Side Upper drop. Original yard and Ivy corrections retained.',
  'display_notes':['M1 combines the old M1 and M2 extents.','M2 is now the separate space inside Ivy.',
    'C7 is the upper Ivy / Alley entrance.','C2 remains the yard-side Ivy exit.',
    'M4 now covers the Back of B drop encounter.','No training performed; new M4 extent pending.'],
  'limits':['User corrected M1/M2 grouping and specified an upper Ivy choke. Numerical extents and other guesses remain pending review.',
    'Meeting patches are authored XYZ selections clipped to NAV; not rectangular room targets.',
    'Popdog C3 uses the ground-level LongDog exit only. The source has 11 ladders outside the current route model.',
    'Upper and lower B selections retain elevation; projection can overlap distinct floors.',
    'Connector C6 is a rotation/retake candidate, not asserted to be an opening battlefront.',
    'All original source regions and directed edges preserved. No new training or source-map changes.']}

def run(source,output):
 if output.exists():raise ValueError('Use a new output directory')
 raw=source.read_bytes();draft=build(json.loads(raw))
 draft.update(source_graph_sha256=hashlib.sha256(raw).hexdigest(),annotator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 output.mkdir(parents=True);(output/'boundaries.json').write_text(json.dumps(draft,indent=2));draw(draft,output/'overview.png')
 lines=['# Train agent battlefront guesses','','Hypotheses for review, not approved training labels.','']
 lines += [f"- {m['id']}: {m['title']}." for m in draft['meetings']]
 lines += ['']+[f"- {c['id']}: {c['title']} ({c['purpose_proposed']})." for c in draft['chokes']]
 lines += ['','## Limits','']+['- '+s for s in draft['limits']]
 (output/'review.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({'meeting_proposals':len(draft['meetings']),'choke_proposals':len(draft['chokes']),'training_eligible':False}))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();run(a.source,a.output)
