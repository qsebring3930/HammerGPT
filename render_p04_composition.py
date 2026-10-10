"""Clear Stage 3 plan and review. No detailed floor generation."""
import json
import math

from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import Polygon


def render(program,compiled,report,path,annotated=True):
    width,height=1800,1600;im=Image.new('RGB',(width,height),'#0f1a26');d=ImageDraw.Draw(im)
    def f(s):return ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',s)
    x0,y0,x1,y1=compiled['envelope'].bounds;scale=min(1520/(x1-x0),1270/(y1-y0));ox=(width-(x1-x0)*scale)/2-x0*scale;oy=1430+y0*scale
    def xy(p):return (ox+p[0]*scale,oy-p[1]*scale)
    def geometry(g,fill):
        mask=Image.new('L',im.size,0);md=ImageDraw.Draw(mask)
        polys=list(g.geoms) if hasattr(g,'geoms') else [g]
        for poly in polys:
            if not isinstance(poly,Polygon):continue
            md.polygon([xy(v) for v in poly.exterior.coords],fill=255)
            for ring in poly.interiors:md.polygon([xy(v) for v in ring.coords],fill=0)
        im.paste(fill,(0,0),mask)
    d.text((70,28),'P04 / revised composition' + (' — validation overlay' if annotated else ' — clean plan'),font=f(40),fill='#ecf4fa')
    d.text((70,83),'Same strategy, one authored composition. Stage 4 and batch generation paused.',font=f(23),fill='#bacdda')
    geometry(compiled['envelope'],'#263440')
    for space in program['spaces']:
        color='#91a8b7' if space['id'] in ('west_yard','east_assembly') else '#718c9f' if space['id'] in ('south_court','west_forecourt','east_forecourt') else '#627e93'
        geometry(compiled['spaces'][space['id']],color)
    geometry(compiled['walls'],'#18242f');geometry(compiled['fixtures'],'#263440')
    for opening in program['openings']:
        pts=[xy(p) for p in opening['aperture']];d.line(pts,fill='#f4e4af',width=6)
    # Recovery allocations annotate existing circulation. Dashed edges do not
    # create an additional physical patch or alter the navigation footprint.
    for allocation in program['allocations'] if annotated else []:
        pts=[xy(p) for p in allocation['boundary']]+[xy(allocation['boundary'][0])]
        for a,b in zip(pts,pts[1:]):
            distance=math.dist(a,b);n=max(1,int(distance/12))
            for j in range(0,n,2):
                p=[a[k]+(b[k]-a[k])*j/n for k in (0,1)];q=[a[k]+(b[k]-a[k])*min(j+1,n)/n for k in (0,1)]
                d.line((tuple(p),tuple(q)),fill='#90d2d1',width=3)
    # Annotation labels are readable, with no circles for every strategic node.
    labels=[('T',(69,15),'T SPAWN'),('CT',(74,105),'CT SPAWN'),('A',(22,83),'A'),('B',(123,85),'B'),
        ('A_prep',(24,42),'A preparation'),('A_fight',(32,52),'A contest'),
        ('B_prep',(111,35),'B preparation'),('B_fight',(115,51),'B contest'),
        ('B_territory',(118,68),'Secure workshop'),('A_rear',(31,99),'fallback'),('A_retake',(19,92),'retake prep'),
        ('B_rear',(121,99),'fallback'),('B_retake',(108,92),'retake prep')]
    for pid,point,text in labels:
        if not annotated and pid not in ('T','CT','A','B'):continue
        pt=xy(point);font=f(55 if pid in ('A','B') else 23 if pid in ('T','CT') else 18)
        bb=d.textbbox((0,0),text,font=font);w=bb[2]-bb[0];h=bb[3]-bb[1]
        d.rounded_rectangle((pt[0]-w/2-5,pt[1]-h/2-5,pt[0]+w/2+5,pt[1]+h/2+7),radius=3,fill='#193043')
        d.text((pt[0]-w/2,pt[1]-h/2-4),text,font=font,fill='#eaf3f9')
    # The two openings of each site show their actual approach directions.
    arrows=[]
    if annotated:
        for row in report['entry_angle_checks']:
            if row['route'].startswith('T-'):
                ingress=row['main_ingress'];v=ingress['inward_approach_vector'];p=ingress['crossing']
                arrows.append(([p[i]-v[i]*4 for i in (0,1)],[p[i]+v[i]*4 for i in (0,1)],'#eabc58'))
            ingress=row['observed_ingress'];v=ingress['inward_approach_vector'];p=ingress['crossing']
            arrows.append(([p[i]-v[i]*4 for i in (0,1)],[p[i]+v[i]*4 for i in (0,1)],'#90d2d1' if row['route'].startswith('CT-') else '#c4a1e6'))
    for a,b,color in arrows:
        start,end=xy(a),xy(b);d.line((start,end),fill=color,width=5)
        v=[end[i]-start[i] for i in (0,1)];norm=math.hypot(*v);v=[q/norm for q in v];normal=[-v[1],v[0]]
        d.polygon([end,tuple(end[i]-v[i]*16+normal[i]*7 for i in (0,1)),tuple(end[i]-v[i]*16-normal[i]*7 for i in (0,1))],fill=color)
    center=xy((73,57));text='INACCESSIBLE\nCOMPOUND\n\nNo Mid connector'
    if annotated:
        d.multiline_text((center[0]-115,center[1]-90),text+'\n\nA recovery: 41.1 / 40–75\nRetake ingress: 180°\nBoth sites\n\nTiming / combat unverified',font=f(19),fill='#bed2df',align='center',spacing=6)
    # Only two measured defender deployment/rotation paths, as an optional
    # overlay. These lines do not define the physical movement connections.
    for rid in ('CT-A-recover','CT-B-recover') if annotated else ():
        route=report['derived_routes'].get(rid)
        if route:
            pts=[xy(p) for p in route['points']]
            d.line(pts,fill='#90d2d1',width=3)
    d.text((70,1491),'Light blue = walkable   Dark = solid/inaccessible   Cream = opening   All space is on one level',font=f(21),fill='#c8d9e5')
    if annotated:d.text((70,1526),'Gold = main ingress   Purple = side ingress   Teal = retake ingress/path and recovery allocations',font=f(20),fill='#a6bed0')
    d.text((70,1560),'Not accepted. Authored representation test; no automatic generation, diversity, VMAP or mesh claim.',font=f(18),fill='#90a9bc')
    im.save(path)


def write_report(p,c,r,out):
    lines=['# P04: one space-and-mass composition','',
        'This is one authored prototype of the replacement Stage 3 representation. It is not a trained or automatic spatial sampler. The original P04 strategy is unchanged. Stop here for visual review; no diversity batch or detailed floor generation is authorized.',
        '',f'![Clean P04 plan]({(out/"plan-clean.png").as_posix()})','',
        f'![Annotated P04 validation]({(out/"plan-annotated.png").as_posix()})','',
        '## What the 180-degree requirement means','',
        'The original P04 outcome supplies an entry_angle value but no geometric frame, aperture orientation or facing vector. The strategic comparison uses directed angles modulo 360, and the recovery relationship describes challenging an occupied entry from a recovery direction. This revision explicitly interprets the value as a directed site-ingress sector relative to primary attacker ingress. That interpretation remains subject to review; exact movement heading is a different quantity.',
        '', 'A side-entry zone is shared combat space inside the site, not an alias for a doorway. T approaches it through the side opening; CT reaches the same zone through rear site access. Ordered strategic places and outcomes are unchanged.',
        '', 'Measurement: find the actual navigation path crossing of the site boundary through an opening. Choose the unit normal pointing from outside into the site, using inside/outside polygon tests. With main ingress u and recovery ingress v, angle = acos(clamp(dot(u,v), -1, 1)). Do not take abs(dot): that would collapse opposite approaches to 0 degrees. Main vectors are (0,+1); rear recovery vectors are (0,-1), yielding 180 degrees. Opening axis orientation alone is identical for these horizontal openings, so cannot express opposition.',
        '', 'Actual shortest-path tangents are also recorded; they need not be exactly perpendicular to an opening. No 180-degree camera, facing or path-tangent claim is made.',
        '', 'The earlier 90-degree report compared the main and side doorway axes without checking where the recovery route actually entered the site. That was an incorrect audit, not reliable evidence of a retake violation. The archived composition is remeasured below using the same directed-ingress convention as this revision.',
        '', '## Constraint provenance','',
        '| Source | Constraints |','|---|---|',
        '| Original P04 strategy (unchanged hash) | Deployment and route-purpose rules; ordered strategic places; site systems and engagements; no Mid; local secondary entry sectors; defender transfer through CT deployment; independent recovery; ground endpoint levels; numeric entry angles; original seconds-based timing; B approach secured before execute preparation; conditional flank. |',
        '| Authored prototype | Every coordinate, architectural boundary, doorway width/location, solid mass, annotation location, abstract scale, 0.8 wall thickness, recovery area allocation and distance budget below. These are not extracted from P04 or learned reference data. |',
        '| Numerical implementation | 0.5 raster step, A* and exact segment-coverage checks. These are numerical settings, not gameplay-quality thresholds. |',
        '', '## Implementation tests versus candidate acceptance','',
        'The earlier 62 tests checked code behavior. Some deliberately asserted that a failed budget and an angle violation stayed visible. Passing those assertions means failure detection works; it does not mean a layout passes. The revision retains the old candidate as a failure-reporting regression case and separately tests the new measured constraints.',
        '', 'Measured constraint checks, original semantic verification, visual acceptance, automatic generation and diversity are separate statuses. The revised candidate is not visually accepted, original timing/gameplay remain unverified, and Stage 4 and batch generation are false. A passing implementation suite cannot change those statuses.',
        '', '## Architectural revision','',
        'A side engagement is now inside the front-side courtyard sector. The side doorway moves along the existing service boundary, the loading mass separates main-entry and side-sector fights, and the retake staging annotation shifts within its unchanged allocated rear area. The recovery crosses the existing yard to that occupied sector; no corridor, route waypoint or distance-inflating detour is added.',
        '', 'At B, the rear opening faces the occupied side sector. The assembly mass separates workshop-facing and side-facing combat, and the shared first-contact annotation sits at the actual approach split. The retake preparation annotation remains inside the same allocated rear area. Unrestricted navigation must still choose separate attack ingress openings; a named alternate is not counted as such when its shortest path enters through main.',
        '', '## Before / after','',
        '| Route | Before distance | After distance | Unchanged authored budget | Before directed ingress | After directed ingress |',
        '|---|---:|---:|---|---:|---:|',
        *[f"| {x['route']} | {x['before_distance']:.2f} | {x['after_distance']:.2f} | {x['unchanged_distance_budget']} | {x['before_directed_ingress']:.0f}° ({x['before_opening']}) | {x['after_directed_ingress']:.0f}° ({x['after_opening']}) |" for x in r['before_after']],
        '', 'The original incorrect axis audit reported 90 degrees for both retakes; it is retained in before/validation.json, not overwritten. The original P04 plan and every area/distance budget remain unchanged.',
        '', '| Route | Required ingress sector | Measured ingress sector | Actual path-tangent difference (diagnostic) |',
        '|---|---:|---:|---:|',
        *[f"| {x['route']} | {x['expected']}° | {x['measured']:.0f}° | {x['trajectory_delta']:.2f}° |" for x in r['entry_angle_checks']],
        '',f"Measured constraint violations remaining: {len(r['issues'])+len(r['violations'])}. This does not certify all original semantics or gameplay.",
        '',
        '## What is composed','',
        'A west courtyard and an east workshop/assembly sequence flank an inaccessible compound. Attacker preparation and first contests annotate the two forecourts. Defender access uses rear circulation through the CT deployment hall. Fallback and retake allocations share rear foyers already inside the footprint. Service circulation provides the separate side entries and recovery interfaces.',
        '', 'Walkable space is derived by subtracting solid boundaries and fixtures from the complete architectural footprint, then cutting the declared openings. Navigation is calculated on that result; no strategic edge, team or phase label creates a physical connection.',
        '', '## Preserved original P04 requirements','',*['- '+s for s in r['preserved']],
        '', '## Violations and unknowns','']
    for violation in r['violations']:lines.append('- **Violation:** '+violation['requirement']+' — '+violation['result'])
    for issue in r['issues']:lines.append('- **Physical-check failure:** '+str(issue))
    for text in r['unverified']:lines.append('- **Unverified:** '+text)
    lines+=['','## Explicit recovery area budgets','',
        '| Annotation | Allocated walkable area | Authored area budget | Result |','|---|---:|---|---|']
    for area in r['area_allocations']:lines.append(f"| {area['role']} | {area['walkable_area']:.1f} | {area['budget']} | {'within allocation' if area['preserved'] else 'VIOLATED'} |")
    lines+=['','## Explicit recovery travel budgets','',
        '| Movement | Measured distance | Authored distance budget | Result |','|---|---:|---|---|']
    for distance in r['distance_allocations']:lines.append(f"| {distance['route']} | {distance['travel_length']:.1f} | {distance['authored_budget']} | {'within allocation' if distance['preserved'] else 'VIOLATED'} |")
    lines+=['','These budgets are transparent program allocations for this composition in abstract units. They are not learned reference-map thresholds or seconds-based claims.',
        '', '## Complete-space navigation checks','',
        f"Unlisted opening samples: {len(r['opening_audit']['unintended_openings'])}.",
        '', 'Approaches deliberately share their prescribed first contest. Their post-contest branches use separate physical openings. Closing either site opening leaves the other entry accessible; the intervening boundary remains solid.',
        '', '| Site | Main post-contest branch | Side post-contest branch | Separate openings survive closure test | Entry separation |',
        '|---|---:|---:|---|---:|']
    for approach in r['approaches']:lines.append(f"| {approach['site']} | {approach['main_branch_length']:.1f} | {approach['side_branch_length']:.1f} | {approach['independent_openings']} | {approach['opening_entry_separation_degrees']}° |")
    rotation=r['rotation']
    lines+=['',f"Shortest A-hold→B-hold path: {rotation['shortest_length']:.1f}. Ordered path through CT annotation: {rotation['ordered_via_deployment_length']:.1f}. Longest initial CT assignment: {rotation['longest_initial_deployment']:.1f}.",
        f"Shortest path avoiding the entire CT deployment hall: {rotation['shortest_avoiding_CT_deployment']}. The default shortest switch intersects CT deployment: {rotation['passes_CT_deployment']}.",
        '', 'A shorter path through the *deployment hall* need not visit the exact spawn annotation. That corner cutting is measured rather than hidden. Frontal cross-site movement remains physically possible through attacker territory; it is compared against the rear switch instead of being blocked by phase labels.',
        '', '## Travel and clearance ledger','',
        'Every route retains its original duration contract alongside its measured travel length. B main additionally retains its explicit requirement to secure B_fight before final execute preparation. Clearance/combat/decision durations are null, not manufactured distances or invented delays. No original timing is silently reassigned to travel.',
        '', 'See validation.json → budget_ledger for all nineteen routes, and playable-space.geojson for the exact planar walkable/solid representation.',
        '', '**One revised composition only. Not accepted; awaiting visual review.** After acceptance, the next experiment must generate four unchanged-P04 compositions through one reusable composition procedure with varying starting conditions/seeds. Manually authoring four layouts or changing the strategy would not meet that milestone. That automatic procedure has not been demonstrated here. Stage 4 and batch generation remain paused.','']
    (out/'review.md').write_text('\n'.join(lines),encoding='utf-8')
