# Layout design brief after v3 playtest

Reference: [Exodus, The dos and don'ts of Counter-Strike level design](https://steamcommunity.com/sharedfiles/filedetails/?id=1110438811).

The guide describes context-dependent design principles, not universal quotas. The v3 generator translated complexity feedback into minimum branching and loop counts. That did not establish tactical usefulness. Its exporter also turns every coarse navigation landmark into a large rectangular room and every link into a uniform 192-unit corridor. Navigation partition boundaries are not architectural room boundaries.

## Verified problems in v3

- CT-to-A routed centerline shortest distance: 1,216 units, one connection.
- CT-to-B: 7,744 units, seven connections, through A and several central areas.
- T-to-B: 6,144 units. These are route-centerline distances, not in-game arrival times or chokepoint timings.
- Removing SiteA disconnects CTSpawn and Junction16 from B and the remaining map. CT has no independent distribution route to B.
- Junction1/Junction12/Junction3 form a triangle. Junction3 is its only attachment to the wider map; the other two areas contain no spawn or objective. The loop does not provide a separate approach, rotation, or flank to a different part of the map. Cover, saving or other locally useful play has not been established there.
- Twenty rooms and 25 corridor components demonstrate faithful export, not coherent level design. Eight branch areas and six cycles are insufficient quality measures.

## Guide-informed design priorities

1. Establish a readable backbone with defender distribution to both sites, attacker approaches, and a contested central region. Roughly three initial fronts is a starting hypothesis for a conventional 5v5 layout, not a mandatory count of junctions.
2. Separate regional roles: staging, chokepoint, site approach, defender access, rotation and post-plant/retake space. Some graph nodes should describe transitions or route bends instead of rooms.
3. Give each optional connection a defensible benefit: another attack direction, withdrawal/repositioning, a rotation, or a travel-versus-exposure tradeoff. A loop attached at one junction needs demonstrated local value; it must not satisfy a general complexity quota by itself.
4. Measure defender/attacker arrival at proposed fronts and site-to-site rotations. Defender access should support taking positions before an execute. Paths must be reviewed for exposure and control, not distance alone.
5. Create broad continuous gameplay spaces, with local narrowing where a choke is intended. Vary shape, width and sightline structure; avoid a universal square-room/narrow-corridor template.
6. Evaluate initial attacks and retakes separately. Entrances and cover must support the post-plant reversal of attack direction.
7. Treat utility, readable navigation, sightlines, sound and weapon-range variety as part of spatial design. Graph connectivity cannot certify them.

## Concrete next implementation

Replace blanket minimum-eight-branches/minimum-six-cycles requirements with a tactical backbone proposal and contextual route checks. Require a CT distribution path to each site without traversing the other objective in this conventional single-level prototype. Flag objective-free side cycles that attach through only one articulation point; retain one only with an explicit reviewed purpose. This is a prototype-specific acceptance condition, not a claim that all successful Counter-Strike maps obey it.

Review the backbone before rendering. The next graybox should include independent CT access to B and remove or repurpose the Junction1/12 side loop. Group navigation landmarks into gameplay spaces and transitions rather than materializing every landmark as a room. Any manual/solver repair must be recorded separately from learned predictions.

Use the same semantics to revise training targets on approved references. This brief does not retrain the model, certify tactical labels, or modify v3. More map data alone cannot repair the current abstraction.
