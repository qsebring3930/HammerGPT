# Semantic layout pipeline

Floorplan generation is paused in `generation-policy.json`. The five radars in preference round 002 are a rejected set. Their geometry is preserved for diagnosis, not repaired. Legacy sampling, preference-batch generation and radar-three revision entry points enforce this pause.

## Why the five share a signature

The legacy sampler places spawns and objectives at exterior extremes, selects Mid near the origin, then links nearby positions. Connectivity and planar geometry determine its route structure. The preference scorer ranks this same family; it cannot supply missing gameplay relationships. That produces long connector strips, a central junction knot, terminal objectives, and perimeter branches that reconnect without an evidenced tactical effect. Changing shapes or adding graph cycles does not change this construction process.

The benchmark reads the saved layouts without modifying their floors. Geometry statistics describe the signature; they are not quality scores. Missing tactical evidence is reported as unverified, rather than claiming that every visually similar path is proven equivalent.

## Four explicit stages

1. **StrategicPlanner** compiles coordinate-free gameplay intentions into typed places, directed team/phase relationships, ordered route witnesses, deployment assignments and complete site systems. `generate(brief)` expands route intentions into those relationships; `plan(brief)` validates the schema. Coordinates are prohibited. Every connection needs a purpose and evidence or an explicit design contract. This is a semantic proposal/compiler API, not a newly trained neural generator.
2. **GameplayValidator** checks contracts and outcomes, validates claimed roles, groups strategically equivalent routes, and rejects redundant or unproven alternatives. Its output carries the exact plan digest, blocking findings, convergence, contact claims, rotations and cycle purposes.
3. **SpatialEmbedder** uses OR-Tools relative constraints to assign abstract XY positions and levels only to a passed, unchanged plan. It preserves relationship identities and checks explicit elevation transitions. This initial embedder does not yet prove physical travel time, visibility or firing angles; those require geometry-aware verification before its embedding can certify competitive behavior.
4. **GeometryGenerator** is a gated backend interface. It requires the same passed plan and embedding, then checks the generation policy before invoking a backend. No new floor backend was executed during this refactor. A future backend must measure physical outcomes against the strategic contract; preserving IDs alone cannot certify those outcomes.

## Gameplay representation

Places distinguish deployment areas, A/B objectives, attacker staging, entry zones, defender positions, fallback and retake areas, Mid candidates, connectors, encounter spaces, chokepoints and vertical transitions. Relationships distinguish deployment, primary and secondary attacks, defensive access, rotations, contests, connector access, retreats, conditional flanks, vertical movement, engagements and control pressure.

A site object owns staging, entries, defense access, fallback/retake paths and multiple engagement interfaces. Attack routes terminate at an entry/engagement interface rather than the objective object. A spawn owns assignments with distinct outcomes. Defender commitments identify a tradeoff and a witnessed switching/rotation route.

Mid requires independent T/CT deployment access, supported arrival windows, and control pressure on at least two meaningful destinations. Staging requires a witnessed preparation role on an attack route. Encounters require compatible local team arrival evidence. Chokes require supported local access constraints. Vertical movement specifies stairs/ramp/drop/boost and direction.

## Equivalence and purposeful alternatives

Every route outcome has destination, timing interval, engagement context, entry angle, elevation, defender bypass, engagement range, information, retreat capability and rotation capability. Each fact has `value`, `status` and `source`. Reviewed, observed and explicit design-contract facts are supported; unknown and geometric proxy facts are not. A design contract expresses intended behavior, not a measured result.

`compare_outcomes` returns:

- **distinct** when at least one supported tactical effect differs;
- **equivalent** when every required effect is supported and effectively the same;
- **unverified** when evidence cannot establish either conclusion.

Capability sets ignore ordering. Engagement sequences retain it. Conservative complete-link grouping avoids merging routes through nontransitive timing tolerances. Every secondary route identifies its comparison route; mere additional geometry never supplies a tactical difference.

An independent reconnecting cycle needs two directed, same-team/phase branches from a shared divergence to a shared rejoin. A supported branch-local effect and purpose must explain the detour. A different fight *after* reconnection does not justify it. Current cycle checking covers a cycle basis, not every possible compound simple cycle; exhaustive alternate-path analysis remains a limitation.

Prototype comparison defaults are 2 seconds for timing equivalence, 30 degrees for angle difference, and 64 units for meaningful elevation difference. Contest defaults are a 4-second arrival gap and a 45-second latest initial contest. These are configurable engineering assumptions, not calibrated Counter-Strike design laws.

## Benchmark and remaining evidence

Proposal 001 adds actor/phase-scoped cycle analysis: an undirected union of opening attacks, retakes and conditional flanks is retained as a diagnostic, rather than automatically treated as a same-actor route choice. Relation phase tags describe declared availability; physical availability across phases still needs verification. They cannot hide an otherwise traversable meaningless loop. `propose_semantic_blueprint.py` compiles one authored strategic proposal into `output/strategic-proposal-001`; it is not a trained-model sample and does not invoke embedding or geometry.

Run `.tools/training/Scripts/python.exe benchmark_semantics.py`. It writes readable blueprints, full JSON reports and a diagnosis in `output/semantic-validation-v1`. All five rejected layouts are blocked for structural semantic omissions. Synthetic positive contracts pass; redundant alternatives, unsupported Mid, incomplete sites/deployments and meaningless rejoining branches fail. Geometry remains paused even when a synthetic contract passes.

Dust2, Anubis, Cache, Train and Cobblestone pass through the same representation and validator. Their reviewed NAV encounter/choke organizations have five different structural signatures. This demonstrates different observed route contexts, not full tactical identity or competitive-quality certification. Reference plans remain incomplete because timing, entry angles, information, defense commitment and several site-system roles have not all been evidenced. Static encounter opportunities are not observed fights. Centroid-path travel estimates remain proxies. Train's reviewed Ivy-to-B route remains a conditional later flank.

The next implementation work is semantic proposal selection plus defensible evidence extraction and physical contract verification. The current benchmark is a rejection gate, not proof that a learned generator has improved. No training run, new floorplan or geometry repair occurred in this refactor. Node, edge and cycle counts remain diagnostic statistics only.
