"""Train patch completion with a differentiable four-neighbor route penalty."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch.nn import functional as F

from train_conditioned import ConditionedNet, annotated, ports, topology
from train_patch import load_target, patch_scores, preview


def route_labels(contexts, plans):
    """Build supervision solely from visible ports and supplied connection groups."""
    if len(contexts)!=len(plans): raise ValueError('Each context needs a plan')
    groups=[ports(x) for x in contexts]
    count=max(1,max(map(len,groups),default=0))
    seeds=np.zeros((len(contexts),count,10,10),dtype=np.float32)
    destinations=np.zeros((len(contexts),count),dtype=np.int64)
    valid=np.zeros((len(contexts),count,count),dtype=bool)
    expected=np.zeros_like(valid,dtype=np.float32)
    for i,(gs,plan) in enumerate(zip(groups,plans)):
        if len(gs)!=len(plan): raise ValueError('Each port needs a connection group')
        for a,g in enumerate(gs):
            for r,c in g: seeds[i,a,r,c]=1
            destinations[i,a]=g[0][0]*10+g[0][1]
            for b in range(a+1,len(gs)):
                valid[i,a,b]=True; expected[i,a,b]=plan[a]==plan[b]
    return seeds,destinations,valid,expected


def reachability(occupancy, seeds):
    """Widest-path confidence: maximum minimum occupancy along any grid path.

    Ninety-nine synchronous updates suffice for every simple path on 100 cells.
    Only four-neighbor moves are allowed; padding is impassable.
    """
    reach=seeds*occupancy
    for _ in range(99):
        padded=F.pad(reach,(1,1,1,1))
        neighbor=torch.maximum(torch.maximum(padded[:,:,0:10,1:11],padded[:,:,2:12,1:11]),
                               torch.maximum(padded[:,:,1:11,0:10],padded[:,:,1:11,2:12]))
        reach=torch.maximum(reach,torch.minimum(neighbor,occupancy))
    return reach


def route_loss(logits, context, labels):
    seeds,destinations,valid,expected=labels
    visibility=context[:,1:2,11:21,11:21]
    occupancy=context[:,:1,11:21,11:21]*visibility+torch.sigmoid(logits[:,:,11:21,11:21])*(1-visibility)
    reached=reachability(occupancy,seeds).flatten(2)
    scores=reached.gather(2,destinations[:,None,:].expand(-1,seeds.shape[1],-1))
    # Balance connect/separate objectives; empty classes contribute no term.
    terms=[]
    for desired in (0,1):
        mask=valid & (expected==desired)
        if mask.any():
            terms.append(F.binary_cross_entropy(scores[mask].clamp(1e-6,1-1e-6),expected[mask]))
    return torch.stack(terms).mean() if terms else logits.sum()*0


def objective(logits,x,y,labels,weight):
    mask=1-x[:,1:2]
    pixel=(F.binary_cross_entropy_with_logits(logits,y,reduction='none')*mask).sum()/mask.sum()
    routes=route_loss(logits,x,labels)
    return pixel+weight*routes,pixel,routes


def experiment(dataset,baseline,output,epochs=40,weight=.25):
    if output.exists(): raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available(): raise RuntimeError('CUDA required')
    torch.set_num_threads(4); torch.manual_seed(20261009); device=torch.device('cuda')
    manifest=json.loads((dataset/'manifest.json').read_text())
    if set(manifest['splits']['train']) & set(manifest['splits']['validation']): raise ValueError('Map leakage')
    y=load_target(dataset,'train',manifest); vy=load_target(dataset,'validation',manifest)
    x,plans=annotated(y); vx,vplans=annotated(vy)
    with np.load(baseline) as archive:
        if not np.array_equal(archive['x'],vx) or not np.array_equal(archive['y'],vy): raise ValueError('Baseline mismatch')
        old=archive['prediction'].copy()
    train_labels=[torch.tensor(a,device=device) for a in route_labels(x,plans)]
    valid_labels=[torch.tensor(a,device=device) for a in route_labels(vx,vplans)]
    x,y,vx,vy=[torch.tensor(a,device=device) for a in (x,y,vx,vy)]
    model=ConditionedNet().to(device); optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    best=None; best_loss=float('inf'); best_epoch=0; history=[]; start=time.perf_counter(); output.mkdir(parents=True)
    for epoch in range(1,epochs+1):
        model.train(); totals=np.zeros(3)
        for ids in torch.randperm(len(x),device=device).split(64):
            optimizer.zero_grad(); values=objective(model(x[ids]),x[ids],y[ids],[a[ids] for a in train_labels],weight)
            values[0].backward(); optimizer.step(); totals+=np.array([a.item() for a in values])*len(ids)
        model.eval(); vt=np.zeros(3)
        with torch.no_grad():
            for ids in torch.arange(len(vx),device=device).split(64):
                values=objective(model(vx[ids]),vx[ids],vy[ids],[a[ids] for a in valid_labels],weight)
                vt+=np.array([a.item() for a in values])*len(ids)
        record={'epoch':epoch,'train_total':totals[0]/len(x),'validation_total':vt[0]/len(vx),
                'validation_pixel_bce':vt[1]/len(vx),'validation_route_bce':vt[2]/len(vx)}
        history.append(record)
        if record['validation_total']<best_loss:
            best_loss=record['validation_total']; best=copy.deepcopy(model.state_dict()); best_epoch=epoch
        if epoch==1 or epoch%5==0: print(json.dumps(record),flush=True)
    model.load_state_dict(best); model.eval()
    with torch.no_grad(): pred=torch.sigmoid(model(vx)).cpu().numpy()
    checkpoint={'architecture':'conditioned-local-v1','state_dict':{k:v.cpu() for k,v in model.state_dict().items()},
                'best_epoch':best_epoch,'route_weight':weight,'dataset_manifest_sha256':hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()}
    torch.save(checkpoint,output/'model.pt')
    restored=ConditionedNet().to(device); restored.load_state_dict(torch.load(output/'model.pt',map_location=device,weights_only=True)['state_dict']); restored.eval()
    with torch.no_grad():
        if not torch.allclose(restored(vx[:1]),model(vx[:1]),atol=1e-6): raise RuntimeError('Checkpoint reload mismatch')
    xx=vx.cpu().numpy(); yy=vy.cpu().numpy()
    methods={name:{'pixels':patch_scores(p,yy),'topology':topology(xx,yy,p)} for name,p in [('pixel_loss_only',old),('pixel_and_route_loss',pred)]}
    limits=['Office is reused development validation; test data were not read.',
            'Both models receive reference-derived coarse connection plans, including validation. A planner must supply those plans for generation.',
            'The new checkpoint is selected by pixel BCE plus weighted soft route BCE; the old checkpoint used pixel BCE. Threshold remains 0.5.',
            'Soft route confidence is the widest-path bottleneck; it does not enforce corridor width, heights, directed NAV traversal, or gameplay.',
            'Connection classes are balanced per batch; this differs from averaging every pair uniformly. No automatic Hammer generation is enabled.',
            'This is a single-seed development comparison. The earlier trainer resets the shuffle seed after model initialization; this run uses the post-initialization RNG state, so batch orders differ.']
    result={'model_training_performed':True,'device':torch.cuda.get_device_name(0),'epochs':epochs,'best_epoch':best_epoch,
            'seconds':round(time.perf_counter()-start,2),'route_weight':weight,'oracle_connection_plan':True,'test_evaluated':False,
            'training_maps':manifest['splits']['train'],'validation_maps':manifest['splits']['validation'],
            'dataset_manifest_sha256':checkpoint['dataset_manifest_sha256'],'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
            'methods':methods,'history':history,'limits':limits}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    np.savez_compressed(output/'validation_predictions.npz',x=xx,y=yy,prediction=pred)
    preview(xx[:,:2],yy,old,pred,output/'validation-preview.png',('Hidden patch','Pixel loss only','Pixel + route loss','Recorded target'))
    lines=['# Route-loss training experiment','','Office development; supplied reference-derived connection intent.','',
           '| Method | Patch IoU | Required pairs preserved | Examples with broken routes | Examples with extra connections |',
           '| --- | ---: | ---: | ---: | ---: |']
    for name,m in methods.items():
        t=m['topology']; lines.append(f"| {name} | {m['pixels']['hidden_pixel_iou']:.3f} | {t['preserved_pairs']}/{t['required_pairs']} | {t['examples_with_broken_connection']} | {t['examples_with_extra_connection']} |")
    lines+=['',str(epochs)+' epochs from the same seeded architecture, optimizer, training data and supplied plans. New objective: pixel BCE + '+str(weight)+' × class-balanced route BCE. Preview uses four fixed example indices.','','## Limits','']+['- '+a for a in limits]
    (output/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps(methods),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True); parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--epochs',type=int,default=40); parser.add_argument('--route-weight',type=float,default=.25)
    args=parser.parse_args()
    if args.epochs<1 or args.route_weight<=0: parser.error('Positive epochs and route weight required')
    experiment(args.dataset,args.baseline,args.output,args.epochs,args.route_weight)
