# Strategic floorplan prototype: first bounded result

The prototype produces three readable floorplan proposals from variable route graphs. This demonstrates connected geometry and structural variation, not competitive map quality or improved neural generation. No training or Hammer export occurred.

Current artifacts: `output/strategic-floorplan-v6`.

![Three candidates](output/strategic-floorplan-v6/comparison.png)

## How to read them

Bright blue-gray is proposed walkable floor; dark space is inaccessible. Dark blocks inside the floor are proposed cover. A/B are the two objectives. Clean radars show physical geometry; route overlays add gold T approaches, cyan CT distribution, purple site rotation and rings at approximately equal-arrival places. Rings are estimates, not reviewed battleground labels. White cross-lines indicate entrances, not necessarily useful tactical chokes.

| Candidate | Organization | Weakness visible in the estimates |
|---|---|---|
| 1, seed 9398 | Primary attacker approaches split early; defender distribution is shorter than attacker access. | T-to-B is 31.9s versus 18.6s to A; site rotation is 25.4s. |
| 2, seed 10505 | Primary approaches share intermediate places before splitting toward A/B. | T reaches B in 16.2s versus CT's 20.2s; defender distribution needs revision. |
| 3, seed 10763 | Separate primary approaches with a shorter, 16.0s site rotation. | T-to-A is still long at 31.7s. |

Times are constant-speed geometric proxies at 250 units/s, with a 32-unit raster and 16-unit disk clearance. They omit acceleration, utility and combat. Opening estimates forbid traversing the other site or opposing spawn region; rotation estimates forbid both spawn regions. Those are explicit prototype conditions. They do not describe every viable match route.

Full-size radars and explanatory overlays:

- [Candidate 1](output/strategic-floorplan-v6/candidate-1/radar.png) · [routes](output/strategic-floorplan-v6/candidate-1/routes.png)
- [Candidate 2](output/strategic-floorplan-v6/candidate-2/radar.png) · [routes](output/strategic-floorplan-v6/candidate-2/routes.png)
- [Candidate 3](output/strategic-floorplan-v6/candidate-3/radar.png) · [routes](output/strategic-floorplan-v6/candidate-3/routes.png)

## Construction and evidence

Random separated positions provide possible planar connections. Roles are assigned under spawn/site placement constraints. The search samples edges rather than filling a fixed three-lane skeleton. Footprints vary between courts, elongated galleries and small transitions; broad passages may merge at declared local junction aprons. Planned nonincident passages cannot cross. Covers are subtracted from the saved floor.

The final search tried 2,200 seeds: seven candidates passed its constraints and occupied five archive bins. Three were selected using route sharing and relative rotation cost. Rejections, all accepted proposals, selected layouts and the exact generation script are saved. Zero geometric repairs were made. Earlier attempts are preserved separately; the final version reduced the overly dense connection budget.

Duplicate detection ignores node names, A/B renaming and degree-two connector subdivisions, while preserving parallel alternatives. Selected graphs are non-isomorphic under that coarse definition. This does **not** prove full strategic equivalence or player-perceived novelty: timing, exposure and decision utility still need evaluation. Route sharing measures the selected primary route pair, not all possible opening paths.

For each selected candidate, an independent audit reconstructs the floor from saved room/passage polygons minus cover, checks every one of ten spawn points, and verifies planned and displayed routes against the eroded geometry. All three passed. Six tests passed, including bogus spawn detection, a wall forcing a physical detour, subdivision/site-name invariance and different distribution at equal edge count.

Dependencies are recorded in `requirements-floorplan.txt`; Shapely was installed into the existing local project environment. Reviewed Dust2 roles and Train's corrected conditional-flank distinction provide semantic context. This prototype does not learn geometry or dimensions from those annotations.

## What remains weak

All layouts are flat. Architectural shapes and cover remain crude; many passages are still long. Mid is currently a central candidate place, not a proven strategic role. Center-to-center visibility is recorded only as a planar proxy. Headroom, CS2 collision, elevation, utility, sound and competitive balance remain unverified. No source map was edited.

The immediate design work should address the visible long approaches and defender distribution failure, then test whether useful decisions survive better architectural realization. More training is not yet justified by these images alone.
