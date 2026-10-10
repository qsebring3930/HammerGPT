"""Review native faces, expanded model render geometry, and changed observations."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageFont

from architecture_report import plane_segments


def build(native_folder,model_folder,observations_folder):
    native=json.loads((native_folder/'features.json').read_text());models=json.loads((model_folder/'instances.json').read_text())
    observations=json.loads((observations_folder/'features.json').read_text());graph=json.loads(Path(native['provenance']['source_graph']).read_text())
    node=max((n for n in graph['nodes'] if n['label']=='MidDoors'),key=lambda n:len(n['nav_area_ids']))
    features=next(n for n in observations['region_features'] if n['region_id']==node['id']);sample=features['sampled_mesh_rays'][0]
    origin=np.asarray(sample['nav_centroid']);box=np.asarray([origin[:2]-768,origin[:2]+768]);height=origin[2]+64
    with np.load(native_folder/'triangles.npz') as a:native_segments=plane_segments(a['triangles'],height,box)
    with np.load(model_folder/'render-triangles.npz') as a:model_segments=plane_segments(a['triangles'],height,box)
    image=Image.new('RGB',(1100,1000),'#111925');draw=ImageDraw.Draw(image);font=lambda n:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n)
    draw.text((25,18),'Dust2: native meshes + expanded static-prop render geometry',font=font(24),fill='#edf2fa')
    draw.text((25,55),f'MidDoors | NAV sample {sample["nav_area_id"]} | slice at z={height:.1f}',font=font(17),fill='#bacbdd')
    def xy(p):return 85+(p[0]-box[0,0])*930/1536,100+(box[1,1]-p[1])*800/1536
    def segment(a,b):
        a=np.asarray(a)[:2];b=np.asarray(b)[:2];delta=b-a;t0,t1=0.,1.
        for i in range(2):
            if abs(delta[i])<1e-10:
                if not box[0,i]<=a[i]<=box[1,i]:return None
            else:
                lower,upper=sorted(((box[0,i]-a[i])/delta[i],(box[1,i]-a[i])/delta[i]));t0=max(t0,lower);t1=min(t1,upper)
                if t0>t1:return None
        return xy(a+t0*delta),xy(a+t1*delta)
    for segments,color in ((native_segments,'#697d8f'),(model_segments,'#72d3e6')):
        for a,b in segments:
            clipped=segment(a,b)
            if clipped:draw.line(clipped,fill=color,width=1)
    for ray in sample['rays']:
        direction=np.asarray([math.cos(ray['angle_radians']),math.sin(ray['angle_radians'])]);hit=ray['high_mesh_hit']
        for distance,color in ((hit['native_hit']['distance_units'],'#bc8547'),(hit['distance_units'],'#a3e388')):
            clipped=segment(origin[:2],origin[:2]+direction*distance)
            if clipped:draw.line(clipped,fill=color,width=2)
    x,y=xy(origin);draw.ellipse((x-6,y-6,x+6,y+6),fill='#ff836b')
    draw.text((25,925),'Gray: native mesh slice | Cyan: added model slice | Gold/green: native/model-aware rays',font=font(16),fill='#edf2fa')
    draw.text((25,954),'Render geometry only. Collision, opacity and agreement with compiled physics remain unverified.',font=font(16),fill='#edf2fa')
    image.save(observations_folder/'geometry-preview.png')
    s=models['summary'];r=observations['summary']
    lines=['# Static-prop geometry expansion','','Approved Dust2 pilot. No new model training.','',
           f'- Expanded {s["status_counts"].get("expanded_render_geometry",0):,}/{s["instances"]:,} static-prop instances.',
           f'- Added {s["render_triangles"]:,} render triangles from {s["unique_dmx"]} shared DMX sources.',
           f'- Counted and omitted {s["unique_source_degenerate_faces_omitted"]:,} zero-area source faces.',
           f'- {r["rays_shortened_by_props"]:,}/{r["sampled_rays"]:,} sampled rays now hit a nearer render surface.',
           f'- {r["transition_probes_with_nearer_prop_hit"]}/{r["transition_probes"]} transition probes hit a nearer prop surface.',
           '', 'Import filters select the requested submeshes. Descriptor translations are applied before exact map-instance scale, rotation and translation. Successful cached inputs are source-hash checked and resume provenance is recorded.',
           '', '## Collision coverage', '', 'All static prop entity collision settings were recorded. The decompiled source descriptors supply render meshes without authored physics meshes. An installed compiled Dust2 world-physics model was CRC-verified and audited with ValveResourceFormat; it contains a PhysAggregateData block. That compiled map has not been verified against the repaired VMAP or supplied NAV, so it is not treated as collision ground truth.',
           '', '## Next step', '', 'Extract the compiled collision shapes with their attributes and test alignment against the repaired geometry/NAV before producing clearance, cover or visibility labels. Render-model intersections can include transparent or nonblocking surfaces. Animated/nonstatic entities, prefabs, material overrides and opacity remain outside this pilot.']
    (observations_folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--models',type=Path,required=True);parser.add_argument('--observations',type=Path,required=True)
    args=parser.parse_args();build(args.native,args.models,args.observations)
