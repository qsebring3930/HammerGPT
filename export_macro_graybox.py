"""Export a trained macro proposal as a connected, editable CS2 graybox."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile
import uuid

from PIL import Image,ImageDraw,ImageFont

from connected_geometry import floor_cells,validate_floor,elevation
from surface_geometry import create_surface_blockout,validate_topology
from hammergpt import Element,convert,fresh_copy,get,make_box,parse,positions,serialize,set_value,vector,walk


def manifold_cells(cells):
    cells=set(cells);original=set(cells)
    while True:
        additions=set()
        for x,y in sorted(cells):
            for dy in (-1,1):
                if (x+1,y+dy) in cells and (x+1,y) not in cells and (x,y+dy) not in cells:additions.add((x+1,y))
        if not additions:return cells,sorted(cells-original)
        cells|=additions


def draw_preview(plan,cells,cover,output):
    regions=plan['design_choices']['regions'];xs=[x*64 for x,y in cells];ys=[y*64 for x,y in cells]
    x0,x1=min(xs)-128,max(xs)+192;y0,y1=min(ys)-128,max(ys)+192
    scale=min(1050/(x1-x0),920/(y1-y0));im=Image.new('RGB',(1150,1060),'#111925');draw=ImageDraw.Draw(im)
    def xy(x,y):return 45+(x-x0)*scale,85+(y1-y)*scale
    for x,y in cells:
        a,b=xy(x*64,(y+1)*64),xy((x+1)*64,y*64);draw.rectangle((*a,*b),fill='#324d62')
        corners=[(x*64,y*64),((x+1)*64,y*64),((x+1)*64,(y+1)*64),(x*64,(y+1)*64)]
        for other,i,j in [((x,y-1),0,1),((x+1,y),1,2),((x,y+1),2,3),((x-1,y),3,0)]:
            if other not in cells:draw.line([xy(*corners[i]),xy(*corners[j])],fill='#b6cfde',width=2)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
    degrees=Counter()
    for edge in plan['design_choices']['connections']:
        degrees.update((edge['source'],edge['target']))
    for r in regions:
        x,y=xy(*r['center'][:2]);color='#f4be69' if r['id'].startswith('Site') else ('#62e1bc' if degrees[r['id']]>=3 else '#e7edf4')
        draw.ellipse((x-5,y-5,x+5,y+5),fill=color);draw.text((x+8,y-10),r['id'],fill=color,font=font)
    for c in cover:
        x,y,z=c['center'];w,d,h=c['size'];a,b=xy(x-w/2,y+d/2),xy(x+w/2,y-d/2)
        draw.rectangle((*a,*b),fill='#a88668')
    draw.text((30,20),plan.get('preview_title','HammerGPT: first learned whole-layout graybox'),fill='#edf2fa',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',27))
    draw.text((30,55),plan.get('preview_subtitle','Learned area placement and graph; authored flat geometry, corridors, entities and cover.'),fill='#cad6e5',font=font)
    draw.text((30,1025),plan.get('preview_footer','Experimental layout. Compile, NAV, collision, timing and gameplay checks are still pending.'),fill='#cad6e5',font=font)
    im.save(output)


def export(proposal,cs2,output,artifacts):
    if output.exists() or artifacts.exists():raise ValueError('Choose new output and artifact paths')
    plan=json.loads(proposal.read_text());cells,added=manifold_cells(floor_cells(plan));height=elevation(plan,cells);validate_floor(cells,height)
    plan['design_choices']['floor_cell_override']=sorted(map(list,cells))
    exe=cs2/'game/bin/win64/dmxconvert.exe';reference=cs2/'content/csgo_addons/aitesting/maps/aitesting.vmap'
    cover=[];entities=[]
    with tempfile.TemporaryDirectory(prefix='hammergpt-macro-') as temporary:
        temporary=Path(temporary);convert(exe,reference,temporary/'reference.txt','keyvalues2')
        header,roots=parse((temporary/'reference.txt').read_text(encoding='utf-8-sig'))
        original=[n for r in roots for n in walk(r)];cube=next(n for n in original if n.kind=='CMapMesh')
        entity_template=next(n for n in original if n.kind=='CMapEntity')
        result,meshes,validation=create_surface_blockout(roots,plan)
        root=next(n for n in result if n.kind=='CMapRootElement');world=get(root,'world');children=get(world,'children')
        counter=max(int(get(n,'nodeID')) for r in result for n in walk(r) if 'nodeID' in n.attrs)
        def next_id():
            nonlocal counter
            counter+=1;return counter
        def entity(classname,name,origin,properties=None,owned=None):
            node=fresh_copy(entity_template,next_id());set_value(node,'origin',vector(origin));set_value(node,'angles','0 0 0')
            attrs={'id':('elementid',str(uuid.uuid4())),'classname':('string',classname),'targetname':('string',name)}
            for k,v in (properties or {}).items():attrs[k]=('string',str(v))
            node.attrs['entity_properties']=('EditGameClassProps',Element('EditGameClassProps',attrs));set_value(node,'children',owned or [])
            children.append(node);entities.append({'classname':classname,'name':name,'node_id':get(node,'nodeID'),'origin':origin})
        by_name={r['id']:r for r in plan['design_choices']['regions']}
        for role,classname in [('TSpawn','info_player_terrorist'),('CTSpawn','info_player_counterterrorist')]:
            x,y,z=by_name[role]['center']
            for i,(dx,dy) in enumerate([(-128,-64),(0,-64),(128,-64),(-64,64),(64,64)]):
                if (int((x+dx)//64),int((y+dy)//64)) not in cells:raise ValueError('Spawn outside floor')
                entity(classname,f'hammergpt_{role}_{i}',[x+dx,y+dy,z+8],{'enabled':'1'})
        for name in ('SiteA','SiteB'):
            x,y,z=by_name[name]['center'];trigger=make_box(cube,next_id(),[x,y,z+64],[256,256,128])
            set_value(get(trigger,'meshData'),'materials',['materials/tools/toolstrigger.vmat'])
            entity('func_bomb_target','hammergpt_'+name,[0,0,0],{'bomb_site_designation':'0'},[trigger])
            for dx,dy in ((192,192),(-192,-192)):
                center=[x+dx,y+dy,z+48];size=[96,128,96]
                for px in (center[0]-48,center[0]+47):
                    for py in (center[1]-64,center[1]+63):
                        if (int(px//64),int(py//64)) not in cells:raise ValueError('Cover outside floor')
                children.append(make_box(cube,next_id(),center,size));cover.append({'center':center,'size':size})
        set_value(world,'children',children);camera=get(root,'defaultcamera')
        set_value(camera,'position','0 -5000 6500');set_value(camera,'lookat','0 0 0')
        (temporary/'graybox.txt').write_text(serialize(header,result),encoding='utf-8')
        convert(exe,temporary/'graybox.txt',temporary/'graybox.vmap','binary')
        convert(exe,temporary/'graybox.vmap',temporary/'check.txt','keyvalues2')
        _,checked=parse((temporary/'check.txt').read_text(encoding='utf-8-sig'))
        before={get(n,'nodeID'):n for r in result for n in walk(r) if n.kind=='CMapMesh'}
        after={get(n,'nodeID'):n for r in checked for n in walk(r) if n.kind=='CMapMesh'}
        if set(before)!=set(after):raise ValueError('Mesh inventory changed in conversion')
        for key,a in before.items():
            b=after[key];validate_topology(b)
            if get(positions(a),'data')!=get(positions(b),'data'):raise ValueError('Vertex data changed in conversion')
            for attr in ('edgeVertexIndices','edgeNextIndices','edgeOppositeIndices','edgeFaceIndices','faceEdgeIndices'):
                if get(get(a,'meshData'),attr)!=get(get(b,'meshData'),attr):raise ValueError('Topology changed in conversion')
            for attr in ('origin','angles','scales'):
                if list(map(float,get(a,attr).split()))!=list(map(float,get(b,attr).split())):raise ValueError('Transform changed in conversion')
        classes=Counter(get(get(n,'entity_properties'),'classname') for r in checked for n in walk(r) if n.kind=='CMapEntity')
        if classes['info_player_terrorist']!=5 or classes['info_player_counterterrorist']!=5 or classes['func_bomb_target']!=2:raise ValueError('Entity count mismatch')
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('xb') as stream:stream.write((temporary/'graybox.vmap').read_bytes())
    artifacts.mkdir(parents=True);(artifacts/'exported-proposal.json').write_text(json.dumps(plan,indent=2))
    report={'output':str(output),'proposal':str(proposal.resolve()),'floor_validation':validation,
            'corner_contact_repair_cells':[list(c) for c in added],'entities':entities,'cover':cover,
            'converted_entity_counts':dict(classes),'binary_roundtrip_passed':True,'compile_or_playtest_performed':False,
            'limits':[f"Prototype with {len(by_name)} semantic placements; layout provenance: {'learned proposal with authored adaptations' if plan.get('learned_generation',plan.get('model_training_performed',False)) else 'authored backbone and footprints'}. See proposal for details.",
                      'Floor geometry, lights, spawns, objective volumes and cover use authored exporter rules; see proposal for layout provenance.',
                      'Explicit floor graph audit, when present, checks junction identity before cover. No ceiling or sky setup was added.',
                      'Source-map conversion and topology passed; compilation, collision, NAV, bombsite behavior and timing remain unverified.']}
    (artifacts/'export.json').write_text(json.dumps(report,indent=2));draw_preview(plan,cells,cover,artifacts/'preview.png')
    print(json.dumps({'output':str(output),'floor_cells':len(cells),'corner_repairs':len(added),'meshes':len(after),'entities':dict(classes),'roundtrip':'passed'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--proposal',type=Path,required=True);parser.add_argument('--cs2',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--artifacts',type=Path,required=True)
    args=parser.parse_args();export(args.proposal,args.cs2,args.output,args.artifacts)
