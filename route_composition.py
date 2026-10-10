"""Typed route purposes and adaptable local building/circulation assemblies.

NAV/radar motifs guide relationships. No NAV polygon or whole map is copied.
"""
import random,math
from shapely.geometry import Polygon,box,LineString,Point
from shapely.ops import unary_union

PURPOSES={
 'staging':'Gather/hold before entry choices; not a mandatory lobby',
 'main_approach':'Primary committed territory; can span connected subspaces',
 'first_contest':'Potential attacker/defender encounter at the objective entry; timing unresolved',
 'connector':'Secondary movement between committed territory and another entry sector',
 'split_point':'Choose primary execute or alternate entry; may share staging',
 'execute_preparation':'Last gathering and clearing support before the objective entry',
 'flank':'Different site-entry sector, opening/later-flank timing unresolved',
 'fallback':'Defender receiving/withdrawal support; safety unresolved',
 'rotation_junction':'Assignments and rotations diverge/converge at defender deployment'}
VERSION='typed-route-assemblies-v1'

def program(network,roles,spec,seed):
 r=random.Random(seed^0x2C017);q=spec['soft_preferences'].get('route_complexity',.5);mid=spec['gameplay']['mid']=='contested';episodes={};sequences={}
 for site in ['A','B']:
  main=network['T-'+site+'-main'];available=main[1:-2]
  choices=['frontage-street'] if q<.25 else ['court-edge','building-wrap','oblique-frontage','frontage-street']
  profile=r.choice(choices);selected=[]
  if available and profile!='frontage-street':
   selected=[available[len(available)//2]]
   episodes[selected[0]]=dict(site=site,profile=profile,purpose='Intermediate committed territory; local circulation follows generated footprint',nav_patterns=['dust2-space-0','cache-space-4','train-space-1'],radar_sources=['R09','R14','R17','R18'])
  sequences[site]=dict(profile=profile,episode_nodes=[list(n) for n in selected],main_nodes=[list(n) for n in main],split_node=list(network[('Mid-' if mid else 'local-')+site][0]),complexity=q,scope='Profile is an adaptable local assembly; no required spawn/lobby/fight/site chain. Short paths share roles rather than adding rooms.')
 return episodes,sequences

def assemble(episode,area,faces,center,aisle):
 x0,y0,x1,y1=area.bounds;cx,cy=center;profile=episode['profile'];domain=area;parts=[];openings=[];building=None
 if profile=='building-wrap':
  # A coherent inaccessible building enclosed by connected circulation, not
  # one tiny obstacle in a generic room. Four bands are actual partitions and
  # share circulation openings; roles can span all of them.
  bx0,bx1=cx-3,cx+3;by0,by1=cy-3,cy+3;building=box(bx0,by0,bx1,by1)
  parts=[('north',box(x0,by1,x1,y1)),('south',box(x0,y0,x1,by0)),('west',box(x0,by0,bx0,by1)),('east',box(bx1,by0,x1,by1))]
  center=[cx,(y0+by0)/2]
  for a,b in [('north','west'),('north','east'),('south','west'),('south','east')]:
   pa=dict(parts)[a];pb=dict(parts)[b];shared=pa.boundary.intersection(pb.boundary)
   openings.append((a,b,shared))
 else:
  # An unused building face bounds a court. An oblique footprint is one coherent
  # frontage, not random bevels of every room. Actual travel ports stay on the
  # used faces and the routing point stays in the free court.
  unused=next((f for f in [(-1,0),(1,0),(0,-1),(0,1)] if f not in faces),None)
  depth=min(6,(x1-x0)/3,(y1-y0)/3)
  if unused==(-1,0):
   building=Polygon([(x0,y0),(x0+depth,y0),(x0+depth*.65 if profile=='oblique-frontage' else x0+depth,y1),(x0,y1)])
  elif unused==(1,0):
   building=Polygon([(x1-depth,y0),(x1,y0),(x1,y1),(x1-depth*.65 if profile=='oblique-frontage' else x1-depth,y1)])
  elif unused==(0,-1):
   building=Polygon([(x0,y0),(x1,y0),(x1,y0+depth*.65 if profile=='oblique-frontage' else y0+depth),(x0,y0+depth)])
  elif unused==(0,1):
   building=Polygon([(x0,y1-depth),(x1,y1-depth*.65 if profile=='oblique-frontage' else y1-depth),(x1,y1),(x0,y1)])
  if building is not None:domain=domain.difference(building)
  parts=[('court',domain)]
 return parts,openings,center,building

def bind(p,network,roles,node_spaces,sequences):
 mid='Mid' in roles;bindings=[]
 def attach(rid,kind,nodes,callout=None,relationship=None):
  spaces=sorted({sid for node in nodes for sid,g in node_spaces[node]})
  bindings.append(dict(id=rid,kind=kind,purpose=PURPOSES[kind],spaces=spaces,nodes=[list(n) for n in nodes],callout=callout,relationship=relationship,confidence='authored role grounded in generated connectivity; tactical timing/control unresolved'))
 for site in ['A','B']:
  main=network['T-'+site+'-main'];alt=network[('Mid-' if mid else 'local-')+site];defense=network['CT-'+site+'-deploy']
  split=alt[0] if not mid else roles['Mid'] if site=='A' else roles.get('Mid2',roles['Mid'])
  attach(site+'-main','main_approach',main[1:-1],site+' Main')
  attach(site+'-staging','staging',[main[-2]])
  attach(site+'-execute','execute_preparation',[main[-2]])
  attach(site+'-split','split_point',[split],relationship='Primary versus different entry sector')
  attach(site+'-connector','connector',alt[1:-1],relationship='Mid connector' if mid else 'Local secondary territory')
  attach(site+'-flank','flank',alt[1:-1],site+' side approach')
  attach(site+'-contest','first_contest',[roles[site]],relationship='Site ingress/defender encounter support; not a separate lobby')
  attach(site+'-fallback','fallback',defense[1:-1])
 attach('CT-rotation-junction','rotation_junction',[roles['CT']])
 p['role_bindings']=bindings;p['route_sequences']=sequences
 p['building_footprints']=[dict(id='building-'+str(i),boundary=x['boundary'],purpose=x['purpose']) for i,x in enumerate(p.get('architectural_buildings',[]))]
