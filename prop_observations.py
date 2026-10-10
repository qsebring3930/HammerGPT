"""Compare native-only probes with added static-prop render geometry."""
import argparse
import copy
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np


class PropIndex:
    def __init__(self,triangles,cell=512):
        self.triangles=triangles;self.cell=cell;self.bins=defaultdict(list);self.global_ids=[]
        self.low=triangles.min(axis=1);self.high=triangles.max(axis=1)
        lo=np.floor(self.low[:,:2]/cell).astype(int);hi=np.floor(self.high[:,:2]/cell).astype(int)
        for i,(a,b) in enumerate(zip(lo,hi)):
            if (b[0]-a[0]+1)*(b[1]-a[1]+1)>256:self.global_ids.append(i);continue
            for x in range(a[0],b[0]+1):
                for y in range(a[1],b[1]+1):self.bins[x,y].append(i)

    def ray(self,origin,direction,length):
        origin=np.asarray(origin,dtype=float);direction=np.asarray(direction,dtype=float)
        direction/=np.linalg.norm(direction);end=origin+direction*length
        lo=np.floor(np.minimum(origin[:2],end[:2])/self.cell).astype(int)
        hi=np.floor(np.maximum(origin[:2],end[:2])/self.cell).astype(int);ids=set(self.global_ids)
        for x in range(lo[0],hi[0]+1):
            for y in range(lo[1],hi[1]+1):ids.update(self.bins[x,y])
        if not ids:return None
        ids=np.asarray(sorted(ids));keep=np.all(self.high[ids]>=np.minimum(origin,end)-1e-6,axis=1)&np.all(self.low[ids]<=np.maximum(origin,end)+1e-6,axis=1)
        ids=ids[keep]
        if not len(ids):return None
        t=self.triangles[ids];e1=t[:,1]-t[:,0];e2=t[:,2]-t[:,0];h=np.cross(direction,e2);det=np.einsum('ij,ij->i',e1,h)
        good=np.abs(det)>1e-9;inv=np.divide(1,det,out=np.zeros_like(det),where=good);s=origin-t[:,0]
        u=np.einsum('ij,ij->i',s,h)*inv;q=np.cross(s,e1);v=q@direction*inv;distance=np.einsum('ij,ij->i',e2,q)*inv
        good&=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(distance>.01)&(distance<=length)
        if not good.any():return None
        distance=np.where(good,distance,np.inf);winner=int(np.argmin(distance))
        return {'distance_units':float(distance[winner]),'model_triangle':int(ids[winner])}


def build(native_folder,model_folder,output):
    if output.exists():raise ValueError('Choose a new output directory')
    native=json.loads((native_folder/'features.json').read_text());models=json.loads((model_folder/'instances.json').read_text())
    if native['provenance']['vmap_sha256']!=models['provenance']['vmap_sha256']:raise ValueError('Source map mismatch')
    with np.load(model_folder/'render-triangles.npz') as data:triangles=data['triangles']
    print('Indexing expanded static-prop geometry...',flush=True);index=PropIndex(triangles)
    starts=np.asarray([r['triangle_start'] for r in models['triangle_ranges']]);ranges=models['triangle_ranges']
    changed=0;total=0;nodes=copy.deepcopy(native['region_features'])
    for node in nodes:
        for sample in node['sampled_mesh_rays']:
            origin=np.asarray(sample['nav_centroid'])
            for ray in sample['rays']:
                direction=[math.cos(ray['angle_radians']),math.sin(ray['angle_radians']),0]
                for key,height in (('low_mesh_hit',32),('high_mesh_hit',64)):
                    total+=1;old=ray[key];hit=index.ray(origin+[0,0,height],direction,old['distance_units'])
                    new=copy.deepcopy(old);new['geometry_source']='native_mesh';new['native_hit']=copy.deepcopy(old)
                    if hit and hit['distance_units']<old['distance_units']-.01:
                        changed+=1;rid=int(np.searchsorted(starts,hit['model_triangle'],side='right')-1)
                        new.update(distance_units=hit['distance_units'],hit_triangle=None,model_triangle=hit['model_triangle'],
                                   model_node_id=ranges[rid]['node_id'],geometry_source='static_prop_render')
                    ray[key]=new
                low,high=ray['low_mesh_hit'],ray['high_mesh_hit']
                ray['low_obstacle_candidate']=(low['hit_triangle'] is not None or low.get('model_triangle') is not None) and low['distance_units']<256 and high['distance_units']>low['distance_units']+64
        node['low_obstacle_candidate_rays']=sum(r['low_obstacle_candidate'] for s in node['sampled_mesh_rays'] for r in s['rays'])
    graph=json.loads(Path(native['provenance']['source_graph']).read_text());polygons={p['id']:p for p in graph['nav_polygons']}
    probes=copy.deepcopy(native['recorded_transition_geometry_probes']);changed_probes=0
    for probe in probes:
        source=np.mean(polygons[probe['source_nav_area']]['corners'],axis=0)+[0,0,64]
        target=np.mean(polygons[probe['target_nav_area']]['corners'],axis=0)+[0,0,64]
        length=float(np.linalg.norm(target-source));old=probe['mesh_hit'];probe['native_mesh_hit']=copy.deepcopy(old)
        hit=index.ray(source,target-source,old['distance_units']) if length>.01 else None
        if hit and hit['distance_units']<old['distance_units']-.01:
            changed_probes+=1;probe['model_render_hit']=hit
    result={'schema_version':1,'map':native['map'],'model_training_performed':False,'region_features':nodes,
            'recorded_transition_geometry_probes':probes,'summary':{'sampled_rays':total,'rays_shortened_by_props':changed,
            'transition_probes':len(probes),'transition_probes_with_nearer_prop_hit':changed_probes,
            'native_low_obstacle_candidate_rays':sum(n['low_obstacle_candidate_rays'] for n in native['region_features']),
            'model_aware_low_obstacle_candidate_rays':sum(n['low_obstacle_candidate_rays'] for n in nodes)},
            'provenance':{'native_features_sha256':hashlib.sha256((native_folder/'features.json').read_bytes()).hexdigest(),
                          'model_instances_sha256':hashlib.sha256((model_folder/'instances.json').read_bytes()).hexdigest(),
                          'extractor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            'limitations':['Render geometry observations only; collision/opacity/material rules and game behavior remain unverified.',
                           'Other model entity classes, prefabs and animation are excluded. No NAV links are added or removed.',
                           'Nearer render-model intersections improve geometric coverage but do not establish gameplay visibility or cover.']}
    output.mkdir(parents=True);(output/'features.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['summary']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--models',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.native,args.models,args.output)
