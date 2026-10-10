# Specification to top-down image

This is a bounded, rule-based Stage 1–3 pipeline. It produces planar candidates
for review, not engine floors, grayboxes, VMAPs, timing certification or accepted
map designs. It does not invoke the learned neural layout models. The architecture
rules were authored by Codex; assembly and bounded backtracking are automatic.
No candidate-specific coordinates or repairs are used.

## Run it

From the HammerGPT repository root, using the existing training Python runtime:

```powershell
.tools\training\Scripts\python.exe map_layout.py --spec config/map-spec-compact.json --output output/my-map --seed 271828 --attempt-limit 4
```

The output directory must be new. Maximum attempt limit is 20, default 6. A run
stops at the first physical AND request-adherence pass. Soft preferences are not
acceptance gates. The base seed is in the specification or supplied via `--seed`;
if absent, it is generated and saved. Attempt seeds are base seed + attempt index.
Unspecified enum choices resolve once per run and are logged, not changed on each
rejection. There is no P04-only search or four-candidate quota.

Successful output: `clean.png`, `encounters.png`, `composition.json`,
`validation.json`, coordinate-free `strategic-blueprint.json`, original/normalized/
resolved specifications, configuration, generator and validator versions, source
snapshots/hashes, runtime versions, decisions, each attempt seed and rejection.
Failure output: `failure-report.json`, `diagnostic.png` and complete attempt history.
Construction diagnostics show rejected role placements, never claim playable floor.
Invalid or unsupported requests fail before generation and receive a diagnostic.

Replay without invoking a language model, using the saved source snapshot:

```powershell
.tools\training\Scripts\python.exe output/specification-to-image-003/compact/source/map_layout.py --spec output/specification-to-image-003/compact/specification.json --output output/replay-compact --attempt-limit 4
```

Compare the `composition_sha256` in both summaries. Preserve the recorded runtime
versions for reliable Shapely/networkx numerical behavior. Each accepted candidate
is also regenerated from scratch within the run and full composition/decision
hashes compared. PNG binary identity is not the reproducibility contract.

## Validated design specification

`map_design_spec.py` is the authoritative local validator. The generated JSON
schema is saved with the demonstrations. Unknown fields, unsupported enum values,
bad numeric types and explicit conflicts are errors. Partial JSON is supported;
missing numeric values use documented defaults, enum values use `auto`. The schema
for the LLM requires all fields; interpretation is checked locally afterward.

| Section / control | Supported values | Actual effect |
|---|---|---|
| gameplay.sites | 2 | Two objective complexes; other counts rejected |
| gameplay.mid | absent / contested / auto | No shared middle, or a physical contest courtyard with independent team approaches and site connectors |
| gameplay.main_approaches | independent | Main approaches share deployment, then stay physically separate before sites |
| gameplay.secondary_access | local / mid / auto | Local alternate entry loops, or Mid routes entering both sites on different external faces |
| gameplay.defender_rotation | rear / central / auto | Ordered route through rear deployment, or via contested Mid; central rotation is control-dependent |
| gameplay.site_commitment | immediate / staged / mixed / auto | Immediate has no investment prerequisite; staged adds a physical investment room and threshold before staging; mixed applies it to B |
| architecture.site_setting | courtyard / interior / mixed / auto | Open courts with attached building corners, versus full-height interior partitions and vestibule thresholds; mixed makes A court/B interior |
| architecture.site_separation | adjacent / separated / auto | Flank roles at inner versus outer reservations; physical site separation checked (adjacent <=2400 HU, separated >=2300 HU) |
| hard_constraints.max_extent_HU | 3584–6400; default 5120 | Bounds the envelope and available arrangement span |
| hard_constraints.minimum_door_width_HU | 96–192; default 128 | Actual clear aperture width requirement; default physical openings are at least 128 HU |
| hard_constraints.maximum_main_route_HU | null or 256–12800 | Optional hard limit on each complete, ordered primary attack route; never a timing substitute |
| soft_preferences.compactness | 0–1; default .7 | Controls reservation span; measured occupancy recorded, no quality score |
| soft_preferences.sightline_breaks | 0–1; default .8 | Depth of attached receiving/deployment frontages; sampled rays shown |
| soft_preferences.asymmetry | 0–1; default .7 | Probability of independently sampled site depths; no guaranteed visual diversity |
| seed | null or integer 0..2^63-1 | Reproducible assembly; CLI override is explicit and saved |

Gameplay requirements are coordinate-free route purposes, not generic connections
or blueprint IDs. A site has primary/secondary approach, staging, actual entrance
sectors, objective and holding area, receiving/fallback and reverse retake paths.
Spawns have multiple deployment assignments rather than one terminal connector.
P04 is an example of no-Mid commitments; P01 is an example of contested Mid. Neither
plan or authored layout is imported by this composer.

Supported combinations: absent Mid + local secondary + rear rotation; contested
Mid + secondary access to BOTH sites + rear or central rotation. Every combination
can request any of the three site settings, separation modes and commitment modes.
This is syntactic/search support, not a promise a bounded search will succeed.
Absent Mid + Mid secondaries/central rotation is a conflict. Contested Mid with
local-only secondaries is unsupported in this version and rejected explicitly.
Explicit Mid secondaries or central rotation resolves unspecified Mid to contested.
Explicit local-only secondaries resolves unspecified Mid to absent. Other `auto`
choices use the seed and are saved.

Architectural settings are implemented preferences with measurable evidence, not
semantic tags: the interior demo adds two actual vestibules and full-height
partitions, altering clear thresholds and sightlines. Courtyard roofs/outdoor
lighting cannot be verified in 2D; no claim of implemented 3D roofs is made.

Unsupported: arbitrary objective counts, hostage modes, split spawns, vertical
bridges/stairs, moving/secret doors, precise calibrated timings, arbitrary room or
route counts, named theme assets, exact reference-map reproduction and arbitrary
graph requests. Unknown JSON controls are rejected; the LLM must list unsupported
natural-language features rather than quietly dropping them.

## Joint architectural assembly

The scaffold is a nonuniform 5x5 arrangement of building reservations. It is not
emitted as a grid of playable rooms. Role positions, main approaches, defense,
Mid and local alternates are chosen together, with bounded backtracking over earlier
path selections and placement. The path budget is 1600 branches per placement,
32 placements per candidate. Site and deployment placements are reconsidered when
later circulation cannot be accommodated. The path proposal uses only adjacent
physical reservations with shared frontages.

After joint selection, occupied space is allocated by purpose: 288-HU continuous
aisles, 480-HU staging/receiving rooms and 576-HU deployment/Mid spaces. Unoccupied
reservation areas become inaccessible building mass. Non-decision circulation
parcels merge into continuous galleries; unnecessary internal grid-boundary doors
are removed. Local objective architecture and actual apertures adapt to neighbors
and full-height partitions. If local openings cannot clear the requested width,
the attempt fails; the next seed repeats shared rules, never manual repair.

Reference-informed motifs are qualitative, not measured/trained distribution claims:
Dust2's threshold/forecourt, Cache's different local objective faces, Train's attached
buildings and receiving, and Cobblestone's investment territory. Previously inspected
reference images remain under `output/annotations/*reviewed*` and
`output/annotations/dust2-boundaries-v4`. No new neural-model training is claimed.

The procedure still has a rectangular reservation scaffold and opposing deployment
bias. It is not an unrestricted architecture generator. Site-depth/separation,
circulation selection, Mid connectivity and local partitions can vary, but this
milestone does not establish broad visual diversity or professional CS2 quality.

## Validation: validity, adherence and diversity are separate

Universal physical checks retain the existing exact space/mass/opening compiler,
geometry-derived navigation and boundary audit. They require nonoverlapping valid
spaces, a single walkable component, all intended routes after provisional player
erosion, actual door width across wall depth matching the nominal aperture, no
sampled undeclared connections, and playable role/holding points. Scale remains
32 HU per plan unit, provisional player width 32 HU, full-height 160 HU, low cover
48 HU and walls 25.6 HU. No runtime headroom, jumping or full 3D collision checks.

Adherence checks include independent main commitments, actual differing primary/
secondary site-complex doors, investment when requested, local interior partitions,
requested distance/width/extent bounds and correct Mid connectivity. The actual
door crossed is checked against the full physical route; graph sectors alone do
not establish alternate entry. Interior clearing thresholds are distinguished from
external site-complex ingress. Tactical equivalence beyond ingress/territory remains
unverified: information, utility and defender reactions need a richer model/playtest.

No-Mid layouts must have no T-to-CT access when both site complexes are blocked.
The shortest rear receiving rotation must traverse rear deployment. An attack-side
rotation via captured sites is still physically possible and is not falsely banned.
Mid layouts allow a site-free route THROUGH the declared contest, but blocking
both sites plus Mid must eliminate it. Both teams must independently reach Mid;
Mid secondary connectors stay apart from the primary commitments before each site.
The distance ratio has a warning at 1.6 and a feasibility rejection at 2.5; these are
explicit provisional design assumptions, not calibrated contest timing.

The old 1536-HU cap applied to external connectors in the frozen P04 prototype.
This composer allocates continuous architectural circulation instead of external
spawn lanes, so it does not inherit that universal cap. Its replacement is an
optional user hard limit on the COMPLETE main route, with ordered and unrestricted
shortest route distances reported separately. No hidden recovery-area minimum or
retake-angle budget is inherited. Existing P04 results and assumptions remain frozen.

Route overlays show declared traversal through physical architectural waypoints,
not an assertion that players choose those routes. Shortest travel may differ and
is reported; territory/first-contact/timing remains unresolved. Standing ray samples
are diagnostics, not exhaustive sightline or encounter-control validation.

Diversity is assessed separately in the demonstration report. No-Mid versus Mid
is a real central connectivity change. Courtyard versus interior with the same
seed is a controlled local architecture change, NOT another macro strategy family.
Passing tests check implementation and regressions, not layout quality.

## Optional natural language

```powershell
$env:OPENAI_API_KEY = 'your API credential'
.tools\training\Scripts\python.exe map_layout.py --prompt "A compact two-site map without Mid, with open courtyards and separate main approaches" --model YOUR_MODEL --output output/prompt-map --seed 271828 --attempt-limit 4
```

Alternatively use `--prompt-file request.txt`. Do not store the API key in the repo.
`map_layout.interpret` is a real LLM adapter using the Responses endpoint and strict
schema output, following [official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
It requests unsupported-feature reporting, checks refusal/incomplete output,
revalidates the specification locally and never uses a keyword fallback. Model is
explicit via `--model` or `OPENAI_MODEL`; API availability/schema support must be
appropriate for that model. `store:false` is sent. Credentials are not logged.

No API key/model access was available in the implementation environment. Direct JSON
is demonstrated end-to-end. The adapter is tested with injected structured responses,
refusal and unsupported requests, but a live language-interpretation request has
NOT been demonstrated. Enable it with an API credential and accessible Responses
model supporting Structured Outputs. This is bounded language interpretation into
the documented controls, not unrestricted understanding or map invention.

## Evidence and history

Final bounded demonstrations: `output/specification-to-image-003` (seed 271828,
up to four attempts each; all three pass first attempt). Read its report and inspect
the images. Earlier implementation rounds `output/spec-layout-demo-r1` through
`r5` and `spec-layout-demo-final` retain failures and evolving source snapshots.
The early cellular render was rejected during internal review; the initial rotation
check incorrectly banned all alternative routes, and the initial Mid bypass check
failed to remove sites. Those implementation errors were fixed without relaxing
the intended physical checks. Interior frontage splitting was then fixed in shared
rules, and actual route ingress checking prompted explicit architectural traversal
waypoints. All prior proposals remain available; no passing test count is used as
proof that the final architecture is good.

The completed frozen P04 search and authored compositions are unchanged regression
evidence. No more P04-only seeds are generated by this work. Stage 4 stays paused.
