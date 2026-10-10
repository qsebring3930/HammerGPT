"""Read-only report/overlays from all recorded distributed-Mid attempts."""
import copy,json
from pathlib import Path
from PIL import Image,ImageDraw
from map_layout import render,font
from playable_composition import compile_composition
from inspect_planar_paths import inspect
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def run():
 root=ROOT/'output/distributed-mid-001';out=root/'review';out.mkdir(exist_ok=False);rows=[];plans=[]
 for name in ('street','courts-handoff','matched'):
  folder=root/'r4'/name;p=read(folder/'composition.json');v=read(folder/'validation.json');c=compile_composition(p);visual=copy.deepcopy(p)
  if 'mid_street' in c['spaces']:visual['annotations']['Mid']['point']=list(c['spaces']['mid_street'].representative_point().coords[0])
  im=render(visual,c,v,False);d=ImageDraw.Draw(im);d.rectangle((0,0,1600,145),fill='#101923');label=p['mid_organization'].replace('_',' ').title();d.text((65,28),label+' / seed '+str(p['seed']),font=font(34),fill='white');d.text((65,80),'Shared seeded rules · 32 HU/plan unit · Stage 4 paused · candidate for review',font=font(21),fill='#c5d5df')
  x0,y0,x1,y1=c['envelope'].bounds;scale=1300/max(x1-x0,y1-y0)
  def xy(q):return 150+(q[0]-x0)*scale,1450-(q[1]-y0)*scale
  if p['mid_organization']=='linked_courts':d.text(xy(p['annotations']['Mid2']['point']),'Mid 2',font=font(23),fill='white',stroke_width=2,stroke_fill='#23313f')
  im.save(out/(name+'-clean.png'));plans.append(im)
  overlay=render(visual,c,v,True);dr=ImageDraw.Draw(overlay)
  for sid in p['mid_spaces']:dr.line([xy(q) for q in c['spaces'][sid].exterior.coords],fill='#73eadf',width=3)
  for site in ('A','B'):
   q=p['annotations'][site+'_transfer']['point'];dr.text(xy(q),site+' transfer',font=font(20),fill='#f4c6df',stroke_width=2,stroke_fill='#101923')
   if site in p['mid_handoffs']:
    dr.text(xy(p['annotations'][site+'_staging']['point']),site+' shared junction',font=font(20),fill='#ffc480',stroke_width=2,stroke_fill='#101923')
  dr.text(xy(p['annotations']['Mid2']['point']),'Mid exit' if p['mid_organization']=='contested_street' else 'Mid 2',font=font(23),fill='#73eadf',stroke_width=2,stroke_fill='#101923');overlay.save(out/(name+'-roles-routes.png'))
  inspect(folder,out/(name+'-unrestricted'),True)
  rows.append(dict(name=name,seed=p['seed'],organization=p['mid_organization'],handoff_sites=p['mid_handoffs'],mid_program=p['mid_program'],handoff_junctions=v['handoff_junctions'],physical_pass=v['physical_pass'],request_pass=v['request_pass'],compactness=v['compactness'],opening_widths=v['opening_widths'],summary=read(folder/'summary.json')))
 sheet=Image.new('RGB',(2400,1200),'#101923')
 for i,im in enumerate(plans[:2]):sheet.paste(im.resize((1200,1200)),(i*1200,0))
 sheet.save(out/'comparison.png');(out/'measurements.json').write_text(json.dumps(rows,indent=2))
 attempts=[]
 for revision in ('r1','r2','r3','r4'):
  for name in ('matched','street','courts-handoff'):
   for a in read(root/revision/name/'summary.json')['attempts']:attempts.append(dict(revision=revision,example=name,**a))
 (out/'all-attempts.json').write_text(json.dumps(attempts,indent=2))
 text=f'''# Distributed Mid — review candidates, Stage 4 paused

Implemented in the shared JSON→strategy→architecture→validation→image pipeline. This changes authored seeded procedural rules, not neural training. No Stage 4, VMAPs, meshes, graybox or candidate-specific geometry edits. All earlier experiments remain preserved.

## Root cause and changes

The earlier planner always assigned T→Mid, CT→Mid, Mid→A and Mid→B to one reservation, and its validator forbade joining any main approach. The spatial generator held Mid in a single chamber on an orthogonal flank scaffold. Extra angle or deformation rules preserved that four-way topology.

Mid now has two independently accessible portions. In `contested_street`, they compile into ONE continuous architectural space with a frontage band spanning both reservations and distributed side mouths. In `linked_courts`, they are separate contest courts joined through circulation around a turn. Mid branches leave different portions and cross transfer territory before reaching entry preparation. Several roles can share the same territory; intermediate reservations can merge into a single gallery. No room is allocated from a callout name.

`mid_access_mode=one_approach_handoff` lets one Mid branch join an existing main preparation junction. The other retains a different site entrance. The handoff is selected coordinate-free from the base seed BEFORE any spatial placement. The selection stays fixed across failed spatial attempts. Handoffs must be declared, must converge only at the intended junction, and must arrive through two distinct physical openings. The shared final site entrance counts as ONE entrance. Its tactical difference, information value and control remain unresolved; it is not counted as another independent site-entry route.

The Mid reservation search uses 6×6 rather than 5×5 and supports staggered-flank/folded-front placement as well as aligned flanks. The additional territory supports intermediate relationships rather than optimizing graph complexity. Width rules remain based on the prior provisional proportions; total span and travel can increase. The reservation lattice still constrains architecture. No-Mid remains optional and uses the existing 5×5 pipeline.

## Supported controls

- `gameplay.mid`: absent, contested, auto.
- `gameplay.mid_organization`: auto, contested_street, linked_courts. Explicit organization conflicts with absent Mid.
- `gameplay.mid_access_mode`: auto, separate_entries, one_approach_handoff. Auto currently chooses separate_entries for backward-compatible semantics; it does not secretly add a handoff. Explicit mode conflicts with absent Mid.
- Existing independent main approaches, secondary access, rotation, site architecture, scale constraints and complexity preferences remain available. These are limited supported organizations, not unrestricted tactical language understanding. The LLM adapter exposes these fields but remains unverified live.

The user's Dust2 example informs the functional change—Mid can deliver players into other approach territory. We did not claim to extract Catwalk/Tunnels/B-main identity or exact design dimensions from coarse NAV subdivisions. Existing conservative Dust2/Cache/Train movement evidence and radar R09/R14/R17/R18 inform street/turn/frontage relationships. Numeric dimensions and these new strategic organizations are authored generation choices, not learned or measured tactical truths.

## Clean plans at identical scale

![Street and linked courts]({(out/'comparison.png').as_posix()})

| Example | Strategic behavior | Physical/request | Attempts in final revision |
|---|---|---|---|
'''
 for row in rows:
  description='Distributed entrances and separate entry preparation for both sites' if not row['handoff_sites'] else 'Distributed courts; '+row['handoff_sites'][0]+' joins a primary preparation junction, other site has separate secondary entry'
  text+=f"| {row['name']} / {row['seed']} | {description} | {row['physical_pass']} / {row['request_pass']} | {row['summary']['total_attempts']} |\n"
 text+='''
Final revision: five attempts, three candidates, two construction rejections. The attempted matched seed 985731 and next seed 985732 exhausted bounded placement/route search. Selected fallback 985733 is NOT a matched-seed before/after. The old seed-985731 cross layout remains unchanged. No gate was relaxed to get a match.

All four shared revisions reran the same three predeclared base seeds; twenty recorded attempts total, including eight construction rejections. r1 introduces distributed Mid and handoffs; r2 merges the street and validates distinct physical handoff arrivals; r3 fixes coordinate-free handoff selection across spatial failures; r4 adds a continuous street frontage band instead of a chamber-to-chamber neck. Full source snapshots, hashes, specifications, decision logs, attempt seeds, acceptance/rejection reasons and diagnostic images remain under each revision. No selective seed repairs.

## Roles and actual routes

Gold paths show ordered main intent; pink secondary intent; blue defender paths; cyan outlines identify actual Mid territory. Transfer labels denote committed movement territory, not guaranteed safety or invented additional rooms. Separate diagnostic images show unrestricted shortest player movement and sampled planar standing rays.

'''
 for row in rows:
  name=row['name'];text+=f"### {name}, seed {row['seed']}\n\n![Roles and routes]({(out/(name+'-roles-routes.png')).as_posix()})\n\n"
  for site,branch in row['mid_program']['branches'].items():text+=f"- {site}: Mid branch → transfer territory → {'shared primary preparation' if branch['mode']=='approach_handoff' else 'separate entry preparation'} → objective. Purpose: {branch['purpose']}.\n"
  if row['handoff_junctions']:
   text+='\nPhysical handoff evidence:\n\n'
   for site,j in row['handoff_junctions'].items():text+=f"- {site}: main arrives through `{j['primary_arrival']}`, Mid through `{j['mid_arrival']}`, in actual space `{j['space']}`. Both use final site opening `{j['shared_site_entry']}`; one final entry.\n"
  text+=f"\nUnrestricted routes and sampled rays: [image]({(out/(name+'-unrestricted')/'movement-sightlines.png').as_posix()}). Compact preference achieved: {row['compactness']['achieved']}.\n\n| Route | Complete ordered HU | Unrestricted HU | Connector subset HU |\n|---|---|---|---|\n"
  for r in row['compactness']['route_distances']:
   if r['route'] in ('T-A-main','T-B-main','T-A-secondary','T-B-secondary','CT-rotate'):text+=f"| {r['route']} | {r['complete_ordered_HU']:.0f} | {r['unrestricted_shortest_HU']:.0f} | {r['connector_only_HU']:.0f} |\n"
 text+='''
## Acceptance versus quality

Physical connectivity, clearance, actual aperture widths/interference, undeclared openings and unintended Mid bypass checks remain enabled. Request checks now allow only an explicitly declared approach handoff, instead of universally forbidding a merge. Transfer/entry support cannot collapse into central Mid. Street is actual shared architecture, not two labels on separate rooms. Independent main commitments and defender access remain checked. Final ingress-sector uniqueness is enforced for separate entries; shared-entry handoffs require distinct arrival openings and are explicitly counted as one final entry.

79 regression/feature tests passed. The affected Mid tests were rerun after the last shared street-band change. New tests cover real shared street geometry, indirect branches, physical handoff arrivals, undeclared handoff rejection, stable strategic choices and absent-Mid conflicts. Testing verifies behavior; it does not certify visual quality. All candidate hashes reproduce in-process; the linked-courts candidate also matches a separate frozen-source process replay (`439115a65f1466060e81da7787dcb04f1302df394e68bae62f2e8980be510e15`).

**Remaining weaknesses:** long perimeter/rear travel, repetitive broad site interiors and angular turn expansions remain. The orthogonal 6×6 reservation graph is larger, not eliminated. Transfer territories still use a limited sequential construction; arbitrary multi-purpose Mid networks, multiple handoffs, pressure-only connectors, vertical Catwalk/underpass relationships and overlapping floors are unsupported. The street and linked-court candidates vary connectivity/approach organization, but they do not establish broad strategic diversity or professional Counter-Strike quality. No calibrated timings, utility, control or balance. Mid is still required to provide access toward both sites in this version; weak/optional Mid behavior is not yet supported. No numeric quality certification.

## Reproduction

From HammerGPT, use fresh output paths:

```powershell
.tools/training/Scripts/python.exe output/distributed-mid-001/r4/street/source/map_layout.py --spec output/distributed-mid-001/street-spec.json --seed 996031 --output output/distributed-mid-replay-street --attempt-limit 4
.tools/training/Scripts/python.exe output/distributed-mid-001/r4/courts-handoff/source/map_layout.py --spec output/distributed-mid-001/courts-handoff-spec.json --seed 996073 --output output/distributed-mid-replay-courts --attempt-limit 4
.tools/training/Scripts/python.exe output/distributed-mid-001/r4/matched/source/map_layout.py --spec output/distributed-mid-001/matched-spec.json --seed 985731 --output output/distributed-mid-replay-base --attempt-limit 4
```

Stopped for visual review. No Stage 4 or engine geometry.
'''
 (root/'review.md').write_text(text,encoding='utf-8');policy=read(ROOT/'generation-policy.json');policy.update(stage_3_experiment_status='distributed_mid_review_candidates',stage_3_review='output/distributed-mid-001/review.md',stage_4_authorized=False,geometry_paused=True);(ROOT/'generation-policy.json').write_text(json.dumps(policy,indent=2))
 print(json.dumps([dict(name=r['name'],seed=r['seed'],handoff=r['handoff_sites'],compact=r['compactness']['achieved']) for r in rows]))
if __name__=='__main__':run()
