"""Retain source Train section geometry without flattening or inferred corridors."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from analyze_map import world_point
from architecture_features import FaceScanner, MeshIndex
from hammergpt import convert
from model_geometry import descriptor, dmx_meshes, resolve_source, transformed

ROI=np.array([[-850,-350,-350],[1750,1900,400]],dtype=float)

def overlaps(points, bounds=ROI):
    points=np.asarray(points)
    return bool(np.all(points.max(axis=0)>=bounds[0]) and np.all(points.min(axis=0)<=bounds[1]))

def select_triangles(triangles, bounds=ROI):
    t=np.asarray(triangles)
    return np.all(t.max(axis=1)>=bounds[0],axis=1)&np.all(t.min(axis=1)<=bounds[1],axis=1)

class SectionScanner(FaceScanner):
    """Decompiled nodeID values repeat. Stream occurrence IDs must not collapse them."""
    def __init__(self,bounds=ROI):
        super().__init__();self.bounds=bounds;self.occurrences=Counter()

    def feed(self,raw):
        frame=self.stack[-1] if self.stack else None
        line=raw.strip()
        if frame and frame.get('_skip_unused_attribute'):
            if line!=']':return
            frame.pop('_skip_unused_attribute',None)
        skip=(frame and line=='[' and frame['kind']=='CDmePolygonMeshDataStream'
              and self.pending and self.pending[0]=='data'
              and not frame.get('is_position') and not frame.get('is_material'))
        if frame and raw.strip().rstrip(',')=='}' and frame['kind'] in ('CMapMesh','CMapEntity'):
            kind=frame['kind'];self.occurrences[kind]+=1
            frame['source_node_id']=frame.get('nodeID')
            frame['nodeID']=f'{kind}:{self.occurrences[kind]}'
        super().feed(raw)
        if skip:frame['_skip_unused_attribute']=True

    def extract_mesh(self,mesh):
        positions=mesh.get('_arrays',{}).get('positions',[])
        if positions and not overlaps([world_point(p,mesh) for p in positions],self.bounds):
            self.stats['meshes_outside_section']+=1;mesh.pop('_arrays',None);return
        super().extract_mesh(mesh)

def nav_section(nav):
    areas={a['id']:a for a in nav['areas'] if a['hull']==0 and a['movable_mesh_id']==0xffffffff}
    selected={k:a for k,a in areas.items() if overlaps(a['corners'])}
    links=[];ports=[]
    for k,a in areas.items():
        for c in a['connections']:
            target=c['target']
            if k in selected and target in selected:links.append({'source':k,**c})
            elif target in areas and ((k in selected)!=(target in selected)):
                ports.append({'source':k,**c,'direction':'outgoing' if k in selected else 'incoming',
                              'source_corners':a['corners'],'target_corners':areas[target]['corners']})
    return {'areas':list(selected.values()),'directed_connections':links,'boundary_connections':ports,
            'source_ladder_count':nav['ladder_count'],
            'ladder_references':[{'area_id':k,'above':a['ladders_above'],'below':a['ladders_below']}
                                 for k,a in selected.items() if a['ladders_above'] or a['ladders_below']]}

def expand_job(job,exe,roots,bounds,shared_meshes=None,shared_digest=None):
    model,instances=job
    try:
        source=resolve_source(model,roots)
        if source is None:raise ValueError('Missing source model')
        raw=source.read_bytes();mesh,modifier,classes=descriptor(raw.decode('utf-8-sig'),allow_physics=True)
        dmx=resolve_source(mesh['filename'],roots)
        if dmx is None:raise ValueError('Missing source DMX')
        if shared_meshes is None:
            with tempfile.TemporaryDirectory(prefix='hammergpt-section-model-') as tmp:
                text=Path(tmp)/'mesh.txt';convert(exe,dmx,text,'keyvalues2')
                meshes=dmx_meshes(text.read_text(encoding='utf-8-sig'),merge_duplicate_names=True)
        else:meshes=shared_meshes
        rule=mesh.get('import_filter',{});exceptions=set(rule.get('exception_list',[]))
        if rule.get('exclude_by_default') and not exceptions<=set(meshes):raise ValueError('Unresolved import filter')
        names=[n for n in meshes if (n in exceptions)==bool(rule.get('exclude_by_default'))]
        if not names:raise ValueError('Empty submesh selection')
        base=np.concatenate([meshes[n][0] for n in names]);pieces=[];records=[]
        for instance in instances:
            triangles=transformed(base,modifier,instance)
            keep=select_triangles(triangles,bounds);triangles=triangles[keep]
            record={'occurrence_id':instance['nodeID'],'source_node_id':instance['source_node_id'],
                    'model':model,'solid':instance['properties'].get('solid'),
                    'collision_override':instance['properties'].get('collision_override'),
                    'triangles_in_section':len(triangles),'source_render_triangles':len(base)}
            if len(triangles):pieces.append(triangles);records.append(record)
        return (np.concatenate(pieces) if pieces else np.empty((0,3,3),dtype=np.float32),records,
                {'model':model,'instances':len(instances),'status':'expanded',
                 'model_sha256':hashlib.sha256(raw).hexdigest(),'dmx_sha256':shared_digest or hashlib.sha256(dmx.read_bytes()).hexdigest(),
                 'physics_descriptor_present':any(c.startswith('Physics') for c in classes),
                 'physics_geometry_expanded':False,'duplicate_submesh_policy':'retain every occurrence selected by name'})
    except (ValueError,RuntimeError,KeyError,IndexError,UnicodeError) as e:
        return np.empty((0,3,3),dtype=np.float32),[],{'model':model,'instances':len(instances),'status':'unresolved','error':str(e)}

def expand_group(dmx,jobs,exe,roots,bounds):
    with tempfile.TemporaryDirectory(prefix='hammergpt-section-model-') as tmp:
        text=Path(tmp)/'mesh.txt';convert(exe,dmx,text,'keyvalues2')
        meshes=dmx_meshes(text.read_text(encoding='utf-8-sig'),merge_duplicate_names=True)
    digest=hashlib.sha256(dmx.read_bytes()).hexdigest()
    return [expand_job(job,exe,roots,bounds,meshes,digest) for job in jobs]

def write_glb(path,native,props,nav):
    """Portable triangle reconstruction; separate NAV layer, no invented volumes."""
    document={'asset':{'version':'2.0','generator':'HammerGPT source section reconstruction'},
              'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'materials':[],
              'buffers':[{'byteLength':0}],'bufferViews':[],'accessors':[]}
    binary=bytearray()
    for name,t,color in [('Native editor faces',native,[.55,.60,.65,1]),
                         ('Source prop render faces',props,[.65,.49,.29,1]),
                         ('Recorded NAV surfaces',nav,[.18,.72,.76,.65])]:
        if not len(t):continue
        p=t.reshape(-1,3).copy();p=np.stack([p[:,0],p[:,2],-p[:,1]],axis=1).astype('<f4')
        offset=len(binary);binary.extend(p.tobytes());view=len(document['bufferViews'])
        document['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':p.nbytes,'target':34962})
        accessor=len(document['accessors']);document['accessors'].append({'bufferView':view,'componentType':5126,
                    'count':len(p),'type':'VEC3','min':p.min(axis=0).tolist(),'max':p.max(axis=0).tolist()})
        material=len(document['materials']);document['materials'].append({'name':name,'doubleSided':True,
            'alphaMode':'BLEND' if color[3]<1 else 'OPAQUE','pbrMetallicRoughness':{'baseColorFactor':color,'metallicFactor':0,'roughnessFactor':1}})
        node=len(document['nodes']);document['nodes'].append({'name':name,'mesh':len(document['meshes'])})
        document['scenes'][0]['nodes'].append(node)
        document['meshes'].append({'primitives':[{'attributes':{'POSITION':accessor},'material':material,'mode':4}]})
    document['buffers'][0]['byteLength']=len(binary)
    encoded=json.dumps(document,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
    binary.extend(b'\0'*((-len(binary))%4))
    path.write_bytes(struct.pack('<III',0x46546c67,2,12+8+len(encoded)+8+len(binary))+
                     struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(binary),0x004e4942)+binary)

def nav_triangles(section):
    return np.asarray([[p[0],p[i],p[i+1]] for a in section['areas'] for p in [a['corners']]
                       for i in range(1,len(p)-1)],dtype=np.float32)

def slice_segments(triangles,height):
    t=np.asarray(triangles)
    t=t[(t[:,:,2].min(axis=1)<=height)&(t[:,:,2].max(axis=1)>=height)]
    result=[]
    for triangle in t:
        points=[]
        for a,b in zip(triangle,np.roll(triangle,-1,axis=0)):
            if (a[2]-height)*(b[2]-height)<=0 and abs(a[2]-b[2])>1e-7:
                p=a+(b-a)*((height-a[2])/(b[2]-a[2]))
                if not any(np.linalg.norm(p-q)<1e-5 for q in points):points.append(p)
        if len(points)==2:result.append(points)
    return result

def preview(path,section,native,props,labels):
    im=Image.new('RGB',(1550,770),'#101923');d=ImageDraw.Draw(im)
    try:font=ImageFont.truetype('arial.ttf',20);small=ImageFont.truetype('arial.ttf',14)
    except OSError:font=small=ImageFont.load_default()
    d.text((30,20),'Train section: source geometry retained, not generated rooms',font=font,fill='white')
    scale=min(650/(ROI[1,0]-ROI[0,0]),780/(ROI[1,1]-ROI[0,1]))
    def xy(p,offset):return (offset+20+(p[0]-ROI[0,0])*scale,690-(p[1]-ROI[0,1])*scale)
    d.text((30,65),'Original NAV polygons colored by height',font=small,fill='#afd7ed')
    d.text((800,65),'NAV + geometry slice at Z=-148 (one eye-height layer)',font=small,fill='#afd7ed')
    for offset in [20,790]:
        for a in sorted(section['areas'],key=lambda a:np.mean(np.asarray(a['corners'])[:,2])):
            z=np.mean(np.asarray(a['corners'])[:,2]);v=np.clip((z+220)/400,0,1)
            color=(int(45+170*v),int(120+65*v),int(170-90*v))
            d.polygon([xy(p,offset) for p in a['corners']],fill=color)
    # Render each panel independently so retained whole triangles outside the ROI
    # cannot draw across the other comparison panel. Clipping is display-only.
    panel=Image.new('RGB',(720,610),'#101923');pd=ImageDraw.Draw(panel)
    for a in sorted(section['areas'],key=lambda a:np.mean(np.asarray(a['corners'])[:,2])):
        z=np.mean(np.asarray(a['corners'])[:,2]);v=np.clip((z+220)/400,0,1)
        pd.polygon([(x-790,y-90) for x,y in [xy(p,790) for p in a['corners']]],fill=(int(45+170*v),int(120+65*v),int(170-90*v)))
    for tris,color in [(native,'#b2bac3'),(props,'#dfa76c')]:
        for segment in slice_segments(tris,-148):
            pd.line([(x-790,y-90) for x,y in [xy(p,790) for p in segment]],fill=color,width=1)
    im.paste(panel,(790,90))
    centers={a['id']:np.mean(a['corners'],axis=0) for a in section['areas']}
    for label in ['TMain','Ivy','LongDog','BombsiteA','Alley']:
        ps=[c for k,c in centers.items() if labels.get(k)==label]
        if ps:
            p=np.mean(ps,axis=0)
            for offset in [20,790]:d.text(xy(p,offset),label,font=small,fill='white',stroke_width=2,stroke_fill='#101923')
    d.text((30,720),'Exact XYZ polygons and directed links retained; no flattening, corridor widening, or inferred boundary walls.',font=small,fill='white')
    d.text((30,743),'Mesh edges are editor/render evidence. Collision, opacity, ladder traversal and NAV freshness are not certified.',font=small,fill='#a7b6c4')
    im.save(path)

def run(graph_path,cs2,output,resume=False):
    if output.exists() and not resume:raise ValueError('Choose a new output directory')
    graph=json.loads(graph_path.read_text());source=Path(graph['provenance']['vmap_source'])
    if graph['map']!='Train' or graph['dataset_role']!='training':raise ValueError('Approved Train training source required')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=graph['provenance']['vmap_source_sha256']:raise ValueError('Source VMAP changed')
    navpath=Path(graph['provenance']['nav_export']);raw=navpath.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=graph['provenance']['nav_export_sha256']:raise ValueError('Source NAV export changed')
    section=nav_section(json.loads(raw));output.mkdir(parents=True,exist_ok=resume);exe=cs2/'game/bin/win64/dmxconvert.exe'
    scanner=SectionScanner()
    if resume:
        cache=json.loads((output/'cache-manifest.json').read_text())
        if cache['provenance']!=graph['provenance']:raise ValueError('Cached source mismatch')
        for name,key in [('native.npz','native_sha256'),('source-entities.json','entities_sha256')]:
            if hashlib.sha256((output/name).read_bytes()).hexdigest()!=cache[key]:raise ValueError('Cache changed')
        native=np.load(output/'native.npz')['triangles'];entities=json.loads((output/'source-entities.json').read_text())
        scanner.stats.update(cache['native_stats'])
    else:
        with tempfile.TemporaryDirectory(prefix='hammergpt-train-section-') as tmp:
            text=Path(tmp)/'source.txt';print('Converting approved Train VMAP...',flush=True);convert(exe,source,text,'keyvalues2')
            print('Scanning source faces with occurrence IDs...',flush=True)
            with text.open(encoding='utf-8-sig') as f:
                for line in f:scanner.feed(line)
            native,faces,spatial=scanner.geometry()
        native=native[select_triangles(native)]
        np.savez_compressed(output/'native.npz',triangles=native)
        entities=[{k:v for k,v in e.items() if k in ('nodeID','source_node_id','origin','angles','scales','properties')} for e in scanner.entities]
        (output/'source-entities.json').write_text(json.dumps(entities))
        cache={'provenance':graph['provenance'],'native_stats':dict(scanner.stats),
               'native_sha256':hashlib.sha256((output/'native.npz').read_bytes()).hexdigest(),
               'entities_sha256':hashlib.sha256((output/'source-entities.json').read_bytes()).hexdigest()}
        (output/'cache-manifest.json').write_text(json.dumps(cache,indent=2))
    jobs={}
    for e in entities:
        if e['properties'].get('classname')=='prop_static':jobs.setdefault(e['properties']['model'],[]).append(e)
    batches=[];instances=[];audit=[];roots=[source.parent.parent,cs2/'content/csgo']
    groups={}
    for model,users in sorted(jobs.items()):
        try:
            modelpath=resolve_source(model,roots)
            if modelpath is None:raise ValueError('Missing model source')
            mesh,_,_=descriptor(modelpath.read_text(encoding='utf-8-sig'),allow_physics=True)
            dmx=resolve_source(mesh['filename'],roots)
            if dmx is None:raise ValueError('Missing DMX source')
            groups.setdefault(dmx,[]).append((model,users))
        except (ValueError,KeyError,UnicodeError) as e:
            audit.append({'model':model,'instances':len(users),'status':'unresolved','error':str(e)})
    print(f'Expanding {len(groups)} shared geometry sources for {len(jobs)} model descriptors...',flush=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(expand_group,dmx,users,exe,roots,ROI):users for dmx,users in sorted(groups.items())}
        for i,future in enumerate(as_completed(tasks)):
            try:results=future.result()
            except (ValueError,RuntimeError,KeyError,IndexError) as e:
                results=[(np.empty((0,3,3)),[],{'model':m,'instances':len(users),'status':'unresolved','error':str(e)}) for m,users in tasks[future]]
            for t,records,record in results:
                audit.append(record);instances.extend(records)
                if len(t):batches.append(t)
            if i%25==0:print(json.dumps({'shared_sources_processed':i+1,'total':len(groups),'section_instances':len(instances)}),flush=True)
    props=np.concatenate(batches) if batches else np.empty((0,3,3),dtype=np.float32)
    np.savez_compressed(output/'props.npz',triangles=props)
    (output/'model-audit.json').write_text(json.dumps({'sources':audit,'section_instances':instances},indent=2))
    section.update(schema_version=1,kind='source_geometry_section',map='Train',roi_xyz=ROI.tolist(),
        selection='Whole source polygons/triangles whose bounds intersect outer yard, T Main, Ivy and Popdog ROI; no clipping or synthetic joins.',
        model_training_performed=False,provenance=graph['provenance'])
    (output/'section.json').write_text(json.dumps(section,indent=2))
    write_glb(output/'reconstruction.glb',native,props,nav_triangles(section))
    labels={a['id']:next(n['label'] for n in graph['nodes'] if n['id']==a['region_id']) for a in graph['nav_polygons']}
    preview(output/'comparison.png',section,native,props,labels)
    stats={'nav_polygons':len(section['areas']),'directed_connections':len(section['directed_connections']),
           'boundary_connections':len(section['boundary_connections']),'nav_height_span_units':float(np.ptp(nav_triangles(section)[:,:,2])),
           'native_triangles':len(native),'prop_render_triangles':len(props),'section_prop_instances':len(instances),
           'model_source_status':dict(Counter(x['status'] for x in audit)),
           'native_extraction_audit':dict(scanner.stats),'ladder_reference_areas':len(section['ladder_references']),
           'model_training_performed':False,'synthetic_corridors':0,'flattened_surfaces':0,
           'limits':['Render/editor triangles do not establish collision, opacity, bullet behavior or tactical cover.',
                     'Static props expanded; dynamic models, prefabs and unsupported model sources remain outside coverage.',
                     'Original ladder references retained; ladder endpoint geometry and traversal are not yet decoded.',
                     'ROI selects whole overlapping geometry; boundary connections remain explicit, not closed by authored walls.']}
    (output/'report.json').write_text(json.dumps(stats,indent=2));print(json.dumps(stats),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--graph',type=Path,required=True);p.add_argument('--cs2',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--resume',action='store_true')
    a=p.parse_args();run(a.graph,a.cs2,a.output,a.resume)
