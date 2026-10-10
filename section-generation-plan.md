# Geometry-first section generation experiment

The previous generator used coarse named areas and graph connections, then authored rooms and corridors. Its connectivity checks did not measure coherent playable structure. The five-map semantic encoder has weak held-out generalization and is not a layout generator.

## Current reconstruction gate

Reconstruct Train outer yard, T Main, Ivy and Popdog from the approved repaired source. Retain exact XYZ NAV polygons, directed adjacency, flags, edge references, external connections and ladder references. Expand editor mesh faces and supported static prop render sources separately. Preserve object occurrences even when decompiled nodeID values repeat.

The canonical geometry is triangles plus original NAV polygons. A derived 32-unit XY input stores interpolated surface heights and area identity, including multiple heights at the same XY. Small polygons retain centroid fallback samples. No synthetic corridors or boundary walls, no flattening, no conversion of each area to a rectangular room.

Editor/render ray intersections are geometric observations only. They are not verified sightlines, collision, cover, opacity or bullet penetration. Missing model sources, unsupported model classes, excluded helpers and omitted traversal must remain visible in the audit.

## Before training

Compare the reconstruction with the source section, including railcar routes, T Main and Ivy entries, Popdog elevation, under/over relationships, and the section's external connections. Preserve reviewed meeting/choke contexts without inventing timing or control labels. Resolve gameplay-significant geometry omissions and decode ladder endpoint/traversal data.

## Section dataset and first learned experiment

Use spatial sections containing an approach, contested space and exits. Store local coordinates, multiple walking layers, source surfaces, geometric observation features and directed entry/exit topology. Crops from a single map belong to one data split; nearby overlapping crops are not independent validation examples. Keep the reserved evaluation maps outside training.

Start with a masked reconstruction task on the five reviewed maps: recover deliberately hidden surface/obstruction patches and withheld local links from their surrounding context. Compare against copying the nearest training section, a geometric interpolation baseline and the existing coarse graph baseline. Success means recovering held-out geometry and traversal relationships, not merely reducing training loss.

Only after held-out reconstruction improves should we attempt conditioned section generation and section assembly. Test route exposure, alternative approaches, elevation continuity, entrance clearance and useful rotations. Collision-aware and timing-aware tests require resolved collision and traversal data; connectivity alone cannot certify layout quality.

No new model training is claimed by the reconstruction experiment.
