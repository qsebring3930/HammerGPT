"""Exactly two Codex-authored Stage 3 compositions; no automatic architect.

001/002 are read-only. All common-scale re-renders go to a separate review folder.
Only planar composition data are emitted: no engine geometry or VMAP.
"""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, LineString, mapping
from playable_composition import compile_composition, DerivedNavigation
from p04_second_composition import validate as physical_checks, rect, font, STRATEGY, ROOT
from p04_space_mass_demo import route_nav
from semantic_pipeline import digest

REVIEW=ROOT/'output/p04-four-composition-review'

class Authoring:
    def __init__(self,number,name):
        first=json.loads((ROOT/'output/p04-playable-composition-001/composition.json').read_text())
        self.p=dict(schema='playable-space-mass-openings-v1',candidate=f'P04-composition-{number:03d}-authored',
            number=number,name=name,authorship='Codex-authored coordinates and architecture; no procedural selection.',
            plan_sha256=digest(json.loads(STRATEGY.read_text())),engine_scale=first['engine_scale'],
            boundary_thickness=.8,envelope=rect(0,0,140,130),elevation={'all_walkable_space':0},
            spaces=[],openings=[],internal_masses=[],allocations=[],annotations={},
            site_spaces={'A':'A_court','B':'B_court'},objective_zones={},defender_positions={},
            historical_budget_source='Original assumptions and proposed revisions remain in frozen 001/002; current allocations are separate design annotations, not universal constraints.',
            references=[dict(source='output/annotations/dust2-boundaries-v4/overview.png',use='A narrower threshold before a wider encounter; deployment frontage should not look directly through the encounter.'),
                dict(source='output/annotations/cache-reviewed-v1/overview.png',use='Local entrances on different objective faces; distinct clearing sectors and receiving pockets.'),
                dict(source='output/annotations/train-reviewed-v1/overview.png',use='Attached building wings divide objective combat space; rear assignments fit between building faces.'),
                dict(source='output/annotations/cobblestone-reviewed-v1/overview.png',use='B staging, territory investment and execute threshold are architectural phases.')],
            reference_limit='Qualitative NAV references. Proportions and heights authored at the unchanged provisional scale, not measured from reference geometry.')
    def space(self,i,b,purpose):self.p['spaces'].append(dict(id=i,boundary=b,description=purpose))
    def door(self,i,a,b,line,purpose):self.p['openings'].append(dict(id=i,spaces=[a,b],aperture=line,purpose=purpose))
    def mass(self,i,b,height,purpose):self.p['internal_masses'].append(dict(id=i,boundary=b,height_source_units=height,height_class='low_cover' if height==48 else 'full_height',purpose=purpose))
    def points(self,pts):self.p['annotations']={k:dict(point=v) for k,v in pts.items()}
    def allocation(self,i,b,purpose):self.p['allocations'].append(dict(id=i,boundary=b,purpose=purpose))

def build003():
    a=Authoring(3,'Offset sites with inset rear receiving complex')
    a.space('T_deployment',[[32,8],[68,8],[68,22],[48,22],[48,18],[32,18]],'Loading deployment along building frontage: west A or east B commitment.')
    a.space('A_arrival',[[12,12],[32,12],[32,30],[22,30],[22,26],[12,26]],'A arrival lane and sheltered unloading recess, not a continuous long service route.')
    a.space('A_forecourt',rect(12,30,46,43),'First A encounter along storefront; right main entry or short left gallery.')
    a.space('A_gallery',rect(12,43,20,60),'Narrow local gallery ending at west site threshold; no rear exit.')
    a.space('A_court',[[20,43],[46,43],[46,61],[42,61],[42,70],[20,70]],'A court has an attached frontage, plant bay and north receiving edge.')
    a.space('A_receiving',rect(24,70,48,82),'Local receiving arcade accommodates fallback/regather within CT building frontage.')
    a.space('CT_deployment',rect(48,72,68,88),'Inset rear deployment: west A receiving versus north B rear assignment. No attacker lobby access.')
    a.space('B_rear_link',rect(58,88,68,108),'Short rear building aisle to B receiving, separated from execute territory by exterior solid.')
    a.space('B_receiving',rect(68,96,108,108),'B rear loading frontage; narrow circulation with local preparation at the site edge.')
    a.space('B_arrival',[[68,12],[80,12],[80,26],[86,26],[86,38],[74,38],[74,24],[68,24]],'Street arrival passes the building corner into B lobby; west wall separates A commitment.')
    a.space('B_lobby',rect(78,38,104,60),'B first encounter with receiving frontage occluding the direct execute view.')
    a.space('B_workshop',rect(78,60,104,70),'Investment strip turns back to western execute threshold, distinct from east side approach.')
    a.space('B_gallery',[[104,55],[116,55],[116,72],[112,72],[112,87],[104,87]],'Alternate local unloading lane ends at east site threshold; no defender-circulation bypass.')
    a.space('B_court',[[78,70],[104,70],[104,96],[90,96],[90,92],[78,92]],'B workshop yard: southwest execute, east alternate, north receiving, different entry-clearing sectors.')
    a.door('T_A','T_deployment','A_arrival',[[32,12],[32,17]],'West commitment at deployment')
    a.door('A_staging','A_arrival','A_forecourt',[[23,30],[28,30]],'A staging threshold')
    a.door('A_main','A_forecourt','A_court',[[35,43],[40,43]],'Main south entry')
    a.door('A_gallery_access','A_forecourt','A_gallery',[[13,43],[18,43]],'Local alternate frontage')
    a.door('A_side','A_gallery','A_court',[[20,53],[20,58]],'West clearing sector')
    a.door('A_rear','A_court','A_receiving',[[32,70],[37,70]],'North defender/retake entry')
    a.door('CT_A','A_receiving','CT_deployment',[[48,75],[48,80]],'A receiving assignment')
    a.door('CT_B','CT_deployment','B_rear_link',[[60,88],[65,88]],'B rear assignment')
    a.door('B_rotation','B_rear_link','B_receiving',[[68,100],[68,105]],'Turn into B receiving')
    a.door('B_rear','B_receiving','B_court',[[95,96],[100,96]],'North defender/retake entry')
    a.door('T_B','T_deployment','B_arrival',[[68,13],[68,19]],'East commitment at deployment')
    a.door('B_staging','B_arrival','B_lobby',[[80,38],[85,38]],'B arrival/lobby threshold')
    a.door('B_territory_access','B_lobby','B_workshop',[[90,60],[95,60]],'Workshop investment before primary execute')
    a.door('B_main','B_workshop','B_court',[[79,70],[84,70]],'Southwest execute entry')
    a.door('B_gallery_access','B_lobby','B_gallery',[[104,55],[104,59]],'Local alternate commitment')
    a.door('B_side','B_gallery','B_court',[[104,78],[104,83]],'East entry sector')
    a.mass('A_frontage',rect(38,51,46,57),160,'Attached storefront divides south-entry clear into near corner and plant bay.')
    a.mass('A_staging_frontage',rect(30,30,37,35),160,'Attached storefront separates staging threshold from the main execute doorway.')
    a.mass('B_lobby_frontage',rect(78,45,89,50),160,'Workshop facade blocks arrival-to-execute line and leaves an encounter lane to the right.')
    a.mass('B_site_workshop',rect(78,79,88,85),160,'Building face separates primary clearing from the deep plant/rear receiving sector.')
    a.mass('CT_receiving_corner',rect(48,82,54,88),160,'A receiving frontage narrows into the CT deployment hall; assignments diverge around this building corner.')
    a.mass('B_rear_storehouse',rect(74,103,88,108),160,'Storehouse frontage limits the broad rear strip to receiving circulation plus a site-facing regather bay.')
    a.mass('A_plant_cover',rect(27,64,30,66),48,'Low plant cover; not standing-eye occlusion.')
    a.mass('B_plant_cover',rect(94,88,97,90),48,'Plant bay cover with separate east and north clearing angles.')
    a.points({'T':[56,14],'CT':[57,80],'A':[32,65],'B':[99,87],
        'A_prep':[25,32],'A_fight':[17,37],'A_entry':[38,47],'A_side':[23,56],
        'A_hold':[32,63],'A_rear':[40,77],'A_retake':[33,77],
        'B_prep':[80,33],'B_fight':[99,56],'B_territory':[84,65],'B_entry':[82,74],
        'B_side':[101,81],'B_hold':[96,87],'B_rear':[99,102],'B_retake':[94,102]})
    a.p['objective_zones']={'A':rect(25,61,36,68),'B':rect(92,83,102,92)}
    a.p['defender_positions']={'A_court':[32,63],'A_gallery':[16,51],'B_lobby_edge':[89,64],'B_plant_bay':[96,87]}
    a.allocation('A_fallback',rect(37,73,45,80),'56 plan² receiving pocket beside CT assignment')
    a.allocation('A_regather',rect(27,73,35,80),'56 plan² north-facing preparation within receiving arcade')
    a.allocation('B_fallback',rect(100,99,106,105),'36 plan² receiving pocket beside rear doorway')
    a.allocation('B_regather',rect(91,99,98,106),'49 plan² entry-facing preparation in rear frontage')
    return a.p

def build004():
    a=Authoring(4,'Stacked objectives along a compact rear defender hall')
    a.space('T_deployment',[[12,65],[30,65],[30,83],[23,83],[23,88],[12,88]],'Warehouse deployment: east immediate A commitment or south loading lane toward B.')
    a.space('A_forecourt',rect(30,68,60,86),'A encounter along warehouse frontage; south execute mouth versus northern local passage.')
    a.space('A_gallery_link',[[40,86],[51,86],[51,98],[60,98],[60,108],[40,108]],'Rear of attacker warehouse opens to north site gallery; terminates before defender receiving.')
    a.space('A_gallery',rect(60,98,86,108),'North alternate entry frontage, not a rotation to B or CT.')
    a.space('A_court',rect(60,72,86,98),'A objective courtyard divided by warehouse wing; main west entry, north alternate, east receiving.')
    a.space('A_receiving',rect(86,72,100,100),'Compact east receiving arcade with local fallback and preparation adjacent to CT hall.')
    a.space('CT_deployment',[[100,51],[117,51],[117,80],[110,80],[110,84],[100,84]],'Rear defender hall: north A versus south B receiving; no long outer perimeter circuit.')
    a.space('B_receiving',[[78,48],[100,48],[100,60],[84,60],[84,56],[78,56]],'B north receiving bay connects directly to rear hall; fallback/regather integrated into the building edge.')
    a.space('B_arrival',rect(12,43,32,65),'South attacker street; building frontage compresses approach before first B encounter.')
    a.space('B_lobby',[[12,25],[48,25],[48,43],[24,43],[24,39],[12,39]],'B loading lobby: east workshop investment or south loading-door alternate.')
    a.space('B_workshop',rect(48,25,68,48),'Local alternate through workshop: northwestern entry reveals a different clearing sector from the primary south execute.')
    a.space('B_gallery_link',rect(30,12,48,25),'Primary B loading commitment: acquire sheltered loading territory before turning toward south site entrance.')
    a.space('B_gallery',rect(48,12,79,22),'Primary B execute frontage from invested loading territory; no CT circulation exit.')
    a.space('B_court',rect(68,22,94,48),'B loading yard: south primary entry, west workshop alternative and north defender receiving.')
    a.door('T_A','T_deployment','A_forecourt',[[30,79],[30,83]],'Recessed east A assignment above the primary site sightline')
    a.door('A_main','A_forecourt','A_court',[[60,72],[60,77]],'West main entrance below warehouse wing')
    a.door('A_gallery_access','A_forecourt','A_gallery_link',[[43,86],[48,86]],'North local alternate investment')
    a.door('A_gallery_turn','A_gallery_link','A_gallery',[[60,100],[60,105]],'Clear warehouse corner before north frontage')
    a.door('A_side','A_gallery','A_court',[[61,98],[66,98]],'North entry sector')
    a.door('A_rear','A_court','A_receiving',[[86,88],[86,93]],'East opposite retake/receiving sector')
    a.door('CT_A','A_receiving','CT_deployment',[[100,74],[100,79]],'North rear assignment')
    a.door('CT_B','CT_deployment','B_receiving',[[100,53],[100,58]],'South rear assignment into north receiving bay')
    a.door('B_rear','B_receiving','B_court',[[83,48],[88,48]],'North opposite retake/receiving sector')
    a.door('T_B','T_deployment','B_arrival',[[18,65],[23,65]],'South B assignment')
    a.door('B_staging','B_arrival','B_lobby',[[25,43],[30,43]],'Sheltered arrival threshold')
    a.door('B_gallery_access','B_lobby','B_workshop',[[48,38],[48,43]],'Workshop local alternate commitment')
    a.door('B_side','B_workshop','B_court',[[68,42],[68,47]],'Western workshop alternate entry')
    a.door('B_territory_access','B_lobby','B_gallery_link',[[36,25],[41,25]],'Primary loading territory threshold')
    a.door('B_execute_turn','B_gallery_link','B_gallery',[[48,16],[48,21]],'Clear loading-bay turn before execute frontage')
    a.door('B_main','B_gallery','B_court',[[72,22],[77,22]],'Southern primary entry sector')
    a.mass('A_forecourt_warehouse',rect(50,78,60,86),160,'Attached warehouse separates main entrance from alternate decision; no cosmetic bend.')
    a.mass('A_site_wing',rect(60,82,69,88),160,'Warehouse wing creates separate north-entry and west-entry clearing sectors around plant bay.')
    a.mass('A_warehouse_back',rect(40,102,50,108),160,'Warehouse back face bounds the alternate frontage turn, leaving a local receiving-width passage.')
    a.mass('B_street_frontage',rect(12,43,23,50),160,'Arrival narrows beside attached building before the loading lobby; not an empty travel room.')
    a.mass('B_workshop_frontage',rect(48,25,56,35),160,'Attached machinery building places entrance and execute at different workshop edges.')
    a.mass('B_site_loading_bay',rect(68,36,79,41),160,'Attached loading bay separates primary entry from the south plant-entry sightline.')
    a.mass('A_plant_cover',rect(78,89,81,91),48,'Low plant protection, visible over from standing positions.')
    a.mass('B_plant_cover',rect(83,32,86,34),48,'Low plant protection, not a tall LOS blocker.')
    a.points({'T':[20,75],'CT':[108,67],'A':[80,87],'B':[87,30],
        'A_prep':[37,74],'A_fight':[44,82],'A_entry':[64,75],'A_side':[64,94],
        'A_hold':[77,87],'A_rear':[94,84],'A_retake':[94,91],
        'B_prep':[27,50],'B_fight':[42,30],'B_territory':[66,17],'B_entry':[74,25],
        'B_side':[72,44],'B_hold':[85,35],'B_rear':[93,55],'B_retake':[86,55]})
    a.p['objective_zones']={'A':rect(75,85,84,94),'B':rect(81,28,91,37)}
    a.p['defender_positions']={'A_plant_bay':[77,87],'A_near_entry':[72,78],'A_gallery_guard':[45,92],
        'B_workshop_threshold':[52,45],'B_plant_bay':[85,35]}
    a.allocation('A_fallback',rect(90,80,98,87),'56 plan² receiving area beside CT assignment')
    a.allocation('A_regather',rect(90,88,98,96),'64 plan² local east-entry preparation')
    a.allocation('B_fallback',rect(90,51,98,58),'56 plan² receiving beside CT hall assignment')
    a.allocation('B_regather',rect(81,51,89,55.5),'36 plan² preparation at north site threshold, clear of receiving-wall thickness')
    return a.p

def rays(c,positions):
    result=[]
    for name,start in positions.items():
        best=None
        for angle in range(0,360,5):
            v=np.array([math.cos(math.radians(angle)),math.sin(math.radians(angle))]);lo=0.;hi=180.
            for _ in range(18):
                mid=(lo+hi)/2
                if c['visibility_standing'].covers(LineString([start,np.array(start)+v*mid])):lo=mid
                else:hi=mid
            if best is None or lo>best['length_plan_units']:
                best=dict(defender=name,start=start,end=list(np.array(start)+v*lo),length_plan_units=lo,length_HU=lo*32)
        result.append(best)
    return result

def validate(p,c,plan):
    # Reuse the existing physical/route checks; replace candidate-002's authored
    # ray origins with this candidate's positions. No frozen result is rewritten.
    r=physical_checks(p,c,plan)
    r['defender_positions']=p['defender_positions'];r['longest_sampled_standing_rays']=rays(c,p['defender_positions'])
    nav=DerivedNavigation(c);a={k:x['point'] for k,x in p['annotations'].items()}
    arrival=[];warnings=[]
    for s in ('A','B'):
        t=route_nav(nav,[a[x] for x in ['T',s+'_prep',s+'_fight']])
        ct=r['strategic_routes']['CT-'+s+'-contest']['path']
        deploy=r['strategic_routes']['CT-'+s+'-deploy']['path'];entry=r['strategic_routes']['T-'+s+'-main']['path']
        row=dict(site=s,T_to_contact_HU=t['length']*32 if t else None,CT_ordered_to_same_contact_HU=ct['length']*32 if ct else None,
            CT_to_hold_HU=deploy['length']*32 if deploy else None,T_to_main_entry_HU=entry['length']*32 if entry else None)
        row['same_contact_distance_conflict']=bool(t and ct and ct['length']>=t['length'])
        if row['same_contact_distance_conflict']:warnings.append(s+': CT ordered route to the same encounter is not shorter than T. Early CT contest timing is unsupported by these distances.')
        arrival.append(row)
    rot=r['defender_rotation'];rear=rot['shortest_path'];outside=rot['CT_avoiding_path']
    margin=(outside['length']-rear['length'])*32 if outside and rear else None
    rot['rear_advantage_HU']=margin
    rot['weak_geometric_margin']=margin is not None and margin<512
    if rot['weak_geometric_margin']:warnings.append('Rear rotation has less than 512 HU geometric advantage over the attacker-territory route; diagnostic threshold only, not a P04 requirement.')
    contact_sightlines=[]
    for s in ('A','B'):
        for name,start in p['defender_positions'].items():
            if not name.startswith(s+'_'):continue
            end=a[s+'_fight'];contact_sightlines.append(dict(site=s,defender=name,standing_line_to_contact=c['visibility_standing'].covers(LineString([start,end])),
                distance_HU=LineString([start,end]).length*32))
    for row in r['allocations']:
        if abs(row['gross_plan_area']-row['current_walkable_plan_area'])>1e-6:
            warnings.append(row['id']+': allocation partly obstructed; reported current area differs from gross.')
    spawn_sightlines=[dict(defender=name,standing_line_to_T_spawn_marker=c['visibility_standing'].covers(LineString([start,a['T']]))) for name,start in p['defender_positions'].items()]
    if any(x['standing_line_to_T_spawn_marker'] for x in spawn_sightlines):warnings.append('Declared defender position has standing visibility to T spawn marker; deployment exposure needs review.')
    r.update(arrival_distance_checks=arrival,design_warnings=warnings,contact_sightline_checks=contact_sightlines,spawn_marker_sightline_checks=spawn_sightlines,
        walkable_components=len(c['walkable'].geoms) if hasattr(c['walkable'],'geoms') else 1,
        arrival_measurement='Ordered paths to the same annotated encounter; no calibrated seconds, running speed or first-contact timing. CT includes defensive hold assignment before contest.',
        acceptance='Geometric check results and warnings only; awaiting visual review, timing/utility/retake safety unverified.')
    return r

def render(p,c,r,number,bounds,overlay=False,pixels_per_plan_unit=10):
    im=Image.new('RGB',(1800,1650),'#101923');d=ImageDraw.Draw(im)
    scale=float(pixels_per_plan_unit);x0,y0,x1,y1=bounds;ox=100+(1600-(x1-x0)*scale)/2;oy=1480
    def xy(v):return (ox+(v[0]-x0)*scale,oy-(v[1]-y0)*scale)
    def poly(g,fill):
        if g.is_empty:return
        if hasattr(g,'geoms'):
            for part in g.geoms:poly(part,fill)
        elif isinstance(g,Polygon):
            d.polygon([xy(v) for v in g.exterior.coords],fill=fill)
            for ring in g.interiors:d.polygon([xy(v) for v in ring.coords],fill='#101923')
    d.text((75,25),p.get('display_title',f'P04 / {number:03d}'+(' — frozen' if number<3 else ' — Codex-authored')),font=font(34),fill='white')
    d.text((75,72),p.get('name','Original authored composition' if number==1 else 'Orthogonal sites with perimeter rear circulation'),font=font(25),fill='#ccd8e0')
    d.text((75,113),f'COMMON SCALE: {scale:g} pixels / plan unit = 32 HU · Stage 4 paused',font=font(22),fill='#9fb5c6')
    poly(c['walkable'],'#718b9c')
    sites=p.get('site_spaces',{'A':'west_yard','B':'east_assembly'})
    for i in sites.values():poly(c['spaces'][i].intersection(c['walkable']),'#9bb1bc')
    for m in p['internal_masses']:poly(Polygon(m['boundary']),'#d1cbb3' if m.get('height_source_units',160)==48 else '#263544')
    for o in p['openings']:d.line([xy(v) for v in o['aperture']],fill='#d4e9e8',width=4)
    for s,b in p['objective_zones'].items():
        pts=[xy(v) for v in b];d.line(pts+[pts[0]],fill='#eed28c',width=3)
        at=xy(p['annotations'][s]['point']);d.text((at[0]-13,at[1]-18),s,font=font(37),fill='#fff0ad',stroke_width=1,stroke_fill='#314250')
    for s in ('T','CT'):
        at=xy(p['annotations'][s]['point']);d.text((at[0]-34,at[1]-12),s+' spawn',font=font(22),fill='white',stroke_width=2,stroke_fill='#253847')
    if overlay:
        for rid,col in [('T-A-main','#efbd6c'),('T-A-alt','#d99ba5'),('T-B-main','#efbd6c'),('T-B-alt','#d99ba5'),('CT-A-deploy','#63d3ec'),('CT-B-deploy','#63d3ec'),('CT-A-switch','#83acec')]:
            path=r['strategic_routes'][rid]['path']
            if path:d.line([xy(v) for v in path['points']],fill=col,width=4)
        for ray in r['longest_sampled_standing_rays']:d.line([xy(ray['start']),xy(ray['end'])],fill='#fb7276',width=2)
        for k,label in {'A_fight':'A encounter','A_retake':'A regroup','B_fight':'B encounter','B_territory':'B investment','B_retake':'B regroup'}.items():
            at=xy(p['annotations'][k]['point']);d.ellipse((at[0]-4,at[1]-4,at[0]+4,at[1]+4),fill='#ffe29b');d.text((at[0]+5,at[1]-23),label,font=font(20),fill='white',stroke_width=2,stroke_fill='#152332')
        for start in r['defender_positions'].values():
            at=xy(start);d.rectangle((at[0]-5,at[1]-5,at[0]+5,at[1]+5),fill='#70e0f5')
    d.line((80,1540,80+16*scale,1540),fill='white',width=4);d.text((80,1560),'512 HU',font=font(22),fill='white')
    d.rectangle((330,1535,330+scale,1535+scale),fill='#fff0ad');d.text((350,1530),'32 HU player',font=font(22),fill='white')
    d.text((600,1525),'Light: objective floor · blue-gray: circulation · dark: full-height · tan: 48 HU cover',font=font(21),fill='#c9d7df')
    d.text((600,1565),'Orange primary · pink alternate · blue CT rotation · red sampled rays' if overlay else 'Outlined plant regions · pale openings · coordinates and architecture authored',font=font(21),fill='#c9d7df')
    return im

def frozen_hashes():
    result={}
    for number in (1,2):
        folder=ROOT/f'output/p04-playable-composition-{number:03d}'
        for path in folder.rglob('*'):
            if path.is_file():result[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def write_reviews(programs,results):
    measurements=[]
    for p,r in zip(programs[2:],results[2:]):
        folder=ROOT/f"output/p04-playable-composition-{p['number']:03d}"
        rows=[]
        for x in r['arrival_distance_checks']:
            rows.append(f"| {x['site']} | {x['T_to_contact_HU']:.0f} | {x['CT_ordered_to_same_contact_HU']:.0f} | {x['CT_to_hold_HU']:.0f} | {x['T_to_main_entry_HU']:.0f} |")
        rot=r['defender_rotation'];main=rot['shortest_path']['length']*32;outside=rot['CT_avoiding_path']['length']*32
        allocations='\n'.join(f"- {x['id']}: {x['current_walkable_plan_area']:g} plan² actual, {x['gross_plan_area']:g} gross. {x['purpose']}." for x in r['allocations'])
        contacts='\n'.join(f"- {x['site']}: {x['defender']} to encounter marker: {'visible' if x['standing_line_to_contact'] else 'occluded'} at standing eye." for x in r['contact_sightline_checks'])
        warnings='\n'.join('- '+x for x in r['design_warnings'])
        weaknesses=('B receiving still includes a straight rear frontage; B is farther from CT than A. The alternate unload bay remains relatively open, and the B near-entry yard needs visual judgement.' if p['number']==3 else 'A has rapid attacker pressure and a comparatively lengthy local northern alternative. The compact CT hall may make defender rotations too efficient; short geometry does not establish safe or balanced rotations.')
        architecture=('Loading deployment diverges west into A frontage and east into B arrival. A clears a near storefront corner before the plant bay, with a west gallery alternative. B clears the lobby facade and acquires workshop frontage before its primary execute; its east unload-bay alternative reaches a different face. The inset CT complex has local receiving at A and an upper building aisle to B.' if p['number']==3 else 'Deployment diverges east into immediate A pressure and south into B loading. A clears below an attached warehouse wing from its west entrance; north frontage is a local alternative. B invests in sheltered loading territory and enters from the south; the workshop alternative enters from the west. A receives defenders from the east, B from the north, both directly off a compact rear hall.')
        report=f'''# P04 composition {p['number']:03d}: {p['name']}

Codex-authored architecture. No procedural generator selected the spatial arrangement.
Reusable code only compiles physical boundaries/masses/openings, derives navigation,
measures geometry and renders the plan. Stage 4 and engine geometry remain paused.
Unchanged P04 strategy hash: `{p['plan_sha256']}`. Scale: 32 HU/plan unit;
32 by 32 HU provisional player, 25.6 HU boundary thickness, 160 HU full height,
48 HU low cover. Runtime collision dimensions, eye heights and travel times are uncalibrated.

## Physical checks and semantic limits

- 19/19 ordered routes connected in raw walkable space and after player-footprint erosion.
- Single connected walkable component. 16/16 declared openings have nominal width
  equal to actual width, checked across boundary depth. Widths: {min(o['actual_clear_HU'] for o in r['openings']):.0f}–{max(o['actual_clear_HU'] for o in r['openings']):.0f} HU.
- No sampled unintended architectural openings. Blocking both objective courts
  removes all T-to-CT paths: no site-free attacker bypass.
- Local alternative routes cross different site openings. Their directed inward
  entry sectors differ by 90° from primary; rear recovery ingress opposes primary
  by 180°. Boundary normals measure approach sector, not door hinge or final heading.
- Primary attacker commitments share no opening. Roles annotate architectural spaces;
  there is no classical Mid. CT site switching passes through rear deployment.
- Shortest physical hold-to-hold rear rotation: {main:.0f} HU; CT-avoiding route
  through attacker territory: {outside:.0f} HU; rear advantage: {outside-main:.0f} HU.
  The rear route is topologically available, not proven safe or correctly timed.

## Arrival-distance warning — compare like destinations

| Site | T ordered to encounter | CT ordered to same encounter | CT ordered to hold | T ordered to main entry |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

All numbers HU. CT's encounter route includes rear receiving and initial holding
assignment before advancing to the encounter waypoint. Its longer length fails to
support the literal early-CT-contest intention in P04; this warning is not hidden.
CT-to-hold and T-to-entry are different destinations, shown separately rather than
silently substituting them for the same-encounter comparison. A defender may project
fire into an encounter without walking to its waypoint. Static visibility below
supports only that possibility, not first-contact timing. No conversion to seconds.

{warnings}

## Encounter structure and reference-informed architecture

{architecture}

Dust2's threshold-to-forecourt relation informs staging; Cache's local entry faces
inform objective clearing sectors; Train's building-attached site divisions inform
the full-height wings; Cobblestone's phased approaches inform B investment and execute.
Exact inspected reference paths are recorded in composition.json. These are qualitative
decisions, not extracted proportions or calibrated reference timings.

Holding positions and plant regions are authored. Marked tan cover is 48 HU high
and does not occlude standing rays. Building frontage and boundary walls are full-height.
The overlay shows primary/secondary approaches, CT deployment and rotation, authored
encounter markers, defender positions, and longest sampled standing rays (5° sampling).
The rays are exact line checks through the planar opaque representation, not an
exhaustive 3D visibility or maximum-sightline analysis.

{contacts}

No marked defender sees the exact T spawn marker under these static standing assumptions.
That does not establish concealment of the entire deployment area or moving players.

## Recovery allocations and remaining weaknesses

{allocations}

These allocate parts of receiving architecture, not extra rooms. Plan² × 1024 = HU².
They reflect the actual local receiving and entry-facing spaces, not imported minima.
Original 001 budgets, unapproved revisions and archived failures remain unchanged
in 001/002, with preservation hashes in the comparison folder. No historical failure
is cleared by the new values, and no detour was added to satisfy a distance budget.

{weaknesses}
Utility, defender control, meaningful retreat, retake viability and first-contact
timing remain unverified. Geometric checks have no detected violations; design
warnings remain. Implementation tests check computation and failure reporting,
not candidate quality or acceptance. Stop for visual review.
'''
        (folder/'review.md').write_text(report,encoding='utf-8')
        measurements.append(f"| {p['number']:03d} | 19/19 | 16/16 | None detected | {main:.0f} | {outside:.0f} | {outside-main:.0f} |")
    comparison=f'''# Four authored P04 compositions — same-scale comparison

Exactly two additional candidates (003 and 004) were composed in this round.
001 and 002 are byte-preserved: frozen-001-002.json hashes every existing file in
their output directories. Their same-scale images here are new re-renders from
unchanged programs; their original files and results were not updated or passed.

All four use unchanged P04 and provisional 32 HU/plan unit. Every comparison panel
uses the same 10 pixels/plan unit, same orientation, and common world bounds.
No fit-to-frame rescaling, mirroring or rotation was used for the comparison.
The 512 HU bars and 32 HU player markers are identical in every panel.

| Candidate | Spatial strengths | Remaining weaknesses |
|---|---|---|
| 001 frozen | More developed forecourts, local clearing spaces, receiving elbows and differentiated objective architecture | Two chains around a central compound; historical recovery assumptions remain unresolved |
| 002 frozen | Different site axes and deployment arrangement | Broad empty spaces, long perimeter rear circulation, narrow rotation-distance advantage and late-A-distance concern |
| 003 new | Staggered site depths, inset CT complex, frontage-based clearing, A west gallery versus B east unload bay | Long B rear frontage, asymmetric CT deployment distances, both same-encounter arrival warnings |
| 004 new | West A pressure versus south B territory investment; different primary axes; compact east/north receiving off rear hall | A pressure is very immediate; northern A alternate may cost too much; rear hall could favour fast defender rotations; arrival warnings |

003 is not a shifted 001: B lies substantially deeper, CT circulation is inset,
and rear receiving is organized around a building aisle. 004 is not a rotated 003:
A's primary ingress is eastward while B's is northward; B's rear access lies north
of its site, and the CT hall serves east A receiving and north B receiving directly.
Staging/execute arrangement and local alternate commitments differ architecturally.
These are manually chosen arrangements, not automatic-generation evidence.

## New candidate check results

| Candidate | Routes with player clearance | Nominal = actual openings | Site-free T-to-CT bypass | Rear rotation HU | CT-avoiding rotation HU | Rear advantage HU |
|---|---:|---:|---|---:|---:|---:|
{chr(10).join(measurements)}

Both candidates have one connected walkable component, no detected unintended
boundary openings, distinct primary/alternate observed entry sectors, and
opposite-side rear retake ingress. All are geometric checks, not timing/balance proof.

Both candidates retain warnings: CT's ordered route to the same encounter waypoint
is longer than T's. CT-to-hold versus T-to-site-entry is reported separately in
each review. Static defender visibility into some encounter positions shows why
reaching the waypoint is not the same as contesting it; it does not resolve timing.
Neither new layout has 002's tiny geometric rear-rotation margin, but 003's B
receiving remains long and 004's short shared rear hall may grant strong CT rotations.
No seconds, calibrated first-contact result or balance claim is supplied.

## Architectural lessons and scope

Carryovers from 001: building-attached full-height wings, local entry-clearing
sectors, staging separated from execute, low cover distinguished from architecture,
and recovery annotations inside receiving space. Approach changes have these
purposes, rather than decorative zigzags or silhouette-only cover changes.
New allocations are reported with gross and actual area; original 001 and 002
history remains untouched. The new candidates are not measured against those
prototype-authored assumptions as universal requirements.

Architecture, coordinates, openings, dimensions, role placement and cover were
authored by Codex. The Authoring helper serializes those decisions; it is not a
procedural architect. Existing reusable code compiles, navigates, checks and renders.
Four authored comparisons do not satisfy the automatic generation/diversity milestone.

Stage 4, engine geometry and graybox remain paused. No further candidates are
authorized by this round. Stop after 003/004 for review.
'''
    (REVIEW/'review.md').write_text(comparison,encoding='utf-8')

def run():
    REVIEW.mkdir(parents=True,exist_ok=True)
    freeze=REVIEW/'frozen-001-002.json';frozen=json.loads(freeze.read_text()) if freeze.exists() else frozen_hashes()
    assert frozen_hashes()==frozen,'Frozen 001/002 changed'
    freeze.write_text(json.dumps(frozen,indent=2))
    plan=json.loads(STRATEGY.read_text());programs=[json.loads((ROOT/f'output/p04-playable-composition-{i:03d}/composition.json').read_text()) for i in (1,2)]+[build003(),build004()]
    compiled=[compile_composition(p) for p in programs]
    # Shared bounds and identical px/HU: no per-panel fit-to-frame rescaling.
    bounds=(0,0,max(c['envelope'].bounds[2] for c in compiled),max(c['envelope'].bounds[3] for c in compiled))
    results=[None,None];summary=[]
    for i in (2,3):
        p=programs[i];c=compiled[i];r=validate(p,c,plan);results.append(r)
        folder=ROOT/f'output/p04-playable-composition-{i+1:03d}';folder.mkdir(parents=True,exist_ok=True)
        for name,value in [('composition.json',p),('validation.json',r),('playable-space.geojson',dict(type='FeatureCollection',features=[dict(type='Feature',properties={'kind':k},geometry=mapping(c[k])) for k in ('walkable','solid','walls','fixtures')]))]:
            (folder/name).write_text(json.dumps(value,indent=2),encoding='utf-8')
        render(p,c,r,i+1,bounds).save(folder/'plan-clean.png');render(p,c,r,i+1,bounds,True).save(folder/'plan-encounters.png')
        summary.append(dict(candidate=i+1,violations=r['violations'],warnings=r['design_warnings'],arrivals=r['arrival_distance_checks'],rotation_advantage_HU=r['defender_rotation']['rear_advantage_HU'],allocations=r['allocations']))
    sheet=Image.new('RGB',(3600,3300),'#101923')
    for i,(p,c,r) in enumerate(zip(programs,compiled,results)):
        image=render(p,c,r,i+1,bounds);image.save(REVIEW/f'clean-{i+1:03d}-same-scale.png');sheet.paste(image,((i%2)*1800,(i//2)*1650))
    sheet.save(REVIEW/'all-four-clean-same-scale.png')
    encounters=Image.new('RGB',(3600,1650),'#101923')
    for i in (2,3):encounters.paste(render(programs[i],compiled[i],results[i],i+1,bounds,True),((i-2)*1800,0))
    encounters.save(REVIEW/'new-encounters-same-scale.png')
    write_reviews(programs,results)
    (REVIEW/'results.json').write_text(json.dumps(dict(authorship='All four authored; no automatic procedural architecture evidence.',strategy_sha256=digest(plan),scale_px_per_plan_unit=10,HU_per_plan_unit=32,common_bounds=bounds,new_candidates=summary),indent=2))
    assert frozen_hashes()==frozen,'Frozen 001/002 changed during generation'
    policy_path=ROOT/'generation-policy.json';policy=json.loads(policy_path.read_text())
    policy.update(stage_3_experiment_status='four_authored_compositions_pending_review',
        stage_3_comparison_authorization={'candidates':['003','004'],'consumed':True,'scope':'Exactly two further authored comparisons; no engine geometry.'},
        stage_3_review='output/p04-four-composition-review/review.md',stage_3_batch_authorized=False,stage_4_authorized=False,geometry_paused=True)
    policy_path.write_text(json.dumps(policy,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':run()
