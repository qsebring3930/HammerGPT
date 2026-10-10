"""Stage 3 planar space/mass/opening representation and geometry-derived nav.

Spaces are architectural partitions, not strategic nodes. Walls are explicit
boundaries with explicit openings. This constructs no floors, meshes or VMAPs.
"""
import heapq
import math

import numpy as np
from shapely import set_precision
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from shapely import contains_xy


def compile_composition(program):
    spaces={s['id']:Polygon(s['boundary'],s.get('holes',[])) for s in program['spaces']}
    envelope=Polygon(program['envelope'])
    if len(spaces)!=len(program['spaces']) or program['boundary_thickness']<=0:
        raise ValueError('Spaces must have unique IDs and positive boundary thickness.')
    for pid,space in spaces.items():
        if not space.is_valid or space.area<=0 or not envelope.covers(space):
            raise ValueError('Invalid or out-of-envelope space: '+pid)
    items=list(spaces.items())
    for i,(pid,space) in enumerate(items):
        for other_id,other in items[i+1:]:
            if space.intersection(other).area>1e-8:
                raise ValueError('Overlapping architectural spaces: '+pid+' / '+other_id)
    floor_extent=unary_union(list(spaces.values()))
    borders=unary_union([s.boundary for s in spaces.values()])
    boundary_mass=borders.buffer(program['boundary_thickness']/2,cap_style=2,join_style=2)
    opening_cuts=[]
    for opening in program['openings']:
        a,b=opening['spaces'];line=LineString(opening['aperture'])
        if a not in spaces or b not in spaces:raise ValueError('Opening needs two architectural spaces.')
        tolerance=program.get('geometric_precision_plan_units',0)*2
        boundaries=[spaces[k].boundary.buffer(tolerance) if tolerance else spaces[k].boundary for k in (a,b)]
        if not all(boundary.covers(line) for boundary in boundaries):
            raise ValueError('Opening must lie on the actual shared boundary: '+opening['id'])
        opening_cuts.append(line.buffer(program['boundary_thickness'],cap_style=2))
    walls=boundary_mass.difference(unary_union(opening_cuts))
    fixtures=unary_union([Polygon(m['boundary']) for m in program['internal_masses']])
    if not fixtures.is_empty and not floor_extent.covers(fixtures):raise ValueError('Internal mass lies outside architectural footprint.')
    walkable=floor_extent.difference(walls.union(fixtures)).buffer(0)
    if program.get('geometric_precision_plan_units'):
        # Oblique Boolean operations can leave 1e-18-area floating-point
        # polygons. Use a declared precision grid, never area-filter genuine
        # disconnected space. Navigation/connectivity gates remain unchanged.
        walkable=set_precision(walkable,program['geometric_precision_plan_units'])
    masses=envelope.difference(walkable).buffer(0)
    visibility={}
    for posture,eye in (('standing',program.get('engine_scale',{}).get('standing_eye_source_units',64)),('crouched',program.get('engine_scale',{}).get('crouched_eye_source_units',46))):
        opaque=unary_union([Polygon(m['boundary']) for m in program['internal_masses'] if m.get('height_source_units',160)>=eye])
        visibility['visibility_'+posture]=floor_extent.difference(walls.union(opaque))
    return {'spaces':spaces,'walkable':walkable,'solid':masses,'walls':walls,'fixtures':fixtures,
            'opening_cuts':opening_cuts,'envelope':envelope,**visibility}


class DerivedNavigation:
    def __init__(self,compiled,step=.5,blocked=None):
        self.walkable=compiled['walkable'] if blocked is None else compiled['walkable'].difference(blocked)
        self.step=step;x0,y0,x1,y1=compiled['envelope'].bounds
        self.xs=np.arange(x0+step/2,x1,step);self.ys=np.arange(y0+step/2,y1,step)
        x,y=np.meshgrid(self.xs,self.ys);self.mask=contains_xy(self.walkable,x,y)
        self.h,self.w=self.mask.shape;self.indices=np.argwhere(self.mask)
        self.coordinates=np.c_[self.xs[self.indices[:,1]],self.ys[self.indices[:,0]]]
        self.neighbor_cache={};self.path_cache={};self.snap_cache={}
    def snap(self,point):
        key=tuple(point)
        if key in self.snap_cache:return self.snap_cache[key]
        if not self.walkable.covers(Point(point)):return None
        distances=np.sum((self.coordinates-np.array(point))**2,axis=1);i=int(np.argmin(distances))
        if math.sqrt(float(distances[i]))>self.step*math.sqrt(2):return None
        result=tuple(self.indices[i]);self.snap_cache[key]=result;return result
    def point(self,index):return [float(self.xs[index[1]]),float(self.ys[index[0]])]
    def path(self,start,end):
        key=(tuple(start),tuple(end))
        if key in self.path_cache:return self.path_cache[key]
        source,target=self.snap(start),self.snap(end)
        if source is None or target is None:return None
        costs={source:0.};parent={};queue=[(0.,0.,source)]
        while queue:
            _,cost,p=heapq.heappop(queue)
            if cost!=costs.get(p):continue
            if p==target:
                indices=[p]
                while p!=source:p=parent[p];indices.append(p)
                points=[list(start)]+[self.point(i) for i in reversed(indices)]+[list(end)]
                # Exact line coverage removes grid zigzags without crossing a
                # wall or solid mass. Navigation is derived from complete space.
                simple=[points[0]];i=0
                while i<len(points)-1:
                    j=len(points)-1
                    while j>i+1 and not self.walkable.covers(LineString([points[i],points[j]])):j-=1
                    simple.append(points[j]);i=j
                if not all(self.walkable.covers(LineString([a,b])) for a,b in zip(simple,simple[1:])):return None
                result={'points':simple,'length':LineString(simple).length,'grid_cost':cost,
                        'numerical_resolution':self.step,'smoothing':'exact walkable-space line coverage'}
                self.path_cache[key]=result
                self.path_cache[(tuple(end),tuple(start))]={**result,'points':list(reversed(simple))}
                return result
            if p not in self.neighbor_cache:
                neighbors=[]
                for dy,dx in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1)):
                    q=(p[0]+dy,p[1]+dx)
                    if not(0<=q[0]<self.h and 0<=q[1]<self.w and self.mask[q]):continue
                    if dy and dx and not(self.mask[p[0],q[1]] and self.mask[q[0],p[1]]):continue
                    if not self.walkable.covers(LineString([self.point(p),self.point(q)])):continue
                    neighbors.append((q,self.step*math.hypot(dx,dy)))
                self.neighbor_cache[p]=neighbors
            for q,delta in self.neighbor_cache[p]:
                value=cost+delta
                if value<costs.get(q,float('inf')):
                    costs[q]=value;parent[q]=p
                    priority=value+self.step*math.hypot(q[0]-target[0],q[1]-target[1])
                    heapq.heappush(queue,(priority,value,q))
        return None


def observed_openings(program,compiled,step=.5):
    """Detect passable cross-partition boundaries, not connection annotations."""
    records=[];leaks=[]
    for i,left in enumerate(program['spaces']):
        for right in program['spaces'][i+1:]:
            boundary=compiled['spaces'][left['id']].boundary.intersection(compiled['spaces'][right['id']].boundary)
            if boundary.length==0:continue
            geometries=list(boundary.geoms) if hasattr(boundary,'geoms') else [boundary]
            for line in geometries:
                if not isinstance(line,LineString) or not line.length:continue
                for d in np.arange(step/2,line.length,step):
                    point=line.interpolate(float(d))
                    tangent=np.array(line.interpolate(min(line.length,d+step/4)).coords[0])-np.array(line.interpolate(max(0,d-step/4)).coords[0])
                    tangent=tangent/(np.linalg.norm(tangent) or 1);normal=np.array([-tangent[1],tangent[0]])
                    cross=LineString([np.array(point.coords[0])-normal*program['boundary_thickness'],np.array(point.coords[0])+normal*program['boundary_thickness']])
                    if compiled['walkable'].covers(cross):
                        matches=[o['id'] for o in program['openings'] if set(o['spaces'])=={left['id'],right['id']} and LineString(o['aperture']).distance(point)<=step/2]
                        record={'spaces':[left['id'],right['id']],'point':list(point.coords[0]),'declared_openings':matches}
                        records.append(record)
                        if not matches:leaks.append(record)
    return {'observed_passable_boundary_samples':records,'unintended_openings':leaks,
            'resolution':step,'scope':'Sampling plus exact free-space crossing tests; no graph edge is accepted solely because it was declared.'}
