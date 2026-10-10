"""Learn a source-face correction to the frozen topology planner.

Unsupported geometry keeps the existing model unchanged. No map generation.
"""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from train_route_organization import GraphPlanner,TRAIN,VALIDATION,TEST,N,encode,mask_example,batch,loss_for,metrics,geometric_neighbors,sha


class SourcePlanner(nn.Module):
    def __init__(self,base):
        super().__init__();self.base=base
        for p in base.parameters():p.requires_grad=False
        self.correction=nn.Sequential(nn.Linear(106,64),nn.SiLU(),nn.Linear(64,32),nn.SiLU(),nn.Linear(32,1))
        nn.init.zeros_(self.correction[-1].weight);nn.init.zeros_(self.correction[-1].bias)

    def forward(self,x,observed,known,valid,node_geometry,pair_geometry):
        with torch.no_grad():base=self.base(x,observed,known,valid)
        h=torch.cat([x,node_geometry],dim=-1)
        a=h[:,:,None,:].expand(-1,-1,N,-1);b=h[:,None,:,:].expand(-1,N,-1,-1)
        delta=x[:,None,:,:3]-x[:,:,None,:3]
        inputs=torch.cat([a,b,delta,torch.linalg.vector_norm(delta,dim=-1,keepdim=True),pair_geometry],dim=-1)
        support=pair_geometry[...,1::2].mean(-1)
        return base+self.correction(inputs).squeeze(-1)*support


def attach(root,name):
    record=encode(root,name,root/'output/route-corpus-expanded-v2');folder=root/'output/source-obstruction-features-v1'
    meta=json.loads((folder/f'{name}.json').read_text())
    if meta['node_ids']!=record['ids'] or meta['source_route_targets_sha256']!=record['provenance']['route_targets_sha256']:raise ValueError('Geometry feature association mismatch')
    if meta['features_sha256']!=sha(folder/f'{name}.npz'):raise ValueError('Geometry features changed')
    geometry=np.load(folder/f'{name}.npz');record['node_geometry']=geometry['node'];record['pair_geometry']=geometry['pair'];record['geometry_metadata']=meta
    return record


def examples(record,seeds):
    result=[]
    for seed in seeds:
        e=mask_example(record,seed);e['node_geometry']=record['node_geometry'];e['pair_geometry']=record['pair_geometry'];result.append(e)
    return result


def tensors(examples,device):
    data=batch(examples,device)
    for key in ('node_geometry','pair_geometry'):data[key]=torch.as_tensor(np.stack([e[key] for e in examples]),device=device)
    return data


def prediction(model,data):
    return model(data['x'],data['observed'],data['known'],data['valid'],data['node_geometry'],data['pair_geometry'])


def decode(probability,base,support,threshold,base_threshold):
    return np.where(support,probability>=threshold,base>=base_threshold).astype(np.float32)


def ray_baseline(examples,threshold,neighbors,minimum_fraction):
    predictions=geometric_neighbors(examples,threshold,neighbors)
    for i,e in enumerate(examples):
        fraction=e['pair_geometry'][...,0::2];known=e['pair_geometry'][...,1::2]
        count=known.sum(-1);average=(fraction*known).sum(-1)/np.maximum(count,1)
        predictions[i]*=((count==0)|(average>=minimum_fraction))
    return predictions


def run(root,output,epochs):
    output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(4);torch.manual_seed(20261009)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    baseline_folder=root/'output/training/route-organization-expanded-v1';checkpoint=torch.load(baseline_folder/'graph_planner.pt',map_location=device,weights_only=False)
    names=checkpoint['training_maps']
    if set(names)&{VALIDATION,TEST}:raise ValueError('Split overlap')
    records=[attach(root,name) for name in names];val_record=attach(root,VALIDATION);validation=examples(val_record,range(220000,220032));val=tensors(validation,device)
    base=GraphPlanner().to(device);base.load_state_dict(checkpoint['state_dict']);base.eval();model=SourcePlanner(base).to(device)
    optimizer=torch.optim.AdamW(model.correction.parameters(),lr=.001,weight_decay=.001)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,epochs)
    weight=checkpoint['training_info']['training_only_positive_weight'];best,best_value,best_epoch=None,float('inf'),0;history=[]
    for epoch in range(1,epochs+1):
        train=[]
        for i in range(24):train+=examples(records[i%len(records)],[100000+epoch*100+i])
        data=tensors(train,device);model.correction.train();optimizer.zero_grad(set_to_none=True)
        loss=loss_for(prediction(model,data),data['target'],data['hidden'],weight);loss.backward();nn.utils.clip_grad_norm_(model.correction.parameters(),2);optimizer.step();scheduler.step()
        if epoch%10==0 or epoch==epochs:
            model.eval()
            with torch.no_grad():value=float(loss_for(prediction(model,val),val['target'],val['hidden'],weight))
            history.append({'epoch':epoch,'training_loss':float(loss.detach()),'validation_loss':value})
            if value<best_value:best_value,best_epoch=value,epoch;best=copy.deepcopy(model.state_dict())
    model.load_state_dict(best);model.eval()
    with torch.no_grad():
        val_prob=prediction(model,val).sigmoid().cpu().numpy()
        val_base=model.base(val['x'],val['observed'],val['known'],val['valid']).sigmoid().cpu().numpy()
    base_threshold=json.loads((root/'output/training/route-organization-expanded-calibrated-v1/decoder.json').read_text())['decoders']['graph_planner']['threshold']
    support=val['pair_geometry'][...,1::2].sum(-1).cpu().numpy()>0
    trials=[]
    for threshold in np.linspace(.05,.995,190):
        score=metrics(decode(val_prob,val_base,support,threshold,base_threshold),validation);trials.append({'threshold':float(threshold),**score})
    selected=max(trials,key=lambda s:(s['hidden_directed_edge_IoU'],s['precision']))
    geometric_trials=[]
    for threshold in (.08,.12,.16,.2,.25,.32,.4,.5):
        for neighbors in (2,3,4,6):
            for cutoff in (0,.25,.5,.75,.95):
                score=metrics(ray_baseline(validation,threshold,neighbors,cutoff),validation)
                geometric_trials.append({'threshold':threshold,'maximum_neighbors':neighbors,'minimum_native_hit_fraction':cutoff,**score})
    ray_config=max(geometric_trials,key=lambda s:(s['hidden_directed_edge_IoU'],s['precision']))
    torch.save({'state_dict':{k:v.cpu() for k,v in model.state_dict().items()},'training_maps':names,'validation_map':VALIDATION,'test_map':TEST,
                'selected_epoch':best_epoch,'history':history,'base_checkpoint_sha256':sha(baseline_folder/'graph_planner.pt'),
                'geometry_provenance':[r['geometry_metadata'] for r in records]},output/'model.pt')
    (output/'decoder.json').write_text(json.dumps({'source_planner':selected,'unsupported_geometry_base_threshold':base_threshold,
        'source_ray_baseline':ray_config,'test_previously_observed':True,'fresh_blind_test':False},indent=2),encoding='utf-8')
    (output/'validation-trials.json').write_text(json.dumps({'source_thresholds':trials,'source_ray_baseline_trials':geometric_trials},indent=2),encoding='utf-8')
    # Source features and labels for Train are not loaded until selection is persisted.
    test_record=attach(root,TEST);test=examples(test_record,range(330000,330032));tb=tensors(test,device)
    with torch.no_grad():
        probability=prediction(model,tb).sigmoid().cpu().numpy();base_probability=model.base(tb['x'],tb['observed'],tb['known'],tb['valid']).sigmoid().cpu().numpy()
    test_support=tb['pair_geometry'][...,1::2].sum(-1).cpu().numpy()>0
    predictions={'source_aware_planner':decode(probability,base_probability,test_support,selected['threshold'],base_threshold),
                 'frozen_graph_planner':(base_probability>=base_threshold).astype(np.float32),
                 'source_ray_geometric_baseline':ray_baseline(test,ray_config['threshold'],ray_config['maximum_neighbors'],ray_config['minimum_native_hit_fraction'])}
    geometric_config=json.loads((baseline_folder/'geometric-baseline-validation.json').read_text())['selected']
    predictions['geometric_neighbors']=geometric_neighbors(test,geometric_config['threshold'],geometric_config['maximum_neighbors'])
    scores={name:metrics(p,test) for name,p in predictions.items()}
    scores_supported={}
    for name,p in predictions.items():
        sub=[{**e,'hidden':e['hidden']&test_support[i]} for i,e in enumerate(test)]
        scores_supported[name]=metrics(p,sub)
    passed=all(scores['source_aware_planner']['hidden_directed_edge_IoU']>scores[n]['hidden_directed_edge_IoU'] for n in predictions if n!='source_aware_planner')
    reload_model=SourcePlanner(GraphPlanner()).to(device);reload_model.load_state_dict(torch.load(output/'model.pt',map_location=device,weights_only=False)['state_dict']);reload_model.eval()
    with torch.no_grad():again=prediction(reload_model,tb).sigmoid().cpu().numpy()
    summary={'training_maps':names,'validation_map':VALIDATION,'test_map':TEST,'selected_epoch':best_epoch,'scores':scores,'supported_geometry_scores':scores_supported,
             'hidden_pair_geometry_supported_fraction':float(test_support[np.stack([e['hidden'] for e in test])].mean()),
             'checkpoint_reload_max_difference':float(np.max(np.abs(probability-again))),'beats_all_baselines':passed,
             'source_geometry_scope':'native VMAP faces only; static props, collision and verified opacity omitted',
             'test_geometry_scope':'cached Train section only; unsupported candidate pairs preserve the frozen planner',
             'hidden_NAV_connections_are_not_geometry_feature_inputs':True,'fresh_blind_test':False,'new_layout_or_Hammer_map_generated':False,
             'model_sha256':sha(output/'model.pt'),'script_sha256':sha(__file__)}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    np.savez_compressed(output/'test-predictions.npz',**predictions,probability=probability,source_support=test_support)
    from calibrate_route_organization import draw
    draw(test_record,test,predictions['source_ray_geometric_baseline'],predictions['source_aware_planner'],output/'comparison.png')
    lines=['# Native-source obstruction-aware planner','','The frozen five-map graph planner is augmented with a learned residual correction using native VMAP face rays. Geometry features accept supplied positions and source triangles; they never accept NAV connection labels. Train is excluded from fitting and checkpoint/decoder selection.', '',
           '| Method | Hidden directed-edge IoU | Precision | Recall |','|---|---:|---:|---:|']
    for name,s in scores.items():lines.append(f"| {name} | {s['hidden_directed_edge_IoU']:.3f} | {s['precision']:.3f} | {s['recall']:.3f} |")
    lines += ['',f'Beats the frozen graph model and both geometric baselines: **{passed}**.', '',
        f"Only {summary['hidden_pair_geometry_supported_fraction']:.1%} of hidden Train candidate pairs have supported segment measurements because the source cache covers one section. Unsupported pairs retain the frozen planner and its previous validation-selected threshold. Covered-subset scores are stored separately, not substituted for full-map scores.", '',
        'Boundary probes use eight directions at two heights. Pair probes use three lateral offsets at two heights with a 2048-unit measurement budget. Every observation has a support mask. Native faces are incomplete obstruction evidence: static props, collision, material opacity and ladders are not modeled. A face intersection is not a forbidden gameplay connection.', '',
        'Checkpoint selection uses Cobblestone weighted loss; decoding and the source-ray geometric baseline use Cobblestone only. Configurations are persisted before Train is loaded for evaluation. Train was previously observed, so this is a development experiment. Area positions/count, terminal roles and positive reviewed contexts are supplied, not generated.', '',
        'No map rebuilding, compilation, automatic graph repair or fresh Hammer layout was used. This experiment measures conditional connection reconstruction, not strategic map quality.', '',
        '![First four fixed Train cases](comparison.png)']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=300)
    args=p.parse_args();run(Path(__file__).resolve().parent,args.output,args.epochs)
