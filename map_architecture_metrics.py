"""Versioned soft compactness assessment; never replaces physical/request gates."""
from shapely.geometry import LineString
from shapely.ops import unary_union
from playable_composition import DerivedNavigation

VERSION='complete-route-compactness-v1'

def targets(spec):
    q=spec['soft_preferences']['compactness'];extent=spec['hard_constraints']['max_extent_HU']
    return dict(primary_approach_HU=extent*(1-.25*q),secondary_approach_HU=extent*(1.35-.25*q),
                defensive_assignment_HU=extent*(1-.25*q),complete_site_rotation_HU=extent*(1.5-.55*q),
                playable_span_HU=extent*(1-.1*q))

def assess(spec,p,c,validation):
    limits=targets(spec);rows=[];checks=[]
    galleries={s['id']:c['spaces'][s['id']] for s in p['spaces'] if s['id'].startswith('circulation_gallery_')}
    for rid,r in validation['routes'].items():
        path=r.get('path');total=path['length_HU'] if path else None;connectors={}
        if path:
            for gid,space in galleries.items():
                # Segment-wise avoids collapsing repeated traversal into one
                # geometric length when an intended route returns through a bay.
                length=sum(LineString([a,b]).intersection(space).length for a,b in zip(path['points'],path['points'][1:]))*32
                if length>1e-5:connectors[gid]=length
        category='primary_approach_HU' if rid.startswith('T-') and rid.endswith('main') else 'secondary_approach_HU' if rid.startswith('T-') and rid.endswith('secondary') else 'defensive_assignment_HU' if rid.startswith('CT-') and rid.endswith('deploy') else 'complete_site_rotation_HU' if rid=='CT-rotate' else None
        met=total is not None and total<=limits[category] if category else None
        if category:checks.append(dict(measurement=rid,value_HU=total,target_HU=limits[category],achieved=met))
        rows.append(dict(route=rid,complete_ordered_HU=total,unrestricted_shortest_HU=r.get('unrestricted_shortest_length_HU'),connector_only_HU=sum(connectors.values()),connector_breakdown_HU=connectors,
                         scope='Connector subset is travel inside named continuous circulation galleries, not the complete approach/rotation and not opening width.',compact_target_HU=limits.get(category),compact_target_achieved=met))
    x0,y0,x1,y1=c['walkable'].bounds;span=max(x1-x0,y1-y0)*32
    checks.append(dict(measurement='playable_span',value_HU=span,target_HU=limits['playable_span_HU'],achieved=span<=limits['playable_span_HU']))
    # Add the distinct defender holding endpoints rather than silently treating
    # the plant/role marker rotation as the same measurement.
    hold_length=None
    if 'A' in p['defender_positions'] and 'B' in p['defender_positions']:
        points=list(p['physical_route_waypoints']['CT-rotate']);points[0]=p['defender_positions']['A'];points[-1]=p['defender_positions']['B']
        clear=c['walkable'].buffer(-.5,join_style=2);legs=[]
        for index,(a,b) in enumerate(zip(points,points[1:])):
            ids=p.get('physical_route_leg_spaces',{}).get('CT-rotate')
            allowed=unary_union([c['spaces'][sid] for sid in ids[index]]) if ids else c['walkable']
            nav=DerivedNavigation(dict(c,walkable=clear.intersection(allowed)));legs.append(nav.path(a,b))
        if all(legs):hold_length=sum(leg['length'] for leg in legs)*32
    return dict(version=VERSION,requested=spec['soft_preferences']['compactness'],achieved=all(x['achieved'] for x in checks),checks=checks,route_distances=rows,
                complete_rotation_holding_to_holding_HU=hold_length,complete_rotation_site_marker_to_site_marker_HU=validation['routes'].get('CT-rotate',{}).get('path',{}).get('length_HU') if validation['routes'].get('CT-rotate',{}).get('path') else None,
                definition='Compact means all complete primary/secondary approaches, defensive assignments, site-marker rear rotation and playable span meet the declared preference-dependent distance targets. These are authored experiment targets, not calibrated CS2 balance/timing constraints.',
                aggregation='All target checks must be achieved; no average hides an overlong route. Soft failure does not reject a physically valid/request-adherent candidate.',targets=limits,timing_verified=False)
