"""Clean plan and physical routes/planar sightlines. No radar texture or mesh."""
import math
from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import Polygon


def render(p,c,r,path,overlay=False,service_before=False,encounter=False):
    im=Image.new('RGB',(1800,1600),'#0e1924');d=ImageDraw.Draw(im)
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',n)
    bounds=c['envelope'].bounds;scale=min(1530/(bounds[2]-bounds[0]),1240/(bounds[3]-bounds[1]))
    ox=(1800-(bounds[2]-bounds[0])*scale)/2-bounds[0]*scale;oy=1440+bounds[1]*scale
    def xy(q):return (ox+q[0]*scale,oy-q[1]*scale)
    def geom(g,color):
        mask=Image.new('L',im.size);md=ImageDraw.Draw(mask)
        for poly in list(g.geoms) if hasattr(g,'geoms') else [g]:
            if not isinstance(poly,Polygon):continue
            md.polygon([xy(v) for v in poly.exterior.coords],fill=255)
            for ring in poly.interiors:md.polygon([xy(v) for v in ring.coords],fill=0)
        im.paste(color,(0,0),mask)
    def label(q,text,size=21,color='#eef5f9'):
        point=xy(q);ft=font(size);bb=d.textbbox((0,0),text,font=ft);w=bb[2];h=bb[3]-bb[1]
        d.rounded_rectangle((point[0]-w/2-5,point[1]-h/2-6,point[0]+w/2+5,point[1]+h/2+5),radius=3,fill='#172b3b')
        d.text((point[0]-w/2,point[1]-h/2-5),text,font=ft,fill=color)
    def line(points,color,width=4,dashed=False):
        screen=[xy(q) for q in points]
        if not dashed:d.line(screen,fill=color,width=width)
        else:
            for a,b in zip(screen,screen[1:]):
                distance=math.dist(a,b);n=max(1,int(distance/13))
                for j in range(0,n,2):
                    d.line([tuple(a[k]+(b[k]-a[k])*j/n for k in (0,1)),tuple(a[k]+(b[k]-a[k])*min(j+1,n)/n for k in (0,1))],fill=color,width=width)
    title='P04 / previous architecture — site-avoiding service bypasses' if service_before else 'P04 / architectural revision' + (' — focused encounters and clearance' if encounter else ' — routes and sightlines' if overlay else ' — clean blockout plan')
    d.text((70,32),title,font=font(38),fill='#eef5f9')
    d.text((70,88),'One authored composition. Stage 4 and batch generation paused; visual review pending.',font=font(23),fill='#b2c9d8')
    for s in p['spaces']:
        color='#96afbf' if s['id'] in ('west_yard','east_assembly') else '#718da0' if s['id'] in ('south_court','west_forecourt','east_gate','deployment_hall') else '#607d92'
        geom(c['spaces'][s['id']],color)
    geom(c['walls'],'#17232e');geom(c['fixtures'],'#1b2b37')
    for mass in p['internal_masses']:
        if mass.get('height_class')=='low_cover':
            geom(Polygon(mass['boundary']),'#bfaa82')
            if overlay:
                centre=Polygon(mass['boundary']).centroid
                label([centre.x,centre.y],'48h',14,'#fff3d9')
    for o in p['openings']:line(o['aperture'],'#f0dea7',6)
    if not overlay and p.get('aperture_correction'):label((120,72),'B main: 128 HU',16,'#f0dea7')
    for site,boundary in p['objective_zones'].items():
        d.line([xy(q) for q in boundary+[boundary[0]]],fill='#d6e6ed',width=2)
    a=p['annotations']
    if service_before:
        for item in r['architecture_audit']['service_routes']:
            route=item['before_site_avoiding_route']
            if route:line(route['points'],'#ed8378',5)
    if overlay and not encounter:
        for rid in ('T-A-main','T-B-main','T-A-alt','T-B-alt'):
            line(r['derived_routes'][rid]['points'],'#e9bd65' if rid.endswith('main') else '#c5a3e2',5)
        line(r['derived_routes']['CT-A-switch']['points'],'#66c8ee',5)
        for item in r['architecture_audit']['service_routes']:
            line(item['after_actual_route']['points'],'#ed8378',4,dashed=True)
            contest=item['defender_contest']
            if contest['line']:line(contest['line'],'#a7e0ad',4)
        for sight in r['architecture_audit']['long_sightlines']:
            if sight['source'] in ('T','CT','A_hold','B_fight','B_territory'):
                line(sight['points'],'#e4edf3',2,dashed=True)
                mid=[sum(q[i] for q in sight['points'])/2 for i in (0,1)]
                label(mid,f"{sight['length']:.0f}u",16)
        for pid,text,offset in [('A_prep','A lobby',(0,0)),('A_fight','A forecourt',(-3,0)),
             ('B_prep','B lobby',(0,0)),('B_fight','B contest',(2,0)),('B_territory','Workshop',(0,0)),
             ('A_hold','D-A',(0,0)),('B_hold','D-B',(0,0))]:
            q=a[pid]['point'];label([q[i]+offset[i] for i in (0,1)],text,18)
    if encounter:
        from playable_composition import DerivedNavigation
        nav=DerivedNavigation(c)
        for name,sequence in p['encounter_sequences'].items():
            points=sequence['points'];route=nav.path(points[0],points[-1])
            if route:line(route['points'],'#c5a3e2' if name.endswith('side') else '#e9bd65',4)
            for i,q in enumerate(points[1:-1],1):
                if any(math.dist(q,h['point'])<3 for h in p['defender_positions']):continue
                offset=[2,2] if name=='B side' and i==2 else [-1.5,-2.5]
                label([q[0]+offset[0],q[1]+offset[1]],f"{name.split()[0]}{'m' if name.endswith('main') else 's'}{i}",14,'#ffde91')
        for defender in p['defender_positions']:
            label(defender['point'],defender['id'],17,'#a7e0ad')
            for target in defender['targets']:
                from shapely.geometry import LineString
                segment=LineString([defender['point'],target])
                if c['visibility_standing'].covers(segment):
                    line([defender['point'],target],'#a7e0ad',3,dashed=True)
            retreat=a[defender['retreat']]['point'];route=nav.path(defender['point'],retreat)
            if route:line(route['points'],'#66c8ee',2,dashed=True)
        for row in r['spatial_usefulness']['doorways']:
            if row['opening'] not in ('A_main','A_side','B_main','B_side','B_side_threshold','B_lobby'):continue
            opening=next(o for o in p['openings'] if o['id']==row['opening']);mid=[sum(v[i] for v in opening['aperture'])/2 for i in (0,1)]
            label([mid[0],mid[1]-1.7],f"{row['clear_source_units']:.0f}w",14,'#f0dea7')
        label((73,72),'Full height: 160 HU',19)
        label((73,68),'Low cover: 48 HU',19)
        label((73,64),'Stand eye 64 / crouch 46',17)
        label((73,59),'Provisional scale',19)
        label((73,55),'1 plan unit = 32 HU',19)
        for i,row in enumerate(r['spatial_usefulness']['deployment_to_first_contact']):
            label((73,49-i*4),f"T → {row['site']} contact: {row['to_first_contact_source_units']:.0f} HU",17)
        switch=next(row for row in r['spatial_usefulness']['key_distances'] if row['route']=='CT-A-switch')
        label((73,41),f"Rear switch: {switch['source_units']:.0f} HU",17)
        label((96,75),'Side staging',16)
    for pid in ('T','CT','A','B'):
        q=a[pid]['point'];label(q,pid+' SPAWN' if pid in ('T','CT') else pid,22 if pid in ('T','CT') else 42)
    if p.get('engine_scale'):
        # Actual-size square, not an enlarged player icon.
        marker=1.;q=[70,21];corners=[xy([q[0]-.5,q[1]-.5]),xy([q[0]+.5,q[1]+.5])]
        d.rectangle((corners[0][0],corners[1][1],corners[1][0],corners[0][1]),fill='#f7e6bb',outline='#17232e')
        label([76,23],'32w player',15,'#f7e6bb')
    if encounter:
        d.text((70,1480),'Gold/purple: main/side entry to plant   Green: standing defender sight   Blue dashed: fallback paths',font=font(21),fill='#bdd1df')
        d.text((70,1516),'Tan: low collision cover, seen over when standing   Cream doorway labels: clear width in HU',font=font(20),fill='#bdd1df')
    elif overlay:
        label((72,67),'Solid compound / no Mid',20)
        d.text((70,1480),'Gold: main attacks   Purple: side attacks   Blue: defender rotation via rear deployment',font=font(21),fill='#bdd1df')
        d.text((70,1516),'Red dashed: service → CT advance through site   Green: defender contest sightline   White dashed: long sampled LOS',font=font(20),fill='#bdd1df')
    elif service_before:d.text((70,1480),'Red: computed service → CT route with both entire site spaces blocked. Previous architecture, preserved for comparison.',font=font(21),fill='#edb0a6')
    else:d.text((70,1480),'Blue-gray: walkable   Dark: full-height solid   Tan: 48-HU low cover   Cream: openings   Outlined: plant envelope',font=font(20),fill='#bdd1df')
    if not overlay and p.get('engine_scale'):
        bar=512/p['engine_scale']['source_units_per_plan_unit']*scale
        d.line([(70,1526),(70+bar,1526)],fill='#e1eaf0',width=4)
        d.text((85+bar,1511),'512 HU — provisional scale',font=font(20),fill='#bdd1df')
    d.text((70,1560),'Provisional HU scale and player footprint. No runtime calibration, timing, balance, mesh or automatic-generation claim.',font=font(18),fill='#92afc2')
    im.save(path)


def write_report(p,r,out):
    audit=r['architecture_audit'];lines=['# P04 architectural revision — not accepted','',
        'Stage 4 and batch generation remain paused. This revises the same authored composition; it does not demonstrate automatic generation or diversity.',
        '',f'![Clean plan]({(out/"plan-clean.png").as_posix()})','',f'![Routes and sightlines]({(out/"plan-annotated.png").as_posix()})','',
        '## Reference-guided architectural changes','',
        '| Change | Inspected references | Applied arrangement |','|---|---|---|']
    for item in p['reference_guidance']:
        refs=', '.join(f'[{s.split("/")[2]}]({(out.parents[1]/s).as_posix()})' for s in item['references'])
        lines.append(f"| {item['change']} | {refs} | {item['use']} |")
    lines+=['',p['proportion_basis'],'',
        'The evidence is qualitative architectural arrangement from the actual source-NAV overviews, not numerical calibration from radar pixels. No source timing, elevation advantage or exact scale is inferred.',
        '', 'A now has a doorway pocket, a constricted transition beside an attached store, a crosscourt fight and a northern objective bay. Its side entry reaches another sector of the same yard. The attached building footprints define these fights instead of isolated cover blocks.',
        '', 'B now has a lobby threshold, a wider contest room, a lateral workshop entrance and a return around the building face into an offset execute/objective bay. The side approach skips the workshop investment but still opens into defended site space. Each turn hides a later threshold; it is not a decorative bend.',
        '', 'T deployment is a compact loading court with separate departure doors. CT deployment and recovery are building-edge receiving spaces with local recesses. Historical rectangular recovery allocations are not drawn as architecture.',
        '', '## Service bypass audit','',
        f'![Previous actual site-avoiding routes]({(out/"service-bypasses-before.png").as_posix()})','',
        'Navigation is derived from the complete walkable footprint. For the bypass test, both complete site spaces are blocked; no team/phase label blocks movement. This checks whether service access can reach CT without entering either site.',
        '', '| Service | Before: actual site-avoiding crossings | After: actual route to CT | Site-avoiding route remains? | Defender sightline |','|---|---|---|---|---|']
    for s in audit['service_routes']:
        lines.append(f"| {s['site']} | {' → '.join(s['before_crossings'])} | {' → '.join(s['after_crossings'])} | {'YES' if s['after_site_avoiding_route'] else 'No'} | {s['defender_contest']['line_of_sight']} |")
    lines.append('')
    for s in audit['service_routes']:
        lines.append(f"- {s['site']} service: previous site-avoiding distance {s['before_site_avoiding_route']['length']:.1f} units; revised through-site advance {s['after_actual_route']['length']:.1f} units.")
    lines+=['',
        'The former A_recovery_access and B_recovery_access openings are removed. Service routes terminate at site entries. D-A and D-B can see their side-entry engagement sectors (green lines), so an attacker advance toward CT crosses a defended site mouth and rear threshold. These are geometric opportunities, not proof that defenders arrive first, hold safely, or win the engagement.',
        '', '## Sightlines and structural preservation','',
        audit['sightline_scope'],'',
        '| Position | Longest sampled visible ray (abstract units) |','|---|---:|']
    for s in audit['long_sightlines']:lines.append(f"| {s['source']} | {s['length']:.1f} |")
    lines+=['',
        'P04 still has separate attacker assignments, no central Mid connector and a shortest defender switch using rear CT deployment circulation. Main and side attack paths reach separate site openings. Original strategy hash is unchanged.',
        '',f"Undeclared opening samples: {len(r['opening_audit']['unintended_openings'])}. Shortest site switch: {r['rotation']['shortest_length']:.1f}; avoiding CT deployment: {r['rotation']['shortest_avoiding_CT_deployment']:.1f}.",
        '', '## Remaining weaknesses','',
        '- The macro plan still consists of separated A/B investments around solid territory, as P04 specifies. Architectural improvements do not establish a stronger automatic strategic generator.',
        '- Long visible rays remain along deployment approaches, rear circulation and parts of A. White lines expose them; real head-height geometry, cover, elevations and utility are not modeled.',
        '- A has tight doorway/store transitions; B side circulation still has a long segment. Player clearance, collision radius and close-range fighting need a later engine-scale check.',
        '- Removing service-to-rear access forces side attacks to win site space before flanking CT, but may make them too committal. Timing, retreat safety and defender power are unverified.',
        '- Prior abstract recovery budgets remain frozen and checked. They are not optimized or relaxed; misses below remain unresolved. Historical allocation rectangles no longer define the revised recovery architecture.',
        '', '## Unresolved ledger','']
    for issue in r['issues']:lines.append('- '+str(issue))
    for violation in r['violations']:lines.append('- '+str(violation))
    lines+=['','No visual acceptance, gameplay-quality pass, diversity batch or Stage 4 authorization is implied. Stop here for review.','']
    (out/'review.md').write_text('\n'.join(lines),encoding='utf-8')
