"""Experimental variable-area VAE with elevation and source-derived route bends.

Six approved references remain a small development set. Graph constraints,
collision-free grid routing and ramp interpolation are authored adaptations.
"""
import argparse
from collections import Counter
import copy
import hashlib
import heapq
import json
import math
from pathlib import Path
import time

import networkx as nx
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from ortools.sat.python import cp_model

from connected_geometry import floor_cells, validate_floor, elevation
from export_macro_graybox import manifold_cells

N=24
PAIRS=[(a,b) for a in range(N) for b in range(a+1,N)]
G=N*5
E=G+N
DIM=E+len(PAIRS)*5
NAMES=['TSpawn','CTSpawn','SiteA','SiteB']+[f'Junction{i}' for i in range(1,N-3)]


def sample_polyline(points, fraction):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    target=sum(lengths)*fraction
    for a,b,length in zip(points,points[1:],lengths):
        if target<=length:
            return np.asarray(a)+(np.asarray(b)-a)*(target/max(length,1e-9))
        target-=length
    return np.asarray(points[-1])


def encode(graph,capacity=N):
    nodes={n['id']:n for n in graph['nodes']};net=nx.Graph()
    net.add_nodes_from(nodes)
    for edge in graph['edges']:
        a,b=edge['source'],edge['target']
        net.add_edge(a,b,weight=max(1,math.dist(nodes[a]['position'],nodes[b]['position'])))
    def anchor(classname):
        counts=Counter(r for a in graph['anchors'] if a['classname']==classname for r in a['region_ids'])
        return counts.most_common(1)[0][0]
    t,ct=anchor('info_player_terrorist'),anchor('info_player_counterterrorist')
    goals=[max(a['region_ids'],key=lambda r:len(nodes[r]['nav_area_ids'])) for a in graph['anchors'] if a['classname']=='func_bomb_target']
    if len(goals)!=2:raise ValueError('Expected two objectives')
    p,q=np.asarray(nodes[t]['position']),np.asarray(nodes[ct]['position'])
    scale=np.linalg.norm(q[:2]-p[:2]);forward=(q[:2]-p[:2])/scale;right=np.array([forward[1],-forward[0]]);origin=(p+q)/2
    def normalized(r):
        d=np.asarray(nodes[r]['position'])-origin
        return np.array([d[:2]@right,d[:2]@forward,d[2]])/scale
    goals.sort(key=lambda r:normalized(r)[0]);seeds=[t,ct,*goals]
    if len(set(seeds))!=4:raise ValueError('Overlapping terminals')
    component=nx.node_connected_component(net,t)
    if not set(seeds)<=component:raise ValueError('Unreachable terminal')
    net=net.subgraph(component).copy()
    dists=[nx.single_source_dijkstra_path_length(net,s,weight='weight') for s in seeds]
    # Variable landmark count: retain route detail at roughly 600 source units.
    while len(seeds)<capacity:
        candidate=max(sorted(component-set(seeds)),key=lambda r:min(d[r] for d in dists))
        gap=min(d[candidate] for d in dists)
        if len(seeds)>=14 and gap<600:break
        seeds.append(candidate);dists.append(nx.single_source_dijkstra_path_length(net,candidate,weight='weight'))
    seeds=seeds[:4]+sorted(seeds[4:],key=lambda r:math.atan2(normalized(r)[1],normalized(r)[0]))
    dists=[nx.single_source_dijkstra_path_length(net,s,weight='weight') for s in seeds]
    owner={r:min(range(len(seeds)),key=lambda i:(dists[i][r],i)) for r in component}
    links={tuple(sorted((owner[a],owner[b]))) for a,b in net.edges if owner[a]!=owner[b]}
    geom=np.zeros((N,5),np.float32);active=np.zeros(N,np.float32);features=np.zeros((len(PAIRS),5),np.float32)
    for i,r in enumerate(seeds):
        geom[i]=[*normalized(r),*np.clip(np.asarray(nodes[r]['span_xy_units'])/scale,.07,.25)]
        active[i]=1
    source_paths={}
    for k,(a,b) in enumerate(PAIRS):
        if (a,b) not in links:continue
        local=net.subgraph([r for r in component if owner[r] in (a,b)])
        route=nx.shortest_path(local,seeds[a],seeds[b],weight='weight')
        points=[normalized(r)[:2] for r in route]
        bends=[]
        for fraction in (1/3,2/3):
            bends.extend(sample_polyline(points,fraction)-((1-fraction)*geom[a,:2]+fraction*geom[b,:2]))
        features[k]=[1,*bends];source_paths[f'{a}:{b}']=route
    return np.concatenate((geom.flatten(),active,features.flatten())),{
        'map':graph['map'],'active_areas':len(seeds),'requested_capacity':capacity,'landmark_regions':seeds,
        'source_region_owner':owner,'source_routes':source_paths,'source_scale_units':float(scale),
        'height_range_units':float(np.ptp(geom[:len(seeds),2])*scale),
        'notes':['Variable count up to 24; geodesic spacing preserves more junction neighborhoods.',
                 'Two bend residuals per contracted link sampled from a source shortest path.',
                 'XYZ retained; connections symmetrized. NAV regions are not architectural rooms or tactical labels.']}


class RouteVAE(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder=nn.Sequential(nn.Linear(DIM,256),nn.SiLU(),nn.Linear(256,128),nn.SiLU())
        self.mu=nn.Linear(128,12);self.lv=nn.Linear(128,12)
        self.decoder=nn.Sequential(nn.Linear(12,128),nn.SiLU(),nn.Linear(128,256),nn.SiLU(),nn.Linear(256,DIM))
    def forward(self,x):
        h=self.encoder(x);mu=self.mu(h);lv=self.lv(h).clamp(-8,4)
        return self.decoder(mu+torch.randn_like(mu)*(.5*lv).exp()),mu,lv


def objective(pred,target):
    active=target[:,G:E];rows=target[:,:G].reshape(-1,N,5);out=pred[:,:G].reshape(-1,N,5)
    weights=torch.tensor([1,1,8,1,1],device=pred.device)
    geometry=((rows-out).square()*active[:,:,None]*weights).sum()/(active.sum()*12)
    edge=target[:,E:].reshape(-1,len(PAIRS),5);pedge=pred[:,E:].reshape_as(edge)
    mask=torch.stack([active[:,a]*active[:,b] for a,b in PAIRS],dim=1)
    topology=(F.binary_cross_entropy_with_logits(pedge[:,:,0],edge[:,:,0],reduction='none')*mask).sum()/mask.sum()
    bends=((pedge[:,:,1:]-edge[:,:,1:]).square()*edge[:,:,0,None]).sum()/(edge[:,:,0].sum()*4).clamp(min=1)
    return 8*geometry+topology+3*bends+.3*F.binary_cross_entropy_with_logits(pred[:,G:E],active)


def fit(data,device,epochs,validation=None):
    torch.manual_seed(20261011);model=RouteVAE().to(device);opt=torch.optim.Adam(model.parameters(),lr=.001)
    x=torch.tensor(data,device=device);history=[];best=None;best_score=math.inf;best_epoch=epochs
    for epoch in range(1,epochs+1):
        ids=torch.randint(len(x),(24,),device=device);target=x[ids];noise=target.clone()
        noise[:,:G]+=torch.randn_like(noise[:,:G])*.004
        pred,mu,lv=model(noise);loss=objective(pred,target)+.003*(-.5*(1+lv-mu.square()-lv.exp()).mean())
        opt.zero_grad();loss.backward();opt.step()
        if epoch%20==0:
            with torch.no_grad():
                val=torch.tensor(validation if validation is not None else data,device=device)
                reconstruction=model.decoder(model.mu(model.encoder(val)))
                score=float(objective(reconstruction,val))
            history.append({'epoch':epoch,'loss':float(loss.detach()),'reconstruction_score':score})
            if score<best_score:best_score=score;best_epoch=epoch;best=copy.deepcopy(model.state_dict())
    if validation is not None:model.load_state_dict(best)
    return model.eval(),history,best_epoch


def choose_graph(positions,probabilities,count,sizes=None):
    """Learned edge scores subject to explicit connectivity/loop/degree constraints."""
    pairs=[p for p in PAIRS if max(p)<count];scores={}
    for k,(a,b) in enumerate(PAIRS):
        if b>=count:continue
        length=np.linalg.norm(positions[a,:2]-positions[b,:2])/5000
        scores[a,b]=float(probabilities[k])- .18*length
    def cross(u,v):return u[0]*v[1]-u[1]*v[0]
    def intersects(a,b,c,d):
        if len({a,b,c,d})<4:return False
        p,q,r,s=[positions[i,:2] for i in (a,b,c,d)]
        return cross(q-p,r-p)*cross(q-p,s-p)<0 and cross(s-r,p-r)*cross(s-r,q-r)<0
    model=cp_model.CpModel();chosen={p:model.new_bool_var(f'edge{p}') for p in pairs}
    if sizes is not None:
        for a,b in pairs:
            p,q=positions[a,:2],positions[b,:2]
            for other in range(count):
                if other in (a,b):continue
                lower=positions[other,:2]-sizes[other]/2-96;upper=positions[other,:2]+sizes[other]/2+96
                start,end=0.,1.
                for axis in (0,1):
                    delta=q[axis]-p[axis]
                    if abs(delta)<1e-6:
                        if p[axis]<lower[axis] or p[axis]>upper[axis]:start,end=1.,0.;break
                    else:
                        u,v=sorted(((lower[axis]-p[axis])/delta,(upper[axis]-p[axis])/delta))
                        start=max(start,u);end=min(end,v)
                if start<=end:model.add(chosen[a,b]==0);break
    for node in range(count):
        degree=sum(chosen[p] for p in pairs if node in p)
        model.add(degree >= (3 if node in (2,3) else 2));model.add(degree<=4)
    decisions=[]
    for node in range(count):
        degree=sum(chosen[p] for p in pairs if node in p)
        decision=model.new_bool_var(f'decision{node}')
        model.add(degree>=3).only_enforce_if(decision)
        model.add(degree<=2).only_enforce_if(decision.Not())
        decisions.append(decision)
    model.add(sum(decisions)>=8)
    model.add(sum(chosen.values())>=count+5)
    model.add(sum(chosen.values())<=count+8)
    for i,(a,b) in enumerate(pairs):
        for c,d in pairs[i+1:]:
            if intersects(a,b,c,d):model.add(chosen[a,b]+chosen[c,d]<=1)
    # Single-commodity flow proves connectedness. Bridge cuts below require
    # alternate routes, including two edge-disjoint approaches to each site.
    flows={}
    for a,b in pairs:
        for u,v in ((a,b),(b,a)):
            flow=model.new_int_var(0,count-1,f'flow{u},{v}')
            model.add(flow<=(count-1)*chosen[a,b]);flows[u,v]=flow
    for node in range(count):
        incoming=sum(f for (a,b),f in flows.items() if b==node)
        outgoing=sum(f for (a,b),f in flows.items() if a==node)
        model.add(outgoing-incoming==(count-1 if node==0 else -1))
    # Penalize additional links and length while favoring learned edge scores.
    model.minimize(sum(int(1000*(.65-scores[p]))*chosen[p] for p in pairs))
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=3;solver.parameters.num_search_workers=4
    for _ in range(8):
        status=solver.solve(model)
        if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):raise ValueError('No geometrically constrained loop graph')
        graph=nx.Graph();graph.add_nodes_from(range(count))
        graph.add_edges_from(p for p in pairs if solver.value(chosen[p]))
        bridges=list(nx.bridges(graph))
        if not bridges:break
        for a,b in bridges:
            temporary=graph.copy();temporary.remove_edge(a,b);component=nx.node_connected_component(temporary,a)
            model.add(sum(chosen[p] for p in pairs if (p[0] in component)!=(p[1] in component))>=2)
    if list(nx.bridges(graph)):raise ValueError('Unresolved bridge after constrained planning')
    return graph, [{'source':a,'target':b,'probability':float(probabilities[PAIRS.index(tuple(sorted((a,b))))])} for a,b in graph.edges]


def room_cells(region):
    x,y,_=region['center'];w,d,_=region['size']
    return {(a,b) for a in range(int((x-w/2)//64),math.ceil((x+w/2)/64))
                    for b in range(int((y-d/2)//64),math.ceil((y+d/2)/64))}


def audit_floor_graph(plan,cells):
    """Extract corridor components from the built floor, then compare the graph."""
    rooms=plan['design_choices']['regions'];owners={}
    for r in rooms:
        for cell in room_cells(r):
            if cell in owners:raise ValueError('Overlapping exported rooms')
            owners[cell]=r['id']
    remaining=set(cells)-set(owners);components=[];observed=Counter()
    while remaining:
        seed=min(remaining);remaining.remove(seed);todo=[seed];component={seed};contacts=set()
        while todo:
            x,y=todo.pop()
            for other in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if other in owners:contacts.add(owners[other])
                if other in remaining:remaining.remove(other);component.add(other);todo.append(other)
        if len(contacts)!=2:raise ValueError(f'Built corridor has {len(contacts)} room contacts: {sorted(contacts)}')
        pair=tuple(sorted(contacts));observed[pair]+=1
        components.append({'rooms':list(pair),'floor_cells':len(component)})
    expected=Counter(tuple(sorted((e['source'],e['target']))) for e in plan['design_choices']['connections'])
    if observed!=expected:raise ValueError('Built floor junctions differ from planned graph')
    return {'room_count':len(rooms),'corridor_components':len(components),
            'planned_graph_matches_floor_components':True,'components':components,
            'limits':'Floor topology before cover and player hull; not compiled NAV or clearance verification.'}


def route_corridors(regions,edges,controls):
    """Route 192-unit corridors with no unintended intersection outside rooms."""
    footprints=[room_cells(r) for r in regions];all_rooms=set().union(*footprints)
    room_owners={c:i for i,foot in enumerate(footprints) for c in foot}
    centers=[tuple(int(v//64) for v in r['center'][:2]) for r in regions]
    low=(min(x for x,y in all_rooms)-24,min(y for x,y in all_rooms)-24)
    high=(max(x for x,y in all_rooms)+24,max(y for x,y in all_rooms)+24)
    occupied=set();routed=[];lengths=[]
    # Long corridors first reduce the chance they get trapped by nearby connectors.
    edges=sorted(edges,key=lambda ab:-math.dist(centers[ab[0]],centers[ab[1]]))
    for a,b in edges:
        start,goal=centers[a],centers[b];allowed=footprints[a]|footprints[b]
        # A one-cell ring separates unrelated routes; 3x3 square is the corridor footprint.
        blocked={}
        def legal(point):
            if point in blocked:return blocked[point]
            x,y=point
            if not (low[0]<=x<=high[0] and low[1]<=y<=high[1]):return False
            footprint={(x+dx,y+dy) for dx in (-1,0,1) for dy in (-1,0,1)}
            room_clearance={(x+dx,y+dy) for dx in range(-2,3) for dy in range(-2,3)}
            if any(c in all_rooms and c not in allowed for c in room_clearance):blocked[point]=False;return False
            if any((x+dx,y+dy) in occupied and (x+dx,y+dy) not in allowed for dx in range(-2,3) for dy in range(-2,3)):
                blocked[point]=False;return False
            blocked[point]=True;return True
        guide=[np.asarray(p)/64 for p in controls[a,b]]
        def guide_distance(point):
            p=np.asarray(point,float);best=math.inf
            for u,v in zip(guide,guide[1:]):
                delta=v-u;f=np.clip(np.dot(p-u,delta)/max(np.dot(delta,delta),1e-9),0,1)
                best=min(best,float(np.linalg.norm(p-u-f*delta)))
            # Keep embedding topology while allowing source-derived bend guides
            # to influence route shape where space permits.
            u,v=guide[0],guide[-1];delta=v-u
            f=np.clip(np.dot(p-u,delta)/max(np.dot(delta,delta),1e-9),0,1)
            chord=float(np.linalg.norm(p-u-f*delta))
            return best+.8*chord
        cost={start:0.};previous={};queue=[(0.,start)]
        while queue:
            _,point=heapq.heappop(queue)
            if point==goal:break
            x,y=point
            for other in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if not legal(other):continue
                value=cost[point]+1+.12*guide_distance(other)
                if value<cost.get(other,math.inf):
                    cost[other]=value;previous[other]=point
                    heuristic=abs(other[0]-goal[0])+abs(other[1]-goal[1])
                    heapq.heappush(queue,(value+heuristic,other))
        if goal not in previous:raise ValueError(f'Cannot route {a}-{b} without extra junction')
        path=[goal]
        while path[-1]!=start:path.append(previous[path[-1]])
        path.reverse();footprint={(x+dx,y+dy) for x,y in path for dx in (-1,0,1) for dy in (-1,0,1)}
        occupied|=footprint
        # Every path cell is retained, so rasterization reproduces exactly the routed footprint.
        routed.append({'source':regions[a]['id'],'target':regions[b]['id'],
                       'path_xy':[[x*64+32,y*64+32] for x,y in path]})
        lengths.append({'source':a,'target':b,'units':(len(path)-1)*64})
    return routed,all_rooms|occupied,lengths


def attach_heights(plan,cells):
    """Feasible 1:8-per-axis ramps between flat room footprints, shared vertices."""
    rooms=plan['design_choices']['regions'];requested=[r['center'][2] for r in rooms]
    bounds=[]
    for r in rooms:
        x,y,z=r['center'];w,d,_=r['size'];bounds.append((x-w/2,y-d/2,x+w/2,y+d/2))
    factor=1.
    for i,a in enumerate(bounds):
        for j,b in enumerate(bounds[i+1:],i+1):
            distance=max(a[0]-b[2],b[0]-a[2],0)+max(a[1]-b[3],b[1]-a[3],0)
            difference=abs(requested[i]-requested[j])
            if difference:factor=min(factor,.125*distance/difference)
    heights=[round(z*factor,3) for z in requested]
    for r,z in zip(rooms,heights):r['center'][2]=z
    values=[]
    vertices={(x+dx,y+dy) for x,y in cells for dx,dy in ((0,0),(1,0),(1,1),(0,1))}
    for x,y in sorted(vertices):
        lower=[];upper=[];px,py=x*64,y*64
        for z,(l,b,r,t) in zip(heights,bounds):
            distance=max(l-px,px-r,0)+max(b-py,py-t,0)
            lower.append(z-.125*distance);upper.append(z+.125*distance)
        values.append([x,y,round((max(lower)+min(upper))/2,4)])
    plan['design_choices']['floor_vertex_heights']=values
    validate_floor(cells,elevation(plan,cells))
    return {'requested_room_heights':requested,'height_amplitude_retained':factor,
            'exported_room_height_range':max(heights)-min(heights),'maximum_per_axis_slope':.125}


def proposal(vector,world_scale):
    raw=vector[:G].reshape(N,5);presence=1/(1+np.exp(-np.clip(vector[G:E],-30,30)))
    # Prefix presence follows the angular ordering used in encoding; 14 is an authored minimum.
    count=int(np.clip(np.sum(presence>.5),14,N))
    positions=raw[:count,:3].copy()*world_scale
    positions[:,2]=np.clip(positions[:,2],-192,192)
    sizes=np.clip(raw[:count,3:]*world_scale,448,768);sizes[:4]=np.clip(sizes[:4],768,1024)
    original=positions.copy()
    for _ in range(180):
        moved=False
        for a in range(count):
            for b in range(a+1,count):
                gap=(sizes[a]+sizes[b])/2+256-np.abs(positions[a,:2]-positions[b,:2])
                if np.all(gap>0):
                    axis=int(np.argmin(gap));sign=1 if positions[b,axis]>=positions[a,axis] else -1
                    positions[a,axis]-=sign*(gap[axis]+1)/2;positions[b,axis]+=sign*(gap[axis]+1)/2;moved=True
        if not moved:break
    positions[:,:2]=np.round(positions[:,:2]/64)*64
    positions[:,2]=np.round(positions[:,2]/16)*16
    sizes=np.round(sizes/128)*128
    features=vector[E:].reshape(len(PAIRS),5);prob=1/(1+np.exp(-np.clip(features[:,0],-30,30)))
    graph,edge_scores=choose_graph(positions,prob,count,sizes)
    regions=[{'id':NAMES[i],'center':p.tolist(),'size':[float(s[0]),float(s[1]),256]} for i,(p,s) in enumerate(zip(positions,sizes))]
    controls={}
    for a,b in graph.edges:
        a,b=sorted((a,b));k=PAIRS.index((a,b));points=[positions[a,:2]]
        for j,fraction in enumerate((1/3,2/3)):
            points.append((1-fraction)*positions[a,:2]+fraction*positions[b,:2]+np.clip(features[k,1+j*2:3+j*2],-.25,.25)*world_scale)
        points.append(positions[b,:2]);controls[a,b]=points
    edges=list(graph.edges);edges=[tuple(sorted(p)) for p in edges]
    routed,cells,lengths=route_corridors(regions,edges,controls)
    cells,repairs=manifold_cells(cells)
    plan={'design_choices':{'regions':regions,'connections':routed,'corridor_width_units':192,
          'floor_cell_override':sorted(map(list,cells))},
          'preview_title':'HammerGPT: route-aware learned graybox v3',
          'preview_subtitle':'Learned placements, heights and bend guides; authored loop constraints, routing and ramps.',
          'learned_outputs':{'normalized_regions':raw.tolist(),'presence_probabilities':presence.tolist(),
                             'edge_and_bend_outputs':features.tolist()},
          'exporter_adaptations':{'world_scale_units':world_scale,'active_areas':count,
              'room_displacement_units':np.linalg.norm(positions[:,:2]-original[:,:2],axis=1).tolist(),
              'selected_edge_scores':edge_scores,'graph_constraints':'Connected, planar, max degree 4, no bridges/leaves, sites at least three links.',
              'corridor_routing':'A* follows learned bend guides; unrelated routes/rooms blocked. Symmetric 192-unit corridor footprint.',
              'corner_repair_cells':list(map(list,repairs)),'actual_corridor_lengths':lengths}}
    heights=attach_heights(plan,cells);plan['exporter_adaptations']['height_interpolation']=heights
    plan['floor_graph_audit']=audit_floor_graph(plan,cells)
    metrics={'areas':count,'links':graph.number_of_edges(),'cycle_rank':graph.number_of_edges()-count+1,
             'decision_areas':sum(d>=3 for n,d in graph.degree),'dead_end_areas':sum(d==1 for n,d in graph.degree),
             'bridges':len(list(nx.bridges(graph))),'site_entrance_counts':[graph.degree[i] for i in (2,3)],
             'edge_disjoint_t_site_paths':[nx.edge_connectivity(graph,0,i) for i in (2,3)],
             'floor_cells':len(cells),'height_range_units':heights['exported_room_height_range'],
             'below_half_probability_edges':sum(e['probability']<.5 for e in edge_scores),
             'mean_room_displacement_units':float(np.mean(plan['exporter_adaptations']['room_displacement_units']))}
    return plan,metrics


def run(source,output):
    if output.exists():raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    torch.set_num_threads(4);device=torch.device('cuda');manifest=json.loads((source/'manifest.json').read_text())
    vectors=[];records=[]
    for row in manifest['maps']:
        raw=(source/row['graph']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Graph hash mismatch')
        graph=json.loads(raw)
        if graph['dataset_role']!='training' or graph['map'] not in manifest['training_maps']:raise ValueError('Unapproved data')
        for capacity in (16,20,24):
            vector,record=encode(graph,capacity);record['source_graph_sha256']=row['sha256'];vectors.append(vector);records.append(record)
    data=np.stack(vectors);hold=np.array([i for i,r in enumerate(records) if r['map']=='Tuscan'])
    training=np.delete(data,hold,axis=0);start=time.perf_counter()
    _,history,epochs=fit(training,device,600,data[hold])
    model,final_history,_=fit(data,device,epochs)
    output.mkdir(parents=True)
    torch.save({'architecture':'route-vae-24-v2','state_dict':{k:v.cpu() for k,v in model.state_dict().items()},
        'epochs':epochs,'maps':list(dict.fromkeys(r['map'] for r in records))},output/'model.pt')
    checkpoint_hash=hashlib.sha256((output/'model.pt').read_bytes()).hexdigest()
    torch.manual_seed(61011)
    with torch.no_grad():
        latent=torch.randn(48,12,device=device);generated=model.decoder(latent).cpu().numpy()
    restored=RouteVAE().to(device);restored.load_state_dict(torch.load(output/'model.pt',map_location=device,weights_only=True)['state_dict'])
    with torch.no_grad():np.testing.assert_allclose(restored.decoder(latent).cpu().numpy(),generated,atol=1e-5)
    # A 1.35 scale multiplier is an explicit graybox design choice, not learned gameplay balance.
    scale=float(np.median([r['source_scale_units'] for r in records])*1.35)
    candidates=[];plans=[]
    for i,vector in enumerate(generated):
        try:
            plan,metrics=proposal(vector,scale)
            score=metrics['mean_room_displacement_units']+.02*sum(r['units'] for r in plan['exporter_adaptations']['actual_corridor_lengths'])
            score+=40*metrics['below_half_probability_edges']
            candidates.append({'index':i,'status':'routed','score':score,**metrics});plans.append((score,i,plan,metrics))
            print(json.dumps(candidates[-1]),flush=True)
            if len(plans)>=4:break
        except ValueError as error:
            candidates.append({'index':i,'status':'rejected','reason':str(error)})
            print(json.dumps(candidates[-1]),flush=True)
    metrics={'training_maps':list(dict.fromkeys(r['map'] for r in records)),'independent_maps':len(set(r['map'] for r in records)),
        'multi_resolution_examples':len(records),
        'device':torch.cuda.get_device_name(0),'selected_epochs':epochs,'development_holdout':'Tuscan from existing training pool',
        'development_history':history,'final_history':final_history,'records':records,'candidates':candidates,
        'representation':'24-slot capacity; XYZ and dimensions, active-area mask, link logits, two source-derived XY bend residuals/link.',
        'limits':['Six independent layouts; 16/20/24-area encodings give 18 representations, not additional independent data.',
                  'Tuscan reconstruction selects an epoch; final demo refits all six. No fresh generation-quality evaluation.',
                  'Bend guides and heights are learned; constraints, larger scale, room separation, safe corridor routing and ramps are authored.',
                  'No tactical role, sightline, sound, secrecy, player-clearance or balance labels were learned.',
                  'Static single-layer floor cannot reproduce stacked maps or source architectural detail.',
                  'Reserved/validation/test maps were not loaded.'], 'seconds':time.perf_counter()-start}
    np.savez_compressed(output/'training-vectors.npz',vectors=data,generated=generated,latent=latent.cpu().numpy())
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2))
    if not plans:raise RuntimeError('No safely routed candidate; training artifacts retained')
    score,index,plan,summary=min(plans,key=lambda r:(r[0],r[1]))
    plan.update(model_training_performed=True,model_checkpoint_sha256=checkpoint_hash,candidate_index=index,
                structural_metrics=summary,model_source_maps=metrics['training_maps'])
    (output/'proposal.json').write_text(json.dumps(plan,indent=2));print(json.dumps({'selected_candidate':index,**summary}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.source,args.output)
