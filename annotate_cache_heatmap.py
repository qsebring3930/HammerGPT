"""Record qualitative screenshot evidence separately from gameplay targets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont


CONTEXTS = [
    ('H1', 'A site and nearby firing positions', ['BombsiteA','Quad','Corner','Squeaky','ForkLift','AMain']),
    ('H2', 'Mid and connecting firing positions', ['Mid','Highway','Connector','Sandbags','Vents']),
    ('H3', 'B site and nearby firing positions', ['BombsiteB','Headshot','BMain','Checkers','BackHall']),
]
OPENING_CONTEXTS = [
    ('O1', 'A entry and nearby opening positions', ['AMain','ForkLift','Squeaky','BombsiteA']),
    ('O2', 'Mid access and opening positions', ['Mid','Highway','Connector','Sandbags','Vents']),
    ('O3', 'B entry and nearby opening positions', ['BMain','Checkers','BackHall','TreeRoom','BombsiteB']),
]


def build(graph, image):
    if graph['map']!='Cache' or graph['dataset_role']!='training':
        raise ValueError('Requires the approved Cache training reference')
    contexts=[]
    for key,title,labels in CONTEXTS:
        ids=[n['id'] for n in graph['nodes'] if n['label'] in labels]
        contexts.append({'id':key,'title':title,'proposed_source_place_context':labels,
                         'region_ids':ids,'evidence_type':'qualitative_killer_location_cluster',
                         'review_status':'pending_source_correspondence_review','supervision_mask':False,
                         'interpretation':'Broad visual correspondence only; full place-group extent is not a measured heatmap mask.'})
    return {'map':'Cache','status':'heatmap_recorded_contexts_pending_review','training_eligible':False,
            'model_training_performed':False,'reference_image':str(image.resolve()),
            'reference_image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
            'screenshot_metadata':{'displayed_kill_count':131333,'selected_dataset':'killer_location',
                                   'side_filter':'Both appears selected; not independently verified',
                                   'selected_filter':'Kills appears selected',
                                   'first_kills_only':'not visibly selected; exact query unavailable',
                                   'match_count':None,'date_range':None,'map_version':None,
                                   'raw_event_coordinates_available':False,'color_scale_available':False},
            'registration':{'performed':False,'basis':'Visual comparison of source NAV and screenshot overview'},
            'contexts':contexts,'source_graph':graph,
            'limits':['Killer-location density describes firing positions, not victim positions or initial control.',
                      'Aggregate kills can combine opening fights, executes, retakes and later-round play.',
                      'Hotspot context is not a chokepoint label; chokepoints require local access evidence.',
                      'Unknown sample composition and color scale prevent normalized kill rates or cross-map comparisons.',
                      'No pixel density or quantitative target is extracted; broad source context extents await review.']}


def build_first_kills(graph,image):
    draft=build(graph,image)
    draft['event_scope']='first_kills'
    draft['user_metadata_confirmation']={'event_scope':'here is a heatmap of first kills',
                                         'location_dataset':'Killer positions'}
    draft['screenshot_metadata']={'displayed_kill_count':None,'selected_dataset':'killer_location',
                                  'first_kills_only':True,'dataset_basis':'explicit user confirmation',
                                  'side_filter':None,'match_count':None,'date_range':None,'map_version':None,
                                  'raw_event_coordinates_available':False,
                                  'qualitative_legend_visible':True,'numeric_color_scale_available':False}
    draft['contexts']=[]
    for key,title,labels in OPENING_CONTEXTS:
        draft['contexts'].append({'id':key,'title':title,'proposed_source_place_context':labels,
                                  'region_ids':[n['id'] for n in graph['nodes'] if n['label'] in labels],
                                  'evidence_type':'qualitative_opening_killer_location_cluster',
                                  'review_status':'pending_source_correspondence_review','supervision_mask':False,
                                  'interpretation':'Candidate opening-fight context, not a full-place hotspot mask or measured arrival front.'})
    draft['limits']=['Opening-kill killer positions locate successful firing positions, not both duel endpoints.',
                     'First-kill filtering supports opening-fight hypotheses but does not measure arrival timing or initial control.',
                     'Broad source place correspondences need review; no image registration or numeric heat extraction performed.',
                     'Sample count, map version and numeric scale are unknown. Compare with the aggregate screenshot qualitatively only.',
                     'No chokepoint label is inferred from a bright pixel; local NAV/geometry evidence remains necessary.']
    return draft


def draw(draft,path):
    graph=draft['source_graph'];im=Image.new('RGB',(1500,1100),'#101a26');pen=ImageDraw.Draw(im)
    def font(size):return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    points=[c for p in graph['nav_polygons'] for c in p['corners']]
    lo=[min(c[i] for c in points) for i in range(2)];hi=[max(c[i] for c in points) for i in range(2)]
    scale=min(870/(hi[0]-lo[0]),870/(hi[1]-lo[1]))
    def xy(p):return 35+(p[0]-lo[0])*scale,125+(hi[1]-p[1])*scale
    selected={r for context in draft['contexts'] for r in context['region_ids']}
    for p in sorted(graph['nav_polygons'],key=lambda p:sum(c[2] for c in p['corners'])):
        pen.polygon([xy(c) for c in p['corners']],fill='#d2ad51' if p['region_id'] in selected else '#465563')
    reps={}
    for n in graph['nodes']:
        label=n['label']
        if label and (label not in reps or len(n['nav_area_ids'])>len(reps[label]['nav_area_ids'])):reps[label]=n
    for label,n in reps.items():
        x,y=xy(n['position']);box=pen.textbbox((x,y),label,font=font(13))
        pen.rectangle((box[0]-2,box[1]-1,box[2]+2,box[3]+1),fill='#101a26');pen.text((x,y),label,font=font(13),fill='#eef2fa')
    for context in draft['contexts']:
        n=reps[context['proposed_source_place_context'][0]];x,y=xy(n['position']);y-=30
        pen.rectangle((x-18,y-12,x+18,y+12),fill='#101a26',outline='#e7cc58')
        pen.text((x-13,y-10),context['id'],font=font(16),fill='#e7cc58')
    opening=draft.get('event_scope')=='first_kills'
    heading='Cache: first-kill context proposals' if opening else 'Cache: qualitative kill-heatmap context proposals'
    pen.text((30,25),heading,font=font(28),fill='#eef2fa')
    pen.text((30,72),'Gold = broad source-place correspondence proposals. This is not a recreated heatmap.',font=font(18),fill='#becbda')
    pen.text((960,155),'Screenshot evidence',font=font(23),fill='#e7cc58')
    evidence=['First kills: user-supplied filter','Killer positions: user-confirmed','Kill count and numeric scale unknown','Map version and match count unknown'] if opening else ['131,333 kills displayed','Killer-location view selected','No event coordinates or color scale','Map version and match count unknown']
    for i,line in enumerate(evidence):
        pen.text((960,205+i*35),line,font=font(18),fill='#becbda')
    for i,c in enumerate(draft['contexts']):
        y=405+i*95
        pen.text((960,y),c['id']+': '+c['title'],font=font(18),fill='#eef2fa')
        pen.text((960,y+30),'Source context extent awaits review',font=font(16),fill='#becbda')
    notes=['Opening firing-position evidence.','Victim positions remain unknown.','No choke or initial-control labels inferred.',
           'Source NAV and screenshot not registered.','No training performed from this draft.'] if opening else ['Firing-position evidence only.','Opening fights are not isolated.','No choke or initial-control labels inferred.',
                             'Source NAV and screenshot not registered.','No training performed from this draft.']
    for i,line in enumerate(notes):
        pen.text((960,770+i*38),line,font=font(17),fill='#becbda')
    im.save(path)


def run(source,image,output,first_kills=False,comparison=None):
    if output.exists():raise ValueError('Use a new artifact directory')
    raw=source.read_bytes();draft=(build_first_kills if first_kills else build)(json.loads(raw),image)
    if comparison:
        comparison_raw=comparison.read_bytes();prior=json.loads(comparison_raw)
        if prior['map']!='Cache' or prior['source_graph_sha256']!=hashlib.sha256(raw).hexdigest():
            raise ValueError('Comparison must refer to the same Cache source graph')
        draft['aggregate_comparison']={'artifact':str(comparison.resolve()),'artifact_sha256':hashlib.sha256(comparison_raw).hexdigest(),
                                       'method':'Qualitative visual comparison only; no pixel subtraction or normalized density ratios',
                                       'observations':['Site and central contexts remain candidates across both views.',
                                                       'First-kill screenshot highlights smaller local concentrations around access positions; exact world-space correspondence remains unregistered.'],
                                       'same_event_sample_verified':False}
    draft.update(source_graph_sha256=hashlib.sha256(raw).hexdigest(),annotator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True);shutil.copyfile(image,output/'reference-heatmap.png')
    (output/'heatmap-context.json').write_text(json.dumps(draft,indent=2));draw(draft,output/'overview.png')
    intro=('The user supplied a first-kill heatmap and explicitly confirmed killer positions. Kill count, match count and numeric color calibration are unknown. '
           'Three opening-fight context correspondences are proposed; complete place groups are not hotspot masks.' if first_kills else
           'The screenshot displays 131,333 kills with Killer location selected. Three broad firing-position context correspondences are proposed on the repaired source NAV. They are not quantitative heat masks or approved battlefronts.')
    lines=['# Cache supplied heatmap context','',intro,'']
    for c in draft['contexts']:lines.append(f"- {c['id']}: {c['title']}. Source place contexts: {', '.join(c['proposed_source_place_context'])}.")
    lines+=['','## Limits','']+['- '+line for line in draft['limits']]
    (output/'review.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'contexts':3,'training_eligible':False,'displayed_kills':draft['screenshot_metadata']['displayed_kill_count'],'first_kills':first_kills}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--reference-image',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--first-kills',action='store_true');p.add_argument('--comparison',type=Path)
    a=p.parse_args();run(a.source,a.reference_image,a.output,a.first_kills,a.comparison)
