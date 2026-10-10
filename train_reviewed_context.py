"""Five-map, map-held-out pilot for reviewed local meeting/choke context.

Only NAV areas covered by a reviewed role are supervised. A zero in the other
channel means absent from that reviewed mask, not proven absence of gameplay.
This is a semantic encoder experiment, not a whole-map generator.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

import networkx as nx
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

MAPS=['Dust2','Anubis','Cache','Train','Cobblestone']
FILES={
 'Dust2':'dust2-boundaries-reviewed-v1/boundaries.json',
 'Anubis':'anubis-control-reviewed-v1/control-targets.json',
 'Cache':'cache-reviewed-v1/semantic-targets.json',
 'Train':'train-reviewed-v1/semantic-targets.json',
 'Cobblestone':'cobblestone-reviewed-v1/semantic-targets.json',
}

def area(corners):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(corners,corners[1:]+corners[:1])))/2

def label_coverage(graph,annotation):
    ids={p['id']:i for i,p in enumerate(graph['nav_polygons'])}
    sizes={p['id']:max(area(p['corners']),1e-6) for p in graph['nav_polygons']}
    y=np.zeros((len(ids),2),np.float32)
    def surfaces(items,channel):
        coverage={}
        for item in items:
            for p in item.get('surface_pieces',[]):
                if p['nav_area_id'] in ids:
                    coverage[p['nav_area_id']]=max(coverage.get(p['nav_area_id'],0),area(p['corners']))
        for key,value in coverage.items():y[ids[key],channel]=min(1,value/sizes[key])
    if graph['map']=='Dust2':
        surfaces([a for a in annotation['annotations'] if a['kind']=='meeting_area'],0)
        surfaces([a for a in annotation['annotations'] if a['kind']=='choke_transition'],1)
    elif graph['map']=='Anubis':
        surfaces([s for s in annotation['spatial_targets'] if s['initial_control_proposed']=='meeting'],0)
        for front in annotation['front_contexts']:
            for e in front['directed_links']:
                for w in e['witnesses']:
                    for key in [w['source_nav_area'],w['target_nav_area']]:
                        if key in ids:y[ids[key],1]=1
    elif graph['map']=='Cache':
        regions={r for b in annotation['battleground_contexts'] for r in b['region_ids']}
        for p in graph['nav_polygons']:
            if p['region_id'] in regions:y[ids[p['id']],0]=1
        surfaces(annotation['choke_targets'],1)
    else:
        surfaces(annotation['meeting_targets'],0);surfaces(annotation['choke_targets'],1)
    # Boundary slivers carry no reliable local role contrast in this pilot.
    mask=y.max(axis=1)>=.25
    return y,mask

def features(graph):
    polygons=graph['nav_polygons'];ids={p['id']:i for i,p in enumerate(polygons)}
    centers=np.array([np.mean(p['corners'],axis=0) for p in polygons])
    raw_path=Path(graph['provenance']['nav_export']);raw=raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=graph['provenance']['nav_export_sha256']:raise ValueError('NAV provenance changed')
    nav=json.loads(raw);net=nx.DiGraph();net.add_nodes_from(ids)
    for p in nav['areas']:
        if p['id'] not in ids:continue
        for e in p['connections']:
            b=e['target']
            if b in ids:net.add_edge(p['id'],b,weight=max(1,math.dist(centers[ids[p['id']]],centers[ids[b]])))
    def anchors(classname):
        return sorted({key for a in graph['anchors'] if a['classname']==classname for key in a['nav_area_ids'] if key in ids})
    terminals=[anchors('info_player_terrorist'),anchors('info_player_counterterrorist')]
    for label in ['BombsiteA','BombsiteB']:
        nodes={n['id']:n for n in graph['nodes']}
        regions={r for a in graph['anchors'] if a['classname']=='func_bomb_target' for r in a['region_ids'] if nodes[r]['label']==label}
        terminals.append([p['id'] for p in polygons if p['region_id'] in regions])
    if any(not t for t in terminals):raise ValueError('Missing terminal features')
    t,ct=[np.mean([centers[ids[key]] for key in keys],axis=0) for keys in terminals[:2]]
    scale=max(1,np.linalg.norm(ct[:2]-t[:2]));forward=(ct[:2]-t[:2])/scale;right=np.array([forward[1],-forward[0]])
    distances=[nx.multi_source_dijkstra_path_length(net if i<2 else net.reverse(),keys,weight='weight') for i,keys in enumerate(terminals)]
    rows=[]
    for p,c in zip(polygons,centers):
        corners=np.array(p['corners']);span=np.ptp(corners,axis=0);delta=c-(t+ct)/2
        perimeter=sum(math.dist(a,b) for a,b in zip(p['corners'],p['corners'][1:]+p['corners'][:1]))
        rows.append([delta[:2]@right/scale,delta[:2]@forward/scale,delta[2]/scale,
                     math.log1p(area(p['corners']))/10,math.log1p(perimeter)/8,
                     math.log1p(min(span[:2]))/8,math.log1p(max(span[:2]))/8,span[2]/128,
                     net.in_degree(p['id'])/8,net.out_degree(p['id'])/8,
                     *[min(d.get(p['id'],8*scale)/scale,8) for d in distances]])
    edges=np.array([(ids[a],ids[b]) for a,b in net.edges],dtype=np.int64).T
    return np.array(rows,np.float32),edges

def assemble():
    manifest=json.loads(Path('output/coarse-layout-v1/manifest.json').read_text());lookup={m['map']:m for m in manifest['maps']}
    data=[]
    for name in MAPS:
        entry=lookup[name];graph_path=Path('output/coarse-layout-v1')/entry['graph'];raw=graph_path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Source graph changed')
        graph=json.loads(raw);path=Path('output/annotations')/FILES[name];annotation_raw=path.read_bytes();annotation=json.loads(annotation_raw)
        if graph['dataset_role']!='training' or annotation['source_graph_sha256']!=entry['sha256']:raise ValueError('Invalid training provenance')
        y,mask=label_coverage(graph,annotation);x,edges=features(graph)
        if not mask.any():raise ValueError('No supervised role contexts')
        data.append({'map':name,'x':x,'edges':edges,'y':y,'mask':mask,
                     'provenance':{'source_graph':str(graph_path.resolve()),'source_graph_sha256':entry['sha256'],
                     'annotation':str(path.resolve()),'annotation_sha256':hashlib.sha256(annotation_raw).hexdigest(),
                     'scope':annotation.get('eligible_target_scope'),'nav_areas':len(x),'supervised_areas':int(mask.sum()),
                     'meeting_positive':int((y[mask,0]>=.25).sum()),'choke_positive':int((y[mask,1]>=.25).sum()),
                     'meeting_scope':'named_place_context' if name=='Cache' else 'reviewed_clipped_spatial_footprint',
                     'choke_scope':'witness_area_context' if name=='Anubis' else 'reviewed_neighborhood'}})
    return data

class ContextNet(nn.Module):
    def __init__(self,inputs=14):
        super().__init__();self.input=nn.Linear(inputs,48)
        self.layers=nn.ModuleList([nn.Linear(144,48) for _ in range(2)]);self.out=nn.Linear(48,2)
    def forward(self,x,edges):
        h=F.silu(self.input(x));src,dst=edges
        for layer in self.layers:
            incoming=torch.zeros_like(h);outgoing=torch.zeros_like(h)
            incoming.index_add_(0,dst,h[src]);outgoing.index_add_(0,src,h[dst])
            inc=torch.bincount(dst,minlength=len(h)).clamp_min(1).unsqueeze(1)
            out=torch.bincount(src,minlength=len(h)).clamp_min(1).unsqueeze(1)
            h=F.silu(layer(torch.cat([h,incoming/inc,outgoing/out],dim=1)))
        return self.out(h)

def metrics(y,p):
    truth=y>=.25;pred=p>=.5;result={}
    for i,key in enumerate(['meeting_context','choke_context']):
        a=truth[:,i];b=pred[:,i];tp=int((a&b).sum());fp=int((~a&b).sum());fn=int((a&~b).sum());tn=int((~a&~b).sum())
        result[key]={'f1':2*tp/max(1,2*tp+fp+fn),'balanced_accuracy':.5*(tp/max(1,tp+fn)+tn/max(1,tn+fp)),
                     'positive_support':int(a.sum()),'negative_mask_membership_support':int((~a).sum()),
                     'confusion':{'tp':tp,'fp':fp,'fn':fn,'tn':tn}}
    return result

def fit(data,epochs,device,seed):
    torch.manual_seed(seed);np.random.seed(seed)
    allx=np.concatenate([d['x'] for d in data]);mean=allx.mean(0);std=allx.std(0).clip(.01)
    tensors=[(torch.tensor((d['x']-mean)/std,device=device),torch.tensor(d['edges'],device=device),
              torch.tensor(d['y'],device=device),torch.tensor(d['mask'],device=device),.5 if d['map']=='Cache' else 1.) for d in data]
    labels=np.concatenate([(d['y'][d['mask']]>=.25).astype(np.float32) for d in data])
    counts=labels.sum(0)
    pos_weight=torch.tensor(((len(labels)-counts)/counts.clip(1)).clip(.05,20),device=device)
    model=ContextNet().to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.01)
    for epoch in range(epochs):
        optimizer.zero_grad();loss=0
        for x,e,y,m,w in tensors:
            loss += w*F.binary_cross_entropy_with_logits(model(x,e)[m],(y[m]>=.25).float(),pos_weight=pos_weight)
        loss=loss/sum(t[-1] for t in tensors);loss.backward();optimizer.step()
    model.eval();return model,mean,std,float(loss.detach())

def predict(model,mean,std,d,device):
    with torch.no_grad():
        return model(torch.tensor((d['x']-mean)/std,device=device),torch.tensor(d['edges'],device=device)).sigmoid().cpu().numpy()

def run(output,epochs):
    if output.exists():raise ValueError('Use a new experiment directory')
    if not torch.cuda.is_available():raise RuntimeError('GPU training expected')
    torch.set_num_threads(4);device='cuda';start=time.time();data=assemble();output.mkdir(parents=True)
    (output/'dataset-manifest.json').write_text(json.dumps({'maps':MAPS,'references':[d['provenance'] for d in data],
      'supervision':'Only areas covered >=25% by at least one reviewed context. Other-channel zero means reviewed-mask nonmembership, not gameplay absence.',
      'cache_context_loss_weight':.5,'excluded_maps':'All other training, validation, test and reserved references.',
      'role_membership_threshold':.25,'overlapping_piece_policy':'Maximum single reviewed footprint coverage per role; avoids double-counting overlapping masks.',
      'loss':'Binary mask membership with per-head positive/negative balance computed only from each training fold.',
      'features':'Geometry, directed adjacency and terminal geodesic context only; no place names, map identity, annotation coverage or heat pixels.'},indent=2))
    print(json.dumps({'device':torch.cuda.get_device_name(0),'supervised_areas':{d['map']:int(d['mask'].sum()) for d in data}}),flush=True)
    folds=[]
    for i,held in enumerate(data):
        training=[d for d in data if d is not held];model,mean,std,loss=fit(training,epochs,device,410+i)
        p=predict(model,mean,std,held,device);m=held['mask'];y=held['y'][m]
        prior=np.average(np.array([d['y'][d['mask']].mean(0) for d in training]),axis=0)
        baseline=np.tile(prior,(len(y),1))
        fold={'held_out_map':held['map'],'training_maps':[d['map'] for d in training],
              'model':metrics(y,p[m]),'constant_training_prior_baseline':metrics(y,baseline),'training_loss':loss}
        folds.append(fold);np.savez_compressed(output/f"heldout-{held['map'].lower()}.npz",probabilities=p,targets=held['y'],supervision_mask=m)
        (output/'fold-results.json').write_text(json.dumps(folds,indent=2))
        print(json.dumps(fold),flush=True)
    model,mean,std,loss=fit(data,epochs,device,500)
    checkpoint=output/'context-encoder.pt'
    torch.save({'state_dict':model.cpu().state_dict(),'mean':torch.tensor(mean),'std':torch.tensor(std),
                'maps':MAPS,'epochs':epochs,'task':'reviewed_local_context_distinction'},checkpoint)
    saved=torch.load(checkpoint,weights_only=True);restored=ContextNet().to(device);restored.load_state_dict(saved['state_dict']);restored.eval()
    reference=predict(model.to(device),mean,std,data[0],device)
    reloaded=predict(restored,saved['mean'].numpy(),saved['std'].numpy(),data[0],device)
    error=float(np.max(np.abs(reference-reloaded)))
    if error>1e-6:raise RuntimeError('Checkpoint reload mismatch')
    summary={'task':'reviewed_local_context_distinction','maps':MAPS,'device':torch.cuda.get_device_name(0),
             'trainer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'epochs_per_fold_and_final_fit':epochs,'whole_map_heldout_folds':folds,'final_training_loss':loss,
             'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),'reload_max_error':error,
             'elapsed_seconds':time.time()-start,'model_training_performed':True,
             'limits':['Five independent maps are a pilot, not enough to certify generalization.',
                       'Evaluation includes reviewed-covered areas only, not detection across unlabeled map regions.',
                       'Cache context and Anubis witness labels differ from precise masks; results retain map-specific scope.',
                       'One fixed seed per fold; no epoch selection on held-out maps. No reserved evaluation maps used.',
                       'This semantic encoder does not generate maps or verify gameplay quality.']}
    (output/'summary.json').write_text(json.dumps(summary,indent=2))
    lines=['# Reviewed context training pilot','','GPU training completed on five approved maps with five whole-map held-out folds.','',
           '| Held-out map | Meeting F1 | Choke F1 | Prior meeting F1 | Prior choke F1 |','|---|---:|---:|---:|---:|']
    for f in folds:lines.append(f"| {f['held_out_map']} | {f['model']['meeting_context']['f1']:.3f} | {f['model']['choke_context']['f1']:.3f} | {f['constant_training_prior_baseline']['meeting_context']['f1']:.3f} | {f['constant_training_prior_baseline']['choke_context']['f1']:.3f} |")
    lines+=['','## Limits','']+['- '+s for s in summary['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'completed':True,'elapsed_seconds':summary['elapsed_seconds'],'reload_error':error}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=120)
    a=p.parse_args();run(a.output,a.epochs)
