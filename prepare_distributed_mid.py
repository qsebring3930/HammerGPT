"""Predeclare contrasting bounded demonstrations, no geometry edits."""
import copy,json
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/'output/distributed-mid-001'
base=json.loads((root/'config/map-spec-mid.json').read_text())
rows=[('matched',985731,'auto','auto'),('street',996031,'contested_street','separate_entries'),('courts-handoff',996073,'linked_courts','one_approach_handoff')]
for name,seed,organization,access in rows:
 spec=copy.deepcopy(base);spec['seed']=seed;spec['gameplay'].update(mid_organization=organization,mid_access_mode=access);(out/(name+'-spec.json')).write_text(json.dumps(spec,indent=2))
(out/'experiment.json').write_text(json.dumps(dict(attempt_limit=4,examples=rows,matched_before='output/mid-quick-985731',stage4_paused=True,manual_repairs=False),indent=2))
