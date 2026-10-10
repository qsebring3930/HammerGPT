"""Record this single-seed experiment, including failed shared-rule revisions."""
import json
from pathlib import Path
from PIL import Image,ImageDraw
from shapely.geometry import Polygon
from playable_composition import compile_composition
from map_layout import font

root=Path(__file__).resolve().parent
out=root/'output/free-mid-1004821-r17'
p=json.loads((out/'composition.json').read_text());v=json.loads((out/'validation.json').read_text());c=compile_composition(p)
attempts=[]
for revision in range(2,18):
 folder=root/f'output/free-mid-1004821-r{revision}'
 file=folder/('failure-report.json' if (folder/'failure-report.json').exists() else 'validation.json')
 if file.exists():attempts.append(dict(revision=revision,seed=1004821,output=str(folder.relative_to(root)),result=json.loads(file.read_text())))
(out/'attempt-history.json').write_text(json.dumps(attempts,indent=2))
measurements=dict(physical_pass=v['physical_pass'],request_pass=v['request_pass'],walkable_component_areas_plan_units_squared=[g.area for g in c['walkable'].geoms],doorways_below_minimum=[o for o in v['opening_widths'] if o['actual_HU']<128-1e-5],construction_revisions=len(attempts),distinct_seeds=1,seed_reproduced=json.loads((out/'summary.json').read_text())['reproduced'])
(out/'review-measurements.json').write_text(json.dumps(measurements,indent=2))
im=Image.open(out/'clean.png');draw=ImageDraw.Draw(im);bounds=c['envelope'].bounds;scale=1300/max(bounds[2]-bounds[0],bounds[3]-bounds[1]);xy=lambda q:(150+(q[0]-bounds[0])*scale,1450-(q[1]-bounds[1])*scale)
draw.rectangle((0,0,1600,65),fill='#101923');draw.text((65,30),'Free-placement revision / seed 1004821 / FOR REVIEW',font=font(30),fill='white')
for label,key in [('Mid link','Mid2'),('B preparation','B_staging')]:
 pos=xy(p['annotations'][key]['point']);draw.text((pos[0]-45,pos[1]),label,font=font(19),fill='white',stroke_width=2,stroke_fill='#23313f')
draw.rectangle((530,1535,1600,1599),fill='#101923');draw.text((550,1542),'Validation failed: two doorway widths and a small isolated pocket.',font=font(18),fill='#f3b0a5')
im.save(out/'plan-for-review.png')
(out/'review.md').write_text('''# Free-placement architectural revision

One seed, 1004821, reused to preserve the preceding lane flow. Existing linked-court Mid strategy retained; this is an architectural revision, not a new strategic family or a diversity demonstration. No neural training, Stage 4 or engine geometry.

Shared rules add offset staging/preparation courts where they fit, flat building frontages facing junction ingress, confluences within deployment territory, and site wings clear of the movement/door envelopes. Low plant cover is declared at 48 HU; full-height building wings at 160 HU. These are provisional conventions.

Four approach episodes fit; one B transfer widening is omitted because another commitment occupies that territory. Roles annotate continuous architecture, not a room for every route node. No new strategic branches were added. Site-free bypass, independent mains and distinct A entries retain their existing checks. B retains its declared approach handoff.

Existing radar observations of offset courts and building-defined transitions informed these authored shared rules; no new NAV extraction or exact image-scale measurement was performed. Natural lanes come from continuous seeded graph placement, not the square reservation scaffold.

Implementation corrected precision metadata during subtraction, constructed true straight opening faces, and included real corridor support on direct complex-to-complex links. No acceptance check was loosened. Automatic approval review rejected a frontage margin reduction; the original width+.8 guard remains.

## Result

All declared ordered routes are now reachable and request checks pass. Physical acceptance fails: two 128-HU nominal doorways measure approximately 127.78 and 125.68 HU; a 0.012-plan-unit-squared isolated A pocket also remains. Exact values are in review-measurements.json. The tiny pocket was not filtered from the connectivity check. Four implementation regression tests are separate from candidate acceptance.

All 16 construction/validation revisions in this turn used the same seed; their outputs and frozen code are retained in attempt-history.json. Shared-rule fixes were rerun; no candidate-specific coordinate edits or different-seed search. Same-seed program reproduction passes.

The global topology and long outer routes remain similar to the preceding attempt. Some junction courts are broad; A secondary preparation extends into the site complex. These are architectural weaknesses to review, not proof of balanced encounters. Vertical movement, timings, utility and gameplay quality remain unverified.

## Reproduction

From the repository root, use a fresh output directory:

```powershell
.tools/training/Scripts/python.exe output/free-mid-1004821-r17/source/free_mid_layout.py --strategy output/distributed-mid-001/r4/courts-handoff --seed 1004821 --output output/free-mid-1004821-replay
```

Frozen implementation and source strategy are saved with this output. Natural-language interpretation remains unverified live. Stage 4 remains paused. Stop for visual review.
''')
policy_path=root/'generation-policy.json';policy=json.loads(policy_path.read_text());policy['stage_3_previous_review']=policy['stage_3_review'];policy['stage_3_review']=str(out.relative_to(root)/'review.md');policy['stage_3_experiment_status']='free_mid_architecture_candidate_rejected_physical_review';policy['stage_4_authorized']=False;policy['geometry_paused']=True;policy_path.write_text(json.dumps(policy,indent=2))
print(json.dumps(measurements,indent=2))
