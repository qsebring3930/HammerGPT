"""Summarize existing attempt records; never generate or repair architecture."""
import json
import platform
from pathlib import Path
import PIL
import numpy
import shapely
from PIL import Image
from playable_composition import compile_composition
from p04_comparison_round import render,frozen_hashes,REVIEW as AUTHORED_REVIEW
from procedural_p04 import ROOT

OUT=ROOT/'output/p04-procedural-001'

def read(path):return json.loads(path.read_text())
def draw_record(revision,seed,bounds,scale):
    folder=OUT/revision/f'seed-{seed}';p=read(folder/'composition.json');v=read(folder/'validation.json')
    display=dict(p);label='STRUCTURAL PASS — review pending' if v['status']=='accepted_for_review' else 'REJECTED — missing required short connections'
    if revision=='r1':label='LONG LANES — rejected by user'
    display['display_title']=f'Seed {seed} / {revision} / {label}'
    return render(display,compile_composition(p),v,seed,bounds,False,scale)

def main():
    seeds=[104,208,312,416];final='r3';summary=read(OUT/final/'summary.json')
    cfg=read(OUT/final/'configuration.json');bounds=(0,0,*cfg['world']);scale=summary['common_pixels_per_plan_unit']
    sheet=Image.new('RGB',(3600,3300),'#101923')
    for i,seed in enumerate(seeds):sheet.paste(draw_record(final,seed,bounds,scale),((i%2)*1800,(i//2)*1650))
    sheet.save(OUT/final/'review-all-four-common-scale.png')
    comparison=Image.new('RGB',(3600,1650),'#101923');same_bounds=(0,0,220,200)
    comparison.paste(draw_record('r1',416,same_bounds,6.25),(0,0));comparison.paste(draw_record('r3',416,same_bounds,6.25),(1800,0))
    comparison.save(OUT/final/'seed-416-before-after-same-scale.png')
    decisions=[];statuses=[];history=[];roads=[]
    for seed in seeds:
        p=read(OUT/final/f'seed-{seed}/composition.json');v=read(OUT/final/f'seed-{seed}/validation.json');macro=p['decision_log'][0]['choices'];local=p['decision_log'][1]['choices']
        decisions.append(f"| {seed} | {macro['axis']} | {macro['B_facing_relationship']} | A {macro['depth_offsets']['A']:+d}, B {macro['depth_offsets']['B']:+d} | {macro['routing_order']} | A {local['A']['gallery_face']}, B {local['B']['gallery_face']} |")
        placed=[d for d in p['decision_log'] if d['stage']=='circulation' and d['status']=='placed']
        widths=v.get('openings',[])
        short={'104':'T approaches fit; CT requires long detours, so both CT connectors omitted.',
               '208':'Neither deployment can reach both sites under the cap; four connectors omitted.',
               '312':'CT connections fit; T needs long approaches, so both T connectors omitted.',
               '416':'All 19 ordered routes, player clearance, 18 apertures, bypass and P04 structural gates pass.'}[str(seed)]
        statuses.append(f"| {seed} | {'Pass for review' if v['status']=='accepted_for_review' else 'Reject'} | {len(placed)}/4 | {short} |")
        if seed==416:
            before=read(OUT/f'r1/seed-{seed}/decisions.json')
            for now in placed:
                old=next(x for x in before if x['stage']=='circulation' and x['team']==now['team'] and x['site']==now['site'])
                reduction=1-now['length_plan_units']/old['length_plan_units']
                roads.append(f"| {now['team']} → {now['site']} frontage | {old['length_plan_units']*32:.0f} | {now['length_plan_units']*32:.0f} | {reduction:.0%} |")
    for revision in ('r1','r2','r3'):
        s=read(OUT/revision/'summary.json');accepted=sum(x['status']=='accepted_for_review' for x in s['attempts'])
        history.append(f'| {revision} | 4 | {accepted} | {4-accepted} |')
    v=read(OUT/final/'seed-416/validation.json');r=v['defender_rotation']
    arrivals='\n'.join(f"| {x['site']} | {x['T_to_encounter_HU']:.0f} | {x['CT_ordered_to_same_encounter_HU']:.0f} | {x['CT_to_hold_HU']:.0f} | {x['T_to_main_entry_HU']:.0f} |" for x in v['arrival_distance_checks'])
    report=f'''# Automatic P04 experiment — short-lane correction and final batch review

Exactly four predeclared seeds; no replacements, candidate-specific coordinate edits
or manual repairs. Shared-rule revisions r1/r2/r3 and all 12 attempts are retained.
Stage 4, graybox and engine geometry remain paused. Original authored outputs are untouched.

## Shorter spawn connections

After the user rejected the first batch's long spawn lanes, placement moved from
map-edge spawns to measured frontage proximity. Complexes are packed closer, deployments
are selected from a logged search using actual disjoint route costs, and connectors
over 48 plan units (1,536 HU) are omitted and make the candidate fail. The cap is
a declared experiment assumption, not a substituted P04 timing requirement.
It has not been increased to pass a failed proposal.

Seed 416 is the complete corrected candidate. Same seed, changed shared procedure:

| Connection, measured along generated lane | r1 HU | r3 HU | Reduction |
|---|---:|---:|---:|
{chr(10).join(roads)}

The before/after image uses identical 6.25 pixels per plan unit. The change is
architectural, not a zoom, stretch or manual candidate adjustment. These distances
exclude local movement inside the site complexes; full route lengths are separately
reported in validation.json. Shorter connection streets do not establish good gameplay.

## Final four seeds at a common scale

The final review sheet uses {scale:.6f} pixels per plan unit and identical 512 HU
bars / 32 HU player markers. Missing connections in rejected plans are genuine
failures, not intended isolation. Original rejected connector paths remain in decisions.json.

| Seed | Gate result | Short connectors emitted | Reason |
|---|---|---:|---|
{chr(10).join(statuses)}

## Short decision log

| Seed | Overall axis | B relative facing | Independent depth offsets | Road reservation order | Local gallery faces |
|---|---|---|---|---|---|
{chr(10).join(decisions)}

Macro and A/B local choices use independent random streams. The procedure assembles
local staging, investment, objective, side frontage and receiving rules, reserves
inaccessible compound interiors jointly, chooses deployments, physically routes
circulation and places actual shared-boundary apertures. The authored 001–004 layouts
are not loaded into generation. They remain regression examples.

## Complete candidate checks

Seed 416: one walkable component, 19/19 ordered routes connected, all 19 retained
after provisional player-footprint erosion. 18/18 apertures have nominal = actual
clear width (128–160 HU). No sampled undeclared opening; blocking both objectives
disconnects T from CT circulation. Main/alternate sectors differ by 90°, and
retake ingress opposes primary by 180° at both sites. B primary traverses its
investment space. Attacker commitments share no opening. There is no introduced Mid.

Shortest hold-to-hold rotation crosses rear deployment: {r['shortest_path']['length']*32:.0f} HU.
Avoiding CT deployment via attacker territory costs {r['CT_avoiding_path']['length']*32:.0f} HU,
an advantage of {r['rear_advantage_HU']:.0f} HU for the rear path. That is geometry,
not verified safety, timing, retake strength or balance.

| Site | T ordered to encounter HU | CT ordered to same encounter HU | CT to hold HU | T to main entry HU |
|---|---:|---:|---:|---:|
{arrivals}

Both same-encounter comparisons retain an early-contest distance conflict. CT's
ordered route includes initial assignment before advancing to the encounter waypoint.
Visibility can project a fight without occupying that marker, but does not resolve
the timing intention. No distances are converted to seconds. All timing claims,
information, utility, retreat and retake safety remain unresolved.

## Attempts and recurring weaknesses

| Revision | Proposals | Structural passes | Rejections |
|---|---:|---:|---:|
{chr(10).join(history)}

r1 produced connected architecture but excessively long independent streets. r2
kept a hard cap and rejected all proposals; overly padded reservations and clamped
packing exposed procedure limitations. r3 corrected those shared rules and replayed
the same seeds. The perpendicular-facing families still cannot reliably compose
short disjoint approaches with this limited search, so their failures are preserved.

Recurring weaknesses: box-shaped local sequences, limited plant/cover vocabulary,
constant-width street connectors, arrival-distance conflicts, and incomplete support
for perpendicular-facing compounds. Search is bounded and reservation order greedy;
failure is evidence about this procedure, not proof an arrangement is impossible.
The parallel-facing case is complete, but one case is not a diversity milestone.

## Command, provenance and reproduction

From the repository, to replay the final procedure into a new revision:

```powershell
.tools\\training\\Scripts\\python.exe procedural_p04.py --config config\\p04-procedural-v3.json --seeds config\\p04-procedural-seeds.json --revision replay
```

Seed/configuration files, source snapshots/hashes, all decisions, rejected lane
proposals, validation JSON and images are saved. Existing revision names cannot
be overwritten. attempts.jsonl includes every batch proposal; startup-errors.json
records the initial syntax failure before any candidate was generated.

Every final seed was regenerated twice from scratch: entire composition and
decision log hashes match, 4/4. The same result requires the same rules, config
and dependencies, not just the seed alone. An independent regression regenerated
416 and matched its recorded hash. 102 selected tests passed, including original
rotation/entry failure cases and the new lane-cap and determinism checks.
Test success is implementation evidence, not gameplay or visual acceptance.

See the repository's p04-procedural-generator.md for rules, qualitative inspected
reference provenance, supported combinations and limitations. This is a minimal
automatic spatial procedure, not new neural-model training. Its rules were authored
by Codex; individual candidate architecture was selected by the seeded procedure.
Stop for review here; no further batch or engine geometry is produced.
'''
    (OUT/final/'review.md').write_text(report,encoding='utf-8')
    (OUT/'review.md').write_text('Final report: [r3/review.md](r3/review.md). Rules: ../../p04-procedural-generator.md. All revisions and startup failure retained.\n',encoding='utf-8')
    versions=dict(python=platform.python_version(),numpy=numpy.__version__,shapely=shapely.__version__,pillow=PIL.__version__)
    (OUT/final/'environment.json').write_text(json.dumps(versions,indent=2))
    assert frozen_hashes()==read(AUTHORED_REVIEW/'frozen-001-002.json'),'Authored outputs changed'
    print(json.dumps(dict(final_revision=final,tests_passed=102,reproduced_seeds=4,passed_seed=416,rejected_seeds=[104,208,312],spawn_connectors_final_HU=[1088,1344,1216,1280],stage4_paused=True),indent=2))

if __name__=='__main__':main()
