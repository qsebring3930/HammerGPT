"""Create a reviewable report and geometry slice from a completed face pilot."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def plane_segments(triangles,height,box):
    low=triangles.min(axis=1); high=triangles.max(axis=1)
    keep=(low[:,2]<=height)&(high[:,2]>=height)
    keep&=np.all(high[:,:2]>=box[0],axis=1)&np.all(low[:,:2]<=box[1],axis=1)
    triangles=triangles[keep]; points=np.full((len(triangles),3,2),np.nan)
    count=np.zeros(len(triangles),dtype=int)
    for i in range(3):
        a,b=triangles[:,i],triangles[:,(i+1)%3]
        crosses=((a[:,2]<=height)&(b[:,2]>height))|((b[:,2]<=height)&(a[:,2]>height))
        ids=np.where(crosses)[0]
        fraction=(height-a[ids,2])/(b[ids,2]-a[ids,2])
        points[ids,count[ids]]=a[ids,:2]+fraction[:,None]*(b[ids,:2]-a[ids,:2])
        count[ids]+=1
    return points[count==2,:2]


def build(folder):
    data=json.loads((folder/'features.json').read_text())
    graph=json.loads(Path(data['provenance']['source_graph']).read_text())
    with np.load(folder/'triangles.npz') as archive:triangles=archive['triangles']
    features={n['region_id']:n for n in data['region_features']}
    choices=[n for n in graph['nodes'] if n['label']=='MidDoors'] or graph['nodes']
    selected=max(choices,key=lambda n:len(n['nav_area_ids']))
    sample=features[selected['id']]['sampled_mesh_rays'][0]
    origin=np.asarray(sample['nav_centroid']);height=origin[2]+64
    box=np.asarray([origin[:2]-768,origin[:2]+768]);segments=plane_segments(triangles,height,box)
    image=Image.new('RGB',(1100,1000),'#111925');draw=ImageDraw.Draw(image)
    font=lambda size:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    draw.text((25,18),f'{data["map"]}: native geometry around {selected["label"] or selected["id"]}',font=font(25),fill='#edf2fa')
    draw.text((25,55),f'Mesh slice at z={height:.1f}; sample from NAV area {sample["nav_area_id"]}',font=font(17),fill='#bacbdd')
    def xy(point):return (85+(point[0]-box[0,0])*930/1536,100+(box[1,1]-point[1])*800/1536)
    # Recorded NAV is context. Native walls are sliced at the observation height.
    for polygon in graph['nav_polygons']:
        points=np.asarray(polygon['corners'])
        if abs(points[:,2].mean()-origin[2])>48:continue
        if np.any(points[:,:2].max(axis=0)<box[0]) or np.any(points[:,:2].min(axis=0)>box[1]):continue
        if np.all(points[:,:2].min(axis=0)>=box[0]) and np.all(points[:,:2].max(axis=0)<=box[1]):
            draw.polygon([xy(p) for p in points],fill='#223a4d')
    # Clip each segment and sampled ray to the local view.
    def clipped(a,b):
        a=np.asarray(a,dtype=float)[:2];b=np.asarray(b,dtype=float)[:2];delta=b-a;t0,t1=0.,1.
        for i in range(2):
            if abs(delta[i])<1e-10:
                if not box[0,i]<=a[i]<=box[1,i]:return None
            else:
                lower,upper=sorted(((box[0,i]-a[i])/delta[i],(box[1,i]-a[i])/delta[i]))
                t0=max(t0,lower);t1=min(t1,upper)
                if t0>t1:return None
        return xy(a+t0*delta),xy(a+t1*delta)
    for a,b in segments:
        segment=clipped(a,b)
        if segment:draw.line(segment,fill='#d6e5ee',width=2)
    for ray in sample['rays']:
        direction=np.asarray([math.cos(ray['angle_radians']),math.sin(ray['angle_radians'])])
        segment=clipped(origin[:2],origin[:2]+direction*ray['high_mesh_hit']['distance_units'])
        if segment:draw.line(segment,fill='#efb759',width=2)
    x,y=xy(origin);draw.ellipse((x-6,y-6,x+6,y+6),fill='#ff836b')
    draw.text((25,925),'White: mesh-plane intersections | Gold: 16 sampled mesh-only rays | Blue: nearby NAV',font=font(17),fill='#edf2fa')
    draw.text((25,954),'External model props and collision rules are excluded. This does not establish gameplay visibility.',font=font(16),fill='#edf2fa')
    image.save(folder/'geometry-preview.png')
    probes=data['recorded_transition_geometry_probes'];blocked=sum(p['mesh_hit']['hit_triangle'] is not None for p in probes)
    candidates=sum(n['low_obstacle_candidate_rays'] for n in data['region_features'])
    ref=json.loads(Path(graph['provenance']['vmap_report']).read_text())
    model_entities=Counter(e['classname'] for e in ref['spatial']['entities'] if e['properties'].get('model'))
    summary={'map':data['map'],'regions':len(features),'native_geometry':data['native_geometry_stats'],
             'transition_probes':len(probes),'transition_probes_intersecting_native_faces':blocked,
             'low_obstacle_candidate_rays':candidates,'model_reference_entity_classes_not_expanded':dict(model_entities),
             'preview_region':selected['id'],'preview_nav_area':sample['nav_area_id'],
             'model_training_performed':False,'features_ready_for_verified_collision_or_visibility_labels':False}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Native architectural geometry pilot','',f'Map: {data["map"]}. Approved training data only. No new model training.','',
           f'- Reconstructed {data["native_geometry_stats"]["faces_retained"]:,} native faces as {len(triangles):,} triangles.',
           f'- Added observation features for {len(features)} coarse navigation areas.',
           f'- Tested {len(probes)} recorded transitions with raised-centroid mesh probes; {blocked} intersect native faces.',
           f'- Flagged {candidates} low-obstacle candidate rays. These are geometric hints, not verified cover.',
           '', 'The preview slices actual native mesh faces at one recorded NAV sample height and shows 16 mesh-only rays. Its area was selected by label and NAV polygon count, not by a model accuracy score.',
           '', 'An obstructed straight probe does not invalidate a NAV transition: a route can bend, change height or posture, or involve a nonblocking surface. Unobstructed probes may miss model props. This is an initial geometry representation, not a collision or sightline ground-truth dataset.',
           '', '## Remaining work', '', 'Expand model geometry and evaluate collision/material semantics before producing cover, clearance or gameplay visibility labels. Validate geometry against the supplied NAV. Then review boundary-based region segmentation and apply the verified pipeline to the other approved training maps.',
           '', '## Extraction limits', '']+['- '+s for s in data['limitations']]
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    build(parser.parse_args().folder)
