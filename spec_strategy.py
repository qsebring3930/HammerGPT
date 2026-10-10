"""Specification -> coordinate-free strategy -> full Stage 2 gate.

The temporal windows below are the existing planner's authored design targets,
never NAV measurements or a timing calibration. Stage 3 must report them as
unverified. The spatial compiler receives this exact plan, not a replacement.
"""
import copy
from semantic_pipeline import StrategicPlanner,GameplayValidator,fact,digest
from semantic_organizations import organization_brief,finish_proposal
from map_design_spec import mid_strategy,SpecificationError

VERSION='specification-strategy-bridge-v1'

def build_plan(spec):
    g=spec['gameplay'];seed=spec.get('seed') or 0;has_mid=g['mid']=='contested'
    condition=dict(control='contested' if has_mid else 'none',deployment='independent',
        defender_rotation='deployment',attacker_rotation='redeploy',
        site_commitment='both_staged',retake='separate',secondary='control' if has_mid else 'local')
    brief=organization_brief(condition,seed)
    source='Explicit provisional specification contract; target windows are authored, not measured: '+digest(spec)
    def cf(value):return fact(value,'design_contract',source)
    routes={r['id']:r for r in brief['route_intents']}
    m=mid_strategy(spec,seed) if has_mid else None
    for s in ('A','B'):
        staged=g['site_commitment']=='staged' or g['site_commitment']=='mixed' and s=='B'
        routes['T-'+s+'-main']['outcome']['timing']=cf([17,19] if staged else [11,13])
        routes['T-'+s+'-main']['preparation_depth']='staged' if staged else 'immediate'
        if has_mid:
            pid=s+'_transfer'
            brief['places'].append(dict(id=pid,name=s+' transfer',kind='connector',role_evidence=cf('Controlled Mid exit leads through transfer territory before site preparation.')))
            alt=routes['T-'+s+'-alt'];alt['places'].insert(-1,pid)
            if s==m['handoff_site']:
                alt['places']=alt['places'][:-1]+[s+'_prep',s+'_fight',s+'_entry']
                alt['outcome']['entry_angle']=cf(0)
                alt['outcome']['defender_bypass']=cf([])
                alt['outcome']['engagement']=cf(['control',s+'_fight',s+'_hold'])
                alt['why']='Win Mid, then join primary preparation. This changes control and information but shares the final site entry.'
                alt['purpose_evidence']=cf(alt['why'])
                for relation in brief['relationships']:
                    if relation['id']=='control-pressure-'+s:relation['to']=s+'_entry'
            if g['secondary_access']=='local_and_mid':
                local=copy.deepcopy(alt);local['id']='T-'+s+'-local';local['places']=['T',s+'_prep',s+'_fight',s+'_side']
                local['why']='A local staging split changes site entry without requiring control of Mid.'
                local['purpose_evidence']=cf(local['why']);local['first_contact']=cf(s+'_fight');local['arrivals']={s+'_fight':cf([10,12])}
                local['outcome'].update(engagement=cf([s+'_fight',s+'_hold']),information=cf([]),defender_bypass=cf([]),retreat_capability=cf([s+'_prep']),rotation_capability=cf(['T']))
                brief['route_intents'].append(local)
        if g['defender_rotation']=='central':
            other='B' if s=='A' else 'A';r=routes['CT-'+s+'-switch']
            entry=s+'_entry' if s==m['handoff_site'] else s+'_side'
            other_entry=other+'_entry' if other==m['handoff_site'] else other+'_side'
            r['places']=[s+'_hold',entry,s+'_transfer','control',other+'_transfer',other_entry,other+'_hold']
            r['why']='Redistribute through contested Mid; requires control of the transfer territory and gives up the original site hold.'
            r['purpose_evidence']=cf(r['why']);r['outcome']['engagement']=cf([entry,'control',other_entry]);r['outcome']['information']=cf(['control'])
            r['requirements']=[dict(place='control',state='controlled',effect='Central rotation is exposed if Mid control is lost.')]
    if has_mid and m['handoff_site'] and g['secondary_access']=='mid':
        s=m['handoff_site'];old=s+'_side';replacement=s+'_entry'
        # A shared final attack entry is also a shared physical recovery entry.
        # Do not retain a fictitious second doorway or 180-degree retake claim.
        for r in brief['route_intents']:
            r['places']=[replacement if q==old else q for q in r['places']]
            if r['id']=='CT-'+s+'-recover':r['outcome']['entry_angle']=cf(0)
        for r in brief['relationships']:
            for key in ('from','to'):
                if r[key]==old:r[key]=replacement
        for site in brief['sites']:
            if site['id']==s:site['entry_zones']=[replacement]
        brief['places']=[p for p in brief['places'] if p['id']!=old]
    if g['defender_rotation']=='central':
        for s in ('A','B'):
            other='B' if s=='A' else 'A'
            routes['CT-'+s+'-switch']['places']=[s+'_hold']+list(reversed(routes['T-'+s+'-alt']['places'][1:]))+routes['T-'+other+'-alt']['places'][2:]+[other+'_hold']
    if has_mid and m['organization']=='linked_courts':
        brief['places'] += [dict(id='control_far',name='Second Mid court',kind='connector',role_evidence=cf('The far portion of the same control district supports B pressure and defender access.')),
                           dict(id='control_link',name='Mid court transition',kind='connector',role_evidence=cf('Transition separates the two court engagements while preserving shared circulation.'))]
        for r in brief['route_intents']:
            path=r['places'];result=[]
            for a,b in zip(path,path[1:]):
                result.append(a)
                if a=='control' and b=='B_transfer':result += ['control_link','control_far']
                if a=='B_transfer' and b=='control':result += ['control_far','control_link']
                if a=='CT' and b=='control':result += ['control_far','control_link']
                if a=='control' and b=='CT':result += ['control_link','control_far']
            r['places']=result+[path[-1]]
    brief.update(name='Specification-driven strategic plan',specification=copy.deepcopy(spec),
                 specification_sha256=digest(spec),compiler_version=VERSION,mid_program=m,
                 evidence_scope='Proposed gameplay contract. Timing windows and engagement outcomes are intentions; no physical or gameplay certification.')
    return finish_proposal(StrategicPlanner().generate(brief))

def validate_plan(spec,plan):
    report=GameplayValidator().validate(plan)
    if plan.get('specification_sha256')!=digest(spec) or plan.get('specification')!=spec:
        report['issues'].append(dict(code='specification_plan_mismatch',subject='specification',status='invalid',detail='Plan is not bound to these exact specification inputs.'))
        report['passed']=False
    return report

def require_plan(spec,plan,report):
    if not report['passed'] or report['plan_sha256']!=digest(plan) or plan.get('specification_sha256')!=digest(spec):
        raise SpecificationError('Stage 3 requires passing Stage 2 validation of the exact plan and specification.')
    if digest(plan)!=digest(build_plan(spec)):
        raise SpecificationError('This strategy is outside the specification compiler capabilities; it cannot be silently reduced to the specification.')

def prepare(spec):
    plan=build_plan(spec);return plan,validate_plan(spec,plan)

def audit_realization(plan,p,c,validation):
    """Bind every typed place and phase route to actual compiled navigation.

    Roles can share physical space. This checks realizability, not safe movement
    through enemy territory, arrival targets, visibility or retake angles.
    """
    from shapely.geometry import Point,LineString
    from playable_composition import DerivedNavigation
    clear=dict(c,walkable=c['walkable'].buffer(-.5,join_style=2));nav=DerivedNavigation(clear)
    points={k:v['point'] for k,v in p['annotations'].items()};mapping={k:points[k] for k in ('T','CT','A','B')}
    if 'Mid' in points:mapping.update(control=points['Mid'])
    if 'Mid2' in points:mapping.update(control_far=points['Mid2'])
    if 'Mid_link' in c['spaces']:mapping['control_link']=list(c['spaces']['Mid_link'].representative_point().coords[0])
    openings={o['id']:o for o in p['openings']}
    for s in ('A','B'):
        for role,key in [('prep','staging'),('fight','staging'),('rear','receiving'),('retake','receiving'),('transfer','transfer')]:
            if s+'_'+key in points:mapping[s+'_'+role]=points[s+'_'+key]
        mapping[s+'_hold']=p['defender_positions'][s]
        for role,kind in [('entry','primary'),('side','secondary')]:
            name=validation['actual_site_ingresses'][s][kind]
            if name in openings:mapping[s+'_'+role]=list(LineString(openings[name]['aperture']).centroid.coords[0])
    bindings=[];issues=[];routes=[]
    for place in plan['places']:
        pid=place['id'];point=mapping.get(pid);support=[sid for sid,g in c['spaces'].items() if point and g.buffer(1e-7).covers(Point(point))]
        usable=point is not None and clear['walkable'].buffer(1e-7).covers(Point(point))
        bindings.append(dict(place=pid,kind=place['kind'],point=point,spaces=support,player_clear=usable))
        if not support or not usable:issues.append('Unrealized strategic place: '+pid)
    for route in plan['routes']:
        distance=0;reachable=True
        for a,b in zip(route['places'],route['places'][1:]):
            path=nav.path(mapping[a],mapping[b]) if a in mapping and b in mapping else None
            if path is None:reachable=False;break
            distance+=path['length']*32
        routes.append(dict(id=route['id'],phase=route['phase'],reachable=reachable,ordered_waypoint_distance_HU=distance if reachable else None))
        if not reachable:issues.append('Unrealized strategic phase route: '+route['id'])
    return dict(plan_sha256=digest(plan),passed=not issues,issues=issues,place_bindings=bindings,phase_routes=routes,
        scope='Player-clear paths between semantic interfaces. Main/secondary separation and shared-entry requirements are additionally checked by the structural validator.',
        unresolved=['Authored timing targets','Territory ownership and contact timing','Safe fallback and retake','Exact engagement/retake angles','Utility and balance'])
