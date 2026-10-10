"""Small whole-layout VAE experiment using six approved coarse training graphs."""
import argparse
from collections import Counter,defaultdict
import copy
import hashlib
import heapq
import json
import math
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

N=12
PAIRS=[(a,b) for a in range(N) for b in range(a+1,N)]
NAMES=['TSpawn','CTSpawn','SiteA','SiteB']+[f'Area{i}' for i in range(1,9)]


def distances(seed,adj):
    result={seed:0.};q=[(0.,seed)]
    while q:
        cost,key=heapq.heappop(q)
        if cost!=result[key]:continue
        for other,w in adj[key].items():
            candidate=cost+w
            if candidate<result.get(other,math.inf):result[other]=candidate;heapq.heappush(q,(candidate,other))
    return result


def encode_graph(graph):
    nodes={n['id']:n for n in graph['nodes']};adj=defaultdict(dict)
    for e in graph['edges']:
        a,b=e['source'],e['target'];w=max(math.dist(nodes[a]['position'],nodes[b]['position']),1)
        adj[a][b]=w;adj[b][a]=w
    def anchor_region(classname):
        counts=Counter(r for a in graph['anchors'] if a['classname']==classname for r in a['region_ids'])
        return counts.most_common(1)[0][0]
    t,ct=anchor_region('info_player_terrorist'),anchor_region('info_player_counterterrorist')
    goals=[a for a in graph['anchors'] if a['classname']=='func_bomb_target']
    goal_regions=[max(a['region_ids'],key=lambda r:len(nodes[r]['nav_area_ids'])) for a in goals]
    if len(goal_regions)!=2:raise ValueError('Expected two objective regions')
    p,q=np.asarray(nodes[t]['position'][:2]),np.asarray(nodes[ct]['position'][:2])
    scale=float(np.linalg.norm(q-p));forward=(q-p)/scale;right=np.array([forward[1],-forward[0]]);origin=(p+q)/2
    def xy(r):
        d=np.asarray(nodes[r]['position'][:2])-origin
        return np.array([d@right,d@forward])/scale
    goal_regions.sort(key=lambda r:xy(r)[0]);seeds=[t,ct,*goal_regions]
    if len(set(seeds))!=4:raise ValueError('Landmark regions overlap')
    reach=distances(t,adj);eligible=set(reach)
    if not set(seeds)<=eligible:raise ValueError('Disconnected objective landmarks')
    dists=[distances(r,adj) for r in seeds]
    while len(seeds)<N:
        chosen=max(sorted(eligible-set(seeds)),key=lambda r:min(d.get(r,math.inf) for d in dists))
        seeds.append(chosen);dists.append(distances(chosen,adj))
    seeds=seeds[:4]+sorted(seeds[4:],key=lambda r:math.atan2(xy(r)[1],xy(r)[0]))
    dists=[distances(r,adj) for r in seeds]
    owner={r:min(range(N),key=lambda i:(dists[i].get(r,math.inf),i)) for r in eligible}
    links={tuple(sorted((owner[a],owner[b]))) for a in eligible for b in adj[a] if b in eligible and owner[a]!=owner[b]}
    rows=[]
    for r in seeds:
        size=np.clip(np.asarray(nodes[r]['span_xy_units'])/scale,.06,.3)
        rows.append([*xy(r),*size])
    values=np.concatenate((np.asarray(rows).flatten(),[float(p in links) for p in PAIRS])).astype(np.float32)
    return values,{'map':graph['map'],'landmark_regions':seeds,'source_region_owner':owner,'source_scale_units':scale,
                   'xy_frame_origin':origin.tolist(),'xy_frame_forward':forward.tolist(),
                   'encoding_notes':['T/CT and two lateral-order objectives anchor twelve regions.',
                                     'Eight additional landmarks use farthest shortest-path distance; remaining regions join nearest landmark.',
                                     'Direction is symmetrized and height is omitted for this flat graybox experiment. A/B are lateral ordering, not source site labels.']}


class MacroVAE(nn.Module):
    def __init__(self):
        super().__init__();self.encoder=nn.Sequential(nn.Linear(114,96),nn.SiLU(),nn.Linear(96,64),nn.SiLU())
        self.mu=nn.Linear(64,4);self.logvar=nn.Linear(64,4)
        self.decoder=nn.Sequential(nn.Linear(4,64),nn.SiLU(),nn.Linear(64,96),nn.SiLU(),nn.Linear(96,114))
    def forward(self,x):
        h=self.encoder(x);mu=self.mu(h);lv=self.logvar(h).clamp(-8,4)
        z=mu+torch.randn_like(mu)*torch.exp(.5*lv)
        return self.decoder(z),mu,lv


def objective(pred,target):
    return F.mse_loss(pred[:,:48],target[:,:48])*5+F.binary_cross_entropy_with_logits(pred[:,48:],target[:,48:])


def fit(data,device,epochs,validation=None):
    torch.manual_seed(20261010);model=MacroVAE().to(device);optimizer=torch.optim.Adam(model.parameters(),lr=.002)
    x=torch.tensor(data,device=device);history=[];best=None;best_value=float('inf');best_epoch=epochs
    for epoch in range(1,epochs+1):
        model.train();ids=torch.randint(len(x),(32,),device=device);target=x[ids];noisy=target.clone()
        noisy[:,:48]+=torch.randn_like(noisy[:,:48])*.006
        pred,mu,lv=model(noisy);loss=objective(pred,target)+.002*(-.5*(1+lv-mu.square()-lv.exp()).mean())
        optimizer.zero_grad();loss.backward();optimizer.step()
        if epoch%20==0:
            model.eval()
            with torch.no_grad():
                target_eval=torch.tensor(validation if validation is not None else data,device=device)
                pred_eval=model.decoder(model.mu(model.encoder(target_eval)))
                score=float(objective(pred_eval,target_eval))
            history.append({'epoch':epoch,'training_loss':float(loss.detach()),'reconstruction_score':score})
            if score<best_value:best_value=score;best=copy.deepcopy(model.state_dict());best_epoch=epoch
    if validation is not None:model.load_state_dict(best)
    return model.eval(),history,best_epoch


def connected_edges(probabilities):
    parent=list(range(N))
    def find(x):
        while parent[x]!=x:x=parent[x]
        return x
    chosen=[];repairs=[]
    for i in sorted(range(len(PAIRS)),key=lambda i:-probabilities[i]):
        a,b=PAIRS[i];different=find(a)!=find(b)
        if probabilities[i]>=.5 or different:
            chosen.append((a,b));parent[find(a)]=find(b)
            if probabilities[i]<.5:repairs.append((a,b))
    return chosen,repairs


def proposal(vector,probabilities):
    raw=vector[:48].reshape(N,4);positions=raw[:,:2]*3600;sizes=np.clip(raw[:,2:]*3600,320,704)
    # Resolve overlapping room footprints explicitly; retain before/after values.
    before=positions.copy()
    for _ in range(120):
        moved=False
        for a,b in PAIRS:
            gap=(sizes[a]+sizes[b])/2+128-np.abs(positions[a]-positions[b])
            if np.all(gap>0):
                axis=int(np.argmin(gap));sign=1 if positions[b,axis]>=positions[a,axis] else -1
                positions[a,axis]-=sign*(gap[axis]+1)/2;positions[b,axis]+=sign*(gap[axis]+1)/2;moved=True
        if not moved:break
    positions=np.round(positions/64)*64;sizes=np.round(sizes/64)*64
    edges,repairs=connected_edges(probabilities)
    regions=[{'id':NAMES[i],'center':[float(p[0]),float(p[1]),0],'size':[float(s[0]),float(s[1]),256]} for i,(p,s) in enumerate(zip(positions,sizes))]
    return {'design_choices':{'regions':regions,'connections':[{'source':NAMES[a],'target':NAMES[b]} for a,b in edges],
                              'corridor_width_units':192},
            'learned_outputs':{'normalized_regions':raw.tolist(),'edge_probabilities':probabilities.tolist()},
            'exporter_adaptations':{'flat_projection':True,'world_scale_units':3600,'minimum_room_size':320,'maximum_room_size':704,
                                    'room_displacement_units':np.linalg.norm(positions-before,axis=1).tolist(),
                                    'below_threshold_connectivity_edges':[list(p) for p in repairs],
                                    'grid_snap_units':64,'corridor_geometry':'authored axis-aligned elbows; intersections can add routes'}}


def run(source,output):
    if output.exists():raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available():raise RuntimeError('CUDA required for requested experiment')
    torch.set_num_threads(4);device=torch.device('cuda');manifest=json.loads((source/'manifest.json').read_text());vectors=[];records=[]
    for row in manifest['maps']:
        raw=(source/row['graph']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Source hash mismatch')
        graph=json.loads(raw)
        if graph['dataset_role']!='training' or graph['map'] not in manifest['training_maps']:raise ValueError('Unapproved training input')
        vector,record=encode_graph(graph);record['source_graph_sha256']=row['sha256'];vectors.append(vector);records.append(record)
    data=np.stack(vectors);hold=next(i for i,r in enumerate(records) if r['map']=='Tuscan');train=np.delete(data,hold,axis=0)
    start=time.perf_counter();dev,history,epoch=fit(train,device,1000,data[hold:hold+1])
    with torch.no_grad():
        val=torch.tensor(data[hold:hold+1],device=device);pred=dev.decoder(dev.mu(dev.encoder(val)))
        dev_score=float(objective(pred,val));mean=train.mean(axis=0);baseline=mean.copy()
        baseline[48:]=np.log(np.clip(mean[48:],.01,.99)/(1-np.clip(mean[48:],.01,.99)))
        baseline_score=float(objective(torch.tensor(baseline[None],device=device),val))
    model,final_history,_=fit(data,device,epoch)
    torch.manual_seed(6027)
    with torch.no_grad():
        z=torch.randn(128,4,device=device);generated=model.decoder(z).cpu().numpy()
    candidates=[]
    for i,v in enumerate(generated):
        probs=1/(1+np.exp(-np.clip(v[48:],-30,30)));plan=proposal(v,probs)
        positions=np.array([r['center'][:2] for r in plan['design_choices']['regions']])
        score=np.mean(plan['exporter_adaptations']['room_displacement_units'])+100*len(plan['exporter_adaptations']['below_threshold_connectivity_edges'])
        score+=max(0,len(plan['design_choices']['connections'])-19)*150
        if np.max(np.abs(positions))>5500:score+=10000
        candidates.append((float(score),i,plan))
    score,index,plan=min(candidates,key=lambda v:(v[0],v[1]));output.mkdir(parents=True)
    torch.save({'architecture':'macro-vae-12-v1','state_dict':{k:v.cpu() for k,v in model.state_dict().items()},'epochs':epoch,'maps':[r['map'] for r in records]},output/'model.pt')
    restored=MacroVAE().to(device);restored.load_state_dict(torch.load(output/'model.pt',map_location=device,weights_only=True)['state_dict'])
    with torch.no_grad():
        np.testing.assert_allclose(restored.decoder(z[index:index+1]).cpu().numpy()[0],generated[index],atol=1e-5)
    plan['model_training_performed']=True;plan['model_checkpoint_sha256']=hashlib.sha256((output/'model.pt').read_bytes()).hexdigest()
    plan['candidate_index']=index;plan['candidate_score']=score
    plan['nearest_source_position_rmse_units']=float(np.min(np.sqrt(np.mean((data[:,:48].reshape(-1,N,4)[:,:,:2]-generated[index,:48].reshape(N,4)[:,:2])**2,axis=(1,2))))*3600)
    (output/'proposal.json').write_text(json.dumps(plan,indent=2))
    np.savez_compressed(output/'training-vectors.npz',vectors=data,generated=generated,latent=z.cpu().numpy())
    metrics={'model_training_performed':True,'device':torch.cuda.get_device_name(0),'independent_maps':6,'training_maps':[r['map'] for r in records],
             'development_holdout':'Tuscan (selected from existing training pool)','development_reconstruction_score':dev_score,
             'mean_baseline_reconstruction_score':baseline_score,'selected_epochs':epoch,'seconds':time.perf_counter()-start,
             'development_history':history,'final_history':final_history,'records':records,'generation_candidate':index,
             'limits':['Six independent maps only; repeated samples/noise do not create new independent maps.',
                       'Tuscan selects the epoch, then all six approved training maps are used in the final demonstration fit.',
                       'Reconstruction sees the held-out input; it is not proof of unconditional generation quality.',
                       'Existing Office/Vertigo and reserved evaluation maps were not loaded.',
                       'Twelve-area flat abstraction; directed links and height are not learned in this first experiment.',
                       'Exported room sizes, non-overlap correction, connectivity repair, corridors, entities and cover are authored constraints.',
                       'Novelty distance only compares encoded landmark positions, not copyright originality or gameplay quality.']}
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2));print(json.dumps({k:v for k,v in metrics.items() if k not in ('records','development_history','final_history')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.source,args.output)
