# Geometry completion experiment v1

## Fixed experiment

Training maps: Dust2, Anubis, Cache. Validation map: Cobblestone. Test map: Train (the reconstructed outer-yard/T Main/Ivy/Popdog section only). All Train examples are excluded from training and checkpoint selection. Reserved corpus maps remain unused. The new model starts from random weights; earlier semantic or coarse-layout checkpoints are not loaded.

Inputs and targets are 16 x 32 x 32 volumes at 32 Source units per cell, with two distinct channels: recorded NAV walking surface and native editor/static-prop render surface. Patch anchors normalize local elevation without providing map identity or place names. Original source geometry and NAV remain cached separately. Surface voxelization uses adaptive triangle samples, not solid occupancy, collision or validated cover.

The test removes a connected 12 x 12 XY region across all 16 height layers (384 x 384 x 512 units). Unknown cells are zero in both input channels and are distinguished by two explicit per-channel known-source masks. Training varies connected mask size/location and rotates sections in XY. No hidden target is an input feature.

A small 3D U-Net is trained locally on the 4080 Super for 60 epochs. Class weights come only from training examples. Cobblestone validation loss selects the checkpoint. Train predictions are computed after checkpoint selection. Threshold is fixed at 0.5; test scores are not used for architecture, threshold, baseline, checkpoint or epoch selection within this run.

Baselines: empty completion, boundary interpolation per height/channel, and nearest training section at four XY rotations using only visible context. The displayed baseline is selected by validation mean IoU. Test metrics include hidden-volume IoU, F1, precision/recall, balanced accuracy and surface prevalence. Accuracy alone is not useful for sparse surfaces.

An additional passage check compares local connectivity in assembled walking-surface voxels. It uses four XY neighbors with a maximum one-cell elevation change and excludes ladders. It is an undirected geometric proxy, not the original directed NAV, collision, player clearance, timings or gameplay quality.

The first eight fixed Train examples are displayed, without selecting attractive results. Raw predictions, retrieval neighbors, checkpoints, history, source hashes and metrics are saved. Checkpoint reload predictions are compared numerically.

## Limits and next decision

Overlapping crops within one map are not independent map examples. Five maps and one held-out map section cannot establish broad generalization. Unsupported source models, decorative/render surfaces and grid sampling affect the targets. Ladders and physics geometry remain unmodeled. This is learned missing-geometry reconstruction, not complete map generation.

The immediate decision is whether the trained model improves on the baseline on the excluded Train section, especially walking surfaces and local passage preservation. A failure remains a reported failure; a lower training loss is not success. More maps should be added to this automated dataset only after interpreting the held-out results and representation limits.


## Completed result and follow-up

Coverage-aware dataset: output/geometry-completion-dataset-v2. Unavailable mesh geometry outside extraction bounds is unknown, not an empty training label. 576 training crops, 96 Cobblestone validation crops, 96 Train test crops. The 366,546-parameter model trained on the 4080 Super for 60 epochs and selected epoch 34 by validation loss. Checkpoint reload predictions match exactly. Twenty-eight focused checks pass.

The fixed 0.5 decoder failed the strongest baseline: mean test IoU 0.494 versus interpolation 0.567. Results are preserved in output/training/geometry-completion-v2.

The follow-up decoder searched only Cobblestone validation predictions, selected a 0.9 walking threshold with one height peak per contiguous surface cluster, and retained 0.5 for mesh surfaces. Separate height clusters remain separate floors. Configuration was saved before loading Train predictions; trained weights were unchanged. This is development evidence after the v2 test was observed, not a fresh blind test. Artifacts are in output/training/geometry-completion-calibrated-v1.

Calibrated Train walking IoU 0.597 versus 0.551 interpolation; mesh IoU 0.572 versus 0.583 interpolation; mean IoU 0.584 versus 0.567. Walking-voxel passage preservation 917/947 (96.8%) versus 838/947 (88.5%). False voxel connections 55/461 (11.9%) versus 54/461 (11.7%). This does not certify collision, directed NAV traversal or map quality. The first eight fixed test examples include failures and are not selected by performance.

The pipeline now trains actual geometry completion, but improvement over interpolation is modest and incomplete. Next corpus expansion should use approved maps through the automatic extractor and a fresh entire evaluation map, retaining supported-source masks and reporting both missing and spurious passages. No complete map generator is claimed.
