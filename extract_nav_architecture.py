"""Conservative local NAV support aggregation; NAV boundaries are never walls."""
import argparse,json,hashlib,math
from pathlib import Path
from collections import Counter
import networkx as nx
import numpy as np
from shapely.geometry import Polygon,LineString,Point,mapping
from shapely.ops import unary_union
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parent
SELECTION={'dust2':['LongDoors','OutsideLong','LongA'],'cache':['BMain','Checkers','BombsiteB'],'train':['Ivy','BombsiteA','TMain']}
VERSION='conservative-nav-support-v1.1-mean-metadata'

def portal(a,b,connection,tol=.05):
 # Matching indexed edge spans, including interpolated Z. This does not certify
 # collision or engine traversal: per-connection traversal type is not exported.
 i,j=connection['source_edge'],connection['target_edge']
 if not (0<=i<len(a['corners']) and 0<=j<len(b['corners'])):return None
 p,q=np.array(a['corners'][i],float),np.array(a['corners'][(i+1)%len(a['corners'])],float)
 u,v=np.array(b['corners'][j],float),np.array(b['corners'][(j+1)%len(b['corners'])],float)
 axis=q[:2]-p[:2];length=np.linalg.norm(axis)
 if length<tol:return None
 axis/=length
 if max(abs(axis[0]*(u[1]-p[1])-axis[1]*(u[0]-p[0])),abs(axis[0]*(v[1]-p[1])-axis[1]*(v[0]-p[0])))>tol:return None
 t0,t1=np.dot(u[:2]-p[:2],axis),np.dot(v[:2]-p[:2],axis);lo,hi=max(0,min(t0,t1)),min(length,max(t0,t1))
 if hi-lo<=tol:return None
 zs=[]
 for t in [lo,hi]:
  za=p[2]+(q[2]-p[2])*t/length;zb=u[2]+(v[2]-u[2])*(t-t0)/(t1-t0)
  if abs(za-zb)>tol:return None
  zs.append((za+zb)/2)
 return {'span':[(p[:2]+axis*lo).tolist(),(p[:2]+axis*hi).tolist()],'z_endpoints':zs,'width_native':float(hi-lo),'confidence':'medium: reciprocal static zero-flag shared 3D support, not certified runtime walkability'}

def eligible(area):return area['hull']==0 and area['movable_mesh_id']==4294967295 and area['flags']==0 and not (area['ladders_above'] or area['ladders_below'])

def support_graph(nav):
 areas={a['id']:a for a in nav['areas'] if eligible(a) and Polygon([p[:2] for p in a['corners']]).is_valid}
 g=nx.Graph();g.add_nodes_from(areas);centers={k:np.mean(a['corners'],axis=0).tolist() for k,a in areas.items()};excluded=Counter()
 for k,a in areas.items():
  for c in a['connections']:
   t=c['target']
   if t not in areas:excluded['target outside eligible subset']+=1;continue
   reverse=[x for x in areas[t]['connections'] if x['target']==k]
   if not reverse:excluded['one-way unverified traversal']+=1;continue
   p=portal(a,areas[t],c)
   if p is None or not any(portal(areas[t],a,r) is not None for r in reverse):excluded['nonmatching geometric/elevation portal']+=1;continue
   middle=np.mean(p['span'],axis=0)
   length=np.linalg.norm(np.array(centers[k])[:2]-middle)+np.linalg.norm(np.array(centers[t])[:2]-middle)
   g.add_edge(k,t,**p,weight=float(length))
 return areas,g,centers,dict(excluded)

def aggregate(areas,g,labels,wanted):
 remaining={k for k in areas if labels.get(k) in wanted};groups=[]
 while remaining:
  seed=min(remaining);members={seed};remaining.remove(seed);low=high=float(np.mean([p[2] for p in areas[seed]['corners']]));queue=[seed]
  while queue:
   node=queue.pop(0)
   for q in sorted(g.neighbors(node)):
    if q not in remaining or labels.get(q)!=labels.get(seed):continue
    z=float(np.mean([p[2] for p in areas[q]['corners']]))
    # Local level tolerance is an authored extraction parameter. Preserve the
    # original 3D areas and group height range; never connect stacked XY floors.
    if max(high,z)-min(low,z)>16:continue
    if max(p[2] for p in areas[q]['corners'])-min(p[2] for p in areas[q]['corners'])>16:continue
    remaining.remove(q);members.add(q);queue.append(q);low=min(low,z);high=max(high,z)
  shape=unary_union([Polygon([p[:2] for p in areas[k]['corners']]) for k in sorted(members)])
  groups.append({'id':'space-'+str(len(groups)),'place_context':labels.get(seed),'area_ids':sorted(members),'mean_elevation_range_native':[low,high],'support_geometry':mapping(shape),'confidence':'medium; connected same-place/compatible-level NAV support, not an architectural room','shape':shape})
 return groups

def smooth(points,support):
 # Remove tessellation wobble only when the replacement stays in NAV support.
 result=[points[0]];i=0
 while i<len(points)-1:
  j=len(points)-1
  while j>i+1 and not support.buffer(.05).covers(LineString([points[i],points[j]])):j-=1
  result.append(points[j]);i=j
 return result

def widths(line,support):
 out=[]
 for f in np.linspace(.05,.95,19):
  t=line.length*f;point=line.interpolate(t);a=line.interpolate(max(0,t-1));b=line.interpolate(min(line.length,t+1));v=np.array(b.coords[0])-a.coords[0];length=np.linalg.norm(v)
  if length<1e-6:continue
  normal=np.array([-v[1],v[0]])/length;xy=np.array(point.coords[0]);cross=LineString([xy-normal*10000,xy+normal*10000]).intersection(support)
  parts=list(cross.geoms) if hasattr(cross,'geoms') else [cross]
  containing=[p for p in parts if isinstance(p,LineString) and p.distance(point)<.05]
  if containing:
   width=float(max(p.length for p in containing));margin=float(point.distance(support.boundary))
   out.append({'point':xy.tolist(),'width_native':width,'boundary_margin_native':margin,'stable_for_ratios':margin>=max(1,width*.1)})
 return out

def extract(name,out):
 nf=ROOT/f'output/{name}-nav.json';gf=ROOT/f'output/{name}-connections.json';nav=json.loads(nf.read_text());prior=json.loads(gf.read_text());labels={k:n['label'] for n in prior['nodes'] for k in n['nav_area_ids']}
 areas,g,centers,excluded=support_graph(nav);groups=aggregate(areas,g,labels,SELECTION[name]);patterns=[]
 for group in sorted(groups,key=lambda x:-len(x['area_ids']))[:6]:
  sub=g.subgraph(group['area_ids']);component=max(nx.connected_components(sub),key=len);sub=sub.subgraph(component)
  if len(sub)<3:continue
  s=min(sub);initial=nx.single_source_dijkstra_path_length(sub,s,weight='weight');start=max(initial,key=initial.get);dist=nx.single_source_dijkstra_path_length(sub,start,weight='weight');end=max(dist,key=dist.get);nodes=nx.shortest_path(sub,start,end,weight='weight')
  raw=[centers[nodes[0]][:2]]
  for a,b in zip(nodes,nodes[1:]):raw.extend([np.mean(g[a][b]['span'],axis=0).tolist(),centers[b][:2]])
  shape=group['shape'];points=smooth(raw,shape);line=LineString(points);samples=widths(line,shape);angles=[]
  for a,b,c in zip(points,points[1:],points[2:]):
   u=np.array(b)-a;v=np.array(c)-b
   if np.linalg.norm(u)*np.linalg.norm(v)>0:angles.append(float(math.degrees(math.acos(np.clip(np.dot(u,v)/(np.linalg.norm(u)*np.linalg.norm(v)),-1,1)))))
  alt=None
  # Alternate paths are geometry-checked navigation choices, not tactical novelty.
  if len(nodes)>3:
   h=sub.copy();h.remove_edge(nodes[len(nodes)//2-1],nodes[len(nodes)//2])
   try:alternative=nx.shortest_path(h,start,end,weight='weight');alt={'area_ids':alternative,'different_support':len(set(alternative)-set(nodes)),'scope':'May be tessellation-equivalent; not credited as a strategic route.'}
   except nx.NetworkXNoPath:pass
  patterns.append({'id':name+'-'+group['id'],'space_id':group['id'],'area_ids':nodes,'points':points,'centerline_support_length_native':line.length,'width_samples':samples,'width_transition_ratio':max(x['width_native'] for x in samples if x['stable_for_ratios'])/min(x['width_native'] for x in samples if x['stable_for_ratios']) if any(x['stable_for_ratios'] for x in samples) else None,'direction_changes_degrees':angles,'elevation_centers_native':[centers[k][2] for k in nodes],'alternative':alt,'support_valid':shape.buffer(.05).covers(line),'confidence':'medium for observed supported planar route; no calibrated timing, wall or doorway interpretation'})
 result={'version':VERSION,'map':name,'provenance':{'nav_export':str(nf.relative_to(ROOT)),'sha256':hashlib.sha256(nf.read_bytes()).hexdigest(),'map_identity_basis':nav['source'],'place_context_export':str(gf.relative_to(ROOT)),'place_context_sha256':hashlib.sha256(gf.read_bytes()).hexdigest(),'parser':nav['parser'],'version':nav['version']},'original_areas':[areas[k] for k in sorted({k for group in groups for k in group['area_ids']})],'selection_place_context':SELECTION[name],'eligible_area_count':len(areas),'excluded_connections':excluded,'spaces':[{k:v for k,v in group.items() if k!='shape'} for group in groups],'movement_patterns':patterns,'aggregation_parameters':{'median_elevation_span_native':16,'portal_matching_tolerance_native':.05,'hull':0,'flags':0,'static_mesh_sentinel':4294967295},'uncertainty':['NAV support boundary is not a wall or a collision contour','No radar-to-NAV registration','Place labels come from earlier source VMAP volume associations; freshness unverified','Level grouping preserves original XYZ and never infers crossing-floor links','Wide-to-narrow support ratios are not physical doorway widths']}
 (out/(name+'.json')).write_text(json.dumps(result,indent=2));render(name,areas,groups,patterns,out)
 return result

def render(name,areas,groups,patterns,out):
 support=unary_union([x['shape'] for x in groups]);x0,y0,x1,y1=support.bounds;scale=700/max(x1-x0,y1-y0);im=Image.new('RGB',(2400,930),'#101923');d=ImageDraw.Draw(im)
 def xy(p,panel):return panel*800+50+(p[0]-x0)*scale,840-(p[1]-y0)*scale
 def poly(g,panel,color,outline=None):
  if hasattr(g,'geoms'):
   for part in g.geoms:poly(part,panel,color,outline)
  elif isinstance(g,Polygon):
   pts=[xy(q,panel) for q in g.exterior.coords];d.polygon(pts,fill=color)
   if outline:d.line(pts+[pts[0]],fill=outline,width=1)
   for ring in g.interiors:d.polygon([xy(q,panel) for q in ring.coords],fill='#101923')
 colors=['#7599a7','#a5ac84','#9b86a7','#91bfae','#b18d7c','#7b93bd']
 for group in groups:
  for k in group['area_ids']:poly(Polygon([p[:2] for p in areas[k]['corners']]),0,'#527083','#a4bdc7')
  poly(group['shape'],1,colors[int(group['id'].split('-')[1])%len(colors)]);poly(group['shape'],2,'#527083')
 for pattern in patterns:
  if len(pattern['points'])>1:d.line([xy(q,2) for q in pattern['points']],fill='#f4bf68',width=3)
  for s in pattern['width_samples'][::3]:
   x,y=xy(s['point'],2);d.ellipse((x-3,y-3,x+3,y+3),fill='#ceecb0')
 for panel,title in enumerate(['Original NAV subdivisions','Aggregated compatible-level support','Supported centerlines / width samples']):d.text((panel*800+25,25),name+' / '+title,fill='white');d.text((panel*800+25,870),'Native XYZ; boundaries are NAV support, not walls. Levels/colors are not rooms.',fill='#afc5cf')
 im.save(out/(name+'-overlay.png'))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 if args.output.exists():raise ValueError('Use new output directory')
 args.output.mkdir(parents=True);results=[extract(name,args.output) for name in SELECTION]
 (args.output/'summary.json').write_text(json.dumps([{'map':r['map'],'spaces':len(r['spaces']),'patterns':len(r['movement_patterns']),'excluded':r['excluded_connections']} for r in results],indent=2))
 print((args.output/'summary.json').read_text())
if __name__=='__main__':main()
