# Whole-map-conditioned topology completion pilot

Fixed fitting maps: Dust2, Anubis, Cache. Cobblestone selects model checkpoints and the geometry-only baseline configuration. Train enters only after selection. Source maps have previously been inspected in this project, so this is a development comparison, not a fresh blind test. Historical planner checkpoints are not loaded because they saw these maps.

Each input supplies up to 64 route-supported coarse NAV areas: normalized XYZ, area/height descriptors, terminal roles and reviewed encounter/choke context. Unknown tactical roles stay masked. Targets retain all recorded directed NAV interfaces among these areas, including connections not used by a sampled route. Names, map identity and target edge labels are not input features. Area count and positions are supplied; this experiment does not invent an entire map from an empty canvas.

Geometry alone selects a region of 5–12 supplied areas. All directed pair labels incident to those areas are hidden, including negatives. Visible empty pairs are distinguished from unknown pairs. No positive-edge-based mask resampling. Three maps provide three independent source organizations; random masks and mirrors do not create new independent maps.

Compare a directed message-passing graph planner with a flat MLP following the legacy planner's approach, retrained with identical inputs, masks, weighted loss and split. This baseline is adapted to 64 supplied slots and is not the historical VAE checkpoint. Also compare nearest fitting-map copying with spatial/context assignment and visible-link agreement, plus a geometry-only nearest-neighbor baseline chosen solely on Cobblestone.

Both train for 300 optimizer steps on the local GPU. Checkpoints minimize Cobblestone weighted loss. Class weights use fitting-map masks only. Fixed probability threshold 0.5; no Train-driven calibration. Save checkpoints, input hashes, loss histories, prediction arrays, scores, baseline selection and checkpoint reload agreement. Display the first four fixed Train masks.

The graph model must beat all three nonempty baselines on hidden directed-edge IoU before reporting evidence for improved conditional connection reconstruction. Precision and recall must accompany IoU so excess links remain visible. That result would still not establish improved empty-canvas layout generation, strategic quality, timings, clearance, sightlines or playability. Do not export a repaired graph or Hammer map to disguise a failed reconstruction comparison.

## Completed development result

Artifacts: `output/training/route-organization-v1` and `output/training/route-organization-calibrated-v1`. Both networks trained on the 4080 Super for 300 optimizer steps; Train was excluded from fitting and checkpoint selection. Checkpoint reload probabilities match exactly. The raw 0.5 graph decoder failed: hidden-edge IoU 0.102, precision 0.103, recall 0.890. The matched flat MLP scored 0.076 IoU, nearest-map copying 0.058, and geometry-only neighbors 0.425.

A separately recorded decoder development follow-up selected thresholds only on Cobblestone validation and saved them before reloading Train predictions. The same graph weights at threshold 0.9 scored 0.244 IoU, precision 0.329 and recall 0.484; the geometry baseline retained 0.425 IoU, precision 0.579 and recall 0.615. Train had already been observed in the raw run, so the follow-up is not a fresh blind test. Both experiments remain available.

The gate failed. This run does not demonstrate improved layout generation and produced no new layout or Hammer map. It exposes excessive predicted connections and weak cross-map reconstruction even when positions and reviewed context are supplied. Three fitting organizations, coarse NAV areas and interface-reconstruction targets cannot establish strategic design ability. More training epochs or loop quotas are not justified by this result.

Next experiment should first expand the same hashed route/geometry representation using already approved independent maps, retain whole-map exclusions, and investigate local spatial scaling/area-boundary evidence. Any architecture or loss change must be compared against the geometry baseline on a newly fixed development split. A future fresh evaluation map remains separate from training and tuning; no reserved map was loaded here.

## Source-only corpus expansion

Tuscan and Vertigo were ingested automatically from existing approved VMAP-derived reports and recorded NAV exports. No map reconstruction, compile, new tactical annotation or reserved-map access was performed. Tuscan has no source place labels: distinct source site-designation fields supply objective identity; absent encounter/choke annotations remain unknown. Vertigo retains its spatial height data. Training maps increased from three to five: Dust2, Anubis, Cache, Tuscan, Vertigo. Cobblestone remains validation and Train remains excluded from fitting.

Artifacts: `output/route-corpus-expanded-v2`, `output/training/route-organization-expanded-v1`, and `output/training/route-organization-expanded-calibrated-v1`. The same 300-step training procedure and development masks were retained. Raw graph IoU increased from 0.102 to 0.130. With separately validation-selected decoding it changed from 0.244 to 0.248, while the geometry-only baseline remained 0.425. This small change does not establish a meaningful improvement in generalization or layout generation. No generated map was exported.

## Native source boundary and obstruction experiment

Artifacts: `output/source-obstruction-features-v1` and `output/training/source-obstruction-planner-v1`. Read-only native face extraction added Tuscan and Vertigo geometry caches. Eight-direction boundary rays and six offset/height pair rays supply first-intersection fractions with explicit support masks. Geometry computation accepts positions and native triangles, never NAV connection labels. Static props, collision, opacity and ladders are omitted; surface intersections are proxy evidence, not gameplay constraints.

A residual network augments the frozen five-map graph planner. It trained for 300 optimizer steps, with checkpoint selection on Cobblestone (epoch 180) and validation-only decoder selection (0.94). Unsupported geometry preserves both frozen logits and the previous 0.865 decoder. Configurations were saved before loading Train for evaluation. Checkpoint reload matched exactly.

Across the same 32 fixed Train masks, source-aware IoU was 0.268, precision 0.344 and recall 0.548; frozen planner IoU was 0.248. Both geometric baselines scored 0.425. The source-ray baseline selected a zero obstruction cutoff on validation, effectively retaining the original geometric rule. The success gate failed and no Hammer map was generated.

Train's cache covers one section: only 7.1% of hidden directed candidate pairs have supported measurements. On that subset the source model scored 0.3654 IoU versus frozen 0.2632 and geometry 0.3648. The tiny margin over geometry is not convincing superiority, and subset performance must not replace the full comparison. Extra network capacity and decoder selection also differ from the frozen model; without an ablation the gain cannot be attributed solely to source geometry. Train remains a previously observed development map.

The immediate measurement limitation is incomplete test geometry. A follow-up should extract full native Train geometry and repeat the frozen comparison before changing the training corpus or requesting more tactical labels. That would remain a development measurement, not a fresh evaluation or proof of empty-canvas generation.
