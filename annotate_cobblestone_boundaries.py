"""Translate user-specified Cobblestone encounters into NAV-grounded proposals."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from annotate_boundaries import select_surfaces


MEETINGS = [
    ('M1', 'Between Long A and Catwalk', ['LongA','Catwalk'], [-3480,400,-40,-2600,1152,100]),
    ('M2', 'Below Underpass / A approach', ['Underpass','ARamp'], [-2720,-700,-280,-1800,500,100]),
    ('M3', 'Upper / Lower tunnels', ['UpperTunnel','LowerTunnel','Tunnels'], [-1141,-803,-40,-635,130,180]),
]
CHOKES = [
    ('C1', 'Underpass doorway candidates', [('region_1956','region_1799'),('region_1798','region_1729')]),
    ('C2', 'Upper / Lower tunnel separation', [('region_382','region_539')]),
    ('C3', 'Long A toward upper hallway', [('region_3457','region_2948'),('region_2948','region_3133')]),
    ('C4', 'Tunnels into T main', [('region_149','region_1')]),
]


def build(graph):
    if graph['map']!='Cobblestone' or graph['dataset_role']!='training':
        raise ValueError('Requires approved Cobblestone training reference')
    meetings=[];chokes=[]
    for key,title,labels,bounds in MEETINGS:
        pieces=select_surfaces(graph,labels,bounds)
        if not pieces: raise ValueError('Empty meeting proposal '+key)
        meetings.append({'id':key,'title':title,'kind':'meeting_area','location_review_status':'user_specified',
                         'boundary_review_status':'pending_extent_review','context_place_labels':labels,
                         'proposed_roi_xyz':bounds,'surface_pieces':pieces,'supervision_mask':False})
    nodes={n['id']:n for n in graph['nodes']}
    for key,title,pairs in CHOKES:
        interfaces=[];pieces=[]
        for index,(a,b) in enumerate(pairs):
            links=[e for e in graph['edges'] if {e['source'],e['target']}=={a,b}]
            if not links:raise ValueError('Missing choke NAV evidence '+key)
            points=[p for e in links for w in e['witnesses'] for p in w['source_edge_endpoints']]
            # Neighborhood is a review mask, not an inferred architectural door.
            bounds=[min(p[i] for p in points)-(48 if i<2 else 24) for i in range(3)]
            bounds += [max(p[i] for p in points)+(48 if i<2 else 24) for i in range(3)]
            interfaces.append({'sub_id':key+chr(97+index) if len(pairs)>1 else key,
                               'region_pair':[a,b],'directed_links':links,'proposed_neighborhood_xyz':bounds})
            pieces.extend(select_surfaces(graph,[nodes[a]['label'],nodes[b]['label']],bounds))
        chokes.append({'id':key,'title':title,'kind':'choke_transition','location_review_status':'user_specified',
                       'boundary_review_status':'pending_source_transition_review','interfaces':interfaces,
                       'surface_pieces':pieces,'supervision_mask':False})
    return {'map':'Cobblestone','status':'user_locations_recorded_boundaries_pending','training_eligible':False,
            'model_training_performed':False,'meetings':meetings,'chokes':chokes,'source_graph':graph,
            'user_feedback':{'meeting_points':['In between longA and catwalk','The area below where you marked underpass','Upper Tunnels/Lower Tunnels'],
                             'chokepoints':['The doorways in underpass (you have it correct)',
                                            'The separation between upper and lower tunnels (you have it correct)',
                                            'The doorways inside of Long A towards the top hallway',
                                            'The doorway leading from tunnels into tmain']},
            'limits':['User specified gameplay locations; proposed numerical extents and exact NAV transition matches await review.',
                      'Meeting and choke channels may overlap. No initial-control labels inferred.',
                      'C1a is lower Underpass/A-ramp access; C1b is side Underpass/TunnelStairs access. Confirm both intended doors.',
                      'C3a is an internal LongA interface; C3b is the Catwalk-side exit. Confirm both intended hallway doors.',
                      'C2 retains the directed drop and its different elevations; a reverse connection is not invented.',
                      'Source NAV is not doorway clearance, visibility or arrival-time evidence.']}


def draw(draft,path):
    graph=draft['source_graph'];im=Image.new('RGB',(1530,1150),'#101a26');pen=ImageDraw.Draw(im)
    def font(size):return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    points=[c for p in graph['nav_polygons'] for c in p['corners']]
    lo=[min(c[i] for c in points) for i in range(2)];hi=[max(c[i] for c in points) for i in range(2)]
    scale=min(865/(hi[0]-lo[0]),945/(hi[1]-lo[1]))
    def xy(p):return 35+(p[0]-lo[0])*scale,120+(hi[1]-p[1])*scale
    for p in sorted(graph['nav_polygons'],key=lambda p:sum(c[2] for c in p['corners'])):
        pen.polygon([xy(c) for c in p['corners']],fill='#465563')
    for item in draft['meetings']+draft['chokes']:
        color='#e7cc58' if item['kind']=='meeting_area' else '#bc666e'
        for p in item['surface_pieces']:pen.polygon([xy(c) for c in p['corners']],fill=color)
    reps={}
    for n in graph['nodes']:
        l=n['label']
        if l and (l not in reps or len(n['nav_area_ids'])>len(reps[l]['nav_area_ids'])):reps[l]=n
    for l,n in reps.items():
        x,y=xy(n['position']);box=pen.textbbox((x,y),l,font=font(13))
        pen.rectangle((box[0]-2,box[1]-1,box[2]+2,box[3]+1),fill='#101a26');pen.text((x,y),l,font=font(13),fill='#edf2fa')
    for item in draft['meetings']:
        centers=[xy([sum(c[i] for c in p['corners'])/len(p['corners']) for i in range(3)]) for p in item['surface_pieces']]
        x=sum(c[0] for c in centers)/len(centers);y=sum(c[1] for c in centers)/len(centers)
        if graph['map']=='Cobblestone' and item['id']=='M3':
            x-=42;y-=8
        pen.rectangle((x-16,y-12,x+16,y+12),fill='#101a26',outline='#e7cc58');pen.text((x-12,y-10),item['id'],font=font(16),fill='#e7cc58')
    for item in draft['chokes']:
        for interface in item['interfaces']:
            coords=[]
            for e in interface['directed_links']:
                for w in e['witnesses']:
                    segment=[xy(p) for p in w['source_edge_endpoints']];coords.extend(segment)
                    pen.line(segment,fill='#ff6666',width=4)
            x=sum(p[0] for p in coords)/len(coords);y=sum(p[1] for p in coords)/len(coords)
            pen.rectangle((x-20,y-27,x+20,y-5),fill='#101a26',outline='#ff7777')
            pen.text((x-16,y-25),interface['sub_id'],font=font(15),fill='#ffaaaa')
    pen.text((30,25),f"{graph['map']}: meeting areas and choke transitions",font=font(28),fill='#edf2fa')
    pen.text((30,70),draft.get('display_subtitle','Your gameplay locations are recorded; NAV-clipped extents and doorway matches are proposals.'),font=font(18),fill='#becbda')
    y=150
    for title,items,color in [('Meeting areas',draft['meetings'],'#e7cc58'),('Choke groups',draft['chokes'],'#ff9999')]:
        pen.text((960,y),title,font=font(23),fill=color);y+=48
        for item in items:
            pen.text((960,y),item['id']+': '+item['title'],font=font(18),fill='#edf2fa');y+=45 if len(draft['meetings'])+len(draft['chokes'])>8 else 65
        y+=20
    notes=['Yellow = meeting footprint proposal.','Red = choke neighborhood + NAV interface.',
           'C1a/b: lower and side Underpass accesses.','C3a/b: internal Long A and Catwalk exit.',
           'C2 has a directed height-changing link.','Control labels remain unassigned.','No new training or source-map changes.']
    notes=draft.get('display_notes',notes)
    for i,line in enumerate(notes):pen.text((960,max(790,y+10)+i*30),line,font=font(16),fill='#becbda')
    im.save(path)


def run(source,output):
    if output.exists():raise ValueError('Use a new output directory')
    raw=source.read_bytes();draft=build(json.loads(raw))
    draft.update(source_graph_sha256=hashlib.sha256(raw).hexdigest(),annotator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True);(output/'boundaries.json').write_text(json.dumps(draft,indent=2));draw(draft,output/'overview.png')
    lines=['# Cobblestone user-specified battlefront draft','','The user specified three meeting contexts and four choke groups. Exact masks and doorway matches remain review proposals.','']
    for item in draft['meetings']+draft['chokes']:lines.append(f"- {item['id']}: {item['title']} ({len(item['surface_pieces'])} clipped NAV pieces).")
    lines+=['','Review: Is M2 the intended area below Underpass? Are C1a/b and C3a/b the intended doorways?','']+draft['limits']
    (output/'review.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'meeting_areas':len(draft['meetings']),'choke_groups':len(draft['chokes']),'training_eligible':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
