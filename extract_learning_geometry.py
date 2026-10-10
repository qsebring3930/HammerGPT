"""Extract approved-map editor/render surfaces for geometry reconstruction training."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import numpy as np
from hammergpt import convert
from model_geometry import descriptor, resolve_source
from reconstruct_train_section import SectionScanner, expand_group, select_triangles

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def extract(name,root,cs2):
    gp=Path(f'output/coarse-layout-v1/{name.lower()}.json');g=json.loads(gp.read_text())
    if g['map']!=name or g['dataset_role']!='training':raise ValueError('Unapproved reference')
    source=Path(g['provenance']['vmap_source'])
    if digest(source)!=g['provenance']['vmap_source_sha256']:raise ValueError('Source changed')
    out=root/name.lower();out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        m=json.loads((out/'manifest.json').read_text())
        if m['source_sha256']!=digest(source):raise ValueError('Cache source mismatch')
        for key in ['native','props']:
            if digest(out/f'{key}.npz')!=m[f'{key}_sha256']:raise ValueError('Cache geometry changed')
        print(name+' completed cache verified',flush=True);return
    points=np.array([p for a in g['nav_polygons'] for p in a['corners']]);bounds=np.array([points.min(axis=0)-[128,128,32],points.max(axis=0)+[128,128,160]])
    scanner=SectionScanner(bounds)
    if (out/'native.npz').exists() and (out/'entities.json').exists():
        entities=json.loads((out/'entities.json').read_text());native=np.load(out/'native.npz')['triangles']
    else:
        with tempfile.TemporaryDirectory(prefix='hammergpt-learning-') as tmp:
            text=Path(tmp)/'source.txt';print(name+' converting source',flush=True)
            convert(cs2/'game/bin/win64/dmxconvert.exe',source,text,'keyvalues2')
            print(name+' scanning original faces',flush=True)
            with text.open(encoding='utf-8-sig') as stream:
                for i,line in enumerate(stream):
                    scanner.feed(line)
                    if i and i%1500000==0:print(f'{name}: {i} source lines scanned',flush=True)
            native,_,_=scanner.geometry()
        native=native[select_triangles(native,bounds)];np.savez_compressed(out/'native.npz',triangles=native)
        entities=[{k:v for k,v in e.items() if k in ('nodeID','source_node_id','origin','angles','scales','properties')} for e in scanner.entities]
        (out/'entities.json').write_text(json.dumps(entities))
    roots=[source.parent.parent,cs2/'content/csgo'];jobs={};audit=[]
    by_model={}
    for e in entities:
        if e['properties'].get('classname')=='prop_static':by_model.setdefault(e['properties']['model'],[]).append(e)
    for model,users in sorted(by_model.items()):
        try:
            mp=resolve_source(model,roots)
            if mp is None:raise ValueError('Missing source model')
            mesh,_,_=descriptor(mp.read_text(encoding='utf-8-sig'),allow_physics=True)
            dmx=resolve_source(mesh['filename'],roots)
            if dmx is None:raise ValueError('Missing source DMX')
            jobs.setdefault(dmx,[]).append((model,users))
        except (ValueError,KeyError,UnicodeError) as e:audit.append({'model':model,'instances':len(users),'status':'unresolved','error':str(e)})
    batches=[];instances=[];print(f'{name}: expanding {len(jobs)} shared geometry files',flush=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(expand_group,dmx,users,cs2/'game/bin/win64/dmxconvert.exe',roots,bounds):users for dmx,users in jobs.items()}
        for i,f in enumerate(as_completed(tasks)):
            try:results=f.result()
            except (ValueError,RuntimeError,KeyError,IndexError) as e:
                results=[(np.empty((0,3,3)),[],{'model':model,'instances':len(users),'status':'unresolved','error':str(e)}) for model,users in tasks[f]]
            for t,records,record in results:
                if len(t):batches.append(t)
                instances.extend(records);audit.append(record)
            if i%50==0:print(f'{name}: {i+1}/{len(tasks)} shared models expanded',flush=True)
    props=np.concatenate(batches) if batches else np.empty((0,3,3),dtype=np.float32)
    np.savez_compressed(out/'props.npz',triangles=props)
    (out/'model-audit.json').write_text(json.dumps({'sources':audit,'instances':instances},indent=2))
    m={'map':name,'source':str(source),'source_sha256':digest(source),'graph_sha256':digest(gp),
       'bounds':bounds.tolist(),'native_triangles':len(native),'prop_triangles':len(props),
       'native_sha256':digest(out/'native.npz'),'props_sha256':digest(out/'props.npz'),
       'native_stats':dict(scanner.stats),'model_status':dict(Counter(x['status'] for x in audit)),
       'limits':['Editor/render surfaces only; not collision, opacity, tactical cover or ladder traversal.',
                 'Unsupported and missing models remain explicit in model-audit.json.'],
       'extractor_sha256':digest(Path(__file__))}
    (out/'manifest.json').write_text(json.dumps(m,indent=2));print(json.dumps(m),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--cs2',type=Path,required=True);p.add_argument('--maps',nargs='+',default=['Anubis','Cache','Cobblestone']);a=p.parse_args()
    if not set(a.maps)<= {'Dust2','Anubis','Cache','Cobblestone'}:raise ValueError('Fixed approved training/validation maps only')
    for name in a.maps:extract(name,a.output,a.cs2)
