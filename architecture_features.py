"""Pilot native-VMAP face geometry and mesh-only observation features.

Ray results describe intersections with extracted editor faces, not game collision
or verified visibility. External model meshes and prefab instances are excluded.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import tempfile

import numpy as np

from analyze_map import SpatialScanner, world_point
from hammergpt import convert
from simplify_section import triangulate


ARRAYS = {'vertexDataIndices','edgeVertexIndices','edgeNextIndices','faceEdgeIndices','faceDataIndices','materials'}
HELPERS = {'env_cs_place','func_bomb_target','func_buyzone','func_hostage_rescue','trigger_multiple',
           'trigger_once','trigger_hurt','trigger_teleport','trigger_push'}


def face_triangles(points):
    points = np.asarray(points,dtype=float)
    if len(points)<3: raise ValueError('Short face')
    normal = np.sum(np.cross(points,np.roll(points,-1,axis=0)),axis=0)
    length = np.linalg.norm(normal)
    if length<1e-8: raise ValueError('Degenerate face')
    normal /= length
    deviation = float(np.max(np.abs((points-points[0])@normal)))
    if deviation>1.: raise ValueError('Nonplanar face exceeds pilot tolerance')
    # Ear clipping supports concave faces without filling their empty corners.
    drop = int(np.argmax(np.abs(normal))); projected = np.delete(points,drop,axis=1).tolist()
    signed = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(projected,projected[1:]+projected[:1]))
    if signed<0:
        points = points[::-1]; projected = projected[::-1]
    indices = triangulate(projected)
    triangles = points[np.asarray(indices)]
    area = float(np.sum(np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1))/2)
    return triangles,normal,area,deviation


class FaceScanner(SpatialScanner):
    def __init__(self):
        super().__init__(); self.batches=[]; self.stats=Counter(); self.mesh_index={}; self.faces=[]

    def feed(self,raw):
        line = raw.strip(); frame = self.stack[-1] if self.stack else None
        if line=='[' and frame:
            mesh = next((s for s in reversed(self.stack) if s['kind']=='CMapMesh'),None)
            key = self.pending[0] if self.pending else None
            if mesh and (key in ARRAYS or (key=='data' and (frame.get('is_position') or frame.get('is_material')))):
                key = 'positions' if frame.get('is_position') and key=='data' else 'material_index' if frame.get('is_material') and key=='data' else key
                frame['_capture']=(mesh,key); mesh.setdefault('_arrays',{})[key]=[]
        elif line==']' and frame:
            frame.pop('_capture',None)
        elif frame and frame.get('_capture') and line.startswith('"'):
            mesh,key=frame['_capture']; value=json.loads(line.rstrip(','))
            mesh['_arrays'][key].append(list(map(float,value.split())) if key=='positions' else value if key=='materials' else int(value))
        closing = frame if frame and line.rstrip(',')=='}' and frame['kind']=='CMapMesh' else None
        super().feed(raw)
        if self.stack and '"semanticName"' in line and '"materialindex"' in line:
            self.stack[-1]['is_material']=True
        if closing: self.extract_mesh(closing)

    def extract_mesh(self,mesh):
        data=mesh.pop('_arrays',{}); node=str(mesh.get('nodeID','')); batch=[]; face_records=[]
        self.stats['meshes_scanned']+=1
        if not all(k in data for k in ('positions','edgeVertexIndices','edgeNextIndices','faceEdgeIndices')):
            self.stats['meshes_without_complete_topology']+=1; return
        vertices=np.asarray([world_point(p,mesh) for p in data['positions']])
        ends,nxt,starts=[data[k] for k in ('edgeVertexIndices','edgeNextIndices','faceEdgeIndices')]
        mapping=data.get('vertexDataIndices',list(range(len(vertices))))
        materials=data.get('materials',[]); face_map=data.get('faceDataIndices',list(range(len(starts))))
        material_indices=data.get('material_index',[])
        for fi,start in enumerate(starts):
            self.stats['faces_scanned']+=1
            try:
                loop=[]; seen=set(); edge=start
                while edge not in seen:
                    if not 0<=edge<len(ends): raise ValueError('Edge index')
                    vertex=ends[edge]
                    if not 0<=vertex<len(mapping) or not 0<=mapping[vertex]<len(vertices): raise ValueError('Vertex index')
                    seen.add(edge); loop.append(vertices[mapping[vertex]]); edge=nxt[edge]
                if edge!=start: raise ValueError('Face loop')
                material=materials[material_indices[face_map[fi]]] if material_indices else ''
                if any(s in material.lower() for s in ('toolssky','tools_sky','toolsvis','toolstrigger','tools_trigger')):
                    self.stats['nonarchitectural_material_faces_excluded']+=1; continue
                triangles,normal,area,deviation=face_triangles(loop)
                begin=len(batch); batch.extend(triangles)
                face_records.append({'node_id':node,'face_index':fi,'material':material,'normal':normal.tolist(),
                    'area_sq_units':area,'planarity_error_units':deviation,
                    'bounds':{'min':np.min(loop,axis=0).tolist(),'max':np.max(loop,axis=0).tolist()},
                    'class':'vertical_surface' if abs(normal[2])<=.2 else 'horizontal_surface' if abs(normal[2])>=.85 else 'sloped_surface',
                    'triangle_start':begin,'triangle_count':len(triangles)})
            except (ValueError,IndexError,KeyError):
                self.stats['faces_skipped_invalid_or_degenerate']+=1
        if batch:
            self.mesh_index[node]=len(self.batches); self.batches.append((node,np.asarray(batch,dtype=np.float32),face_records))

    def geometry(self):
        spatial=super().finish(); meshes={m['node_id']:m for m in spatial['meshes']}
        entities={e['node_id']:e['classname'] for e in spatial['entities']}
        triangles=[]; face_records=[]; offset=0
        for node,batch,faces in self.batches:
            mesh=meshes[node]; owner=entities.get(mesh['owner_entity'],'')
            if mesh['editor_only'] or owner in HELPERS or owner.startswith('trigger_'):
                self.stats['helper_or_editor_meshes_excluded']+=1; continue
            for face in faces:
                face['triangle_start']+=offset; face['owner_classname']=owner or None
            triangles.append(batch); face_records.extend(faces); offset+=len(batch)
        self.stats['triangles_retained']=offset; self.stats['faces_retained']=len(face_records)
        self.stats['retained_meshes']=len(triangles)
        return np.concatenate(triangles) if triangles else np.empty((0,3,3),dtype=np.float32),face_records,spatial


class MeshIndex:
    def __init__(self,triangles,cell=512):
        self.triangles=triangles; self.cell=cell; self.bins=defaultdict(list); self.global_ids=[]
        for i,t in enumerate(triangles):
            lo=np.floor(t[:,:2].min(axis=0)/cell).astype(int);hi=np.floor(t[:,:2].max(axis=0)/cell).astype(int)
            if (hi[0]-lo[0]+1)*(hi[1]-lo[1]+1)>256:
                self.global_ids.append(i);continue
            for x in range(lo[0],hi[0]+1):
                for y in range(lo[1],hi[1]+1):self.bins[x,y].append(i)

    def ray(self,origin,direction,length):
        origin=np.asarray(origin,dtype=float);direction=np.asarray(direction,dtype=float)
        direction/=np.linalg.norm(direction);end=origin+direction*length
        lo=np.floor(np.minimum(origin[:2],end[:2])/self.cell).astype(int)
        hi=np.floor(np.maximum(origin[:2],end[:2])/self.cell).astype(int)
        ids=set(self.global_ids)
        for x in range(lo[0],hi[0]+1):
            for y in range(lo[1],hi[1]+1):ids.update(self.bins[x,y])
        if not ids:return {'distance_units':length,'hit_triangle':None}
        ids=np.asarray(sorted(ids));t=self.triangles[ids]
        # Double-sided Moller-Trumbore intersections. Exclude the ray origin.
        e1=t[:,1]-t[:,0];e2=t[:,2]-t[:,0];h=np.cross(direction,e2);det=np.einsum('ij,ij->i',e1,h)
        good=np.abs(det)>1e-9;inv=np.divide(1,det,out=np.zeros_like(det),where=good)
        s=origin-t[:,0];u=np.einsum('ij,ij->i',s,h)*inv;q=np.cross(s,e1)
        v=q@direction*inv;distance=np.einsum('ij,ij->i',e2,q)*inv
        good&=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(distance>.01)&(distance<=length)
        if not good.any():return {'distance_units':length,'hit_triangle':None}
        distance=np.where(good,distance,np.inf);winner=int(np.argmin(distance))
        return {'distance_units':float(distance[winner]),'hit_triangle':int(ids[winner])}


def features(graph,triangles,faces):
    index=MeshIndex(triangles); polygons={a['id']:a for a in graph['nav_polygons']};nodes=[];probes=[]
    lows=np.asarray([f['bounds']['min'] for f in faces]);highs=np.asarray([f['bounds']['max'] for f in faces])
    for node in graph['nodes']:
        members=[polygons[k] for k in node['nav_area_ids']]
        # Sample existing NAV polygon centroids; a coarse region centroid may lie in a wall.
        members=sorted(members,key=lambda a:a['id']);take=[members[i] for i in sorted({0,len(members)//2,len(members)-1})]
        samples=[]
        for polygon in take:
            origin=np.mean(polygon['corners'],axis=0);rays=[]
            for angle in np.arange(16)*math.tau/16:
                direction=[math.cos(angle),math.sin(angle),0]
                low=index.ray(origin+[0,0,32],direction,2048);high=index.ray(origin+[0,0,64],direction,2048)
                rays.append({'angle_radians':float(angle),'low_mesh_hit':low,'high_mesh_hit':high,
                             'low_obstacle_candidate':low['hit_triangle'] is not None and low['distance_units']<256 and high['distance_units']>low['distance_units']+64})
            samples.append({'nav_area_id':polygon['id'],'nav_centroid':origin.tolist(),'rays':rays})
        box=node['bounds'];near=np.all(highs>=np.asarray(box['min'])-128,axis=1)&np.all(lows<=np.asarray(box['max'])+128,axis=1)
        nearby=[f for f,keep in zip(faces,near) if keep]
        nodes.append({'region_id':node['id'],'nearby_native_faces':len(nearby),
                      'nearby_face_area_by_class':{c:sum(f['area_sq_units'] for f in nearby if f['class']==c) for c in ('vertical_surface','horizontal_surface','sloped_surface')},
                      'sampled_mesh_rays':samples,
                      'low_obstacle_candidate_rays':sum(r['low_obstacle_candidate'] for s in samples for r in s['rays'])})
    for edge in graph['edges']:
        witness=max(edge['witnesses'],key=lambda w:w.get('source_edge_length_xy',0))
        source=np.mean(polygons[witness['source_nav_area']]['corners'],axis=0)+[0,0,64]
        target=np.mean(polygons[witness['target_nav_area']]['corners'],axis=0)+[0,0,64]
        delta=target-source;length=float(np.linalg.norm(delta))
        hit=index.ray(source,delta,length) if length>.01 else {'distance_units':length,'hit_triangle':None}
        probes.append({'source':edge['source'],'target':edge['target'],
                       'source_nav_area':witness['source_nav_area'],'target_nav_area':witness['target_nav_area'],
                       'raised_centroid_segment_length':length,'mesh_hit':hit,
                       'interpretation':'mesh-only straight segment probe; recorded NAV traversal may bend or change posture'})
    return nodes,probes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph',type=Path,required=True);parser.add_argument('--cs2',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();graph=json.loads(args.graph.read_text())
    if args.output.exists():parser.error('Choose a new output directory')
    if graph['dataset_role']!='training':parser.error('Only approved training graph allowed')
    source=Path(graph['provenance']['vmap_source'])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=graph['provenance']['vmap_source_sha256']:raise ValueError('VMAP changed since graph extraction')
    args.output.mkdir(parents=True);scanner=FaceScanner()
    with tempfile.TemporaryDirectory(prefix='hammergpt-face-scan-') as temporary:
        text=Path(temporary)/'source.txt'
        convert(args.cs2/'game/bin/win64/dmxconvert.exe',source,text,'keyvalues2')
        print('Scanning native mesh faces...',flush=True)
        with text.open(encoding='utf-8-sig') as stream:
            for line in stream:scanner.feed(line)
        triangles,faces,spatial=scanner.geometry()
    print(json.dumps(dict(scanner.stats)),flush=True)
    if not len(triangles):raise ValueError('No native face triangles extracted')
    np.savez_compressed(args.output/'triangles.npz',triangles=triangles)
    (args.output/'faces.json').write_text(json.dumps(faces),encoding='utf-8')
    print('Sampling mesh-only observations...',flush=True)
    nodes,probes=features(graph,triangles,faces)
    data={'schema_version':1,'map':graph['map'],'model_training_performed':False,'native_geometry_stats':dict(scanner.stats),
          'region_features':nodes,'recorded_transition_geometry_probes':probes,
          'parameters':{'ray_heights_above_nav_centroid':[32,64],'directions_per_sample':16,'maximum_ray_units':2048,
                        'nearby_face_bounds_margin':128,'planarity_tolerance_units':1},
          'provenance':{'source_graph':str(args.graph.resolve()),'source_graph_sha256':hashlib.sha256(args.graph.read_bytes()).hexdigest(),
                        'vmap_source':str(source),'vmap_sha256':graph['provenance']['vmap_source_sha256'],
                        'extractor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
          'limitations':['Native editable mesh faces only; external models and prefab instances are not expanded.',
                         'Trigger/helper and editor-only meshes are excluded; material sky/visibility/trigger surfaces are excluded.',
                         'Nonplanar, degenerate or invalid faces are skipped and counted. Subdivision and displacement are not evaluated.',
                         'Triangle intersections are double-sided geometry observations, not collision, opacity, bullet penetration, player clearance or verified sightlines.',
                         'Nearby-face association uses expanded bounds and may include another elevation or an adjacent area.',
                         'Low-obstacle candidates compare rays at selected heights; they do not establish tactical cover.',
                         'Straight segment probes do not invalidate recorded NAV links. Geometry/NAV freshness still needs validation.']}
    (args.output/'features.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({'regions':len(nodes),'transition_probes':len(probes),'output':str(args.output)}),flush=True)


if __name__=='__main__':main()
