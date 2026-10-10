# Progressive layout generation pilot

The task changed from missing-link reconstruction to sampling a new spatial graph: area count, normalized XYZ, height/area descriptors, multi-hot terminal roles and directed links are generated. No source graph, existing area count, positions or reference map is passed at generation time. Normalization uses fitting maps only. These nodes remain coarse NAV regions, not architectural rooms; polygon and Hammer geometry generation are outside this pilot.

The implementation is a small autoregressive GRU with a four-component Gaussian geometry distribution and a shared four-component Bernoulli mixture per directed edge row. The shared component can correlate a row's edge decisions. It is inspired by progressive graph generation, not a reproduction of [GRAN](https://arxiv.org/abs/1910.00760). It has no GRAN attention/message-passing architecture. Recurrent history receives node descriptors, roles and prior degrees; explicit graph-state message passing remains absent.

Complete recorded coarse graphs replace route-selected subsets. Fitting maps and counts: Dust2 110, Anubis 159, Cache 157, Tuscan 118, Vertigo 167. No source graph was truncated. Cobblestone (259 nodes) selects checkpoints using four fixed source-order permutations. Train and all reserved evaluation maps are excluded from loading. Five independent maps remain five maps despite ordering/mirror augmentation.

## Runs and visible result

`output/training/progressive-layout-v1` preserves the first 1000-step GPU run. Its unconstrained Gaussian size descriptors produced negative values. `output/training/progressive-layout-v2` retrains with log-positive descriptors; zero source heights have a small numerical floor. This is part of the output representation, not graph repair. The selected corrected checkpoint is step 600. Its saved checkpoint reproduces the first fixed sample exactly. The exact corrected script is preserved as `training-script.py` beside the checkpoint. The historical v1 checkpoint used the earlier descriptor transform and should not be sampled with the corrected transform.

Six seeds, 7100–7105, were specified before looking at sample quality. No rejection, source copying, connectivity repair, quotas or authored route templates were applied. Corrected samples contain 116–306 nodes, 16–40 connected components and 15–37 isolated nodes. Three contain all four terminal roles; only one has a component containing each role. This is weak undirected connectivity, not demonstrated directed spawn-to-site access. Generated cycle rank spans 89–361 versus 49–71 in fitting graphs. Counts are only weakly fitted and include sizes outside the observed fitting range.

The corrected generator passes causality and deterministic sampling checks; positive size descriptors are now guaranteed by parameterization. Twenty-nine relevant tests pass. These checks validate implementation behavior, not layout quality.

## Interpretation

This is an actual generation feasibility result, not evidence of improved competitive layouts. Teacher-forced validation loss improved early and then deteriorated; fitting loss continued to improve. Free samples show disconnected regions, weak terminal organization and excess loops. A lower source-prefix likelihood loss cannot substitute for generated-sample validation. Exact reconstruction edge IoU is not applicable because generated node counts/positions differ from any particular source.

The experiment exposes several hypotheses worth testing separately: inadequate graph-state history, sampling drift after errors, a weak count distribution, and insufficient independent organizations. They are not proven causes. Compare free-generated samples and whole-graph statistics when changing the architecture; don't merely lengthen training or hide defects with connectivity repair. A future game brief may condition required terminals, but that constraint should be explicit rather than presented as learned behavior.

No compile, source VMAP edits, new annotation requests or Hammer export occurred. The [corrected report](output/training/progressive-layout-v2/report.md) and [six fixed samples](output/training/progressive-layout-v2/samples.png) record the output.

## Completed graph-state follow-up

`train_graph_state_layout.py` adds two directed message-passing layers to each completed prefix, pooling newest-node and whole-prefix embeddings into the recurrent input. It recomputes context from the actual completed graph at sampling time. Every training prefix masks future nodes and links; tests verify no future-state leakage, sensitivity to different neighbors at identical degrees, and training/sampling context agreement. The baseline sampler was refactored through a hook without altering output; its first six saved samples reproduced exactly.

Artifacts: `output/training/graph-state-layout-v1`. Same five full fitting maps, normalization, source-order/mirror seeds, optimizer, learning rate, 1000 steps and Cobblestone selection. No Train or reserved-map loading. Checkpoint selected at step 700 and saved before producing 32 fixed samples (7100–7131). No sample repair or rejection. A reloaded checkpoint reproduces the first generated sample exactly. Thirty-four relevant checks pass.

The change improves some connectivity measures: all four directed spawn/site access pairs rise from 2/32 to 7/32; all terminal roles appear in 8/32 versus 11/32; mean isolated-area fraction falls from 10.2% to 5.6%. However, mean neighbor degree rises from 4.10 to 6.26 (fitting sources 2.77), and cycle rank per node rises from 1.19 to 2.21 (sources 0.40). Mean normalized link length also rises from 0.148 to 0.161 (sources 0.100). Validation loss is worse: 16.936 versus 16.100. Additional links can account for improved reachability without better strategic organization.

This is a mixed development result, not a successful radar generator or proof of greater design variety. The graph-state model has more parameters and no capacity-matched ablation was run. It improves connectivity while worsening the excess-link problem. Graphs, positions and defects remain visible in the saved comparison; no diagram has been presented as a floorplan. The bounded experiment is complete rather than automatically extending training.
