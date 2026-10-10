"""Physical service-access and planar sightline diagnostics for one composition."""
import math
from shapely.geometry import LineString,Point
from shapely.ops import unary_union
from playable_composition import compile_composition,DerivedNavigation
from p04_space_mass_demo import crossed_openings


def audit(p,c,previous):
    old_c=compile_composition(previous);nav=DerivedNavigation(c);old_nav=DerivedNavigation(old_c)
    blocked=unary_union([c['spaces'][s] for s in ('west_yard','east_assembly')])
    old_blocked=unary_union([old_c['spaces'][s] for s in ('west_yard','east_assembly')])
    no_sites=DerivedNavigation(c,blocked=blocked);old_no_sites=DerivedNavigation(old_c,blocked=old_blocked)
    service=[];a=p['annotations'];old_a=previous['annotations']
    for site,start in (('A',[52,52]),('B',[96,54])):
        old_path=old_no_sites.path(start,old_a['CT']['point']);restricted=no_sites.path(start,a['CT']['point'])
        actual=nav.path(start,a['CT']['point'])
        portal=a[site+'_side']['point'];hold=a[site+'_hold']['point']
        visible=c['visibility_standing'].covers(LineString([hold,portal]))
        service.append({'site':site,'service_start':start,
            'before_site_avoiding_route':old_path,'before_crossings':crossed_openings(old_path,previous),
            'after_site_avoiding_route':restricted,'after_actual_route':actual,'after_crossings':crossed_openings(actual,p),
            'defender_contest':{'position':hold,'target':portal,'line_of_sight':visible,
                'line':[hold,portal] if visible else None,
                'scope':'Geometric contest opportunity only; no timing, safe hold or gunfight win certified.'}})
    # Longest directly visible ray from selected tactical positions. Exact full
    # segment coverage forbids sight through solid walls. Head-height, doors,
    # elevation and smoke are absent from this planar Stage 3 representation.
    sightlines=[]
    for pid in ('T','CT','A_entry','A_side','A_hold','B_fight','B_territory','B_side','B_hold'):
        start=a[pid]['point'];best=None
        for degree in range(0,360,2):
            theta=math.radians(degree);v=(math.cos(theta),math.sin(theta));lo,hi=0.,180.
            for _ in range(14):
                mid=(lo+hi)/2;end=[start[i]+v[i]*mid for i in (0,1)]
                if c['visibility_standing'].covers(LineString([start,end])):lo=mid
                else:hi=mid
            if best is None or lo>best['length']:
                best={'source':pid,'points':[start,[start[i]+v[i]*lo for i in (0,1)]],'length':lo,'bearing':degree}
        sightlines.append(best)
    return {'service_routes':service,'long_sightlines':sightlines,
        'sightline_scope':'Standing-eye visibility over explicitly low cover; full-height walls/masses opaque. 2-degree sampling on one flat ground level. Not a complete 3D visibility or combat analysis.',
        'service_shortcut_removed':all(x['after_site_avoiding_route'] is None for x in service),
        'all_service_mouths_geometrically_contestable':all(x['defender_contest']['line_of_sight'] for x in service)}
