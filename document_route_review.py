"""Document measurements from the frozen focused demonstration; no generation."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def run():
 root=ROOT/'output/route-composition-001';review=root/'review';rows=read(review/'measurements.json')
 text='''# Route composition review — Stage 4 paused

This is an automatic seeded shared-rule experiment, not neural training or engine geometry. Candidates remain visually unaccepted. Existing outputs and the matched before candidate are unchanged. Three seeds, four-attempt maximum per seed, three first-attempt physical/request passes, no rejected generation attempts and no candidate-specific edits. Soft compactness fails for 962331; it was retained and reported. Test failures during development were implementation regressions, not hidden generation attempts: missing staged-investment annotation was corrected in the shared code; legacy schema/byte-equality tests were replaced by backward-compatible behavior checks. 62 regression tests and 7 new purpose/geometry tests pass. Passing tests does not establish architectural quality.

## Audit: both semantics and spatial flattening

The earlier coordinate-free contract had deployment, staging, secondary access, receiving and retreat. Main travel was reduced to a T→staging→site intent link; intermediate main, split, execute and contest purposes were missing. Meanwhile the spatial network already contained several intermediate reservations, but important-node selection and the straight-run gallery merge flattened most of them into continuous axis-aligned travel. The 5×5 orthogonal reservation search, fixed site-facing arrangement and nominal routing centres still bias the result. Merely adding labels would not fix that.

The contract now defines staging, main approach, potential first contest, connector, split point, execute preparation, flank, fallback and rotation junction. Actual support bindings are many-to-many: a main spans multiple connected spaces; staging and execute share a court; connector and flank share secondary territory. Callout text is metadata and does not create rooms. An opening-graph support check rejects empty/disconnected role supports. First contest currently shares objective-entry support, rather than adding a mandatory fight room. Its timing and control are unverified. This is a limited operational role system, not a new unconstrained strategic planner: current two-site approach and rear-rotation relationships remain.

## Shared architectural changes

Seeded route profiles select a straight frontage street, attached court-edge building, one-sided oblique building frontage, or circulation around an inaccessible building. Selected intermediate reservations become architectural assemblies before remaining gallery runs merge. Building-wrap has four connected architectural bands and actual shared-boundary openings; roles span them. Court profiles subtract a coherent building footprint from playable court space; the compiler preserves holes. Ports remain on actual boundaries. These replace selected gallery segments, not all segments, and leave useful straights intact.

Complexity is deliberately coarse: `soft_preferences.route_complexity` defaults to 0.5. Below 0.25, intermediate profiles remain frontage streets; at/above 0.25, local assemblies are available; at/above 0.7, compatible local secondary branches split one reservation earlier. It does not maximize room count, create mandatory extra rooms, or promise monotonic density. Mid remains independently absent/contested. Demonstrations use the unchanged input specification and its new backwards-compatible default 0.5. A separate test confirms high complexity changes actual branch connectivity.

## Provenance and confidence

Radar library R09 (Screenshot378), R14 (Screenshot594), R17 (Screenshot93) and R18 (Screenshot99) inform serial transitions, offset courts, coherent oblique frontage and interlocked circulation. Measurements are image ratios without calibrated scale. NAV dust2-space-0 and train-space-1 support circulation around exclusions; cache-space-4 supports a direction change; cache-space-1 supports retaining straight circulation. Conservative original/aggregated/pattern overlays remain in `output/nav-radar-integration-001/references-r4`; radar source overlays remain in `output/radar-reference-001`. Pattern IDs, source hashes and rule versions are frozen in each candidate's configuration/source snapshot. These are observed movement/composition patterns; the band partitions, authored dimensions, profile choices and semantic interpretation are generation choices. No NAV area was treated as a room, no overlapping floors connected from appearance, and no NAV timing or heights inferred. Exact prototype dimensions are authored at provisional 32 HU per plan unit.

## Matched and new-seed results

![Matched before/after](review/matched.png)

![New seeds at the same scale](review/new-seeds.png)

| Candidate | A intermediate arrangement | B intermediate arrangement | Physical/request gates | Compact preference |
|---|---|---|---|---|
| 927611 before | merged gallery | frontage bank with passing bay | pass/pass | achieved |
| 927611 after | connected circulation around building | one-sided oblique court | pass/pass | achieved |
| 962117 | oblique court | frontage street | pass/pass | achieved |
| 962331 | court edge | frontage street | pass/pass | missed rear rotation target |

927611 and 962117 repeat the folded macro scaffold. Their local sequences differ meaningfully but do not establish overall diversity. 962331 uses the flank placement with A west and B east, a different attacker commitment and longer rear circulation. These are reviewable procedural candidates, not proof of natural CS2 architectural quality.

## Distances and unrestricted movement

Distances below are provisional HU, rounded. Ordered routes follow declared strategic waypoints/space support; unrestricted routes use the complete clearance-eroded playable representation and can choose either approach. Main and secondary routes with identical endpoints share the same unrestricted shortest path; this is not evidence of distinct tactical choices. Connector-only distances are retained separately in validation.json, not substituted for full movement.

| Candidate | A ordered / unrestricted | B ordered / unrestricted | Rear rotation ordered / unrestricted | Sampled A / B / rotation planar ray |
|---|---|---|---|---|
'''
 for r in rows:
  table={x['route']:x for x in r['routes']};diag=read(review/(('before' if r['label'].startswith('BEFORE') else str(r['seed']))+'-unrestricted')/'planar-sightlines.json');rays=[round(x['maximum_sampled_along_route_planar_ray_HU']) for x in diag['routes']]
  pairs=[' / '.join(str(round(table[key][field])) for field in ('ordered_HU','unrestricted_HU')) for key in ('T-A-main','T-B-main','CT-rotate')]
  text+='| '+r['label']+' | '+' | '.join(pairs)+' | '+' / '.join(map(str,rays))+' |\n'
 text+='''
**Remaining regression:** the matched B oblique profile replaces the earlier bank/passing bay, increasing the sampled along-route standing ray from about 1,595 to 3,015 HU. It is physically valid but architecturally worse on that measure. A barely changes its sampled longest ray. The building-wrap introduces genuine geometric alternatives, but their strategic equivalence is unresolved: they reconnect in the same commitment and are not counted as extra strategic attack routes. No numeric CS2-quality score is used.

## Purpose, space and route overlays

Numbers identify actual architectural spaces; the keys below show all roles sharing each space. Outlines show partitions, not one new wall per semantic role. Movement overlays use unrestricted shortest routes (gold/pink attacker, blue defender) with sampled red planar rays. These rays use declared full-height boundaries and low-cover heights, sample along route tangents, and are not a proof of maximum visibility, timing, utility or engine behavior.

'''
 for seed in (927611,962117,962331):
  text+=f'### Seed {seed}\n\n![Actual spaces and role IDs](review/{seed}-roles.png)\n\n![Unrestricted movement and planar rays](review/{seed}-unrestricted/movement-sightlines.png)\n\n| Marker | Actual space | Semantic roles |\n|---|---|---|\n'
  for k in read(review/f'{seed}-role-key.json'):text+=f"| {k['number']} | {k['actual_space']} | {', '.join(k['roles'])} |\n"
  p=read(root/'after-r1'/f'seed-{seed}'/'composition.json');v=read(root/'after-r1'/f'seed-{seed}'/'validation.json')
  blueprint=['# Realized route purpose blueprint', '', 'Roles annotate support; they do not each allocate a room. First contest and flank timing are unresolved.','']
  for r in p['role_bindings']:blueprint += [f"- {r['id']}: {r['purpose']}. Actual spaces: {', '.join(r['spaces'])}."]
  blueprint+=['','Geometric building-wrap cycles reconnect within main commitment; not counted as extra tactical routes. Independent primary commitments and local secondary distinct ingress sectors are checked; defender access/fallback use rear deployment.']
  (review/f'{seed}-semantic-blueprint.md').write_text('\n'.join(blueprint),encoding='utf-8')
 text+='''
## Checks, reproducibility and limits

Connectivity, 32-HU player clearance, actual aperture width/interference, undeclared openings, independent main commitments, distinct site ingress sectors, role-support connectivity and site-free T→CT bypass gates remain enabled. Detailed widths/checks and complete/connector lengths are saved per candidate. No gate was loosened. New-role support is a connectivity check, not proof that every label has achieved tactical function. Optional Mid behavior remains regression-tested; this three-seed demonstration is no-Mid only.

All seeds reproduce in-process; matched seed 927611 additionally reproduces from its frozen source in a separate process with the identical complete composition/log hash `d508344838b3249e2d9305ab2d703c22b6ef8d74eb948918c3b329729c8fc670`. Predeclared seeds and all attempt logs/source snapshots remain preserved. Reproduction commands run from HammerGPT, using fresh output paths:

```powershell
.tools/training/Scripts/python.exe output/route-composition-001/after-r1/seed-927611/source/map_layout.py --spec output/route-composition-001/after-r1/seed-927611/input-specification.json --seed 927611 --output output/route-replay-new-927611 --attempt-limit 4
.tools/training/Scripts/python.exe output/route-composition-001/after-r1/seed-962117/source/map_layout.py --spec output/route-composition-001/after-r1/seed-962117/input-specification.json --seed 962117 --output output/route-replay-new-962117 --attempt-limit 4
.tools/training/Scripts/python.exe output/route-composition-001/after-r1/seed-962331/source/map_layout.py --spec output/route-composition-001/after-r1/seed-962331/input-specification.json --seed 962331 --output output/route-replay-new-962331 --attempt-limit 4
```

Remaining constraints: orthogonal 5×5 reservation connectivity; local assemblies fit existing parcels; nominal opening placement and approach/site formulas still regular; first contest is only objective-entry support; stage/fallback safety and strategic equivalence of local loops unverified; long rear circulation persists; navigation samples at 0.5 plan unit (16 provisional HU) with exact line-coverage smoothing. Oblique frontage does not provide free oblique overall route topology. Vertical routes, bridges, stacked floors and special traversal unsupported. No Stage 4, VMAP, meshes or graybox. Natural-language adapter remains implemented but unverified live. Physical validity, request adherence, architectural variety and visual quality are separate judgments. Stop for visual review.
'''
 # Codex previews require absolute local image paths.
 text=text.replace('](review/',']('+review.as_posix()+'/')
 (root/'review.md').write_text(text,encoding='utf-8')
 policy=read(ROOT/'generation-policy.json');policy['stage_3_experiment_status']='route_composition_focused_review';policy['stage_3_review']='output/route-composition-001/review.md';policy['stage_4_authorized']=False;policy['geometry_paused']=True;(ROOT/'generation-policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
if __name__=='__main__':run()
