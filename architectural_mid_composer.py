"""Seeded architectural complexes with free circulation around joint masses.

Local rules are authored, adaptable architectural motifs, not imported layouts.
The new local+Mid strategy is specified independently of P04. No engine geometry.
"""
import math,random
import numpy as np
import networkx as nx
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from shapely.affinity import rotate,translate,scale
from map_design_spec import SpecificationError,strategic_contract
from map_composer import SearchFailure
from semantic_pipeline import digest

VERSION='validated-strategy-architectural-districts-v3'
CONFIG=dict(version=VERSION,units_HU=32,boundary_thickness=.8,precision_plan_units=1e-8,
            routing_clearance_plan_units=.65,route_order_limit=4,arrangement_fit_limit=12,
            deployment_visibility_sample_spacing_HU=32,
            macro_placement='Seeded site districts around a jointly composed Mid/deployment district; no reservation grid',
            site_assemblies=['courtyard with a building-defined side entry','workshop vestibule with a local gallery'],
            connector_cap='No inherited P04 1536-HU connector cap; complete route cap comes from the request',
            unsupported=['Vertical routes','arbitrary architectural families','verified encounter timing'],
            evidence='User images 2442.jpg and 2444.jpg; authored proportions and scale, not recovered engine dimensions')

def transform(g,center,angle,sx=1,sy=1):
 return translate(rotate(scale(g,xfact=sx,yfact=sy,origin=(0,0)),angle,origin=(0,0)),*center)

def site_module(site,center,angle,sx,sy,mid_target=None,attacker_target=None,handoff=False,local=True,staged=True):
 """Rooms, external building masses and portals chosen as one assembly."""
 if site=='A':
  floors={
   'A_staging':box(-16,-22,4,-12),
   'A_main':box(-16,-12,-6,-2),
   'A_objective':Polygon([(-16,-2),(-6,-2),(-6,-8),(12,-8),(12,12),(6,12),(6,6),(0,6),(0,12),(-16,12)]),
   'A_side':Polygon([(4,-22),(18,-22),(18,-10),(20,-10),(20,8),(12,8),(12,-8),(4,-8)]),
   'A_receiving':box(-16,12,12,20)}
  buildings={'A_warehouse':box(-30,-10,-16,10),'A_entry_building':box(-6,-12,4,-8),'A_site_wing':box(0,6,6,12)}
  doors=[('A_staging','A_main',(-11,-12),(1,0),'Offset main threshold into the west entry court'),
         ('A_main','A_objective',(-11,-2),(1,0),'Clear the west court before the plant sector'),
         ('A_staging','A_side',(4,-17),(0,1),'Local split around the entrance building'),
         ('A_side','A_objective',(12,3),(0,1),'East side entry clears a different holding sector'),
         ('A_receiving','A_objective',(-9,12),(1,0),'Rear defender assignment and fallback')]
  sockets={'attack':('A_staging',(-6,-22),(0,-1)),
           'rear':('A_receiving',(-3,20),(0,1)),
           'mid':('A_side',(20,-3),(1,0))}
  points={'staging':(-6,-17),'main':(-11,-7),'site':(-3,3),'side':(16,-3),'receiving':(-8,16)}
  cover=box(-4,7,-2,9);plant=box(-6,0,0,6);holding=(-11,7)
  floors.update(A_alley=box(20,-12,26,-2),A_rear_lobby=box(12,12,20,22),
                A_forecourt=box(-4,-30,20,-22).difference(box(-4,-30,6,-26)))
  buildings['A_forecourt_frontage']=box(-4,-30,6,-26)
  doors += [('A_side','A_alley',(20,-6),(0,1),'Turn from the Mid alley into side-entry preparation'),
            ('A_receiving','A_rear_lobby',(12,16),(0,1),'Rear lobby supports receiving without a perimeter detour'),
            ('A_forecourt','A_staging',(0,-22),(1,0),'Offset facade threshold protects staging from the deployment approach')]
  sockets.update(attack=('A_forecourt',(20,-26),(1,0)),rear=('A_rear_lobby',(20,18),(1,0)),mid=('A_alley',(23,-12),(0,-1)))
  points.update(transfer=(23,-7),rear_lobby=(16,18),forecourt=(12,-26))
 else:
  floors={'B_staging':box(-20,-18,-8,-8),'B_main':box(-8,-18,8,-10),
          'B_vestibule':box(0,-10,8,0),
          'B_objective':Polygon([(0,0),(20,0),(20,18),(6,18),(6,11),(0,11)]),
          'B_side':Polygon([(-20,-8),(-10,-8),(-10,4),(0,4),(0,11),(-20,11)]),
          'B_receiving':box(4,18,20,26)}
  buildings={'B_workshop':box(-10,-8,0,4),'B_workshop_return':box(-8,-10,0,-8),
             'B_site_wing':box(0,11,6,18),'B_east_building':box(20,0,30,18)}
  doors=[('B_staging','B_main',(-8,-14),(0,1),'Enter workshop parallel to its building frontage'),
         ('B_main','B_vestibule',(4,-10),(1,0),'Turn into execute preparation behind the workshop'),
         ('B_vestibule','B_objective',(4,0),(1,0),'Interior clearing threshold; plant court follows'),
         ('B_staging','B_side',(-15,-8),(1,0),'Local alternate goes around the workshop'),
         ('B_side','B_objective',(0,7.5),(0,1),'West entry sees a different part of the site'),
         ('B_receiving','B_objective',(14,18),(1,0),'Rear receiving and retake doorway')]
  sockets={'attack':('B_staging',(-14,-18),(0,-1)),
           'rear':('B_receiving',(12,26),(0,1)),
           'mid':('B_side',(-20,4),(-1,0))}
  points={'staging':(-14,-13),'main':(0,-14),'execute':(4,-5),'site':(11,8),'side':(-14,7),'receiving':(12,22)}
  cover=box(14,10,16,12);plant=box(8,5,14,11);holding=(17,15)
  floors.update(B_passage=Polygon([(-34,-8),(-20,-8),(-20,4),(-26,4),(-26,-2),(-34,-2)]),
                B_rear_lobby=box(-6,18,4,28),B_forecourt=box(-34,-22,-20,-10))
  buildings['B_frontage_separator']=box(-34,-10,-20,-8)
  doors += [('B_passage','B_side',(-20,-1),(0,1),'Bent workshop passage clears into side preparation'),
            ('B_receiving','B_rear_lobby',(4,22),(0,1),'Rear arrival turns into the receiving room'),
            ('B_forecourt','B_staging',(-20,-14),(0,1),'Front lobby opens across the workshop approach')]
  sockets.update(attack=('B_forecourt',(-27,-22),(0,-1)),rear=('B_rear_lobby',(-6,23),(-1,0)),mid=('B_passage',(-34,-5),(-1,0)))
  points.update(transfer=(-23,-4),rear_lobby=(-1,23),forecourt=(-27,-16))
 if not local:
  doors=[o for o in doors if set(o[:2])!={site+'_staging',site+'_side'}]
 if handoff:
  old=floors.pop(site+'_side')
  doors=[o for o in doors if site+'_side' not in o[:2]]
  if site=='A':
   old=old.union(floors.pop('A_alley'));floors['A_handoff']=box(4,-22,26,-12)
   buildings['A_handoff_separator']=old.difference(floors['A_handoff'])
   doors.append(('A_handoff','A_staging',(4,-17),(0,1),'Mid joins preparation before the same main entry'))
   sockets['mid']=('A_handoff',(26,-17),(1,0));points['transfer']=(16,-17);points['side']=(8,-17)
  else:
   floors['B_handoff']=box(-20,-8,-10,4);buildings['B_handoff_separator']=old.difference(floors['B_handoff'])
   doors += [('B_passage','B_handoff',(-20,-1),(0,1),'Passage transfers into main preparation'),('B_handoff','B_staging',(-15,-8),(1,0),'Mid joins the workshop preparation sequence')]
   points['side']=(-15,-2)
 if not staged:
  floors.pop(site+'_forecourt');doors=[o for o in doors if site+'_forecourt' not in o[:2]]
  if site=='A':buildings.pop('A_forecourt_frontage');sockets['attack']=('A_staging',(-10,-22),(0,-1))
  else:sockets['attack']=('B_staging',(-14,-18),(0,-1))
 def pt(q):return list(transform(Point(q),center,angle,sx,sy).coords[0])
 def vec(q):
  radians=math.radians(angle);x,y=q;v=np.array([x*sx,y*sy]);v=np.array([v[0]*math.cos(radians)-v[1]*math.sin(radians),v[0]*math.sin(radians)+v[1]*math.cos(radians)]);return list(v/np.linalg.norm(v))
 if mid_target is not None and not (handoff and site=='A'):
  # Select an exposed transfer frontage from the whole assembly's bearing.
  # The interior turn remains fixed; the outside opening adapts to its district.
  options=[('A_alley',(23,-12),(0,-1)),('A_alley',(26,-7),(1,0))] if site=='A' else [('B_passage',(-34,-5),(-1,0)),('B_passage',(-30,-2),(0,1))]
  def score(port):
   delta=np.array(mid_target)-pt(port[1]);return float(np.dot(delta/np.linalg.norm(delta),vec(port[2])))
  sockets['mid']=max(options,key=score)
 if attacker_target is not None and site=='B' and staged:
  options=[('B_forecourt',(-27,-22),(0,-1)),('B_forecourt',(-34,-16),(-1,0))]
  def score_attack(port):
   delta=np.array(attacker_target)-pt(port[1]);return float(np.dot(delta/np.linalg.norm(delta),vec(port[2])))
  sockets['attack']=max(options,key=score_attack)
 return dict(floors={k:transform(g,center,angle,sx,sy) for k,g in floors.items()},
             buildings={k:transform(g,center,angle,sx,sy) for k,g in buildings.items()},
             sockets={k:dict(space=s,point=pt(q),normal=vec(n)) for k,(s,q,n) in sockets.items()},
             doors=[dict(spaces=[a,b],point=pt(q),tangent=vec(t),purpose=why) for a,b,q,t,why in doors],
             points={k:pt(q) for k,q in points.items()},cover=transform(cover,center,angle,sx,sy),
             plant=transform(plant,center,angle,sx,sy),holding=pt(holding))

def mid_module(center,angle,organization='contested_street'):
 # Two encounter portions around one coherent stepped building frontage;
 # entry and exit doors occupy different portions, not four cross arms.
 floors={'Mid_west':box(-20,-6,4,6),'Mid_east':box(-4,-12,16,0),
         'T_mid_alley':Polygon([(-32,-6),(-20,-6),(-20,0),(-26,0),(-26,6),(-32,6)]),
         'CT_mid_gallery':Polygon([(16,-12),(28,-12),(28,6),(22,6),(22,-6),(16,-6)])}
 # Partition the overlap into the eastern portion. It remains a generous
 # architectural transition and receives an actual shared circulation opening.
 floors['Mid_west']=floors['Mid_west'].difference(floors['Mid_east'])
 buildings={'Mid_north_building':box(4,0,16,12),'Mid_south_building':box(-20,-10,-4,-6),
            'T_mid_corner':box(-26,0,-20,6),'CT_mid_corner':box(16,-6,22,6)}
 sockets={'A':('Mid_west',(-11,6),(0,1)), 'B':('Mid_east',(8,-12),(0,-1))}
 doors=[('T_deployment','T_mid_alley',(-29,6),(1,0),'Leave deployment behind the alley corner'),
        ('T_mid_alley','Mid_west',(-20,-3),(0,1),'Offset attacker threshold into contested Mid'),
        ('CT_deployment','CT_mid_gallery',(28,3),(0,1),'Defender access turns behind the receiving facade'),
        ('CT_mid_gallery','Mid_east',(16,-9),(0,1),'Defender gallery clears behind a full-height return before Mid')]
 points={'Mid':(0,3),'Mid2':(8,-5),'T_mid_travel':(-29,0),'CT_mid_travel':(25,-4)}
 if organization=='linked_courts':
  floors.update(Mid_west=box(-20,-8,0,10),Mid_link=box(0,-8,6,-2),Mid_east=box(6,-14,16,4))
  buildings.update(Mid_north_building=box(0,-2,6,12),Mid_south_building=box(-20,-12,-4,-8))
  sockets.update(A=('Mid_west',(-11,10),(0,1)),B=('Mid_east',(11,-14),(0,-1)))
  points.update(Mid=(-8,2),Mid2=(11,-6),Mid_link=(3,-5))
  doors += [('Mid_west','Mid_link',(0,-5),(0,1),'Offset transition between separate Mid courts'),('Mid_link','Mid_east',(6,-5),(0,1),'Clear the far court before using its site transfer')]
 def pt(q):return list(transform(Point(q),center,angle).coords[0])
 def vec(q):return list(np.array(rotate(LineString([(0,0),q]),angle,origin=(0,0)).coords[-1]))
 deployments={}
 for team,g,q,ports in [('T',box(-40,6,-24,18),(-31,12),{'A':((-31,18),(0,1)),'B':((-37,6),(0,-1))}),
                       ('CT',box(28,0,44,14),(36,8),{'A':((36,14),(0,1)),'B':((36,0),(0,-1))})]:
  deployments[team]=dict(floor=transform(g,center,angle),point=pt(q),sockets={k:dict(space=team+'_deployment',point=pt(p),normal=vec(n)) for k,(p,n) in ports.items()})
 return dict(floors={k:transform(g,center,angle) for k,g in floors.items()},
             buildings={k:transform(g,center,angle) for k,g in buildings.items()},
             sockets={k:dict(space=s,point=pt(q),normal=vec(n)) for k,(s,q,n) in sockets.items()},
             points={k:pt(q) for k,q in points.items()},
             deployments=deployments,
             doors=[dict(spaces=[a,b],point=pt(q),tangent=vec(t),purpose=why) for a,b,q,t,why in doors],
             transition=transform(LineString([(-4,0),(4,0)]),center,angle))

def deployment(team,center,forward,targets):
 angle=math.degrees(math.atan2(forward[1],forward[0]))-90
 floor=transform(Polygon([(-10,-7),(10,-7),(10,6),(-6,6),(-6,10),(-10,10)]),center,angle)
 def pt(q):return list(transform(Point(q),center,angle).coords[0])
 def vec(q):return list(np.array(rotate(LineString([(0,0),q]),angle,origin=(0,0)).coords[-1]))
 # Site assignments emerge on different sides of deployment; Mid is a third
 # commitment. Match side portals to the real bearing, rather than labels.
 local_left=np.array(vec((-1,0)));a_side=-1 if np.dot(np.array(targets['A'])-center,local_left)>0 else 1
 sockets={site:dict(space=team+'_deployment',point=pt((side*10,0)),normal=vec((side,0))) for site,side in [('A',a_side),('B',-a_side)]}
 sockets['Mid']=dict(space=team+'_deployment',point=pt((0,6)),normal=vec((0,1)))
 return dict(floor=floor,point=list(center),sockets=sockets)

def polygon_parts(g):return list(g.geoms) if hasattr(g,'geoms') else [g]

def visibility_route(start,end,obstacles,halfwidth,rng):
 """Shortest continuous visibility route around whole footprint reservations.

 No orthogonal reservation grid; straight stretches remain where they fit.
 Extra stubs normal to the actual doorway prevent angled aperture shoulders.
 """
 delta=np.array(end['point'])-start['point'];distance=np.linalg.norm(delta)
 if 1e-6<distance<4*halfwidth+2 and np.dot(delta/distance,start['normal'])>.35 and np.dot(-delta/distance,end['normal'])>.35:
  # Facing nearby frontages need an architectural join, not two outward stubs
  # that each run into the opposite building's inflated reservation. All raw
  # floor/mass overlap, aperture and physical-clearance gates still apply.
  points=[start['point'],end['point']];line=LineString(points)
  floor=LineString([np.array(start['point'])-np.array(start['normal']),*points,np.array(end['point'])-np.array(end['normal'])]).buffer(halfwidth,cap_style=2,join_style=2)
  # Only its endpoint districts may be touched; separate circulation remains
  # a real obstacle even when this join is short.
  allowed=[g for g in obstacles if g.distance(Point(start['point']))<1e-6 or g.distance(Point(end['point']))<1e-6]
  if not any(floor.intersection(g).area>1e-7 for g in obstacles if not any(g.equals(h) for h in allowed)):
   return dict(points=points,line=line,floor=floor,method='nearby-facing-frontage-join')
 stub_length=halfwidth+1.5
 a=np.array(start['point'])+np.array(start['normal'])*stub_length
 b=np.array(end['point'])+np.array(end['normal'])*stub_length
 expanded=unary_union(obstacles).buffer(halfwidth+CONFIG['routing_clearance_plan_units'],join_style=2)
 blocker=expanded.buffer(-1e-5,join_style=2)
 if blocker.covers(Point(a)) or blocker.covers(Point(b)):return None
 vertices=[tuple(a),tuple(b)]
 for g in polygon_parts(expanded):
  if isinstance(g,Polygon):
   for ring in [g.exterior]+list(g.interiors):vertices.extend(list(ring.coords)[:-1])
 vertices=list(dict.fromkeys(vertices));graph=nx.Graph();graph.add_nodes_from(range(len(vertices)))
 for i,first in enumerate(vertices):
  for j in range(i):
   line=LineString([first,vertices[j]])
   if not line.intersects(blocker):graph.add_edge(i,j,weight=line.length*(1+rng.random()*.015))
 try:indices=nx.shortest_path(graph,0,1,weight='weight')
 except nx.NetworkXNoPath:return None
 points=[start['point']]+[list(vertices[i]) for i in indices]+[end['point']]
 line=LineString(points);floor=line.buffer(halfwidth,cap_style=2,join_style=2)
 return dict(points=points,line=line,floor=floor,method='visibility-route-around-reservations')

def arrangement(rng,spec):
 # Different angular gaps and staggered radii determine the occupied land;
 # this is a limited sector assembly, not arbitrary architectural diversity.
 def polar(radius,degrees):return np.array([radius*math.cos(math.radians(degrees)),radius*math.sin(math.radians(degrees))])
 # Allocate land to the full complexes, including their surrounding buildings,
 # rather than spend the requested extent entirely on centre separation.
 # 35 plan units reserves the largest local frontage plus rendering envelope;
 # the resulting envelope still has to pass its independent exact check.
 site_radius_cap=spec['hard_constraints']['max_extent_HU']/64-35
 centers={'A':polar(min(rng.uniform(46,51),site_radius_cap),rng.uniform(148,171)),
          'B':polar(min(rng.uniform(46,51),site_radius_cap),rng.uniform(-12,22)),
          'T':polar(rng.uniform(44,51),rng.uniform(248,286)),
          'CT':polar(rng.uniform(34,40),rng.uniform(73,102)),
          'Mid':np.array([rng.uniform(-5,5),rng.uniform(-5,5)])}
 angles={}
 local_ports={'A':{'T':(-6,-22),'CT':(-3,20),'Mid':(20,-3)},'B':{'T':(-14,-18),'CT':(12,26),'Mid':(-20,4)}}
 for site in ('A','B'):
  # Fit the entire building assembly to attacker, rear and Mid territories.
  cross=dot=0
  for role,local in local_ports[site].items():
   desired=centers[role]-centers[site];desired/=np.linalg.norm(desired);local=np.array(local,dtype=float);local/=np.linalg.norm(local)
   cross+=local[0]*desired[1]-local[1]*desired[0];dot+=float(np.dot(local,desired))
  angles[site]=math.degrees(math.atan2(cross,dot))
 return centers,angles

def supports(spec):
 g,a=spec['gameplay'],spec['architecture']
 if g['mid']!='contested' or g['secondary_access'] not in ('mid','local_and_mid'):raise SpecificationError('Architectural composer requires contested Mid with Mid secondary access')
 if a['site_setting']!='mixed':raise SpecificationError('This assembly currently supports courtyard A and interior B (site_setting=mixed)')
 if a['site_separation']!='separated':raise SpecificationError('This architectural family currently supports separated site districts')
 if g['secondary_access']=='local_and_mid' and g['mid_access_mode']=='one_approach_handoff':raise SpecificationError('Local plus Mid alternatives with a shared main handoff are not yet supported by the architectural compiler')

def generate(spec,seed,plan=None,validation=None):
 from spec_strategy import prepare,require_plan
 if plan is None:plan,validation=prepare(spec)
 require_plan(spec,plan,validation);supports(spec)
 failures=[]
 for fit in range(CONFIG['arrangement_fit_limit']):
  try:
   p=_compose(spec,seed,plan,seed if fit==0 else seed^(fit*104729))
   p['decision_log'].insert(0,dict(stage='bounded_architectural_fitting',attempts=failures+[dict(fit=fit,status='constructed')]))
   p['plan_sha256']=digest(plan);return p
  except (SearchFailure,ValueError) as exc:failures.append(dict(fit=fit,status='rejected',reason=str(exc),decisions=getattr(exc,'log',[])))
 raise SearchFailure('Architectural fitting exhausted twelve arrangements',failures)

def _compose(spec,seed,plan,placement_seed):
 rng=random.Random(placement_seed);log=[];centers,angles=arrangement(rng,spec)
 program=plan['mid_program'];handoff=program['handoff_site'];local_access=spec['gameplay']['secondary_access']=='local_and_mid'
 staged={s:spec['gameplay']['site_commitment']=='staged' or spec['gameplay']['site_commitment']=='mixed' and s=='B' for s in ('A','B')}
 proportions={site:(rng.uniform(.96,1.06),rng.uniform(.96,1.04)) for site in ('A','B')}
 cross=dot=0
 # Orient the complete deployment district toward the selected team territories.
 # A/B transfer sockets adapt through attached passages; they must not torque
 # the district back into the previous four-portal Mid arrangement.
 for role,local in {'T':(-31,12),'CT':(36,8)}.items():
  desired=centers[role]-centers['Mid'];desired/=np.linalg.norm(desired);local=np.array(local,dtype=float);local/=np.linalg.norm(local)
  cross+=local[0]*desired[1]-local[1]*desired[0];dot+=float(np.dot(local,desired))
 mid_angle=math.degrees(math.atan2(cross,dot));mid=mid_module(centers['Mid'],mid_angle,program['organization'])
 deployments=mid['deployments'];orientation_targets={k:list(v) for k,v in centers.items()}
 for team,d in deployments.items():centers[team]=np.array(d['point'])
 modules={site:site_module(site,centers[site],angles[site],*proportions[site],centers['Mid'],centers['T'],site==handoff,local_access,staged[site]) for site in ('A','B')}
 p=dict(schema='playable-space-mass-openings-v1',candidate='architectural-mid-'+str(seed),generator_version=VERSION,seed=seed,
        specification_sha256=digest(spec),engine_scale=dict(source_units_per_plan_unit=32,standing_eye_source_units=64,crouched_eye_source_units=46),
        boundary_thickness=CONFIG['boundary_thickness'],geometric_precision_plan_units=CONFIG['precision_plan_units'],
        spaces=[],openings=[],internal_masses=[],external_masses=[],annotations={},objective_zones={},site_spaces={},defender_positions={},
        space_program={},physical_route_waypoints={},physical_route_leg_spaces={},decision_log=log,mid_handoffs=[handoff] if handoff else [],mid_organization=program['organization'],
        reference_influences=dict(image1='2442.jpg: site complexes, staged clearing, integrated rear spaces',image2='2444.jpg: changing lane axes, coherent oblique building alignment',scope='Qualitative composition evidence; absolute dimensions and heights authored provisionally'),
        nav_reference_influences=dict(source='Existing dust2/cache/train movement observations',use='Connected space sequences around exclusions; no NAV cells become rooms'),measure_entry_faces=True)
 shapes={}
 def add(sid,g,kind,purpose):
  if g.geom_type!='Polygon' or not g.is_valid:raise SearchFailure('Architectural region is split or invalid: '+sid,log)
  shapes[sid]=g;p['spaces'].append(dict(id=sid,boundary=list(g.exterior.coords)[:-1],holes=[list(h.coords)[:-1] for h in g.interiors],kind=kind,purpose=purpose));p['space_program'][sid]=dict(kind=kind,purpose=purpose)
 def door(identifier,a,b,point,tangent,purpose,width=None):
  width=width or spec['hard_constraints']['minimum_door_width_HU']/32
  q=np.array(point);t=np.array(tangent);t=t/np.linalg.norm(t)
  p['openings'].append(dict(id=identifier,spaces=[a,b],aperture=[list(q-t*width/2),list(q+t*width/2)],purpose=purpose))
 for site,module in modules.items():
  for sid,g in module['floors'].items():
   kind='courtyard' if site=='A' and sid in ('A_objective','A_staging') else 'interior'
   purpose={'staging':'Prepare main entry; local split only where requested','main':'Clear the entrance territory','vestibule':'Execute preparation after a workshop turn','objective':'Plant, hold and contest distinct entry sectors','side':'Mid-controlled side entry; local access only where requested','handoff':'Mid joins main preparation; shared final entry counted once','receiving':'Rear assignment, fallback and retake support','alley':'Mid transfer turns behind the facade before the side entry','passage':'Workshop passage separates Mid contact from the site execute','rear_lobby':'Receiving threshold and protected rear preparation','forecourt':'Attached main investment; arrival axis differs from staging threshold'}[sid.split('_',1)[1]]
   add(sid,g,kind,purpose)
  for index,o in enumerate(module['doors']):
   identifier=site+'_interior_threshold' if o['spaces']==['B_vestibule','B_objective'] else site+'_local_opening_'+str(index)
   door(identifier,*o['spaces'],o['point'],o['tangent'],o['purpose'])
  for bid,g in module['buildings'].items():p['external_masses'].append(dict(id=bid,boundary=list(g.exterior.coords)[:-1],purpose='Coherent building footprint jointly assembled with site circulation',height_source_units=160))
  p['internal_masses'].append(dict(id=site+'_plant_cover',boundary=list(module['cover'].exterior.coords)[:-1],height_source_units=48,purpose='Low cover at the plant edge; different standing/crouched visibility assumption'))
  p['objective_zones'][site]=list(module['plant'].exterior.coords)[:-1];p['defender_positions'][site]=module['holding'];p['site_spaces'][site]=site+'_objective'
 for sid,g in mid['floors'].items():add(sid,g,'courtyard' if sid.startswith('Mid') else 'interior','Contested street territory with site transfers' if sid.startswith('Mid') else 'Buffered independent Mid access; a building corner separates deployment from first contact')
 for bid,g in mid['buildings'].items():p['external_masses'].append(dict(id=bid,boundary=list(g.exterior.coords)[:-1],purpose='Stepped frontage separates Mid encounters and interrupts a full street sightline',height_source_units=160))
 if program['organization']=='contested_street':
  transition=mid['transition'];door('Mid_shared_transition','Mid_west','Mid_east',list(transition.interpolate(.5,normalized=True).coords[0]),np.array(transition.coords[-1])-transition.coords[0],'Shared circulation within one contested Mid street',width=6)
 for team,d in deployments.items():add(team+'_deployment',d['floor'],'deployment','Choose independent main commitments or Mid; defender rear rotations also traverse CT deployment')
 for index,o in enumerate(mid['doors']):door('Mid_access_'+str(index),*o['spaces'],o['point'],o['tangent'],o['purpose'])
 # B's attached front lobby, workshop turn and frontage separator now perform
 # the approach transition. The old detached approach warehouse forced a long
 # perimeter bypass and is deliberately absent from this shared procedure.
 architectural_reservations=[]
 for module in modules.values():architectural_reservations.append(unary_union(list(module['floors'].values())+list(module['buildings'].values())))
 architectural_reservations += [unary_union(list(mid['floors'].values())+list(mid['buildings'].values()))]+[d['floor'] for d in deployments.values()]
 log.append(dict(stage='joint_architecture',centers={k:list(q) for k,q in centers.items()},orientation_targets=orientation_targets,orientations_degrees=dict(angles,Mid=mid_angle),
                 motifs={'A':'Facade forecourt, offset entrance court, attached Mid alley and rear lobby within a courtyard complex','B':'Front lobby, workshop entrance, turned execute and bent Mid passage with an adaptable exterior opening','Mid':'Joint deployment district: two street portions, full-height entrance returns and distributed transfers'},
                 selected_frontages={site:{key:port for key,port in module['sockets'].items()} for site,module in modules.items()},
                 decision_source='Shared seeded rules. No prior composition loaded, no candidate-specific coordinate edits.'))
 connections=[]
 for team in ('T','CT'):
  for site in ('A','B'):
   connections.append((team+'-'+site,deployments[team]['sockets'][site],modules[site]['sockets']['attack' if team=='T' else 'rear'],3.75 if team=='T' and site=='A' else 3.25 if team=='T' else 3))
 for site in ('A','B'):connections.append(('Mid-'+site,mid['sockets'][site],modules[site]['sockets']['mid'],3))
 routed=None
 for order_index in range(CONFIG['route_order_limit']):
  order=list(connections)
  if order_index:random.Random(seed^order_index).shuffle(order)
  routes={};reservations=list(architectural_reservations);rejected=None
  for rid,start,end,halfwidth in order:
   route=visibility_route(start,end,reservations,halfwidth,random.Random(seed^sum(map(ord,rid))^order_index))
   if route is None:rejected=rid;break
   # A main has an approach court against its facade. B instead retains a
   # gallery-to-workshop entrance, avoiding one repeated doorway formula.
   route['floor']=route['floor'].difference(unary_union(list(shapes.values())))
   if route['floor'].geom_type!='Polygon':rejected=rid+' split corridor';break
   if any(route['floor'].intersection(g).area>1e-7 for g in [Polygon(m['boundary']) for m in p['external_masses']]):rejected=rid+' crosses a building';break
   routes[rid]=route;reservations.append(route['floor'])
  log.append(dict(stage='circulation_search',order_index=order_index,order=[x[0] for x in order],result='complete' if rejected is None else 'rejected',reason=rejected))
  if rejected is None:routed=routes;break
 if routed is None:raise SearchFailure('No separate continuous circulation fits this joint architecture within four route orders',log)
 p['external_route_geometry']={}
 for index,(rid,start,end,halfwidth) in enumerate(connections):
  route=routed[rid];sid='circulation_gallery_'+str(index);route['sid']=sid
  add(sid,route['floor'],'circulation','Committed main approach' if rid.startswith('T-') and rid!='T-Mid' else 'Rear defender assignment and rotation' if rid.startswith('CT-') and rid!='CT-Mid' else 'Independent Mid access' if rid.endswith('Mid') else 'Mid transfer to local entry preparation')
  for suffix,port in [('start',start),('end',end)]:
   n=port['normal'];door(rid+'_'+suffix,port['space'],sid,port['point'],(-n[1],n[0]),'Flush architectural opening into '+rid)
  p['external_route_geometry'][rid]=dict(points=route['points'],space=sid,width_HU=halfwidth*64,length_HU=route['line'].length*32,method=route['method'])
 # Compatibility IDs encode identities only, never room/cell coordinates.
 names=['T','CT','A','B','Mid','Mid2','Mid_link','A_staging','A_main','A_secondary','A_receiving','B_staging','B_main','B_execute','B_secondary','B_receiving','A_travel','B_travel','A_rear_travel','B_rear_travel','T_mid_travel','CT_mid_travel','A_transfer','B_transfer','A_transfer_travel','B_transfer_travel','A_rear_lobby','B_rear_lobby','A_forecourt','B_forecourt']
 ids={name:(i,0) for i,name in enumerate(names)};positions={};supports_by_node={}
 def node(name,point,space):positions[ids[name]]=point;supports_by_node[ids[name]]=[space]
 for team,d in deployments.items():node(team,d['point'],team+'_deployment')
 for site,m in modules.items():
  for suffix,key in [('', 'site'),('_staging','staging'),('_main','main'),('_secondary','side'),('_receiving','receiving')]:node(site+suffix,m['points'][key],site+'_objective' if not suffix else site+('_handoff' if site==handoff else '_side') if suffix=='_secondary' else site+suffix)
  if site=='B':node('B_execute',m['points']['execute'],'B_vestibule')
  for role in ('rear_lobby','forecourt'):
   if site+'_'+role in shapes:node(site+'_'+role,m['points'][role],site+'_'+role)
  node(site+'_transfer',m['points']['transfer'],site+('_handoff' if site=='A' and site==handoff else '_alley' if site=='A' else '_passage'))
 for name,q in mid['points'].items():node(name,q,{'Mid':'Mid_west','Mid2':'Mid_east','Mid_link':'Mid_link','T_mid_travel':'T_mid_alley','CT_mid_travel':'CT_mid_gallery'}[name])
 travel_names={'T-A':'A_travel','T-B':'B_travel','CT-A':'A_rear_travel','CT-B':'B_rear_travel','Mid-A':'A_transfer_travel','Mid-B':'B_transfer_travel'}
 for rid,name in travel_names.items():route=routed[rid];node(name,list(route['line'].interpolate(.5,normalized=True).coords[0]),route['sid'])
 net={
  'T-A-main':['T','A_travel','A_forecourt','A_staging','A_main','A'],
  'T-B-main':['T','B_travel','B_forecourt','B_staging','B_main','B_execute','B'],
  'local-A':['A_staging','A_secondary','A'], 'local-B':['B_staging','B_secondary','B'],
  'CT-A-deploy':['CT','A_rear_travel','A_rear_lobby','A_receiving','A'],
  'CT-B-deploy':['CT','B_rear_travel','B_rear_lobby','B_receiving','B'],
  'Mid-spine':['Mid','Mid2'], 'T-Mid':['T','T_mid_travel','Mid'],
  'CT-Mid':['CT','CT_mid_travel','Mid2','Mid'],
  'Mid-A':['Mid','A_transfer_travel','A_transfer','A_secondary','A'],
  'Mid-B':['Mid','Mid2','B_transfer_travel','B_transfer','B_secondary','B']}
 for site in ('A','B'):
  if not staged[site]:net['T-'+site+'-main'].remove(site+'_forecourt')
  if site==handoff:
   net['Mid-'+site]=net['Mid-'+site][:-1]+net['T-'+site+'-main'][net['T-'+site+'-main'].index(site+'_staging'):]
  if not local_access:net.pop('local-'+site)
 if 'Mid_link' in mid['floors']:
  for key,path in net.items():
   for i in range(len(path)-1,0,-1):
    if {path[i-1],path[i]}=={'Mid','Mid2'}:path.insert(i,'Mid_link')
 p['strategic_network']={k:[list(ids[name]) for name in route] for k,route in net.items()}
 p['free_node_positions']={str(n):list(q) for n,q in positions.items()}
 p['mid_program']=dict(branches={site:dict(branch_node=list(ids['Mid' if site=='A' else 'Mid2']),handoff_node=list(ids[site+'_staging']) if site==handoff else None) for site in ('A','B')},scope='Validated strategy selects shared preparation versus distinct entry')
 p['mid_spaces']=['Mid_west','Mid_east']+(['Mid_link'] if 'Mid_link' in mid['floors'] else [])
 for name in ('T','CT','A','B','Mid','Mid2','A_staging','A_secondary','A_receiving','A_transfer','B_staging','B_secondary','B_receiving','B_transfer','T_mid_travel','CT_mid_travel'):p['annotations'][name]=dict(point=positions[ids[name]])
 for site in ('A','B'):
  p['annotations'][site+'_split']=dict(point=positions[ids[site+'_staging']])
  if staged[site]:p['annotations'][site+'_investment']=dict(point=positions[ids[site+'_forecourt']])
 contract=strategic_contract(spec);p['route_contracts']={r['id']:r['places'] for r in contract['routes']}
 intended={}
 for site in ('A','B'):
  intended['T-'+site+'-main']=net['T-'+site+'-main'];intended['CT-'+site+'-deploy']=net['CT-'+site+'-deploy'];intended[site+'-retreat']=list(reversed(net['CT-'+site+'-deploy']))
  intended['T-'+site+'-secondary']=net['T-Mid'][:-1]+net['Mid-'+site]
  if local_access:intended['T-'+site+'-local']=net['T-'+site+'-main'][:-2 if site=='A' else -3]+net['local-'+site][1:]
 intended['T-Mid']=net['T-Mid'];intended['CT-Mid']=net['CT-Mid'];intended['CT-rotate']=list(reversed(net['CT-A-deploy']))+net['CT-B-deploy'][1:]
 if spec['gameplay']['defender_rotation']=='central':intended['CT-rotate']=list(reversed(net['Mid-A']))+net['Mid-B'][1:]
 for rid,names_in_route in intended.items():
  path=[ids[name] for name in names_in_route];p['physical_route_waypoints'][rid]=[positions[n] for n in path]
  p['physical_route_leg_spaces'][rid]=[sorted(set(supports_by_node[a]+supports_by_node[b])) for a,b in zip(path,path[1:])]
 p['role_bindings']=[]
 def bind(identifier,kind,spaces,purpose):p['role_bindings'].append(dict(id=identifier,kind=kind,spaces=spaces,purpose=purpose,confidence='Authored functional intent; timing and control unverified'))
 for site in ('A','B'):
  bind(site+'-main','main_approach',[routed['T-'+site]['sid']]+([site+'_forecourt'] if staged[site] else [])+[site+'_staging',site+'_main']+(['B_vestibule'] if site=='B' else []),'Independent main investment and site-specific clearing sequence')
  bind(site+'-split','split_point',[site+'_staging'],'Choose main or local side entry after committed staging')
  bind(site+'-execute','execute_preparation',[site+'_main' if site=='A' else 'B_vestibule'],'Prepare and clear the primary objective entry')
  if local_access:bind(site+'-local','flank',[site+'_staging',site+'_side'],'Local alternate changes entry angle; no Mid commitment required')
  bind(site+'-Mid-transfer','connector',list(dict.fromkeys([routed['Mid-'+site]['sid'],modules[site]['sockets']['mid']['space'],site+('_handoff' if site==handoff else '_side')])),'Mid control unlocks the entry or handoff declared in the validated strategy')
  bind(site+'-contest','first_contest',[site+'_objective'],'Potential contact at distinct main, side and rear entries')
  bind(site+'-fallback','fallback',[site+'_receiving',site+'_rear_lobby',routed['CT-'+site]['sid']],'Defender withdrawal and rear retake preparation')
 bind('Mid-contest','first_contest',p['mid_spaces'],'Independent T/CT contact and control-dependent transfers toward both sites')
 bind('T-Mid-buffer','main_approach',['T_mid_alley'],'Clear the corner before exposure to Mid; main assignments remain separate')
 bind('CT-Mid-buffer','main_approach',['CT_mid_gallery'],'Receive and contest Mid behind a frontage turn')
 bind('CT-rotation','rotation_junction',['CT_deployment'],'Rear defensive assignments and rotations diverge here')
 p['architectural_buildings']=p['external_masses'];p['building_footprints']=p['external_masses']
 floor=unary_union(list(shapes.values()));all_architecture=floor.union(unary_union([Polygon(m['boundary']) for m in p['external_masses']]))
 p['envelope']=list(all_architecture.convex_hull.buffer(6,join_style=2).exterior.coords)[:-1]
 log.append(dict(stage='composition',role_cells={name:list(ids[name]) for name in ('T','CT','A','B','Mid','Mid2')},site_settings={'A':'courtyard','B':'interior'},ids_are_not_grid_coordinates=True))
 return p

def deployment_visibility_audit(p,c):
 """Finite area sampling supplements marker rays; it is not a timing test."""
 import shapely
 spacing=CONFIG['deployment_visibility_sample_spacing_HU']/32
 visible=c['visibility_standing'].buffer(1e-7)
 clear_floor=c['walkable'].buffer(-.5,join_style=2)
 def samples(sid):
  region=c['spaces'][sid].intersection(clear_floor).buffer(-.01)
  if region.is_empty:return []
  x1,y1,x2,y2=region.bounds
  return [(float(x),float(y)) for x in np.arange(math.ceil(x1/spacing)*spacing,x2,spacing) for y in np.arange(math.ceil(y1/spacing)*spacing,y2,spacing) if region.covers(Point(x,y))]
 points={sid:samples(sid) for sid in ['T_deployment','CT_deployment','Mid_west','Mid_east']}
 records=[]
 for source,target in [('T_deployment','CT_deployment'),('T_deployment','Mid_west'),('T_deployment','Mid_east'),('CT_deployment','Mid_west'),('CT_deployment','Mid_east')]:
  pairs=np.asarray([[a,b] for a in points[source] for b in points[target]],dtype=float)
  if len(pairs):
   lines=shapely.linestrings(pairs);indices=np.flatnonzero(np.asarray(shapely.covers(visible,lines)))
  else:indices=[]
  records.append(dict(source=source,target=target,tested_lines=len(pairs),clear_lines=len(indices),example=pairs[indices[0]].tolist() if len(indices) else None))
 return dict(sample_spacing_HU=CONFIG['deployment_visibility_sample_spacing_HU'],records=records,
             scope='Finite sampling across whole player-clear regions. Full-height architecture occludes; 48-HU cover does not occlude standing rays. No exhaustive visibility or runtime claim.')

def audit(spec,p,c,v):
 """Additional physical/request checks; never remove a common violation."""
 if p.get('generator_version')!=VERSION:return v
 from playable_composition import DerivedNavigation
 physical=v['physical_violations'];adherence=v['adherence_violations'];observations=[]
 floor=unary_union(list(c['spaces'].values()))
 for mass in p['external_masses']:
  g=Polygon(mass['boundary'])
  if floor.intersection(g).area>1e-7:physical.append('Playable region crosses declared building mass: '+mass['id'])
 span=max(c['envelope'].bounds[2]-c['envelope'].bounds[0],c['envelope'].bounds[3]-c['envelope'].bounds[1])*32
 if span>spec['hard_constraints']['max_extent_HU']:adherence.append('Complete architectural envelope exceeds requested extent')
 for site in ('A','B'):
  local=v['routes'].get('T-'+site+'-local',{}).get('path');mid=v['routes']['T-'+site+'-secondary']['path'];main=v['routes']['T-'+site+'-main']['path']
  def ingress(path):
   if not path:return None
   line=LineString(path['points']);matches=[]
   for opening in p['openings']:
    if site+'_objective' not in opening['spaces']:continue
    cut=line.intersection(LineString(opening['aperture']))
    if not cut.is_empty:matches.append((line.project(cut.centroid),opening['id']))
   return min(matches)[1] if matches else None
  primary,local_entry,mid_entry=ingress(main),ingress(local),ingress(mid)
  if spec['gameplay']['secondary_access']=='local_and_mid':
   if local_entry is None or primary==local_entry:adherence.append('Local alternate lacks distinct actual site entry: '+site)
   if local_entry!=mid_entry:adherence.append('Mid transfer fails to reach declared local entry preparation: '+site)
  if site in p['mid_handoffs'] and mid_entry!=primary:adherence.append('Handoff does not share the primary final entry: '+site)
  if site not in p['mid_handoffs'] and (mid_entry is None or mid_entry==primary):adherence.append('Mid branch lacks its declared separate entry: '+site)
  if main and LineString(main['points']).intersection(unary_union([c['spaces'][sid] for sid in p['mid_spaces']])).length>1e-5:adherence.append('Independent main route crosses Mid: '+site)
  observations.append(dict(site=site,main_entry=primary,local_entry=local_entry,Mid_entry=mid_entry,distinct_final_attacker_entries=len(set(x for x in (primary,local_entry,mid_entry) if x)),scope='Local and Mid share the side-entry sector; counted once. Different territory/first-contact intent, not a third final entry or verified timing difference.'))
 blocked=unary_union([c['spaces'][site+'_objective'] for site in ('A','B')]+[c['spaces'][sid] for sid in p['mid_spaces']])
 bypass=DerivedNavigation(c,blocked=blocked).path(p['annotations']['T']['point'],p['annotations']['CT']['point'])
 if bypass:adherence.append('Site-free attacker bypass avoids contested Mid')
 lines={}
 for first,last in [('T','CT'),('T','Mid'),('CT','Mid')]:
  line=LineString([p['annotations'][first]['point'],p['annotations'][last]['point']])
  clear=c['visibility_standing'].buffer(1e-7).covers(line)
  lines[first+'-'+last]=dict(direct_standing_line_clear=clear,straight_distance_HU=line.length*32)
  if clear:adherence.append('Deployment buffer leaves a direct standing line: '+first+'-'+last)
 v['deployment_sightline_audit']=lines
 v['deployment_region_sightlines']=deployment_visibility_audit(p,c)
 for item in v['deployment_region_sightlines']['records']:
  if not item['tested_lines']:adherence.append('Deployment visibility audit lacks samples: '+item['source']+' to '+item['target'])
  elif item['clear_lines']:adherence.append('Deployment buffer exposes a sampled direct line: '+item['source']+' to '+item['target'])
 v['architectural_entry_audit']=observations;v['architectural_envelope_HU']=span;v['physical_pass']=not physical;v['request_pass']=not adherence
 if spec['gameplay']['secondary_access']=='local_and_mid':v['warnings'].append('Local and Mid approaches share their final side doorway; strategic distinction comes from commitment/contest territory, not extra final entrances. Tactical timing and information differences unverified.')
 return v
