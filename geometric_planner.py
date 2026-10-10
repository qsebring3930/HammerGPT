"""Office development: geometry features, missed-link costs and candidate ranking."""
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

from train_connection_planner import ConnectionPlanner,pair_inputs,pair_targets,plan_scores,complete
from train_conditioned import ports,reference_plan,ConditionedNet,topology
from train_patch import patch_input,load_target,patch_scores,preview,interpolation
from improve_connection_planner import transform_features
from evaluate_topology import local_view,components
from solver_planner import solve_plan


def port_geometry(context,cells):
    normals=[]; neighborhood=set()
    for r,c in cells:
        sides=[]
        if r==0: sides.append((1,0))
        if r==9: sides.append((-1,0))
        if c==0: sides.append((0,1))
        if c==9: sides.append((0,-1))
        for dr,dc in sides:
            normals.append((dr,dc))
            for distance in range(1,5):
                for lateral in range(-1,2):
                    rr=r+11-dr*distance-dc*lateral; cc=c+11-dc*distance+dr*lateral
                    if 0<=rr<32 and 0<=cc<32 and context[1,rr,cc]>0: neighborhood.add((rr,cc))
    normal=np.mean(normals,axis=0) if normals else np.zeros(2)
    strength=float(np.linalg.norm(normal)); unit=normal/strength if strength else normal
    density=float(np.mean([context[0,r,c] for r,c in neighborhood])) if neighborhood else 0.
    return np.asarray(cells).mean(axis=0),unit,strength,density


def geometry_inputs(contexts,indices):
    descriptions=[]; guessed=[]; visible=[]; groups=[]
    for original in contexts:
        x=original[:2].copy(); x[0]*=x[1]; visible.append(x)
        gs=ports(x); groups.append(gs); descriptions.append([port_geometry(x,g) for g in gs])
    predicted=interpolation(np.asarray(visible))
    guessed=[reference_plan(x,p) for x,p in zip(visible,predicted)]
    rows=[]
    for i,a,b in indices:
        ca,na,sa,da=descriptions[i][a]; cb,nb,sb,db=descriptions[i][b]
        delta=cb-ca; distance=float(np.linalg.norm(delta)); direction=delta/distance if distance else np.zeros(2)
        separation=min(np.linalg.norm(np.asarray(pa)-pb) for pa in groups[i][a] for pb in groups[i][b])
        rows.append([min(len(groups[i][a]),len(groups[i][b]))/40,max(len(groups[i][a]),len(groups[i][b]))/40,
                     distance/(9*np.sqrt(2)),separation/(9*np.sqrt(2)),(np.dot(na,nb)+1)/2,
                     (np.dot(na,direction)-np.dot(nb,direction)+2)/4,min(sa,sb),max(sa,sb),min(da,db),max(da,db),
                     float(visible[i][0].sum()/max(visible[i][1].sum(),1)),float(guessed[i][a]==guessed[i][b])])
    return np.asarray(rows,dtype=np.float32).reshape(-1,12)


class GeometryPlanner(ConnectionPlanner):
    def __init__(self):
        super().__init__(); self.head=nn.Sequential(nn.Linear(64*4*4+12,64),nn.ReLU(),nn.Linear(64,1))

    def forward(self,x,geometry):
        return self.head(torch.cat((self.features(x).flatten(1),geometry),dim=1)).squeeze(1)


def proposal_plans(matrix):
    p=np.clip(matrix,1e-6,1-1e-6); logits=np.log(p)-np.log1p(-p); choices=[]; info=[]
    for bias in (-.75,-.25,0.,.25,.75):
        adjusted=1/(1+np.exp(-(logits+bias))); np.fill_diagonal(adjusted,1)
        plan,diagnostic=solve_plan(adjusted)
        if plan not in choices: choices.append(plan); info.append({'bias':bias,**diagnostic})
    for plan in ([0]*len(matrix),list(range(len(matrix)))):
        if plan not in choices: choices.append(plan); info.append({'bias':None,'status':'explicit_extreme'})
    return choices,info


def rank_cost(context,prediction,plan,matrix):
    """No reference target: score confidence and fulfillment of the proposed plan."""
    actual=reference_plan(context,prediction); pairs=list(itertools.combinations(range(len(plan)),2))
    violations=sum((plan[a]==plan[b])!=(actual[a]==actual[b]) for a,b in pairs)/max(len(pairs),1)
    likelihood=-sum(np.log(np.clip(matrix[a,b] if plan[a]==plan[b] else 1-matrix[a,b],1e-6,1)) for a,b in pairs)/max(len(pairs),1)
    grid=local_view(context,prediction); covered=np.zeros((10,10),dtype=bool)
    for r in range(9):
        for c in range(9):
            if grid[r:r+2,c:c+2].all(): covered[r:r+2,c:c+2]=True
    inside=grid[1:9,1:9]; narrow=float((inside & ~covered[1:9,1:9]).sum()/max(inside.sum(),1))
    _,gs=components(grid); islands=sum(len(g) for g in gs if all(1<=r<9 and 1<=c<9 for r,c in g))/64
    return {'total':float(likelihood+2*violations+.25*narrow+.1*islands),'negative_mean_log_score':float(likelihood),
            'plan_violation_fraction':float(violations),'narrow_cell_fraction':narrow,'island_pixel_fraction':islands}


def infer(model,contexts,use_geometry,device):
    features,indices,counts=pair_inputs(contexts); g=geometry_inputs(contexts,indices)
    if not use_geometry: g[:]=0
    scores=[]; model.eval()
    with torch.no_grad():
        for start in range(0,len(features),128):
            scores.extend(torch.sigmoid(model(torch.tensor(features[start:start+128],device=device),torch.tensor(g[start:start+128],device=device))).cpu().tolist())
    matrices=[np.eye(n) for n in counts]
    for (i,a,b),score in zip(indices,scores): matrices[i][a,b]=matrices[i][b,a]=score
    return matrices


def fit(features,geometry,labels,vfeatures,vgeometry,vlabels,config,epochs,device):
    torch.manual_seed(20261009); model=GeometryPlanner().to(device); optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    torch.manual_seed(20261009)
    tx,tg,ty,vx,vg,vy=[torch.tensor(a,device=device) for a in (features,geometry,labels,vfeatures,vgeometry,vlabels)]
    if not config['geometry']: tg.zero_(); vg.zero_()
    best=None; best_loss=float('inf'); best_epoch=0; history=[]
    for epoch in range(1,epochs+1):
        model.train(); total=0
        for ids in torch.randperm(len(tx),device=device).split(128):
            batch=transform_features(tx[ids],torch.randint(8,(len(ids),),device=device))
            optimizer.zero_grad(); loss=F.binary_cross_entropy_with_logits(model(batch,tg[ids]),ty[ids],pos_weight=torch.tensor(config['positive_cost'],device=device))
            loss.backward(); optimizer.step(); total+=loss.item()*len(ids)
        model.eval()
        with torch.no_grad(): validation=sum(F.binary_cross_entropy_with_logits(model(vx[ids],vg[ids]),vy[ids]).item()*len(ids) for ids in torch.arange(len(vx),device=device).split(128))/len(vx)
        record={'epoch':epoch,'weighted_train_bce':total/len(tx),'unweighted_validation_bce':validation}; history.append(record)
        if validation<best_loss: best_loss=validation; best=copy.deepcopy(model.state_dict()); best_epoch=epoch
        if epoch==1 or epoch%10==0: print(json.dumps({'arm':config['name'],**record}),flush=True)
    model.load_state_dict(best); model.eval(); return model,history,best_epoch,best_loss


def experiment(dataset,floor_checkpoint,previous,output,epochs=40):
    if output.exists(): raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available(): raise RuntimeError('CUDA required')
    torch.set_num_threads(4); device=torch.device('cuda'); manifest=json.loads((dataset/'manifest.json').read_text())
    cohort=json.loads((dataset.parent.parent/'evaluation-reservations.json').read_text())['maps']
    if set(manifest['splits']['train'])&set(manifest['splits']['validation']): raise ValueError('Map leakage')
    if {r['name'] for r in cohort}&set(manifest['splits']['train']+manifest['splits']['validation']): raise ValueError('Evaluation cohort used for development')
    manifest_hash=hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()
    floor_state=torch.load(floor_checkpoint,map_location=device,weights_only=True)
    if floor_state['dataset_manifest_sha256']!=manifest_hash: raise ValueError('Floor provenance mismatch')
    floor=ConditionedNet().to(device); floor.load_state_dict(floor_state['state_dict']); floor.eval()
    # Read only development archives; observed cohort predictions are not loaded.
    y=load_target(dataset,'train',manifest); vy=load_target(dataset,'validation',manifest); x=patch_input(y); vx=patch_input(vy)
    truth=[reference_plan(a,b) for a,b in zip(x,y)]; vtruth=[reference_plan(a,b) for a,b in zip(vx,vy)]
    features,indices,_=pair_inputs(x); vfeatures,vindices,_=pair_inputs(vx)
    g=geometry_inputs(x,indices); vg=geometry_inputs(vx,vindices); labels=pair_targets(indices,truth); vlabels=pair_targets(vindices,vtruth)
    prior=json.loads((previous/'metrics.json').read_text())
    if prior['dataset_manifest_sha256']!=manifest_hash or prior['floor_checkpoint_sha256']!=hashlib.sha256(floor_checkpoint.read_bytes()).hexdigest(): raise ValueError('Prior provenance mismatch')
    with np.load(previous/'validation_predictions.npz') as d:
        if not np.array_equal(d['x'],vx) or not np.array_equal(d['y'],vy): raise ValueError('Previous examples mismatch')
        old=d['prediction'].copy()
    configs=[{'name':'context_control','geometry':False,'positive_cost':1.},
             {'name':'geometry','geometry':True,'positive_cost':1.},
             {'name':'geometry_recall','geometry':True,'positive_cost':2.}]
    output.mkdir(parents=True); arms={}; outputs={}; start=time.perf_counter()
    for config in configs:
        name=config['name']; model,history,epoch,loss=fit(features,g,labels,vfeatures,vg,vlabels,config,epochs,device)
        torch.save({'architecture':'geometric-pair-cnn-v1','state_dict':{k:v.cpu() for k,v in model.state_dict().items()},'configuration':config,'best_epoch':epoch,'dataset_manifest_sha256':manifest_hash},output/(name+'.pt'))
        restored=GeometryPlanner().to(device); restored.load_state_dict(torch.load(output/(name+'.pt'),map_location=device,weights_only=True)['state_dict']); restored.eval()
        with torch.no_grad():
            query=torch.tensor(vfeatures[:1],device=device); geom=torch.tensor(vg[:1] if config['geometry'] else np.zeros_like(vg[:1]),device=device)
            if not torch.allclose(model(query,geom),restored(query,geom),atol=1e-6): raise RuntimeError('Reload mismatch')
        matrices=infer(model,vx,config['geometry'],device)
        single_solved=[solve_plan(p) for p in matrices]; single=[p for p,info in single_solved]; single_pred=complete(floor,vx,single,device)
        candidates=[]; owners=[]; candidate_info=[]
        for i,p in enumerate(matrices):
            ps,info=proposal_plans(p); candidate_info.append(info)
            for plan in ps: candidates.append(plan); owners.append(i)
        candidate_pred=complete(floor,vx[owners],candidates,device); groups=[[] for _ in vx]
        costs=[rank_cost(vx[i],pred,plan,matrices[i]) for i,pred,plan in zip(owners,candidate_pred,candidates)]
        for k,i in enumerate(owners): groups[i].append(k)
        winners=[min(group,key=lambda k:costs[k]['total']) for group in groups]
        ranked=[candidates[k] for k in winners]; ranked_pred=candidate_pred[winners]
        methods={}
        for method,plans,pred in [('single_plan',single,single_pred),('ranked_candidates',ranked,ranked_pred)]:
            methods[method]={'plan':plan_scores(plans,vtruth),'pixels':patch_scores(pred,vy),'topology':topology(vx,vy,pred)}; outputs[name,method]=pred
            quality=[rank_cost(a,b,p,m) for a,b,p,m in zip(vx,pred,plans,matrices)]
            methods[method]['mean_plan_violation_fraction']=float(np.mean([q['plan_violation_fraction'] for q in quality]))
            methods[method]['mean_narrow_cell_fraction']=float(np.mean([q['narrow_cell_fraction'] for q in quality]))
        arms[name]={'configuration':config,'best_epoch':epoch,'best_validation_bce':loss,'history':history,'methods':methods,'candidate_count':len(candidates),
                    'single_solver_optimal_examples':sum(info['optimal'] for p,info in single_solved),'single_solver_fallback_examples':sum(info['fallback'] is not None for p,info in single_solved)}
        (output/(name+'-candidates.json')).write_text(json.dumps({'owners':owners,'plans':candidates,'costs':costs,'chosen_indices':winners,'solver_diagnostics':candidate_info},indent=2))
    chosen=min(arms,key=lambda n:arms[n]['best_validation_bce']); selected=outputs[chosen,'ranked_candidates']
    result={'model_training_performed':True,'device':torch.cuda.get_device_name(0),'epochs_per_arm':epochs,'seconds':round(time.perf_counter()-start,2),
            'training_maps':manifest['splits']['train'],'validation_maps':manifest['splits']['validation'],'dataset_manifest_sha256':manifest_hash,
            'floor_checkpoint_sha256':hashlib.sha256(floor_checkpoint.read_bytes()).hexdigest(),'selected_arm':chosen,'selected_method':'ranked_candidates','arms':arms,
            'cohort_evaluated_this_run':False,'test_evaluated':False,'automatic_hammer_generation_enabled':False,
            'limits':['Office is reused development validation; the previously observed evaluation cohort was not rerun or loaded.',
                      'All arms use augmentation and the same architecture. Control geometry inputs are zero. Arm and checkpoint selection use unweighted validation BCE.',
                      'The positive-cost arm doubles loss for connected labels. Its sigmoid outputs are cost-sensitive scores, not calibrated probabilities.',
                      'Candidate biases and ranking coefficients were fixed before this run. Ranking uses predicted plans and floors only, never hidden reference geometry.',
                      'Width is a raster proxy: fraction of hidden occupied cells outside any full 2x2 floor square. It does not establish player clearance or architectural quality.',
                      'This remains a single-seed local-patch study. Future confirmation after tuning needs a new cohort.']}
    (output/'metrics.json').write_text(json.dumps(result,indent=2)); np.savez_compressed(output/'validation_predictions.npz',x=vx,y=vy,prediction=selected)
    preview(vx,vy,old,selected,output/'validation-preview.png',('Hidden patch','Previous planner','Geometry + ranking','Recorded target'))
    lines=['# Geometry and candidate-ranking experiment','','Office development; frozen floor model.','',
           '| Arm | Method | Plan pair accuracy | Patch IoU | Required pairs preserved | Broken-route cases | Extra-connection cases |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for name,arm in arms.items():
        for method,m in arm['methods'].items():
            t=m['topology']; lines.append(f"| {name} | {method} | {m['plan']['accuracy']:.3f} | {m['pixels']['hidden_pixel_iou']:.3f} | {t['preserved_pairs']}/{t['required_pairs']} | {t['examples_with_broken_connection']} | {t['examples_with_extra_connection']} |")
    lines+=['',f'Selected arm by pair BCE: {chosen}. Candidate cost: negative mean plan log score + 2 * plan-violation fraction + 0.25 * narrow-cell fraction + 0.1 * island-pixel fraction. Previews use four fixed indices.','','## Limits','']+['- '+a for a in result['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps({'selected':chosen,'arms':{n:a['methods'] for n,a in arms.items()}}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--dataset',type=Path,required=True); parser.add_argument('--floor-checkpoint',type=Path,required=True)
    parser.add_argument('--previous',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--epochs',type=int,default=40)
    args=parser.parse_args()
    if args.epochs<1: parser.error('Positive epochs required')
    experiment(args.dataset,args.floor_checkpoint,args.previous,args.output,args.epochs)
