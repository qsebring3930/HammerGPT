"""Simplify a flat study contour while protecting route markers and area."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from extract_sections import inside


def signed_area(points):
    return sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))/2


def turn(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]; denominator=dx*dx+dy*dy
    if denominator==0: return math.dist(p,a)
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/denominator))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)


def intersects(a,b,c,d):
    def on(p,u,v):
        return abs(turn(u,v,p))<1e-8 and min(u[0],v[0])-1e-8<=p[0]<=max(u[0],v[0])+1e-8 and min(u[1],v[1])-1e-8<=p[1]<=max(u[1],v[1])+1e-8
    return (turn(a,b,c)*turn(a,b,d)<0 and turn(c,d,a)*turn(c,d,b)<0) or any((on(c,a,b),on(d,a,b),on(a,c,d),on(b,c,d)))


def simple(points):
    if len(points)<3 or len(set(map(tuple,points)))!=len(points) or signed_area(points)<=0: return False
    edges=list(zip(points,points[1:]+points[:1])); count=len(edges)
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges):
            if j<=i or j==i+1 or (i==0 and j==count-1): continue
            if intersects(a,b,c,d): return False
    return True


def boundary(cells,grid=64):
    edges={}
    for x,y in cells:
        for neighbor,a,b in [((x,y-1),(x,y),(x+1,y)),((x+1,y),(x+1,y),(x+1,y+1)),
                             ((x,y+1),(x+1,y+1),(x,y+1)),((x-1,y),(x,y+1),(x,y))]:
            if neighbor not in cells:
                if a in edges: raise ValueError('Nonmanifold cell boundary')
                edges[a]=b
    start=min(edges); current=start; outline=[]
    while current in edges:
        outline.append([current[0]*grid,current[1]*grid]); current=edges.pop(current)
    if current!=start or edges: raise ValueError('Simplification supports a single outline without holes')
    return outline


def simplify(points,protected,tolerance=64):
    original=copy.deepcopy(points); original_area=signed_area(original)
    result=copy.deepcopy(points)
    def acceptable(candidate):
        if not simple(candidate) or abs(signed_area(candidate)/original_area-1)>.15: return False
        if any(not inside(p[0],p[1],candidate) for p in protected): return False
        # Compare original corners and proposed edge samples in both directions.
        for source,target in ((original,candidate),(candidate,original)):
            edges=list(zip(target,target[1:]+target[:1]))
            samples=source+[[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t] for a,b in zip(source,source[1:]+source[:1]) for t in (.25,.5,.75)]
            if any(min(distance(p,a,b) for a,b in edges)>tolerance+1e-6 for p in samples): return False
        return True
    changed=True
    while changed and len(result)>3:
        changed=False
        order=sorted(range(len(result)),key=lambda i:distance(result[i],result[i-1],result[(i+1)%len(result)]))
        for i in order:
            candidate=result[:i]+result[i+1:]
            if acceptable(candidate): result=candidate; changed=True; break
    return result


def triangulate(points):
    if not simple(points): raise ValueError('Expected a simple counterclockwise outline')
    remaining=list(range(len(points))); triangles=[]
    while len(remaining)>3:
        for pos,b in enumerate(remaining):
            a=remaining[pos-1]; c=remaining[(pos+1)%len(remaining)]
            if turn(points[a],points[b],points[c])<=1e-8: continue
            def in_triangle(p):
                return all(turn(u,v,p)>=-1e-8 for u,v in ((points[a],points[b]),(points[b],points[c]),(points[c],points[a])))
            if any(in_triangle(points[i]) for i in remaining if i not in (a,b,c)): continue
            triangles.append([a,b,c]); remaining.pop(pos); break
        else: raise ValueError('Outline could not be triangulated without degeneracy')
    triangles.append(remaining)
    if abs(sum(signed_area([points[i] for i in t]) for t in triangles)-signed_area(points))>1e-5:
        raise ValueError('Triangulation area mismatch')
    return triangles


def plan_simplification(plan,tolerance=64):
    cells={tuple(c) for c in plan['design_choices']['floor_cell_override']}; original=boundary(cells)
    protected=[r['center'][:2] for r in plan['design_choices']['regions']]
    if any(not inside(p[0],p[1],original) for p in protected): raise ValueError('A route marker is outside the starting footprint')
    outline=simplify(original,protected,tolerance); triangulate(outline)
    result=copy.deepcopy(plan); result['kind']='simplified_reference_derived_flat_study'
    result['design_choices']['floor_polygon_override']=outline
    result['simplification']={'original_boundary_segments':len(original),'simplified_boundary_segments':len(outline),
                              'original_area_units_squared':signed_area(original),'simplified_area_units_squared':signed_area(outline),
                              'sampled_boundary_distance_limit_units':tolerance,'protected_route_markers':len(protected),
                              'limits':['Protects route marker positions, not corridor width or tactical branching.',
                                        'Boundary distance is checked at vertices and quarter-edge samples, not a continuous error bound.']}
    result['adaptations'].append('Replaced the grid outline with a simplified polygon and triangulated floor; source NAV evidence is unchanged.')
    return result


def preview(plan,original):
    before=boundary({tuple(c) for c in original['design_choices']['floor_cell_override']}); after=plan['design_choices']['floor_polygon_override']
    low=[min(p[i] for p in before+after) for i in (0,1)]; high=[max(p[i] for p in before+after) for i in (0,1)]
    scale=min(900/max(1,high[0]-low[0]),650/max(1,high[1]-low[1]))
    def coords(points): return ' '.join(f'{50+(p[0]-low[0])*scale:.2f},{740-(p[1]-low[1])*scale:.2f}' for p in points)
    return '\n'.join(['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="820">','<rect width="1000" height="820" fill="#101827"/>',
        '<text x="40" y="35" fill="white" font-family="Arial" font-size="22">Section outline: original and simplified</text>',
        f'<polygon points="{coords(after)}" fill="#36586f" stroke="#83d6b0" stroke-width="4"/>',
        f'<polygon points="{coords(before)}" fill="none" stroke="#ffb454" stroke-width="2" stroke-dasharray="6 4"/>',
        '<text x="40" y="790" fill="white" font-family="Arial" font-size="15">Green: simplified walls · dashed orange: original outline · elevations remain flattened</text></svg>'])


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--input',required=True,type=Path); parser.add_argument('--output',required=True,type=Path); parser.add_argument('--tolerance',type=float,default=64)
    args=parser.parse_args()
    if not math.isfinite(args.tolerance) or not 0<=args.tolerance<=128: parser.error('Tolerance must be between 0 and 128 units')
    if args.output.exists() or args.output.with_suffix('.svg').exists(): parser.error('Choose new output paths')
    raw=args.input.read_bytes(); original=json.loads(raw); result=plan_simplification(original,args.tolerance)
    result['input_study_sha256']=hashlib.sha256(raw).hexdigest(); args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)); args.output.with_suffix('.svg').write_text(preview(result,original),encoding='utf-8')
    print(json.dumps(result['simplification']))


if __name__=='__main__': main()
