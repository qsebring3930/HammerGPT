"""Limited seeded architectural grammar, not authored-layout mutation.

Each site complex is assembled from local reference-informed spatial rules.
Independent macro choices place/orient complexes and deployments. A physical
router chooses circulation around reserved masses. No seed-specific branches,
coordinate overrides, imported authored layouts or automatic resampling.
"""
import argparse
import copy
import hashlib
import heapq
import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw
from shapely.geometry import Polygon,LineString,Point,box,mapping
from shapely.ops import unary_union
from shapely import contains_xy
from semantic_pipeline import digest,GameplayValidator,ROOT as PROJECT_ROOT
from playable_composition import compile_composition
from p04_comparison_round import render

ROOT=PROJECT_ROOT

def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
def stream(seed,name):return random.Random(int(hashlib.sha256(f'{seed}:{name}'.encode()).hexdigest(),16))

def local_rules(site,seed,cfg):
    r=stream(seed,'local-'+site)
    params={k:r.choice(cfg[k+'_choices']) for k in ('court_width','court_depth','staging_depth','investment_depth','receiving_depth','side_gallery_width')}
    params['gallery_face']=r.choice(['west','east'])
    params['frontage']=r.choice(['entry_wing','deep_plant_wing'])
    params['staging_frontage']=r.choice(['recessed_loading','open_forecourt'])
    params['investment_depth']=params['investment_depth'] if site=='B' else 0
    w=params['court_width'];h=params['court_depth'];d=params['staging_depth'];v=params['investment_depth'];rd=params['receiving_depth'];gw=params['side_gallery_width']
    x=4+gw;y=4;sy=y+d+v;ry=sy+h;total_w=x+w+4;total_h=ry+rd+4
    p=dict(spaces=[],openings=[],internal_masses=[],annotations={},allocations=[],objective_zones={},defender_positions={})
    def space(i,b,why):p['spaces'].append(dict(id=site+'_'+i,boundary=b,description=why))
    def door(i,a,b,line,why):p['openings'].append(dict(id=site+'_'+i,spaces=[site+'_'+a,site+'_'+b],aperture=line,purpose=why))
    def mass(i,b,ht,why):p['internal_masses'].append(dict(id=site+'_'+i,boundary=b,height_source_units=ht,height_class='low_cover' if ht==48 else 'full_height',purpose=why))
    space('staging',rect(x,y,x+w,y+d),'Deployment approach receives attackers behind frontage; choose primary or local alternate commitment.')
    if site=='B':
        space('investment',rect(x,y+d,x+w,sy),'Invest in workshop territory; entrance and execute threshold lie on different sides of attached frontage.')
        door('investment_access','staging','investment',[[x+3,y+d],[x+8,y+d]],'Acquire workshop territory before primary execute')
        mass('investment_building',rect(x+w-9,y+d,x+w,y+d+4),160,'Workshop building frontage makes investment a clearing phase, not another route edge.')
    space('court',rect(x,sy,x+w,ry),'Objective court: primary, local alternate and rear defender receiving faces with distinct clearing sectors.')
    space('receiving',rect(x,ry,x+w,ry+rd),'Fallback/regather occupy local receiving frontage within defender circulation.')
    source='investment' if site=='B' else 'staging'
    door('main',source,'court',[[x+w-8,sy],[x+w-3,sy]],'Primary site entry')
    door('rear','court','receiving',[[x+8,ry],[x+13,ry]],'Opposite-side defender access and retake approach')
    alt_y=sy+h/2
    if site=='B':
        split=sy-4
        space('gallery_lower',rect(4,y,x,split),'Local alternate unloading frontage; ends before CT receiving.')
        space('gallery_upper',rect(x-8,split,x,alt_y+5),'Building transition narrows the unloading frontage before the alternate site sector.')
        door('gallery_transition','gallery_lower','gallery_upper',[[x-7,split],[x-2,split]],'Clear local receiving-width transition')
        alt_source='gallery_lower';alt_target='gallery_upper'
    else:
        space('gallery',rect(4,y,x,alt_y+5),'Short local frontage alternative; no rear-service exit.')
        alt_source=alt_target='gallery'
    door('gallery_access','staging',alt_source,[[x,y+d-8],[x,y+d-3]],'Local alternate commitment near the encounter fork changes site entry sector')
    door('side',alt_target,'court',[[x,alt_y-2.5],[x,alt_y+2.5]],'Alternate sector; not an attacker bypass into defender circulation')
    wing_y=sy+7 if params['frontage']=='entry_wing' else sy+h-12
    mass('site_building',rect(x+w-9,wing_y,x+w,wing_y+6),160,'Attached site building divides entry clearing from plant/receiving sectors.')
    if params['staging_frontage']=='recessed_loading':
        mass('staging_building',rect(x+1,y,x+8,y+3),160,'Attached frontage keeps arrival, staging and decision space integrated.')
    mass('rear_building',rect(x,ry+rd-3,x+6,ry+rd),160,'Rear building edge bounds a local preparation pocket without allocating a separate room.')
    mass('plant_cover',rect(x+7,ry-6,x+10,ry-4),48,'Declared low cover protects plant space but does not block standing sightlines.')
    points={site:[x+14,ry-5],site+'_prep':[x+w/2,y+3.5],site+'_fight':[x+4.5,y+d-4],
        site+'_entry':[x+w-5.5,sy+2.5],site+'_side':[x+2.5,alt_y],site+'_hold':[x+16,ry-8],
        site+'_rear':[x+w-7,ry+rd/2],site+'_retake':[x+10.5,ry+rd/2]}
    if site=='B':points['B_territory']=[x+w-12,sy-4]
    p['annotations']={k:dict(point=v,interpretation='Role annotates composed architectural space; does not create floor.') for k,v in points.items()}
    p['objective_zones'][site]=rect(x+5,ry-10,x+18,ry-2)
    p['defender_positions'][site+'_court']=[x+16,ry-8]
    p['defender_positions'][site+'_gallery']=[x-4,alt_y-1]
    if site=='B':p['defender_positions']['B_investment']=[x+6,y+d+3]
    p['allocations']=[dict(id=site+'_fallback',boundary=rect(x+w-11,ry+2,x+w-3,ry+rd-2),purpose='Receiving frontage beside assigned defender circulation; independent design assumption.'),
        dict(id=site+'_regather',boundary=rect(x+7,ry+2,x+14,ry+rd-2),purpose='Preparation next to actual rear site threshold, not an extra room.')]
    # External route sockets lie on architectural boundaries, not on semantic nodes.
    p['sockets']={'attack':dict(point=[x+w/2,y],normal=[0,-1],space=site+'_staging'),
        'defense':dict(point=[x+w-7,ry+rd],normal=[0,1],space=site+'_receiving')}
    # Reflection is a local alternate-face rule, not a whole-layout transformation.
    if params['gallery_face']=='east':map_local(p,lambda q:[total_w-q[0],q[1]],lambda q:[-q[0],q[1]])
    return p,[total_w,total_h],params

def map_local(p,f,vector):
    for kind in ('spaces','internal_masses','allocations'):
        for item in p[kind]:item['boundary']=[f(q) for q in item['boundary']]
    for item in p['openings']:item['aperture']=[f(q) for q in item['aperture']]
    for item in p['annotations'].values():item['point']=f(item['point'])
    p['objective_zones']={k:[f(q) for q in v] for k,v in p['objective_zones'].items()}
    p['defender_positions']={k:f(v) for k,v in p['defender_positions'].items()}
    for socket in p['sockets'].values():socket['point']=f(socket['point']);socket['normal']=vector(socket['normal'])

def rotate(q,k):
    x,y=q
    return [[x,y],[-y,x],[-x,-y],[y,-x]][k%4]

def arrangement(seed,cfg,sizes):
    r=stream(seed,'macro');axis=r.choice(cfg['arrangement_axes']);relationship=r.choice(cfg['B_facing_relationships'])
    width,height=cfg['world'];centers={};base=0 if axis=='northbound' else 3
    rotations={'A':base,'B':(base+{'parallel':0,'inward':1,'outward':-1}[relationship])%4}
    depths={'A':r.choice([-16,-6,6,16]),'B':r.choice([-16,-6,6,16])}
    lateral={'A':r.randint(-8,8),'B':r.randint(-8,8)}
    # Packing depends on actual complex extents, not a fixed authored floorplan.
    extents={s:(sizes[s] if rotations[s]%2==0 else list(reversed(sizes[s]))) for s in ('A','B')}
    gap=r.choice([10,14,18])
    if axis=='northbound':
        centers={'A':[width/2-gap/2-extents['A'][0]/2,height/2+depths['A']],
                 'B':[width/2+gap/2+extents['B'][0]/2,height/2+depths['B']]}
    else:
        centers={'A':[width/2+depths['A'],height/2-gap/2-extents['A'][1]/2],
                 'B':[width/2+depths['B'],height/2+gap/2+extents['B'][1]/2]}
    for s in ('A','B'):
        centers[s]=[max(20+extents[s][i]/2,min(cfg['world'][i]-20-extents[s][i]/2,centers[s][i])) for i in range(2)]
    return dict(axis=axis,B_facing_relationship=relationship,rotations=rotations,complex_centers=centers,
        depth_offsets=depths,packing_gap=gap,deployment={},routing_order=r.choice(cfg['routing_orders']))

def orient_module(local,size,k,center):
    p=copy.deepcopy(local);corners=[rotate(q,k) for q in rect(0,0,*size)]
    xs=[q[0] for q in corners];ys=[q[1] for q in corners]
    shift=[center[0]-(max(xs)+min(xs))/2,center[1]-(max(ys)+min(ys))/2]
    map_local(p,lambda q:[rotate(q,k)[i]+shift[i] for i in range(2)],lambda q:rotate(q,k))
    # Reserve the actual compound extent, not the four-unit authoring padding.
    # The former padding forced extra circulation detours without protecting any
    # building or playable footprint. Interior unplayable areas stay reserved.
    reservation=box(*unary_union([Polygon(s['boundary']) for s in p['spaces']]).bounds)
    return p,reservation

def deployment_ports(center,size,targets):
    cx,cy=center;w,h=size;groups={};out={}
    for site,target in targets.items():
        dx,dy=target[0]-cx,target[1]-cy
        face=('east' if dx>0 else 'west') if abs(dx)/(w/2)>abs(dy)/(h/2) else ('north' if dy>0 else 'south')
        groups.setdefault(face,[]).append(site)
    for face,sites in groups.items():
        for i,site in enumerate(sorted(sites)):
            offset=0 if len(sites)==1 else (-4 if i==0 else 4)
            if face in ('east','west'):n=[1 if face=='east' else -1,0];pt=[cx+n[0]*w/2,cy+offset]
            else:n=[0,1 if face=='north' else -1];pt=[cx+offset,cy+n[1]*h/2]
            out[site]=dict(point=pt,normal=n)
    return out

def orthogonal_route(free,start,end,step):
    """Deterministic four-neighbour routing; no graph edge creates walkable floor."""
    x0,y0,x1,y1=free.bounds;xs=np.arange(step/2,x1,step);ys=np.arange(step/2,y1,step)
    xx,yy=np.meshgrid(xs,ys);mask=contains_xy(free,xx,yy);indices=np.argwhere(mask)
    if not len(indices):return None
    coords=np.c_[xs[indices[:,1]],ys[indices[:,0]]]
    def attachment(p):
        order=np.argsort(np.sum((coords-np.array(p))**2,axis=1))[:24]
        for i in order:
            q=list(coords[i])
            if math.dist(p,q)>step*3:continue
            for corner in ([q[0],p[1]],[p[0],q[1]]):
                pts=[list(p),corner,q]
                if all(free.covers(LineString([a,b])) for a,b in zip(pts,pts[1:])):return tuple(indices[i]),pts
        return None
    left,right=attachment(start),attachment(end)
    if left is None or right is None:return None
    source,target=left[0],right[0];cost={source:0};parents={};queue=[(0,0,source)]
    def point(q):return [float(xs[q[1]]),float(ys[q[0]])]
    while queue:
        _,g,p=heapq.heappop(queue)
        if g!=cost.get(p):continue
        if p==target:
            chain=[p]
            while p!=source:p=parents[p];chain.append(p)
            raw=left[1]+[point(q) for q in reversed(chain)]+list(reversed(right[1]))
            result=[]
            for q in raw:
                if result and q==result[-1]:continue
                if len(result)>1 and ((result[-2][0]==result[-1][0]==q[0]) or (result[-2][1]==result[-1][1]==q[1])):result[-1]=q
                else:result.append(q)
            return result
        for dy,dx in ((0,1),(0,-1),(1,0),(-1,0)):
            q=(p[0]+dy,p[1]+dx)
            if not(0<=q[0]<len(ys) and 0<=q[1]<len(xs) and mask[q]):continue
            if not free.covers(LineString([point(p),point(q)])):continue
            ng=g+step
            if ng<cost.get(q,float('inf')):
                cost[q]=ng;parents[q]=p;heapq.heappush(queue,(ng+step*(abs(q[0]-target[0])+abs(q[1]-target[1])),ng,q))
    return None

def route_connector(start,end,obstacles,cfg):
    width=cfg['road_width'];half=width/2;world=box(0,0,*cfg['world']);collar=half+cfg['routing_margin']+cfg['routing_grid_step']
    left=list(np.array(start['point'])+np.array(start['normal'])*collar);right=list(np.array(end['point'])+np.array(end['normal'])*collar)
    occupied=unary_union([o.buffer(half+cfg['routing_margin'],join_style=2) for o in obstacles])
    free=world.buffer(-half-1,join_style=2).difference(occupied)
    route=orthogonal_route(free,left,right,cfg['routing_grid_step'])
    if route is None:return None
    points=[start['point']]+route+[end['point']];line=LineString(points)
    shape=line.buffer(half,cap_style=2,join_style=2)
    return dict(points=points,shape=shape,length=line.length)

def choose_deployment(team,sockets,reservations,other,cfg):
    """Choose fork frontage by measured connector cost, not map-edge placement.

The deterministic shortlist/search is logged; it does not resample whole layouts.
Both preview roads must remain separate and fit the shared length limit.
"""
    w,h=cfg['deployment_size'];kind='attack' if team=='T' else 'defense'
    targets={s:sockets[s][kind]['point'] for s in ('A','B')}
    reserved=unary_union(reservations+list(other.values())).buffer(cfg['routing_margin']+cfg['road_width']/2,join_style=2)
    candidates=[]
    for x in range(math.ceil(w/2+14),math.floor(cfg['world'][0]-w/2-14),4):
        for y in range(math.ceil(h/2+14),math.floor(cfg['world'][1]-h/2-14),4):
            area=box(x-w/2,y-h/2,x+w/2,y+h/2)
            if area.intersects(reserved):continue
            distances=[abs(x-t[0])+abs(y-t[1]) for t in targets.values()]
            candidates.append((max(distances)+sum(distances)*.1,x,y))
    candidates.sort();search=[];best=None
    for _,x,y in candidates[:cfg['deployment_search_shortlist']]:
        area=box(x-w/2,y-h/2,x+w/2,y+h/2);ports=deployment_ports([x,y],[w,h],targets)
        obstacles=reservations+list(other.values())+[area];lengths=[]
        for site in ('A','B'):
            route=route_connector(ports[site],sockets[site][kind],obstacles,cfg)
            if route is None:break
            lengths.append(route['length']);obstacles.append(route['shape'])
        feasible=len(lengths)==2 and max(lengths)<=cfg['maximum_spawn_connector_plan_length']
        search.append(dict(center=[x,y],preview_lengths_plan_units=lengths,within_shared_limit=feasible))
        if len(lengths)==2:
            cost=max(lengths)+sum(lengths)*.1
            if best is None or (feasible and not best['feasible']) or (feasible==best['feasible'] and cost<best['cost']):
                best=dict(center=[x,y],area=area,ports=ports,cost=cost,feasible=feasible)
    if best is None:
        # Explicit failed fallback location solely permits rendering the rejected
        # proposal; it is never presented as a successful deployment placement.
        _,x,y=candidates[0] if candidates else (0,14,14)
        area=box(x-w/2,y-h/2,x+w/2,y+h/2);best=dict(center=[x,y],area=area,ports=deployment_ports([x,y],[w,h],targets),feasible=False,cost=None)
    return best,search

def generate(plan,seed,cfg):
    if digest(plan)!=cfg['strategy_sha256']:raise ValueError('Unchanged P04 strategy hash required')
    mods={};sizes={};choices={}
    for site in ('A','B'):mods[site],sizes[site],choices[site]=local_rules(site,seed,cfg)
    macro=arrangement(seed,cfg,sizes);world=box(0,0,*cfg['world'])
    p=dict(schema='playable-space-mass-openings-v1',candidate=f'P04-auto-seed-{seed}',seed=seed,
        name=f"{macro['axis']} / B {macro['B_facing_relationship']} / independent depth offsets",
        display_title=f'P04 / seed {seed} — procedural rule assembly',authorship='Shared seeded architecture procedure; no candidate-specific coordinate edits.',
        rule_version=cfg['rule_version'],plan_sha256=digest(plan),engine_scale=cfg['scale'],
        boundary_thickness=cfg['scale']['wall_thickness_source_units']/32,envelope=rect(0,0,*cfg['world']),
        site_spaces={'A':'A_court','B':'B_court'},elevation={'all_walkable_space':0},
        spaces=[],openings=[],internal_masses=[],annotations={},allocations=[],objective_zones={},defender_positions={})
    reserves=[];log=[dict(stage='overall_arrangement',choices=macro),dict(stage='local_architecture',choices=choices)]
    errors=[];sockets={}
    for site in ('A','B'):
        module,reservation=orient_module(mods[site],sizes[site],macro['rotations'][site],macro['complex_centers'][site])
        if not world.covers(reservation):errors.append('Out-of-world module reservation: '+site)
        if any(reservation.intersection(x).area>1e-6 for x in reserves):errors.append('Overlapping site-complex reservations')
        reserves.append(reservation);sockets[site]=module['sockets']
        for key in ('spaces','openings','internal_masses','allocations'):p[key].extend(module[key])
        for key in ('annotations','objective_zones','defender_positions'):p[key].update(module[key])
    deployment={};ports={}
    team_order=('CT','T') if macro['routing_order']=='defender_first' else ('T','CT')
    for team in team_order:
        choice,search=choose_deployment(team,sockets,reserves,deployment,cfg)
        c=choice['center'];area=choice['area'];macro['deployment'][team]=c
        deployment[team]=area
        log.append(dict(stage='deployment_placement',team=team,chosen_center=c,within_shared_limit=choice['feasible'],search=search))
        if not choice['feasible']:errors.append('No short disjoint deployment placement found for '+team)
        p['spaces'].append(dict(id=team+'_deployment',boundary=list(area.exterior.coords)[:-1],description='Deployment frontage: assignments diverge here, no universal encounter junction.'))
        p['annotations'][team]=dict(point=c,interpretation='Deployment assignment area, not an endpoint.')
        ports[team]=choice['ports']
    roads={};obstacles=reserves+list(deployment.values());width=cfg['road_width'];half=width/2
    order={'attacker_first':[('T','A'),('T','B'),('CT','A'),('CT','B')],
        'defender_first':[('CT','A'),('CT','B'),('T','A'),('T','B')],
        'site_interleaved':[('T','A'),('CT','A'),('T','B'),('CT','B')]}[macro['routing_order']]
    for team,site in order:
        kind='attack' if team=='T' else 'defense';start=ports[team][site];end=sockets[site][kind]
        route=route_connector(start,end,obstacles,cfg)
        if route is None:
            errors.append('No disjoint circulation placement for '+team+'-'+site)
            log.append(dict(stage='circulation',team=team,site=site,status='rejected_route',start=start,end=end));continue
        points=route['points'];shape=route['shape']
        if route['length']>cfg['maximum_spawn_connector_plan_length']:
            errors.append('Spawn connector exceeds shared length limit: '+team+'-'+site)
            log.append(dict(stage='circulation',team=team,site=site,status='rejected_length',points=points,length_plan_units=route['length'],limit_plan_units=cfg['maximum_spawn_connector_plan_length']))
            continue
        if not isinstance(shape,Polygon) or not shape.is_valid:
            errors.append('Invalid swept circulation polygon '+team+'-'+site);continue
        rid=team+'_'+site+'_circulation';roads[rid]=shape
        p['spaces'].append(dict(id=rid,boundary=list(shape.exterior.coords)[:-1],description='Physical '+('attacker approach' if team=='T' else 'rear defender assignment')+' around composed inaccessible buildings.'))
        for sid,socket,other,label in [(team+'_'+site,start,team+'_deployment','Deployment assignment'),(site+'_'+kind+'_arrival',end,end['space'],'Approach/receiving threshold')]:
            n=socket['normal'];t=[-n[1],n[0]];ow=cfg['road_opening_width'];line=[list(np.array(socket['point'])-np.array(t)*ow/2),list(np.array(socket['point'])+np.array(t)*ow/2)]
            p['openings'].append(dict(id=sid,spaces=[other,rid],aperture=line,purpose=label+'; physical opening generated on shared frontage'))
        obstacles.append(shape)
        log.append(dict(stage='circulation',team=team,site=site,status='placed',points=points,width_plan_units=width,length_plan_units=LineString(points).length))
    p['composition_errors']=errors;p['decision_log']=log
    p['mass_reservations']=[dict(site=s,boundary=list(reserves[i].exterior.coords)[:-1],purpose='Joint building/playable reservation; remaining envelope is inaccessible solid.') for i,s in enumerate(('A','B'))]
    return p

def source_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('procedural_p04.py','procedural_p04_checks.py','playable_composition.py','p04_comparison_round.py')}

def run_batch(args):
    from procedural_p04_checks import validate
    cfg=json.loads(args.config.read_text());seeds=json.loads(args.seeds.read_text())['seeds'];plan=json.loads((ROOT/cfg['strategy']).read_text())
    if len(seeds)!=4 or len(set(seeds))!=4:raise ValueError('This experiment requires exactly four distinct declared seeds')
    args.output.mkdir(parents=True,exist_ok=True);revision=args.output/args.revision
    if revision.exists():raise ValueError('Attempt revision already exists; use a new revision to preserve the full attempt history')
    revision.mkdir();(revision/'source').mkdir()
    sources=source_hashes()
    for name in sources:(revision/'source'/Path(name).name).write_bytes((ROOT/name).read_bytes())
    (revision/'configuration.json').write_text(json.dumps(cfg,indent=2));(revision/'seeds.json').write_bytes(args.seeds.read_bytes())
    (revision/'strategy-validation.json').write_text(json.dumps(GameplayValidator().validate(plan),indent=2))
    attempts=[];pictures=[];bounds=(0,0,*cfg['world']);px=min(1600/cfg['world'][0],1250/cfg['world'][1])
    for seed in seeds:
        folder=revision/f'seed-{seed}';folder.mkdir();p=generate(plan,seed,cfg);again=generate(plan,seed,cfg)
        reproduction=dict(same_seed_same_composition=digest(p)==digest(again),first_sha256=digest(p),second_sha256=digest(again),scope='Entire composition plus decision log, regenerated from scratch; validation/PNG determinism not implied.')
        (folder/'composition.json').write_text(json.dumps(p,indent=2));(folder/'decisions.json').write_text(json.dumps(p['decision_log'],indent=2));(folder/'reproducibility.json').write_text(json.dumps(reproduction,indent=2))
        try:
            c=compile_composition(p);r=validate(plan,p,c,cfg)
            status='accepted_for_review' if not r['violations'] and not p['composition_errors'] else 'rejected_structurally'
            r.update(status=status,reproducibility=reproduction)
            clean=render(p,c,r,seed,bounds,False,px);overlay=render(p,c,r,seed,bounds,True,px)
            if status!='accepted_for_review':
                for im in (clean,overlay):ImageDraw.Draw(im).text((75,155),'REJECTED — inspect validation; not an accepted map',fill='#ff9c9c')
            clean.save(folder/'plan-clean.png');overlay.save(folder/'plan-encounters.png');pictures.append(clean)
            (folder/'playable-space.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=[dict(type='Feature',properties={'kind':k},geometry=mapping(c[k])) for k in ('walkable','solid','walls','fixtures')]),indent=2))
        except ValueError as exc:
            status='rejected_compile';r=dict(status=status,violations=[str(exc)],warnings=[],composition_errors=p['composition_errors'],reproducibility=reproduction)
            # Raw proposal view remains inspectable; it is explicitly not compiled walkable space.
            raw=unary_union([Polygon(s['boundary']) for s in p['spaces']]);fake=dict(walkable=raw,spaces={s['id']:Polygon(s['boundary']) for s in p['spaces']})
            clean=render(p,fake,None,seed,bounds,False,px);ImageDraw.Draw(clean).text((75,155),'REJECTED COMPILE — raw proposed spaces; overlaps/openings are not valid',fill='#ff9c9c')
            clean.save(folder/'plan-clean.png');pictures.append(clean)
        (folder/'validation.json').write_text(json.dumps(r,indent=2))
        attempts.append(dict(seed=seed,status=status,violations=r['violations'],warnings=r.get('warnings',[]),composition_errors=p['composition_errors'],composition_sha256=digest(p),reproduced=reproduction['same_seed_same_composition']))
    sheet=Image.new('RGB',(3600,3300),'#101923')
    for i,im in enumerate(pictures):sheet.paste(im,((i%2)*1800,(i//2)*1650))
    sheet.save(revision/'all-four-clean-same-scale.png')
    summary=dict(rule_version=cfg['rule_version'],revision=args.revision,seeds=seeds,source_hashes=sources,configuration_sha256=digest(cfg),strategy_sha256=digest(plan),common_pixels_per_plan_unit=px,attempts=attempts,stage4_paused=True)
    (revision/'summary.json').write_text(json.dumps(summary,indent=2))
    with (args.output/'attempts.jsonl').open('a',encoding='utf-8') as f:
        for attempt in attempts:f.write(json.dumps(dict(revision=args.revision,rule_version=cfg['rule_version'],**attempt))+'\n')
    policy_path=ROOT/'generation-policy.json';policy=json.loads(policy_path.read_text());policy.update(stage_3_experiment_status='minimal_procedural_batch_pending_review',
        stage_3_procedural_experiment={'seeds':seeds,'revision':args.revision,'batch_consumed':True,'engine_geometry_authorized':False},
        stage_3_review=str((revision/'review.md').relative_to(ROOT)).replace('\\','/'),stage_4_authorized=False,stage_3_batch_authorized=False,geometry_paused=True)
    policy_path.write_text(json.dumps(policy,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path,default=ROOT/'config/p04-procedural-v3.json')
    ap.add_argument('--seeds',type=Path,default=ROOT/'config/p04-procedural-seeds.json')
    ap.add_argument('--output',type=Path,default=ROOT/'output/p04-procedural-001')
    ap.add_argument('--revision',required=True,help='New immutable attempt revision, e.g. r1; never overwrites an attempt')
    args=ap.parse_args();run_batch(args)

if __name__=='__main__':main()
