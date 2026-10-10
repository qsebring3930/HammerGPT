"""Learn local entrance connectivity from visible context; evaluate on Office only."""
import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from train_conditioned import ports, reference_plan, encode_plan, ConditionedNet, topology
from train_patch import patch_input, load_target, patch_scores, preview, interpolation


def pair_inputs(contexts):
    """Inference features and indices; no target or connection labels accepted."""
    features=[]; indices=[]; counts=[]
    for index,context in enumerate(contexts):
        visible=context[:2].copy(); visible[0]*=visible[1]
        groups=ports(visible); counts.append(len(groups))
        for a,b in itertools.combinations(range(len(groups)),2):
            markers=np.zeros((1,32,32),dtype=np.float32)
            for r,c in groups[a]+groups[b]: markers[0,r+11,c+11]=1
            features.append(np.concatenate((visible,markers))); indices.append((index,a,b))
    return np.asarray(features,dtype=np.float32).reshape(-1,3,32,32),indices,counts


def pair_targets(indices,plans):
    return np.asarray([plans[i][a]==plans[i][b] for i,a,b in indices],dtype=np.float32)


def partition(probabilities,threshold=.5):
    """Complete-link clustering: every cross-cluster pair must support a merge.

    This makes a consistent partition without transitive merges overruling an
    explicitly low-confidence pair. It is a heuristic, not an optimal decoder.
    """
    p=np.asarray(probabilities)
    if p.ndim!=2 or p.shape[0]!=p.shape[1] or not np.isfinite(p).all(): raise ValueError('Invalid probability matrix')
    if not np.allclose(p,p.T) or np.any(p<0) or np.any(p>1): raise ValueError('Expected symmetric probabilities')
    groups=[[i] for i in range(len(p))]
    while True:
        candidates=[]
        for a,b in itertools.combinations(range(len(groups)),2):
            cross=p[np.ix_(groups[a],groups[b])]
            if cross.min()>=threshold: candidates.append((float(cross.mean()),-a,-b))
        if not candidates: break
        _,a,b=max(candidates); a=-a; b=-b
        groups[a]+=groups[b]; del groups[b]
    result=[0]*len(p)
    for label,group in enumerate(groups):
        for port in group: result[port]=label
    return result


class ConnectionPlanner(nn.Module):
    def __init__(self):
        super().__init__()
        self.features=nn.Sequential(nn.Conv2d(3,16,3,padding=1),nn.ReLU(),
                                    nn.Conv2d(16,32,3,stride=2,padding=1),nn.ReLU(),
                                    nn.Conv2d(32,64,3,stride=2,padding=1),nn.ReLU(),
                                    nn.Conv2d(64,64,3,stride=2,padding=1),nn.ReLU())
        self.head=nn.Sequential(nn.Flatten(),nn.Linear(64*4*4,64),nn.ReLU(),nn.Linear(64,1))

    def forward(self,x): return self.head(self.features(x)).squeeze(1)


def probabilities(model,features,device):
    if not len(features): return np.empty(0)
    model.eval()
    with torch.no_grad():
        return np.concatenate([torch.sigmoid(model(torch.tensor(batch,device=device))).cpu().numpy()
                               for batch in np.array_split(features,max(1,(len(features)+127)//128)) if len(batch)])


def predict_plans(model,contexts,device):
    features,indices,counts=pair_inputs(contexts); scores=probabilities(model,features,device)
    matrices=[np.eye(count,dtype=np.float32) for count in counts]
    for (i,a,b),value in zip(indices,scores): matrices[i][a,b]=matrices[i][b,a]=value
    return [partition(matrix) for matrix in matrices],scores,indices


def binary_scores(prediction,target):
    p=np.asarray(prediction)>=.5; y=np.asarray(target)>=.5
    tp=int((p&y).sum()); tn=int((~p&~y).sum()); fp=int((p&~y).sum()); fn=int((~p&y).sum())
    return {'pairs':len(y),'accuracy':float((p==y).mean()) if len(y) else None,
            'true_connected':tp,'true_separate':tn,'false_connections':fp,'missed_connections':fn,
            'connected_recall':tp/(tp+fn) if tp+fn else None,'separate_recall':tn/(tn+fp) if tn+fp else None}


def plan_scores(predicted,expected):
    indices=[(i,a,b) for i,p in enumerate(expected) for a,b in itertools.combinations(range(len(p)),2)]
    score=binary_scores(pair_targets(indices,predicted),pair_targets(indices,expected))
    eligible=[i for i,p in enumerate(expected) if len(p)>=2]
    exact=lambda i: all((predicted[i][a]==predicted[i][b])==(expected[i][a]==expected[i][b]) for a,b in itertools.combinations(range(len(expected[i])),2))
    score['examples_with_two_or_more_ports']=len(eligible)
    score['exact_partition_examples']=sum(exact(i) for i in eligible)
    return score


def complete(floor_model,contexts,plans,device):
    inputs=np.stack([encode_plan(x,p) for x,p in zip(contexts,plans)])
    return probabilities_floor(floor_model,inputs,device)


def probabilities_floor(model,inputs,device):
    model.eval()
    with torch.no_grad():
        return np.concatenate([torch.sigmoid(model(torch.tensor(batch,device=device))).cpu().numpy()
                               for batch in np.array_split(inputs,max(1,(len(inputs)+63)//64)) if len(batch)])


def experiment(dataset,floor_checkpoint,floor_predictions,output,epochs=40):
    if output.exists(): raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available(): raise RuntimeError('CUDA required')
    torch.set_num_threads(4); device=torch.device('cuda'); manifest=json.loads((dataset/'manifest.json').read_text())
    if set(manifest['splits']['train']) & set(manifest['splits']['validation']): raise ValueError('Map leakage')
    registry=dataset.parent.parent/'evaluation-reservations.json'
    reserved=json.loads(registry.read_text())['maps']
    development=set(manifest['splits']['train']+manifest['splits']['validation'])
    if development & {r['name'] for r in reserved}: raise ValueError('Reserved evaluation map in development data')
    manifest_hash=hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()
    checkpoint=torch.load(floor_checkpoint,map_location='cpu',weights_only=True)
    if checkpoint['dataset_manifest_sha256']!=manifest_hash: raise ValueError('Floor model provenance mismatch')
    # Only existing development archives are accessed; no reserved NAVs or test.npz.
    y=load_target(dataset,'train',manifest); vy=load_target(dataset,'validation',manifest)
    x=patch_input(y); vx=patch_input(vy)
    plans=[reference_plan(a,b) for a,b in zip(x,y)]; vplans=[reference_plan(a,b) for a,b in zip(vx,vy)]
    features,indices,_=pair_inputs(x); vfeatures,vindices,_=pair_inputs(vx)
    labels=pair_targets(indices,plans); vlabels=pair_targets(vindices,vplans)
    if not len(labels) or not len(vlabels): raise ValueError('No entrance pairs to train or validate')
    with np.load(floor_predictions) as data:
        if not np.array_equal(data['y'],vy) or not np.array_equal(data['x'][:,:2],vx): raise ValueError('Floor prediction examples mismatch')
        oracle=data['prediction'].copy()
    torch.manual_seed(20261009); model=ConnectionPlanner().to(device)
    optimizer=torch.optim.Adam(model.parameters(),lr=.001); torch.manual_seed(20261009)
    tx=torch.tensor(features,device=device); ty=torch.tensor(labels,device=device)
    tvx=torch.tensor(vfeatures,device=device); tvy=torch.tensor(vlabels,device=device)
    best=None; best_loss=float('inf'); best_epoch=0; history=[]; start=time.perf_counter(); output.mkdir(parents=True)
    for epoch in range(1,epochs+1):
        model.train(); total=0
        for ids in torch.randperm(len(tx),device=device).split(128):
            optimizer.zero_grad(); loss=F.binary_cross_entropy_with_logits(model(tx[ids]),ty[ids]); loss.backward(); optimizer.step(); total+=loss.item()*len(ids)
        model.eval()
        with torch.no_grad(): val=sum(F.binary_cross_entropy_with_logits(model(tvx[ids]),tvy[ids]).item()*len(ids) for ids in torch.arange(len(tvx),device=device).split(128))/len(tvx)
        record={'epoch':epoch,'train_bce':total/len(tx),'validation_bce':val}; history.append(record)
        if val<best_loss: best_loss=val; best=copy.deepcopy(model.state_dict()); best_epoch=epoch
        if epoch==1 or epoch%10==0: print(json.dumps(record),flush=True)
    model.load_state_dict(best); model.eval()
    torch.save({'architecture':'entrance-pair-cnn-v1','state_dict':{k:v.cpu() for k,v in model.state_dict().items()},
                'best_epoch':best_epoch,'threshold':.5,'decoder':'complete-link','dataset_manifest_sha256':manifest_hash},output/'planner.pt')
    restored=ConnectionPlanner().to(device); restored.load_state_dict(torch.load(output/'planner.pt',map_location=device,weights_only=True)['state_dict']); restored.eval()
    with torch.no_grad():
        if not torch.allclose(restored(tvx[:1]),model(tvx[:1]),atol=1e-6): raise RuntimeError('Checkpoint reload mismatch')
    predicted,pair_prob,predicted_indices=predict_plans(model,vx,device)
    if predicted_indices!=vindices: raise RuntimeError('Pair ordering changed')
    floor=ConditionedNet().to(device); floor.load_state_dict(checkpoint['state_dict']); floor.eval()
    all_connected=[[0]*len(p) for p in vplans]; all_separate=[list(range(len(p))) for p in vplans]
    # The same connectivity extractor can label a guessed completion; here its
    # input is interpolation from visible edges, never the recorded target.
    interpolated_plans=[reference_plan(a,b) for a,b in zip(vx,interpolation(vx))]
    methods={}; outputs={}
    for name,selected in [('learned_plan',predicted),('all_connected',all_connected),('all_separate',all_separate),('interpolated_plan',interpolated_plans)]:
        pred=complete(floor,vx,selected,device); outputs[name]=pred
        methods[name]={'plan':plan_scores(selected,vplans),'pixels':patch_scores(pred,vy),'topology':topology(vx,vy,pred)}
    methods['reference_plan_diagnostic']={'plan':plan_scores(vplans,vplans),'pixels':patch_scores(oracle,vy),'topology':topology(vx,vy,oracle)}
    limits=['Office is reused development validation; the five reserved maps and Vertigo test archive were not evaluated.',
            'Planner inference accepts only visible context and candidate entrance markers. Reference connectivity supplies supervised training labels and evaluation targets, not inference inputs.',
            'A visible footprint can admit several valid connection plans. Matching one reference does not establish design quality or tactical balance.',
            'The floor model is frozen and was trained on reference-derived plans; learned plans introduce an inference distribution shift.',
            'Complete-link clustering produces transitive connection groups but is a heuristic; it can discard individual pair predictions.',
            'This chooses local connectivity for an 8x8 missing patch, not whole-map topology, elevation, room semantics, or text-guided design. No automatic Hammer generation is enabled.']
    result={'model_training_performed':True,'task':'visible-context entrance-pair planning plus frozen footprint completion',
            'device':torch.cuda.get_device_name(0),'epochs':epochs,'best_epoch':best_epoch,'seconds':round(time.perf_counter()-start,2),
            'training_maps':manifest['splits']['train'],'validation_maps':manifest['splits']['validation'],'training_pairs':len(labels),
            'validation_pairs':len(vlabels),'training_connected_fraction':float(labels.mean()),'test_evaluated':False,'reserved_maps_evaluated':False,
            'dataset_manifest_sha256':manifest_hash,'floor_checkpoint_sha256':hashlib.sha256(floor_checkpoint.read_bytes()).hexdigest(),
            'floor_predictions_sha256':hashlib.sha256(floor_predictions.read_bytes()).hexdigest(),'raw_pair_metrics':binary_scores(pair_prob,vlabels),
            'methods':methods,'history':history,'limits':limits}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    (output/'validation_plans.json').write_text(json.dumps({'predicted':predicted,'reference_for_scoring':vplans,'pair_indices':vindices,'pair_probabilities':pair_prob.tolist()},indent=2))
    np.savez_compressed(output/'validation_predictions.npz',x=vx,y=vy,prediction=outputs['learned_plan'])
    preview(vx,vy,oracle,outputs['learned_plan'],output/'validation-preview.png',('Hidden patch','Reference plan','Learned plan','Recorded target'))
    lines=['# Learned connection planner','','Office development data. The floor model is frozen.','',
           '| Plan source | Exact plans (2+ ports) | Patch IoU | Required pairs preserved | Broken-route examples | Extra-connection examples |',
           '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in methods.items():
        p=m['plan']; t=m['topology']; lines.append(f"| {name} | {p['exact_partition_examples']}/{p['examples_with_two_or_more_ports']} | {m['pixels']['hidden_pixel_iou']:.3f} | {t['preserved_pairs']}/{t['required_pairs']} | {t['examples_with_broken_connection']} | {t['examples_with_extra_connection']} |")
    lines+=['','Checkpoint selected by Office pair BCE; pair threshold 0.5 and complete-link decoding fixed before training. The reference-plan row is privileged-information diagnosis, not an autonomous baseline. Four fixed preview indices.','','## Limits','']+['- '+a for a in limits]
    (output/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps({'raw_pairs':result['raw_pair_metrics'],'methods':methods}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True); parser.add_argument('--floor-checkpoint',type=Path,required=True)
    parser.add_argument('--floor-predictions',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--epochs',type=int,default=40)
    args=parser.parse_args()
    if args.epochs<1: parser.error('Positive epoch count required')
    experiment(args.dataset,args.floor_checkpoint,args.floor_predictions,args.output,args.epochs)
