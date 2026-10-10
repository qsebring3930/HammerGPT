"""Map-separated layered walking/source-surface volumes for masked completion."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from audit_train_reconstruction import sample_nav

CELL=32
SHAPE=(16,32,32)
SPLITS={'train':['Dust2','Anubis','Cache'],'validation':['Cobblestone'],'test':['Train']}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def stamp(volume,points,origin):
    q=np.floor((points-origin)/CELL).astype(np.int32)
    keep=np.all(q>=0,axis=1)&np.all(q<np.array(volume.shape[::-1]),axis=1);q=q[keep]
    volume[q[:,2],q[:,1],q[:,0]]=1

def raster_surfaces(triangles,volume,origin):
    """Adaptive triangle samples, <=32-unit edges; approximate surface occupancy."""
    high=origin+np.array(volume.shape[::-1])*CELL
    for begin in range(0,len(triangles),8192):
        t=triangles[begin:begin+8192]
        t=t[np.all(t.max(axis=1)>=origin,axis=1)&np.all(t.min(axis=1)<high,axis=1)]
        pending=[t]
        while pending:
            t=pending.pop()
            if not len(t):continue
            # Prune child triangles outside the volume before further subdivision.
            t=t[np.all(t.max(axis=1)>=origin,axis=1)&np.all(t.min(axis=1)<high,axis=1)]
            lengths=np.linalg.norm(t-np.roll(t,-1,axis=1),axis=2).max(axis=1)
            small=t[lengths<=CELL]
            if len(small):
                stamp(volume,np.concatenate([small.reshape(-1,3),small.mean(axis=1),((small+np.roll(small,-1,axis=1))/2).reshape(-1,3)]),origin)
            large=t[lengths>CELL]
            if len(large):
                a,b,c=large[:,0],large[:,1],large[:,2];ab=(a+b)/2;bc=(b+c)/2;ca=(c+a)/2
                children=np.concatenate([np.stack([a,ab,ca],1),np.stack([ab,b,bc],1),np.stack([ca,bc,c],1),np.stack([ab,bc,ca],1)])
                pending.extend(children[i:i+32768] for i in range(0,len(children),32768))

def sources(name,cache):
    if name=='Dust2':
        native=Path('output/architecture-dust2-v1/triangles.npz');props=Path('output/model-geometry-dust2-v2/render-triangles.npz')
        audit=json.loads(Path('output/architecture-dust2-v1/features.json').read_text())['provenance']
        prop_audit=json.loads(Path('output/model-geometry-dust2-v2/instances.json').read_text())
        g=json.loads(Path('output/coarse-layout-v1/dust2.json').read_text())
        if audit['vmap_sha256']!=g['provenance']['vmap_source_sha256'] or prop_audit['provenance']['vmap_sha256']!=audit['vmap_sha256']:raise ValueError('Dust2 cache source mismatch')
        return native,props,None
    if name=='Train':
        p=Path('output/train-reconstruction-v1');s=json.loads((p/'section.json').read_text())
        return p/'native.npz',p/'props.npz',np.array(s['roi_xyz'])
    p=cache/name.lower();waited=0
    while not (p/'manifest.json').exists():
        if waited%60==0:print(f'Waiting for {name} geometry cache ({waited}s)',flush=True)
        if waited>=7200:raise TimeoutError('Geometry extraction did not finish')
        time.sleep(5);waited+=5
    m=json.loads((p/'manifest.json').read_text())
    for key in ['native','props']:
        if sha(p/f'{key}.npz')!=m[key+'_sha256']:raise ValueError('Geometry cache changed')
    return p/'native.npz',p/'props.npz',None

def make_volume(name,cache,out):
    gp=Path(f'output/coarse-layout-v1/{name.lower()}.json');g=json.loads(gp.read_text())
    navpath=Path(g['provenance']['nav_export']);raw=navpath.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=g['provenance']['nav_export_sha256']:raise ValueError('NAV source mismatch')
    nav=json.loads(raw);areas=[a for a in nav['areas'] if a['hull']==0 and a['movable_mesh_id']==0xffffffff]
    native,props,bounds=sources(name,cache)
    if bounds is not None:
        ids={a['id'] for a in json.loads(Path('output/train-reconstruction-v1/section.json').read_text())['areas']};areas=[a for a in areas if a['id'] in ids]
    existing=out/(name.lower()+'-metadata.json')
    if existing.exists():
        meta=json.loads(existing.read_text());path=out/(name.lower()+'-volume.npz')
        if meta['graph_sha256']!=sha(gp) or meta['native_sha256']!=sha(native) or meta['props_sha256']!=sha(props) or meta['volume_sha256']!=sha(path):raise ValueError('Cached volume changed')
        meta['geometry_bounds']=bounds.tolist() if bounds is not None else (json.loads((cache/name.lower()/'manifest.json').read_text())['bounds'] if name!='Dust2' else None)
        with np.load(path) as d:return d['volume'],d['origin'],areas,bounds,meta
    points=np.array([p for a in areas for p in a['corners']]);low=points.min(axis=0)-[64,64,128];high=points.max(axis=0)+[64,64,384]
    origin=np.floor(low/CELL)*CELL;shape=tuple(map(int,np.ceil((high-origin)/CELL).astype(int)[::-1]));volume=np.zeros((2,*shape),dtype=np.uint8)
    samples,fallback=sample_nav(areas,CELL)
    xyz=np.stack([(samples[:,1]+.5)*CELL,(samples[:,2]+.5)*CELL,samples[:,3]],axis=1)
    stamp(volume[0],xyz,origin)
    if len(fallback):stamp(volume[0],fallback[:,1:],origin)
    for path in [native,props]:
        t=np.load(path)['triangles'];print(name+' rasterizing '+path.name+f' ({len(t)} triangles)',flush=True);raster_surfaces(t,volume[1],origin)
    path=out/(name.lower()+'-volume.npz');np.savez_compressed(path,volume=volume,origin=origin)
    meta={'map':name,'graph_sha256':sha(gp),'nav_sha256':sha(navpath),'vmap_sha256':g['provenance']['vmap_source_sha256'],
          'native':str(native),'props':str(props),'native_sha256':sha(native),'props_sha256':sha(props),
          'volume_sha256':sha(path),'shape_zyx':shape,'origin_xyz':origin.tolist(),
          'selection_bounds':bounds.tolist() if bounds is not None else None,
          'geometry_bounds':bounds.tolist() if bounds is not None else (json.loads((cache/name.lower()/'manifest.json').read_text())['bounds'] if name!='Dust2' else None),
          'small_nav_polygons_with_centroid_fallback':len(fallback)}
    (out/(name.lower()+'-metadata.json')).write_text(json.dumps(meta,indent=2))
    return volume,origin,areas,bounds,meta

def crop(volume,c):
    z,y,x=c;low=np.array([z-4,y-16,x-16]);high=low+SHAPE
    if np.any(low<0) or np.any(high>volume.shape[1:]):return None
    return volume[:,low[0]:high[0],low[1]:high[1],low[2]:high[2]].copy()

def build(cache,out,resume=False):
    if out.exists() and (not resume or (out/'manifest.json').exists()):raise ValueError('Choose a new dataset directory')
    out.mkdir(parents=True,exist_ok=resume);rng=np.random.default_rng(20261009);man={'splits':SPLITS,'cell_units':CELL,'patch_shape_zyx':SHAPE,
        'hidden_xy':[10,22],'channels':['recorded_NAV_walking_surface','source_editor_and_static_render_surface'],
        'maps':[],'samples':{},'seed':20261009,'model_training_performed':False,
        'limits':['Surface voxelization is sampled geometry, not solid occupancy or collision.',
                  'No initial-control, sightline, cover, ladder traversal or whole-map generation target.',
                  'Train test covers only the reconstructed outer-yard section. Entire Train excluded from training/validation.',
                  'Crops overlap within a map; sample count does not equal independent map count.']}
    for split,names in SPLITS.items():
        patches=[];records=[];supports=[]
        for name in names:
            v,o,areas,bounds,meta=make_volume(name,cache,out);man['maps'].append(meta)
            count=192 if split=='train' else 96;centers=np.array([np.mean(a['corners'],axis=0) for a in areas]);keys=set();accepted=0
            for attempt in range(count*100):
                p=centers[rng.integers(len(centers))].copy();p[:2]+=rng.integers(-4,5,size=2)*CELL
                if bounds is not None and (np.any(p[:2]-512<bounds[0,:2]) or np.any(p[:2]+512>bounds[1,:2])):continue
                c=np.floor((p-o)/CELL).astype(int)[::-1];key=tuple(c)
                if key in keys:continue
                a=crop(v,c)
                if a is None:continue
                valid=np.ones_like(a,dtype=np.uint8)
                if meta['geometry_bounds'] is not None:
                    bb=np.array(meta['geometry_bounds']);zz,yy,xx=np.indices(SHAPE)
                    low=o+(c[::-1]-[16,16,4])*CELL
                    xyz=np.stack([xx,yy,zz],-1)*CELL+low+CELL/2
                    valid[1]=np.all((xyz>=bb[0])&(xyz<=bb[1]),axis=-1)
                if valid[1,:,10:22,10:22].sum()<144*4:continue
                hidden=a[0,:,10:22,10:22]
                # Retain nontrivial missing walking structure; no test-based model tuning.
                if hidden.sum()<12 or hidden.sum()>16*144*.4:continue
                keys.add(key);patches.append(a);supports.append(valid);records.append({'map':name,'anchor_xyz':p.tolist(),'center_voxel_zyx':c.tolist()});accepted+=1
                if accepted==count:break
            if accepted<24:raise ValueError(f'Insufficient useful {name} sections: {accepted}')
            print(name+f': {accepted} fixed section patches',flush=True)
        file=out/(split+'.npz');np.savez_compressed(file,y=np.stack(patches),valid=np.stack(supports));(out/(split+'-records.json')).write_text(json.dumps(records,indent=2))
        man['samples'][split]={'count':len(patches),'sha256':sha(file),'records_sha256':sha(out/(split+'-records.json'))}
    (out/'manifest.json').write_text(json.dumps(man,indent=2));print(json.dumps(man['samples']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args();build(a.cache,a.output,a.resume)
