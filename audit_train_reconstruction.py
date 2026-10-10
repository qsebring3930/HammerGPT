"""Audit source preservation and construct a layered section input, not training."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from prop_observations import PropIndex
from reconstruct_train_section import overlaps

def sample_nav(areas,grid=32):
    samples=[];fallback=[]
    for a in areas:
        p=np.asarray(a['corners'],dtype=float);count=0
        for x in range(math.floor(p[:,0].min()/grid),math.ceil(p[:,0].max()/grid)):
            for y in range(math.floor(p[:,1].min()/grid),math.ceil(p[:,1].max()/grid)):
                xy=np.array([(x+.5)*grid,(y+.5)*grid])
                for i in range(1,len(p)-1):
                    t=p[[0,i,i+1]];basis=(t[1:,:2]-t[0,:2]).T
                    if abs(np.linalg.det(basis))<1e-9:continue
                    u,v=np.linalg.solve(basis,xy-t[0,:2])
                    if u>=-1e-7 and v>=-1e-7 and u+v<=1+1e-7:
                        z=t[0,2]+u*(t[1,2]-t[0,2])+v*(t[2,2]-t[0,2])
                        samples.append([a['id'],x,y,z]);count+=1;break
        if count==0:fallback.append([a['id'],*p.mean(axis=0)])
    return np.asarray(samples,dtype=float).reshape(-1,4),np.asarray(fallback,dtype=float).reshape(-1,4)

def run(directory):
    s=json.loads((directory/'section.json').read_text());navpath=Path(s['provenance']['nav_export'])
    raw=navpath.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=s['provenance']['nav_export_sha256']:raise ValueError('NAV source changed')
    source={a['id']:a for a in json.loads(raw)['areas'] if a['hull']==0 and a['movable_mesh_id']==0xffffffff}
    for a in s['areas']:
        if a!=source[a['id']]:raise ValueError('A retained NAV polygon or traversal attribute was changed')
    selected={a['id'] for a in s['areas']}
    expected=[{'source':k,**c} for k,a in source.items() for c in a['connections'] if k in selected and c['target'] in selected]
    if expected!=s['directed_connections']:raise ValueError('Directed topology changed')
    samples,fallback=sample_nav(s['areas']);np.savez_compressed(directory/'layered-nav-input.npz',
        area_grid_xy_height=samples,small_area_centroid_fallback=fallback,grid_units=np.array(32))
    heights={}
    for _,x,y,z in samples:heights.setdefault((int(x),int(y)),[]).append(z)
    multi=int(sum(max(z)-min(z)>48 for z in heights.values()))
    native=np.load(directory/'native.npz')['triangles'];props=np.load(directory/'props.npz')['triangles']
    triangles=np.concatenate([native,props]);index=PropIndex(triangles)
    centers=[(a['id'],np.mean(a['corners'],axis=0)) for a in s['areas']]
    # Spatially distributed anchors, rather than the first IDs or place-name hints.
    chosen=[centers[0]]
    while len(chosen)<min(48,len(centers)):
        remaining=[c for c in centers if c[0] not in {a[0] for a in chosen}]
        chosen.append(max(remaining,key=lambda c:min(np.linalg.norm(c[1]-a[1]) for a in chosen)))
    observations=[]
    for key,p in chosen:
        rays=[]
        for angle in np.arange(16)*math.tau/16:
            direction=[math.cos(angle),math.sin(angle),0]
            hit=index.ray(p+[0,0,64],direction,1024)
            rays.append({'distance_units':hit['distance_units'] if hit else 1024,
                         'hit_triangle':hit['model_triangle'] if hit else None})
        observations.append({'nav_area_id':key,'origin_xyz':(p+[0,0,64]).tolist(),'rays':rays})
    (directory/'mesh-observations.json').write_text(json.dumps({'ray_count':16,'maximum_length_units':1024,
        'observations':observations,'interpretation':'Double-sided intersections with source editor/render triangles, not validated visibility or collision.'},indent=2))
    annotation_path=Path('output/annotations/train-reviewed-v1/semantic-targets.json')
    annotation=json.loads(annotation_path.read_text());contexts=[]
    for kind in ['meeting_targets','choke_targets']:
        for c in annotation[kind]:
            pieces=[p for p in c.get('surface_pieces',[]) if p['nav_area_id'] in selected and overlaps(p['corners'])]
            if pieces:contexts.append({'kind':kind,'id':c['id'],'title':c['title'],'surface_pieces':pieces})
    if not contexts:raise ValueError('Section has no reviewed contexts')
    (directory/'reviewed-contexts.json').write_text(json.dumps({'source':str(annotation_path),
        'source_sha256':hashlib.sha256(annotation_path.read_bytes()).hexdigest(),'contexts':contexts,
        'limits':'Existing reviewed context extents only; no new timing or visibility labels.'},indent=2))
    r=json.loads((directory/'report.json').read_text());r.update(source_nav_exact_roundtrip=True,
        retained_directed_topology_exact=True,layered_nav_samples=len(samples),
        small_area_fallbacks=len(fallback),xy_grid_locations_with_layers_separated_over_48_units=multi,
        geometric_ray_observations=len(observations)*16,training_started=False)
    (directory/'report.json').write_text(json.dumps(r,indent=2))
    lines=['# Train section reconstruction','','This is a representation experiment, not a generated map or a trained model.',
        '',f"Preserved {r['nav_polygons']} original XYZ NAV polygons and {r['directed_connections']} directed links, with {r['boundary_connections']} explicit connections across the crop.",
        f"Retained {r['native_triangles']} native editor triangles and {r['prop_render_triangles']} source static-prop render triangles.",
        f"Layered input uses {len(samples)} 32-unit XY samples with interpolated heights; {len(fallback)} small polygons retain a separate centroid fallback. Original polygons remain canonical.",
        f"{multi} grid locations retain surfaces separated by more than 48 vertical units. Elevations are not collapsed into a single floor.",
        '', '## Checks','', 'All selected source NAV polygons, flags, edge indices, ladder references and directed links match the cached source exactly.',
        'Occurrence IDs preserve separate decompiled objects even when their original nodeID values repeat.',
        '', '## Next experiment','',
        'Review the reconstructed section and coverage before training. Resolve gameplay-significant omissions, especially collision and ladders. Then construct equivalent section inputs across the five reviewed maps, keeping all sections of each evaluation map out of training.',
        '', '## Limits','']+['- '+x for x in r['limits']]
    (directory/'review.md').write_text('\n'.join(lines)+'\n');print(json.dumps(r),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);run(p.parse_args().directory)
