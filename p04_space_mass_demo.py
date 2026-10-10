"""ONE authored P04 replacement-representation prototype. No batch generation.

Unchanged strategy; architectural space partitions, explicit solid boundaries
and portals, then geometry-derived navigation. This is not a learned sampler.
"""
import json
import math
from pathlib import Path

from shapely.geometry import Polygon,LineString,Point,box,mapping
from shapely.ops import unary_union

from semantic_pipeline import digest,GameplayValidator,SpatialEmbedder
from playable_composition import compile_composition,DerivedNavigation,observed_openings

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/p04-playable-composition-001'


def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]


def prior_program():
    p={'schema':'playable-space-mass-openings-v1','candidate':'P04-one-composition',
       'units':'abstract planar units and square units; not CS units/metres/seconds',
       'boundary_thickness':.8,'elevation':{'all_walkable_space':0},'spaces':[],'internal_masses':[],
       'openings':[],'annotations':{},'allocations':[],'scope':'Single authored composition proving a representation, not automatic generation or Stage 4 geometry.'}
    def space(pid,boundary,description):p['spaces'].append({'id':pid,'boundary':boundary,'description':description})
    space('south_court',[[15,5],[122,5],[122,24],[95,24],[95,30],[39,30],[39,24],[15,24]],'Shared deployment courtyard; target assignments diverge toward separate forecourts.')
    space('west_forecourt',[[15,24],[39,24],[39,42],[48,42],[48,58],[10,58],[10,36],[15,36]],'Bent street and widened forecourt; preparation and first contest share circulation.')
    space('west_yard',rect(10,58,48,90),'Open site courtyard with two entry sectors and a rear defender access.')
    space('west_service',rect(48,46,61,90),'Side circulation/recovery access; no independent strategic patch per role.')
    space('west_foyer',rect(10,90,48,104),'Fallback and retake preparation occupy parts of the same built-in rear foyer.')
    space('gallery_west',rect(48,90,61,104),'Rear circulation beside the central compound.')
    space('deployment_hall',rect(61,84,86,110),'Defender deployment/assignment divergence; two site arms meet here.')
    space('gallery_east',rect(86,90,99,104),'Rear circulation for eastern site access and recovery.')
    space('east_foyer',rect(99,90,136,104),'Eastern fallback and independent retake preparation, integrated into the footprint.')
    space('east_assembly',rect(99,74,136,90),'Interior site space; main entry follows the secured workshop while the side entry arrives from service circulation.')
    space('east_workshop',rect(99,58,136,74),'Territory secured before main-site execute preparation; clearance is not represented as extra path length.')
    space('east_service',[[86,50],[104,50],[104,58],[99,58],[99,90],[86,90]],'Side approach bypasses workshop commitment and supports rear recovery.')
    space('east_forecourt',[[95,24],[122,24],[122,38],[136,38],[136,58],[104,58],[104,44],[95,44]],'Eastern staging and first contest share a yard/work frontage.')
    p['envelope']=[[15,5],[122,5],[122,36],[136,36],[136,104],[86,104],[86,110],[61,110],[61,104],[10,104],[10,36],[15,36]]
    def opening(pid,a,b,line,why):p['openings'].append({'id':pid,'spaces':[a,b],'aperture':line,'purpose':why})
    opening('south_west','south_court','west_forecourt',[[20,24],[33,24]],'Deploy into the west attack investment.')
    opening('south_east','south_court','east_forecourt',[[100,24],[117,24]],'Deploy into a separate east attack investment.')
    opening('A_main','west_forecourt','west_yard',[[21,58],[29,58]],'Main A entry after the shared first contest.')
    opening('A_side_access','west_forecourt','west_service',[[48,48],[48,55]],'Branch after the A contest into a different site-entry sector.')
    opening('A_side','west_service','west_yard',[[48,62],[48,70]],'Side attacker ingress into the occupied side-entry engagement sector; recovery challenges it from rear site access.')
    opening('A_rear','west_yard','west_foyer',[[27,90],[35,90]],'Defender access/fallback between hold and rear foyer.')
    opening('foyer_west_gallery','west_foyer','gallery_west',[[48,95],[48,102]],'Rear fallback/rotation circulation.')
    opening('A_recovery_access','west_service','gallery_west',[[52,90],[58,90]],'Side-entry recovery through shared service circulation.')
    opening('west_CT','gallery_west','deployment_hall',[[61,94],[61,103]],'West assignment connects to CT deployment.')
    opening('east_CT','deployment_hall','gallery_east',[[86,94],[86,103]],'East assignment connects to CT deployment.')
    opening('gallery_east_foyer','gallery_east','east_foyer',[[99,95],[99,102]],'East fallback/rotation circulation.')
    opening('B_rear','east_foyer','east_assembly',[[105,90],[114,90]],'Rear defender access faces the side-entry sector, integrating recovery with the site interior.')
    opening('B_main','east_workshop','east_assembly',[[115,74],[123,74]],'Main B entry after securing workshop territory.')
    opening('B_territory_access','east_forecourt','east_workshop',[[115,58],[123,58]],'Win approach space before the workshop investment.')
    opening('B_side_access','east_forecourt','east_service',[[104,51],[104,57]],'Branch after the same first B contest toward a side entry.')
    opening('B_side','east_service','east_assembly',[[99,79],[99,87]],'Secondary attacker ingress; recovery challenges the side-entry sector from rear site access.')
    opening('B_recovery_access','east_service','gallery_east',[[91,90],[97,90]],'Recovery from rear circulation into side access.')
    for pid,boundary,why in [
        ('west_shed',rect(13,68,22,76),'Courtyard sightline break without severing both entries.'),
        ('west_loading',rect(33,64,39,70),'Loading mass separates the main fight from the side-entry sector and rear recovery approach.'),
        ('workbench',rect(126,60,132,65),'Workshop mass defining preparation space.'),
        ('assembly_equipment',rect(108,74,114,82),'Assembly mass separates workshop-facing combat from side-entry combat; rear recovery reaches the side sector directly.'),
        ('south_store',rect(47,8,56,17),'Deployment sightline break, not a new tactical route.')]:p['internal_masses'].append({'id':pid,'boundary':boundary,'purpose':why})
    anchors={'T':(69,15),'CT':(74,100),'A':(22,83),'A_prep':(24,42),'A_fight':(36,52),
             'A_entry':(25,58),'A_side':(44,66),'A_hold':(35,80),'A_rear':(31,97),'A_retake':(18,97),
             'B':(123,85),'B_prep':(110,39),'B_fight':(108,54),'B_territory':(119,65),
             'B_entry':(119,74),'B_side':(103,83),'B_hold':(113,84),'B_rear':(116,97),'B_retake':(104,98)}
    parents={'T':'south_court','CT':'deployment_hall','A':'west_yard','A_prep':'west_forecourt','A_fight':'west_forecourt',
             'A_entry':'west_yard','A_side':'west_yard','A_hold':'west_yard','A_rear':'west_foyer','A_retake':'west_foyer',
             'B':'east_assembly','B_prep':'east_forecourt','B_fight':'east_forecourt','B_territory':'east_workshop',
             'B_entry':'east_assembly','B_side':'east_assembly','B_hold':'east_assembly','B_rear':'east_foyer','B_retake':'east_foyer'}
    p['annotations']={pid:{'point':list(pos),'space':parents[pid],'level':0,
        'interpretation':'strategic annotation inside shared architectural space, not an allocated floor patch'} for pid,pos in anchors.items()}
    for role,boundary,budget in [('A_rear',rect(24,92,36,100),[80,110]),('A_retake',rect(13,91,25,99),[80,110]),
                               ('B_rear',rect(108,92,124,100),[110,140]),('B_retake',rect(100,92,111,100),[75,105])]:
        p['allocations'].append({'role':role,'boundary':boundary,'area_budget':budget,
            'source':'Explicit allocation for this one composition; not a reference-derived CS quality threshold.'})
    p['distance_budgets']={'CT-A-withdraw':[15,35],'CT-B-withdraw':[10,25],
        'CT-A-regather':[8,18],'CT-B-regather':[8,18],'CT-A-recover':[40,75],'CT-B-recover':[15,40]}
    p['budget_source']='Authored space-program allocations in abstract units; separate from original second-based design contracts.'
    return p


def program():
    from p04_architecture_revision import build
    return build(prior_program())


def route_nav(nav,points):
    parts=[];total=0.
    for a,b in zip(points,points[1:]):
        part=nav.path(a,b)
        if part is None:return None
        total+=part['length'];parts.extend(part['points'] if not parts else part['points'][1:])
    return {'points':parts,'length':total}


def crossed_openings(result,p):
    if result is None:return []
    line=LineString(result['points'])
    crossings=[]
    for o in p['openings']:
        intersection=line.intersection(LineString(o['aperture']))
        if intersection.is_empty:continue
        pieces=list(intersection.geoms) if hasattr(intersection,'geoms') else [intersection]
        distance=min(line.project(q if isinstance(q,Point) else Point(list(q.coords)[0])) for q in pieces)
        crossings.append((distance,o['id']))
    return [pid for _,pid in sorted(crossings)]


def aperture_separation(left,right):
    def tangent(o):
        a,b=o['aperture'];v=(b[0]-a[0],b[1]-a[1]);n=math.hypot(*v)
        return (v[0]/n,v[1]/n)
    u,v=tangent(left),tangent(right)
    return math.degrees(math.acos(min(1,abs(u[0]*v[0]+u[1]*v[1]))))


def site_ingress(result,p,c,space_id):
    """Observed inward crossing of a site boundary; normal is directed, not an axis.

    Measures ingress sector, not view direction or last-segment heading. Record
    path tangent separately so the convention cannot hide that distinction.
    """
    if result is None:return None
    poly=c['spaces'][space_id];events=[]
    for index,(a,b) in enumerate(zip(result['points'],result['points'][1:])):
        seg=LineString([a,b]);dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        if length==0:continue
        for opening in p['openings']:
            if space_id not in opening['spaces']:continue
            cross=seg.intersection(LineString(opening['aperture']))
            if not isinstance(cross,Point):continue
            heading=(dx/length,dy/length)
            before=Point(cross.x-heading[0]*.01,cross.y-heading[1]*.01)
            after=Point(cross.x+heading[0]*.01,cross.y+heading[1]*.01)
            if poly.contains(before) or not poly.contains(after):continue
            v0,v1=opening['aperture'];tx,ty=v1[0]-v0[0],v1[1]-v0[1];norm=math.hypot(tx,ty)
            normal=[-ty/norm,tx/norm]
            if not poly.contains(Point(cross.x+normal[0]*.01,cross.y+normal[1]*.01)):
                normal=[-normal[0],-normal[1]]
            events.append((index,seg.project(cross),{'opening':opening['id'],'crossing':[cross.x,cross.y],
                'inward_approach_vector':normal,'path_tangent':list(heading)}))
    return sorted(events,key=lambda e:(e[0],e[1]))[0][2] if events else None


def directed_delta(u,v):
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(u,v))))))


def validate(plan,p,compiled):
    nav=DerivedNavigation(compiled);routes={};issues=[];preserved=[];unverified=[];a=p['annotations']
    for route in plan['routes']:
        points=[a[pid]['point'] for pid in route['places']]
        result=route_nav(nav,points);routes[route['id']]=result
        if result is None:issues.append({'code':'unreachable_ordered_route','route':route['id']})
    opening_audit=observed_openings(p,compiled)
    if opening_audit['unintended_openings']:issues.append({'code':'unintended_openings','samples':opening_audit['unintended_openings']})
    areas=[]
    for allocation in p['allocations']:
        poly=Polygon(allocation['boundary']);area=poly.intersection(compiled['walkable']).area;lo,hi=allocation['area_budget']
        ok=lo<=area<=hi;areas.append({'role':allocation['role'],'walkable_area':area,'budget':[lo,hi],'preserved':ok})
        if not ok:issues.append({'code':'recovery_area_budget','role':allocation['role'],'area':area,'budget':[lo,hi]})
    distances=[]
    for rid,budget in p['distance_budgets'].items():
        result=routes[rid];actual=None if result is None else result['length'];ok=actual is not None and budget[0]<=actual<=budget[1]
        distances.append({'route':rid,'travel_length':actual,'authored_budget':budget,'preserved':ok})
        if not ok:issues.append({'code':'recovery_distance_budget','route':rid,'length':actual,'budget':budget})
    approaches=[]
    for s in ('A','B'):
        main=nav.path(a[s+'_fight']['point'],a[s+'_entry']['point']);alt=nav.path(a[s+'_fight']['point'],a[s+'_side']['point'])
        other_main=next(o for o in p['openings'] if o['id']==s+'_main');other_alt=next(o for o in p['openings'] if o['id']==s+'_side')
        without_main=DerivedNavigation(compiled,blocked=LineString(other_main['aperture']).buffer(p['boundary_thickness']))
        without_alt=DerivedNavigation(compiled,blocked=LineString(other_alt['aperture']).buffer(p['boundary_thickness']))
        # Test access into site just beyond each opening, not a point on a now
        # blocked wall; this independently confirms actual branch reachability.
        main_inside=[a[s+'_entry']['point'][0],a[s+'_entry']['point'][1]+1]
        side_inside=list(a[s+'_side']['point'])
        side_survivor=without_main.path(a[s+'_fight']['point'],side_inside)
        main_survivor=without_alt.path(a[s+'_fight']['point'],main_inside)
        side_crossings=crossed_openings(side_survivor,p);main_crossings=crossed_openings(main_survivor,p)
        alt_survives=s+'_side' in side_crossings and s+'_rear' not in side_crossings
        main_survives=s+'_main' in main_crossings and s+'_rear' not in main_crossings
        approach={'site':s,'main_branch_length':main['length'] if main else None,'side_branch_length':alt['length'] if alt else None,
                  'independent_openings':alt_survives and main_survives,'opening_entry_separation_degrees':aperture_separation(other_main,other_alt),
                  'main_crossings_with_side_closed':main_crossings,'side_crossings_with_main_closed':side_crossings,
                  'shared_before_divergence':s+'_fight','main_opening':s+'_main','side_opening':s+'_side'}
        approaches.append(approach)
        if not approach['independent_openings']:issues.append({'code':'approaches_collapse','site':s})
    # Cross-site navigation is derived from the entire footprint, with no phase
    # labels, team-only walls, hand-authored connection graph or travel bands.
    rotation=nav.path(a['A_hold']['point'],a['B_hold']['point']);switch=routes['CT-A-switch']
    ct_zone=compiled['spaces']['deployment_hall']
    no_CT=DerivedNavigation(compiled,blocked=ct_zone)
    avoiding_ct=no_CT.path(a['A_hold']['point'],a['B_hold']['point'])
    rotation_check={'shortest_length':rotation['length'] if rotation else None,
        'ordered_via_deployment_length':switch['length'] if switch else None,
        'shortest_avoiding_CT_deployment':avoiding_ct['length'] if avoiding_ct else None,
        'passes_CT_deployment':rotation is not None and LineString(rotation['points']).intersects(ct_zone),
        'longest_initial_deployment':max(routes[rid]['length'] for rid in ('CT-A-deploy','CT-B-deploy') if routes[rid])}
    if not rotation_check['passes_CT_deployment']:issues.append({'code':'defender_rotation_bypasses_deployment','detail':rotation_check})
    if rotation and rotation['length']<=rotation_check['longest_initial_deployment']:issues.append({'code':'rotation_not_costly_relative_to_assignment','detail':rotation_check})
    if avoiding_ct and rotation and avoiding_ct['length']<rotation['length']:issues.append({'code':'unintended_rotation_shortcut','detail':rotation_check})
    preserved.extend(['Two independent attacker assignments with shared initial deployment only.',
        'No central playable connector/Mid; the central compound is a solid mass.',
        'Main and side approaches share the prescribed first contest but use separate physical site openings.',
        'Fallback and retake preparation are annotations within rear foyers, not peripheral appendages.',
        'All space remains on the original ground endpoint level; no new vertical tactical effect is invented.'])
    if rotation_check['passes_CT_deployment']:preserved.append('Shortest defender site switch uses CT deployment circulation; front-side bypass is measured separately.')
    budget_ledger=[]
    for route in plan['routes']:
        result=routes[route['id']]
        budget_ledger.append({'route':route['id'],'original_duration_contract':route['outcome']['timing'],
            'travel_length':result['length'] if result else None,'travel_units':p['units'],
            'clearance_requirements':route.get('requirements',[]),'clearance_duration':None,
            'conditional_requirements':route.get('condition'),'combat_or_decision_duration':None,
            'timing_status':'unverified: original seconds are unallocated; no speed or combat-time substitution'})
    unverified.extend(['Every original seconds-based duration remains uncalibrated; distance is not converted to CS travel time.',
        'B main retains its workshop-clearance requirement. No seconds of delay or extra walking are fabricated for clearance.',
        'The original CT switch is the two deployment legs in reverse/forward order, so its 17–19 seconds cannot be explained by two 6–8 second travel legs at one pace.',
        'Reset paths reverse opening travel while original reset durations differ; movement, combat and decision time are not allocated.',
        'Information gain, first-contact timing, exposure, engagement range, retreat safety and retake balance require gameplay or reference evidence.',
        'Conditional attacker flank requires cleared/vacated defender space. Physical navigation is unrestricted by team or phase labels.'])
    violations=[];angles=[]
    for s,space_id in (('A','west_yard'),('B','east_assembly')):
        main=site_ingress(routes[f'T-{s}-main'],p,compiled,space_id)
        for rid in (f'T-{s}-alt',f'CT-{s}-recover'):
            ingress=site_ingress(routes[rid],p,compiled,space_id)
            expected=next(r for r in plan['routes'] if r['id']==rid)['outcome']['entry_angle']['value']
            measured=directed_delta(main['inward_approach_vector'],ingress['inward_approach_vector']) if main and ingress else None
            ok=measured is not None and abs(measured-expected)<1e-6
            angles.append({'route':rid,'expected':expected,'measured':measured,'passed':ok,
                'main_ingress':main,'observed_ingress':ingress,
                'trajectory_delta':directed_delta(main['path_tangent'],ingress['path_tangent']) if main and ingress else None})
            if not ok:violations.append({'requirement':f'{rid} directed ingress {expected} degrees',
                'result':f'Measured {measured}.','status':'violated'})
    unverified.append('entry_angle is evaluated as directed site-ingress sector relative to main ingress; the original contract did not specify a geometric frame. Exact path-tangent/facing angles are reported separately and are not certified as 180 degrees.')
    return {'schema':'playable-composition-validation-v1','plan_sha256':digest(plan),'program_sha256':digest(p),
        'physical_checks_passed':not issues and not violations,'original_requirements_all_preserved':False,'stage_4_authorized':False,
        'candidate_accepted':False,'implementation_tests_are_acceptance':False,'entry_angle_checks':angles,
        'angle_convention':'Directed site-boundary ingress normal, relative to T primary ingress. acos(dot(u,v)); do not abs the dot. Not doorway-axis alignment or camera/path-tangent heading.',
        'recovery_budget_status':p.get('recovery_budget_status','active'),
        'awaiting_visual_review':True,'preserved':preserved,'violations':violations,'unverified':unverified,'issues':issues,
        'area_allocations':areas,'distance_allocations':distances,'approaches':approaches,'rotation':rotation_check,
        'opening_audit':opening_audit,'budget_ledger':budget_ledger,'derived_routes':routes,
        'navigation_source':'complete walkable space = architectural footprint minus explicit solids/walls + opening cuts',
        'numerical_resolution':nav.step,'scope':'One authored Stage 3 composition; no tactical quality thresholds, trained-generator or feasibility-pass claim.'}


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    original=ROOT/'output/strategic-diversity-001/P04/plan.json';plan=json.loads(original.read_text())
    strategic_validation=GameplayValidator().validate(plan)
    if not strategic_validation['passed']:raise ValueError('P04 strategic contract failed.')
    p=program();p['plan_sha256']=digest(plan)
    c=SpatialEmbedder().compose(plan,strategic_validation,space_program=p);report=validate(plan,p,c)
    from p04_route_sightline_audit import audit
    old=json.loads((OUT/'architecture-before/validation.json').read_text());old_p=json.loads((OUT/'architecture-before/composition.json').read_text());old_c=compile_composition(old_p)
    report['architecture_audit']=audit(p,c,old_p)
    from p04_spatial_usefulness import measure
    report['strategy_routes_for_measurement']=plan['routes']
    report['spatial_usefulness']=measure(p,c,report,json.loads((OUT/'usefulness-before/validation.json').read_text()))
    del report['strategy_routes_for_measurement']
    from p04_allocation_reconciliation import reconcile
    reconcile(p,report,OUT)
    comparison=[]
    for s,sid in (('A','west_yard'),('B','east_assembly')):
        original_main=site_ingress(old['derived_routes'][f'T-{s}-main'],old_p,old_c,sid)
        original_retake=site_ingress(old['derived_routes'][f'CT-{s}-recover'],old_p,old_c,sid)
        before_angle=directed_delta(original_main['inward_approach_vector'],original_retake['inward_approach_vector'])
        after=next(row for row in report['entry_angle_checks'] if row['route']==f'CT-{s}-recover')
        comparison.append({'route':f'CT-{s}-recover','before_distance':old['derived_routes'][f'CT-{s}-recover']['length'],
            'after_distance':report['derived_routes'][f'CT-{s}-recover']['length'],
            'unchanged_distance_budget':p['distance_budgets'][f'CT-{s}-recover'],
            'previous_incorrect_axis_audit':90,'before_directed_ingress':before_angle,'after_directed_ingress':after['measured'],
            'before_opening':original_retake['opening'],'after_opening':after['observed_ingress']['opening']})
    report['before_after']=comparison
    report['constraint_provenance']={
        'original_P04':'Coordinate-free deployment rules; ordered route places/purposes; site entry/engagement systems; distinct local secondary approaches; no Mid; rear rotation through deployment; independent recovery; ground endpoint levels; entry angles; original seconds-based timing; B territory clearance and conditional flank.',
        'authored_prototype':'All architectural coordinates, space boundaries, opening positions/widths, solid masses, annotation positions, abstract scale, .8 boundary thickness, area allocations and six distance budgets.',
        'numerical_method':'Raster step .5 and exact segment coverage are numerical settings, not gameplay budgets.'}
    report['acceptance']={'implementation_suite':'Checks algorithm behavior and failure reporting, not map quality.',
        'measured_candidate_constraints_passed':report['physical_checks_passed'],
        'original_semantics_fully_verified':False,'visual_accepted':False,'automatic_generation_demonstrated':False,
        'diversity_demonstrated':False,'stage4_authorized':False,'batch_authorized':False}
    for name,data in [('composition.json',p),('validation.json',report),('original-strategy.json',plan),
                      ('playable-space.geojson',{'type':'FeatureCollection','features':[
                          {'type':'Feature','properties':{'type':'walkable'},'geometry':mapping(c['walkable'])},
                          {'type':'Feature','properties':{'type':'solid'},'geometry':mapping(c['solid'])}]} )]:
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
    from render_p04_architecture import render,write_report
    render(p,c,report,OUT/'plan-clean.png')
    render(p,c,report,OUT/'plan-annotated.png',overlay=True,encounter=True)
    render(p,c,report,OUT/'plan-encounters.png',overlay=True,encounter=True)
    render(p,c,report,OUT/'plan.png',overlay=True,encounter=True);write_report(p,report,OUT)
    from p04_usefulness_report import append_report
    append_report(p,report,OUT)
    old_p['objective_zones']={'A':rect(18,79,26,87),'B':rect(119,83,126,89)}
    render(old_p,old_c,report,OUT/'service-bypasses-before.png',service_before=True)
    # Preserve the failed batch as immutable regression inputs, not material to
    # repair or rewrite. Schema audit states why its footprints are insufficient.
    regression=[]
    for pid in ('P01','P04','P06','P10'):
        for i in range(1,5):
            path=ROOT/f'output/spatial-composition-001/{pid}/E{i}-embedding.json'
            data=json.loads(path.read_text());validation=json.loads(path.with_name(f'E{i}-preservation.json').read_text())
            regression.append({'candidate':f'{pid}-E{i}','input_sha256':digest(data),
                'old_relative_checks_passed':validation['schematic_checks_passed'],
                'old_issue_codes':sorted({v['code'] for v in validation['issues']}),
                'new_complete_space_schema_satisfied':False,'reason':'No explicit architectural boundaries/openings/solid masses; territory-envelope overlap cannot certify intended circulation.'})
    (OUT/'failed-batch-regression.json').write_text(json.dumps(regression,indent=2),encoding='utf-8')
    print(json.dumps({'candidate':'P04-one-composition','physical_checks_passed':report['physical_checks_passed'],
                      'issues':report['issues'],'stage_4_authorized':False,'stopped_for_visual_review':True}))


if __name__=='__main__':run()
