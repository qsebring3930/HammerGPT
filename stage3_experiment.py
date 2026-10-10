"""Sixteen territory schematics, semantic-preservation and novelty reports.

No GeometryGenerator, mesh generator, VMAP writer or game install writes.
"""
import copy
import html
import itertools
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import Polygon

from semantic_pipeline import SpatialEmbedder,GameplayValidator
from spatial_validation import validate_preservation,spatial_equivalence

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/spatial-composition-001'
SELECTED={'P01':[71317,81401,91457,101501],
          'P04':[112061,122069,132071,142081],
          'P06':[152087,162089,172097,182101],
          'P10':[192109,202117,212123,222127]}


def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',size)


def identity(e):
    a=e['anchors'];t=np.array(a['T']['xy']);ct=np.array(a['CT']['xy']);aa=np.array(a['A']['xy']);bb=np.array(a['B']['xy'])
    closest='A' if np.linalg.norm(aa-t)<np.linalg.norm(bb-t) else 'B'
    from spatial_validation import angle
    fan=angle(aa-t,bb-t);bridge='raised rear crossing' if e['bridge'] else 'ground-level transfers'
    dominant=max(e['regions'],key=lambda k:Polygon(e['regions'][k]['boundary']).area)
    return f'{closest} faces T more closely; sites fan {fan:.0f}°; {dominant.replace("_"," ")} dominates; {bridge}'


def render(e,report,title,path,width=1040,height=820):
    im=Image.new('RGB',(width,height),'#101b28');draw=ImageDraw.Draw(im)
    xmin,ymin,xmax,ymax=e['bounds'];pad=55;top=116;bottom=100
    scale=min((width-2*pad)/(xmax-xmin),(height-top-bottom)/(ymax-ymin))
    ox=width/2-(xmin+xmax)/2*scale;oy=top+(height-top-bottom)/2+(ymin+ymax)/2*scale
    def xy(p):return (p[0]*scale+ox,oy-p[1]*scale)
    draw.text((22,14),title,font=font(27),fill='#edf3f9')
    desc=identity(e)
    # Wrap subtitle to avoid overlapping the actual territory image.
    words=desc.split();lines=['']
    for w in words:
        if draw.textlength(lines[-1]+' '+w,font=font(17))>width-44:lines.append(w)
        else:lines[-1]+=(' ' if lines[-1] else '')+w
    for j,line in enumerate(lines):draw.text((22,53+j*22),line,font=font(17),fill='#aabccc')
    for carrier in e['travel_envelopes'].values():
        draw.polygon([xy(p) for p in carrier['boundary']],fill='#35485a')
    colors={'A':'#627f99','B':'#648399','T':'#836840','CT':'#416d86','control':'#697f8b','regroup':'#6a7083','retake_union':'#557581'}
    for key,region in e['regions'].items():
        poly=[xy(p) for p in region['boundary']];draw.polygon(poly,fill=colors.get(key,'#496175'))
        draw.line(poly+[poly[0]],fill='#8b9dab',width=2)
    # Main physical paths are annotations across shared territories. They are
    # not line-buffered floor walls. Do not draw every semantic relation.
    for rid,r in e['routes'].items():
        if r['purpose'] not in ('primary_attack','secondary_attack','rotation','defensive_access'):continue
        if r['purpose']=='defensive_access' and r['phase']!='opening':continue
        pts=[xy(p) for p in r['points']]
        color='#e9b451' if r['purpose']=='primary_attack' else '#bb94e8' if r['purpose']=='secondary_attack' else '#82c9df' if r['purpose']=='defensive_access' else '#e2eaf0'
        if r['purpose']=='rotation':
            for i in range(0,len(pts)-1,3):draw.line(pts[i:min(i+2,len(pts))],fill=color,width=2)
        else:draw.line(pts,fill=color,width=3)
        if len(pts)>3:
            end=np.array(pts[-1]);v=end-np.array(pts[-3]);v=v/(np.linalg.norm(v) or 1);normal=np.array([-v[1],v[0]])
            draw.polygon([tuple(end),tuple(end-v*11+normal*4),tuple(end-v*11-normal*4)],fill=color)
    for key,carrier in e['travel_envelopes'].items():
        if carrier['level']:
            pts=[xy(p) for p in e['segments'][key]['points']]
            draw.line(pts,fill='#edf4fb',width=9)
            draw.line(pts,fill='#a6b6d3',width=4)
            draw.text(pts[len(pts)//2],'+1 / ramps',font=font(15),fill='#ffffff')
    label_boxes=[]
    label_order=sorted(e['regions'],key=lambda k:(k not in ('A','B','T','CT','control'),k))
    for key in label_order:
        region=e['regions'][key]
        label={'T':'T spawn','CT':'CT spawn','A':'A','B':'B','control':'Mid' if any(p=='control' for p in region['strategic_places']) and report['measurements']['mid_access'] else 'CT control' if key=='control' else 'control'}.get(key,key.replace('_',' '))
        point=xy(region['center']);f=font(31 if key in ('A','B') else 16)
        box=draw.textbbox((0,0),label,font=f);w=box[2]-box[0];h=box[3]-box[1]
        offsets=[(0,0),(0,-24),(0,24),(w/2+14,0),(-w/2-14,0),(0,-48),(0,48)]
        candidates=[]
        for dx,dy in offsets:
            rect=(point[0]+dx-w/2-4,point[1]+dy-h/2-5,point[0]+dx+w/2+4,point[1]+dy+h/2+7)
            overlap=sum(max(0,min(rect[2],q[2])-max(rect[0],q[0]))*max(0,min(rect[3],q[3])-max(rect[1],q[1])) for q in label_boxes)
            candidates.append((overlap,dx,dy,rect))
            if overlap==0:break
        _,dx,dy,rect=min(candidates,key=lambda v:v[0]);label_boxes.append(rect)
        if dx or dy:draw.line((point,(point[0]+dx,point[1]+dy)),fill='#e1eaf0',width=1)
        draw.rounded_rectangle(rect,radius=3,fill='#152330')
        draw.text((point[0]+dx-w/2,point[1]+dy-h/2-4),label,font=f,fill='#eef4fa')
    y=height-82
    for x,label,color in [(22,'main attack','#e9b451'),(223,'alternate','#bb94e8'),(409,'CT access','#82c9df'),(610,'rotation','#e2eaf0')]:
        draw.line((x,y+9,x+28,y+9),fill=color,width=3);draw.text((x+36,y-3),label,font=font(16),fill='#d4e2ec')
    status='Relative checks pass / physical claims pending' if report['schematic_checks_passed'] else 'REJECTED: '+', '.join(sorted({i['code'] for i in report['issues']}))
    draw.text((22,height-53),status[:100],font=font(15),fill='#bfe0cc' if report['schematic_checks_passed'] else '#ffb39d')
    draw.text((22,height-28),'Approximate territories + travel envelopes. No walls, floors or VMAP meshes.',font=font(14),fill='#91a4b7')
    im.save(path)
    return im


def diagnostic_traits(e):
    a=e['anchors'];t=np.array(a['T']['xy']);ct=np.array(a['CT']['xy']);scale=np.linalg.norm(ct-t)
    def normalized(pid):return ((np.array(a[pid]['xy'])-t)/(scale or 1)).tolist()
    from spatial_validation import angle
    return {'normalized_landmarks':{pid:normalized(pid) for pid in ('A','B','T','CT')},
        'site_fan_degrees_at_T':angle(np.array(a['A']['xy'])-t,np.array(a['B']['xy'])-t),
        'rotation_directness':{rid:r['length']/(np.linalg.norm(np.array(r['points'][-1])-np.array(r['points'][0])) or 1) for rid,r in e['routes'].items() if r['purpose']=='rotation'},
        'territory_compactness':{k:4*math.pi*Polygon(v['boundary']).area/Polygon(v['boundary']).length**2 for k,v in e['regions'].items()},
        'region_environments':{k:v['environment'] for k,v in e['regions'].items()},
        'level_separation':e['bridge'],'purpose':'Measurements/diagnostics, not novelty optimization objectives.'}


def run():
    OUT.mkdir(parents=True,exist_ok=True);all_rows=[];comparisons=[];pages=[]
    source_rows=json.loads((ROOT/'output/strategic-diversity-001/proposals.json').read_text())
    for pid,seeds in SELECTED.items():
        directory=OUT/pid;directory.mkdir(exist_ok=True)
        plan=json.loads((ROOT/f'output/strategic-diversity-001/{pid}/plan.json').read_text());strategic=GameplayValidator().validate(plan)
        if not strategic['passed']:raise RuntimeError('Selected strategy no longer passes: '+pid)
        (directory/'original-strategy.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
        original=next(row for row in source_rows if row['id']==pid)
        (directory/'original-intent.md').write_text('\n\n'.join(f'**{key.replace("_"," ")}:** {original[key]}' for key in
            ('identity','deployment','convergence','first_contacts','site_approach','rotation','control','flank','retreat','recovery','path_equivalence')),encoding='utf-8')
        candidates=[];images=[]
        for i,seed in enumerate(seeds,1):
            eid=f'{pid}-E{i}';embedding=SpatialEmbedder().compose(plan,strategic,seed);report=validate_preservation(plan,embedding)
            row={'id':eid,'blueprint':pid,'seed':seed,'identity':identity(embedding),
                 'schematic_checks_passed':report['schematic_checks_passed'],'rejected_as_equivalent':False,
                 'blocking_codes':sorted({v['code'] for v in report['issues']}),
                 'unverified_codes':sorted({v['code'] for v in report['unverified']}),
                 'semantic_claims_fully_verified':False,'stage_4_authorized':False}
            for name,obj in [('embedding',embedding),('preservation',report),('traits',diagnostic_traits(embedding))]:
                (directory/f'E{i}-{name}.json').write_text(json.dumps(obj,indent=2),encoding='utf-8')
            candidates.append((eid,embedding,row));all_rows.append(row)
            images.append(render(embedding,report,eid,directory/f'E{i}.png'))
            print(json.dumps({'candidate':eid,'relative_checks':report['schematic_checks_passed'],'issues':row['blocking_codes']}),flush=True)
        for (aid,a,ar),(bid,b,br) in itertools.combinations(candidates,2):
            comp=spatial_equivalence(a,b);comparisons.append({'blueprint':pid,'left':aid,'right':bid,**comp})
            if comp['equivalent']:br['rejected_as_equivalent']=True;br.setdefault('equivalent_to',[]).append(aid)
        sheet=Image.new('RGB',(2080,1640),'#101b28')
        for i,im in enumerate(images):sheet.paste(im,((i%2)*1040,(i//2)*820))
        sheet.save(directory/'four-candidates.png')
        pages.append((pid,original,candidates))
    summary={'selected':list(SELECTED),'spatial_candidates':len(all_rows),
        'relative_check_passes':sum(r['schematic_checks_passed'] for r in all_rows),
        'equivalent_rejections':sum(r['rejected_as_equivalent'] for r in all_rows),
        'fully_verified_semantic_candidates':0,'stage_4_authorized':False,
        'floor_geometry_generated':False,'gate':'Human spatial review + unresolved preservation checks. Do not infer Stage 4 approval from diversity.'}
    for name,data in [('summary.json',summary),('candidates.json',all_rows),('spatial-equivalence.json',comparisons)]:
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
    lines=['# Stage 3: spatial composition experiment','',
        'Sixteen independent territory compositions from four unchanged strategic plans. No detailed floor geometry, walls or VMAP meshes.',
        '',f"Relative-check passes: {summary['relative_check_passes']}/16. Equivalent rejections: {summary['equivalent_rejections']}. Fully verified tactical candidates: 0. Stage 4 remains paused.",
        '', 'Approximate envelopes are potential playable territory, not built corridors. Strategic places share territories and ports. Intent relationships do not automatically become new physical links.',
        '', 'All units are abstract. Lengths/ratios and observed entry directions are measured directly. No CS-speed conversion or new tactical quality cutoff is claimed. Novelty alignment removes translation, rotation, reflection and uniform scale; uncertainty comes from the approximate territory anchors.',
        '', '## Four compositions of each unchanged blueprint','']
    for pid,original,candidates in pages:
        lines += [f'### {pid}: original intent','',original['identity']+' '+original['why_different'],'',
                  f'![Four spatial compositions of {pid}]({(OUT/pid/"four-candidates.png").as_posix()})','',
                  '| Candidate | Spatial identity | Relative preservation | Novelty |','|---|---|---|---|']
        for eid,e,row in candidates:
            status='checks pass; tactical claims pending' if row['schematic_checks_passed'] else 'REJECTED: '+', '.join(row['blocking_codes'])
            novelty='REJECTED as equivalent' if row['rejected_as_equivalent'] else 'not equivalent under the uncertainty audit'
            lines.append(f"| {eid} | {row['identity']} | {status} | {novelty} |")
        lines += ['',f'Original plan and all route measurements: `{pid}/original-intent.md`, `E1-preservation.json` through `E4-preservation.json`.','']
    lines += ['## Preservation limits and Stage 3 diagnosis','',
        'The region model merges site entries, defender positions and objective space into one territory while preserving separate ports. Staging and encounters can occupy connected subspaces. A conditional rear flank reuses existing defender transfer geometry, rather than adding a straight chord because its intent skips a strategic waypoint.',
        '', 'The free-territory navigation check ignores team/phase labels. It flags possible short/safe rotations caused by territory overlap. Exposure checks use the transfer territory as a coarse threat proxy; there is no verified line of sight. Upper decks/ramp transitions are schematic and require movement checks. Timing-order checks use existing plan intentions; meaningful timing and angle quality still need calibration.',
        '', 'These schematics cannot prove actual information gain, encounter range, cover, exposure, retreat safety or retake quality. Drawing different silhouettes does not settle those claims. Any failed preservation check or equivalent composition remains rejected, with its measurements retained.',
        '', 'Stage 1 future work remains recorded: common main/secondary-entry scaffolding, limited flank/recovery grammar, ownership relay and vertical commitment weaknesses. Those did not prevent producing this Stage 3 experiment.',
        '', '**No automatic Stage 4 progression.** The visual criterion—four clearly different compositions of the same strategy—is for human review. If these still read as connected patches rather than coherent territories, Stage 3 needs a stronger region-partition/site-composition model before geometry.','']
    (OUT/'review.md').write_text('\n'.join(lines),encoding='utf-8')
    # Local HTML offers four-column side-by-side review and direct measurement links.
    content=['<!doctype html><meta charset="utf-8"><title>Stage 3 spatial review</title><style>body{background:#101b28;color:#e1edf5;font:16px system-ui;margin:30px}section{margin:40px 0}.grid{display:grid;grid-template-columns:repeat(4,minmax(230px,1fr));gap:12px}img{width:100%;cursor:zoom-in}article{background:#1b2a38;padding:12px;border-radius:10px}a{color:#9ed4ff}p{line-height:1.5}.warn{color:#ffb39d}@media(max-width:1100px){.grid{grid-template-columns:repeat(2,1fr)}}</style><h1>Stage 3: approximate territories</h1><p>No floor geometry. Click a schematic for full size. All tactical claims remain provisional.</p>']
    for pid,original,candidates in pages:
        content += [f'<section><h2>{pid}</h2><p>{html.escape(original["identity"]+" "+original["why_different"])}</p><div class="grid">']
        for i,(eid,e,row) in enumerate(candidates,1):
            content += [f'<article><h3>{eid}</h3><a href="{pid}/E{i}.png"><img src="{pid}/E{i}.png"></a><p>{html.escape(row["identity"])}</p><p class="warn">'+html.escape(', '.join(row['blocking_codes']) or 'Relative checks pass; tactical verification pending')+'</p>'+f'<a href="{pid}/E{i}-preservation.json">Preservation measurements</a></article>']
        content += ['</div></section>']
    content+=['<p>Stage 4 paused. <a href="spatial-equivalence.json">All transformation-invariant comparisons</a></p>']
    (OUT/'review.html').write_text('\n'.join(content),encoding='utf-8')
    print(json.dumps(summary),flush=True)
    audit_existing(refresh_annotations=False)
    return summary


def audit_existing(refresh_annotations=True):
    """Finalize review of saved candidates without generating any new embedding."""
    from spatial_validation import equivalence_controls
    from strategic_similarity import compare_strategies
    controls=[];comparisons=[];selection=[];plans={}
    for pid in SELECTED:
        plans[pid]=json.loads((OUT/pid/'original-strategy.json').read_text());saved=[];images=[]
        for i in range(1,5):
            e=json.loads((OUT/pid/f'E{i}-embedding.json').read_text())
            report=json.loads((OUT/pid/f'E{i}-preservation.json').read_text());saved.append((i,e))
            description=[f'# {pid}-E{i}: spatial review','',identity(e),'',
                '**Composition milestone rejected.** This schematic does not establish a coherent map. Spatial interpretation retains the unchanged strategic plan; the checks below report which intentions survive or fail.',
                '', '## Site approaches and timing comparisons','',
                '| Approaches | Main length | Alternate length | Ratio | Intended duration ratio interval | Observed entry separation |',
                '|---|---:|---:|---:|---|---:|']
            for comparison in report['measurements']['alternatives']:
                description.append(f"| {' / '.join(comparison['routes'])} | {comparison['lengths'][0]:.2f} | {comparison['lengths'][1]:.2f} | {comparison['length_ratio']:.2f} | {comparison['contract_duration_ratio_interval']} | {comparison['entry_angle_observed_degrees']:.1f}° |")
            description+=['', 'Lengths are abstract measurements; intended duration ratios are design contracts, not measured CS travel times. The observed directions are compared without inventing a minimum useful angle.',
                '', '## Rotation composition','']
            for rotation in report['measurements']['rotations']:
                description.append(f"- {rotation['route']}: drawn path {rotation['planned_length']:.2f}; coarse shortest ground path {rotation['coarse_shortest_ground_length']}. Territory overlap may admit shortcuts that the drawn path conceals.")
            description+=['','## Preservation findings','']
            if report['issues']:
                for issue in report['issues']:description.append(f"- REJECTED / {issue['code']}: {issue['detail']}")
            else:description.append('Limited relative checks pass, but the visual composition milestone fails and physical tactical claims remain unverified.')
            description+=['','## Unknowns','']
            for item in report['unverified']:description.append(f"- {item['code']}: {item.get('note','')}")
            description+=['','Same-plan landmark positions, territory shapes, convergence, overlaps and any upper crossing are in the adjacent embedding and preservation JSON. No detailed floor geometry exists.','']
            (OUT/pid/f'E{i}-review.md').write_text('\n'.join(description),encoding='utf-8')
            if refresh_annotations:images.append(render(e,report,f'{pid}-E{i}',OUT/pid/f'E{i}.png'))
        if refresh_annotations:
            sheet=Image.new('RGB',(2080,1640),'#101b28')
            for j,im in enumerate(images):sheet.paste(im,((j%2)*1040,(j//2)*820))
            sheet.save(OUT/pid/'four-candidates.png')
        for (i,a),(j,b) in itertools.combinations(saved,2):comparisons.append({'blueprint':pid,'left':f'{pid}-E{i}','right':f'{pid}-E{j}',**spatial_equivalence(a,b)})
        controls.extend({'blueprint':pid,**row} for row in equivalence_controls(saved[1][1]))
    for (pa,a),(pb,b) in itertools.combinations(plans.items(),2):selection.append({'left':pa,'right':pb,**compare_strategies(a,b)})
    summary=json.loads((OUT/'summary.json').read_text())
    summary.update(critical_composition_test_passed=False,
        assistant_visual_review='FAILED: repeated patch-and-travel-band construction; not four coherent spatial compositions per strategy.',
        equivalent_rejections=sum(c['equivalent'] for c in comparisons),
        dominant_arrangement_equivalent_pairs=sum(c['dominant_landmark_arrangement_equivalent'] for c in comparisons),
        transformation_controls_equivalent=sum(c['equivalent'] for c in controls),transformation_control_count=len(controls),
        stage_3_experiment='stopped after sixteen candidates; no further composition generation',stage_4_authorized=False)
    for name,data in [('summary.json',summary),('spatial-equivalence.json',comparisons),('equivalence-controls.json',controls),('strategic-selection.json',selection)]:
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
    diagnosis="""# Stage 3 visual gate: FAILED

The sixteen requested candidates were produced and retained, then composition generation stopped. All four blueprint sheets were visually inspected. They still read as separate patches joined by travel bands, with clustered site systems, long recovery appendages and inconsistent territorial separation. They do not demonstrate the requested four coherent Counter-Strike compositions of each strategy.

## Why the relative-check result is insufficient

Three P01 candidates pass limited route-order, entry-direction and access checks. That is not a pass of the composition milestone or a physical tactical certification. Thirteen candidates fail at least one preservation check. Different coordinates, region outlines and raised-crossing annotations are not enough to establish useful spatial diversity. All candidates are rejected for Stage 4 progression.

The exact-transform/jitter controls verify the equivalence mechanism. Full normalized coordinate comparisons do not detect every recurring *construction signature*. The sampler can be non-equivalent numerically and still keep generating patches and connective bands. Primary-landmark comparisons are reported separately to prevent distant recovery appendages dominating every comparison.

## Cause in the embedder

1. Site systems are coalesced, but most other strategic roles still allocate independent territory centres. Approximate shapes are then grown locally around those centres.
2. Continuous fitting mainly minimizes movement-length stress. It does not decide a coherent partition into surrounding courtyards, building masses, connected interiors and circulation around inaccessible space.
3. Travel envelopes are still built from pairwise curves. Variable widths remove the constant-width corridor assumption but do not remove the graph drawing signature.
4. Overlapping envelopes admit unintended movement. The ground-territory audit finds routes that can avoid the specified exposed transfer, or shorten a costly rotation.
5. Recovery spaces remain weakly constrained and drift into long peripheral appendages. Their movement and area budgets are not composed with the rest of the territory.

## What failed preservation

- P01-E1 loses independently accessible Mid under the schematic territory exclusions.
- P04 candidates either invert an intended approach-length ordering or admit a shorter-than-intended defender switch.
- P06 candidates invert an intended approach-length ordering.
- P10 candidates admit a ground path avoiding the proposed exposed-transfer territory; some also undermine rotation cost.

Length-order checks intentionally expose a modelling limitation: strategic duration contracts mix travel and territory-clearance investment. The experiment reports this mismatch; it does not claim a measured CS timing failure. Real exposure, cover, information, navigation and retakes are unverified because detailed geometry does not exist.

## Next Stage 3 work, before any further generation

Replace centre-first packing plus per-link envelopes with a continuous territory-partition representation. Let one strategic region occupy multiple connected subspaces, and let several strategic relationships share the same circulation area. Solve ownership, contact boundaries, site entry sectors, recovery location and circulation through the same composition. Allocate timing to travel versus contest/clearance explicitly. Check full schematic movement availability rather than relying on phase labels or drawn routes.

The failed batch remains a regression set for that Stage 3 work. Existing Stage 1 limitations stay recorded as future grammar work and did not prevent this experiment. No detailed floors, VMAPs or meshes were generated. Stage 4 remains paused.
"""
    (OUT/'diagnosis.md').write_text(diagnosis,encoding='utf-8')
    review=OUT/'review.md';body=review.read_text(encoding='utf-8')
    warning='**Stage 3 composition gate FAILED. Generation stopped after this batch.** Three limited-check passes do not certify a coherent map. See [the diagnosis](diagnosis.md).\n\n'
    if warning not in body:review.write_text(body.replace('# Stage 3: spatial composition experiment\n\n','# Stage 3: spatial composition experiment\n\n'+warning),encoding='utf-8')
    h=OUT/'review.html';body=h.read_text(encoding='utf-8')
    banner='<p class="warn"><strong>Stage 3 composition gate FAILED. No Stage 4.</strong> <a href="diagnosis.md">Diagnosis</a></p>'
    if banner not in body:h.write_text(body.replace('<h1>Stage 3: approximate territories</h1>','<h1>Stage 3: approximate territories</h1>'+banner),encoding='utf-8')
    print(json.dumps(summary),flush=True)
    return summary


if __name__=='__main__':run()
