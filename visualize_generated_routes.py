"""Readable route view of a fixed generated sample; never changes its graph."""
import json
from pathlib import Path
import numpy as np
from scipy.sparse.csgraph import dijkstra
from PIL import Image,ImageDraw,ImageFont


def main():
    root=Path(__file__).resolve().parent;folder=root/'output/training/progressive-layout-v2'
    s=json.loads((folder/'samples.json').read_text())[0]
    x=np.asarray(s['descriptors']);roles=np.asarray(s['roles']);a=np.asarray(s['adjacency'])
    lengths=np.linalg.norm(x[:,None,:3]-x[None,:,:3],axis=-1)
    distance,predecessor=dijkstra(np.maximum(lengths,1e-6)*a,directed=True,return_predecessors=True)
    names=('T','CT','A','B');groups={n:np.flatnonzero(roles&(1<<i)) for i,n in enumerate(names)}
    routes=[]
    for start,target in [('T','A'),('T','B'),('CT','A'),('CT','B')]:
        choices=[(float(distance[u,v]),int(u),int(v)) for u in groups[start] for v in groups[target] if np.isfinite(distance[u,v])]
        if not choices:routes.append({'name':f'{start} to {target}','path':[]});continue
        cost,u,v=min(choices);path=[v]
        while path[-1]!=u:path.append(int(predecessor[u,path[-1]]))
        routes.append({'name':f'{start} to {target}','path':path[::-1],'normalized_distance':cost})
    (folder/'readable-routes.json').write_text(json.dumps({'seed':s['seed'],'routes':routes,'selection':'first fixed sample, shortest directed geometric route to any matching role; not tactical opening classification','graph_modified':False},indent=2))
    image=Image.new('RGB',(1800,1200),'#101a26');p=ImageDraw.Draw(image);font=lambda n:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n)
    p.text((35,25),'A readable look at the generated layout',font=font(34),fill='#f2f6fa')
    p.text((35,73),'First fixed sample (7100). The model chose every area position and connection.',font=font(21),fill='#c2ced8')
    colors=['#f5af45','#e66e39','#48bed8','#718efa']
    included=set(i for r in routes for i in r['path'])|set(i for g in groups.values() for i in g)
    positions=x[:,:2];lo=positions[list(included)].min(0)-.09;hi=positions[list(included)].max(0)+.09
    def xy(i):return 65+(positions[i,0]-lo[0])/(hi[0]-lo[0])*1100,170+(hi[1]-positions[i,1])/(hi[1]-lo[1])*790
    p.rounded_rectangle((35,130,1230,1030),radius=16,fill='#172635',outline='#334a5b',width=2)
    # Context is dots only so unrelated edge clutter doesn't obscure the four routes.
    for i in range(len(x)):
        if np.all(positions[i]>=lo) and np.all(positions[i]<=hi):
            px,py=xy(i);p.ellipse((px-2,py-2,px+2,py+2),fill='#3e5264')
    edges={tuple(sorted((u,v))) for r in routes for u,v in zip(r['path'],r['path'][1:])}
    for u,v in edges:p.line([xy(u),xy(v)],fill='#35495a',width=28)
    for i in included:
        px,py=xy(i);p.ellipse((px-14,py-14,px+14,py+14),fill='#4b6479',outline='#8aa3b6',width=2)
    # Offset parallel highlights preserve shared links rather than merge their route identities.
    for k,r in enumerate(routes):
        for u,v in zip(r['path'],r['path'][1:]):
            start=np.asarray(xy(u));end=np.asarray(xy(v));delta=end-start;perp=np.array([-delta[1],delta[0]])/max(np.linalg.norm(delta),1)
            offset=perp*(k-1.5)*4;p.line([tuple(start+offset),tuple(end+offset)],fill=colors[k],width=4)
            at=start*.35+end*.65+offset;direction=delta/max(np.linalg.norm(delta),1)
            p.polygon([tuple(at+direction*7),tuple(at-direction*5+perp*4),tuple(at-direction*5-perp*4)],fill=colors[k])
    for name,g in groups.items():
        for number,i in enumerate(g,1):
            px,py=xy(i);color='#f2ac45' if name=='T' else '#60bcd9' if name=='CT' else '#acdda1'
            radius=23 if name in ('T','CT') else 18
            p.ellipse((px-radius,py-radius,px+radius,py+radius),fill=color,outline='#101a26',width=3)
            label=name if len(g)==1 else f'{name}{number}'
            p.rounded_rectangle((px-27,py-57,px+48,py-27),radius=5,fill='#101a26')
            p.text((px-20,py-55),label,font=font(22),fill=color)
    sx=1270;p.text((sx,145),'How to read this',font=font(27),fill='white')
    lines=['T = attacker spawn','CT = defender spawn','A / B = site-marked regions','','Circles: generated areas','Bands: existing graph connections','Arrows: route direction','Faint dots: other generated areas']
    for k,line in enumerate(lines):p.text((sx,195+k*35),line,font=font(20),fill='#c9d5df')
    p.text((sx,505),'Four shortest access routes',font=font(25),fill='white')
    for k,r in enumerate(routes):
        yy=555+k*70;p.line([(sx,yy+12),(sx+36,yy+12)],fill=colors[k],width=5)
        p.text((sx+50,yy),r['name'],font=font(23),fill=colors[k])
        p.text((sx+50,yy+29),f"{max(len(r['path'])-1,0)} connections" if r['path'] else 'No directed path',font=font(17),fill='#c9d5df')
    for k,line in enumerate(['A1/A2 and B1-B4 reveal repeated','site labels in the model output.','They are not extra intended bombsites.','','Only these routes are highlighted.','Other links are still in the saved graph.']):
        p.text((sx,865+k*27),line,font=font(17),fill='#c9d5df')
    p.text((35,1065),'This is a route sketch, not a Hammer floor plan.',font=font(27),fill='#f5bf69')
    p.text((35,1110),'Circle sizes and band widths are display choices. Room shapes, corridor widths and walkability have not been generated.',font=font(20),fill='#c2ced8')
    image.save(folder/'readable-overview.png')
    print(json.dumps(routes))


if __name__=='__main__':main()
