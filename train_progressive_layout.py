"""Small autoregressive joint spatial graph generator; inspired by GRAN, not GRAN.

Generates count, node roles, descriptors and correlated directed edge rows.
Full coarse graphs; no query map, supplied positions or post-generation repair.
"""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from PIL import Image,ImageDraw,ImageFont
from train_route_organization import sha

FITTING=('dust2','anubis','cache','tuscan','vertigo')
CAPACITY=320


def spatial_transform(x):
    result=x.copy();result[...,3:]=np.log(np.maximum(result[...,3:],1e-4));return result


def load(root,name):
    path=root/'output/route-corpus-expanded-v2'/f'{name}.json';raw=json.loads(path.read_text())
    source=Path(raw['source_graph'])
    if sha(source)!=raw['source_graph_sha256']:raise ValueError('Source changed')
    graph=json.loads(source.read_text());nodes=graph['nodes'];ids=[n['id'] for n in nodes]
    if len(ids)>CAPACITY:raise ValueError('Source exceeds capacity; never truncate')
    ix={k:i for i,k in enumerate(ids)};owner={a:i for i,n in enumerate(nodes) for a in n['nav_area_ids']}
    centers={p['id']:np.mean(p['corners'],axis=0) for p in graph['nav_polygons']}
    t=centers[raw['terminals']['T']['representative_nav_area']];ct=centers[raw['terminals']['CT']['representative_nav_area']]
    scale=float(np.linalg.norm((ct-t)[:2]));forward=(ct-t)[:2]/scale;right=np.array([forward[1],-forward[0]]);origin=(ct+t)/2
    x=[];roles=np.zeros(len(nodes),np.int64)
    for bit,key in enumerate(('T','CT','A','B')):
        for a in raw['terminals'][key]['nav_area_ids']:roles[owner[a]]|=1<<bit
    for n in nodes:
        p=np.asarray(n['position'])-origin
        x.append([p[:2]@right/scale,p[:2]@forward/scale,p[2]/scale,n['height_range_units']/scale,np.log1p(n['summed_nav_polygon_area_xy']/scale**2)])
    y=np.zeros((len(nodes),len(nodes),2),np.float32)
    for e in graph['edges']:
        if not e['witnesses']:raise ValueError('Missing source interface witness')
        a,b=ix[e['source']],ix[e['target']];y[a,b,0]=1;y[b,a,1]=1
    return {'name':name,'x':np.asarray(x,np.float32),'roles':roles,'edges':y,
            'provenance':{'source_graph':str(source),'source_graph_sha256':sha(source),'targets_sha256':sha(path)},'scale_units':scale}


def ordering(record,seed):
    rng=np.random.default_rng(seed);y=record['edges'][...,0];adj=(y+y.T)>0
    roots=np.flatnonzero(record['roles']&1);root=int(rng.choice(roots)) if len(roots) else 0
    result=[];seen=set();queue=[root]
    while len(result)<len(y):
        if not queue:queue=[int(rng.choice([i for i in range(len(y)) if i not in seen]))]
        a=queue.pop(0)
        if a in seen:continue
        seen.add(a);result.append(a)
        neighbors=np.flatnonzero(adj[a]);rng.shuffle(neighbors);queue.extend(int(i) for i in neighbors if i not in seen)
    return np.asarray(result)


def pack(records,seeds,mean,std,device,mirror=True):
    length=max(len(r['x']) for r in records);b=len(records)
    x=np.zeros((b,length,5),np.float32);role=np.zeros((b,length),np.int64);edge=np.zeros((b,length,length,2),np.float32);valid=np.zeros((b,length),bool)
    for k,(r,seed) in enumerate(zip(records,seeds)):
        order=ordering(r,seed);n=len(order);a=r['x'][order].copy()
        if mirror and seed%2:a[:,0]*=-1
        x[k,:n]=(spatial_transform(a)-mean)/std;role[k,:n]=r['roles'][order];edge[k,:n,:n]=r['edges'][order][:,order];valid[k,:n]=True
    result={k:torch.as_tensor(v,device=device) for k,v in {'x':x,'role':role,'edge':edge,'valid':valid}.items()}
    result['count']=result['valid'].sum(1)-1
    return result


class Progressive(nn.Module):
    def __init__(self):
        super().__init__();self.role_embedding=nn.Embedding(16,8);self.start=nn.Parameter(torch.zeros(1,1,18));self.count_logits=nn.Parameter(torch.zeros(CAPACITY))
        self.gru=nn.GRU(18,64,batch_first=True)
        self.role_head=nn.Linear(64,16)
        # Four Gaussian components for positions and descriptors.
        self.space=nn.Linear(64,4+4*5*2)
        self.edge_head=nn.Sequential(nn.Linear(128+5,64),nn.SiLU(),nn.Linear(64,8))
        self.edge_mix=nn.Linear(64,4)

    def representation(self,x,role,edges):
        n=x.shape[1];past=torch.tril(torch.ones(n,n,device=x.device),-1)[None,...,None]
        degree=(edges*past).sum(2)/n
        return torch.cat([x,self.role_embedding(role),degree,degree*0+1/n,torch.arange(n,device=x.device)[None,:,None].expand(x.shape[0],-1,1)/CAPACITY],-1)

    def spatial(self,h):
        raw=self.space(h);mix=raw[...,:4];mu=raw[...,4:24].reshape(*h.shape[:-1],4,5);logstd=raw[...,24:].reshape(*h.shape[:-1],4,5).clamp(-3,1)
        return mix,mu,logstd

    def sampling_input(self,x,role,edges,i,n):
        degree=edges[:,i,:i].sum(1)/n
        return torch.cat([x[:,i],self.role_embedding(role[:,i]),degree,degree*0+1/n,torch.full((1,1),i/CAPACITY,device=x.device)],-1)[:,None]

    def forward(self,data):
        r=self.representation(data['x'],data['role'],data['edge']);inputs=torch.cat([self.start.expand(r.shape[0],-1,-1),r[:,:-1]],1)
        h,_=self.gru(inputs);n=h.shape[1]
        a=h[:,:,None,:].expand(-1,-1,n,-1);b=h[:,None,:,:].expand(-1,n,-1,-1)
        delta=data['x'][:,:,None,:]-data['x'][:,None,:,:]
        edges=self.edge_head(torch.cat([a,b,delta],-1)).reshape(h.shape[0],n,n,4,2)
        return h,edges

    def losses(self,data):
        h,edge_logits=self(data);valid=data['valid'];n=h.shape[1]
        role=F.cross_entropy(self.role_head(h).transpose(1,2),data['role'],reduction='none')
        mix,mu,ls=self.spatial(h);diff=(data['x'][...,None,:]-mu)/ls.exp()
        logp=(-.5*diff.square()-ls-.5*np.log(2*np.pi)).sum(-1)
        space=-torch.logsumexp(F.log_softmax(mix,-1)+logp,-1)
        mask=torch.tril(torch.ones(n,n,device=h.device),-1)[None]*valid[:,:,None]*valid[:,None,:]
        bce=F.binary_cross_entropy_with_logits(edge_logits,data['edge'][...,None,:].expand_as(edge_logits),reduction='none').sum(-1)
        # Joint mixture couples all directed edges in a generated row.
        edge=-torch.logsumexp(F.log_softmax(self.edge_mix(h),-1)-(bce*mask[...,None]).sum(2),-1)
        count=F.cross_entropy(self.count_logits[None].expand(h.shape[0],-1),data['count'])
        terms={'role':(role*valid).sum()/valid.sum(),'space':(space*valid).sum()/valid.sum(),
               'edge':(edge*valid).sum()/valid.sum(),'count':count}
        return sum(terms.values()),terms

    @torch.no_grad()
    def sample(self,seed,mean,std,device):
        torch.manual_seed(seed);n=int(torch.distributions.Categorical(logits=self.count_logits).sample())+1
        x=torch.zeros(1,n,5,device=device);role=torch.zeros(1,n,dtype=torch.long,device=device);edges=torch.zeros(1,n,n,2,device=device)
        hidden=None;inp=self.start
        for i in range(n):
            h,hidden=self.gru(inp,hidden);h=h[:,0]
            role[:,i]=torch.distributions.Categorical(logits=self.role_head(h)).sample()
            mix,mu,ls=self.spatial(h);component=int(torch.distributions.Categorical(logits=mix[0]).sample())
            x[:,i]=mu[:,component]+torch.randn(1,5,device=device)*ls[:,component].exp()
            if i:
                delta=x[:,i,None,:]-x[:,:i,:]
                logits=self.edge_head(torch.cat([h[:,None,:].expand(-1,i,-1),states[:,:i],delta],-1)).reshape(1,i,4,2)
                k=int(torch.distributions.Categorical(logits=self.edge_mix(h)[0]).sample());row=torch.bernoulli(logits[:,:,k].sigmoid())
                edges[:,i,:i]=row;edges[:,:i,i]=row.flip(-1)
            states=h[:,None,:] if i==0 else torch.cat([states,h[:,None,:]],1)
            # Same full-capacity degree divisor and step encoding as teacher forcing.
            inp=self.sampling_input(x,role,edges,i,n)
        geometry=x[0].cpu().numpy()*std+mean
        geometry[:,3:]=np.exp(geometry[:,3:])
        return {'seed':seed,'node_count':n,'descriptors':geometry.tolist(),'roles':role[0].cpu().tolist(),'adjacency':edges[0,...,0].cpu().int().tolist(),'count_capacity_hit':n==CAPACITY}


def statistics(sample):
    a=np.asarray(sample['adjacency']);n=len(a);und=(a+a.T)>0;seen=set();components=[]
    for root in range(n):
        if root in seen:continue
        stack=[root];component=set()
        while stack:
            u=stack.pop()
            if u in seen:continue
            seen.add(u);component.add(u);stack.extend(np.flatnonzero(und[u]).tolist())
        components.append(component)
    roles=np.asarray(sample['roles']);groups=[set(np.flatnonzero(roles&(1<<i))) for i in range(4)]
    terminal_present=[bool(g) for g in groups]
    terminal_connected=all(terminal_present) and any(all(c&g for g in groups) for c in components)
    return {'nodes':n,'directed_edges':int(a.sum()),'components':len(components),'isolated_nodes':int((und.sum(1)==0).sum()),
            'cycle_rank':int(np.triu(und,1).sum()-n+len(components)),'terminal_regions':[len(g) for g in groups],
            'all_terminals_present':all(terminal_present),'terminals_share_component':bool(terminal_connected),
            'negative_height_or_area_descriptors':int((np.asarray(sample['descriptors'])[:,3:]<0).sum())}


def draw(samples,path):
    im=Image.new('RGB',(1500,1060),'#101a26');pen=ImageDraw.Draw(im);font=lambda s:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',s)
    pen.text((20,14),'Progressive generator: six fixed, unfiltered samples',font=font(28),fill='white')
    pen.text((20,52),'Count, positions, roles and connections generated. Lines are topology, not corridors or verified walkability.',font=font(17),fill='#becbd6')
    for k,s in enumerate(samples):
        ox=20+(k%3)*495;oy=100+(k//3)*465;x=np.asarray(s['descriptors'])[:,:2];lo=x.min(0);extent=np.maximum(x.max(0)-lo,.1);scale=min(445/extent[0],335/extent[1]);points=(x-lo)*scale
        def xy(i):return ox+15+points[i,0],oy+45+335-points[i,1]
        a=np.asarray(s['adjacency']);stats=s['statistics']
        pen.text((ox,oy),f"Seed {s['seed']}: {len(x)} areas, {stats['components']} components",font=font(19),fill='white')
        for i,j in zip(*np.nonzero(np.triu((a+a.T)>0,1))):pen.line([xy(i),xy(j)],fill='#536c80',width=1)
        for i,r in enumerate(s['roles']):
            px,py=xy(i);pen.ellipse((px-3,py-3,px+3,py+3),fill='#ecbe58' if r else '#bbceda')
            if r:pen.text((px+3,py),'/'.join(v for bit,v in enumerate(('T','CT','A','B')) if r&(1<<bit)),font=font(11),fill='#f6d990')
        pen.text((ox,oy+394),f"{stats['directed_edges']} links | {stats['isolated_nodes']} isolated | terminals connected: {stats['terminals_share_component']}",font=font(14),fill='#becbd6')
    im.save(path)


def run(root,output,steps):
    output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(4);torch.manual_seed(20261010)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu');records=[load(root,n) for n in FITTING];val=load(root,'cobblestone')
    allx=spatial_transform(np.concatenate([r['x'] for r in records]));mean=allx.mean(0);std=np.maximum(allx.std(0),.05)
    model=Progressive().to(device);opt=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.001);history=[];best=None;best_loss=float('inf')
    validation=pack([val]*4,[9000+i for i in range(4)],mean,std,device,False)
    for step in range(1,steps+1):
        chosen=[records[(step+i)%len(records)] for i in range(5)];data=pack(chosen,[step*10+i for i in range(5)],mean,std,device)
        model.train();opt.zero_grad(set_to_none=True);loss,terms=model.losses(data);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),2);opt.step()
        if step%50==0 or step==steps:
            model.eval()
            with torch.no_grad():vl,vt=model.losses(validation)
            row={'step':step,'fitting_loss':float(loss.detach()),'validation_loss':float(vl),'validation_terms':{k:float(v) for k,v in vt.items()}};history.append(row)
            if float(vl)<best_loss:best_loss=float(vl);best=copy.deepcopy(model.state_dict());selected=step
            print(json.dumps(row),flush=True)
    model.load_state_dict(best);model.eval();torch.save({'state_dict':best,'mean':mean,'std':std,'training_maps':FITTING,'validation_map':'cobblestone','selected_step':selected},output/'model.pt')
    # Fixed seeds declared independently of quality; never reject or repair samples.
    samples=[model.sample(seed,mean,std,device) for seed in range(7100,7106)]
    reloaded=Progressive().to(device);reloaded.load_state_dict(torch.load(output/'model.pt',map_location=device,weights_only=False)['state_dict']);reloaded.eval()
    reload_agreement=reloaded.sample(7100,mean,std,device)==samples[0]
    for s in samples:s['statistics']=statistics(s)
    (output/'samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8');draw(samples,output/'samples.png')
    source_stats=[]
    for r in records:
        s={'adjacency':r['edges'][...,0].tolist(),'roles':r['roles'].tolist(),'descriptors':r['x'].tolist()};source_stats.append({'map':r['name'],**statistics(s)})
    # Score count/degree/role distributions and geometry descriptively; no fake edge-IoU pairing.
    summary={'training_maps':FITTING,'validation_map':'cobblestone','test_or_reserved_maps_loaded':False,'steps':steps,'selected_step':selected,'device':str(device),
        'full_graph_node_counts':{r['name']:len(r['x']) for r in records},'source_statistics':source_stats,'sample_statistics':[s['statistics'] for s in samples],
        'history':history,'provenance':[r['provenance'] for r in records],'validation_provenance':val['provenance'],'checkpoint_reload_sample_agreement':reload_agreement,
        'size_parameterization':'log-positive height and log-positive log1p(area); source zero heights floored at normalized 0.0001',
        'provided_generation_inputs':['random seed','fitting-only normalization'],'provided_source_positions_or_graph_at_generation':False,
        'graph_representation':'all source coarse NAV regions, not architectural rooms','post_generation_repair_or_rejection':False,
        'architecture':'GRU autoregressive node generator, Gaussian-mixture geometry, row-mixture directed Bernoulli edges; GRAN-inspired, not a GRAN reproduction',
        'limitations':['five independent fitting maps','count head has discrete support and can memorize source sizes','BFS ordering is training-only; not new data',
                      'no polygon generation, clearance, sightline or gameplay validation','no fresh test evaluation','no evidence of competitive layout quality'],
        'model_sha256':sha(output/'model.pt'),'script_sha256':sha(__file__)}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Progressive spatial topology generator','','This pilot generates its own area count, descriptors, roles and directed graph. It takes no source map or supplied area positions at sampling time. It is inspired by progressive graph generation (https://arxiv.org/abs/1910.00760), not an implementation of GRAN.', '',
        'Full coarse graphs from Dust2, Anubis, Cache, Tuscan and Vertigo supply fitting targets. Cobblestone selects the checkpoint. Train and reserved maps are not loaded. Training-order permutations and mirrors are augmentations of five maps, not independent organizations.', '',
        '| Seed | Areas | Directed links | Components | Isolated | All terminals connected |','|---|---:|---:|---:|---:|---|']
    for s in samples:
        a=s['statistics'];lines.append(f"| {s['seed']} | {a['nodes']} | {a['directed_edges']} | {a['components']} | {a['isolated_nodes']} | {a['terminals_share_component']} |")
    lines+=['','Six fixed samples are saved without rejection, degree quotas, connectivity repair, handcrafted routes or source copying. Terminal labels may be missing or repeated across generated regions. Positions are normalized by fitting statistics, not a selected reference map.', '',
        'The joint edge-row mixture captures correlations among directed links. Teacher-forced role, Gaussian geometry and row-edge likelihoods plus a separate count likelihood select checkpoints. This objective is not a gameplay score. The count head can memorize the five observed sizes. Size descriptors are generated in log-positive space; zero source heights have a small numerical floor. Positive sizes still do not establish valid geometry. NAV clusters do not equal rooms, and drawn links are not built corridors.', '',
        'This is a generation feasibility experiment, not a demonstrated improvement in strategic map design. No Hammer export or compile occurred. Structural defects remain visible. The next decision should use generated samples and whole-graph statistics, not reconstruction IoU alone.', '', '![Fixed samples](samples.png)']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(json.dumps({k:summary[k] for k in ('selected_step','sample_statistics','device')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--steps',type=int,default=1000);a=p.parse_args();run(Path(__file__).resolve().parent,a.output,a.steps)
