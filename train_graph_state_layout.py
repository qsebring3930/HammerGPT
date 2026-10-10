"""Bounded matched experiment adding causal full-prefix graph messages.

Every prefix is encoded independently: future positions, roles and edges are
excluded, including edges among earlier nodes added in the future.
"""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from scipy.sparse.csgraph import dijkstra
from PIL import Image,ImageDraw,ImageFont
from train_progressive_layout import Progressive,FITTING,CAPACITY,load,pack,spatial_transform,statistics
from train_route_organization import sha


class GraphStateProgressive(Progressive):
    def __init__(self):
        super().__init__();self.start=nn.Parameter(torch.zeros(1,1,50));self.gru=nn.GRU(50,64,batch_first=True)
        self.graph_input=nn.Linear(13,16)
        self.graph_layers=nn.ModuleList([nn.Linear(48,16) for _ in range(2)])

    def graph_messages(self,features,adjacency):
        h=F.silu(self.graph_input(features))
        outgoing=adjacency/adjacency.sum(-1,keepdim=True).clamp_min(1)
        incoming=adjacency.transpose(-1,-2);incoming=incoming/incoming.sum(-1,keepdim=True).clamp_min(1)
        for layer in self.graph_layers:
            h=F.silu(layer(torch.cat([h,torch.bmm(outgoing,h),torch.bmm(incoming,h)],-1)))
        return h

    def representation(self,x,role,edges):
        base=super().representation(x,role,edges);b,n,_=x.shape
        features=torch.cat([x,self.role_embedding(role)],-1);indices=torch.arange(n,device=x.device)
        local=[];pooled=[]
        # A separate masked GNN per completed prefix, batched in small chunks.
        for offset in range(0,n,12):
            steps=indices[offset:offset+12];k=len(steps);present=indices[None,:]<=steps[:,None]
            adjacency=edges[:,None,:,:,0]*present[None,:,:,None]*present[None,:,None,:]
            encoded=self.graph_messages(features[:,None].expand(-1,k,-1,-1).reshape(b*k,n,13),adjacency.reshape(b*k,n,n)).reshape(b,k,n,16)
            local.append(encoded[:,torch.arange(k,device=x.device),steps])
            pooled.append((encoded*present[None,:,:,None]).sum(2)/present.sum(-1)[None,:,None])
        return torch.cat([base,torch.cat(local,1),torch.cat(pooled,1)],-1)

    def sampling_input(self,x,role,edges,i,n):
        base=super().sampling_input(x,role,edges,i,n)
        features=torch.cat([x[:,:i+1],self.role_embedding(role[:,:i+1])],-1)
        encoded=self.graph_messages(features,edges[:,:i+1,:i+1,0])
        return torch.cat([base,encoded[:,i:i+1],encoded.mean(1,keepdim=True)],-1)


def measures(sample):
    result=statistics(sample);a=np.asarray(sample['adjacency']);x=np.asarray(sample['descriptors']);r=np.asarray(sample['roles']);n=len(a)
    distance=dijkstra(np.where(a>0,1,0),directed=True)
    groups=[np.flatnonzero(r&(1<<i)) for i in range(4)]
    access=[]
    for origin in (0,1):
        for target in (2,3):
            access.append(bool(len(groups[origin]) and len(groups[target]) and np.isfinite(distance[groups[origin]][:,groups[target]]).any()))
    degrees=((a+a.T)>0).sum(-1)
    lengths=np.linalg.norm(x[:,None,:3]-x[None,:,:3],axis=-1)[a>0]
    result.update({'directed_spawn_site_access_pairs':int(sum(access)),'all_four_directed_access_pairs':all(access),
        'isolated_fraction':result['isolated_nodes']/n,'cycle_rank_per_node':result['cycle_rank']/n,
        'mean_degree':float(degrees.mean()),'degree_over_six_fraction':float((degrees>6).mean()),
        'mean_normalized_link_length':float(lengths.mean()) if len(lengths) else 0,
        'planar_extent_aspect_ratio':float(max(np.ptp(x[:,:2],axis=0))/max(min(np.ptp(x[:,:2],axis=0)),1e-6))})
    return result


def aggregate(samples):
    rows=[measures(s) for s in samples]
    keys=('nodes','directed_edges','isolated_fraction','cycle_rank_per_node','mean_degree','degree_over_six_fraction','mean_normalized_link_length')
    result={k:float(np.mean([r[k] for r in rows])) for k in keys}
    result.update({'samples':len(rows),'all_terminals_present':sum(r['all_terminals_present'] for r in rows),
                   'terminals_share_component':sum(r['terminals_share_component'] for r in rows),
                   'all_four_directed_access_pairs':sum(r['all_four_directed_access_pairs'] for r in rows)})
    return result,rows


def comparison_picture(old,new,path):
    im=Image.new('RGB',(1600,1150),'#101a26');p=ImageDraw.Draw(im);font=lambda s:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',s)
    p.text((25,20),'Same seeds: previous generator / graph-state generator',font=font(29),fill='white')
    p.text((25,62),'First three fixed samples. Actual generated positions. These are graph diagnostics, not radar floorplans.',font=font(19),fill='#c3cfd9')
    for row in range(3):
        for col,s in enumerate((old[row],new[row])):
            ox=25+col*800;oy=110+row*340;x=np.asarray(s['descriptors']);a=np.asarray(s['adjacency']);stats=measures(s)
            p.text((ox,oy),f"{'Previous' if col==0 else 'Graph state'} | seed {s['seed']} | {len(x)} areas",font=font(21),fill='white')
            lo=x[:,:2].min(0);extent=np.maximum(np.ptp(x[:,:2],axis=0),.1);scale=min(650/extent[0],235/extent[1]);pos=(x[:,:2]-lo)*scale
            def xy(i):return ox+50+pos[i,0],oy+40+235-pos[i,1]
            for i,j in zip(*np.nonzero(np.triu((a+a.T)>0,1))):p.line([xy(i),xy(j)],fill='#425d72',width=1)
            for i,r in enumerate(s['roles']):
                px,py=xy(i);p.ellipse((px-2,py-2,px+2,py+2),fill='#eac45f' if r else '#b7cad8')
                if r:p.text((px+3,py),'/'.join(n for bit,n in enumerate(('T','CT','A','B')) if r&(1<<bit)),font=font(12),fill='#f4d980')
            p.text((ox,oy+285),f"Isolated: {stats['isolated_nodes']} | mean degree: {stats['mean_degree']:.1f} | directed access: {stats['directed_spawn_site_access_pairs']}/4",font=font(18),fill='#c3cfd9')
    im.save(path)


def run(root,output,steps):
    output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(4);torch.manual_seed(20261010)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu');records=[load(root,n) for n in FITTING];val_record=load(root,'cobblestone')
    allx=spatial_transform(np.concatenate([r['x'] for r in records]));mean=allx.mean(0);std=np.maximum(allx.std(0),.05)
    model=GraphStateProgressive().to(device);opt=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.001)
    val=pack([val_record]*4,[9000+i for i in range(4)],mean,std,device,False)
    baseline_folder=root/'output/training/progressive-layout-v2';checkpoint=torch.load(baseline_folder/'model.pt',map_location=device,weights_only=False)
    if tuple(checkpoint['training_maps'])!=FITTING or not np.array_equal(mean,checkpoint['mean']) or not np.array_equal(std,checkpoint['std']):raise ValueError('Baseline corpus or normalization differs')
    baseline=Progressive().to(device);baseline.load_state_dict(checkpoint['state_dict']);baseline.eval()
    history=[];best_loss=float('inf');best=None
    for step in range(1,steps+1):
        data=pack([records[(step+i)%5] for i in range(5)],[step*10+i for i in range(5)],mean,std,device)
        model.train();opt.zero_grad(set_to_none=True);loss,terms=model.losses(data);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),2);opt.step()
        if step%50==0 or step==steps:
            model.eval()
            with torch.no_grad():value,parts=model.losses(val)
            row={'step':step,'fitting_loss':float(loss.detach()),'validation_loss':float(value),'validation_terms':{k:float(v) for k,v in parts.items()}};history.append(row)
            if float(value)<best_loss:best_loss=float(value);best=copy.deepcopy(model.state_dict());selected_step=step
            print(json.dumps(row),flush=True)
    model.load_state_dict(best);model.eval()
    torch.save({'state_dict':best,'mean':mean,'std':std,'training_maps':FITTING,'validation_map':'cobblestone','selected_step':selected_step,'model_class':'GraphStateProgressive'},output/'model.pt')
    (output/'selection.json').write_text(json.dumps({'selected_step':selected_step,'validation_loss':best_loss,'selection':'four fixed Cobblestone prefix likelihoods; no generated-sample tuning','sampling_seeds':list(range(7100,7132))},indent=2))
    # Selection is final before free generation; all 32 seeds retained.
    old=[];new=[]
    for seed in range(7100,7132):
        old.append(baseline.sample(seed,mean,std,device));new.append(model.sample(seed,mean,std,device))
        if seed%8==3:print(f'Compared samples through seed {seed}',flush=True)
    old_metrics,old_rows=aggregate(old);new_metrics,new_rows=aggregate(new)
    sources=[{'descriptors':r['x'].tolist(),'roles':r['roles'].tolist(),'adjacency':r['edges'][...,0].tolist()} for r in records];source_metrics,_=aggregate(sources)
    for s,row in zip(old,old_rows):s['statistics']=row
    for s,row in zip(new,new_rows):s['statistics']=row
    reload_model=GraphStateProgressive().to(device);reload_model.load_state_dict(torch.load(output/'model.pt',map_location=device,weights_only=False)['state_dict']);reload_model.eval()
    reloaded=reload_model.sample(7100,mean,std,device);reload_match=all(reloaded[k]==new[0][k] for k in reloaded)
    original_samples=json.loads((baseline_folder/'samples.json').read_text());baseline_match=all(all(old[i][k]==original_samples[i][k] for k in ('seed','node_count','descriptors','roles','adjacency')) for i in range(6))
    with torch.no_grad():baseline_val,_=baseline.losses(val)
    summary={'training_maps':FITTING,'validation_map':'cobblestone','test_or_reserved_maps_loaded':False,'steps':steps,'selected_step':selected_step,
        'baseline_validation_loss':float(baseline_val),'graph_state_validation_loss':best_loss,'baseline_metrics':old_metrics,'graph_state_metrics':new_metrics,'source_metrics':source_metrics,
        'checkpoint_reload_agreement':reload_match,'first_six_baseline_samples_reproduced':baseline_match,'baseline_checkpoint_sha256':sha(baseline_folder/'model.pt'),
        'provenance':[r['provenance'] for r in records],'validation_provenance':val_record['provenance'],'history':history,'device':str(device),
        'architecture_change':'two directed message-passing layers on every completed prefix; newest-node and mean whole-prefix context added to recurrent input',
        'unchanged':['corpus','normalization','orders and mirrors','1000 steps','optimizer and rate','heads and sampling distributions','count capacity','validation selection','no repair or rejection'],
        'limitations':['model has more parameters; no capacity-matched ablation','five independent fitting maps','same seeds do not guarantee identical node counts between checkpoints','teacher forcing differs from free generation','no floor polygons or radar generated','development comparison not competitive gameplay evaluation'],
        'model_sha256':sha(output/'model.pt'),'script_sha256':sha(__file__)}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'baseline-samples.json').write_text(json.dumps(old),encoding='utf-8');(output/'samples.json').write_text(json.dumps(new),encoding='utf-8')
    comparison_picture(old,new,output/'comparison.png')
    lines=['# Graph-state progressive generator comparison','','Two directed message-passing layers encode each completed graph prefix. Newest-node and whole-prefix context enter the recurrent generator. Positions, roles and edges from future nodes are masked out; sampling uses only its own generated graph.', '',
       'The same full graphs, fitting normalization, ordering/mirror seeds, optimizer, 1000 steps and four Cobblestone validation orders are used. Heads, count distribution and sampling remain unchanged. Train and reserved maps are not loaded. Checkpoint selection is persisted before generating 32 fixed samples. Nothing is repaired or rejected.', '',
       '| Metric | Previous | Graph state | Fitting source mean |','|---|---:|---:|---:|']
    for key in ('nodes','isolated_fraction','mean_degree','cycle_rank_per_node','mean_normalized_link_length'):
        lines.append(f'| {key} | {old_metrics[key]:.3f} | {new_metrics[key]:.3f} | {source_metrics[key]:.3f} |')
    for key in ('all_terminals_present','terminals_share_component','all_four_directed_access_pairs'):
        lines.append(f'| {key} | {old_metrics[key]}/32 | {new_metrics[key]}/32 | {source_metrics[key]}/5 |')
    lines+=['',f'Selected step: {selected_step}. Validation likelihood loss: previous {float(baseline_val):.3f}, graph state {best_loss:.3f}. This is not a gameplay score.', '',
       f'Baseline first six saved samples reproduced: {baseline_match}. New checkpoint sample reload agreement: {reload_match}.', '',
       'The model is larger; a capacity-matched control is not run. These are descriptive development results from five independent fitting maps, not proof of strategic design ability. All-four directed access requires at least one generated region per role and some directed route for each spawn/site pair; it does not validate every spawn or imply clearance. Repeated site roles are region labels, not extra bombsite entities.', '',
       'Source graphs also contain some isolated regions. Link-length and cycle statistics are normalized and compared without graph repair. Counts can differ because count weights differ at validation-selected steps. Independent samples from one checkpoint are not independent training maps.', '',
       'Outputs remain graphs with positions, not rooms or engine geometry. The comparison image is explicitly a diagnostic graph drawing, not a radar.','', '![First three fixed cases](comparison.png)']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (output/'training-script.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'baseline':old_metrics,'graph_state':new_metrics,'reload_match':reload_match,'baseline_match':baseline_match}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--steps',type=int,default=1000);a=p.parse_args();run(Path(__file__).resolve().parent,a.output,a.steps)
