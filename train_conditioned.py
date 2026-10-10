"""Development experiment: complete footprints given a coarse port connection plan."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn

from evaluate_topology import components, local_view, analyze, aggregate
from train_layout import LayoutNet
from train_patch import patch_input, load_target, fit, patch_scores, preview

# A 40-cell rim can contain at most 20 disconnected occupied groups.
MAX_GROUPS = 20


def ports(context):
    return components(local_view(context, np.zeros((1,32,32))))[1]


def reference_plan(context, target):
    """Offline annotation only: collapse target connectivity to port group labels."""
    labels, _ = components(local_view(context, target))
    canonical = {}
    result = []
    for group in ports(context):
        label = int(labels[group[0]])
        if label not in canonical:
            canonical[label] = len(canonical)
        result.append(canonical[label])
    return result


def encode_plan(context, plan):
    """Inference input uses visible cells and an external plan, never target pixels."""
    groups = ports(context)
    if len(plan) != len(groups):
        raise ValueError('Plan must assign every visible port')
    result = np.zeros((2+MAX_GROUPS,32,32), dtype=np.float32)
    result[:2] = context[:2]
    canonical = {}
    for cells, label in zip(groups, plan):
        if not isinstance(label, (int, np.integer)) or label < 0:
            raise ValueError('Plan labels must be nonnegative integers')
        if label not in canonical:
            canonical[label] = len(canonical)
        channel = canonical[label]
        if channel >= MAX_GROUPS:
            raise ValueError('Too many connection groups')
        for row, col in cells:
            result[2+channel,row+11,col+11] = 1
    return result


class ConditionedNet(LayoutNet):
    def __init__(self):
        super().__init__()
        self.encode[0] = nn.Conv2d(2+MAX_GROUPS,16,3,padding=1)


def annotated(targets):
    visible = patch_input(targets)
    plans = [reference_plan(x,y) for x,y in zip(visible,targets)]
    return np.stack([encode_plan(x,p) for x,p in zip(visible,plans)]), plans


def topology(x,y,pred):
    return aggregate([analyze(a,b,c) for a,b,c in zip(x,y,pred)])


def experiment(dataset, baseline, output, epochs=40):
    if output.exists(): raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available(): raise RuntimeError('CUDA required')
    torch.set_num_threads(4)
    manifest=json.loads((dataset/'manifest.json').read_text())
    if set(manifest['splits']['train']) & set(manifest['splits']['validation']):
        raise ValueError('Map leakage')
    # Only training and validation archives are accessed.
    y=load_target(dataset,'train',manifest); vy=load_target(dataset,'validation',manifest)
    x,plans=annotated(y); vx,vplans=annotated(vy)
    with np.load(baseline) as archive:
        if not np.array_equal(archive['y'],vy) or not np.array_equal(archive['x'],vx[:,:2]):
            raise ValueError('Baseline examples do not match')
        previous=archive['local'].copy()
    output.mkdir(parents=True)
    device=torch.device('cuda'); torch.manual_seed(20261009); start=time.perf_counter()
    tensors=[torch.tensor(a,device=device) for a in (x,y,vx,vy)]
    model,pred,history,best=fit(ConditionedNet(),*tensors,epochs,device)
    checkpoint={'architecture':'conditioned-local-v1','state_dict':{k:v.cpu() for k,v in model.state_dict().items()},
                'max_groups':MAX_GROUPS,'best_epoch':best,'dataset_manifest_sha256':hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()}
    torch.save(checkpoint,output/'model.pt')
    restored=ConditionedNet().to(device)
    restored.load_state_dict(torch.load(output/'model.pt',map_location=device,weights_only=True)['state_dict']); restored.eval()
    with torch.no_grad():
        if not torch.allclose(restored(tensors[2][:1]),model(tensors[2][:1]),atol=1e-6):
            raise RuntimeError('Checkpoint reload mismatch')
    methods={name:{'pixels':patch_scores(p,vy),'topology':topology(vx,vy,p)} for name,p in [('unconditioned',previous),('conditioned',pred)]}
    # Withhold the connection channels as a diagnostic of reliance on supplied intent.
    withheld=tensors[2].clone(); withheld[:,2:]=0
    with torch.no_grad(): missing=torch.sigmoid(model(withheld)).cpu().numpy()
    methods['conditioned_plan_withheld']={'pixels':patch_scores(missing,vy),'topology':topology(vx,vy,missing)}
    result={'model_training_performed':True,'device':torch.cuda.get_device_name(0),'epochs':epochs,'best_epoch':best,
            'seconds':round(time.perf_counter()-start,2),'training_examples':len(y),'validation_examples':len(vy),
            'training_maps':manifest['splits']['train'],'validation_maps':manifest['splits']['validation'],
            'test_evaluated':False,'oracle_connection_plan':True,'methods':methods,'history':history,
            'limits':['Connection plans are coarse annotations derived from reference targets, including validation targets. This gives additional design intent; it is not a fair same-information comparison with the unconditioned model.',
                      'Input channels mark visible rim ports only. Hidden pixel geometry is never included in the input.',
                      'A future planner or user must supply the desired connection groups at inference. This experiment does not learn that intent from text.',
                      'Office remains a reused development map. Withheld-plan input is a diagnostic distribution shift, not an independent control or test.',
                      'Four-neighbor footprint connectivity does not establish directed NAV traversal, architecture, or gameplay.']}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    (output/'plans.json').write_text(json.dumps({'training':plans,'validation':vplans,'encoding':'Canonical connection group per visible rim port; no hidden geometry'}))
    np.savez_compressed(output/'validation_predictions.npz',x=vx,y=vy,prediction=pred)
    preview(vx[:,:2],vy,previous,pred,output/'validation-preview.png',('Hidden patch','Unconditioned','With connection plan','Recorded target'))
    lines=['# Connection-conditioned completion','','Office development experiment with reference-derived connection intent.','',
           '| Method | Patch IoU | Required pairs preserved | Examples with broken routes | Examples with extra connections |',
           '| --- | ---: | ---: | ---: | ---: |']
    for name,m in methods.items():
        t=m['topology']; lines.append(f"| {name} | {m['pixels']['hidden_pixel_iou']:.3f} | {t['preserved_pairs']}/{t['required_pairs']} | {t['examples_with_broken_connection']} | {t['examples_with_extra_connection']} |")
    lines+=['','Preview columns: visible context, previous unconditioned model, connection-conditioned model, recorded target. Four fixed example indices; no success selection.','','## Limits','']+['- '+v for v in result['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(methods),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True); parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--epochs',type=int,default=40)
    args=parser.parse_args()
    if args.epochs<1: parser.error('Positive epoch count required')
    experiment(args.dataset,args.baseline,args.output,args.epochs)
