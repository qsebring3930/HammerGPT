"""Record user-named Cache doorway contexts with directed NAV evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image,ImageDraw,ImageFont
from annotate_boundaries import select_surfaces


SPECS=[
    ('C1','A Halls left exit into A','Squeaky','BombsiteA',
     'A Halls reaches the site through the source Squeaky context; doorway match is proposed.'),
    ('C2','A Main into A','AMain','BombsiteA','Direct named-place interface.'),
    ('C3','Red-side doorway into Mid','Garage','Mid',
     'Source Red connects to Garage; this proposes the Mid-facing Garage exit, not a nonexistent direct Red/Mid edge.'),
    ('C4','Connector into Mid','Connector','Mid','Direct named-place interface.'),
    ('C5','B Main into B','BMain','BombsiteB','Direct named-place interface.'),
]


def build(graph):
    if graph['map']!='Cache' or graph['dataset_role']!='training':raise ValueError('Requires approved Cache training reference')
    nodes={n['id']:n for n in graph['nodes']};annotations=[]
    for key,title,a,b,note in SPECS:
        links=[e for e in graph['edges'] if {nodes[e['source']]['label'],nodes[e['target']]['label']}=={a,b}]
        if not links or any(not e['witnesses'] for e in links):raise ValueError('Missing choke evidence '+key)
        points=[p for e in links for w in e['witnesses'] for p in w['source_edge_endpoints']]
        bounds=[min(p[i] for p in points)-(48 if i<2 else 24) for i in range(3)]
        bounds += [max(p[i] for p in points)+(48 if i<2 else 24) for i in range(3)]
        pieces=select_surfaces(graph,[a,b],bounds)
        annotations.append({'id':key,'title':title,'kind':'choke_transition','user_location_status':'specified',
                            'review_status':'pending_source_match_and_neighborhood_review','supervision_mask':False,
                            'source_place_pair':[a,b],'directed_links':links,'interpretation':note,
                            'proposed_neighborhood_xyz':bounds,'surface_pieces':pieces})
    return {'map':'Cache','status':'user_choke_locations_recorded_boundaries_pending','training_eligible':False,
            'model_training_performed':False,'annotations':annotations,'source_graph':graph,
            'user_feedback':['doorway between the left side of A halls and the bombsite',
                             'doorway between A main and the bombsite',
                             'the doorway between red and mid',
                             'the doorway between connector and mid',
                             'the doorway between b main and b bombsite'],
            'limits':['Locations are user-specified; exact source transition matches and expanded neighborhoods are proposals.',
                      'Red patches are NAV neighborhoods, not architectural door frames or clearance measurements.',
                      'Heatmap and opening-fight contexts remain separate evidence channels. No meeting boundaries approved here.',
                      'Original directed links and elevations remain preserved. No new training or source-map edits.']}


def draw(draft,path):
    graph=draft['source_graph'];im=Image.new('RGB',(1500,1100),'#101a26');pen=ImageDraw.Draw(im)
    def font(size):return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    points=[c for p in graph['nav_polygons'] for c in p['corners']]
    lo=[min(c[i] for c in points) for i in range(2)];hi=[max(c[i] for c in points) for i in range(2)]
    scale=min(875/(hi[0]-lo[0]),870/(hi[1]-lo[1]))
    def xy(p):return 35+(p[0]-lo[0])*scale,125+(hi[1]-p[1])*scale
    for p in sorted(graph['nav_polygons'],key=lambda p:sum(c[2] for c in p['corners'])):
        pen.polygon([xy(c) for c in p['corners']],fill='#465563')
    meeting_regions={r for b in draft.get('battlegrounds',[]) for r in b['region_ids']}
    for p in graph['nav_polygons']:
        if p['region_id'] in meeting_regions:
            pen.polygon([xy(c) for c in p['corners']],fill='#d2ad51')
    for item in draft['annotations']:
        for p in item['surface_pieces']:pen.polygon([xy(c) for c in p['corners']],fill='#bc666e')
    reps={}
    for n in graph['nodes']:
        label=n['label']
        if label and (label not in reps or len(n['nav_area_ids'])>len(reps[label]['nav_area_ids'])):reps[label]=n
    for label,n in reps.items():
        x,y=xy(n['position']);box=pen.textbbox((x,y),label,font=font(13))
        pen.rectangle((box[0]-2,box[1]-1,box[2]+2,box[3]+1),fill='#101a26');pen.text((x,y),label,font=font(13),fill='#eef2fa')
    for item in draft['annotations']:
        pts=[]
        for e in item['directed_links']:
            for w in e['witnesses']:
                segment=[xy(p) for p in w['source_edge_endpoints']];pts.extend(segment)
                pen.line(segment,fill='#ff6666',width=4)
        x=sum(p[0] for p in pts)/len(pts);y=sum(p[1] for p in pts)/len(pts)-20
        pen.rectangle((x-17,y-12,x+17,y+12),fill='#101a26',outline='#ff9999');pen.text((x-12,y-10),item['id'],font=font(16),fill='#ffaaaa')
    reviewed=draft.get('status')=='reviewed_first_pass_chokes_and_battleground_context'
    pen.text((30,25),'Cache: reviewed chokes and battleground context' if reviewed else 'Cache: user-specified choke locations',font=font(29),fill='#eef2fa')
    pen.text((30,72),'Gold = named battleground context; red = reviewed choke neighborhood; lines = source NAV evidence.' if reviewed else 'Red = proposed doorway neighborhood; bright lines retain source NAV transition evidence.',font=font(18),fill='#becbda')
    for i,item in enumerate(draft['annotations']):
        y=170+i*88
        pen.text((960,y),item['id']+': '+item['title'],font=font(20),fill='#eef2fa')
        pen.text((960,y+30),'Source: '+' / '.join(item['source_place_pair']),font=font(16),fill='#becbda')
    if reviewed:
        pen.text((960,665),'Battlegrounds: A Main, B Main, Mid',font=font(19),fill='#e7cc58')
    notes=['Five choke locations reviewed.','Squeaky and Garage matches confirmed.',
           'Gold shows source place-group context.', 'Precise meeting boundaries are unmeasured.',
           'Heatmap density remains separate evidence.', 'Timing and visibility remain unmeasured.',
           'No new training or source-map changes.'] if reviewed else ['C1 uses the Squeaky-side entrance.','C3 uses the Garage-to-Mid doorway.',
           'Confirm these two naming correspondences.','Other doorway locations retain NAV witnesses.',
           'Exact neighborhoods await review.','Heatmap context remains separate.','No new training or source-map changes.']
    for i,line in enumerate(notes):pen.text((960,720+i*37),line,font=font(17),fill='#becbda')
    im.save(path)


def run(source,output):
    if output.exists():raise ValueError('Use a new output directory')
    raw=source.read_bytes();draft=build(json.loads(raw))
    draft.update(source_graph_sha256=hashlib.sha256(raw).hexdigest(),annotator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True);(output/'chokes.json').write_text(json.dumps(draft,indent=2));draw(draft,output/'overview.png')
    lines=['# Cache user-specified choke draft','','Five gameplay doorway locations are recorded. Exact source matches and neighborhood masks await review.','']
    for item in draft['annotations']:lines.append(f"- {item['id']}: {item['title']}. {item['interpretation']}")
    lines+=['','Review priority: Does C1 match the A Halls/Squeaky doorway, and C3 the Red-side Garage exit into Mid?','']+draft['limits']
    (output/'review.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'choke_locations':5,'training_eligible':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
