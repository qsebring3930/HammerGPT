"""Re-plan preserved VAE samples without repeating model training."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np

from train_route_macro import proposal


def run(source,output):
    if output.exists():raise ValueError('Use a new artifact directory')
    metrics=json.loads((source/'metrics.json').read_text())
    generated=np.load(source/'training-vectors.npz')['generated']
    scale=float(np.median([r['source_scale_units'] for r in metrics['records']])*1.35)
    output.mkdir(parents=True);plans=[];candidates=[];start=time.perf_counter()
    for i,vector in enumerate(generated):
        try:
            plan,summary=proposal(vector,scale)
            score=summary['mean_room_displacement_units']+.02*sum(r['units'] for r in plan['exporter_adaptations']['actual_corridor_lengths'])+40*summary['below_half_probability_edges']
            candidates.append({'index':i,'status':'routed','score':score,**summary})
            plans.append((score,i,plan,summary))
        except ValueError as error:candidates.append({'index':i,'status':'rejected','reason':str(error)})
        print(json.dumps(candidates[-1]),flush=True)
        (output/'planning-progress.json').write_text(json.dumps(candidates,indent=2))
        if len(plans)>=3:break
    metrics['previous_planning_attempts']=metrics['candidates'];metrics['candidates']=candidates
    metrics['replanning_source']=str(source.resolve());metrics['replanning_retrained_model']=False
    metrics['replanning_seconds']=time.perf_counter()-start
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2))
    if not plans:raise RuntimeError('No safely routed candidate')
    score,index,plan,summary=min(plans,key=lambda r:(r[0],r[1]))
    shutil.copy2(source/'model.pt',output/'model.pt');shutil.copy2(source/'training-vectors.npz',output/'training-vectors.npz')
    plan.update(model_training_performed=True,model_checkpoint_sha256=hashlib.sha256((output/'model.pt').read_bytes()).hexdigest(),
                candidate_index=index,structural_metrics=summary,model_source_maps=metrics['training_maps'])
    (output/'proposal.json').write_text(json.dumps(plan,indent=2));print(json.dumps({'selected_candidate':index,**summary}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.source,args.output)
