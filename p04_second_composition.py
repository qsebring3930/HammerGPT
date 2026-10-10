"""One authorized, manually composed P04 alternative. Stage 4 stays paused.

Spatial authorship is explicit. Reuses physical compilation and derived navigation,
not a claimed automatic composition generator. Never writes candidate 001.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, LineString, Point, mapping
from playable_composition import compile_composition, DerivedNavigation, observed_openings
from p04_space_mass_demo import route_nav, crossed_openings, site_ingress, directed_delta
from semantic_pipeline import digest

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/p04-playable-composition-002'
FIRST = ROOT / 'output/p04-playable-composition-001'
STRATEGY = ROOT / 'output/strategic-diversity-001/P04/plan.json'

def rect(x0,y0,x1,y1):
    return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]

def build():
    spaces=[]; openings=[]
    def space(i,b,d): spaces.append(dict(id=i,boundary=b,description=d))
    def door(i,a,b,line,purpose): openings.append(dict(id=i,spaces=[a,b],aperture=line,purpose=purpose))
    space('T_deployment',[[10,8],[30,8],[30,28],[26,28],[26,40],[10,40]],'Integrated loading court with a narrowed north frontage: north A or east B assignment.')
    space('A_forecourt',rect(10,40,46,55),'A staging and first contact; east main entrance or local west gallery.')
    space('A_gallery',rect(10,55,28,74),'Local alternate approach to west court face; terminates at contested entry.')
    space('A_court',[[28,55],[58,55],[58,77],[52,77],[52,83],[28,83]],'Objective court, south forecourt entry, west gallery entry, north defender receiving edge.')
    space('A_rear',rect(28,83,65,95),'Rear receiving arcade; fallback and preparation are annotations within circulation.')
    space('CT_west_arm',rect(65,83,76,95),'Rear building circulation to A; joins B circulation only through deployment.')
    space('CT_deployment',[[76,83],[94,83],[94,67],[116,67],[116,95],[76,95]],'Elbow deployment hall: west A and east B assignments diverge around building frontage.')
    space('B_rear',[[116,20],[130,20],[130,48],[124,48],[124,65],[130,65],[130,79],[116,79]],'East receiving court narrows behind workshop building frontage before opening into CT approach; no attacker service bypass.')
    space('B_departure',[[30,12],[43,12],[43,8],[58,8],[58,28],[48,28],[48,24],[30,24]],'Loading apron along recessed building frontage: B commitment separated from A by solid buildings.')
    space('B_lobby',[[58,8],[76,8],[76,12],[86,12],[86,28],[58,28]],'B loading entrance and encounter lobby; workshop investment north or south entry east.')
    space('B_workshop',[[58,28],[70,28],[70,31],[86,31],[86,48],[58,48]],'Workshop threshold turns into execute territory; frontage forms an entry-clearing corner.')
    space('B_side',rect(86,8,108,20),'Local south loading entrance; provides a different site sector, not CT access.')
    space('B_court',[[86,20],[116,20],[116,48],[100,48],[100,43],[86,43]],'B loading yard: west execute entry, south alternate entry, east rear defender access.')
    door('A_staging','T_deployment','A_forecourt',[[22,40],[26,40]],'Recessed north assignment threshold keeps the A gallery off the spawn sightline')
    door('A_main','A_forecourt','A_court',[[40,55],[46,55]],'Primary south court entry')
    door('A_gallery_access','A_forecourt','A_gallery',[[12,55],[18,55]],'Local alternate investment at the opposite frontage from the primary entrance')
    door('A_side','A_gallery','A_court',[[28,64],[28,69]],'West entry; different clearing sector')
    door('A_rear','A_court','A_rear',[[44,83],[49,83]],'Defender north receiving / opposite retake sector')
    door('A_rotation','A_rear','CT_west_arm',[[65,86],[65,92]],'Protected rear A circulation')
    door('CT_A','CT_west_arm','CT_deployment',[[76,86],[76,92]],'West deployment assignment')
    door('CT_B','CT_deployment','B_rear',[[116,70],[116,76]],'South/east deployment assignment')
    door('B_rear','B_court','B_rear',[[116,30],[116,36]],'East defender receiving / opposite retake sector')
    door('T_B','T_deployment','B_departure',[[30,15],[30,21]],'East attacker assignment')
    door('B_staging','B_departure','B_lobby',[[58,15],[58,21]],'B lobby threshold')
    door('B_workshop_access','B_lobby','B_workshop',[[61,28],[67,28]],'Enter workshop before primary execute')
    door('B_main','B_workshop','B_court',[[86,34],[86,40]],'West workshop execute entry')
    door('B_side_access','B_lobby','B_side',[[86,12],[86,18]],'Local south route commitment')
    door('B_side','B_side','B_court',[[91,20],[97,20]],'South site entry; distinct from workshop sector')
    pts={'T':[20,18],'CT':[103,83],'A':[39,75],'B':[108,32],
         'A_prep':[20,43],'A_fight':[20,49],'A_entry':[43,59],'A_side':[31,67],
         'A_hold':[39,72],'A_rear':[54,89],'A_retake':[45,89],
         'B_prep':[47,18],'B_fight':[71,19],'B_territory':[72,38],
         'B_entry':[90,37],'B_side':[95,25],'B_hold':[105,34],
         'B_rear':[123,42],'B_retake':[123,32]}
    masses=[dict(id='A_building_wing',boundary=rect(46,64,58,70),height_source_units=160,height_class='full_height',purpose='Attached building frontage breaks main-to-rear visibility and separates plant clearing sectors.'),
            dict(id='B_back_bay',boundary=rect(109,41,116,48),height_source_units=160,height_class='full_height',purpose='Rear loading bay defines a defender pocket and breaks yard-to-gallery visibility.'),
            dict(id='A_low_cover',boundary=rect(35,73,38,75),height_source_units=48,height_class='low_cover',purpose='Plant protection; standing sightlines pass over it.'),
            dict(id='B_low_cover',boundary=rect(102,27,105,29),height_source_units=48,height_class='low_cover',purpose='South entry plant cover, not a full-height sight blocker.')]
    first=json.loads((FIRST/'composition.json').read_text())
    return dict(schema='playable-space-mass-openings-v1',candidate='P04-composition-002-authored',
        plan_sha256=digest(json.loads(STRATEGY.read_text())),
        strategy_source_file_sha256=hashlib.sha256(STRATEGY.read_bytes()).hexdigest(),
        authorship='Manual architectural program; reusable compiler/navigation/measurement/rendering only.',
        units='Plan units; provisional 32 HU/unit, no travel-time calibration.',
        envelope=rect(0,0,140,113),boundary_thickness=.8,spaces=spaces,openings=openings,
        internal_masses=masses,annotations={k:dict(point=v) for k,v in pts.items()},
        site_spaces={'A':'A_court','B':'B_court'},elevation={'all_walkable_space':0},
        engine_scale=first['engine_scale'],
        objective_zones={'A':rect(33,71,44,79),'B':rect(100,25,112,37)},
        allocations=[dict(id='A_fallback',boundary=rect(50,85,60,93),purpose='Rear arcade receiving/withdrawal, 80 plan square units gross.'),
                     dict(id='A_retake_preparation',boundary=rect(39,85,48,93),purpose='Local north-entry regrouping, 72 gross; shares rear architecture.'),
                     dict(id='B_fallback',boundary=rect(119,39,127,47),purpose='Receiving bay in east gallery, 64 gross.'),
                     dict(id='B_retake_preparation',boundary=rect(119,27,127,36),purpose='Preparation next to east site aperture, 72 gross.')],
        historical_budget_source='Candidate 001: original values and unapproved proposals are preserved verbatim in budget-history.json; none is a universal constraint on candidate 002.',
        references=[dict(source='output/annotations/dust2-boundaries-v4/overview.png',decision='A forecourt opens through a narrower threshold into a courtyard; no Dust2 Mid copied.'),
                    dict(source='output/annotations/cache-reviewed-v1/overview.png',decision='Different local entry faces and receiving edges for each objective; A main / halls and B main inform entry separation.'),
                    dict(source='output/annotations/train-reviewed-v1/overview.png',decision='Building-attached wings divide objective clearing sectors rather than isolated blocks.'),
                    dict(source='output/annotations/cobblestone-reviewed-v1/overview.png',decision='B lobby, investment threshold and execute territory are separated by architectural edges.')],
        reference_limit='Qualitative arrangements from inspected NAV overviews; dimensions and cover heights authored, not extracted/calibrated.')

def validate(p,c,plan):
    a={k:v['point'] for k,v in p['annotations'].items()};nav=DerivedNavigation(c)
    hull={**c,'walkable':c['walkable'].buffer(-.5,join_style=2)};clear=DerivedNavigation(hull)
    routes={};issues=[]
    for r in plan['routes']:
        route=route_nav(nav,[a[k] for k in r['places']]); width=route_nav(clear,[a[k] for k in r['places']])
        routes[r['id']]={'path':route,'player_clearance_connected':width is not None,'crossed_openings':crossed_openings(route,p)}
        if route is None or width is None: issues.append('Unreachable or player-width blocked: '+r['id'])
    audit=observed_openings(p,c)
    if audit['unintended_openings']: issues.append('Unintended architectural boundary openings')
    doors=[]
    for o in p['openings']:
        line=LineString(o['aperture']);v=np.array(o['aperture'][1])-o['aperture'][0];v=v/np.linalg.norm(v);n=np.array([-v[1],v[0]])
        from shapely.affinity import translate
        actual=line.intersection(c['walkable']).intersection(translate(c['walkable'],xoff=n[0]*.8,yoff=n[1]*.8)).intersection(translate(c['walkable'],xoff=-n[0]*.8,yoff=-n[1]*.8))
        center=line.intersection(hull['walkable'])
        doors.append(dict(id=o['id'],nominal_HU=line.length*32,actual_clear_HU=actual.length*32,player_center_span_HU=center.length*32))
        if abs(actual.length-line.length)>1e-6: issues.append('Aperture interference: '+o['id'])
    sectors={};closures={}
    for s in ('A','B'):
        primary=routes['T-'+s+'-main']['path'];alt=routes['T-'+s+'-alt']['path'];retake=routes['CT-'+s+'-recover']['path']
        ingress=[site_ingress(x,p,c,p['site_spaces'][s]) for x in (primary,alt,retake)]
        if all(ingress):
            sectors[s]=dict(main=ingress[0],secondary=ingress[1],retake=ingress[2],
                secondary_delta_degrees=directed_delta(ingress[0]['inward_approach_vector'],ingress[1]['inward_approach_vector']),
                retake_delta_degrees=directed_delta(ingress[0]['inward_approach_vector'],ingress[2]['inward_approach_vector']))
            if sectors[s]['secondary_delta_degrees']!=90 or sectors[s]['retake_delta_degrees']!=180:issues.append('Ingress sector contract violation: '+s)
        else:issues.append('Missing observed site ingress: '+s)
        for kind in ('main','side'):
            o=next(o for o in p['openings'] if o['id']==s+'_'+kind)
            blocked=LineString(o['aperture']).buffer(.85,cap_style=2)
            sealed=DerivedNavigation(c,blocked=blocked)
            end=s+'_entry' if kind=='main' else s+'_side'
            path=sealed.path(a[s+'_fight'],a[end]);cross=crossed_openings(path,p)
            closures[s+'_'+kind]=dict(path_remaining=path is not None,crossed_openings=cross,
                explanation='A remaining route must go through the other site entrance or captured rear; it is not an undeclared seam.')
    t_a=routes['T-A-main']['crossed_openings'];t_b=routes['T-B-main']['crossed_openings']
    shared=set(t_a)&set(t_b)
    if shared:issues.append('Primary attacker commitments share openings: '+str(shared))
    direct_rear=DerivedNavigation(c,blocked=c['spaces']['A_court'].union(c['spaces']['B_court'])).path(a['T'],a['CT'])
    if direct_rear:issues.append('Attacker bypass to CT without traversing either site')
    for s in ('A','B'):
        for suffix,opening in (('main','main'),('alt','side')):
            if s+'_'+opening not in routes['T-'+s+'-'+suffix]['crossed_openings']:
                issues.append('Declared approach uses wrong entry: '+s+' '+suffix)
    rotation=nav.path(a['A_hold'],a['B_hold']);rotation_cross=crossed_openings(rotation,p)
    # Block CT deployment itself: the alternate physical route goes back through T.
    avoiding=DerivedNavigation(c,blocked=c['spaces']['CT_deployment']).path(a['A_hold'],a['B_hold'])
    if not {'CT_A','CT_B'}.issubset(rotation_cross):issues.append('Shortest defender rotation bypasses deployment')
    deploy_max=max(routes['CT-'+s+'-deploy']['path']['length'] for s in ('A','B'))
    if rotation and rotation['length']<=deploy_max:issues.append('Site rotation no longer than initial assignment')
    if avoiding and rotation and avoiding['length']<=rotation['length']:issues.append('Non-rear rotation shortcut')
    allocations=[dict(id=x['id'],gross_plan_area=Polygon(x['boundary']).area,
        current_walkable_plan_area=Polygon(x['boundary']).intersection(c['walkable']).area,
        purpose=x['purpose'],acceptance_budget='Design assumption only; no inherited minimum imposed.') for x in p['allocations']]
    plants=[dict(site=s,gross_HU2=Polygon(b).area*1024,
        available_floor_HU2=Polygon(b).intersection(c['walkable']).area*1024,
        player_center_region_HU2=Polygon(b).intersection(hull['walkable']).area*1024) for s,b in p['objective_zones'].items()]
    # Rays measured against standing visibility, never against the route graph.
    defender_points={'A_court':[39,72],'A_gallery_contact':[15,62],
        'B_yard':[105,34],'B_workshop_contact':[64,32],'B_rear_receiving':[123,37]}
    rays=[]
    for name,start in defender_points.items():
        best=None
        for degrees in range(0,360,5):
            v=[math.cos(math.radians(degrees)),math.sin(math.radians(degrees))]
            lo=0.;hi=140.
            for _ in range(18):
                mid=(lo+hi)/2;end=[start[i]+mid*v[i] for i in range(2)]
                if c['visibility_standing'].covers(LineString([start,end])):lo=mid
                else:hi=mid
            if best is None or lo>best['length_plan_units']:
                best=dict(defender=name,start=start,end=[start[i]+lo*v[i] for i in range(2)],length_plan_units=lo,length_HU=lo*32)
        rays.append(best)
    return dict(candidate=p['candidate'],plan_sha256=p['plan_sha256'],implementation_checks='Candidate checks below are geometric evidence, not gameplay acceptance.',
        violations=issues,strategic_routes=routes,openings=doors,opening_audit=audit,entry_sectors=sectors,
        sealed_opening_tests=closures,primary_commitments_shared_openings=sorted(shared),
        attacker_CT_access_with_both_sites_blocked=direct_rear,
        defender_rotation=dict(shortest_path=rotation,crossed_openings=rotation_cross,
            initial_assignment_max_length=deploy_max,CT_avoiding_path=avoiding),
        allocations=allocations,plant_regions=plants,defender_positions=defender_points,longest_sampled_standing_rays=rays,
        sightline_method='Planar opaque full-height boundaries; 5-degree rays from authored defender positions. Standing eye 64 HU sees over 48 HU cover. Not full 3D visibility or exhaustive maximum.',
        unverified=['Travel timing and first-contact timing; no distance-to-seconds substitution.',
            'Defender contest strength, smoke/utility, visibility from eye positions, safe retreat and retake viability.',
            'The semantic information/range/conditional flank claims need engine/playtest evidence.',
            'Architectural quality and proportions require visual review; no automatic-generation evidence.'],
        automatic_composition_generation=False,visually_accepted=False,stage_4_authorized=False)

def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)

def render(p,c,r,overlay=False):
    im=Image.new('RGB',(1800,1600),'#101923');d=ImageDraw.Draw(im)
    scale=11.2; ox=100;oy=1450
    def xy(v):return (ox+v[0]*scale,oy-v[1]*scale)
    def poly(g,fill,outline=None):
        if g.is_empty:return
        if hasattr(g,'geoms'):
            for part in g.geoms:poly(part,fill,outline)
        elif isinstance(g,Polygon):
            d.polygon([xy(v) for v in g.exterior.coords],fill=fill,outline=outline)
            for ring in g.interiors:d.polygon([xy(v) for v in ring.coords],fill='#101923')
    d.text((80,35),'P04 · Composition 2 · Authored architectural alternative',font=font(34),fill='white')
    d.text((80,85),'Same strategy · provisional 32 HU/unit · Stage 4 paused · no engine geometry',font=font(24),fill='#bccbd7')
    poly(c['walkable'],'#718b9c')
    for i in ('A_court','B_court'):poly(c['spaces'][i].intersection(c['walkable']),'#9bb1bc')
    for mass in p['internal_masses']:
        poly(Polygon(mass['boundary']),'#bec6be' if mass['height_source_units']==48 else '#263544', '#e3ded0' if mass['height_source_units']==48 else None)
    for o in p['openings']:d.line([xy(v) for v in o['aperture']],fill='#c3e6e8',width=5)
    for s,b in p['objective_zones'].items():
        pts=[xy(v) for v in b];d.line(pts+[pts[0]],fill='#e8c778',width=3)
        pos=p['annotations'][s]['point'];d.text(xy([pos[0]-1,pos[1]+2]),s,font=font(42),fill='#fff0ac')
    for s in ('T','CT'):
        pos=p['annotations'][s]['point'];d.text(xy([pos[0]-4,pos[1]+2]),s+' spawn',font=font(22),fill='#f8e8c5' if s=='T' else '#d9edf8')
    if overlay:
        groups=[('T-A-main','#efbd6c'),('T-A-alt','#d99ba5'),('T-B-main','#efbd6c'),('T-B-alt','#d99ba5'),('CT-A-deploy','#63d3ec'),('CT-B-deploy','#63d3ec'),('CT-A-switch','#83acec')]
        for rid,color in groups:
            route=r['strategic_routes'][rid]['path']
            if route:d.line([xy(v) for v in route['points']],fill=color,width=4)
        labels={'A_prep':'A staging','A_fight':'A contact','A_side':'A west entry','A_retake':'A retake','B_fight':'B contact','B_territory':'Workshop execute','B_side':'South entry','B_retake':'B retake'}
        for k,text in labels.items():
            at=xy(p['annotations'][k]['point']);d.ellipse((at[0]-5,at[1]-5,at[0]+5,at[1]+5),fill='#fbdd8a');d.text((at[0]+8,at[1]-20),text,font=font(19),fill='white',stroke_width=2,stroke_fill='#17212c')
        for ray in r['longest_sampled_standing_rays']:
            d.line([xy(ray['start']),xy(ray['end'])],fill='#fb7276',width=3)
        for start in r['defender_positions'].values():
            at=xy(start);d.rectangle((at[0]-5,at[1]-5,at[0]+5,at[1]+5),fill='#71e0f6')
        d.text((80,1515),'Orange primary · pink alternate · cyan CT positions/deployment · blue rotation · red sampled standing sightlines',font=font(21),fill='#dce3e9')
    else:
        d.text((80,1515),'Light floor: sites · blue-gray: circulation · dark: solid/full-height · pale blocks: 48 HU cover · cyan: openings',font=font(22),fill='#dce3e9')
    # Same scale marker on both candidate-2 views; players and boundaries explicit.
    d.rectangle((1600,1250,1600+scale,1250+scale),fill='#fff0ac');d.text((1510,1280),'32 HU player',font=font(21),fill='white')
    d.line((1500,1380,1500+8*scale,1380),fill='white',width=4);d.text((1490,1400),'256 HU',font=font(21),fill='white')
    return im

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=OUT/'frozen-first-manifest.json'
    frozen=json.loads(manifest.read_text()) if manifest.exists() else {name:hashlib.sha256((FIRST/name).read_bytes()).hexdigest() for name in ('composition.json','validation.json','plan-clean.png','plan-encounters.png','review.md')}
    assert all(hashlib.sha256((FIRST/n).read_bytes()).hexdigest()==h for n,h in frozen.items()),'Frozen first candidate changed before run'
    p=build();plan=json.loads(STRATEGY.read_text());c=compile_composition(p);r=validate(p,c,plan)
    def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')
    save('composition.json',p);save('validation.json',r);save('frozen-first-manifest.json',frozen)
    first=json.loads((FIRST/'composition.json').read_text());first_result=json.loads((FIRST/'validation.json').read_text())
    save('budget-history.json',dict(first_candidate='001 frozen',original_allocations=first.get('allocations'),
        original_distance_budgets=first.get('distance_budgets'),unapproved_revision_proposals=first.get('budget_revision_proposals'),
        first_current_reconciliation=first_result.get('allocation_reconciliation'),first_validation_area_measurements=first_result.get('area_allocations'),
        first_validation_distance_measurements=first_result.get('distance_allocations'),second_current_allocations=r['allocations'],
        interpretation='Historical assumptions retained; current candidate-2 allocations are independently authored, no universal recovery minimum.'))
    save('playable-space.geojson',dict(type='FeatureCollection',features=[dict(type='Feature',properties={'kind':k},geometry=mapping(c[k])) for k in ('walkable','solid','walls','fixtures')]))
    render(p,c,r).save(OUT/'plan-clean.png');render(p,c,r,True).save(OUT/'plan-encounters.png')
    comparison=Image.new('RGB',(3600,1700),'#101923');draw=ImageDraw.Draw(comparison)
    draw.text((60,20),'Frozen composition 1 — unchanged',font=font(30),fill='white')
    draw.text((1860,20),'Composition 2 — manual spatial alternative',font=font(30),fill='white')
    comparison.paste(Image.open(FIRST/'plan-clean.png').convert('RGB'),(0,100));comparison.paste(Image.open(OUT/'plan-clean.png'),(1800,100))
    comparison.save(OUT/'comparison-clean.png')
    lengths={k:v['path']['length']*32 for k,v in r['strategic_routes'].items()}
    rot=r['defender_rotation'];rear=rot['shortest_path']['length']*32;outside=rot['CT_avoiding_path']['length']*32
    report=f'''# P04: one additional Stage 3 composition, awaiting visual review

Stage 4 and batch generation remain paused. The graybox proposal is deferred.
Only candidate 002 was composed. Candidate 001's composition, validation, clean
image, encounter image and review are hash-frozen in frozen-first-manifest.json.
No VMAP, mesh or engine geometry was created. The unchanged semantic strategy
hash is `{p['plan_sha256']}`.

## What changed spatially

| Aspect | Frozen first composition | Second composition |
|---|---|---|
| Objectives | Paired upper-left/upper-right complexes | A above the western approach; B east of a southern workshop |
| T deployment | Lower central court branching outward | Integrated southwest loading court: north frontage versus east apron |
| A approach | West forecourt into yard plus service-side entry | Frontage encounter, south court entrance and west gallery entry |
| B approach | Eastern gate/workshop sequence below B | Eastward loading lobby, north workshop investment, west execute entry; local south alternative |
| CT circulation | Upper rear gallery linking both sites | North arcade into elbow deployment, then east receiving court behind B |
| Receiving space | Separate labelled allocations within rear spaces | Fallback/regroup annotations inside arcade and receiving court, not new rooms |

This is a new spatial program, not a transformed copy: B's primary ingress is
eastward while A's is northward; site spacing, deployment frontage, architectural
partitions and rear circulation all change. The macro strategic organization
deliberately remains P04. Spatial difference does not imply strategic diversity.

## Authorship and references

All architectural coordinates, contours, openings, cover, role annotations,
plant regions, scale and new recovery allocations were manually authored.
There is **no automatic composition generation procedure** here. Reusable code
compiles boundaries/masses/openings into floor extent, derives physical navigation,
checks width/entry sectors/bypasses, measures areas and renders the plan.
Those operations do not choose the architecture. This second handcrafted layout
provides another representation experiment, not evidence that the generator works
or completion of the four-composition diversity milestone.

- Dust2 reviewed NAV: narrower threshold opening into A's forecourt/courtyard;
  the recessed deployment threshold and west gallery entrance break direct spawn visibility.
- Cache reviewed NAV: local site entries on different faces; A south/west and
  B west/south entries lead to different clearing sectors.
- Train reviewed NAV: building-attached frontage divides objective space;
  A's attached building wing and B's back loading bay are full-height architecture.
- Cobblestone reviewed NAV: separate lobby, investment and execute phases;
  B's workshop entrance turns around building frontage before its west execute threshold.

These are qualitative references, not measured replicas. Proportions and cover
heights are provisional assumptions. Each exact reference path is in composition.json.

## Navigation and clearance evidence

- 19/19 ordered strategy routes connected, also after erosion for a provisional
  32 by 32 HU player footprint. Raster resolution: 0.5 plan units = 16 HU;
  every smoothed path segment is checked against exact walkable polygons.
- 15/15 openings have nominal width equal to actual clear width. Range 128–192 HU;
  A side and rear openings are 160 HU, B main is 192 HU. Boundaries are 25.6 HU thick.
- No unintended openings detected in sampled shared boundaries. No site-free
  T-to-CT bypass: blocking both objective courts disconnects those deployments.
- A/B main and alternate routes use different observed entry openings and 90°
  inward sectors. Retake ingress opposes primary ingress by 180° at both sites.
  These measure directed boundary-crossing normals, not door hinge orientation,
  camera heading, or the angle between the final path segments.
- Primary attacker paths share no openings. Their only common architectural
  space is T deployment; local main/alternate branches converge at their own site.
- Shortest physical A-hold to B-hold rotation crosses A rear, A rotation, CT A,
  CT B and B rear: {rear:.0f} HU. The CT-avoiding route through attacker territory
  is {outside:.0f} HU, only {outside-rear:.0f} HU longer. This is a small geometric
  margin, not proof that rear circulation is safe or competitively preferable.
- Sealing a primary or alternate aperture forces remaining paths through another
  legitimate entrance/rear sector; it does not expose a wall seam. Raw checks in validation.json.

| Ordered route | Provisional geometric length, HU |
|---|---:|
| T A main / alternate | {lengths['T-A-main']:.0f} / {lengths['T-A-alt']:.0f} |
| T B main / alternate | {lengths['T-B-main']:.0f} / {lengths['T-B-alt']:.0f} |
| CT A / B deployment | {lengths['CT-A-deploy']:.0f} / {lengths['CT-B-deploy']:.0f} |
| CT A / B recovery | {lengths['CT-A-recover']:.0f} / {lengths['CT-B-recover']:.0f} |

No conversion to seconds or calibrated timing claim. In particular CT A deployment
is longer than the T A main path; P04's intended early defensive assignment timing
is **unverified and potentially incompatible** with these proportions. All intended
strategic timing ranges remain unchanged; they have not been declared satisfied.
No classical Mid is added: forecourt and lobby only pressure their respective
objective, and the rear multi-site circulation remains CT deployment architecture.

## Recovery assumption history and current allocations

Original candidate-1 area budgets: A fallback 80–110, A regroup 80–110,
B fallback 110–140, B regroup 75–105 plan square units. Original A recover
distance 40–75 plan units. Those originals, their unapproved replacement proposals,
first current versus archived measurements and first validation failures remain
separate in budget-history.json; candidate 001 is not retrospectively passed.

| Allocation | Frozen first current area | Second current area | Why this allocation |
|---|---:|---:|---|
| A fallback | 72 | 80 | Arcade receiving pocket beside north site edge |
| A regroup | 31.5 | 72 | Shared arcade preparation west of receiving pocket |
| B fallback | 64 | 64 | East receiving court adjacent to rear entry |
| B regroup | 54 | 72 | Entry-facing preparation in the same receiving court |

Areas are plan square units, gross = actual unobstructed allocated area in candidate 2.
Multiply by 1024 for HU squared. They reserve parts of existing architectural
spaces; they do not carve out rooms or certify safe player capacity. Candidate 2
does not inherit the prototype minima as universal requirements. Its A recovery
length is {lengths['CT-A-recover']/32:.2f} plan units, explicitly below the old
40–75 interval; that historical assumption has not been relaxed to manufacture a pass.
No new numeric travel requirement was imposed, and no distance-padding corridor added.

## Encounter overlay and remaining weaknesses

Orange: primary approach; pink: local alternate; cyan: defender positions and
deployment; blue: rear rotation; red: longest sampled standing ray from each
marked defender (5° sampling against actual full-height architectural occlusion).
The plant regions and pale 48 HU cover distinguish low protection from 160 HU
walls/building wings. Standing rays see over low cover; crouched visibility is
compiled separately. The encounter labels are design hypotheses, not kill data.

Remaining weaknesses: long open rays, sparse objective cover, a lengthy B receiving
gallery, CT A arrival uncertainty, and a small rear-versus-attacker rotation margin.
Fallback/retake safety, utility, information gains and actual first-contact timing
remain unverified. The broad open approach spaces may still feel underdeveloped;
visual acceptance is pending. No claim of calibrated balance or normal gameplay.

The selected implementation regression suite passed 85 tests, including a deliberately
obstructed B aperture detected as a failure. This tests implementation behavior;
the candidate's limited geometric checks report no violations, but full strategy
preservation and human acceptance are not established. Stop here for review.
'''
    (OUT/'review.md').write_text(report,encoding='utf-8')
    assert all(hashlib.sha256((FIRST/n).read_bytes()).hexdigest()==h for n,h in frozen.items()),'First candidate changed'
    policy_path=ROOT/'generation-policy.json';policy=json.loads(policy_path.read_text())
    policy.update(stage_3_experiment_status='second_single_authored_composition_pending_visual_review',stage_4_inspection_status='deferred_by_user',
        stage_3_single_candidate_authorization={'candidate':'002','consumed':True,'scope':'One additional composition only; no batch or engine geometry.'},
        stage_3_review='output/p04-playable-composition-002/review.md',stage_3_batch_authorized=False,stage_4_authorized=False)
    policy_path.write_text(json.dumps(policy,indent=2)+'\n')
    print(json.dumps({'violations':r['violations'],'routes':len(r['strategic_routes']),'sectors':r['entry_sectors'],'rotation':r['defender_rotation'],'allocations':r['allocations']},indent=2))

if __name__=='__main__':run()
