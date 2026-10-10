# Research: strategic diversity and spatial generation for CS2

Research date: 9 October 2026. Scope: comparison and representation proposal only; no generator changes, training, or installations.

## Recommendation

Build a hybrid planner that varies strategic organization, realizes it as connected floor geometry, and retains multiple distinct valid candidates. Keep the existing VMAP/NAV extraction work. Use learned models as proposal sources rather than treating their graphs as finished maps.

This is an architectural recommendation, not evidence that the proposed system already generates good competitive maps. The research below supports individual components; none demonstrates an end-to-end CS2 bomb-defusal solution.

## Six systems compared

### 1. Procedural Generation of First Person Shooter Maps using MAP-Elites

Primary source: [2026 preprint, full paper](https://arxiv.org/html/2605.30570v1). Posted 28 May 2026; publication status here is arXiv preprint.

| Question | Finding |
|---|---|
| Representation | Point-Line encodes room endpoints, sizes and an L-shaped corridor orientation. Spatial-Layout encodes rectangular room sizes, guiding segments and separation. |
| Topology versus geometry | Point-Line directly couples them. Spatial-Layout solves positions, then constructs connections; it does not start with a fixed strategic graph. |
| Spatial embedding | Z3 enforces bounded, separated rooms near guiding lines. A Delaunay minimum spanning tree connects them; line intersections add links. |
| Quality | Kill-share entropy from five simulated 1v1 deathmatches. |
| Diversity | Sliding-boundary MAP-Elites archives: walkable area/symmetry and combat pace/average eccentricity. |
| Validity | Solver constraints and spanning-tree connectivity; infeasible solutions can be discarded. |
| Paths/decisions | Geometry-derived topology and simulated combat; not team objective planning. |
| Transfer | Connected geometry, spatial constraints, and an archive rather than one winner. |
| Do not copy | Rectangular rooms, 1v1 kill balance as bomb-defusal quality, or symmetry as sufficient strategic diversity. |

Limitations: redundant Point-Line encodings; poor Spatial-Layout mutation locality; simulation-dependent pace. Improved measured diversity/balance does not establish interesting tactical choices.

### 2. Sentient Sketchbook

Primary sources: [original paper](https://www.antoniosliapis.com/papers/sentient_sketchbook.pdf), [documented web service](https://www.sentientsketchbook.com/webservice.php).

| Question | Finding |
|---|---|
| Representation | Coarse tiles: traversable terrain, obstacles, bases and resources. |
| Topology versus geometry | Paths and regions are derived from the sketch; detailed terrain is interpreted afterward. |
| Quality | Resource safety, safe area and exploration, including balance between players. |
| Diversity | Feasible/infeasible novelty search proposes alternatives for human selection. |
| Validity | Accessibility checks require bases/resources to be mutually reachable. |
| Paths/decisions | Shortest paths, exploration and choke/open-space analysis; no CS2 team simulation. |
| Spatial embedding | Tiles already have positions; subsequent interpretation adds detail. |
| Transfer | An editable gameplay abstraction, immediate feedback, several different suggestions. |
| Do not copy | RTS resources, tile-based choke rules, or equal resource access as CS2 balance. |

The service documentation describes JSON-configurable generation and evaluation, including shooter configurations. That documents an interface, not evidence that its hosted service currently works. The original study is strategy-oriented; its path measures are useful examples of feedback, not ready-made CS2 rewards.

### 3. FI-MAP-Elites

Primary sources: [room-based generation paper](https://www.antoniosliapis.com/papers/a_general-purpose_expressive_algorithm_for_room-based_environments.pdf), [implementation](https://github.com/konsfik/FI-MAP-Elites).

| Question | Finding |
|---|---|
| Representation | Design Specification: room graph, areas and connections. Design Implementation: tessellation, room-cell assignments, doors. |
| Topology versus geometry | The supplied specification constrains generated geometry. |
| Quality | Feasible fitness measures room-area precision; infeasible fitness rewards partial constraint satisfaction. |
| Diversity | Separate feasible/infeasible archives indexed by plan and room compactness. |
| Validity | Connected rooms, prescribed adjacency/doors, area tolerances and passage widths; explicit repair operators. |
| Paths/decisions | Connectivity constraints, not simulated combat decisions. |
| Spatial embedding | Grid or Voronoi cells become connected room regions; doors lie on shared boundaries. |
| Transfer | Irregular regions, geometry constrained by topology, repair and near-feasible candidates. |
| Do not copy | Fixed graph as the entire diversity mechanism, compactness as fun, or its numerical width thresholds. |

Important limitation for our problem: holding the specification graph fixed preserves its connection organization. Diverse room outlines alone do not solve repeated strategic layouts. Repair is a legitimate construction tool; record it separately when evaluating a learned model's unaided predictions.

### 4. Dungeon Architect: Snap Grid Flow and Cell Flow

Primary sources: [Snap Grid Flow graph](https://docs.dungeonarchitect.dev/unity/snap-grid-flow/sgf-create-flow-graph/), [connections](https://docs.dungeonarchitect.dev/unity/snap-grid-flow/sgf-connections/), [Cell Flow overview](https://docs.dungeonarchitect.dev/unreal/cell-flow/cellflow-overview/), [Cell Flow settings](https://docs.dungeonarchitect.dev/unreal/cell-flow/cellflow-settings/).

| Question | Finding |
|---|---|
| Representation | Snap Grid Flow: paths on a 3D grid, mapped to modules. Cell Flow: partitioned cells merged into chunks with flow paths and heights. |
| Topology versus geometry | Flow operations and spatial/module constraints interact during construction. |
| Quality | Configured construction constraints; the cited documentation does not establish a competitive gameplay score. |
| Diversity | Procedural paths, branches, cycles, module choices and cell arrangements; not a quality-diversity archive. |
| Validity | Connection/module compatibility, cell constraints, retries and finalization. |
| Paths/decisions | Explicit flow paths; dungeon progression operations are not team tactical reasoning. |
| Spatial embedding | Stitch modules through portals, or realize irregular cell chunks at specified heights. |
| Transfer | Explicit portals, controlled branch construction, irregular footprints and vertical connections. |
| Do not copy | Mandatory quest backbone, keys/locks, or a grid/module palette as a CS2 design rule. |

These are Unity/Unreal tools, not Hammer integrations. Their architecture is relevant even without adopting the products. Snap Grid Flow should not be confused with the older Snap Flow documentation, which has different cycle limitations.

### 5. Edgar-DotNet

Primary sources: [official repository](https://github.com/OndrejNepozitek/Edgar-DotNet), [performance guidance](https://ondrejnepozitek.github.io/Edgar-DotNet/docs/other/performance-tips/).

| Question | Finding |
|---|---|
| Representation | Supplied room-connectivity graph plus polygonal room templates and allowed door positions. |
| Topology versus geometry | Connectivity is input; template selection and placement realize it. |
| Quality | Geometric fit and configured requirements, not combat quality. |
| Diversity | Template variants, transformations and placements; a fixed graph remains fixed topology. |
| Validity | Placement and doorway compatibility constrain realizations; some graphs are difficult to generate. |
| Paths/decisions | Room connections, not timing, visibility or tactical route choice. |
| Spatial embedding | Place templates and connect doors directly or through corridor rooms. |
| Transfer | A concrete graph-to-polygon/portal contract; .NET implementation is worth examining for bridge compatibility. |
| Do not copy | A dungeon room for every NAV region, template-only architecture, or 2D placement as sufficient for vertical maps. |

Official guidance recommends smaller graphs and describes incremental subgraph placement. This reinforces a practical separation between coarse design regions and fine navigation patches. Language compatibility alone does not make it a Hammer exporter.

### 6. G-PCGRL

Primary sources: [original paper](https://arxiv.org/html/2407.10483v1), [official implementation](https://github.com/FlorianRupp/g-pcgrl).

| Question | Finding |
|---|---|
| Representation | Adjacency matrix; diagonal fixes node types. Graph-narrow edits a selected edge; graph-wide can select an edge anywhere. |
| Topology versus geometry | Generates graph connections only; no physical embedding. |
| Quality | Reward for improving constraint validity, with a completion bonus. |
| Diversity | Multiple graphs satisfy the rules; no demonstrated archive of strategic behaviors. |
| Validity | Required/allowed connections between node types. This does not establish spatial or tactical validity. |
| Paths/decisions | Evaluated on economies and skill trees, not spatial player decisions. |
| Spatial embedding | Absent; would need a separate constrained geometry system. |
| Transfer | A possible learned graph-edit policy after strategic constraints are defined. |
| Do not copy | Domain-inferred edge direction or local type-adjacency rules as complete CS2 correctness. |

The reported experiments use small graphs, up to ten nodes. The repository notes limits including per-type connection-count constraints and scaling. This is a future proposal mechanism, not a reason to begin RL now. A faster policy cannot compensate for an inadequate validity or quality definition.

## What this changes in our diagnosis

Our [recorded experiment](progressive-layout-experiment.md) generates coarse NAV-region graphs, coordinates and descriptors. The graph-state follow-up improved some access counts, but increased excess connectivity: mean degree rose from 4.10 to 6.26 versus 2.77 in fitting sources. Directed access to all four spawn/site pairs occurred in 7/32 samples. Those checks do not certify access from every spawn point, physical corridors, or tactical quality.

Our [earlier design brief](layout-design-brief.md) also documents a separate exporter problem: converting navigation landmarks into rectangular rooms and links into uniform corridors. The authored radar illustrations were another separate system; their polish was not a measured capability of the local trained generator.

These observations support a representation/realization gap. They do not yet prove that the neural model's outputs all share the same strategic organization: we need an equivalence test to measure that, rather than inferring it solely from ugly graph drawings.

The closest paper offers connected geometric candidates and an archive; our current pilot offers neither. Conversely, simply replacing our pilot with fixed-graph room placement would still allow the exact repetition you object to. We need both variable strategic graphs and constrained realization.

## Proposed CS2 representation

The following is our design proposal, informed by the comparisons above. Its usefulness remains to be tested.

### A. Strategic places and route families

Represent a small graph of gameplay places, independent of the number of NAV polygons:

- T and CT spawn regions with their actual spawn points.
- A/B objective regions, each allowed to span several physical patches.
- Staging spaces, encounter spaces, distribution junctions and connectors. Roles can overlap; an encounter is not automatically an enclosed room.
- Transitions with intended choke roles, rather than calling every graph edge a choke.

Store route families over this graph: team, target, phase, ordered places, divergence and convergence, approach direction, and conditional use. Distinguish opening attacks, defender distribution, rotations, flanks, retakes and withdrawals. Leave uncertain purpose unknown.

Preserve your Train correction: the Ivy-to-CT-to-B route is a **conditional later flank if attacking A through Ivy is too dangerous**, not an opening B route.

Team control is phase-dependent evidence or a prediction, not a T-only/CT-only physical access restriction. The same doorway can support different roles after a plant. Mid should describe a relevant contested/distribution role, without forcing every map into a central cross.

Allow mutations of strategic organization: which fronts share staging, where routes split, whether mid feeds one or both sites, and how defenders distribute/rotate. Changing dimensions around a fixed route backbone must not count as strategic novelty.

### B. Physical regions, portals and elevation

Each strategic place maps to one or more connected floor polygons with height, boundary/occluder data and coverage provenance. Adjacency exists through actual portals, not merely nearby region centers.

Portals encode location, width, clearance, direction and movement type: walking, stairs, ramp, drop or boost. A reversible stair and a one-way drop are different connections. Boost-dependent paths require their own capability profile.

Relative placement constraints can express separation, ordering, approach sectors and elevation relationships without imposing absolute coordinates or a fixed rectangular arena. Overlapping XY footprints are legal on separate levels; transitions must explicitly connect those levels.

A geometric solver/search realizes the strategic proposal using irregular regions and portals. It may repair proposals, but every repair must be recorded. After realization, derive the actual traversal graph again: added accidental doorways or blocked planned connections change the strategy and require re-evaluation.

This takes constrained realization from the research without assuming that rectangular rooms or an MST produce appropriate CS2 decisions. The radar then renders these same physical polygons; it is not a second generator inventing a nicer-looking map.

### C. Timing and visibility as separate relationships

Travel estimates use traversable portal-to-portal paths, movement speeds and vertical-transition costs. Graph hop count and straight-line distance are insufficient. Measure T/CT arrival at each contest and defender site distribution/rotation separately. Record assumptions; estimates need eventual Hammer/CS2 validation.

Maintain a separate visibility relationship derived from sampled positions, eye heights and occluding geometry. Visibility is not traversal: players may see across a space without being able to cross it. Evaluate approach exposure, crossfire possibilities and opportunities to break sightlines. Unknown occlusion data cannot certify a sightline test.

Utility, sound, team coordination and real match balance remain later validation needs. A coarse geometry score should be labeled as a proxy, not presented as win-rate evidence.

### D. Strategic path equivalence

Compare routes by their decisions, not just their polylines. A proposed signature contains:

`team + phase + objective + ordered decision regions/bottleneck sets + approach sector/elevation + timing/exposure bands + movement requirements`

Two corridors that diverge briefly and rejoin before the same mandatory choke, with similar arrival/exposure and no useful intervening position, are candidates for one strategic route family. A route reaching a different site entrance, bypassing a contest, enabling a withdrawal, or trading speed for exposure can be a meaningful alternative.

This is an approximate, context-dependent equivalence test. Preserve differences when timing, cover or elevation changes the choice. Flag objective-free side loops for explanation rather than deleting them automatically: a local repositioning or saving space can be useful.

Canonical comparison should ignore arbitrary node IDs, camera rotation and equivalent relabelings. Renaming A/B or mirroring an otherwise equivalent decision graph must not inflate strategic diversity.

## Search, validity and diversity

Keep separate feasible and near-feasible candidate pools. Feasibility requires physical reachability for the intended movement profiles, terminal presence, intended connections, usable portal clearances and consistent elevation. Check every actual spawn point. Geometry missing the necessary evidence remains unverified.

For our initial prototype, require independent defender distribution to each site without traversing the other objective. This is an explicit design brief condition, not a universal law for every Counter-Strike map.

Do not reward arbitrary edge count or cycle count. Start an archive with only two strategic descriptors to avoid spreading a small search across too many empty bins:

1. **Opening-route sharing:** how much viable attacker site approaches share staging and bottlenecks before their first contests.
2. **Defender rotation cost:** geometric A/B rotation time relative to opening distribution time.

Track mid dependence, approach directions, contest arrival differences, vertical choices and role-graph equivalence alongside those bins. Reject strategic duplicates even when their room outlines differ. These descriptors are proposed measurements; first calibrate them against the already approved references. They are not established correlates of player enjoyment.

Within bins, assess access correctness and explicit brief compliance first, then timing/exposure proxies and route purpose. Do not collapse everything into an unvalidated “fun” number. Human review selects among readable alternatives; actual playtests eventually supply stronger quality evidence.

## Bounded next step, after approval to implement

Build one small representation-and-realization prototype using existing extracted data and reviewed roles. No new annotation campaign, engine rebuild, mass map ingestion or RL run is needed to test this architecture.

Its deliverable should be **three readable floorplan radars with different strategic organizations**, generated from the same broad brief. For example, candidate structures can differ in shared versus separate attacker staging, where mid access enters the sites, and defender rotation organization. Those are dimensions to vary, not three permanent authored templates.

Acceptance evidence:

- Each image comes from its candidate's actual floor polygons and portals.
- All intended access routes survive physical realization; one-way/elevation changes are explicit.
- The three candidates differ under the strategic-equivalence comparison, not just shape or orientation.
- Each has a short overlay explaining site approaches, first contests and rotations, with estimated timings clearly labeled.
- Unedited output and any solver repairs are saved separately. If fewer than three distinct valid candidates are produced, report that result directly.

Only after this produces understandable alternatives should we compare learned proposals with procedural proposals under the same constraints and archive. Additional approved maps can improve priors and calibration then; adding maps before this test would not establish that we fixed the repetition.

## Research boundaries

Paper and official documentation claims were checked online. This was not a source-code audit or an execution benchmark of external packages. The FPS paper links its implementation, but that repository was not successfully inspected in this research pass. Hosted Sentient Sketchbook availability was not tested. No claim here establishes that one of these packages can directly export a working CS2 VMAP.
