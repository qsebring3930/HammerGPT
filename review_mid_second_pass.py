"""Read-only experiment report, including rejected revisions."""
import json
from pathlib import Path
from PIL import Image,ImageDraw
from map_layout import font
from inspect_planar_paths import inspect
ROOT=Path(__file__).resolve().parent
def run():
 root=ROOT/'output/mid-frontage-001';out=root/'review';out.mkdir(exist_ok=False)
 base=root/'after-r1/seed-974021';after=root/'second-pass-r4'
 sheet=Image.new('RGB',(2400,1200),'#101923')
 for i,(folder,label) in enumerate([(base,'FIRST COMPOSITION'),(after,'SECOND PASS — SAME TOPOLOGY')]):
  im=Image.open(folder/'clean.png').copy();d=ImageDraw.Draw(im);d.rectangle((0,0,1600,145),fill='#101923');d.text((65,30),label,font=font(35),fill='white');d.text((65,85),'Seed 974021 · contested Mid · identical image scale · Stage 4 paused',font=font(23),fill='#c0d1dd');sheet.paste(im.resize((1200,1200)),(i*1200,0))
 sheet.save(out/'second-pass-comparison.png')
 inspect(base,out/'base-unrestricted',True);inspect(after,out/'relaxed-unrestricted',True)
 b=json.loads((base/'validation.json').read_text());a=json.loads((after/'validation.json').read_text());p=json.loads((after/'composition.json').read_text());config=p['second_spatial_pass']['configuration']
 text=f'''# Mid experiment and second spatial pass

Stage 4 remains paused. User rejected the emerging cross-square scaffold during the Mid experiment; further Mid batch generation stopped. Initial candidates and failures remain archived. Three requested Mid seeds (974021, 974053, 974089), at most four attempts each: selected 974021, 974054, 974089 in four total attempts. 974053 failed physical connectivity. Their geometric frontages varied, but all retained the flank/cross scaffold and were not accepted visually. These are regression evidence, not an architectural success.

The shared Mid frontage rules were subsequently restricted to offset one functional frontage family, rather than slanting every lane. Mid placement search now allows a left/centre/right interior position rather than always (2,2). This shared revision passes the existing Mid unit case; no additional visual batch was run after the user's steering. The original working JSON pipeline remains usable. A new optional, separate CLI now prototypes the requested second spatial pass on an existing frozen candidate. It is not automatically enabled in map_layout.py.

## Mechanical prototype

First composition is frozen seed 974021. Second pass acts on playable spaces and their surrounding solids together through a continuous piecewise-affine district map. Horizontal compression {config['x_compression']}, vertical compression {config['y_compression']}, deployment displacement {config['deployment_offset']:.2f} plan units, site stagger parameter {config['site_stagger']:.2f} plan units. Provisional scale remains 32 HU/plan unit. A single broad district field is used, not one random bend per lane. Space roles, space adjacency, strategic networks and independent main/Mid relationships remain unchanged. Apertures are reconstructed on actual mapped shared boundaries with original nominal widths. Fixtures, plant areas, annotation positions and route support waypoints are transformed jointly. Ordinary generator outputs remain preserved.

![Matched first and second composition]({(out/'second-pass-comparison.png').as_posix()})

**Visual finding: this remains a cross-square scaffold. It is compressed and offset, not a new architectural organization.** Passing physical checks proves this mechanical relaxation can operate safely on this candidate. It does not meet the user's desired organic architecture or establish strategic variety. It is deliberately not promoted as the solution.

| Movement | First composition HU | Second pass HU |
|---|---|---|
'''
 for key in ('T-A-main','T-B-main','T-Mid','CT-Mid','CT-rotate'):
  text+=f"| {key} | {b['routes'][key]['path']['length_HU']:.0f} | {a['routes'][key]['path']['length_HU']:.0f} |\n"
 text+=f'''
Full ordered movement lengths, not calibrated travel timing. Unrestricted routes, connector subsets and sampled planar rays are available separately in validation/diagnostics. Soft compact preference: first {b['compactness']['achieved']}, second {a['compactness']['achieved']}.

![Unrestricted movement / sampled rays after second pass]({(out/'relaxed-unrestricted/movement-sightlines.png').as_posix()})

## Validation and history

Second-pass r1: three rejected constructions from numerical seams while dissolving transformed triangulated pieces. r2/r3: three rejected constructions each under the initial frontage end-margin assumption. r4: first attempt passes physical and request checks. Every revision has its own frozen sources and attempt summary; no output overwritten and no candidate-specific edits. An additional development diagnostic directly inspected the r3 seed-974021 failure and established that 8.19 plan units of shared frontage could fit its original 7-unit doorway, but failed the 1.6-unit authored end-margin assumption. The final fitting rule derives its 0.8-unit total end margin from the actual 0.8-unit wall thickness; this is an explicitly changed construction assumption, not a relaxed clearance/aperture acceptance gate.

Original doorway widths remain unchanged within numerical tolerance. Opening interference, clearance, disconnected space, undeclared openings, actual distinct site ingresses, independent main access, Mid access/pressure and unintended bypass checks all pass. Timing, utility, balance and vertical movement remain unverified. No false new tactical route is claimed by preserving topology.

Mapped vertices are jointly noded before transformation to keep neighboring spaces aligned. Declared 1e-7 plan-unit precision (0.0000032 provisional HU) permits a twice-precision tolerance for shared-boundary collinearity only. The physical width and navigation checks remain unchanged; no disconnected components are filtered out. Numerical tolerance is far smaller than player clearance. No-height/scale inference from radar or NAV is involved.

69 regression tests plus four new second-pass tests pass. They check physical/request gates, unchanged topology, retained actual doorway widths, reduced movement, source immutability and seed reproducibility. The complete program hash repeats deterministically, saved in second-pass-r4/reproduction.json. Test success is independent of visual quality.

## Reproduction

Run from HammerGPT, using a fresh output path:

```powershell
.tools/training/Scripts/python.exe output/mid-frontage-001/second-pass-r4/source/organify_layout.py --candidate output/mid-frontage-001/after-r1/seed-974021 --output output/mid-second-pass-replay --seed 974021 --attempt-limit 3
```

## What the useful second layer still needs

Replace the coordinate-deformation prototype with architectural recomposition: choose which travel districts to compress, relocate actual junctions and site-front territories, then reroute continuous corridors around building footprints independently of the 5×5 reservations. Preserve widths as constraints while relocating centre lines, rather than scaling whole rooms and plant zones. Reconsider a macro connection when it cannot produce distinct entry/decision territory. Revalidate shortest movement, openings, separation and shortcuts after every shared-rule proposal. The original strategic planner still restricts Mid to a flank/cross family; geometry relaxation cannot make that graph strategically different. This needs both a richer macro organization and a less constrained spatial pass. No new batch or Stage 4 work is authorized by this report.
'''
 (root/'review.md').write_text(text,encoding='utf-8')
 policy=json.loads((ROOT/'generation-policy.json').read_text());policy['stage_3_experiment_status']='mid_second_pass_mechanical_prototype_visual_problem_unresolved';policy['stage_3_review']='output/mid-frontage-001/review.md';policy['geometry_paused']=True;policy['stage_4_authorized']=False;(ROOT/'generation-policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
if __name__=='__main__':run()
