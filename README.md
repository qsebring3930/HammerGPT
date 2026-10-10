# HammerGPT

Create editable CS2 Hammer geometry from conversational requests. The first milestone is a local room generator; the ChatGPT/MCP connection is still to come.

## First prototype

Requires Windows, Python 3.10+, and CS2 Workshop Tools. No Python packages or API keys are needed.

Save a map with one unrotated, unscaled, axis-aligned cube and a `light_omni2`. The generator uses the first mesh and omni light as templates, retaining their material and lighting settings. It writes a **new map** with a floor, ceiling, four walls, and one light. Dimensions describe the clear interior in Hammer units, with floor surface at Z=0.

From the repository directory in PowerShell:

```powershell
python hammergpt.py `
  --cs2 "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive" `
  --reference "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\content\csgo_addons\aitesting\maps\aitesting.vmap" `
  --output "output\my_room.vmap" `
  --width 512 --depth 512 --height 256 --thickness 16
```

Copy the new map into your addon's `maps` directory and open it in Hammer. Existing output paths are refused. The reference map is read only. Valve's `dmxconvert.exe` converts to editable text, then back to binary; another conversion checks that Valve can read the result.

This is an editor geometry test. It does not add player spawns, compile a playable map, modify an open Hammer session, or connect to ChatGPT yet. Texture coordinates inherit the reference cube's mapping and may need adjustment. Hammer visual validation is a separate check from DMX conversion.

## Verification

```powershell
python -m unittest discover -s tests -v
```

Tests check room bounds, unique identities, parser round trips, preservation of the input, and invalid dimensions. The fixture comes from the saved sandbox cube and light.

## Next milestones

1. Verify generated geometry in Hammer.
2. Extend creation tools to boxes, doorways, stairs, and entity placement, with previews and undo.
3. Expose the creation functions through MCP for Codex and ChatGPT.
4. Package a Windows companion with addon detection and guided connection setup.

## Explore installed examples

```powershell
python catalog.py --cs2 "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive"
```

This reads the installed editor zoo maps, gameplay templates, and scripting demo source maps. It creates `output/catalog.json` with entity counts, observed property names, up to three examples per class per map, and referenced assets. `output/catalog.md` is the readable summary. Use a new `--output` path for subsequent scans, or pass repeated `--map` arguments to select specific maps.

The scanner streams the converted text because zoo maps can contain hundreds of megabytes of mesh data. Source files remain untouched. Each failed source is recorded and makes the command exit with an error; successful sources are still reported. Prefabs are listed as references rather than recursively expanded. Example values are not entity defaults, and the catalog is not a complete entity schema. Full map files and local generated catalogs are excluded from Git.

## Place a prop

After scanning the catalog, append a static prop to a new map copy:

```powershell
python place_prop.py `
  --cs2 "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive" `
  --input "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\content\csgo_addons\aitesting\maps\hammergpt_room.vmap" `
  --output "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\content\csgo_addons\aitesting\maps\hammergpt_room_crate.vmap" `
  --model "models/props/de_dust/hr_dust/dust_crates/dust_crate_style_01_32x32x32.vmdl" `
  --position 216 216 0
```

Optional `--angles PITCH YAW ROLL` and `--scale NUMBER` control rotation and uniform scale. All previous objects are retained. The output path must be new, and the model must occur in the local catalog. Placement is in world coordinates using the model's authored pivot; it does not yet read model bounds or snap to floors. Verify the crate's floor contact and wall clearance in Hammer. This command creates editor entities, not live game objects.

## Analyze a reference map

```powershell
python analyze_map.py `
  --cs2 "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive" `
  --addon "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\content\csgo_addons\dust2_tournament" `
  --map "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\content\csgo_addons\dust2_tournament\maps\de_dust2_tournament.vmap" `
  --output "output\dust2-analysis.json"
```

The analyzer writes JSON with mesh bounds, all entity placements/properties, gameplay anchors, material usage, and an asset-resolution audit; a Markdown report; and an SVG top-down overview. It streams geometry arrays and applies each node's authored world transform. Child references identify entity ownership; parent offsets are not applied again. Bounding boxes are approximate spatial evidence, not detected rooms or navigable routes. Model geometry and external prefab contents are not expanded. Parent relationships restored by decompilation may differ from the original source.

Asset resolution checks addon, game/core mounts, loose compiled resources, and VPK directory entries without unpacking archives. Unresolved references need investigation and may depend on other mounts. `--text` can reuse a previously converted KeyValues2 file. The source addon is never modified. This pipeline prepares reference features; it does not train a model or automatically evaluate map balance.

## Extract recorded routes

`tools/NavExport` uses [ValveResourceFormat](https://github.com/ValveResourceFormat/ValveResourceFormat) 20.0.6980 (MIT) to parse current Source 2 NAV files. Building requires .NET 10. The development SDK, if installed locally, lives in ignored `.tools/dotnet`; packaged distribution can provide a self-contained helper later.

```powershell
dotnet run --project tools/NavExport -- `
  "C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\content\csgo_addons\dust2_tournament\maps\de_dust2.nav" `
  "output/dust2-nav.json"

python build_routes.py `
  --nav-json "output/dust2-nav.json" `
  --reference "output/dust2-reference.json" `
  --output "output/dust2-connections.json"
```

Use new output paths on subsequent runs. For the local SDK, replace `dotnet` with `& ".\.tools\dotnet\dotnet.exe"` in PowerShell.

Recorded directed NAV links are the evidence for graph edges. Region names are inferred by polygon-centroid containment in named-area bounding boxes. Strongly connected, same-label areas form regions; unknown areas remain explicit and nearby polygons do not create links. Every graph edge retains its original NAV-area witnesses. Example routes use Dijkstra with distances between polygon centers; these are not travel times or tactical recommendations. The default selects static hull 0 and omits ladders/movable NAV. The supplied NAV may predate repairs to the VMAP, so alignment checks do not establish freshness. No fine-tuning occurs in this step.

## Compare references

```powershell
python compare_maps.py `
  --map Dust2 output/dust2-reference.json output/dust2-nav.json output/dust2-connections.json `
  --map Cobblestone output/cobblestone-reference-final.json output/cobblestone-nav.json output/cobblestone-connections-final.json `
  --map Vertigo output/vertigo-reference-final.json output/vertigo-nav.json output/vertigo-connections-final.json `
  --output output/reference-comparison-final.json
```

Profiles retain source provenance, NAV-center extents and height percentiles, named-area coverage, observed prop/material palettes, and example routes. These are inputs for a future planner, not model weights or a trained generator. The spatial analyzer supports both inline mesh children and shared element references; selection-set references do not create spatial parents. Multiply parented nodes are reported rather than assigned a guessed parent.

## Propose a blockout

```powershell
python planner.py --prompt "Create a compact vertical industrial defusal map" `
  --references output/reference-comparison-planner.json `
  --output output/industrial-proposal.json
```

The offline prototype ranks references using style keywords, footprint, and height variation. It writes a JSON proposal and SVG preview. Defaults provide two sites and three attack approaches; region dimensions and connections are authored prototype rules, not learned geometry. Recorded reference routes remain separate from proposed connections. Reusable prop candidates exclude map-specific baked models. Prompt interpretation currently handles style, compactness, and verticality only; other constraints require review. No model training, API call, VMAP generation, or addon modification occurs in this command. The proposal is the intermediate contract for a future model planner and blockout generator.

## Generate open blockout geometry

`blockout.py --cs2 <installation> --reference <cube-and-light.vmap> --proposal output/industrial-proposal.json --output <new-map.vmap>` creates room platforms and straight connecting passage slabs. Raised rooms receive sloped passages clipped to room boundaries. The generator refuses existing outputs and validates mesh transforms and vertices through Valve's binary conversion roundtrip. A companion `.blockout.json` records mesh IDs and geometry decisions. This is an open geometry study without enclosing walls, spawns, objectives, or cover. Intersecting passages may add routes beyond the proposed graph; compile, NAV generation, and gameplay validation remain necessary.

Use `--connected` for the revised enclosed blockout. It builds the union of room footprints and overlapping elbow passages on a 64-unit grid, merges floor strips, and adds 256-unit walls only along the outer boundary. Passage entrances have no internal wall. Shared elevation bands around the raised site keep every adjacent floor edge continuous with slopes no steeper than 1:4; nearby rooms can also lie on these slopes. The generator checks that the entire floor has one connected component, and tests inspect generated floor vertex heights and wall locations. This layout differs from the diagonal proposal and can introduce additional intersections. It remains open above and requires compilation, NAV, and playtesting before traversal or balance claims.

Use `--surfaces` to generate one welded, editable `CMapMesh` instead of solid boxes. Each floor grid cell contributes an upward-facing quad and each perimeter edge contributes an inward-facing wall quad. Floor/wall vertices and opposing half edges are shared; exposed wall tops use boundary half edges with face index -1, matching authored open meshes in the Cobblestone reference. The generator rebuilds topology, per-corner UVs/normals/tangents, per-face texture axes, and subdivision arrays. Tests check winding, shared edges, boundary loops, stream sizes, and wall direction. Binary conversion must preserve topology and positions. The sample has 1,068 faces versus 2,388 box faces in the connected version. It removes hidden box faces but retains the 64-unit floor grid for slope continuity; coplanar face merging is not yet implemented. Single-sided rendering and compiled collision still need validation in Hammer/CS2. Physics settings are inherited from the user's saved cube; no runtime collision result is claimed.

## Extract local topology examples

```powershell
python extract_sections.py --nav output/cobblestone-nav.json `
  --graph output/cobblestone-connections-final.json --output output/cobblestone-section.json
```

Choose new paths for reruns. The extractor takes a roughly 1,200-unit middle segment from the recorded TSpawn-to-A example path and nearby outgoing neighbors. JSON retains exact NAV polygon corners, heights, directed connections, labels, route witnesses, and input hashes. An SVG shows the original NAV outlines and path; sampled signed turns describe the centroid path, not architectural corner angles. The companion `-study.json` projects the outlines onto a flat floor, rasterizes at 64 units, and widens recorded links for continuous geometry. It explicitly records removed isolated fragments and corner-contact repairs. This is a reference-derived study, not an original generated layout or fine-tuning dataset ready for training. NAV boundaries are not architectural walls, and flattening can merge stacked spaces.

Pass the study JSON to `blockout.py --surfaces --proposal <section-study.json>` to create a separate editable map. The general prompt planner still uses its existing authored layout rules; section retrieval/remixing is a separate experimental path until evaluated. Future work should preserve elevation layers, extract room/portal boundaries from source geometry, and evaluate how well new sections retain reference patterns.

## Simplify section walls

```powershell
python simplify_section.py --input output/cobblestone-section-study.json `
  --output output/cobblestone-section-clean.json --tolerance 64
```

This flat-study pass traces the exterior contour, then removes corners while preserving a simple polygon, all route/light markers, area within 15%, and a sampled boundary distance within the selected tolerance. It rejects holes and multiple outlines instead of filling them. The SVG overlays the original and simplified outlines. Use the output proposal with `blockout.py --surfaces` to generate a triangulated flat floor and longer inward-facing wall polygons. The sample reduces 60 boundary segments to nine with a 6.1% area increase. It remains reference-derived, flattened geometry; neither minimum passage width nor tactical branching is guaranteed by marker containment. Tests check concave triangulation, protected markers, zero-tolerance behavior, hole rejection, and resulting Hammer topology. Source NAV files and evidence are unchanged.

For maps without named spawn-to-objective routes, `extract_sections.py --allow-unnamed` selects a generic recorded NAV path to a farthest reachable centroid. Its start uses a nearest-centroid spawn association when available. The selection method is recorded, and no objective association is claimed. This fallback does not model ladder traversal.

## First learned layout pilot

The first trainable task is hidden-half completion of a 32×32 NAV footprint at 64 Hammer units per pixel. Input contains the visible left half plus a visibility mask; loss and metrics use the hidden right half only. This is a small CNN trained from scratch, not a fine-tuned language model or text-to-map generator. It does not learn architectural walls, assets, height, ladders, or gameplay balance.

The installed GPU environment lives in ignored `.tools/training`. It uses Python 3.13, PyTorch 2.7.1 with CUDA 12.6, NumPy, and Pillow. Dependencies are pinned in `requirements-training.txt`; installation follows the [official PyTorch Windows guidance](https://pytorch.org/get-started/locally/). The local RTX 4080 Super was verified with an actual CUDA tensor computation. Create/rebuild an isolated environment with `python -m venv .tools/training` and its Python's `-m pip install -r requirements-training.txt`.

```powershell
& ".\.tools\training\Scripts\python.exe" training_dataset.py `
  --corpus output/reference-corpus-status.json --output output/training/pilot-v1
& ".\.tools\training\Scripts\python.exe" train_layout.py `
  --dataset output/training/pilot-v1 --output output/training/run-v1 --require-cuda --epochs 30
```

Use new dataset/run directories for subsequent experiments. Six maps train the pilot: Dust2, Cobblestone, Anubis, Tuscan, Cache, and Train. Office is validation, Vertigo is held-out test; maps never span splits. Aztec, Assault, and Cruise lack NAV and are excluded from this task. Sampling creates 256 distinct windows per map, with exact footprint duplicates rejected across splits. Nearby windows still overlap, so 2,048 examples do not represent 2,048 independent layouts. Projecting polygons within a 48-unit height band can alias vertical layers. Input provenance, map assignments, source hashes, and example coordinates are retained in the dataset manifest.

The trainer selects its checkpoint by validation loss, uses a fixed 0.5 threshold, and evaluates the test map after selection. It compares hidden-pixel IoU/F1 against straight-strip extrapolation and a training-only pixel-frequency baseline. These are completion baselines, not a comparison of complete playable maps with the old planner. Each run saves trained weights, epoch losses, metrics, predictions, a visual comparison, and checkpoint reload verification. One validation map and one test map make this a preliminary experiment; topology and playability need separate evaluation before model output reaches Hammer generation.

### Validation-only patch experiment

`train_patch.py --dataset output/training/pilot-v1 --output output/training/patch-v2 --epochs 40` uses the GPU environment to train the original local CNN and a deeper encoder/decoder on the same central 8×8 missing patch. The surrounding footprint and visibility mask are inputs; hidden values are removed. Both models share the fixed mask, training data, BCE loss, optimizer, and epoch budget. A differentiability test confirms that distant context can affect the deeper model's center prediction. Checkpoints are chosen by Office validation loss; a fixed 0.5 threshold is used for pixel metrics. The script never loads `test.npz` or reruns the observed Vertigo test.

The development run produced Office patch IoU of 0.563 for the local CNN, 0.556 for the context model, and 0.514 for edge interpolation. This is an easier, different task than half-section completion, so it does not establish an improvement on the first task. The larger network showed overfitting and did not outperform the smaller one. The six training maps and Office validation windows remain unchanged and correlated. A future confirmation needs a fresh reserved map and topology checks; these models are not yet connected to the Hammer generator. Outputs include both checkpoints, training histories, validation metrics, and a fixed-index preview.

### Topology evaluation

`evaluate_topology.py --predictions output/training/patch-v2/validation_predictions.npz --output output/training/topology-v2` evaluates the missing patch plus a one-cell visible rim using four-neighbor raster connectivity. Connected rim groups form ports. For each pair, the reference completion defines expected connectivity for scoring only; model predictions can preserve, break, or add a connection. Floor components entirely inside the patch are counted as isolated islands. This local measure excludes outside detours and does not assert directed NAV traversal, ladder access, or gameplay.

On Office development data, the local CNN preserves 339/448 expected port pairs versus 245/448 for interpolation, but adds 266 connections across 541 reference-separated pairs. Forty-eight examples contain broken expected connections and 84 contain extra connections. The broader model preserves 359/448 pairs but adds 277/541. Local island removal eliminates one predicted single-pixel island using only context and predictions; it does not repair missing routes. Ground-truth isolated components are counted separately because rasterization/projection can themselves fragment the target. Neither model is enabled for automatic Hammer generation. Future layout generation should take explicit port-connection intent and check constraints before converting predictions into meshes.


### Connection-conditioned experiment

`train_conditioned.py --dataset output/training/pilot-v1 --baseline output/training/patch-v2/validation_predictions.npz --output output/training/conditioned-v3 --epochs 40` trains the local CNN with additional visible-rim connection-group channels. Offline annotations reduce reference target connectivity to one group label per visible port. The inference encoder takes visible context and an external plan; it never takes hidden target pixels. Tests verify that different hidden shapes with the same connectivity produce identical inputs and that changing the supplied plan changes only the condition channels. Checkpoint reload is verified.

This run deliberately provides reference-derived connection intent on Office validation, so it has more information than the previous unconditioned model. It measures execution of supplied intent, not inference of intent or a fair same-information architecture comparison. Vertigo is not accessed. Forty GPU epochs selected a checkpoint by validation BCE. Required port pairs preserved fell from 339/448 to 330/448; extra connections fell from 266/541 to 167/541. Examples with broken routes rose from 48 to 50, while examples with extra connections fell from 84 to 57. Patch IoU was essentially unchanged (0.563 to 0.561). This is a mixed result and remains disconnected from Hammer generation. Withholding the plan caused predictions to collapse; this is an out-of-distribution diagnostic, not an independent control. Next research should optimize explicit route constraints rather than pixel BCE alone.


### Explicit route-loss training

`train_routes.py --dataset output/training/pilot-v1 --baseline output/training/conditioned-v3/validation_predictions.npz --output output/training/routes-v4 --epochs 40 --route-weight 0.25` adds a differentiable route term to the conditioned CNN's masked pixel BCE. Four-neighbor flood propagation computes widest-path confidence (the highest bottleneck occupancy among paths) over the patch and visible rim. Ninety-nine updates cover all simple paths on the 100-cell local grid. Route supervision uses visible ports and supplied connection-group labels only. Connected and separated pair classes are balanced per batch; missing classes are omitted. The checkpoint is selected by validation pixel BCE plus 0.25 times route BCE. The floor threshold stays 0.5.

On the same Office development examples, required connection preservation increased from 330/448 to 398/448 (74% to 89%). Examples with broken required connections fell from 50 to 26 and examples with unwanted connections fell from 57 to 6. Hidden-patch IoU changed from 0.561 to 0.566. Four examples contain isolated predicted floor components (14 pixels total); there were none in the previous conditioned run. These results still use reference-derived connection intent, including validation, and do not establish autonomous intent selection or generalization to new maps. This is one seeded run with a different batch shuffle schedule from the earlier trainer. No test archive was read. The model remains separate from automatic Hammer generation.

Tests check bottleneck gradients, alternate paths, winding paths longer than the grid diameter, diagonal and padding isolation, connection-versus-separation penalties, and no-port batches. Checkpoints are reloaded and compared against the trained model. Outputs retain histories, objective settings, dataset/baseline hashes, topology and pixel scores, predictions, and a fixed-index visual comparison. Remaining route failures require validation before mesh generation; a later planner must learn to choose the connection intent itself.


### Reserved evaluation cohort

Five user-approved maps are reserved in `output/evaluation-reservations.json`: Tombstone (`cs_tombstone.vmap`), Warsong (`ctf_warsong_gulch.vmap`), Russka (`de_russka.vmap`), Inferno2 (`de_inferno2.vmap`), and Nightfever (`de_nightfever.vmap`). They remain outside training and development validation; no model predictions have been run on them. The pilot dataset builder rejects any source marked `dataset_role: evaluation_only`. Source hashes, map/NAV reports, and preflight limitations are retained in the registry.

Russka, Inferno2, and Nightfever NAV files were copied from their compiled addon VPKs into workspace outputs using `extract_vpk_entry.py`, with entry CRC checks. The utility supports VPK versions 1 and 2, preload bytes and split archives, and refuses existing output files. Extraction and parsing do not establish whether a compiled NAV is current against the repaired VMAP. All five maps lack resolved named-area labels; they can support footprint/connectivity evaluation. Russka has six recorded ladders and Nightfever has one, excluded from the current footprint task. Freeze the planner and evaluation settings before running predictions, and keep any subsequent tuning separate from confirmation claims.


### Learned local connection planner

`train_connection_planner.py --dataset output/training/pilot-v1 --floor-checkpoint output/training/routes-v4/model.pt --floor-predictions output/training/routes-v4/validation_predictions.npz --output output/training/planner-v5 --epochs 40` trains an entrance-pair CNN on the existing six-map training split. Inputs contain visible occupancy, visibility and the union of two queried entrance masks. Hidden floor values and reference connection labels are absent from inference inputs. Reference patch connectivity supplies supervised labels only. Pair scores are decoded into a consistent connection partition by complete-link clustering with a fixed 0.5 threshold. The frozen route-loss floor model then completes the patch from the predicted plan. The script checks dataset and floor checkpoint provenance, verifies reload, and never reads test.npz or reserved map NAVs.

The first run used 3,980 training pairs and 989 Office validation pairs; the best checkpoint was epoch 5. Training loss kept falling while validation loss rose, showing overfitting. Decoded plans matched 59.8% of reference pair decisions and exactly matched 85/227 examples with at least two ports. A visible-edge interpolation plan baseline matched 60.3% and 90/227, so this run does not establish an advantage in choosing plans. The interpolation diagnostic was added after the first result was observed. Passing learned plans to the frozen floor model gave patch IoU 0.517, 248/448 required pairs preserved, 74 examples with broken routes and 82 with extra connections. Supplying reference-derived plans gave 0.566 IoU, 398/448 preserved pairs, 26 broken-route examples and six extra-connection examples; this diagnostic has privileged information. The learned pipeline is autonomous for local entrance decisions but remains unreliable and is not enabled in Hammer generation.

All five reserved maps remain unevaluated. Next development should address overfitting and plan decoding on existing development data before a fixed confirmation run. Visible context admits multiple valid hidden layouts, so matching a reference partition is an imitation measure rather than a design-quality score. This planner does not choose whole-map routes, elevation, architectural features or text-driven goals.


### Planner augmentation and external constraint solving

`improve_connection_planner.py --dataset output/training/pilot-v1 --floor-checkpoint output/training/routes-v4/model.pt --previous output/training/planner-v5 --output output/training/planner-v6 --epochs 40` compares control, eight square symmetries, dropout/weight decay, and their combination. All channels are transformed together; reference labels are unchanged by these local symmetries. The training arm is selected by Office pair BCE. Both complete-link and exhaustive maximum-likelihood partition decoding are measured with the same frozen floor model. Augmentation was selected in this single-seed run. Its maximum-likelihood pipeline matched 100/227 complete plans versus 85/227 previously; broken-route examples stayed at 74 and extra-connection examples fell from 82 to 71. Patch IoU fell slightly from 0.517 to 0.512. Regularization alone did not improve validation BCE. The small development gain needs confirmation; all reserved maps remain unevaluated.

`solver_planner.py` uses Google OR-Tools CP-SAT 9.15.6755 to replace custom exhaustive partition enumeration. Boolean pair variables and triangle constraints enforce a consistent equivalence relation across up to 20 entrances. The objective maximizes integer-scaled learned log-odds and prefers fewer connections in rounded-score ties. A two-second, single-worker solve limit is applied; status, objective bound and fallback use are exposed. Optimality refers to that mathematical score, not tactical or architectural quality. Integration outputs in `output/training/solver-v6` matched all 256 previous Office plans with optimal status. Tests independently check small exhaustive problems, consistency, 20-port groups, malformed inputs and empty cases. Dependencies are pinned in requirements-training.txt; the installation leaves training inside the project virtual environment. Documentation: https://developers.google.com/optimization/cp/cp_solver/ .


### First reserved-map confirmation

`evaluate_reserved.py freeze --registry output/evaluation-reservations.json --development output/training/pilot-v1 --planner-run output/training/planner-v6 --floor-checkpoint output/training/routes-v4/model.pt --output output/evaluation/confirmation-v1` wrote a protocol before predictions. `evaluate_reserved.py run --output output/evaluation/confirmation-v1` then sampled and evaluated 256 unique eligible windows per map using frozen seeds, pilot filters, height projection, exact deduplication against development manifest fingerprints, and equal-weight map averages. NAV bounding-box prefiltering only accelerates the original raster operation; tests check equivalence. Source code, model weights, runtime versions, source maps and NAV exports are checked against frozen hashes. The learned planner consumes visible context only. OR-Tools reported optimal status on all 1,280 queries with no fallbacks. No weights were trained or changed.

The learned pipeline's macro patch IoU was 0.592 versus 0.617 for direct edge interpolation. Required-pair preservation was 60.7% versus 74.9%; extra-pair rates were 32.2% versus 46.6%. It had 348 examples with broken required routes versus 258, 181 with extra connections versus 203, and nine with isolated floors versus 88. Pixel IoU improved on Russka and Inferno2 but trailed interpolation on Tombstone, Warsong and Nightfever. Supplying reference-derived connection plans to the same frozen floor model preserved 95.2% of required pairs with a 2.4% extra-pair rate. This privileged-information diagnostic points to connection planning as a major limitation; it does not validate autonomous design. Automatic Hammer generation remains disabled.

This cohort is now observed, recorded in evaluation-reservations.json and the corpus status. It remains excluded from training. Any later model tuning informed by these findings needs fresh maps for another untouched confirmation. Five maps are the independent units; windows overlap and are correlated. NAV freshness, vertical-layer aliasing, missing ladder traversal and the lack of tactical/architectural measures remain limitations. Full per-map baselines, sample provenance, predicted plans, solver diagnostics, archived predictions and fixed-index previews are retained in output/evaluation/confirmation-v1.


### Entrance geometry and ranked proposals

`geometric_planner.py --dataset output/training/pilot-v1 --floor-checkpoint output/training/routes-v4/model.pt --previous output/training/planner-v6 --output output/training/planner-v7 --epochs 40` compares a same-architecture zero-geometry control, visible geometry features, and geometry with twice the loss cost for missed connected labels. Twelve symmetric features describe port sizes, distances, inward-facing alignment, surrounding visible floor density and an interpolation-inferred connection. Inputs are masked before geometry extraction. All arms use square-symmetry augmentation; feature invariance and channel alignment are tested. Checkpoints and arms are selected by unweighted Office pair BCE. Weighted-arm sigmoid outputs are cost-sensitive scores, not calibrated probabilities.

OR-Tools proposes plans from five fixed logit biases plus all-connected/all-separated extremes. The frozen floor model completes each unique plan. A target-free ranking cost combines model score, violations of the proposed plan, occupied cells outside any full 2x2 raster square, and isolated floor pixels. This width proxy is not player clearance. The ranking criteria never consume hidden reference geometry. Candidate costs, selections, solver diagnostics and model hashes are archived. Checkpoint reload is verified.

The selected geometry arm with ranking preserved 294/448 required Office pairs (65.6%), with 62 broken-route examples and 74 extra-connection examples. The previous selected planner had 74 and 71 respectively: fewer broken routes with a slight increase in shortcuts. Patch IoU fell from 0.512 to 0.509. Within the new geometry arm, ranking changed broken-route cases from 65 to 62 and extra-connection cases from 69 to 74. The higher-recall arm reduced broken-route examples to 28 but increased extra-connection examples to 109 and was not selected by pair BCE. This is a modest, mixed development result; no automatic Hammer generation is enabled. The observed five-map cohort was not rerun or loaded. A new cohort is required for future untouched confirmation.

## Whole-map layout extraction

`whole_map_layout.py` builds spatial navigation graphs from the six approved pilot training maps only. Current artifacts are in `output/whole-map-layout-v2`: per-map JSON, SVG/PNG diagrams, a manifest, report and explicit quality issues. The graphs preserve 14,663 static hull-0 NAV polygons, grouped into 1,884 strongly connected spatial regions with 5,094 directed inter-region edges. Source and extractor hashes are recorded.

Regions use 512-unit XY and 128-unit elevation bins plus inferred place labels; they are not architectural rooms. Size and entrance features are NAV geometry proxies. Spawns and objective bounds come from the VMAP reports, and spawn associations/path distances are diagnostic. Cache has an objective with no strictly contained NAV centroid; Cobblestone has a target unreachable from the diagnostic team seeds in the selected directed graph. Ladders, movable navigation, NAV freshness, room boundaries, cover and sightlines still need work. These artifacts are not certified whole-map training targets, and this step performs no new training. Validation, test and reserved evaluation maps were not loaded.

Validation: all 107 tests passed, including disconnected-area separation, one-way preservation, elevation bins, objective bounds, excluded links and directed shortest paths.

### Objective alignment correction and coarse areas

Latest whole-map graphs: `output/whole-map-layout-v3`. The Cache and Cobblestone route gaps were objective-volume boundary precision artifacts. A recorded 0.001 Hammer-unit containment tolerance restores all 24 diagnostic team/objective routes using unchanged NAV exports; strict match counts and correction evidence are retained.

`coarse_layout.py` prepares larger connected navigation areas by merging only bidirectional recorded interfaces with compatible inferred place labels, sufficient edge support and size/elevation caps. `output/coarse-layout-v1` contains six graphs, SVG/PNG previews, a Dust2 before/after comparison, provenance, merge histories and boundary-tolerance audit. It reduces 1,883 spatial segments to 938 coarse areas. Partition and surviving directed witnesses are conserved; interface support is tessellation-dependent and does not establish clearance. These are navigation neighborhoods, not architectural rooms, and no model training occurred. All 114 tests passed.

## Native architectural geometry pilot

`architecture_features.py` streams native editable face geometry without loading an entire VMAP into the full typed parser. It reconstructs half-edge face loops, applies authored world transforms, triangulates concave polygons, records materials/normals and filters helper/editor meshes and sky/visibility/trigger material faces. `architecture_report.py` renders a real mesh-plane slice for inspection.

The first pilot uses approved Dust2 only. `output/architecture-dust2-v1` contains 314,005 retained native faces, 450,309 triangles, geometry features for 110 coarse areas, and 291 recorded-transition straight-segment probes. Model props, prefab expansion, collision/opacity rules, subdivision and displacement are not represented. In particular, 2,415 prop_static model references remain unexpanded. Mesh rays, low-obstacle candidates and surface bounds are geometric evidence, not verified sightline, clearance, tactical-cover or room labels. No new training occurred, and other training maps were not processed by this pilot. All 118 tests passed.

## Static-prop render geometry and collision audit

`model_geometry.py` expands approved static props from local decompiled ModelDoc and DMX sources, respecting submesh import filters, descriptor translations and exact map instance transforms. Latest Dust2 artifacts: `output/model-geometry-dust2-v2`. All 2,415 instances expanded, yielding 4,352,220 render triangles from 307 shared source files; 2,597 zero-area faces were counted and omitted. The initial pass rejected affected files; the revised pass preserves valid faces and source-hash-checks reused successful instances. Instance origins match the VMAP report and triangle ranges are conserved.

`prop_observations.py` compares against native-mesh probes, with reports/preview from `prop_geometry_report.py` in `output/prop-observations-dust2-v1`. Added props shortened 104 of 7,424 sampled rays; none of the 291 transition probes gained a nearer hit. Low-obstacle candidates changed from 249 to 252. These are render-geometry observations, not verified collision, cover or visibility labels.

`tools/ResourceAudit` uses the installed ValveResourceFormat parser. The exact installed Dust2 `world_physics.vmdl_c` entry was copied to workspace with CRC verification and SHA-256 provenance, and its PHYS aggregate audited: 10,143 hulls and six meshes. Artifacts are retained in `output/model-geometry-dust2-v1`. Compiled collision shape geometry has not been extracted or verified against the repaired VMAP/NAV; all static prop collision settings remain explicitly unresolved. No new training occurred. All 125 Python tests pass, and the resource audit builds/runs successfully.

## First learned whole-layout graybox

`train_macro_planner.py` trains a small twelve-area VAE on the six approved coarse training graphs. The representation retains spawn/objective roles and geodesically selected area landmarks, projects height away, and symmetrizes links. Internal Tuscan reconstruction selects an epoch, followed by a final fit using all six maps. This is a six-map experiment, not evidence of broad generation quality. Actual GPU training and weights are recorded under `output/training/macro-planner-v1`.

`export_macro_graybox.py` exports the selected proposal to `aitesting/maps/hammergpt_macro_v1.vmap`. The result has 12 areas and 14 proposed links, continuous editable floor/wall surfaces, 5 spawns per team, 2 objective volumes, 12 lights and 4 authored cover boxes. No below-threshold graph connections or grid-corner repairs were required. Learned outputs and exporter adaptations are recorded separately. Preview and report are under `output/macro-graybox-v1`. All 128 tests and binary/topology/entity checks passed. Compilation, sky/ceiling setup, NAV and gameplay validation remain pending.

### Reviewed graybox v2

`review_macro_layout.py` creates a traceable manual revision using user feedback and the [Exodus design guide](https://steamcommunity.com/sharedfiles/filedetails/?id=1110438811). Area8 and its corridor are removed; v1 and the model weights are preserved. `output/macro-review-v2` contains the proposal, before/after floor-route audit and report. All six terminal-to-terminal grid distances are unchanged after removing 144 floor cells. The audit detects a nonincident corridor overlap near Area2. Graph leaves and overlap flags require review, rather than automatic deletion or claims of tactical usefulness. The preview additionally exposes Area7 as a geometric dead-end spur despite its two proposed graph connections; this remains unresolved.

`aitesting/maps/hammergpt_macro_v2.vmap` has 11 areas, 1,662 connected floor cells, five spawns per team and two objective volumes. All 131 tests and binary conversion/topology checks pass. The installed CS2 resource compiler completed successfully (16 resources compiled, zero failed) and produced `game/csgo_addons/aitesting/maps/hammergpt_macro_v2.vpk`, including GPU-baked lighting. Full log and preview: `output/macro-graybox-v2`. Build diagnostics include missing detail-prop metadata, no lightmap resolution volume, and zero NAV areas. A successful compile does not verify in-game movement, bombsite behavior, visibility or balance. The next step is an in-game walk-through and route revision, including Area7; no additional maps or retraining were used for v2.

### Route-aware training and graybox v3

`train_route_macro.py` replaces the fixed twelve-area vector with capacity for 24 areas, XYZ positions, dimensions, an active-area mask, and two bend residuals per link sampled from source shortest paths. Each of the six approved training maps is encoded at 16, 20 and 24 areas, yielding 18 representations of six independent maps. All Tuscan representations are held out together for development epoch selection; the final demonstration refits all six maps for 80 epochs on the 4080 Super. Checkpoint reload is numerically verified. No validation/test/reserved maps are loaded. Current artifacts: `output/training/route-macro-v3-reviewed`, with the original training run and failed planning attempts preserved under `route-macro-v3` and earlier experiment directories.

The locally installed NetworkX and OR-Tools libraries perform graph analysis and constrained planning. Learned edge scores guide a degree-bounded connected graph with at least eight branch areas, alternate routes and geometric crossing constraints. Grid A* follows predicted bend guides while keeping unrelated rooms and corridors separated. Every built corridor component must connect exactly its two intended rooms, and the extracted floor graph must match the proposal. Feasible shared-vertex height fields interpolate flat rooms with gentle ramps; floor quads are triangulated for nonplanar elevation.

`replan_route_macro.py` reuses saved samples and weights when planning constraints change. The selected v3 sample has 20 areas, 25 links, eight branch areas and six graph cycles, no leaves or bridges, and four/three connections to the sites. Its built floor has exactly the 25 intended corridor components. Playable floor area increases 45.7% over v2 (2,422 versus 1,662 cells), with only 24 units of height relief. Most selected links (23/25) scored below 0.5: authored structural constraints dominate the route choices, so this is not evidence of strong learned tactical topology or useful secrets.

The new editable `aitesting/maps/hammergpt_macro_v3.vmap` preserves prior versions. Binary topology/position/entity checks and all 135 tests pass. CS2 compilation succeeds (16 resources, zero failed), producing `game/csgo_addons/aitesting/maps/hammergpt_macro_v3.vpk` with GPU-baked lighting. Preview, compile log, checkpoint provenance, floor route distances and design limitations are under `output/macro-graybox-v3`. NAV remains empty; timing, movement, objective behavior and balance require an in-game walkthrough. The long outer T-side approach and stepped grid boundaries are explicit review concerns.

### Gameplay-role annotation pilot

After playtesting v3, `layout-design-brief.md` records the missing independent CT-to-B route and the objective-free Junction1/12 side loop. Branch/cycle quotas and one-room-per-landmark rendering are inadequate design criteria.

`annotate_layout.py` prepares a human-reviewable Dust2 interpretation from the approved directed coarse NAV graph and objective/spawn anchors. `output/annotations/dust2-v1` contains `annotation.json`, a source-NAV overview and `review.md`. Eighteen place-name groups carry proposed gameplay roles; ten unlabeled coarse regions remain unresolved. Eight directed route traces retain original NAV edge witnesses, including separate CT access to each objective, Long/Short A approaches, tunnel/Mid B approaches, CT-side rotation, and Lower-tunnel/Mid repositioning. Route distance proxies and visual centroid traces are not actual travel paths or timing measurements.

The artifact is explicitly `draft_pending_user_review` and `training_eligible: false`. Proposed staging, battlefront, retake and positioning roles do not establish safety, exposure or tactical utility. No source maps were modified and no training occurred. Three focused annotation tests pass, checking direction preservation, route place restrictions and required-label verification. The next step is review of the interpretations before refining boundaries or preparing approved training targets.

The user reviewed Dust2's role context, placed contest contexts at A-doors, Middle and Upper tunnels, and suggested merging original groups 15/18 into Outside B. `review_dust2_annotation.py` records that feedback in `output/annotations/dust2-v2`, retaining the original subareas, all 110 regions and 291 directed links. Seventeen groups provide first-pass role context for 100 regions; ten unlabeled regions have supervision masked off. Reviewed context does not approve exact spatial boundaries or timing/safety claims, and no training occurred.

`annotate_boundaries.py` prepares separate meeting-footprint and choke-transition proposals under `output/annotations/dust2-boundaries-v1`. Three authored meeting ROIs are clipped to source NAV polygons; five local choke neighborhoods retain nine recorded directed interface witnesses in total. The supplied marked screenshot guides location interpretation but is not registered to world coordinates. XYZ clipping preserves ramp elevations and excludes other-floor surfaces; two focused tests pass. Yellow meeting masks and red choke masks may overlap intentionally and must remain separate target channels. All new boundary targets remain `pending_boundary_review`, with `training_eligible: false`. The overview and review notes are ready for feedback; exact doorway clearance, timing fronts and sightlines remain unmeasured.

Latest corrected boundary draft: `output/annotations/dust2-boundaries-v3`. User feedback excludes Pit from M1, extends M2 into the Mid-door split, and moves C1 to the upper A-door exit. Both A-door sets sit within the same coarse LongDoors region, so the upper C1 uses a verified internal directed NAV link (354 to 366), with source hash verification, instead of the erroneous lower cross-place boundary. M1 uses only LongDoors/LongA footprints; M2 includes the local MidDoors portion up to the inspected doorway-gap draft boundary (y=1632). All eight retained choke-interface witnesses and the three corrections are recorded. Original drafts remain available, and boundary training eligibility remains false. Geometry checks confirm Pit exclusion, the correct internal NAV witness, and M2's updated extent.

Subsequent M3 correction: latest draft is `output/annotations/dust2-boundaries-v4`. A tunnel-only extension covers the complete small hallway below C2 and part of Upper Tunnels, reaching y=1280. The original B-side extent is retained, and the other seven boundary geometries are unchanged. M3 now contains 48 clipped NAV surface pieces. The spatial targets remain pending review; no model training occurred.


Dust2 v4 boundary extents were explicitly approved by the user. The review record is in `output/annotations/dust2-boundaries-reviewed-v1`; its eligibility is limited to reviewed meeting extents and choke neighborhoods, without timing, sightline or clearance certification. No new training occurred.

`annotate_anubis_control.py` now prepares initial-control context from the user diagram. Latest draft: `output/annotations/anubis-control-v3`. Source Bridge is split into Top Mid and Bridge corridor proposals; source Canal receives Water meeting and Boat T-control proposals. Three access fronts retain original directed NAV witnesses. Six directed routes cover independent CT access to each site, T Long/Boat approaches and rotations in both directions. Actual spawn entity associations are retained with their diagnostic scope rather than replaced by place names. All 159 source nodes and 404 directed edges remain unchanged; draft supervision remains disabled. Eight focused tests pass. For unfamiliar approved references, establish anchor/route evidence first and keep unverified control, staging and battlefront interpretations masked rather than requiring expert user annotations.


The user approved Anubis v3 ("this looks good"). `review_anubis_control.py` preserves that draft and records review in `output/annotations/anubis-control-reviewed-v1`. Control targets supervise 101 regions and mask 58 unresolved regions; four reviewed spatial subdivisions remain separate from whole-region labels. All original nodes, directed edges and NAV polygons are retained. No new training occurred.

`annotate_reference_backbone.py` prepares evidence-first drafts for approved training references and rejects evaluation references. Latest Cobblestone draft: `output/annotations/cobblestone-backbone-v3`. Four directed route examples cover T access to both objectives and rotations in both directions. CT-to-A associations overlap one coarse region; CT-to-B fails the broader BombsiteA-place exclusion but has an unrestricted witnessed Connector path. These are abstraction ambiguities, not map-design verdicts. Initial control and meeting labels remain unassigned, and supervision remains disabled. Eleven focused tests pass. Next, inspect the CT overlap at individual NAV-area scale.


User-provided Cobblestone encounter contexts: between Long A and Catwalk, below Underpass, and Upper/Lower tunnels. Choke contexts: Underpass doors, Upper/Lower tunnel separation, Long A doors toward the upper hallway, and Tunnels to Tmain. `annotate_cobblestone_boundaries.py` records those locations in `output/annotations/cobblestone-boundaries-v1`, with three NAV-clipped meeting proposals and four witnessed choke groups. Numerical extents and C1/C3 doorway matches await review; initial-control labels remain unassigned. The one-way elevated UpperTunnel-to-LowerTunnel witness remains directed. All 259 source nodes and 607 directed edges are preserved. No new training or map edits occurred.


The user supplied a Cache heatmap screenshot showing 131,333 kills with Killer location selected. `annotate_cache_heatmap.py` preserves the exact image and its hash in `output/annotations/cache-heatmap-v1`, records missing match/version/query information and proposes three qualitative firing-position context correspondences. No image registration, calibrated heat density, initial-control labels or quantitative training targets are inferred. `output/annotations/cache-backbone-v1` retains six directed route examples and unchanged source topology. All new Cache gameplay supervision remains disabled pending review; no model training occurred.


The user additionally supplied a Cache first-kill heatmap and confirmed that it shows killer positions. `annotate_cache_heatmap.py --first-kills --comparison ...` records this distinct scope in `output/annotations/cache-first-kills-v1` with three opening-fight context proposals. It does not inherit the aggregate image's 131,333-kill count. The supplied qualitative legend is preserved; match count, map version, side mix and numeric heat scale remain unknown. Comparison with the aggregate reference is qualitative, with matching event samples unverified. All source topology is preserved, review masks remain disabled, and no new training occurred.


The user specified five Cache choke contexts: A Halls left doorway into A, A Main into A, Red into Mid, Connector into Mid, and B Main into B. `annotate_cache_chokes.py` records these under `output/annotations/cache-chokes-v1`, preserving original directed NAV interfaces and source geometry. C1 proposes the Squeaky-side A entrance; C3 proposes the Mid-facing Garage exit from the Red-side approach. These naming correspondences and expanded NAV neighborhoods await review. Gameplay location feedback does not approve exact doorway dimensions, meeting masks, or heatmap density targets. No new training occurred.


The user approved all five Cache choke matches and specified B Main, A Main and Mid as battlegrounds. `review_cache_annotation.py` records that feedback in `output/annotations/cache-reviewed-v1`, preserving the original draft and all 157 nodes/395 directed edges. Five first-pass choke neighborhoods and three named battleground contexts are reviewed; 16 regions receive positive context supervision and the remaining regions have null masked targets. Named context footprints are not exact meeting masks. Heatmap density and initial-control/timing labels remain separate. No new training occurred.


At the user's request, `annotate_train_boundaries.py` guesses Train battlefront contexts in `output/annotations/train-boundaries-v1`. Five meeting-area proposals accompany T Main, Ivy, Popdog and upper/lower B access; six witnessed choke proposals include those entries and an explicitly separate Connector rotation/retake candidate. Authored XYZ selections retain floor elevations. Popdog only includes the ground-level LongDog exit; 11 source ladders remain outside the route model. Six route examples are in `output/annotations/train-backbone-v1`. All source topology is unchanged and all new gameplay supervision remains disabled pending user review. No new training occurred.


Train boundary correction: latest draft `output/annotations/train-boundaries-v2`. The user requested merging previous M1/M2 into one outer-yard encounter and adding a separate meeting area inside Ivy with a choke at its upper entrance. M1 now spans the old extents and intervening source NAV; M2 is restricted to the Ivy place footprint. C7 retains witnessed Alley/Ivy transitions. Original yard-side C2 and all other choke geometries remain unchanged, as do M3/M4/M5. All source topology remains preserved; new extents and unreviewed hypotheses remain excluded from training.


Train M4 correction: latest `output/annotations/train-boundaries-v3`. The user accepted v2 with an M4 move left into Back of B around the T Side Upper drop, where CT and T meet. M4 now clips the Back of B/drop context over its source elevations instead of the near-site lower-entry train lanes. M1/M2/M3/M5 and all seven choke geometries are unchanged. Prior acceptance and the new M4 correction are recorded separately; the corrected numerical footprint remains pending review, with no new training performed.


Train review finalized by the user: "remove m5 and we are finished". `review_train_annotation.py` removes only M5 and records four meeting footprints and seven choke contexts in `output/annotations/train-reviewed-v1`. All retained geometries and the original source graph are unchanged; C5 remains an upper B choke separate from the removed meeting area. The removed proposal produces no negative training label. Target eligibility covers first-pass spatial context only. No new training occurred.


Cobblestone review is complete in `output/annotations/cobblestone-reviewed-v1`. `train_reviewed_context.py` trains a two-layer directed message-passing encoder on geometry, local NAV adjacency and terminal geodesic descriptors, without place names, map IDs, annotation inputs or heatmap pixels. The five-map pilot uses only Dust2, Anubis, Cache, Train and Cobblestone. Local areas covered at least 25% by a reviewed context are supervised; other-channel zero denotes nonmembership in a reviewed mask, not proven absence of gameplay. Cache named-context examples receive half loss weight. Overlapping footprint coverage uses the maximum single piece, avoiding double counting.

GPU runs are preserved in `output/training/reviewed-context-v1` (unbalanced) and `reviewed-context-v2` (balanced). Each experiment uses five whole-map held-out folds with training-fold-only feature normalization; v2 also computes class weights exclusively from training folds. Fixed 120 epochs per fold and final all-five fit. No reserved references are loaded. The checkpoint reload passed numerical verification, and 14 focused tests passed. Mean held-out balanced accuracy is 51.5% for meeting context and 53.8% for choke context, versus a 50% constant baseline. Generalization remains weak and uneven, particularly Anubis; this is an experimental semantic encoder, not a whole-map generator. Initial-control labels and screenshot density were not trained.


`gameplay_backbone.py` implements an authored tactical-backbone comparison after the weak context-model pilot. `output/gameplay-backbone-v2` contains the graph diagram, continuous-floor preview and proposal. Seventeen named gameplay spaces and 20 purposeful connections provide three encounter fronts, independent CT access to both objectives, central attack alternatives, and rear rotation. There are no branch/cycle quotas. Shape footprints are asymmetric polygon cell selections; access widths vary from 192 to 448 units. Actual floor checks preserve independent site access and demonstrate paths via Mid while masking a main approach footprint and the other site. These footprint masks do not close an entire street; an adjacent bypass can remain. Unrelated streets do not touch or intersect outside semantic footprints. Fourteen targeted geometry tests pass.

The new sandbox map is `aitesting/maps/hammergpt_backbone_v1.vmap`; export artifacts are in `output/backbone-graybox-v1`. Binary round-trip topology/positions and entity inventory passed. CS2 compilation passed with 16 resources compiled and zero failures. This layout is authored and flat, with placeholder site cover; it is not a learned layout prediction and it does not certify tactical quality, timings, visibility or utility. No source reference maps were modified and no new training occurred.


Geometry-first Train section reconstruction: `reconstruct_train_section.py` and `audit_train_reconstruction.py` produce `output/train-reconstruction-v1`. The outer-yard/T Main/Ivy/Popdog selection retains 836 original XYZ NAV polygons, 2,059 directed links, 67 crop-boundary connections, nine ladder-reference areas and a 320-unit height span. Source editor and supported static-prop render triangles remain separate. Occurrence identities avoid collapsing repeated decompiled node IDs. Shared DMX files are parsed once, and repeated submesh names retain all selected occurrences. Render descriptors may declare physics shapes; those physics shapes are explicitly not expanded. One multi-render-mesh gas-meter source remains unsupported.

Exact source NAV/traversal attributes and directed topology passed round-trip comparison. The portable GLB native/prop triangle coordinates match their extracted arrays exactly after the documented axis change. The reference VMAP hash remains unchanged. Eighteen focused tests pass. Derived inputs retain 2,766 grid/height samples, 360 small-area centroid fallbacks and 83 XY positions with walking layers more than 48 units apart. Original polygons remain canonical. There are 768 double-sided editor/render ray observations, not validated gameplay visibility. No new model training occurred. Collision, ladder endpoints/traversal, dynamic/prefab geometry and tactical quality remain unresolved. `section-generation-plan.md` records the next dataset and held-out reconstruction experiment.


Geometry-completion pilot (actual GPU learning): extract_learning_geometry.py extracts source editor/static render surfaces for approved maps; geometry_completion_dataset.py builds map-separated 3D walking/mesh patches with explicit source-coverage masks. Dust2/Anubis/Cache train, Cobblestone validates, Train outer-yard section tests. Unsupported source cells are excluded from labels/loss/metrics. train_geometry_completion.py trains a 366,546-parameter 3D U-Net for 60 epochs; epoch 34 is selected by Cobblestone, with zero checkpoint reload difference. Dataset: output/geometry-completion-dataset-v2. Checkpoint/results: output/training/geometry-completion-v2. Fixed-threshold mean IoU 0.494 loses to interpolation 0.567.

calibrate_geometry_completion.py freezes a Cobblestone-selected thin-surface decoder before applying it to Train. Follow-up artifacts: output/training/geometry-completion-calibrated-v1. Walking IoU improves to 0.597 vs baseline 0.551; mesh IoU 0.572 remains below baseline 0.583. Mean IoU 0.584 vs 0.567 is modest. Local voxel passage preservation 96.8% vs 88.5%; false connections 11.9% vs 11.7%. Train remains excluded from gradients/selection, but this follow-up comes after observing the first test and is development evidence, not a fresh blind test. Twenty-eight focused checks pass. No full-map generation, collision, ladder or tactical-quality certification. See geometry-learning-experiment.md for experiment scope and source coverage.
