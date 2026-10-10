# Minimal automatic P04 architectural experiment

Stage 4 stays paused. This is a limited Stage 3 spatial procedure, not a trained
model, a complete Counter-Strike generator, or proof of gameplay quality.

## Generate and reproduce

From the HammerGPT repository in PowerShell:

```powershell
.tools\training\Scripts\python.exe procedural_p04.py --config config\p04-procedural-v3.json --seeds config\p04-procedural-seeds.json --revision replay
```

Use a new revision name for each replay; an existing revision cannot be overwritten.
The command regenerates exactly the four declared seeds, not a filtered success set.
Existing delivered revisions are `r1`, `r2`, `r3` under `output/p04-procedural-001`.
The full input configuration, source hashes/snapshots and decision logs are recorded
per revision. Composition hashes include the entire decision log. The same seed,
configuration, rule implementation and dependencies reproduce the same composition.
Changing rules or configuration intentionally changes the result.

The final batch regenerated each composition twice from scratch and compared
canonical SHA-256 digests. An independent regression test also regenerates seed 416.
This is composition reproducibility, not a claim of bit-identical PNGs across
Pillow versions or identical navigation numbers across dependency changes.

## Overall choices versus local choices

Separate deterministic random streams derive from the seed plus `macro`, `local-A`
and `local-B` keys. The procedure never loads 001–004's composition data or calls
their authored builders. The shared renderer is reused; its generic footer's
“architecture authored” refers to the vocabulary/rules, not manual candidate edits.

Overall arrangement:

1. Choose the axis along which commitments advance, relative B facing (parallel,
   inward perpendicular, outward perpendicular), and independent site depth offsets.
2. Pack the actual complex extents across that axis with a sampled separation gap.
   Reserve each compound's playable architecture and interior inaccessible masses
   together; the remaining envelope is solid. World bounds constrain packing.
3. Search a deterministic shortlist of potential deployment frontages. Preview
   actual, disjoint physical connectors to both appropriate site sockets. Prefer
   feasible short connections and minimize worst connection plus total length.
   Both unsuccessful preview placements and the selected one are logged.
4. Route the four final assignment connections in a seeded order, avoiding other
   compounds, deployments and already placed circulation. Construct their swept
   playable cross-sections, boundary walls and real shared-frontage openings.
5. Reject a connector longer than **48 plan units = 1,536 HU**, instead of emitting
   an enormous detour. An absent connector makes that whole candidate fail.

The length cap is a new experiment assumption introduced after the user's long-lane
feedback. It is not a universal P04 requirement, timing estimate or calibrated
balance criterion. Failed placements are not repaired, replaced or resampled.

Local architecture is assembled before global placement:

- A: staging/encounter frontage, primary objective entry, local side frontage,
  attached site wing, plant bay, low cover and rear receiving architecture.
- B: those phases plus separately acquired investment territory and an execute
  threshold; its local alternative bypasses that primary investment to another
  clearing sector, not to CT circulation.
- Choose frontage depth, court proportions, west/east alternate face, near-entry
  versus deeper plant-dividing building wing, recessed versus open staging, and
  receiving depth. A longer local unloading approach narrows through an architectural
  threshold rather than existing as a generic perimeter graph edge.
- Place main, side and rear apertures on actual shared boundaries. Anchors describe
  roles inside those spaces, never patches of floor per semantic node.
- Allocate fallback and regather beside the rear entry inside receiving circulation.
  Original prototype area/distance assumptions remain archived in 001/002;
  they are not imposed on new assemblies or retrospectively cleared.

These are local architectural rules assembled into new overall organizations,
not fixed copies of whole authored layouts. The procedure remains restrictive:
it currently combines two orthogonal compound vocabularies and independent streets.

## Reference-informed rule provenance

These motifs are qualitative interpretations of inspected NAV overviews, not
automatically extracted measurements or additional neural training:

| Inspected reference | Rule informed |
|---|---|
| `output/annotations/dust2-boundaries-v4/overview.png` | Narrower approach threshold opening into encounter/forecourt space |
| `output/annotations/cache-reviewed-v1/overview.png` | Local entrances on different objective faces and entry-clearing sectors |
| `output/annotations/train-reviewed-v1/overview.png` | Building-attached full-height divisions of objective space and rear receiving |
| `output/annotations/cobblestone-reviewed-v1/overview.png` | Separating B arrival, encounter, territory acquisition and execute |

001's lessons informed integrated staging and receiving annotations, declared cover
heights, actual apertures and attached architecture. The authored layouts serve as
regression inputs, not generation templates. Their original output files remain intact.

## Supported combinations and limits

The rule vocabulary syntactically supports two overall axes × three relative B
facings, independent depth offsets and local architectural choices. Syntactic support
does not imply that every combination can be packed or connected under the short-lane
cap. The delivered batch demonstrates one complete parallel-facing assembly; its
perpendicular assemblies remain rejected when short disjoint connections cannot fit.
Those failures are retained, not quietly replaced by parallel templates.

- Only unchanged P04 is supported (strategy hash is checked). No classical Mid.
- Ground level only; orthogonal static spaces and flat openings. No multi-floor,
  curved, diagonal, door, jump, boost, crowd, headroom or utility model.
- Current deployment search is a bounded shortlist, not an exhaustive optimizer.
  Greedy road reservation can block a later route. A rejection means this procedure
  failed to realize the arrangement, not that no possible architecture could do so.
- Assignment streets are still simple, constant-width circulation. The cap removes
  the worst detours; it does not supply rich street combat architecture.
- Local compound vocabulary can still produce repeating room sequences and sparse
  cover. Staging mass placement is limited, and proportion/visibility quality needs review.
- No optimization for node, edge or cycle counts; they are not used as quality scores.

## Checks and interpretation

Use the existing playable-space compiler and derived navigation. Verify valid
nonoverlapping spaces, a connected walkable component, all 19 ordered routes,
32×32 HU provisional player-footprint erosion, measured clear aperture width across
wall depth, and sampled undeclared passable boundaries. Block both objective courts
and reject site-free attacker access to CT deployment.

Check actual main/alternate ingress sectors, 180° opposite rear retake sector,
B primary investment, separate attacker commitments, and shortest hold-to-hold
defender rotation through rear deployment. Reject a shortest non-rear shortcut.
Diagnostic weak rotation margin and arrival-distance comparisons remain warnings.
Main/alternate tactical distinction is supported by measured entry sectors only;
timing, information, engagement range, utility and retreat safety remain unresolved.

CT's ordered encounter path includes initial site assignment before advancing to
the same encounter marker as T. Compare that distance explicitly. Also report
CT-to-hold and T-to-entry separately, without substituting different destinations
to manufacture an arrival pass. Being able to see an encounter without occupying
its marker is a separate static visibility observation, not verified timing.

`accepted_for_review` means the declared physical/structural gate passed. It does
not mean visually accepted, calibrated, balanced, or ready for engine generation.

## Attempt history

- Startup syntax failure occurred before any seed was generated; recorded separately.
- r1: four proposals, two structural passes. Rejected by the user for long spawn lanes.
  104 had a shorter non-rear rotation; 208's alternate entry collapsed onto B main.
- r2: shared compact packing, measured deployment search, length cap and encounter-side
  gallery fork. All four rejected. Padded reservations exaggerated clearance detours;
  clamped world packing also overlapped in one case.
- r3: all four seeds replayed after removing authoring padding from routing reservations,
  shortening clearance collars, expanding the common packing envelope and broadening
  deployment search. Cap unchanged. One complete candidate, three rejected; all reproduce.

`attempts.jsonl` is append-only. Each proposal, rejected connector path, preview,
source snapshot, clean plan, validation and composition digest is preserved.
No per-candidate coordinate corrections, seed filtering or manual repairs were used.

Stop after this batch for review. No Stage 4, VMAP, engine mesh, graybox or additional
unreviewed generation is authorized by this experiment.
