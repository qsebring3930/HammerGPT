"""Source-face ray evidence. No NAV connections accepted by feature computation."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import tempfile
import numpy as np
from architecture_features import MeshIndex
from reconstruct_train_section import SectionScanner,select_triangles,ROI
from hammergpt import convert
from train_route_organization import encode,N,sha


class FastIndex(MeshIndex):
    def __init__(self,triangles,cell=512):
        self.triangles=triangles;self.cell=cell;self.bins=defaultdict(list);self.global_ids=[]
        self.low=triangles.min(1);self.high=triangles.max(1)
        lo=np.floor(triangles[:,:,:2].min(1)/cell).astype(int);hi=np.floor(triangles[:,:,:2].max(1)/cell).astype(int)
        for i,((x0,y0),(x1,y1)) in enumerate(zip(lo,hi)):
            if (x1-x0+1)*(y1-y0+1)>256:self.global_ids.append(i);continue
            for x in range(x0,x1+1):
                for y in range(y0,y1+1):self.bins[x,y].append(i)

    def ray(self,origin,direction,length):
        origin=np.asarray(origin,dtype=float);direction=np.asarray(direction,dtype=float);direction/=np.linalg.norm(direction)
        end=origin+direction*length;low=np.minimum(origin,end);high=np.maximum(origin,end)
        lo=np.floor(low[:2]/self.cell).astype(int);hi=np.floor(high[:2]/self.cell).astype(int)
        ids=set(self.global_ids)
        for x in range(lo[0],hi[0]+1):
            for y in range(lo[1],hi[1]+1):ids.update(self.bins[x,y])
        if not ids:return {'distance_units':length,'hit_triangle':None}
        ids=np.array(sorted(ids));keep=np.all(self.high[ids]>=low-1e-5,axis=1)&np.all(self.low[ids]<=high+1e-5,axis=1)
        ids=ids[keep]
        if not len(ids):return {'distance_units':length,'hit_triangle':None}
        triangles=self.triangles[ids];e1=triangles[:,1]-triangles[:,0];e2=triangles[:,2]-triangles[:,0]
        h=np.cross(direction,e2);det=np.einsum('ij,ij->i',e1,h);good=np.abs(det)>1e-9
        inv=np.divide(1,det,out=np.zeros_like(det),where=good);s=origin-triangles[:,0];u=np.einsum('ij,ij->i',s,h)*inv
        q=np.cross(s,e1);v=np.einsum('ij,j->i',q,direction)*inv;distance=np.einsum('ij,ij->i',e2,q)*inv
        good&=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(distance>.01)&(distance<=length)
        if not good.any():return {'distance_units':length,'hit_triangle':None}
        distance=np.where(good,distance,np.inf);winner=int(np.argmin(distance))
        return {'distance_units':float(distance[winner]),'hit_triangle':int(ids[winner])}


def supported(start,end,bounds):
    return bool(np.all(np.minimum(start,end)>=bounds[0]) and np.all(np.maximum(start,end)<=bounds[1]))


def ray_fraction(index,start,end,bounds):
    delta=end-start;length=float(np.linalg.norm(delta))
    if length<=.01 or not supported(start,end,bounds):return 0.,0.
    hit=index.ray(start,delta,length)
    return hit['distance_units']/length,1.


def features(triangles,origins,bounds,right,forward):
    """Inputs contain supplied positions and source faces, never adjacency labels."""
    index=FastIndex(triangles);node=np.zeros((N,32),np.float32);pair=np.zeros((N,N,12),np.float32)
    for i,point in enumerate(origins):
        for k,angle in enumerate(np.arange(8)*math.pi/4):
            direction=np.r_[right*math.cos(angle)+forward*math.sin(angle),0.]
            for j,height in enumerate((32,64)):
                start=point+[0,0,height];value,known=ray_fraction(index,start,start+direction*512,bounds)
                node[i,2*(k*2+j):2*(k*2+j)+2]=value,known
        for other,end in enumerate(origins):
            delta=end-point;length=np.linalg.norm(delta)
            if i==other or length>2048 or length<=.01:continue
            side=np.array([-delta[1],delta[0],0.]);side/=max(np.linalg.norm(side),1e-9)
            for k,offset in enumerate((-16,0,16)):
                for j,height in enumerate((32,64)):
                    shift=side*offset+[0,0,height]
                    value,known=ray_fraction(index,point+shift,end+shift,bounds)
                    slot=2*(k*2+j);pair[i,other,slot:slot+2]=value,known
        if i%10==0:print(f'Geometry-only ray features: {i+1}/{len(origins)} supplied areas',flush=True)
    return node,pair


def extract_native(root,name,output,cs2):
    record=encode(root,name,root/'output/route-corpus-expanded-v2')
    graph=json.loads(Path(record['provenance']['source_graph']).read_text());source=Path(graph['provenance']['vmap_source'])
    if sha(source)!=graph['provenance']['vmap_source_sha256']:raise ValueError('Source VMAP changed')
    output.mkdir(parents=True,exist_ok=False)
    points=np.array([p for a in graph['nav_polygons'] for p in a['corners']]);bounds=np.array([points.min(0)-[2048,2048,512],points.max(0)+[2048,2048,512]])
    scanner=SectionScanner(bounds)
    with tempfile.TemporaryDirectory(prefix='hammergpt-native-obstruction-') as tmp:
        text=Path(tmp)/'source.txt';convert(cs2/'game/bin/win64/dmxconvert.exe',source,text,'keyvalues2')
        print(f'{name}: scanning original VMAP faces',flush=True)
        with text.open(encoding='utf-8-sig') as stream:
            for i,line in enumerate(stream):
                scanner.feed(line)
                if i and i%1500000==0:print(f'{name}: {i} source lines',flush=True)
        triangles,_,_=scanner.geometry()
    triangles=triangles[select_triangles(triangles,bounds)]
    np.savez_compressed(output/'native.npz',triangles=triangles)
    (output/'manifest.json').write_text(json.dumps({'map':name,'bounds':bounds.tolist(),'source':str(source),'source_sha256':sha(source),
        'native_sha256':sha(output/'native.npz'),'native_triangles':len(triangles),'scanner_stats':dict(scanner.stats)},indent=2),encoding='utf-8')
    print(f'{name}: cached {len(triangles)} original editor triangles',flush=True)


def source_cache(root,name):
    if name in ('anubis','cache','cobblestone'):
        folder=root/f'output/learning-geometry-v1/{name}';m=json.loads((folder/'manifest.json').read_text())
        return folder/'native.npz',np.array(m['bounds']),m['native_sha256'],m['source_sha256']
    if name=='train':
        folder=root/'output/train-reconstruction-v1';m=json.loads((folder/'cache-manifest.json').read_text())
        return folder/'native.npz',ROI,m['native_sha256'],m['provenance']['vmap_source_sha256']
    if name=='dust2':
        folder=root/'output/architecture-dust2-v1';m=json.loads((folder/'features.json').read_text())
        audit=json.loads((root/'output/geometry-completion-dataset-v2/dust2-metadata.json').read_text())
        return folder/'triangles.npz',np.array([[-1e8]*3,[1e8]*3]),audit['native_sha256'],m['provenance']['vmap_sha256']
    folder=root/f'output/native-obstruction-cache-v1/{name}';m=json.loads((folder/'manifest.json').read_text())
    return folder/'native.npz',np.array(m['bounds']),m['native_sha256'],m['source_sha256']


def build(root,name,output):
    output.mkdir(parents=True,exist_ok=True)
    record=encode(root,name,root/'output/route-corpus-expanded-v2');graph=json.loads(Path(record['provenance']['source_graph']).read_text())
    cache,bounds,digest,vmap_digest=source_cache(root,name)
    if sha(cache)!=digest or graph['provenance']['vmap_source_sha256']!=vmap_digest:raise ValueError('Geometry cache provenance mismatch')
    triangles=np.load(cache)['triangles'];nodes={n['id']:n for n in graph['nodes']}
    polygon_centers={p['id']:np.mean(p['corners'],axis=0) for p in graph['nav_polygons']}
    # Sample supplied area interiors geometrically, never using a neighboring NAV pair.
    origins=np.array([min((polygon_centers[a] for a in nodes[key]['nav_area_ids']),key=lambda p:np.linalg.norm(p-nodes[key]['position'])) for key in record['ids']])
    raw=json.loads(Path(record['provenance']['route_targets']).read_text())
    t=polygon_centers[raw['terminals']['T']['representative_nav_area']];ct=polygon_centers[raw['terminals']['CT']['representative_nav_area']]
    forward=(ct-t)[:2];forward/=np.linalg.norm(forward);right=np.array([forward[1],-forward[0]])
    node,pair=features(triangles,origins,bounds,right,forward)
    np.savez_compressed(output/f'{name}.npz',node=node,pair=pair)
    valid=record['valid'];mask=valid[:,None]&valid[None,:]&~np.eye(N,dtype=bool)
    metadata={'map':name,'source_faces':str(cache.resolve()),'source_faces_sha256':digest,'vmap_sha256':vmap_digest,'bounds':bounds.tolist(),
              'source_route_targets_sha256':record['provenance']['route_targets_sha256'],'node_ids':record['ids'],
              'features_sha256':sha(output/f'{name}.npz'),'node_ray_supported_fraction':float(node[:len(origins),1::2].mean()),
              'pair_ray_supported_fraction':float(pair[:,:,1::2][mask].mean()),'static_props_included':False,
              'hidden_nav_connections_used_as_feature_inputs':False,'native_intersections_are_not_collision_or_visibility':True}
    (output/f'{name}.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8');print(json.dumps(metadata),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--extract-native',action='store_true');p.add_argument('--cs2',type=Path)
    args=p.parse_args();root=Path(__file__).resolve().parent
    if args.extract_native:extract_native(root,args.map,args.output,args.cs2)
    else:build(root,args.map,args.output)
