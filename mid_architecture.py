"""Joint offset frontages and continuous street alignments for contested Mid.

Reservations prevent crossings, not architectural room boundaries. Offsets are
chosen as a coherent court/street frontage system, not bends per corridor edge.
"""
import math,random
from shapely.geometry import Polygon,box,LineString
from shapely.ops import unary_union
from shapely.affinity import rotate,translate

VERSION='mid-offset-street-frontages-v2'
def compose(cells,centers,neighbors,roles,aisle,seed,organization=None):
 r=random.Random(seed^0x714CA)
 # Offset one functional frontage family, not every row/column or every lane.
 # Choose a building-aligned receiving frontage opposite an unused face.
 # Other streets retain their straight alignments.
 family=r.choice(['main-frontages','mid-connector-frontages','deployment-frontages'])
 positions={n:list(centers[n]) for n in neighbors}
 for n in sorted(neighbors):
  adjacent_sites=[name for name in ('A','B') if roles[name] in neighbors[n]]
  selected=(family=='deployment-frontages' and n in (roles['T'],roles['CT'])) or bool(adjacent_sites and ((family=='mid-connector-frontages' and abs(n[0]-roles['Mid'][0])+abs(n[1]-roles['Mid'][1])<=1) or family=='main-frontages'))
  if not selected:continue
  used={(q[0]-n[0],q[1]-n[1]) for q in neighbors[n]}
  closed=next((f for f in [(-1,0),(1,0),(0,-1),(0,1)] if f not in used),None)
  if closed:
   amount=r.choice([2.4,3.2]);positions[n]=[centers[n][i]-closed[i]*amount for i in range(2)]
 ports={};edges={tuple(sorted((n,q))) for n in neighbors for q in neighbors[n]}
 for a,b in sorted(edges):
  ca,cb=positions[a],positions[b];shared=cells[a].boundary.intersection(cells[b].boundary)
  axis=0 if a[0]!=b[0] else 1;value=list(shared.coords)[0][axis];t=(value-ca[axis])/(cb[axis]-ca[axis]);point=[ca[i]+t*(cb[i]-ca[i]) for i in range(2)]
  ports[(a,b)]=point
 shapes={};decisions=[]
 for n in sorted(neighbors):
  area=cells[n];x0,y0,x1,y1=area.bounds;cx,cy=positions[n];role=next((k for k,v in roles.items() if v==n),None)
  joins=[ports[tuple(sorted((n,q)))] for q in neighbors[n]]
  # Main lanes follow actual adjacent court/frontage locations rather than
  # forcing the axis through every cell centre. Building mass is the explicit
  # complement of these jointly reserved playable footprints.
  ribbons=[]
  for p in joins:
   length=math.dist(p,[cx,cy]);beyond=[p[i]+aisle*(p[i]-[cx,cy][i])/length for i in range(2)]
   ribbons.append(LineString([[cx,cy],beyond]).buffer(aisle/2,cap_style=2,join_style=2).intersection(area))
  direction=max(joins,key=lambda p:math.dist(p,[cx,cy]));angle=math.degrees(math.atan2(direction[1]-cy,direction[0]-cx))
  if role in ('A','B'):
   # Keep a complete plant/holding band; entry-facing court adapts to real
   # opening positions. The inaccessible footprint forms the whole boundary.
   core=box(x0+3,y1-10,x1-3,y1)
   banks=[box(x0,y1-8,x1,y1),core]+ribbons
   shape=unary_union(banks).convex_hull.intersection(area)
   profile='entry-shaped-objective-court'
  elif role in ('Mid','Mid2'):
   # Broad contested court, offset bank side and several distributed mouths.
   # No central obstruction at the contest marker; pressure to both sites is
   # provided by the network, not a central label.
   if organization=='contested_street':
    other=roles['Mid2' if role=='Mid' else 'Mid'];angle=math.degrees(math.atan2(centers[other][1]-cy,centers[other][0]-cx))
   core=rotate(box(-8,-5.5 if organization=='contested_street' else -6,8,5.5 if organization=='contested_street' else 6),angle,origin=(0,0));core=translate(core,cx,cy).intersection(area.buffer(-.8))
   shape=unary_union([core]+ribbons).convex_hull.intersection(area)
   profile='distributed-mouth-mid-court'
  elif role in ('T','CT'):
   core=rotate(box(-8,-5,8,5),angle,origin=(0,0));core=translate(core,cx,cy).intersection(area.buffer(-.8))
   shape=unary_union([core]+ribbons).convex_hull.intersection(area);profile='deployment-frontage'
  else:
   # Through street vs widening at an actual change of direction/junction.
   vectors=[(p[0]-cx,p[1]-cy) for p in joins]
   straight=len(vectors)==2 and sum(a*b for a,b in zip(*vectors))<0 and abs(vectors[0][0]*vectors[1][1]-vectors[0][1]*vectors[1][0])<20
   radius=aisle/2 if straight else aisle/2+1.2
   core=rotate(box(-radius,-radius*.75,radius,radius*.75),angle,origin=(0,0));core=translate(core,cx,cy).intersection(area)
   # A turn/junction is a continuous clearing court. Filling the inside wedge
   # avoids acute leftover wall pockets from overlapping oblique ribbon arms.
   shape=unary_union([core]+ribbons).convex_hull.intersection(area)
   profile='continuous-street' if straight else 'turn-or-split-frontage'
  if shape.geom_type!='Polygon':raise ValueError('Joint frontage produced disconnected playable footprint')
  shapes[n]=shape
  decisions.append(dict(node=list(n),profile=profile,frontage_family=family,frontage_point=[cx,cy],openings=joins,radar_sources=['R09','R14','R17','R18'],nav_patterns=['dust2-space-0','cache-space-1','cache-space-4','train-space-1'],scope='Reference-informed relationships; offsets, absolute widths and court construction authored shared rules. No NAV areas treated as rooms.'))
 if organization=='contested_street':
  # The semantic street is actual continuous street space, not two labelled
  # courts with a doorway neck between them. Its frontage band spans both
  # reservations while side mouths widen only where circulation branches.
  band=LineString([positions[roles['Mid']],positions[roles['Mid2']]]).buffer((aisle+2)/2,cap_style=2,join_style=2)
  for name in ('Mid','Mid2'):
   n=roles[name];shapes[n]=shapes[n].union(band.intersection(cells[n]))
 return shapes,positions,decisions
