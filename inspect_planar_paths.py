"""Inspect existing Stage3 candidates; never generates or repairs architecture."""
import argparse,json,math
from pathlib import Path
from shapely.geometry import LineString,Point
from playable_composition import compile_composition,DerivedNavigation
from map_layout import render
from PIL import ImageDraw

def inspect(folder,out,unrestricted=False):
 if out.exists():raise ValueError('Use new diagnostics directory')
 out.mkdir(parents=True);p=json.loads((folder/'composition.json').read_text());v=json.loads((folder/'validation.json').read_text());c=compile_composition(p);geometry=c['visibility_standing'];rows=[];im=render(p,c,v,True);d=ImageDraw.Draw(im);x0,y0,x1,y1=c['envelope'].bounds;scale=1300/max(x1-x0,y1-y0)
 def xy(q):return 150+(q[0]-x0)*scale,1450-(q[1]-y0)*scale
 if unrestricted:
  nav=DerivedNavigation(dict(c,walkable=c['walkable'].buffer(-.5,join_style=2)))
  for row in v['routes'].values():
   path=row.get('unrestricted_path') or nav.path(p['annotations'][row['places'][0]]['point'],p['annotations'][row['places'][-1]]['point'])
   row['path']=dict(points=path['points'],length_HU=path['length']*32) if path else None
  im=render(p,c,v,True);d=ImageDraw.Draw(im)
 for rid in ['T-A-main','T-B-main','CT-rotate']:
  route=v['routes'][rid]['path']
  if route is None:continue
  line=LineString(route['points']);rays=[]
  # Fixed-interval samples avoid tying diagnostics to NAV/route vertex count.
  count=max(3,math.ceil(line.length/8))
  for i in range(count+1):
   t=line.length*i/count;point=line.interpolate(t);before=line.interpolate(max(0,t-.2));after=line.interpolate(min(line.length,t+.2));dx=after.x-before.x;dy=after.y-before.y
   if abs(dx)+abs(dy)<1e-9:continue
   heading=math.atan2(dy,dx)
   for angle in [heading,heading+math.pi]:
    target=[point.x+256*math.cos(angle),point.y+256*math.sin(angle)];cut=LineString([point.coords[0],target]).intersection(geometry)
    parts=list(cut.geoms) if hasattr(cut,'geoms') else [cut];near=[part for part in parts if isinstance(part,LineString) and part.distance(point)<1e-6]
    if not near:continue
    segment=max(near,key=lambda q:q.length);rays.append({'origin':list(point.coords[0]),'endpoint':list(segment.coords[-1]),'length_HU':segment.length*32})
  longest=sorted(rays,key=lambda q:-q['length_HU']);rows.append({'route':rid,'complete_movement_length_HU':route['length_HU'],'maximum_sampled_along_route_planar_ray_HU':longest[0]['length_HU'] if longest else None,'rays':rays})
  # Up to three different origins per route; sampled rays are not maxima proof.
  shown=[]
  for ray in longest:
   if any(Point(ray['origin']).distance(Point(q))<8 for q in shown):continue
   shown.append(ray['origin']);d.line([xy(ray['origin']),xy(ray['endpoint'])],fill='#ec7676',width=3)
   if len(shown)==3:break
 d.rectangle((0,95,1600,145),fill='#101923');d.text((65,100),('UNRESTRICTED shortest movement. ' if unrestricted else 'Ordered intent. ')+'Red: sampled planar rays; declared full-height occlusion only.',fill='#f2aaaa')
 im.save(out/'movement-sightlines.png');result={'seed':p['seed'],'routes':rows,'scope':'Planar sampled standing rays using prototype full-height boundaries and declared low-cover heights. Not calibrated sightline balance, 3D visibility or engine certification. Along-route tangents sampled every about256HU, both directions; no numeric quality score.'};(out/'planar-sightlines.json').write_text(json.dumps(result,indent=2));print(json.dumps([{k:v for k,v in row.items() if k!='rays'} for row in rows]))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--unrestricted',action='store_true');args=ap.parse_args();inspect(args.candidate,args.output,args.unrestricted)
