"""Stage 3: sampled territory compositions, not floor/VMAP generation.

Strategic places can be ports/subspaces of one territory. They are not one
square per node. Curves are travel envelopes, not walls or constructed floors.
"""
import math
import random

import numpy as np
from scipy.optimize import least_squares
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union

from semantic_pipeline import digest


def unit(v):
    v=np.asarray(v,dtype=float);n=np.linalg.norm(v)
    return v/n if n else np.array([1.,0.])


def length(points):return float(np.linalg.norm(np.diff(np.asarray(points),axis=0),axis=1).sum())


def role_groups(plan):
    kinds={p['id']:p['kind'] for p in plan['places']};groups={}
    for pid,kind in kinds.items():
        if pid in ('A','B'):groups[pid]=pid
        elif pid.startswith(('A_','B_')):
            s=pid[0]
            groups[pid]=s+'_approach' if kind in ('attacker_staging','encounter_space') else s+'_recovery' if kind=='retake_staging' else s
        else:groups[pid]=pid
    return groups


def sample_embedding(plan,validation,seed):
    if not validation['passed'] or validation['plan_sha256']!=digest(plan):raise ValueError('Exact passed strategy required.')
    rng=random.Random(seed);groups=role_groups(plan);keys=sorted(set(groups.values()));n=len(keys)
    # Shape/packing variables sampled independently; no case-specific silhouette
    # or fixed compass position for sites, spawns or control space.
    shape={k:{'rx':rng.uniform(1.3,2.8),'ry':rng.uniform(1.3,3.1),
              'angle':rng.uniform(-math.pi,math.pi),'radial':[rng.uniform(.72,1.22) for _ in range(12)],
              'openness':rng.uniform(.35,.95),'environment':rng.choice(['interior','exterior','mixed'])} for k in keys}
    for k in ('A','B'):
        shape[k]['rx']*=1.5;shape[k]['ry']*=1.5
    initial=np.array([[rng.gauss(0,9),rng.gauss(0,9)] for _ in keys]);initial[keys.index('T')]=0
    lean={s:rng.choice([-1,1]) for s in ('A','B')}
    # Desired movement budgets are sampled from the existing contracts. No CS
    # movement speed, timing cutoff or angle-quality threshold is invented.
    selected=[r for r in plan['routes'] if r['phase']=='opening' and r['places'][0] in ('T','CT')]
    desired={r['id']:rng.uniform(*r['outcome']['timing']['value']) for r in selected}
    def anchors(centers):
        c={k:centers[i] for i,k in enumerate(keys)};result={}
        for pid,g in groups.items():
            v=c[g].copy()
            if pid.startswith(('A_','B_')) and g in ('A','B'):
                s=pid[0];front=unit(c[s+'_approach']-c[s]);rear=unit(c['CT']-c[s])
                radius=(shape[s]['rx']+shape[s]['ry'])/2
                if pid.endswith('_entry'):v+=front*radius
                elif pid.endswith('_side'):v+=np.array([-front[1],front[0]])*radius*lean[s]
                elif pid.endswith('_hold'):v+=rear*radius*.4
                elif pid.endswith('_rear'):v+=rear*radius
            elif pid.endswith('_prep'):v+=unit(c['T']-v)*shape[g]['rx']*.3
            elif pid.endswith('_fight'):v+=unit(c[pid[0]]-v)*shape[g]['ry']*.3
            elif pid.endswith('_territory'):v+=unit(c[pid[0]]-v)*shape[g]['ry']*.5
            result[pid]=v
        return result
    def residual(flat):
        centers=flat.reshape(n,2);a=anchors(centers);res=[]
        for r in selected:
            observed=length([a[p] for p in r['places']]);res.append(observed-desired[r['id']])
        # Spatial packing is feasibility scaffolding, not a novelty objective.
        # Its separation distance is derived from this seed's region extents.
        for i in range(n):
            for j in range(i):
                separation=(min(shape[keys[i]]['rx'],shape[keys[i]]['ry'])+min(shape[keys[j]]['rx'],shape[keys[j]]['ry']))*.8
                res.append(max(0,separation-np.linalg.norm(centers[i]-centers[j])))
        res.extend(centers[keys.index('T')]*2)
        return res
    solution=least_squares(residual,initial.ravel(),max_nfev=150,ftol=1e-6,xtol=1e-6,gtol=1e-6)
    centers={k:solution.x.reshape(n,2)[i] for i,k in enumerate(keys)};a=anchors(solution.x.reshape(n,2))
    regions={}
    for key,c in centers.items():
        sp=shape[key];coords=[]
        for j,radial in enumerate(sp['radial']):
            t=2*math.pi*j/len(sp['radial']);local=np.array([sp['rx']*math.cos(t),sp['ry']*math.sin(t)])*radial
            co,si=math.cos(sp['angle']),math.sin(sp['angle'])
            coords.append((c+np.array([local[0]*co-local[1]*si,local[0]*si+local[1]*co])).tolist())
        poly=Polygon(coords).buffer(0)
        # Strategic subspaces are contained in their shared territory. Ports
        # can extend the initial sampled shape without becoming separate boxes.
        parts=[poly]+[Point(a[pid]).buffer(min(sp['rx'],sp['ry'])*.35) for pid,g in groups.items() if g==key]
        poly=unary_union(parts).convex_hull
        regions[key]={'boundary':list(map(list,poly.exterior.coords)),'center':c.tolist(),
                      'level':0,'environment':sp['environment'],'openness':sp['openness'],
                      'kind':'site system' if key in ('A','B') else 'approach territory' if key.endswith('_approach') else 'recovery territory' if 'recovery' in key or 'retake' in key else 'deployment' if key in ('T','CT') else 'shared/control territory',
                      'strategic_places':[pid for pid,g in groups.items() if g==key]}
    carriers={};segments={}
    for r in plan['routes']:
        for p,q in zip(r['places'],r['places'][1:]):
            key='|'.join(sorted((p,q)))
            if key in segments:continue
            p0,p3=a[p],a[q];delta=p3-p0;norm=np.linalg.norm(delta);normal=np.array([-unit(delta)[1],unit(delta)[0]])
            # A conditional flank that skips a strategic transfer waypoint must
            # not create a new straight physical shortcut. Reuse the known rear
            # transfer composition, independent of team/phase intent labels.
            implementation=None
            if {p,q}=={'A_rear','B_rear'}:
                for known in plan['routes']:
                    if known['team']=='CT' and known['purpose']=='rotation' and p in known['places'] and q in known['places']:
                        i,j=known['places'].index(p),known['places'].index(q)
                        waypoints=known['places'][i:j+1] if i<j else list(reversed(known['places'][j:i+1]))
                        implementation=[];shared=[]
                        for u,v in zip(waypoints,waypoints[1:]):
                            sk='|'.join(sorted((u,v)));shared.append(sk)
                            if sk not in segments:implementation=None;break
                            seg=segments[sk];part=seg['points'] if seg['from']==u else list(reversed(seg['points']))
                            implementation.extend(part if not implementation else part[1:])
                        if implementation:
                            segments[key]={'from':p,'to':q,'points':implementation,'level':0,'shared_implementation_with':shared}
                            break
                if implementation:continue
            bow=rng.uniform(-.28,.28)*norm
            # End tangent at a site-entry port follows its local entry sector.
            c1=p0+delta/3+normal*bow;c2=p0+2*delta/3+normal*bow
            if q.endswith(('_entry','_side')):c2=p3+unit(p3-centers[q[0]])*norm*.25
            if p.endswith(('_entry','_side')):c1=p0+unit(p0-centers[p[0]])*norm*.25
            t=np.linspace(0,1,17)[:,None]
            curve=(1-t)**3*p0+3*(1-t)**2*t*c1+3*(1-t)*t**2*c2+t**3*p3
            forward=curve.tolist();segments[key]={'from':p,'to':q,'points':forward,'level':0}
            # Territory envelope expands/compresses along travel. The envelope
            # is approximate permissible space, not a constructed corridor.
            gp,gq=groups[p],groups[q]
            if gp==gq:continue
            scale=(min(shape[gp]['rx'],shape[gp]['ry'])+min(shape[gq]['rx'],shape[gq]['ry']))/2
            widths=[scale*(.45+.55*math.sin(math.pi*j/16)**2)*rng.uniform(.85,1.15) for j in range(17)]
            footprint=unary_union([LineString(curve).buffer(min(widths))]+[Point(v).buffer(w) for v,w in zip(curve,widths)])
            carriers[key]={'boundary':list(map(list,footprint.exterior.coords)),'level':0,
                           'widths':widths,'connecting_territories':[gp,gq]}
    route_paths={}
    for r in plan['routes']:
        points=[];segment_keys=[]
        for p,q in zip(r['places'],r['places'][1:]):
            key='|'.join(sorted((p,q)));seg=segments[key];part=seg['points'] if seg['from']==p else list(reversed(seg['points']))
            points.extend(part if not points else part[1:]);segment_keys.append(key)
        route_paths[r['id']]={'points':points,'segments':segment_keys,'length':length(points),
                             'endpoint_level':0,'purpose':r['purpose'],'team':r['team'],'phase':r['phase']}
    # Grade-separated travel is a sampled implementation option, not a new
    # tactical gate. Endpoint levels stay unchanged. A schematic verifier must
    # assess whether it undermines intended exposed transfer.
    bridge=None
    candidates=[k for k,v in carriers.items() if any(k in path['segments'] for rid,path in route_paths.items() if path['purpose']=='rotation')]
    if candidates and rng.random()<.5:
        bridge=rng.choice(candidates);carriers[bridge]['level']=1;segments[bridge]['level']=1
        carriers[bridge]['support_transitions']=['ramp at first endpoint','ramp at second endpoint']
    bounds=unary_union([Polygon(r['boundary']) for r in regions.values()]+[Polygon(r['boundary']) for r in carriers.values()]).bounds
    return {'stage':'spatial_embedding','schema_version':2,'seed':seed,'plan_sha256':digest(plan),
        'regions':regions,'anchors':{pid:{'xy':pos.tolist(),'region':groups[pid],'level':0,
                    'uncertainty':min(shape[groups[pid]]['rx'],shape[groups[pid]]['ry'])*.35} for pid,pos in a.items()},
        'travel_envelopes':carriers,'segments':segments,'routes':route_paths,
        'relationship_ids':[r['id'] for r in plan['relationships']],
        'bounds':list(bounds),'bridge':bridge,'units':'abstract distance units; no conversion to CS units or seconds',
        'solver':{'method':'seeded free continuous territory packing; contract-relative movement stress',
                  'evaluations':solution.nfev,'cost':float(solution.cost),'success':bool(solution.success)},
        'passed':False,'scope':'Approximate territory composition only. No floors, walls, VMAP, meshes or verified sightlines.'}
