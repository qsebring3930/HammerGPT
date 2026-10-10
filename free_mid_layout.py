"""One continuous-space Stage3 feasibility attempt, no reservation-grid fallback.

Uses an existing typed strategy, discards its spatial coordinates and footprints.
Degree-two route subdivisions become continuous streets, not individual rooms.
"""
import argparse,copy,json,math,random,hashlib
from pathlib import Path
import numpy as np
import networkx as nx
from shapely import set_precision
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union,linemerge
from shapely.affinity import rotate,translate
from map_layout import render,write,SOURCES,font
from map_composer import validate
from playable_composition import compile_composition
from semantic_pipeline import digest
VERSION='free-network-composition-feasibility-v2'

def route_architecture(route,positions,net,roles,obstacles=None):
 """Continuous lanes with purposeful side courts, not a room per NAV/node.

 Only preparation/transfer locations and one investment location on a long
 main route widen. The central movement line remains continuous. These are
 authored assemblies informed by the existing reference observations, not
 copied NAV rooms or new tactical connections.
 """
 line=LineString([positions[n] for n in route]);floor=line.buffer(4.5,cap_style=2,join_style=2);episodes=[]
 purposes={}
 for site in ('A','B'):
  main=net['T-'+site+'-main'];alt=net['Mid-'+site]
  purposes[main[-2]]='execute preparation'
  purposes.setdefault(alt[-3],'connector transfer')
  if len(main)>4:purposes.setdefault(main[len(main)//2],'attacker staging')
 for j,n in enumerate(route[1:-1],1):
  if n not in purposes:continue
  before,after=np.array(positions[route[j-1]]),np.array(positions[route[j+1]])
  direction=after-before;direction/=np.linalg.norm(direction);normal=np.array([-direction[1],direction[0]])
  # Offset the holding court towards the inside of the architectural turn.
  incoming=np.array(positions[n])-before;outgoing=after-np.array(positions[n]);side=1 if incoming[0]*outgoing[1]-incoming[1]*outgoing[0]>=0 else -1
  angle=math.degrees(math.atan2(direction[1],direction[0]));court=None
  for chosen_side in (side,-side):
   center=np.array(positions[n])+normal*chosen_side*2
   candidate=translate(rotate(box(-6,-5.5,6,5.5),angle,origin=(0,0)),*center)
   if obstacles is not None and candidate.intersects(obstacles):continue
   court=candidate;side=chosen_side;break
  if court is None:
   episodes.append(dict(node=list(n),purpose=purposes[n],placed=False,reason='No whole preparation court fits without compromising another commitment'));continue
  floor=floor.union(court)
  episodes.append(dict(node=list(n),purpose=purposes[n],placed=True,boundary=list(court.exterior.coords)[:-1],center=list(center),side=side))
 return floor,episodes

def generate(base,spec,seed):
 p=copy.deepcopy(base);graph=nx.Graph();net={k:[tuple(q) for q in route] for k,route in base['strategic_network'].items()}
 for route in net.values():graph.add_edges_from(zip(route,route[1:]))
 roles={k:tuple(q) for k,q in base['decision_log'][-1]['role_cells'].items()};anchors=set(roles.values())|{n for n in graph if graph.degree(n)!=2}
 # The topology is retained; no original cell geometry is used. Free initial
 # placement and relaxation are continuous and not tied to cardinal directions.
 raw=nx.spring_layout(graph,seed=seed,iterations=700,scale=1)
 nodes=list(graph);points=np.array([raw[n] for n in nodes])*43
 radius=np.array([10 if n in (roles['A'],roles['B']) else 8 if n in anchors else 4.5 for n in nodes])
 for iteration in range(160):
  changes=np.zeros_like(points)
  for i in range(len(nodes)):
   for j in range(i):
    v=points[i]-points[j];dist=np.linalg.norm(v);required=radius[i]+radius[j]+1.2
    if dist<required:
     move=v/max(dist,.001)*(required-dist)*.15;changes[i]+=move;changes[j]-=move
  # Site separation is a request constraint, not an exterior-edge placement.
  ia,ib=nodes.index(roles['A']),nodes.index(roles['B']);v=points[ia]-points[ib];dist=np.linalg.norm(v);desired=74 if spec['architecture']['site_separation']=='separated' else 50
  if dist<desired:
   move=v/max(dist,.001)*(desired-dist)*.12;changes[ia]+=move;changes[ib]-=move
  points+=changes
 extent=np.max(np.ptp(points,axis=0));points*=min(1,89/extent);points+=np.array([64,64])-points.mean(axis=0)
 positions={n:list(points[i]) for i,n in enumerate(nodes)};precision=1e-7;cores={}
 for n in sorted(anchors):
  name=next((k for k,q in roles.items() if q==n),None);x,y=positions[n]
  neighbor=max(graph[n],key=lambda q:np.linalg.norm(np.array(positions[q])-points[nodes.index(n)]));q=positions[neighbor];angle=math.degrees(math.atan2(q[1]-y,q[0]-x))
  # A three-way deployment is a circulation court: enough frontage for its
  # independent assignments, rather than a narrow endpoint rectangle.
  width,depth=(18,16) if name in ('A','B') else (18,14) if name in ('T','CT') else (15,11) if name in ('Mid','Mid2') else (12,10)
  core=set_precision(translate(rotate(box(-width/2,-depth/2,width/2,depth/2),angle,origin=(0,0)),x,y),precision);cores[n]=core
 chains=[];visited=set()
 for start in sorted(anchors):
  for first in sorted(graph[start]):
   edge=tuple(sorted((start,first)))
   if edge in visited:continue
   route=[start,first];visited.add(edge)
   while route[-1] not in anchors:
    previous,current=route[-2:];n=next(q for q in graph[current] if q!=previous);visited.add(tuple(sorted((current,n))));route.append(n)
   chains.append(route)
 # Deployment and branch complexes include the actual confluence of their
 # incident lanes. A fixed rectangle must not leave a second, undeclared
 # junction just beyond its wall. Unrelated route crossings are not merged.
 reserved_lanes=[LineString([positions[n] for n in route]).buffer(4.5,cap_style=2,join_style=2) for route in chains]
 for n in sorted(anchors):
  incident=[i for i,route in enumerate(chains) if n in (route[0],route[-1])]
  patches=[reserved_lanes[i].intersection(reserved_lanes[j]) for index,i in enumerate(incident) for j in incident[:index]]
  patches=[q.buffer(.8,join_style=2) for q in patches if not q.is_empty]
  if patches:
   grown=unary_union([cores[n]]+patches)
   if grown.geom_type!='Polygon':raise ValueError('Incident lanes intersect away from their declared junction')
   # One coherent building/court footprint around the confluence, rather than
   # tiny jagged perimeter fragments left by overlapping corridor buffers.
   # Remove sub-precision collinear hull vertices before constructing the
   # common boundaries. These are rounding artifacts, not real corners.
   cores[n]=grown.convex_hull.simplify(precision,preserve_topology=True)
  name=next((k for k,q in roles.items() if q==n),None)
  if name in ('Mid','Mid2') or name is None:
   # Circulation courts have actual flat frontages normal to each incoming
   # lane. Compose the enclosing building faces from those ingress axes;
   # a rotated rectangle can split a usable mouth across two short corners.
   center=np.array(positions[n]);court=translate(box(-18,-18,18,18),*center)
   confluence=unary_union([reserved_lanes[i].intersection(reserved_lanes[j]) for index,i in enumerate(incident) for j in incident[:index]])
   confluence_parts=list(confluence.geoms) if hasattr(confluence,'geoms') else [confluence]
   confluence_points=[np.array(q) for part in confluence_parts if isinstance(part,Polygon) for q in part.exterior.coords]
   for i in incident:
    route=chains[i];neighbor=route[1] if route[0]==n else route[-2]
    u=np.array(positions[neighbor])-center;u/=np.linalg.norm(u);v=np.array([-u[1],u[0]])
    reach=max([6.5]+[float(np.dot(point-center,u))+.8 for point in confluence_points]);q=center+u*reach
    halfplane=Polygon([q+v*100,q-v*100,q-v*100-u*200,q+v*100-u*200])
    court=court.intersection(halfplane)
   cores[n]=court
 # Compose adjacent complexes together: reserve a continuous circulation
 # gap between their territories. Unused court corners must not overlap an
 # unrelated complex. This changes footprints, never the acceptance gates.
 territories=dict(cores)
 for n in sorted(anchors):
  center=np.array(positions[n]);court=cores[n]
  for other in sorted(anchors):
   if other==n:continue
   # Do not clip already disjoint complexes: that would cut an intended
   # deployment confluence merely because another court is nearby.
   if not territories[n].intersects(territories[other]):continue
   delta=np.array(positions[other])-center;distance=np.linalg.norm(delta);u=delta/distance;v=np.array([-u[1],u[0]]);q=center+u*(distance/2-1.5)
   halfplane=Polygon([q+v*200,q-v*200,q-v*200-u*400,q+v*200-u*400]);court=court.intersection(halfplane)
  if court.geom_type!='Polygon':raise ValueError('No coherent territory remains for a required complex')
  cores[n]=court
 # Coordinates are already fixed. Clear attached GEOS precision metadata
 # before subtraction so intersections use these exact shared edges instead
 # of independently rounding a new intersection back into an existing core.
 cores={n:set_precision(g,0) for n,g in cores.items()}
 core_union=unary_union(list(cores.values()))
 p.update(candidate='free-mid-'+str(seed),seed=seed,generator_version=VERSION,geometric_precision_plan_units=precision,spaces=[],openings=[],internal_masses=[],annotations={},objective_zones={},defender_positions={},space_program={},architectural_buildings=[],building_footprints=[])
 p['free_node_positions']={str(n):q for n,q in positions.items()};node_spaces={};shapes={};edge_spaces={}
 def add(sid,g,kind,purpose):
  if g.geom_type!='Polygon':raise ValueError('Free composition produced split space: '+sid)
  shapes[sid]=g;p['spaces'].append(dict(id=sid,boundary=list(g.exterior.coords)[:-1],holes=[list(h.coords)[:-1] for h in g.interiors],kind=kind,purpose=purpose));p['space_program'][sid]=dict(kind=kind,purpose=purpose)
 for n,g in cores.items():
  name=next((k for k,q in roles.items() if q==n),None);sid=name+'_objective' if name in ('A','B') else 'free_'+str(n[0])+'_'+str(n[1]);kind='courtyard' if name in ('A','B','Mid','Mid2') else 'deployment' if name in ('T','CT') else 'circulation'
  add(sid,g,kind,'Deployment/objective/contest complex' if name else 'Actual circulation branch junction');node_spaces[n]=[(sid,g)]
 p['approach_episodes']=[]
 for i,route in enumerate(chains):
  obstacles=unary_union([lane.buffer(.8) for j,lane in enumerate(reserved_lanes) if j!=i]+[core for n,core in cores.items() if n not in route])
  gross,episodes=route_architecture(route,positions,net,roles,obstacles)
  # Subtract already quantized cores LAST. Snapping a subtracted boundary
  # afterwards previously rounded it back across an oblique core edge.
  # Keep exact common boundaries; the compiler's overlap gate is unchanged.
  floor=gross.difference(core_union)
  if floor.is_empty:raise ValueError('Collapsed route: '+str(i))
  sid='circulation_gallery_'+str(i);add(sid,floor,'circulation','Continuous route around jointly reserved complexes; intermediate roles annotate this street')
  for a,b in zip(route,route[1:]):edge_spaces[frozenset((a,b))]=sid
  for episode in episodes:episode['space']=sid;p['approach_episodes'].append(episode)
  for n in route[1:-1]:node_spaces[n]=[(sid,floor)]
  for n in (route[0],route[-1]):
   coreid,g=node_spaces[n][0];shared=g.boundary.intersection(floor.boundary.buffer(precision))
   if shared.geom_type=='MultiLineString':shared=linemerge(shared)
   parts=list(shared.geoms) if hasattr(shared,'geoms') else [shared];width=spec['hard_constraints']['minimum_door_width_HU']/32
   straight=[LineString([a,b]) for q in parts if isinstance(q,LineString) for a,b in zip(q.coords,q.coords[1:])]
   viable=[q for q in straight if q.length>=width+.8]
   if not viable:raise ValueError('Free route lacks clear actual frontage: '+str((i,n)))
   line=max(viable,key=lambda q:q.length);mid=line.length/2;ap=LineString([line.interpolate(mid-width/2),line.interpolate(mid+width/2)])
   if ap.length<width-1e-6:raise ValueError('Free frontage aperture crosses architectural corner')
   p['openings'].append(dict(id='free_opening_'+str(len(p['openings'])),spaces=[coreid,sid],aperture=list(ap.coords),purpose='Actual frontage into continuous route'))
 # Role points can cross a shared architectural boundary when a confluence
 # expands. Include their actual spatial support as well as their route
 # gallery; one role may span spaces, several roles may share a court.
 for n in nodes:
  actual=[(sid,g) for sid,g in shapes.items() if g.covers(Point(positions[n]))]
  node_spaces[n]=list({sid:(sid,g) for sid,g in node_spaces[n]+actual}.values())
 # Joint site/approach architecture: attached building wings shape clearing,
 # while low plant cover has a separate declared visibility assumption.
 # Choose outside route centre lines AND actual opening/turning envelopes.
 protected=unary_union([LineString([positions[n] for n in route]).buffer(2,join_style=2) for route in chains]+[LineString(o['aperture']).buffer(2,cap_style=2) for o in p['openings']])
 for name,n in roles.items():p['annotations'][name]=dict(point=positions[n])
 for site in ('A','B'):
  g=cores[roles[site]];p['site_spaces'][site]=node_spaces[roles[site]][0][0]
  # A provisional planted/holding inset, no invented height or balance claim.
  inset=g.buffer(-2,join_style=2);p['objective_zones'][site]=list(inset.exterior.coords)[:-1];p['defender_positions'][site]=list(inset.representative_point().coords[0])
  coords=list(g.exterior.coords)[:-1];wing=None
  for index in range(len(coords)):
   corner=np.array(coords[index]);next_corner=np.array(coords[(index+1)%len(coords)]);previous=np.array(coords[index-1]);u=(next_corner-corner)/np.linalg.norm(next_corner-corner);v=(previous-corner)/np.linalg.norm(previous-corner)
   # Inset within the boundary wall thickness (no walkable seam) so a wing
   # is robustly inside the footprint after JSON reconstruction.
   shape=Polygon([corner,corner+u*6,corner+u*6+v*3,corner+v*3]).intersection(g.buffer(-.05,join_style=2))
   if shape.geom_type!='Polygon' or shape.area<8:continue
   if shape.intersects(protected):continue
   wing=shape;p['internal_masses'].append(dict(id=site+'_building_wing',boundary=list(shape.exterior.coords)[:-1],height_source_units=160,purpose='Attached full-height building wing separates entry clearing from objective court'))
   p['architectural_buildings'].append(dict(boundary=list(shape.exterior.coords)[:-1],purpose='Site building footprint defines a holding corner and sightline break'));break
  for index in range(len(coords)):
   corner=np.array(coords[index]);u=(np.array(coords[(index+1)%len(coords)])-corner);u/=np.linalg.norm(u);v=np.array(coords[index-1])-corner;v/=np.linalg.norm(v)
   origin=corner+u*4+v*4;cover=Polygon([origin,origin+u*2.5,origin+u*2.5+v*1.8,origin+v*1.8])
   if not g.buffer(-1).covers(cover) or cover.intersects(protected) or (wing is not None and cover.distance(wing)<1):continue
   p['internal_masses'].append(dict(id=site+'_plant_cover',boundary=list(cover.exterior.coords)[:-1],height_source_units=48,purpose='Low plant-edge cover; crouched/standing occlusion differs'))
   break
  available=inset.difference(unary_union([Polygon(m['boundary']).buffer(1) for m in p['internal_masses'] if m['id'].startswith(site+'_')]))
  plant=available.representative_point();plantzone=box(plant.x-2,plant.y-2,plant.x+2,plant.y+2).intersection(available)
  if plantzone.geom_type=='Polygon':p['objective_zones'][site]=list(plantzone.exterior.coords)[:-1]
  p['annotations'][site]['point']=list(plant.coords[0]);p['defender_positions'][site]=positions[n]
  for suffix,rid,idx in [('staging','T-'+site+'-main',-2),('receiving','CT-'+site+'-deploy',-2),('secondary','Mid-'+site,-2),('transfer','Mid-'+site,-3),('split','Mid-'+site,0)]:p['annotations'][site+'_'+suffix]=dict(point=positions[net[rid][idx]])
 p['physical_route_waypoints']={}
 p['physical_route_leg_spaces']={}
 def leg_support(a,b):
  # A direct link between two complexes still traverses its connecting
  # gallery. Anchor-only role bindings must not omit that actual floor.
  return sorted({edge_spaces[frozenset((a,b))]}|{sid for n in (a,b) for sid,g in node_spaces[n]})
 for site in ('A','B'):
  routes={'T-'+site+'-main':net['T-'+site+'-main'],'T-'+site+'-secondary':net['T-Mid'][:-1]+net['Mid-'+site],'CT-'+site+'-deploy':net['CT-'+site+'-deploy'],site+'-retreat':list(reversed(net['CT-'+site+'-deploy']))}
  for rid,route in routes.items():
   p['physical_route_waypoints'][rid]=[positions[n] for n in route];p['physical_route_leg_spaces'][rid]=[leg_support(a,b) for a,b in zip(route,route[1:])]
 for rid,route in [('T-Mid',net['T-Mid']),('CT-Mid',net['CT-Mid']),('CT-rotate',list(reversed(net['Mid-A']))+net['Mid-B'][1:])]:
  p['physical_route_waypoints'][rid]=[positions[n] for n in route];p['physical_route_leg_spaces'][rid]=[leg_support(a,b) for a,b in zip(route,route[1:])]
 p['mid_spaces']=sorted({sid for n in net['Mid-spine'] for sid,g in node_spaces[n]})
 for binding in p['role_bindings']:
  binding['spaces']=p['mid_spaces'] if binding['id']=='Mid-contest' else sorted({sid for q in binding.get('nodes',[]) for sid,g in node_spaces[tuple(q)]})
 floor=unary_union(list(shapes.values()));p['envelope']=list(floor.convex_hull.buffer(6,join_style=2).exterior.coords)[:-1]
 p['decision_log']=[dict(stage='free_embedding',seed=seed,strategy_source_sha256=digest(base),method='Continuous force placement, clearance relaxation, jointly reserved cores and continuous routes. No cell coordinates, peripheral lane requirement or grid fallback.',limits='Existing strategy retained; free placement can fail intersections, clearance or request gates.'),dict(stage='architecture',purposeful_approach_episodes=len(p['approach_episodes']),rules='Offset staging/preparation courts integrated into continuous lanes; site wings outside actual ingress and movement envelopes.',provenance='Authored rule assembly; offset courts and building-defined transitions informed by existing radar library. NAV connectivity retained without treating subdivisions as rooms. No new extraction or tactical timing claim.'),dict(stage='composition',role_cells={k:list(q) for k,q in roles.items()},site_settings={'A':'courtyard','B':'courtyard'},role_ids_only=True)]
 return p

def run(folder,out,seed):
 if out.exists():raise ValueError('Use a fresh output path')
 out.mkdir(parents=True);base=json.loads((folder/'composition.json').read_text());spec=json.loads((folder/'resolved-specification.json').read_text());write(out/'specification.json',spec);write(out/'strategy-source.json',base);frozen=out/'source';frozen.mkdir()
 for name in SOURCES+['free_mid_layout.py']:(frozen/name).write_bytes((Path(__file__).resolve().parent/name).read_bytes())
 try:
  p=generate(base,spec,seed);write(out/'composition.json',p);c=compile_composition(p);v=validate(spec,p,c)
  span=max(c['envelope'].bounds[2]-c['envelope'].bounds[0],c['envelope'].bounds[3]-c['envelope'].bounds[1])*32
  if span>spec['hard_constraints']['max_extent_HU']:v['physical_violations'].append('Free composition exceeds maximum extent');v['physical_pass']=False
  write(out/'validation.json',v);render(p,c,v).save(out/'clean.png');render(p,c,v,True).save(out/'encounters.png');write(out/'summary.json',dict(seed=seed,attempts=1,physical_pass=v['physical_pass'],request_pass=v['request_pass'],reproduced=digest(generate(base,spec,seed))==digest(p),stage4_paused=True));print(json.dumps(dict(physical=v['physical_violations'],request=v['adherence_violations'])))
 except ValueError as e:
  write(out/'failure-report.json',dict(seed=seed,attempts=1,reason=str(e),stage4_paused=True));print(str(e))
  # Diagnostic preview is clearly separate from a compiled/accepted plan.
  if 'p' in locals():
   from PIL import Image,ImageDraw
   im=Image.new('RGB',(1600,1600),'#101923');d=ImageDraw.Draw(im);geoms=[Polygon(s['boundary']) for s in p['spaces']];bounds=unary_union(geoms).bounds;scale=1200/max(bounds[2]-bounds[0],bounds[3]-bounds[1]);xy=lambda q:(200+(q[0]-bounds[0])*scale,1400-(q[1]-bounds[1])*scale)
   for g in geoms:d.polygon([xy(q) for q in g.exterior.coords],fill='#718b9c',outline='#dca0a0')
   for m in p['internal_masses']:d.polygon([xy(q) for q in m['boundary']],fill='#d7cba1' if m['height_source_units']==48 else '#263544')
   for o in p['openings']:d.line([xy(q) for q in o['aperture']],fill='#e6f3e6',width=3)
   for label in ('T','CT','A','B','Mid'):d.text(xy(p['annotations'][label]['point']),label,font=font(25),fill='white')
   d.text((60,35),'FAILED free-placement attempt — diagnostic, not validated layout',font=font(29),fill='#ffa7a7');im.save(out/'diagnostic.png')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--strategy',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seed',type=int,required=True);a=ap.parse_args();run(a.strategy,a.output,a.seed)
