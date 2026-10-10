"""Office-only planner ablation: augmentation, regularization and plan decoding."""
import argparse
import copy
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from train_connection_planner import ConnectionPlanner,pair_inputs,pair_targets,probabilities,partition,plan_scores,complete,binary_scores
from train_conditioned import ConditionedNet,reference_plan,topology
from train_patch import patch_input,load_target,patch_scores,preview


def transform_features(features,codes):
    """Apply each sample's square symmetry to occupancy, visibility and markers."""
    if len(codes)!=len(features) or ((codes<0)|(codes>7)).any(): raise ValueError('Expected one symmetry code 0..7 per example')
    result=torch.empty_like(features)
    for code in range(8):
        selected=codes==code
        if not selected.any(): continue
        value=torch.rot90(features[selected],code%4,dims=(-2,-1))
        if code>=4: value=torch.flip(value,dims=(-1,))
        result[selected]=value
    return result


@lru_cache(maxsize=9)
def candidate_partitions(count):
    """Enumerate each unlabeled partition once using restricted-growth labels."""
    if count<0 or count>8: raise ValueError('Exact enumeration supports up to eight ports')
    candidates=[]
    def visit(labels):
        if len(labels)==count:
            candidates.append(tuple(labels)); return
        for label in range(max(labels,default=-1)+2): visit(labels+[label])
    visit([])
    pairs=list(itertools.combinations(range(count),2))
    same=np.asarray([[p[a]==p[b] for a,b in pairs] for p in candidates],dtype=np.float64).reshape(len(candidates),len(pairs))
    return candidates,same


def maximum_likelihood_partition(probabilities):
    """Choose the highest pairwise Bernoulli likelihood among consistent plans.

    Exact for <=8 ports under the pair-independence scoring assumption; larger
    inputs explicitly fall back to the existing complete-link decoder.
    """
    p=np.asarray(probabilities)
    if p.ndim!=2 or p.shape[0]!=p.shape[1] or not np.isfinite(p).all(): raise ValueError('Invalid probability matrix')
    if not np.allclose(p,p.T) or np.any(p<0) or np.any(p>1): raise ValueError('Expected symmetric probabilities')
    if len(p)>8: return partition(p)
    candidates,same=candidate_partitions(len(p))
    values=np.asarray([p[a,b] for a,b in itertools.combinations(range(len(p)),2)])
    values=np.clip(values,1e-6,1-1e-6)
    scores=same@(np.log(values)-np.log1p(-values))
    best=np.flatnonzero(np.isclose(scores,scores.max(),rtol=0,atol=1e-12))
    # In an exact tie prefer fewer connections, then canonical enumeration order.
    winner=int(best[np.argmin(same[best].sum(axis=1))])
    return list(candidates[winner])


def decode(counts,indices,scores,decoder):
    matrices=[np.eye(count,dtype=np.float64) for count in counts]
    for (i,a,b),value in zip(indices,scores): matrices[i][a,b]=matrices[i][b,a]=value
    return [decoder(p) for p in matrices]


class RegularizedPlanner(ConnectionPlanner):
    def __init__(self,dropout=0):
        super().__init__(); self.dropout=nn.Dropout(dropout)

    def forward(self,x):
        hidden=self.head[:3](self.features(x))
        return self.head[3](self.dropout(hidden)).squeeze(1)


def fit(features,labels,vfeatures,vlabels,configuration,epochs,device):
    torch.manual_seed(20261009); model=RegularizedPlanner(configuration['dropout']).to(device)
    optimizer=torch.optim.Adam(model.parameters(),lr=.001,weight_decay=configuration['weight_decay']); torch.manual_seed(20261009)
    tx,ty,tvx,tvy=[torch.tensor(a,device=device) for a in (features,labels,vfeatures,vlabels)]
    best=None; best_loss=float('inf'); best_epoch=0; history=[]
    for epoch in range(1,epochs+1):
        model.train(); total=0
        for ids in torch.randperm(len(tx),device=device).split(128):
            batch=tx[ids]
            if configuration['augmentation']: batch=transform_features(batch,torch.randint(8,(len(batch),),device=device))
            optimizer.zero_grad(); loss=F.binary_cross_entropy_with_logits(model(batch),ty[ids]); loss.backward(); optimizer.step(); total+=loss.item()*len(ids)
        model.eval()
        with torch.no_grad(): val=sum(F.binary_cross_entropy_with_logits(model(tvx[ids]),tvy[ids]).item()*len(ids) for ids in torch.arange(len(tvx),device=device).split(128))/len(tvx)
        record={'epoch':epoch,'train_bce':total/len(tx),'validation_bce':val}; history.append(record)
        if val<best_loss: best_loss=val; best=copy.deepcopy(model.state_dict()); best_epoch=epoch
        if epoch==1 or epoch%10==0: print(json.dumps({'arm':configuration['name'],**record}),flush=True)
    model.load_state_dict(best); model.eval()
    return model,history,best_epoch,best_loss


def experiment(dataset,floor_checkpoint,previous,output,epochs=40):
    if output.exists(): raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available(): raise RuntimeError('CUDA required')
    torch.set_num_threads(4); device=torch.device('cuda'); manifest=json.loads((dataset/'manifest.json').read_text())
    reserved=json.loads((dataset.parent.parent/'evaluation-reservations.json').read_text())['maps']
    if set(manifest['splits']['train']) & set(manifest['splits']['validation']): raise ValueError('Map leakage')
    if set(manifest['splits']['train']+manifest['splits']['validation']) & {r['name'] for r in reserved}: raise ValueError('Reserved map in development data')
    manifest_hash=hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()
    floor_state=torch.load(floor_checkpoint,map_location='cpu',weights_only=True)
    if floor_state['dataset_manifest_sha256']!=manifest_hash: raise ValueError('Floor checkpoint provenance mismatch')
    floor=ConditionedNet().to(device); floor.load_state_dict(floor_state['state_dict']); floor.eval()
    # No test archive or reserved-map NAV is accessed.
    y=load_target(dataset,'train',manifest); vy=load_target(dataset,'validation',manifest)
    x=patch_input(y); vx=patch_input(vy)
    plans=[reference_plan(a,b) for a,b in zip(x,y)]; vplans=[reference_plan(a,b) for a,b in zip(vx,vy)]
    features,indices,_=pair_inputs(x); vfeatures,vindices,counts=pair_inputs(vx)
    labels=pair_targets(indices,plans); vlabels=pair_targets(vindices,vplans)
    if not len(labels) or not len(vlabels): raise ValueError('No entrance pairs')
    old_metrics=json.loads((previous/'metrics.json').read_text())
    floor_hash=hashlib.sha256(floor_checkpoint.read_bytes()).hexdigest()
    if old_metrics['dataset_manifest_sha256']!=manifest_hash or old_metrics['floor_checkpoint_sha256']!=floor_hash: raise ValueError('Previous run provenance mismatch')
    with np.load(previous/'validation_predictions.npz') as archive:
        if not np.array_equal(archive['x'],vx) or not np.array_equal(archive['y'],vy): raise ValueError('Previous examples mismatch')
        old=archive['prediction'].copy()
    configurations=[{'name':'control','augmentation':False,'dropout':0.,'weight_decay':0.},
                    {'name':'augmentation','augmentation':True,'dropout':0.,'weight_decay':0.},
                    {'name':'regularization','augmentation':False,'dropout':.25,'weight_decay':.001},
                    {'name':'combined','augmentation':True,'dropout':.25,'weight_decay':.001}]
    output.mkdir(parents=True); start=time.perf_counter(); arms={}; completion_outputs={}
    for configuration in configurations:
        name=configuration['name']; model,history,best_epoch,best_loss=fit(features,labels,vfeatures,vlabels,configuration,epochs,device)
        torch.save({'architecture':'entrance-pair-cnn-v2','state_dict':{k:v.cpu() for k,v in model.state_dict().items()},
                    'configuration':configuration,'best_epoch':best_epoch,'dataset_manifest_sha256':manifest_hash},output/(name+'.pt'))
        restored=RegularizedPlanner(configuration['dropout']).to(device)
        restored.load_state_dict(torch.load(output/(name+'.pt'),map_location=device,weights_only=True)['state_dict']); restored.eval()
        with torch.no_grad():
            query=torch.tensor(vfeatures[:1],device=device)
            if not torch.allclose(restored(query),model(query),atol=1e-6): raise RuntimeError('Checkpoint reload mismatch')
        scores=probabilities(model,vfeatures,device); methods={}; decoded={}
        for method,decoder in [('complete_link',partition),('maximum_likelihood',maximum_likelihood_partition)]:
            selected=decode(counts,vindices,scores,decoder); decoded[method]=selected
            pred=complete(floor,vx,selected,device); completion_outputs[name,method]=pred
            methods[method]={'plan':plan_scores(selected,vplans),'pixels':patch_scores(pred,vy),'topology':topology(vx,vy,pred)}
        arms[name]={'configuration':configuration,'best_epoch':best_epoch,'best_validation_bce':best_loss,
                    'raw_pairs':binary_scores(scores,vlabels),'methods':methods,'history':history}
        (output/(name+'-plans.json')).write_text(json.dumps({'plans':decoded,'pair_indices':vindices,'probabilities':scores.tolist()},indent=2))
    # Choose the training arm by pair BCE, independently of decoded floor metrics.
    selected=min(arms,key=lambda name:arms[name]['best_validation_bce'])
    chosen=completion_outputs[selected,'maximum_likelihood']
    limits=['Office is reused development validation; all five reserved maps and the Vertigo archive remain unevaluated.',
            'The four training arms and hyperparameters were fixed before this run. Arm selection uses validation pair BCE, not floor connectivity scores.',
            'Dropout and weight decay form one regularization arm. Augmentation changes training inputs; it does not create independent maps.',
            'Maximum-likelihood decoding assumes independent pair evidence. It optimizes that score, not design quality; it can override individual low-confidence pairs.',
            'Exact partition search supports up to eight ports and falls back to complete-link above that limit.',
            'Inference uses visible context only. Reference connections provide supervised labels and evaluation targets. The frozen floor model was trained on reference-derived plans.',
            'This is a single-seed local patch experiment. It does not generate whole-map topology, elevation, architecture or text-driven goals. Automatic Hammer generation remains disabled.']
    result={'model_training_performed':True,'device':torch.cuda.get_device_name(0),'epochs_per_arm':epochs,'seconds':round(time.perf_counter()-start,2),
            'training_maps':manifest['splits']['train'],'validation_maps':manifest['splits']['validation'],'training_pairs':len(labels),'validation_pairs':len(vlabels),
            'test_evaluated':False,'reserved_maps_evaluated':False,'oracle_connection_plan_for_learned_pipeline':False,
            'dataset_manifest_sha256':manifest_hash,'floor_checkpoint_sha256':floor_hash,'previous_metrics_sha256':hashlib.sha256((previous/'metrics.json').read_bytes()).hexdigest(),
            'arms':arms,'selected_arm':selected,'selected_decoder':'maximum_likelihood','exact_decoder_limit':8,
            'validation_decoder_fallback_examples':sum(n>8 for n in counts),'validation_max_ports':max(counts),'limits':limits,
            'previous_learned_pipeline':old_metrics['methods']['learned_plan'],'interpolation_baseline':old_metrics['methods']['interpolated_plan']}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    np.savez_compressed(output/'validation_predictions.npz',x=vx,y=vy,prediction=chosen)
    preview(vx,vy,old,chosen,output/'validation-preview.png',('Hidden patch','Previous planner','Selected planner','Recorded target'))
    lines=['# Planner augmentation and decoding experiment','','Office development; frozen floor model.','',
           '| Training arm | Decoder | Plan pair accuracy | Exact plans (2+ ports) | Patch IoU | Broken-route examples | Extra-connection examples |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for name,arm in arms.items():
        for decoder,m in arm['methods'].items():
            p=m['plan']; t=m['topology']; lines.append(f"| {name} | {decoder} | {p['accuracy']:.3f} | {p['exact_partition_examples']}/{p['examples_with_two_or_more_ports']} | {m['pixels']['hidden_pixel_iou']:.3f} | {t['examples_with_broken_connection']} | {t['examples_with_extra_connection']} |")
    lines+=['',f'Selected training arm by validation pair BCE: {selected}. Preview uses its maximum-likelihood decoder and four fixed example indices. No reference plan is provided to the learned pipeline.','','## Limits','']+['- '+a for a in limits]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'selected':selected,'arms':{name:{'best_validation_bce':a['best_validation_bce'],'methods':a['methods']} for name,a in arms.items()}}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True); parser.add_argument('--floor-checkpoint',type=Path,required=True)
    parser.add_argument('--previous',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--epochs',type=int,default=40)
    args=parser.parse_args()
    if args.epochs<1: parser.error('Positive epoch count required')
    experiment(args.dataset,args.floor_checkpoint,args.previous,args.output,args.epochs)
