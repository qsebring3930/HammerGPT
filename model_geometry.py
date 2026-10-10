"""Expand approved decompiled static model instances with explicit coverage audit."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import tempfile

import numpy as np

from analyze_map import SCALAR, transform
from architecture_features import face_triangles
from hammergpt import convert, get, parse, walk, Element


def modeldoc(text):
    text=re.sub(r'<!--.*?-->','',text,flags=re.S)
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|[A-Za-z_][\w]*|[{}\[\]=,]',text)
    cursor=0
    def value():
        nonlocal cursor
        token=tokens[cursor];cursor+=1
        if token=='{':
            result={}
            while tokens[cursor]!='}':
                key=tokens[cursor];cursor+=1
                if tokens[cursor]!='=':raise ValueError('Unsupported ModelDoc syntax')
                cursor+=1;result[key]=value()
                if tokens[cursor]==',':cursor+=1
            cursor+=1;return result
        if token=='[':
            result=[]
            while tokens[cursor]!=']':
                result.append(value())
                if tokens[cursor]==',':cursor+=1
            cursor+=1;return result
        if token.startswith('"'):return json.loads(token)
        if token in ('true','false'):return token=='true'
        if token=='null':return None
        return float(token)
    result=value()
    if cursor!=len(tokens):raise ValueError('Trailing ModelDoc data')
    return result


def doc_nodes(node):
    if isinstance(node,dict):
        if '_class' in node:yield node
        for v in node.values():yield from doc_nodes(v)
    elif isinstance(node,list):
        for v in node:yield from doc_nodes(v)


def descriptor(text,allow_physics=False):
    nodes=list(doc_nodes(modeldoc(text)))
    known={'RootNode','BoneMarkupList','RenderMeshList','RenderMeshFile','ModelModifierList','ModelModifier_Translate'}
    if allow_physics:known|={'PhysicsHullFile','PhysicsMeshFile','PhysicsShapeList'}
    unsupported={n['_class'] for n in nodes}-known
    if unsupported:raise ValueError('Unsupported ModelDoc classes: '+','.join(sorted(unsupported)))
    meshes=[n for n in nodes if n['_class']=='RenderMeshFile']
    if len(meshes)!=1:raise ValueError('Pilot requires exactly one RenderMeshFile')
    translations=[np.asarray(n['translation'],dtype=float) for n in nodes if n['_class']=='ModelModifier_Translate']
    return meshes[0],sum(translations,np.zeros(3)),[n['_class'] for n in nodes]


def entity_frames(lines):
    result={};pending=False;current=None;depth=0;prop_depth=None;prop_pending=False
    for raw in lines:
        line=raw.strip()
        if current is None:
            if re.fullmatch(r'"(?:[^" ]+"\s+")?CMapEntity"',line):pending=True
            elif pending and line=='{':
                current={'properties':{}};depth=1;pending=False
            continue
        if line=='{':
            depth+=1
            if prop_pending:prop_depth=depth;prop_pending=False
        elif line.rstrip(',')=='}':
            if prop_depth==depth:prop_depth=None
            depth-=1
            if depth==0:
                result[current['node_id']]=current;current=None
        elif depth==1 and re.match(r'"entity_properties"',line):prop_pending=True
        elif line.startswith('"'):
            match=SCALAR.fullmatch(line)
            if not match:continue
            key,typ,val=match.groups()
            if depth==1:
                if key=='nodeID':current['node_id']=val
                elif key in ('origin','angles','scales'):current[key]=list(map(float,val.split()))
            elif prop_depth==depth:current['properties'][key]=val
    if current is not None:raise ValueError('Truncated entity stream')
    return result


def dmx_meshes(text,merge_duplicate_names=False):
    _,roots=parse(text);elements=[n for r in roots for n in walk(r)]
    byid={get(n,'id'):n for n in elements if 'id' in n.attrs}
    def resolve(value):return value if isinstance(value,Element) else byid[value]
    for node in elements:
        if node.kind=='DmeTransform':
            if not np.allclose(list(map(float,get(node,'position').split())),0,atol=1e-6) or not np.allclose(list(map(float,get(node,'orientation').split())),[0,0,0,1],atol=1e-6):
                raise ValueError('Nonidentity DMX skeleton transform unsupported')
    meshes={}
    for mesh in elements:
        if mesh.kind!='DmeMesh':continue
        state=resolve(get(mesh,'currentState'));keys=[k for k,(t,v) in state.attrs.items() if k.startswith('position$') and t=='vector3_array']
        if len(keys)!=1:raise ValueError('Ambiguous position stream')
        key=keys[0];positions=np.asarray([list(map(float,p.split())) for p in get(state,key)])
        mapping=list(map(int,get(state,key+'Indices')));triangles=[];materials=[];degenerate=0
        for fs in get(mesh,'faceSets'):
            fs=resolve(fs);material=resolve(get(fs,'material'));name=get(material,'mtlName')
            face=[]
            for index in map(int,get(fs,'faces')):
                if index==-1:
                    if len(face)<3:raise ValueError('Short model face')
                    try:
                        if len(face)==3:
                            tri=np.asarray([face],dtype=np.float32)
                            if np.linalg.norm(np.cross(tri[0,1]-tri[0,0],tri[0,2]-tri[0,0]))<1e-8:raise ValueError('Degenerate face')
                        else:tri,_,_,_=face_triangles(face)
                        triangles.extend(tri);materials.extend([name]*len(tri))
                    except ValueError as error:
                        if str(error)!='Degenerate face':raise
                        degenerate+=1
                    face=[]
                else:
                    if not 0<=index<len(mapping) or not 0<=mapping[index]<len(positions):raise ValueError('Invalid model vertex index')
                    face.append(positions[mapping[index]])
            if face:raise ValueError('Unterminated model face')
        meshname=get(mesh,'name')
        result=(np.asarray(triangles,dtype=np.float32).reshape(-1,3,3),materials,degenerate)
        if meshname in meshes:
            if not merge_duplicate_names:raise ValueError('Duplicate submesh name')
            old=meshes[meshname];result=(np.concatenate([old[0],result[0]]),old[1]+materials,old[2]+degenerate)
        meshes[meshname]=result
    if not meshes:raise ValueError('No DMX meshes')
    return meshes


def transformed(triangles,modifier,frame):
    # Descriptor modifiers operate in model space, before the entity transform.
    origin=np.asarray(transform([0,0,0],frame));matrix=np.column_stack([np.asarray(transform(np.eye(3)[i],frame))-origin for i in range(3)])
    return ((triangles+modifier)@matrix.T+origin).astype(np.float32)


def resolve_source(path,roots):
    path=path.replace('\\','/')
    if path.startswith('/') or ':' in path or '..' in path.split('/'):raise ValueError('Unsafe source path')
    return next((r/path for r in roots if (r/path).is_file()),None)


def build(graph_path,cs2,output,resume=None):
    if output.exists():raise ValueError('Choose a new output directory')
    graph=json.loads(graph_path.read_text())
    if graph['dataset_role']!='training':raise ValueError('Training sources only')
    source=Path(graph['provenance']['vmap_source']);addon=source.parent.parent
    if hashlib.sha256(source.read_bytes()).hexdigest()!=graph['provenance']['vmap_source_sha256']:raise ValueError('VMAP changed')
    output.mkdir(parents=True);exe=cs2/'game/bin/win64/dmxconvert.exe';roots=[addon,cs2/'content/csgo']
    instances=[];jobs=defaultdict(list);sources={};batches=[];ranges=[];offset=0
    prior=None;prior_triangles=None;prior_instances={}
    if resume:
        prior=json.loads((resume/'instances.json').read_text())
        if prior['provenance']['vmap_sha256']!=graph['provenance']['vmap_source_sha256']:raise ValueError('Resume map mismatch')
        prior_instances={r['node_id']:r for r in prior['instances']}
        with np.load(resume/'render-triangles.npz') as cached:prior_triangles=cached['triangles']
    with tempfile.TemporaryDirectory(prefix='hammergpt-model-expansion-') as temporary:
        temporary=Path(temporary);vmap=temporary/'vmap.txt'
        if prior:
            frames={r['node_id']:{**r['frame'],'properties':{'classname':'prop_static','model':r['model'],'solid':r['solid'],'collision_override':r['collision_override']}} for r in prior['instances']}
        else:
            convert(exe,source,vmap,'keyvalues2');print('Reading exact map instance transforms...',flush=True)
            with vmap.open(encoding='utf-8-sig') as stream:frames=entity_frames(stream)
        for node,frame in frames.items():
            props=frame['properties']
            if props.get('classname')!='prop_static':continue
            record={'node_id':node,'model':props.get('model'),'frame':{k:frame.get(k,d) for k,d in [('origin',[0,0,0]),('angles',[0,0,0]),('scales',[1,1,1])]},
                    'solid':props.get('solid'),'collision_override':props.get('collision_override'),
                    'collision_status':'entity_declares_nonsolid' if props.get('solid')=='0' else 'collision_geometry_not_resolved',
                    'status':'pending'}
            instances.append(record)
            try:
                model=resolve_source(record['model'],roots)
                if model is None:raise ValueError('Missing source model')
                raw=model.read_bytes();mesh,modifier,classes=descriptor(raw.decode('utf-8-sig'))
                dmx=resolve_source(mesh['filename'],roots)
                if dmx is None:raise ValueError('Missing source DMX')
                record.update(model_source=str(model),model_sha256=hashlib.sha256(raw).hexdigest(),
                              descriptor_translation=modifier.tolist(),import_filter=mesh.get('import_filter'),
                              source_model_classes=classes)
                jobs[dmx].append((record,mesh,modifier))
            except (ValueError,KeyError,IndexError,TypeError) as error:record.update(status='unsupported_or_missing',error=str(error))
        print(json.dumps({'instances':len(instances),'unique_shared_dmx':len(jobs)}),flush=True)
        for i,(dmx,users) in enumerate(sorted(jobs.items())):
            try:
                if prior and str(dmx) in prior['source_dmx'] and all(prior_instances[r['node_id']]['status']=='expanded_render_geometry' for r,_,_ in users):
                    if hashlib.sha256(dmx.read_bytes()).hexdigest()!=prior['source_dmx'][str(dmx)]['sha256']:raise ValueError('Resume DMX changed')
                    sources[str(dmx)]=prior['source_dmx'][str(dmx)]
                    for record,_,_ in users:
                        old=prior_instances[record['node_id']]
                        if record['model_sha256']!=old['model_sha256']:raise ValueError('Resume descriptor changed')
                        count=old['triangle_count'];placed=prior_triangles[old['triangle_start']:old['triangle_start']+count]
                        record.update(status='expanded_render_geometry',selected_submeshes=old['selected_submeshes'],triangle_start=offset,triangle_count=count,bounds=old['bounds'])
                        batches.append(placed);cached_range=next(r for r in prior['triangle_ranges'] if r['node_id']==record['node_id'])
                        ranges.append({**cached_range,'triangle_start':offset});offset+=count
                    continue
                converted=temporary/'model.txt';convert(exe,dmx,converted,'keyvalues2')
                meshes=dmx_meshes(converted.read_text(encoding='utf-8-sig'))
                sources[str(dmx)]={'sha256':hashlib.sha256(dmx.read_bytes()).hexdigest(),'submeshes':list(meshes),
                                  'degenerate_faces_omitted':sum(m[2] for m in meshes.values())}
                for record,mesh,modifier in users:
                    try:
                        rule=mesh.get('import_filter',{});exceptions=set(rule.get('exception_list',[]))
                        names=[n for n in meshes if n in exceptions] if rule.get('exclude_by_default') else [n for n in meshes if n not in exceptions]
                        if rule.get('exclude_by_default') and not exceptions<=set(meshes):raise ValueError('Unresolved import filter submesh')
                        if not names:raise ValueError('Empty mesh selection')
                        triangles=np.concatenate([meshes[n][0] for n in names]);placed=transformed(triangles,modifier,record['frame'])
                        record.update(status='expanded_render_geometry',selected_submeshes=names,triangle_start=offset,triangle_count=len(placed),
                                      bounds={'min':placed.min(axis=(0,1)).tolist(),'max':placed.max(axis=(0,1)).tolist()})
                        batches.append(placed);ranges.append({'node_id':record['node_id'],'triangle_start':offset,'triangle_count':len(placed),
                                                            'material_counts':dict(Counter(m for n in names for m in meshes[n][1]))});offset+=len(placed)
                    except (ValueError,KeyError,IndexError) as error:record.update(status='unsupported_or_missing',error=str(error))
            except (ValueError,KeyError,RuntimeError,IndexError) as error:
                for record,_,_ in users:record.update(status='unsupported_or_missing',error=str(error))
            if i%25==0:print(json.dumps({'shared_models_processed':i+1,'total':len(jobs),'render_triangles':offset}),flush=True)
        if batches:np.savez_compressed(output/'render-triangles.npz',triangles=np.concatenate(batches))
    summary={'map':graph['map'],'instances':len(instances),'status_counts':dict(Counter(r['status'] for r in instances)),
             'collision_status_counts':dict(Counter(r['collision_status'] for r in instances)),
             'render_triangles':offset,'unique_dmx':len(sources),'model_training_performed':False}
    summary['unique_source_degenerate_faces_omitted']=sum(r.get('degenerate_faces_omitted',0) for r in sources.values())
    data={'schema_version':1,'summary':summary,'instances':instances,'triangle_ranges':ranges,'source_dmx':sources,
          'provenance':{'source_graph':str(graph_path.resolve()),'graph_sha256':hashlib.sha256(graph_path.read_bytes()).hexdigest(),
                        'vmap_source':str(source),'vmap_sha256':graph['provenance']['vmap_source_sha256'],
                        'extractor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
          'limitations':['Static props only; other entity classes and prefab instances are not expanded.',
                         'Import filters and descriptor translations precede map instance scale/rotation/translation.',
                         'Only identity DMX skeleton transforms and the explicitly supported ModelDoc classes are accepted; unsupported sources are recorded.',
                         'These source model descriptors lack authored physics meshes. Solid entity settings are recorded, not treated as collision geometry.',
                         'Render triangles do not establish collision, opacity, bullet behavior, material overrides or animated poses.']}
    if resume:data['provenance']['resume']={'instances_sha256':hashlib.sha256((resume/'instances.json').read_bytes()).hexdigest(),
                                         'triangles_sha256':hashlib.sha256((resume/'render-triangles.npz').read_bytes()).hexdigest()}
    (output/'instances.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--graph',type=Path,required=True)
    parser.add_argument('--cs2',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--resume-from',type=Path)
    args=parser.parse_args();build(args.graph,args.cs2,args.output,args.resume_from)
