"""Draft Dust2 meeting footprints and NAV-backed choke transitions for review.

World-space ROIs are authored proposals informed by the user diagram and NAV.
They are not pixel registrations, architectural doorway bounds or timed fronts.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


MEETINGS=[
    ('M1','A-doors / Long encounter',['LongDoors','LongA'],[520,760,-32,1792,1248,64],
     'User correction: exclude Pit; include A Long and the outside of upper A-doors toward Long.'),
    ('M2','Middle encounter',['Middle','TopofMid','MidDoors'],[-560,320,-160,-240,1632,64],
     'Middle meeting context extends along the lane; includes part of the TopofMid place footprint, not the whole Top Mid zone.'),
    ('M3','Upper-tunnel / B-mouth encounter',['UpperTunnel','BombsiteB'],[-2144,1664,-16,-1888,2016,96],
     'User correction: include the entire small hallway below C2 and an adjoining portion of Upper tunnels.'),
]
# Extend only the tunnel-side surface selection, preserving the B-side extent.
MEETING_EXTENSIONS={'M3': [(['UpperTunnel'],[-2184,1280,-16,-1750,1664,96])]}
CHOKES=[
    ('C1','Upper A-doors / Long exit','LongDoors','LongDoors','M1'),
    ('C2','B tunnel exit','UpperTunnel','BombsiteB','M3'),
    ('C3','Lower tunnels -> Mid','LowerTunnel','Middle','M2'),
    ('C4','B doors','BDoors','BombsiteB',None),
    ('C5','Short A transition','ShortStairs','ExtendedA',None),
]


def clip_polygon(polygon,bounds):
    """Clip a 3D NAV surface polygon to XYZ half-planes, retaining elevation."""
    points=[list(p) for p in polygon]
    for axis,limit,greater in [(0,bounds[0],True),(1,bounds[1],True),(2,bounds[2],True),
                                (0,bounds[3],False),(1,bounds[4],False),(2,bounds[5],False)]:
        result=[]
        for a,b in zip(points,points[1:]+points[:1]):
            inside_a=a[axis]>=limit if greater else a[axis]<=limit
            inside_b=b[axis]>=limit if greater else b[axis]<=limit
            if inside_a:result.append(a)
            if inside_a!=inside_b:
                fraction=(limit-a[axis])/(b[axis]-a[axis])
                result.append([a[i]+fraction*(b[i]-a[i]) for i in range(3)])
        points=result
        if len(points)<3:return []
    # Remove repeated corners introduced at exact clip boundaries.
    clean=[]
    for p in points:
        if not clean or math.dist(p,clean[-1])>1e-6:clean.append(p)
    if len(clean)>1 and math.dist(clean[0],clean[-1])<1e-6:clean.pop()
    area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(clean,clean[1:]+clean[:1])))/2
    return clean if len(clean)>=3 and area>1e-4 else []


def select_surfaces(graph,labels,bounds):
    nodes={n['id']:n for n in graph['nodes']};pieces=[]
    for polygon in graph['nav_polygons']:
        if nodes[polygon['region_id']]['label'] not in labels:continue
        clipped=clip_polygon(polygon['corners'],bounds)
        if clipped:pieces.append({'nav_area_id':polygon['id'],'region_id':polygon['region_id'],'corners':clipped})
    return pieces


def build(graph):
    if graph['map']!='Dust2' or graph['dataset_role']!='training':raise ValueError('Requires approved Dust2 training reference')
    nodes={n['id']:n for n in graph['nodes']};annotations=[]
    for key,title,labels,bounds,reason in MEETINGS:
        pieces=select_surfaces(graph,labels,bounds)
        extensions=MEETING_EXTENSIONS.get(key,[])
        for extra_labels,extra_bounds in extensions:
            pieces.extend(select_surfaces(graph,extra_labels,extra_bounds))
        if not pieces:raise ValueError('Empty meeting footprint '+key)
        annotations.append({'id':key,'kind':'meeting_area','title':title,'review_status':'pending_boundary_review',
            'selection_basis':'Authored world-space ROI clipped to source NAV surfaces and place context.',
            'context_place_labels':labels,'proposed_roi_xyz':bounds,'surface_pieces':pieces,'interpretation':reason,
            'additional_rois':[{'context_place_labels':l,'proposed_roi_xyz':b} for l,b in extensions],
            'uncertainty':'Extent is a review proposal, not a measured arrival front or image registration.'})
    for key,title,source,target,meeting in CHOKES:
        witnesses=[];segments=[];seen=set()
        if key=='C1':
            # The actual upper doorway is INTERNAL to the coarse LongDoors
            # region. A cross-place interface would mark the wrong location.
            nav_bytes=Path(graph['provenance']['nav_export']).read_bytes()
            if hashlib.sha256(nav_bytes).hexdigest()!=graph['provenance']['nav_export_sha256']:raise ValueError('NAV export changed')
            areas={a['id']:a for a in json.loads(nav_bytes)['areas']}
            a,b=areas[354],areas[366]
            connection=next((c for c in a['connections'] if c['target']==b['id']),None)
            if connection is None:raise ValueError('Upper A-door NAV witness missing')
            index=connection['source_edge'];points=[a['corners'][index],a['corners'][(index+1)%len(a['corners'])]]
            if not all(600<p[0]<650 and 720<p[1]<760 for p in points):raise ValueError('Upper door geometry changed')
            segment_length=math.dist(points[0][:2],points[1][:2])
            owner={p['id']:p['region_id'] for p in graph['nav_polygons']}
            segments.append(points)
            witnesses.append({'source_region':owner[a['id']],'target_region':owner[b['id']],
                'evidence_scope':'Recorded directed NAV link inside one coarse LongDoors region; not a cross-place boundary.',
                'reverse_edge_exists':any(c['target']==a['id'] for c in b['connections']),
                'recorded_nav_witness':{'source_nav_area':a['id'],'target_nav_area':b['id'],
                    'source_edge':index,'target_edge':connection['target_edge'],
                    'source_edge_endpoints':points,'source_edge_length_xy':segment_length}})
        for edge in ([] if key=='C1' else graph['edges']):
            if (nodes[edge['source']]['label'],nodes[edge['target']]['label'])!=(source,target):continue
            for witness in edge['witnesses']:
                points=witness['source_edge_endpoints']
                # B window/prop-top surfaces must not silently widen the ground-door label.
                if key=='C4' and max(p[2] for p in points)>48:continue
                signature=tuple(sorted(tuple(round(v,4) for v in p) for p in points))
                if signature in seen:continue
                seen.add(signature);segments.append(points)
                witnesses.append({'source_region':edge['source'],'target_region':edge['target'],
                                  'reverse_edge_exists':edge['reverse_edge_exists'],'recorded_nav_witness':witness})
        if not segments:raise ValueError('Missing interface evidence '+key)
        vertices=[p for segment in segments for p in segment]
        bounds=[min(p[0] for p in vertices)-64,min(p[1] for p in vertices)-64,min(p[2] for p in vertices)-32,
                max(p[0] for p in vertices)+64,max(p[1] for p in vertices)+64,max(p[2] for p in vertices)+32]
        pieces=select_surfaces(graph,[source,target],bounds)
        if not pieces:raise ValueError('Empty choke neighborhood '+key)
        annotations.append({'id':key,'kind':'choke_transition','title':title,'review_status':'pending_boundary_review',
            'source_place_label':source,'target_place_label':target,'related_meeting_area':meeting,
            'interface_segments':segments,'directed_witnesses':witnesses,'proposed_roi_xyz':bounds,
            'surface_pieces':pieces,'selection_basis':'Recorded cross-place NAV interfaces plus an authored local neighborhood.',
            'uncertainty':'NAV interfaces locate a transition; segment lengths and neighborhood bounds are not physical doorway dimensions.'})
    return {'schema_version':1,'map':'Dust2','dataset_role':'training','task':'meeting_area_and_choke_boundary_draft',
            'status':'pending_boundary_review','training_eligible':False,'annotations':annotations,
            'user_corrections_applied':['M2 extends into the double-door gap using the locally inspected MidDoors footprint up to y=1632; it stops before the north-side Outside B space.',
                'M1 excludes Pit and Side, covering Long and the upper-door exit courtyard.',
                'C1 moved from the lower door approach to the upper A-door internal NAV transition (areas 354 -> 366).',
                'M3 includes the full B-exit hallway and some Upper tunnels using a separate tunnel-only extension ROI.'],
            'limits':['Meeting areas and choke neighborhoods can overlap intentionally; they require separate target channels.',
                      'World-space bounds are authored proposals; the supplied screenshot was not formally registered to this repaired map.',
                      'NAV surface extents are not architectural geometry, doorway clearance, sightlines or timed battlefronts.',
                      'XZ/YZ differences remain in surface points; projected XY overlaps do not mean same-floor connectivity.',
                      'C4 annotates ground B doors only. No new training or source-map editing occurred.']}


def draw(graph,draft,output):
    vertices=[p for poly in graph['nav_polygons'] for p in poly['corners']]
    x0,x1=min(p[0] for p in vertices),max(p[0] for p in vertices)
    y0,y1=min(p[1] for p in vertices),max(p[1] for p in vertices)
    scale=min(970/(x1-x0),990/(y1-y0))
    im=Image.new('RGB',(1550,1190),'#111925');pen=ImageDraw.Draw(im)
    font=lambda size:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    def xy(p):return 35+(p[0]-x0)*scale,120+(y1-p[1])*scale
    pen.text((30,20),'Dust2: meeting areas and choke transitions',font=font(30),fill='#edf2fa')
    pen.text((30,66),'Draft extents on source NAV. Yellow = encounter space; red = local access transition.',font=font(18),fill='#cbd4df')
    for poly in graph['nav_polygons']:pen.polygon([xy(p) for p in poly['corners']],fill='#344354')
    for item in draft['annotations']:
        color='#e7ce55' if item['kind']=='meeting_area' else '#ee7974'
        for piece in item['surface_pieces']:pen.polygon([xy(p) for p in piece['corners']],fill=color)
        if item['kind']=='choke_transition':
            for segment in item['interface_segments']:pen.line([xy(p) for p in segment],fill='#ff2929',width=6)
        bounds=item['proposed_roi_xyz'];x,y=xy([(bounds[0]+bounds[3])/2,(bounds[1]+bounds[4])/2,0])
        # Small label leaders avoid covering the tight B-exit meeting/choke overlap.
        dx,dy={'M1':(50,0),'M2':(55,-25),'M3':(-45,-35),'C2':(-45,20)}.get(item['id'],(20,-20))
        pen.line([(x,y),(x+dx,y+dy)],fill=color,width=2)
        x,y=x+dx,y+dy
        pen.rounded_rectangle((x-18,y-13,x+18,y+13),radius=5,fill='#111925',outline=color,width=2)
        pen.text((x-12,y-10),item['id'],font=font(16),fill=color)
    pen.text((1040,135),'Meeting-area proposals',font=font(23),fill='#e7ce55')
    y=185
    for item in draft['annotations']:
        if item['kind']!='meeting_area':continue
        pen.text((1040,y),f"{item['id']}: {item['title']}",font=font(19),fill='#edf2fa')
        pen.text((1040,y+28),f"{len(item['surface_pieces'])} clipped NAV surfaces",font=font(16),fill='#bdcadb');y+=85
    pen.text((1040,490),'Choke-transition proposals',font=font(23),fill='#ee7974');y=540
    for item in draft['annotations']:
        if item['kind']!='choke_transition':continue
        pen.text((1040,y),f"{item['id']}: {item['title']}",font=font(19),fill='#edf2fa')
        pen.text((1040,y+27),f"{len(item['directed_witnesses'])} recorded interface segments",font=font(16),fill='#bdcadb');y+=73
    for i,text in enumerate(['Red line = NAV interface evidence.', 'Red patch = proposed local neighborhood.',
        'Yellow boundary is a review draft.', 'Not a timing, sightline or clearance test.']):
        pen.text((1040,965+i*30),text,font=font(16),fill='#bdcadb')
    pen.text((30,1145),'Boundary review pending. Role review remains recorded separately. No new training or map changes.',font=font(19),fill='#f2bf77')
    im.save(output)


def run(source,reference_image,output):
    if output.exists():raise ValueError('Use a new output directory')
    raw=source.read_bytes();graph=json.loads(raw);draft=build(graph)
    draft.update(source_graph_sha256=hashlib.sha256(raw).hexdigest(),source_provenance=graph['provenance'],
                 reference_image=str(reference_image.resolve()),reference_image_sha256=hashlib.sha256(reference_image.read_bytes()).hexdigest(),
                 annotator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True);(output/'boundaries.json').write_text(json.dumps(draft,indent=2));draw(graph,draft,output/'overview.png')
    lines=['# Dust2 spatial boundary draft','',
        'Three meeting footprints and five choke neighborhoods are proposed separately. Broad role context was reviewed earlier; these new extents await review.', '',
        'The supplied screenshot identifies the locations qualitatively. It was not registered to world coordinates, and may depict a different Dust2 version. Yellow footprints use authored XYZ bounds clipped to source NAV. Red center lines retain recorded directed NAV interface witnesses; surrounding red neighborhoods are authored.', '',
        '| ID | Type | Location | Review concern |','|---|---|---|---|']
    for item in draft['annotations']:lines.append(f"| {item['id']} | {item['kind']} | {item['title']} | {item['uncertainty']} |")
    lines+=['','## Review questions','',
        'Are M1/M2/M3 too broad or too small? M2 includes part of the TopofMid NAV place label within the broader Middle encounter context.',
        'Are C1-C5 at the intended transitions? The red patches show neighborhoods, not certified architectural doorway bounds.',
        'C2 overlaps M3 intentionally: the same location can have both a choke transition and surrounding encounter space.', '',
        'Training eligibility remains false. Timings, exposure, safety, clearance and tactical quality have not been inferred from these masks.']
    (output/'review.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'status':draft['status'],'training_eligible':False,'annotations':[{'id':a['id'],'pieces':len(a['surface_pieces']),
        'interfaces':len(a.get('directed_witnesses',[]))} for a in draft['annotations']]},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--reference-image',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.reference_image,a.output)
