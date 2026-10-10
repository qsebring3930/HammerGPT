"""Whole-map-conditioned directed topology completion, not empty-canvas generation."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from scipy.optimize import linear_sum_assignment
from PIL import Image, ImageDraw, ImageFont

N, FEATURES = 64, 13
TRAIN = ('dust2','anubis','cache')
VALIDATION, TEST = 'cobblestone', 'train'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encode(root,name,target_directory=None):
    path=(Path(target_directory) if target_directory else root/'output/gameplay-route-targets-v5')/f'{name}.json'
    raw=json.loads(path.read_text());source=Path(raw['source_graph'])
    if sha(source)!=raw['source_graph_sha256']:raise ValueError('Source graph changed')
    graph=json.loads(source.read_text());nodes={n['id']:n for n in graph['nodes']}
    owner={a:n['id'] for n in graph['nodes'] for a in n['nav_area_ids']}
    selected={owner[a] for row in raw['route_sets'] for route in row['routes'] for a in route['path']}
    # Keep actual recorded connections between supplied areas, including links
    # not used by the selected route samples. Those are not negative examples.
    roles={key:set(owner[a] for a in terminal['nav_area_ids']) for key,terminal in raw['terminals'].items()}
    nav_centers={p['id']:np.mean(p['corners'],axis=0) for p in graph['nav_polygons']}
    t=nav_centers[raw['terminals']['T']['representative_nav_area']]
    ct=nav_centers[raw['terminals']['CT']['representative_nav_area']]
    scale=float(np.linalg.norm((ct-t)[:2]));forward=(ct-t)[:2]/scale;right=np.array([forward[1],-forward[0]])
    origin=(t+ct)/2
    def xyz(key):
        p=np.array(nodes[key]['position'])-origin
        return np.array([p[:2]@right,p[:2]@forward,p[2]])/scale
    ids=sorted(selected,key=lambda k:(float(np.arctan2(xyz(k)[1],xyz(k)[0])),float(np.linalg.norm(xyz(k)[:2])),k))
    if len(ids)>N:raise ValueError('Capacity exceeded; do not truncate a source graph')
    index={key:i for i,key in enumerate(ids)}
    x=np.zeros((N,FEATURES),np.float32);y=np.zeros((N,N),np.float32);valid=np.zeros(N,bool);valid[:len(ids)]=True
    meeting={owner[a] for c in raw['meeting_contexts'] for a in c['centroid_supported_nav_ids']}
    choke={owner[a] for c in raw['choke_contexts'] for pair in c['directed_nav_pairs'] for a in pair if a in owner}
    for key,i in index.items():
        n=nodes[key];m=float(key in meeting);c=float(key in choke)
        x[i]=[*xyz(key),n['height_range_units']/scale,np.log1p(n['summed_nav_polygon_area_xy']/scale**2),
              *[float(key in roles[r]) for r in ('T','CT','A','B')],m,m,c,c]
    for edge in graph['edges']:
        if edge['source'] in index and edge['target'] in index:
            if not edge['witnesses']:raise ValueError('Connection missing original NAV witness')
            y[index[edge['source']],index[edge['target']]]=1
    return {'map':name,'x':x,'y':y,'valid':valid,'ids':ids,'roles':{r:sorted(index[k] for k in values if k in index) for r,values in roles.items()},
            'provenance':{'route_targets':str(path.resolve()),'route_targets_sha256':sha(path),
                          'source_graph':str(source.resolve()),'source_graph_sha256':sha(source)},'scale_units':scale}


def mask_example(record,seed):
    rng=np.random.default_rng(seed);count=int(record['valid'].sum())
    pivot=int(rng.integers(count));size=int(rng.integers(5,min(13,count)))
    distance=np.linalg.norm(record['x'][:count,:3]-record['x'][pivot,:3],axis=1)
    holes=np.zeros(N,bool);holes[np.argsort(distance,kind='stable')[:size]]=True
    pairs=record['valid'][:,None]&record['valid'][None,:]&~np.eye(N,dtype=bool)
    hidden=pairs&(holes[:,None]|holes[None,:])
    known=pairs&~hidden
    return {'x':record['x'].copy(),'observed':record['y']*known,'known':known.astype(np.float32),
            'hidden':hidden,'valid':record['valid'].copy(),'target':record['y'].copy(),'holes':holes,'seed':int(seed)}


def batch(examples,device):
    return {k:torch.as_tensor(np.stack([e[k] for e in examples]),device=device) for k in ('x','observed','known','hidden','valid','target')}


class GraphPlanner(nn.Module):
    def __init__(self):
        super().__init__();self.input=nn.Linear(FEATURES,48)
        self.layers=nn.ModuleList([nn.Linear(144,48) for _ in range(3)])
        self.norms=nn.ModuleList([nn.LayerNorm(48) for _ in range(3)])
        self.output=nn.Sequential(nn.Linear(102,64),nn.SiLU(),nn.Linear(64,32),nn.SiLU(),nn.Linear(32,1))

    def forward(self,x,observed,known,valid):
        h=F.silu(self.input(x))*valid[...,None]
        out=observed/observed.sum(-1,keepdim=True).clamp_min(1)
        incoming=observed.transpose(1,2);incoming=incoming/incoming.sum(-1,keepdim=True).clamp_min(1)
        for layer,norm in zip(self.layers,self.norms):
            h=F.silu(norm(h+layer(torch.cat([h,torch.bmm(out,h),torch.bmm(incoming,h)],dim=-1))))*valid[...,None]
        a=h[:,:,None,:].expand(-1,-1,N,-1);b=h[:,None,:,:].expand(-1,N,-1,-1)
        delta=x[:,None,:,:3]-x[:,:,None,:3]
        features=torch.cat([a,b,delta,torch.linalg.vector_norm(delta,dim=-1,keepdim=True),observed[...,None],known[...,None]],dim=-1)
        return self.output(features).squeeze(-1)


class FlatPlanner(nn.Module):
    """Matched denoising baseline using the legacy planner's flat MLP approach.

    Adapted to 64 supplied slots; no historical checkpoint or VAE target encoder.
    """
    def __init__(self):
        super().__init__();self.net=nn.Sequential(nn.Linear(N*FEATURES+2*N*N,128),nn.SiLU(),nn.Linear(128,96),nn.SiLU(),nn.Linear(96,N*N))

    def forward(self,x,observed,known,valid):
        return self.net(torch.cat([x.flatten(1),observed.flatten(1),known.flatten(1)],dim=1)).reshape(-1,N,N)


def loss_for(logits,target,hidden,weight):
    loss=F.binary_cross_entropy_with_logits(logits,target,pos_weight=torch.tensor(weight,device=logits.device),reduction='none')
    return (loss*hidden).sum()/hidden.sum().clamp_min(1)


def fit(model,records,validation,device,epochs):
    model=model.to(device);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001)
    schedule=torch.optim.lr_scheduler.CosineAnnealingLR(opt,epochs)
    weight_examples=[mask_example(r,12000+i) for r in records for i in range(32)]
    positives=sum((e['target']*e['hidden']).sum() for e in weight_examples)
    negatives=sum(e['hidden'].sum()-(e['target']*e['hidden']).sum() for e in weight_examples)
    weight=float(negatives/max(positives,1));val=batch(validation,device)
    best,best_loss,best_epoch=None,float('inf'),0;history=[]
    for epoch in range(1,epochs+1):
        examples=[mask_example(records[i%len(records)],100000+epoch*100+i) for i in range(24)]
        # Mirror only during fitting; source map identity and place names never enter the model.
        for i,e in enumerate(examples):
            if (epoch+i)%2:e['x'][:,0]*=-1
        data=batch(examples,device);model.train();opt.zero_grad(set_to_none=True)
        logits=model(data['x'],data['observed'],data['known'],data['valid'])
        loss=loss_for(logits,data['target'],data['hidden'],weight);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),2);opt.step();schedule.step()
        if epoch%10==0 or epoch==epochs:
            model.eval()
            with torch.no_grad():
                logits=model(val['x'],val['observed'],val['known'],val['valid'])
                value=float(loss_for(logits,val['target'],val['hidden'],weight))
            history.append({'epoch':epoch,'train_loss':float(loss.detach()),'validation_loss':value})
            if value<best_loss:
                best_loss,best_epoch=value,epoch;best=copy.deepcopy(model.state_dict())
            if epoch%50==0:print(json.dumps({'model':type(model).__name__,'epoch':epoch,'validation_loss':value}),flush=True)
    model.load_state_dict(best)
    return model,{'history':history,'selected_epoch':best_epoch,'training_only_positive_weight':weight,'parameters':sum(p.numel() for p in model.parameters())}


def retrieval(examples,records):
    predictions,neighbors=[],[]
    for example in examples:
        count=int(example['valid'].sum());query=example['x'][:count]
        candidates=[]
        for record in records:
            reference=record['x'][record['valid']]
            for mirror in (1,-1):
                ref=reference.copy();ref[:,0]*=mirror
                cost=np.linalg.norm(query[:,None,:3]-ref[None,:,:3],axis=-1)
                cost+=4*np.abs(query[:,None,5:9]-ref[None,:,5:9]).sum(-1)
                cost+=.5*np.abs(query[:,None,9:]-ref[None,:,9:]).sum(-1)
                rows,columns=linear_sum_assignment(cost)
                mapping=np.full(N,-1,int);mapping[rows]=columns
                pred=np.zeros((N,N),np.float32)
                for a in rows:
                    for b in rows:pred[a,b]=record['y'][mapping[a],mapping[b]]
                known=example['known'].astype(bool)
                # Candidate selection sees supplied features and known links only.
                positive=known&(example['observed']>0)
                mismatch=float(np.abs(pred-example['observed'])[positive].mean()) if positive.any() else 0
                score=float(cost[rows,columns].mean())+mismatch
                candidates.append((score,record['map'],mirror,pred))
        _,name,mirror,pred=min(candidates,key=lambda c:(c[0],c[1],c[2]))
        predictions.append(pred);neighbors.append({'map':name,'mirror':mirror})
    return np.asarray(predictions),neighbors


def metrics(probabilities,examples):
    target=np.stack([e['target'] for e in examples])>0
    hidden=np.stack([e['hidden'] for e in examples]);pred=probabilities>=.5
    tp=int((pred&target&hidden).sum());fp=int((pred&~target&hidden).sum());fn=int((~pred&target&hidden).sum())
    return {'hidden_directed_edge_IoU':tp/max(tp+fp+fn,1),'precision':tp/max(tp+fp,1),'recall':tp/max(tp+fn,1),
            'F1':2*tp/max(2*tp+fp+fn,1),'true_positive':tp,'false_positive':fp,'false_negative':fn,
            'hidden_positive_prevalence':float(target[hidden].mean())}


def geometric_neighbors(examples,threshold,maximum_neighbors):
    predictions=[]
    for example in examples:
        positions=example['x'][:,:3];distance=np.linalg.norm(positions[:,None]-positions[None,:],axis=-1)
        valid=example['valid'][:,None]&example['valid'][None,:]&~np.eye(N,dtype=bool)
        distance=np.where(valid,distance,np.inf)
        pred=np.zeros((N,N),np.float32)
        for a in np.flatnonzero(example['valid']):
            neighbors=np.argsort(distance[a],kind='stable')[:maximum_neighbors]
            pred[a,neighbors[distance[a,neighbors]<=threshold]]=1
        predictions.append(pred)
    return np.asarray(predictions)


def draw(record,examples,predictions,output):
    # First four fixed masks, never selected by quality. Every method uses the same positions.
    width,height=2500,1850;im=Image.new('RGB',(width,height),'#101a26');pen=ImageDraw.Draw(im)
    font=lambda s:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',s)
    titles=['Observed connections','Copy nearest training map','Legacy-style flat MLP','Graph planner','Original directed NAV']
    pen.text((25,20),'Train: fixed first four topology-completion examples',font=font(30),fill='#eef4fa')
    pen.text((25,62),'Positions and reviewed context are supplied. This is not a new generated map. Green = recovered edge; red = extra edge; yellow = missed edge.',font=font(19),fill='#bccbdb')
    count=int(record['valid'].sum());pos=record['x'][:count,:2];lo=pos.min(0);hi=pos.max(0)
    scale=min(390/max(hi[0]-lo[0],.1),305/max(hi[1]-lo[1],.1))
    for row,e in enumerate(examples[:4]):
        for col,title in enumerate(titles):
            ox,oy=20+col*500,115+row*430
            pen.text((ox,oy),title,font=font(21),fill='#edf3fa')
            def xy(i):return ox+40+(pos[i,0]-lo[0])*scale,oy+60+(hi[1]-pos[i,1])*scale
            truth=e['target']>0
            if col==0:pred=e['observed']>0
            elif col==4:pred=truth
            else:pred=predictions[col-1][row]>=.5
            assembled=np.where(e['known']>0,e['observed']>0,pred)
            if col==0:assembled=pred
            for a in range(count):
                for b in range(count):
                    if a==b:continue
                    exists=assembled[a,b];miss=truth[a,b] and not exists and e['hidden'][a,b]
                    if not exists and not miss:continue
                    color='#536a79' if e['known'][a,b] else '#73d59c' if exists and truth[a,b] else '#ec737c' if exists else '#d6b653'
                    if col==4:color='#73d59c' if e['hidden'][a,b] else '#536a79'
                    if col==0 and miss:continue
                    pen.line([xy(a),xy(b)],fill=color,width=2)
            for i in range(count):
                x,y=xy(i);pen.ellipse((x-3,y-3,x+3,y+3),fill='#f7d867' if e['holes'][i] else '#c0ced9')
            for role,ids in record['roles'].items():
                if ids:
                    x,y=xy(ids[0]);pen.text((x+4,y),role,font=font(15),fill='#ffffff',stroke_width=1,stroke_fill='#101a26')
            if col in (1,2,3):
                score=metrics(predictions[col-1][row:row+1],[e]);pen.text((ox,oy+365),f"Hidden edge IoU {score['hidden_directed_edge_IoU']:.2f}",font=font(18),fill='#bccbdb')
    im.save(output)


def run(root,output,epochs,training_maps=TRAIN,target_directory=None):
    output.mkdir(parents=True,exist_ok=False);start=time.time()
    torch.set_num_threads(4);device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if set(training_maps)&{VALIDATION,TEST}:raise ValueError('Whole-map split overlap')
    records=[encode(root,n,target_directory) for n in training_maps];validation_record=encode(root,VALIDATION,target_directory)
    validation=[mask_example(validation_record,220000+i) for i in range(32)]
    # Strong geometry-only baseline selected on validation before Train is loaded.
    trials=[]
    for threshold in (.08,.12,.16,.2,.25,.32,.4,.5):
        for neighbors in (2,3,4,6):
            value=metrics(geometric_neighbors(validation,threshold,neighbors),validation)
            trials.append({'threshold':threshold,'maximum_neighbors':neighbors,**value})
    geometric_config=max(trials,key=lambda t:(t['hidden_directed_edge_IoU'],t['precision']))
    (output/'geometric-baseline-validation.json').write_text(json.dumps({'selected':geometric_config,'trials':trials},indent=2),encoding='utf-8')
    models,training={},{}
    for name,cls in [('flat_MLP',FlatPlanner),('graph_planner',GraphPlanner)]:
        torch.manual_seed(20261009)
        model,info=fit(cls(),records,validation,device,epochs)
        checkpoint={'state_dict':{k:v.cpu() for k,v in model.state_dict().items()},'training_maps':list(training_maps),
                    'validation_map':VALIDATION,'test_map':TEST,'training_info':info,'task':'conditional_directed_topology_completion',
                    'feature_count':FEATURES,'capacity':N,'input_provenance':[r['provenance'] for r in records]}
        torch.save(checkpoint,output/f'{name}.pt');models[name]=model.to(device);training[name]=info
    # Test graph and targets enter only after both checkpoints have been selected.
    test_record=encode(root,TEST,target_directory);test=[mask_example(test_record,330000+i) for i in range(32)]
    test_batch=batch(test,device);predictions={};reload_checks={}
    for name,model in models.items():
        model.eval()
        with torch.no_grad():prob=model(test_batch['x'],test_batch['observed'],test_batch['known'],test_batch['valid']).sigmoid().cpu().numpy()
        cls=FlatPlanner if name=='flat_MLP' else GraphPlanner
        reloaded=cls().to(device);reloaded.load_state_dict(torch.load(output/f'{name}.pt',map_location=device,weights_only=False)['state_dict']);reloaded.eval()
        with torch.no_grad():again=reloaded(test_batch['x'],test_batch['observed'],test_batch['known'],test_batch['valid']).sigmoid().cpu().numpy()
        reload_checks[name]=float(np.max(np.abs(prob-again)));predictions[name]=prob
    nearest,neighbors=retrieval(test,records);predictions['nearest_training_map']=nearest
    predictions['geometric_neighbors']=geometric_neighbors(test,geometric_config['threshold'],geometric_config['maximum_neighbors'])
    predictions['empty_hidden']=np.zeros_like(nearest)
    scores={name:metrics(prob,test) for name,prob in predictions.items()}
    gate=all(scores['graph_planner']['hidden_directed_edge_IoU']>scores[b]['hidden_directed_edge_IoU'] for b in ('flat_MLP','nearest_training_map','geometric_neighbors'))
    summary={'task':'conditional_directed_topology_completion','training_maps':list(training_maps),'validation_map':VALIDATION,'test_map':TEST,
             'test_previously_observed_in_project':True,'fresh_blind_test':False,'positions_and_node_count_supplied':True,
             'unknown_tactical_roles_not_supervised':True,'threshold':.5,'epochs':epochs,'training':training,'scores':scores,
             'checkpoint_reload_max_difference':reload_checks,'beats_both_baselines_on_hidden_edge_IoU':gate,
             'gate_includes_geometry_only_baseline':True,'geometric_baseline_validation_selected':geometric_config,
             'empty_canvas_generation_trained':False,'new_layout_or_Hammer_map_generated':False,
             'elapsed_seconds':time.time()-start,'device':torch.cuda.get_device_name() if device.type=='cuda' else 'CPU',
             'source_records':[r['provenance'] for r in [*records,validation_record,test_record]],
             'checkpoint_hashes':{name:sha(output/f'{name}.pt') for name in models},'script_sha256':sha(__file__)}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'retrieval-neighbors.json').write_text(json.dumps(neighbors,indent=2),encoding='utf-8')
    np.savez_compressed(output/'test-predictions.npz',**predictions,target=np.stack([e['target'] for e in test]),hidden=np.stack([e['hidden'] for e in test]),observed=np.stack([e['observed'] for e in test]),x=test_record['x'])
    (output/'test-records.json').write_text(json.dumps({'map':TEST,'seeds':[e['seed'] for e in test],'node_ids':test_record['ids'],'roles':test_record['roles']},indent=2),encoding='utf-8')
    draw(test_record,test,[nearest,predictions['flat_MLP'],predictions['graph_planner']],output/'comparison.png')
    lines=['# Conditional whole-map topology planner experiment','',f"Fitting maps: {', '.join(training_maps)}. Cobblestone selects checkpoints. Train is excluded from fitting and checkpoint selection. Fixed 32 validation masks and 32 Train masks; all masks on one map are correlated observations, not independent maps.", '',
           '| Method | Hidden directed-edge IoU | Precision | Recall | F1 |', '|---|---:|---:|---:|---:|']
    for name,score in scores.items():lines.append(f"| {name} | {score['hidden_directed_edge_IoU']:.3f} | {score['precision']:.3f} | {score['recall']:.3f} | {score['F1']:.3f} |")
    lines += ['',f"Graph model beats the flat MLP, nearest-map and geometry-only baselines on hidden-edge IoU: **{gate}**.", '',
        '## What was learned', '',
        'A directed message-passing model receives normalized XYZ positions, area/height descriptors, terminal roles, positive reviewed encounter/choke context with unknown masks, and visible directed connections. It predicts missing directed connections around a spatially chosen group of supplied areas. Targets are recorded NAV interfaces between route-supported coarse areas; valid source connections unused by a sampled route are retained.', '',
        'Known empty and unknown hidden pairs are distinguished. Hidden connection labels never enter model features, mask selection, or retrieval candidate selection. Masks are selected by geometry, not positive-edge labels. All checkpoint selection uses Cobblestone weighted loss; class weights use fitting maps only. Fixed threshold 0.5; no Train-driven threshold search. Place names and map identity do not enter the models.', '',
        'The flat MLP baseline is retrained using the same inputs, masks, split, loss and epochs; it follows the legacy flat-network approach but is adapted to 64 supplied nodes. It is not the old VAE checkpoint. Historical checkpoints saw Train, so using them as held-out benchmarks would contaminate the comparison. Nearest-map copying uses only fitting maps, node assignment from supplied spatial/context features, and visible edge agreement.', '',
        '## Limits and generation decision', '',
        '- Positions, area count and positive reviewed contexts are supplied from source maps. This tests conditional connection reconstruction, not invention of room positions, route count or whole-map geometry.',
        '- Train has been inspected in this project before: this is a fixed-split development experiment, not a fresh blind evaluation. This remains a small independent-map corpus.',
        '- Coarse areas are not architectural rooms. Source interfaces are directed evidence, not collision, clearance, actual traversal times or ladders. Source NAV freshness remains unresolved.',
        '- Recovering interfaces does not establish sensible strategic choices, cover, sightlines, first contact or map quality. The corrected Train flank remains a conditional later flank in source data; unknown route-purpose labels are not invented or trained as opening attacks.',
        '- No arbitrary graph repair, minimum loop quota, generated Hammer map or empty-canvas layout sample is used to disguise a reconstruction failure.',
        '- A positive result would support the conditional topology component only. A negative result blocks a claim of improved whole-layout generation; next changes must be justified by the observed errors or corpus expansion.', '',
        '![Fixed first four Train examples](comparison.png)']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('scores','beats_both_baselines_on_hidden_edge_IoU','elapsed_seconds')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=300)
    p.add_argument('--training-maps',nargs='+',default=list(TRAIN));p.add_argument('--targets',type=Path)
    args=p.parse_args();run(Path(__file__).resolve().parent,args.output,args.epochs,args.training_maps,args.targets)
