"""Stage 3 measurement, preservation checks and transformation-invariant audit.

There are no new tactical quality thresholds. Orders come from strategy;
distance/angle uncertainty comes from approximate regions or raster resolution.
"""
import heapq
import itertools
import math

import numpy as np
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
from shapely import contains_xy

from semantic_pipeline import digest
from spatial_composition import length


def angle(a,b):
    a=np.asarray(a);b=np.asarray(b);norm=np.linalg.norm(a)*np.linalg.norm(b)
    return math.degrees(math.acos(float(np.clip(np.dot(a,b)/norm,-1,1)))) if norm else None


def physical_access(embedding,blocked_regions=()):
    """Coarse free-territory navigation; no phase/team walls or imagined doors."""
    regions=[Polygon(v['boundary']) for k,v in embedding['regions'].items() if k not in blocked_regions]
    carriers=[Polygon(v['boundary']) for v in embedding['travel_envelopes'].values() if v['level']==0]
    footprint=unary_union(regions+carriers)
    if blocked_regions:footprint=footprint.difference(unary_union([Polygon(embedding['regions'][k]['boundary']) for k in blocked_regions]))
    xmin,ymin,xmax,ymax=embedding['bounds'];step=max(xmax-xmin,ymax-ymin)/80
    xs=np.arange(xmin,xmax+step,step);ys=np.arange(ymin,ymax+step,step)
    xx,yy=np.meshgrid(xs,ys);mask=contains_xy(footprint,xx,yy)
    h,w=mask.shape
    def nearest(pid):
        xy=np.array(embedding['anchors'][pid]['xy']);indices=np.argwhere(mask)
        if not len(indices):return None
        points=np.c_[xs[indices[:,1]],ys[indices[:,0]]]
        distances=np.sum((points-xy)**2,axis=1);index=int(np.argmin(distances))
        # Never snap a blocked endpoint across an inaccessible territory and
        # call that access. This bound is raster error, not a gameplay cutoff.
        if math.sqrt(float(distances[index]))>step*math.sqrt(2):return None
        return tuple(indices[index])
    def shortest(start,end):
        source,target=nearest(start),nearest(end)
        if source is None or target is None:return None
        queue=[(0.,source)];dist={source:0.}
        while queue:
            d,p=heapq.heappop(queue)
            if p==target:return d
            if d!=dist.get(p):continue
            for dy,dx in ((0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)):
                q=(p[0]+dy,p[1]+dx)
                if not (0<=q[0]<h and 0<=q[1]<w and mask[q]):continue
                if dy and dx and not (mask[p[0],q[1]] and mask[q[0],p[1]]):continue
                nd=d+step*math.hypot(dx,dy)
                if nd<dist.get(q,float('inf')):dist[q]=nd;heapq.heappush(queue,(nd,q))
        return None
    return shortest,{'cell_size':step,'length_uncertainty':2*step*math.sqrt(2),
                     'scope':'Coarse ground-territory reachability; open interiors assumed, ramps/upper deck require finer verification.'}


def validate_preservation(plan,embedding):
    issues=[];unverified=[];measurements={};checks=[]
    def check(name,passed,detail):
        checks.append({'check':name,'passed':bool(passed),'detail':detail})
        if not passed:issues.append({'code':name,'detail':detail})
    check('exact_strategy',embedding['plan_sha256']==digest(plan),'Spatial interpretation must refer to the unchanged strategy.')
    check('place_coverage',set(embedding['anchors'])=={p['id'] for p in plan['places']},'All places require an anchor or shared subspace.')
    check('relationship_coverage',set(embedding['relationship_ids'])=={r['id'] for r in plan['relationships']},'No strategic relationships removed.')
    routes={r['id']:r for r in plan['routes']};a=embedding['anchors']
    for rid,route in routes.items():
        curve=embedding['routes'][rid]['points'];start=np.array(a[route['places'][0]]['xy']);end=np.array(a[route['places'][-1]]['xy'])
        check('route_endpoints',np.allclose(curve[0],start) and np.allclose(curve[-1],end),rid)
        if route['outcome']['elevation']['value']=='ground':
            check('endpoint_elevation',embedding['routes'][rid]['endpoint_level']==a[route['places'][0]]['level'],rid)
    alternatives=[]
    for alt in routes.values():
        if not alt.get('alternative_to'):continue
        base=routes[alt['alternative_to']];pa=embedding['routes'][base['id']];pb=embedding['routes'][alt['id']]
        va=np.array(pa['points'][-1])-np.array(pa['points'][-3]);vb=np.array(pb['points'][-1])-np.array(pb['points'][-3])
        observed_angle=angle(va,vb);expected=abs((base['outcome']['entry_angle']['value']-alt['outcome']['entry_angle']['value']+180)%360-180)
        la,lb=pa['length'],pb['length'];ta,tb=base['outcome']['timing']['value'],alt['outcome']['timing']['value']
        wanted_order='longer' if tb[0]>ta[1] else 'shorter' if tb[1]<ta[0] else 'overlapping target windows'
        ordering=lb>la if wanted_order=='longer' else lb<la if wanted_order=='shorter' else True
        check('alternate_length_order',ordering,{'routes':[base['id'],alt['id']],'intended':wanted_order,'observed_ratio':lb/la})
        if expected:
            check('entry_directions_noncoincident',observed_angle is not None and not np.isclose(observed_angle,0),{'routes':[base['id'],alt['id']],'observed_degrees':observed_angle})
        alternatives.append({'routes':[base['id'],alt['id']],'lengths':[la,lb],'length_ratio':lb/la,
            'contract_duration_ratio_interval':[tb[0]/ta[1],tb[1]/ta[0]],'intended_length_order':wanted_order,
            'entry_angle_observed_degrees':observed_angle,'entry_angle_contract_degrees':expected,
            'scope':'Order and noncoincidence checks only; meaningful-angle and actual-time claims remain uncalibrated.'})
    measurements['alternatives']=alternatives
    nav,nav_scope=physical_access(embedding);measurements['navigation_resolution']=nav_scope
    mid=[]
    for claim in plan['mid_claims']:
        pid=claim['place']
        for team,rid in claim['access'].items():
            access=routes[rid]
            independent_nav,_=physical_access(embedding,blocked_regions=('A','B','CT' if team=='T' else 'T'))
            distance=independent_nav(access['places'][0],pid)
            check('independent_mid_access',distance is not None,{'team':team,'distance':distance})
            mid.append({'team':team,'route':rid,'planned_length':embedding['routes'][rid]['length'],'coarse_shortest_ground_length':distance})
        for relid in claim['pressure_relationships']:
            rel=next(r for r in plan['relationships'] if r['id']==relid);d=nav(pid,rel['to'])
            check('mid_destination_access',d is not None,{'destination':rel['to'],'coarse_length':d})
    measurements['mid_access']=mid
    rotations=[]
    for route in routes.values():
        if route['purpose']!='rotation':continue
        start,end=route['places'][0],route['places'][-1];planned=embedding['routes'][route['id']]['length'];short=nav(start,end)
        rotations.append({'route':route['id'],'planned_length':planned,'coarse_shortest_ground_length':short,
                          'potential_shortcut_reduction':None if short is None else planned-short})
        # Drawing a costly path is not proof that the territory forces it.
        if short is not None and short+nav_scope['length_uncertainty']<planned:
            unverified.append({'code':'potential_rotation_shortcut','route':route['id'],'planned':planned,'coarse_shortest':short,
                               'note':'Approximate open territory admits a shorter path; protection/cost cannot be certified.'})
        if route['outcome']['engagement']['value'] and 'transfer' in embedding['regions']:
            safe_nav,safe_scope=physical_access(embedding,blocked_regions=('transfer',));safe=safe_nav(start,end)
            check('exposed_transfer_not_bypassed',safe is None,{'route':route['id'],'exposure_region':'transfer','ground_path_avoiding_it':safe,
                       'scope':'Transfer territory is the schematic exposure proxy; no verified LOS.'})
        if route['outcome']['timing']['value'][0]>max(r['outcome']['timing']['value'][1] for r in routes.values() if r['team']=='CT' and r['purpose']=='defensive_access' and r['phase']=='opening'):
            deploy=max(embedding['routes'][r['id']]['length'] for r in routes.values() if r['team']=='CT' and r['purpose']=='defensive_access' and r['phase']=='opening')
            check('costly_transfer_remains_longer_than_deployment',short is not None and short>deploy,{'route':route['id'],'shortest_transfer':short,'longest_deployment':deploy})
    measurements['rotations']=rotations
    overlaps=[]
    for (ka,ra),(kb,rb) in itertools.combinations(embedding['regions'].items(),2):
        area=Polygon(ra['boundary']).intersection(Polygon(rb['boundary'])).area
        if area:overlaps.append({'regions':[ka,kb],'intersection_area':area,'separate_levels':ra['level']!=rb['level']})
    for k,carrier in embedding['travel_envelopes'].items():
        if carrier['level']:
            other=unary_union([Polygon(v['boundary']) for q,v in embedding['travel_envelopes'].items() if q!=k and v['level']==0])
            overlaps.append({'regions':[k,'ground travel envelopes'],'intersection_area':Polygon(carrier['boundary']).intersection(other).area,'separate_levels':True})
    measurements['overlaps']=overlaps
    measurements['convergence']=[{'place':pid,'xy':a[pid]['xy'],'region':a[pid]['region'],
        'routes':[r['id'] for r in routes.values() if pid in r['places']]} for pid in a if len([r for r in routes.values() if r['team']=='T' and r['purpose'] in ('primary_attack','secondary_attack') and pid in r['places']])>1 and pid!='T']
    unverified.extend([{'code':'actual_timing_unverified','note':'Distance ratios are reported. Combat delays, movement speed, stairs and absolute timing are unmeasured.'},
        {'code':'entry_angle_quality_unverified','note':'Measured entry directions differ, but no reference-derived meaningful-angle threshold is claimed.'},
        {'code':'information_exposure_retreat_unverified','note':'No detailed occluders, combat simulation or compiled navigation; preserved claims remain schematic hypotheses.'}])
    if embedding['bridge']:unverified.append({'code':'grade_separation_verification_pending','segment':embedding['bridge'],'note':'Ramps are schematic support transitions; movement, cover and exposure remain unverified.'})
    return {'stage':'spatial_preservation_validation','plan_sha256':digest(plan),'embedding_sha256':digest(embedding),
            'schematic_checks_passed':not issues,'semantic_claims_fully_verified':False,
            'stage_4_authorized':False,'issues':issues,'unverified':unverified,'checks':checks,'measurements':measurements,
            'scope':'Relative composition/territory tests only. No new tactical numeric thresholds or geometry approval.'}


def spatial_equivalence(left,right):
    if left['plan_sha256']!=right['plan_sha256']:raise ValueError('Spatial equivalence compares the same strategic intent.')
    keys=sorted(left['anchors']);x=np.array([left['anchors'][k]['xy'] for k in keys]);y=np.array([right['anchors'][k]['xy'] for k in keys])
    xc=x-x.mean(axis=0);yc=y-y.mean(axis=0);sx=np.linalg.norm(xc);sy=np.linalg.norm(yc)
    xn=xc/sx;yn=yc/sy;u,_,vt=np.linalg.svd(yn.T@xn);rot=u@vt;aligned=yn@rot
    residual=np.linalg.norm(aligned-xn,axis=1)
    uncertainty=np.array([left['anchors'][k]['uncertainty']/sx+right['anchors'][k]['uncertainty']/sy for k in keys])
    anchors_equivalent=bool(np.all(residual<=uncertainty))
    # A large distortion of approach/rotation curves must not be hidden by
    # unchanged centres. Curves are aligned in the same common frame.
    route_errors=[]
    for rid in sorted(left['routes']):
        p=np.asarray(left['routes'][rid]['points']);q=np.asarray(right['routes'][rid]['points'])
        def resample(v):
            d=np.r_[0,np.cumsum(np.linalg.norm(np.diff(v,axis=0),axis=1))]
            return np.c_[np.interp(np.linspace(0,d[-1],40),d,v[:,0]),np.interp(np.linspace(0,d[-1],40),d,v[:,1])]
        p=(resample(p)-x.mean(axis=0))/sx;q=(resample(q)-y.mean(axis=0))/sy@rot
        route_errors.append({'route':rid,'maximum_normalized_deviation':float(np.max(np.linalg.norm(p-q,axis=1))),
                             'within_approximate_anchor_envelope':bool(np.max(np.linalg.norm(p-q,axis=1))<=float(np.max(uncertainty)))})
    layering_left={k:v['level'] for k,v in left['travel_envelopes'].items()};layering_right={k:v['level'] for k,v in right['travel_envelopes'].items()}
    same_layers=layering_left==layering_right
    region_errors=[]
    for key in sorted(left['regions']):
        p=(np.array(left['regions'][key]['boundary'])-x.mean(axis=0))/sx
        q=(np.array(right['regions'][key]['boundary'])-y.mean(axis=0))/sy@rot
        error=Polygon(p).hausdorff_distance(Polygon(q))
        limits=[uncertainty[i] for i,k in enumerate(keys) if left['anchors'][k]['region']==key]
        bound=max(limits) if limits else float(np.max(uncertainty))
        region_errors.append({'region':key,'normalized_boundary_change':error,'within_declared_uncertainty':bool(error<=bound)})
    dleft=np.linalg.norm(xn[:,None]-xn[None,:],axis=2);dright=np.linalg.norm(yn[:,None]-yn[None,:],axis=2)
    equivalent=anchors_equivalent and all(r['within_approximate_anchor_envelope'] for r in route_errors) and all(r['within_declared_uncertainty'] for r in region_errors) and same_layers
    core_keys=[k for k in ('T','CT','A','B','control','regroup','defender_hub','shared_prep') if k in left['anchors']]
    cx=np.array([left['anchors'][k]['xy'] for k in core_keys]);cy=np.array([right['anchors'][k]['xy'] for k in core_keys])
    cx-=cx.mean(axis=0);cy-=cy.mean(axis=0);csx=np.linalg.norm(cx);csy=np.linalg.norm(cy);cx/=csx;cy/=csy
    cu,_,cvt=np.linalg.svd(cy.T@cx);cr=np.linalg.norm(cy@(cu@cvt)-cx,axis=1)
    cb=np.array([left['anchors'][k]['uncertainty']/csx+right['anchors'][k]['uncertainty']/csy for k in core_keys])
    core_equivalent=bool(np.all(cr<=cb))
    return {'equivalent':equivalent,'rigid_or_scaled_copy':bool(np.allclose(residual,0)),
        'aligned_anchor_rms':float(np.sqrt(np.mean(residual**2))),
        'normalized_pair_distance_rms':float(np.sqrt(np.mean((dleft-dright)**2))),
        'largest_anchor_change':keys[int(np.argmax(residual))],
        'same_elevation_structure':same_layers,'route_shape_diagnostics':route_errors,
        'region_shape_diagnostics':region_errors,
        'dominant_landmark_arrangement_equivalent':core_equivalent,
        'dominant_landmark_aligned_rms':float(np.sqrt(np.mean(cr**2))),
        'anchor_uncertainty_bounds':uncertainty.tolist(),
        'scope':'Similarity-normalized alignment includes reflection. Equivalence uses declared approximate territory-anchor uncertainty, not a CS tactical cutoff.'}


def transformed_copy(embedding,matrix,offset,scale):
    """Adversarial equivalence control; not a new generated spatial candidate."""
    import copy
    result=copy.deepcopy(embedding);matrix=np.array(matrix);offset=np.array(offset)
    def apply(points):return (np.array(points)@matrix*scale+offset).tolist()
    for a in result['anchors'].values():a['xy']=apply(a['xy']);a['uncertainty']*=scale
    for r in result['regions'].values():r['center']=apply(r['center']);r['boundary']=apply(r['boundary'])
    for r in result['travel_envelopes'].values():r['boundary']=apply(r['boundary']);r['widths']=[v*scale for v in r['widths']]
    for s in result['segments'].values():s['points']=apply(s['points'])
    for r in result['routes'].values():r['points']=apply(r['points']);r['length']*=scale
    x0,y0,x1,y1=result['bounds'];corners=np.array(apply([[x0,y0],[x0,y1],[x1,y0],[x1,y1]]))
    result['bounds']=[float(corners[:,0].min()),float(corners[:,1].min()),float(corners[:,0].max()),float(corners[:,1].max())]
    return result


def equivalence_controls(embedding):
    t=math.radians(73);rotation=[[math.cos(t),-math.sin(t)],[math.sin(t),math.cos(t)]]
    cases=[('translation',[[1,0],[0,1]],[53,-17],1),('rotation',rotation,[0,0],1),
           ('reflection',[[-1,0],[0,1]],[0,0],1),('uniform scaling',[[1,0],[0,1]],[0,0],3.7),
           ('combined transform',[[-math.cos(t),math.sin(t)],[math.sin(t),math.cos(t)]],[53,-17],3.7)]
    rows=[{'control':name,**spatial_equivalence(embedding,transformed_copy(embedding,matrix,offset,scale))} for name,matrix,offset,scale in cases]
    import copy,random
    jitter=copy.deepcopy(embedding);rng=random.Random(8803)
    bound=min(a['uncertainty'] for a in embedding['anchors'].values())/20
    for a in jitter['anchors'].values():a['xy']=[v+rng.uniform(-bound,bound) for v in a['xy']]
    rows.append({'control':'minor anchor jitter within declared uncertainty',**spatial_equivalence(embedding,jitter)})
    return rows
