"""Physical/structural acceptance for generated P04 programs, including failures.

Reuses exact walkable compilation, raster navigation and measured site ingress.
Never equates implementation tests or graph complexity with gameplay acceptance.
"""
import math
import numpy as np
from shapely.geometry import LineString,Point,Polygon
from shapely.affinity import translate
from playable_composition import DerivedNavigation,observed_openings
from p04_space_mass_demo import route_nav,crossed_openings,site_ingress,directed_delta
from p04_comparison_round import rays
from semantic_pipeline import digest

def validate(plan,p,c,cfg):
    issues=list(p.get('composition_errors',[]));warnings=[];a={k:x['point'] for k,x in p['annotations'].items()}
    nav=DerivedNavigation(c);hull={**c,'walkable':c['walkable'].buffer(-cfg['scale']['player_width_source_units']/64,join_style=2)};player=DerivedNavigation(hull)
    if digest(plan)!=p['plan_sha256']:issues.append('Strategy hash changed')
    routes={}
    for route in plan['routes']:
        points=[a[k] for k in route['places']];actual=route_nav(nav,points);clear=route_nav(player,points)
        routes[route['id']]=dict(path=actual,player_clearance_connected=clear is not None,crossed_openings=crossed_openings(actual,p))
        if actual is None:issues.append('Unreachable ordered route: '+route['id'])
        elif clear is None:issues.append('Player clearance fails: '+route['id'])
    audit=observed_openings(p,c)
    if audit['unintended_openings']:issues.append('Undeclared passable architectural boundary')
    components=len(c['walkable'].geoms) if hasattr(c['walkable'],'geoms') else 1
    if components!=1:issues.append('Disconnected walkable components: '+str(components))
    widths=[]
    for o in p['openings']:
        line=LineString(o['aperture']);v=np.array(o['aperture'][1])-o['aperture'][0];v=v/np.linalg.norm(v);n=np.array([-v[1],v[0]]);depth=p['boundary_thickness']
        actual=line.intersection(c['walkable']).intersection(translate(c['walkable'],xoff=n[0]*depth,yoff=n[1]*depth)).intersection(translate(c['walkable'],xoff=-n[0]*depth,yoff=-n[1]*depth))
        width=dict(id=o['id'],nominal_HU=line.length*32,actual_clear_HU=actual.length*32,player_center_span_HU=line.intersection(hull['walkable']).length*32);widths.append(width)
        if abs(width['nominal_HU']-width['actual_clear_HU'])>1e-5:issues.append('Aperture interference: '+o['id'])
        if width['actual_clear_HU']<cfg['scale']['player_width_source_units']:issues.append('Narrow opening: '+o['id'])
    site_spaces=p.get('site_spaces',{'A':'west_yard','B':'east_assembly'})
    removed=c['spaces'][site_spaces['A']].union(c['spaces'][site_spaces['B']])
    bypass=DerivedNavigation(c,blocked=removed).path(a['T'],a['CT'])
    if bypass:issues.append('Site-free attacker access to CT circulation')
    sectors={}
    for site in ('A','B'):
        ids=['T-'+site+'-main','T-'+site+'-alt','CT-'+site+'-recover']
        entries=[site_ingress(routes[r]['path'],p,c,site_spaces[site]) for r in ids]
        if not all(entries):issues.append('Cannot establish site entry sectors: '+site)
        else:
            vectors=[e['inward_approach_vector'] for e in entries]
            sectors[site]=dict(main=entries[0],secondary=entries[1],retake=entries[2],secondary_delta_degrees=directed_delta(vectors[0],vectors[1]),retake_delta_degrees=directed_delta(vectors[0],vectors[2]))
            if abs(sectors[site]['secondary_delta_degrees']-90)>1e-6:issues.append('Equivalent or wrong alternate ingress: '+site)
            if abs(sectors[site]['retake_delta_degrees']-180)>1e-6:issues.append('Retake ingress not opposite primary: '+site)
        for suffix,opening in [('main','main'),('alt','side')]:
            if site+'_'+opening not in routes['T-'+site+'-'+suffix]['crossed_openings']:issues.append('Wrong observed '+suffix+' entry: '+site)
    b_invest=p.get('required_investment_space','B_investment')
    b_route=routes['T-B-main']['path']
    investment=False
    if b_route and b_invest in c['spaces']:
        investment=LineString(b_route['points']).intersection(c['spaces'][b_invest]).length>1
    if not investment:issues.append('B primary route lacks investment territory')
    shared=set(routes['T-A-main']['crossed_openings'])&set(routes['T-B-main']['crossed_openings'])
    if shared:issues.append('Attacker commitments share circulation openings: '+', '.join(sorted(shared)))
    # Also inspect geometric road intersections, not only declared crossings.
    deployment_id='CT_deployment' if 'CT_deployment' in c['spaces'] else 'deployment_hall'
    rotation=nav.path(a['A_hold'],a['B_hold']);avoiding=DerivedNavigation(c,blocked=c['spaces'][deployment_id]).path(a['A_hold'],a['B_hold'])
    crosses=crossed_openings(rotation,p);deploy_lengths=[routes['CT-'+s+'-deploy']['path']['length'] for s in ('A','B') if routes['CT-'+s+'-deploy']['path']]
    if rotation is None:issues.append('Disconnected defensive rotation')
    elif not LineString(rotation['points']).intersection(c['spaces'][deployment_id]).length>1:issues.append('Shortest rotation bypasses rear deployment')
    if rotation and deploy_lengths and rotation['length']<=max(deploy_lengths):issues.append('Rotation no longer than an initial assignment')
    margin=(avoiding['length']-rotation['length'])*32 if avoiding and rotation else None
    if margin is not None and margin<=0:issues.append('Non-rear rotation shortcut')
    elif margin is not None and margin<cfg['acceptance']['weak_rotation_advantage_HU']:warnings.append('Weak rear rotation distance advantage: '+str(round(margin))+' HU (diagnostic, not calibrated gameplay).')
    arrival=[]
    for site in ('A','B'):
        t=route_nav(nav,[a[k] for k in ('T',site+'_prep',site+'_fight')]);ct=routes['CT-'+site+'-contest']['path'];hold=routes['CT-'+site+'-deploy']['path'];entry=routes['T-'+site+'-main']['path']
        row=dict(site=site,T_to_encounter_HU=t['length']*32 if t else None,CT_ordered_to_same_encounter_HU=ct['length']*32 if ct else None,CT_to_hold_HU=hold['length']*32 if hold else None,T_to_main_entry_HU=entry['length']*32 if entry else None)
        row['distance_conflict']=bool(t and ct and ct['length']>=t['length']);arrival.append(row)
        if row['distance_conflict']:warnings.append(site+': CT ordered same-encounter distance exceeds T; early contest timing unresolved.')
    positions=p.get('defender_positions',{})
    contacts=[]
    for name,start in positions.items():
        if not c['walkable'].covers(Point(start)):issues.append('Defender position in solid: '+name)
        site=name[0]
        if site in ('A','B'):
            contacts.append(dict(defender=name,site=site,standing_visible=c['visibility_standing'].covers(LineString([start,a[site+'_fight']]))))
    allocations=[dict(id=x['id'],gross_plan_area=Polygon(x['boundary']).area,current_walkable_plan_area=Polygon(x['boundary']).intersection(c['walkable']).area,purpose=x['purpose'],status='Design assumption; no inherited recovery minimum.') for x in p['allocations']]
    longest=rays(c,positions)
    if longest and max(x['length_HU'] for x in longest)>1536:warnings.append('At least one sampled standing sightline exceeds 1536 HU; architecture may still expose long lanes.')
    # Explicitly retain unsolved semantic claims rather than passing by length.
    unresolved=['All P04 travel/first-contact timing ranges: no runtime calibration.',
        'Encounter control and information, utility, retreat safety and retake viability.',
        'Conditional flank assumes captured A and vacated rear defense; navigation alone cannot verify those conditions.',
        'Ground-only, static planar geometry: no doors, jumping, crowding, headroom or full 3D visibility.']
    return dict(plan_sha256=p['plan_sha256'],violations=list(dict.fromkeys(issues)),warnings=warnings,
        strategic_routes=routes,opening_audit=audit,openings=widths,walkable_components=components,
        attacker_CT_access_with_both_sites_blocked=bypass,entry_sectors=sectors,B_primary_investment_observed=investment,
        attacker_commitments_shared_openings=sorted(shared),defender_rotation=dict(shortest_path=rotation,CT_avoiding_path=avoiding,crossed_openings=crosses,rear_advantage_HU=margin),
        arrival_distance_checks=arrival,allocations=allocations,defender_positions=positions,longest_sampled_standing_rays=longest,contact_sightline_checks=contacts,
        unresolved=unresolved,timing_verified=False,gameplay_quality_accepted=False,visually_accepted=False,stage4_authorized=False)
