"""Experimental second Stage3 composition pass; topology stays explicit/frozen.

Jointly relax travel districts and their surrounding masses, then reconstruct
real apertures and revalidate. This is geometry relaxation, not strategic
diversity or a claim that warping repairs an uninteresting strategic graph.
"""
import argparse,copy,json,random,hashlib
from pathlib import Path
import numpy as np
from shapely import set_precision
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union,transform,linemerge
from map_composer import validate
from map_layout import render,SOURCES,write
from playable_composition import compile_composition
from semantic_pipeline import digest
VERSION='district-relaxation-prototype-v1'

def relax(base,spec,seed):
 p=copy.deepcopy(base);r=random.Random(seed);extent=Polygon(p['envelope']).bounds;size=extent[2]
 original=p['decision_log'][-1]['parcels_dimensions'];xs=[0]+original['x']+[size];ys=[0]+original['y']+[size]
 config=dict(seed=seed,x_compression=.94,y_compression=r.choice([.82,.86]),deployment_offset=r.choice([-1,1])*r.uniform(4,7),site_stagger=r.uniform(3,5),precision_plan_units=1e-7)
 def target(x,y):
  # Large architectural districts move together. A floor and all its adjacent
  # building boundaries undergo the same continuous invertible local map.
  # No corridor-specific decorative bend is introduced.
  cx=64;cy=64;blend=max(0,1-abs(x-cx)/64)*max(0,1-abs(y-cy)/64)
  shift=np.interp(y,[0,32,64,100,128],[0,-config['deployment_offset'],config['deployment_offset']/3,config['deployment_offset'],0])
  return [cx+config['x_compression']*(x-cx)+shift*blend,cy+config['y_compression']*(y-cy)+config['site_stagger']*(x-cx)/64*blend]
 triangles=[]
 for x0,x1 in zip(xs,xs[1:]):
  for y0,y1 in zip(ys,ys[1:]):
   for coords in ([(x0,y0),(x1,y0),(x1,y1)],[(x0,y0),(x1,y1),(x0,y1)]):
    matrix=np.array([[x,y,1] for x,y in coords]);affine=np.linalg.solve(matrix,np.array([target(x,y) for x,y in coords]));det=np.linalg.det(affine[:2,:])
    if det<.55:raise ValueError('District deformation folds or excessively compresses a region')
    triangles.append((Polygon(coords),affine))
 mesh=unary_union([tri.boundary for tri,affine in triangles])
 vertices=[q for s in base['spaces'] for ring in [s['boundary']]+s.get('holes',[]) for q in ring]
 cache={}
 def point(q):
  key=tuple(round(float(v),7) for v in q)
  if key in cache:return cache[key]
  for tri,affine in triangles:
   if tri.buffer(1e-7).covers(Point(key)):
    cache[key]=[round(float(v),7) for v in np.array([*key,1])@affine];return cache[key]
  raise ValueError('Point outside deformation domain')
 def shape(g):
  def ring(coords):
   mapped=[]
   for a,b in zip(coords,coords[1:]):
    line=LineString([a,b]);cut=line.intersection(mesh);knots=[a,b]
    def collect(part):
     if hasattr(part,'geoms'):
      for x in part.geoms:collect(x)
     elif not part.is_empty:knots.extend(list(part.coords))
    collect(cut)
    knots.extend(q for q in vertices if line.distance(Point(q))<1e-7 and -1e-7<=line.project(Point(q))<=line.length+1e-7)
    parameters=sorted({round(line.project(Point(q)),8) for q in knots})
    for t in parameters[:-1]:
     q=point(line.interpolate(t).coords[0])
     if not mapped or q!=mapped[-1]:mapped.append(q)
   return mapped
  result=Polygon(ring(list(g.exterior.coords)),[ring(list(h.coords)) for h in g.interiors])
  if not result.is_valid or result.area<=0:raise ValueError('Deformation invalidates an architectural space')
  return result
 spaces={}
 for s in p['spaces']:
  g=shape(Polygon(s['boundary'],s.get('holes',[])));spaces[s['id']]=g;s['boundary']=list(g.exterior.coords)[:-1];s['holes']=[list(r.coords)[:-1] for r in g.interiors]
 for o in p['openings']:
  original_line=LineString(o['aperture']);goal=Point(point(original_line.interpolate(.5,normalized=True).coords[0]));shared=spaces[o['spaces'][0]].boundary.intersection(spaces[o['spaces'][1]].boundary)
  if shared.geom_type=='MultiLineString':shared=linemerge(shared)
  candidates=list(shared.geoms) if hasattr(shared,'geoms') else [shared]
  width=max(spec['hard_constraints']['minimum_door_width_HU']/32,original_line.length)
  end_clearance=p['boundary_thickness']/2
  candidates=[g for g in candidates if isinstance(g,LineString) and g.length>=width+2*end_clearance]
  if not candidates:raise ValueError('Deformed frontage cannot retain aperture width: '+o['id']+'; shared='+str(shared.length)+'; requested='+str(width)+'; type='+shared.geom_type)
  line=min(candidates,key=lambda g:g.distance(goal));t=max(width/2+end_clearance,min(line.length-width/2-end_clearance,line.project(goal)));ap=LineString([line.interpolate(t-width/2),line.interpolate(t+width/2)])
  if ap.length<width-1e-5 or ap.distance(line)>1e-7:raise ValueError('Deformed aperture crosses a boundary turn: '+o['id'])
  o['aperture']=list(ap.coords)
 for s in p['internal_masses']:s['boundary']=list(shape(Polygon(s['boundary'])).exterior.coords)[:-1]
 for a in p['annotations'].values():a['point']=point(a['point'])
 p['defender_positions']={k:point(q) for k,q in p['defender_positions'].items()}
 p['objective_zones']={k:list(shape(Polygon(g)).exterior.coords)[:-1] for k,g in p['objective_zones'].items()}
 p['physical_route_waypoints']={k:[point(q) for q in points] for k,points in p['physical_route_waypoints'].items()}
 for key in ('architectural_buildings','building_footprints'):
  for s in p.get(key,[]):s['boundary']=list(shape(Polygon(s['boundary'])).exterior.coords)[:-1]
 p['geometric_precision_plan_units']=config['precision_plan_units'];p['second_spatial_pass']=dict(version=VERSION,configuration=config,base_sha256=digest(base),scope='Joint district compression and offset; topology preserved. Not automatic invention of new strategic organization.')
 p['decision_log'].insert(-1,dict(stage='district_relaxation',**p['second_spatial_pass']))
 return p

def run(folder,out,seed,limit):
 if out.exists():raise ValueError('Preserve previous outputs; use a fresh output directory')
 out.mkdir(parents=True);base=json.loads((folder/'composition.json').read_text());spec=json.loads((folder/'resolved-specification.json').read_text());write(out/'base-composition.json',base);write(out/'specification.json',spec)
 frozen=out/'source';frozen.mkdir();hashes={}
 for name in SOURCES+['organify_layout.py']:
  data=(Path(__file__).resolve().parent/name).read_bytes();(frozen/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
 write(out/'manifest.json',dict(version=VERSION,source_candidate=str(folder),seed=seed,attempt_limit=limit,source_hashes=hashes,stage4_paused=True))
 records=[];selected=None
 for i in range(limit):
  directory=out/f'attempt-{i+1:02d}';directory.mkdir();p=None
  try:
   p=relax(base,spec,seed+i);write(directory/'composition.json',p);c=compile_composition(p);v=validate(spec,p,c);write(directory/'validation.json',v);render(p,c,v).save(directory/'clean.png');render(p,c,v,True).save(directory/'encounters.png');passed=v['physical_pass'] and v['request_pass'];reasons=v['physical_violations']+v['adherence_violations'];status='candidate_for_review' if passed else 'rejected_validation'
  except ValueError as e:passed=False;reasons=[str(e)];status='rejected_construction'
  record=dict(attempt=i+1,seed=seed+i,status=status,reasons=reasons);records.append(record);write(directory/'attempt.json',record)
  if passed:
   selected=seed+i;write(out/'composition.json',p);write(out/'validation.json',v);render(p,c,v).save(out/'clean.png');render(p,c,v,True).save(out/'encounters.png');write(out/'reproduction.json',dict(matches=digest(relax(base,spec,seed+i))==digest(p),composition_sha256=digest(p)));break
 write(out/'summary.json',dict(attempts=records,selected_seed=selected,stage4_paused=True));print(json.dumps(records))
 if selected is None:raise ValueError('Bounded second-pass experiment failed; all attempts preserved')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seed',type=int,required=True);ap.add_argument('--attempt-limit',type=int,default=3);a=ap.parse_args();run(a.candidate,a.output,a.seed,a.attempt_limit)
