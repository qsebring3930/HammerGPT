"""Extract local NAV route neighborhoods as reference topology examples."""
import argparse
import hashlib
import html
import json
import math
import heapq
from pathlib import Path

from build_routes import center


def extract(nav,graph,target_length=1200,allow_unnamed=False):
    if graph['provenance']['nav_source']!=nav['source']:
        raise ValueError('Graph and NAV source mismatch')
    routes=[r for r in graph['example_routes'] if r['start']=='TSpawn' and r['goal']=='BombsiteA']
    areas={a['id']:a for a in nav['areas'] if a['hull']==graph['hull'] and a['movable_mesh_id']==0xffffffff}
    method='middle segment of recorded representative TSpawn-to-A route'
    if routes:
        route=routes[0]['nav_area_path']
    elif allow_unnamed:
        associations=[a for a in graph.get('spawn_alignment',[]) if a['classname']=='info_player_terrorist' and a['nearest_nav_area'] in areas]
        seed=associations[0]['nearest_nav_area'] if associations else min(areas)
        costs={seed:0}; previous={}; queue=[(0,seed)]
        while queue:
            cost,key=heapq.heappop(queue)
            if cost!=costs[key]: continue
            for connection in areas[key]['connections']:
                target=connection['target']
                if target not in areas: continue
                candidate=cost+math.dist(center(areas[key]),center(areas[target]))
                if candidate<costs.get(target,math.inf):
                    costs[target]=candidate; previous[target]=key; heapq.heappush(queue,(candidate,target))
        goal=max(costs,key=costs.get); route=[goal]
        while route[-1]!=seed: route.append(previous[route[-1]])
        route.reverse()
        if len(route)<6: raise ValueError('No sufficiently long recorded path for unnamed section')
        method='middle segment of shortest recorded NAV path to farthest reachable centroid; start uses nearest-centroid spawn association when available; no objective association'
    else:
        raise ValueError('No recorded TSpawn-to-A example route; use --allow-unnamed for generic NAV path extraction')
    start=len(route)//3; path=[route[start]]; distance=0
    for a,b in zip(route,route[1:]):
        if a not in areas or b not in areas or b not in {c['target'] for c in areas[a]['connections']}:
            raise ValueError('Example route does not follow recorded NAV connections')
    for key in route[start+1:]:
        distance+=math.dist(center(areas[path[-1]]),center(areas[key])); path.append(key)
        if distance>=target_length and len(path)>=6: break
    selected=set(path); centers=[center(areas[k]) for k in path]
    # One-hop context; require proximity to the path so a long link cannot swallow another section.
    for key in path:
        for connection in areas[key]['connections']:
            target=connection['target']
            if target in areas and min(math.dist(center(areas[target]),p) for p in centers)<384:
                selected.add(target)
    links=[{'source':k,'target':c['target']} for k in sorted(selected) for c in areas[k]['connections'] if c['target'] in selected]
    origin=centers[0]
    polygons=[{'nav_area_id':k,'corners':areas[k]['corners']} for k in sorted(selected)]
    points=[p for polygon in polygons for p in polygon['corners']]
    bounds={'min':[min(p[i] for p in points) for i in range(3)],'max':[max(p[i] for p in points) for i in range(3)]}
    labels={a['area_id']:a['label'] for a in graph['area_assignments']}
    # Downsample centroids before describing bends; retain raw path for auditing.
    samples=[centers[0]]
    for p in centers[1:]:
        if math.dist(p,samples[-1])>=128: samples.append(p)
    if samples[-1]!=centers[-1]: samples.append(centers[-1])
    bends=[]
    for a,b,c in zip(samples,samples[1:],samples[2:]):
        u=[b[i]-a[i] for i in range(2)]; v=[c[i]-b[i] for i in range(2)]
        if math.hypot(*u)*math.hypot(*v)>1e-6:
            bends.append(round(math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],sum(x*y for x,y in zip(u,v)))),2))
    return {'schema_version':1,'kind':'reference_nav_section','model_training_performed':False,
            'nav_source':nav['source'],'map_source':graph['provenance']['map_source'],
            'origin':origin,'bounds':bounds,'polygons':polygons,'recorded_connections':links,'section_selection_method':method,
            'route_nav_area_ids':path,'route_centers':centers,
            'area_labels':{str(k):labels.get(k) for k in sorted(selected)},
            'measurements':{'nav_polygons':len(polygons),'recorded_directed_links':len(links),
                            'route_center_distance_units':round(distance,2),'height_span_units':round(bounds['max'][2]-bounds['min'][2],2),
                            'sampled_signed_turn_angles_degrees':bends},
            'limits':['NAV outlines describe walkable regions, not original architectural walls or rooms.',
                      'This section follows recorded NAV links; traversal flags, ladders, and map repair freshness are not evaluated.']}


def inside(x,y,polygon):
    result=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: result=not result
    return result


def study(section):
    grid=64; origin=section['origin']; cells=set()
    def local(p): return (p[0]-origin[0],p[1]-origin[1])
    def disk(point,radius=96):
        x,y=local(point)
        for ix in range(math.floor((x-radius)/grid),math.ceil((x+radius)/grid)):
            for iy in range(math.floor((y-radius)/grid),math.ceil((y+radius)/grid)):
                if math.hypot((ix+.5)*grid-x,(iy+.5)*grid-y)<=radius: cells.add((ix,iy))
    for polygon in section['polygons']:
        points=[local(p) for p in polygon['corners']]
        for x in range(math.floor(min(p[0] for p in points)/grid),math.ceil(max(p[0] for p in points)/grid)):
            for y in range(math.floor(min(p[1] for p in points)/grid),math.ceil(max(p[1] for p in points)/grid)):
                if inside((x+.5)*grid,(y+.5)*grid,points): cells.add((x,y))
    centers={p['nav_area_id']:[sum(v[i] for v in p['corners'])/len(p['corners']) for i in range(3)] for p in section['polygons']}
    for link in section['recorded_connections']:
        a,b=centers[link['source']],centers[link['target']]; length=math.dist(a,b)
        for step in range(max(1,math.ceil(length/32))+1):
            t=step/max(1,math.ceil(length/32)); disk([a[i]+t*(b[i]-a[i]) for i in range(3)])
    # Discard isolated raster fragments, recording the simplification; never infer measured NAV links from this union.
    seed=min(cells,key=lambda c:math.hypot((c[0]+.5)*grid,(c[1]+.5)*grid)); reached={seed}; todo=[seed]
    while todo:
        x,y=todo.pop()
        for n in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if n in cells and n not in reached: reached.add(n); todo.append(n)
    removed=len(cells-reached); cells=reached
    # Remove corner-only contacts, which cannot form a manifold floor surface.
    changed=True
    while changed:
        changed=False
        for x,y in sorted(cells):
            for dy in (-1,1):
                if (x+1,y+dy) in cells and (x+1,y) not in cells and (x,y+dy) not in cells:
                    cells.add((x+1,y)); changed=True
    regions=[]
    route=section['route_centers']; stride=max(1,len(route)//6)
    for index,p in enumerate(route[::stride]):
        x,y=local(p); regions.append({'id':f'SectionLight{index}','center':[x,y,0],'size':[256,256,256]})
    return {'schema_version':1,'kind':'reference_derived_flat_study','status':'proposal','model_training_performed':False,
            'source_section':section['nav_source'],'source_nav_area_ids':[p['nav_area_id'] for p in section['polygons']],
            'design_choices':{'regions':regions,'connections':[],'corridor_width_units':192,'floor_cell_override':[list(c) for c in sorted(cells)]},
            'adaptations':['Translated reference section to origin; projected all elevations onto a flat walking surface.',
                           'Rasterized outlines at 64 units; widened recorded link corridors to join narrow gaps.',
                           'Added boundary walls; these are study geometry, not extracted source walls.',
                           f'Removed {removed} isolated raster cells; filled corner-only contacts.'],
            'limits':['This is a simplified reference-derived section, not an original generated map or learned model output.',
                      'Flattening can merge vertically separated areas and changes traversal. NAV connections remain evidence only.']}


def svg(section):
    points=[p for poly in section['polygons'] for p in poly['corners']]; low=section['bounds']['min']; high=section['bounds']['max']
    scale=min(900/max(1,high[0]-low[0]),650/max(1,high[1]-low[1]))
    def xy(p): return (50+(p[0]-low[0])*scale,740-(p[1]-low[1])*scale)
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="820">','<rect width="1000" height="820" fill="#101827"/>',
           '<text x="40" y="35" fill="white" font-family="Arial" font-size="22">Recorded reference section — NAV outlines</text>']
    for poly in section['polygons']:
        coords=' '.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,poly['corners']))
        parts.append(f'<polygon points="{coords}" fill="#36586f" stroke="#92b3c5" stroke-width="1"/>')
    coords=' '.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,section['route_centers']))
    parts.append(f'<polyline points="{coords}" fill="none" stroke="#ffb454" stroke-width="4"/>')
    parts.append('<text x="40" y="790" fill="white" font-family="Arial" font-size="15">Orange: recorded route · blue: walkable NAV polygons · outlines are not architectural walls</text></svg>')
    return '\n'.join(parts)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--nav',required=True,type=Path); parser.add_argument('--graph',required=True,type=Path); parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--allow-unnamed',action='store_true',help='Allow generic recorded NAV path when named objective routes are unavailable')
    args=parser.parse_args(); paths=[args.output,args.output.with_suffix('.svg'),args.output.with_name(args.output.stem+'-study.json')]
    if any(p.exists() for p in paths): parser.error('Choose new output paths')
    raw=args.nav.read_bytes(); graphraw=args.graph.read_bytes(); section=extract(json.loads(raw),json.loads(graphraw),allow_unnamed=args.allow_unnamed)
    section['provenance']={'nav_export_sha256':hashlib.sha256(raw).hexdigest(),'graph_sha256':hashlib.sha256(graphraw).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(section,indent=2)); paths[1].write_text(svg(section),encoding='utf-8'); paths[2].write_text(json.dumps(study(section),indent=2))
    print(json.dumps({'section':str(args.output),**section['measurements']}))


if __name__=='__main__': main()
