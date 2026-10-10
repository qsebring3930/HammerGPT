"""Local 3D geometry completion with validation-selected checkpoint and held-out Train."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import torch
from torch import nn
from torch.nn import functional as F
from geometry_completion_dataset import SPLITS,sha

def masked_input(y,start=10,end=22,valid=None):
    known=np.ones_like(y,dtype=np.float32) if valid is None else valid.astype(np.float32).copy();known[:,:,:,start:end,start:end]=0
    return np.concatenate([y*known,known],axis=1)

def block(a,b):
    return nn.Sequential(nn.Conv3d(a,b,3,padding=1),nn.GroupNorm(4,b),nn.SiLU(),nn.Conv3d(b,b,3,padding=1),nn.GroupNorm(4,b),nn.SiLU())

class GeometryNet(nn.Module):
    def __init__(self):
        super().__init__();self.a=block(4,8);self.b=block(8,16);self.c=block(16,32);self.low=block(32,64)
        self.dc=block(96,32);self.db=block(48,16);self.da=block(24,8);self.out=nn.Conv3d(8,2,1)
    def forward(self,x):
        a=self.a(x);b=self.b(F.max_pool3d(a,2));c=self.c(F.max_pool3d(b,2));low=self.low(F.max_pool3d(c,2))
        c=self.dc(torch.cat([c,F.interpolate(low,size=c.shape[-3:],mode='trilinear',align_corners=False)],1))
        b=self.db(torch.cat([b,F.interpolate(c,size=b.shape[-3:],mode='trilinear',align_corners=False)],1))
        a=self.da(torch.cat([a,F.interpolate(b,size=a.shape[-3:],mode='trilinear',align_corners=False)],1))
        return self.out(a)

def loss(logits,y,known,weights,valid=None):
    hidden=(1-known)*(torch.ones_like(y) if valid is None else valid)
    bce=(F.binary_cross_entropy_with_logits(logits,y,pos_weight=weights,reduction='none')*hidden).sum()/hidden.sum().clamp_min(1)
    p=logits.sigmoid()*hidden;t=y*hidden;dims=(0,2,3,4)
    dice=(1-(2*(p*t).sum(dims)+1)/(p.sum(dims)+t.sum(dims)+1)).mean()
    return bce+.25*dice

def score(pred,y,valid=None):
    support=np.ones_like(y,dtype=bool) if valid is None else valid.astype(bool)
    support=support[:,:,:,10:22,10:22]
    p=(pred[:,:,:,10:22,10:22]>=.5)&support;t=(y[:,:,:,10:22,10:22]>=.5)&support;result={}
    for i,name in enumerate(['walking_surface','mesh_surface']):
        a,b=p[:,i],t[:,i];tp=int((a&b).sum());fp=int((a&~b).sum());fn=int((~a&b).sum());tn=int((~a&~b&support[:,i]).sum())
        result[name]={'iou':tp/max(tp+fp+fn,1),'f1':2*tp/max(2*tp+fp+fn,1),
                      'precision':tp/max(tp+fp,1),'recall':tp/max(tp+fn,1),
                      'balanced_accuracy':.5*(tp/max(tp+fn,1)+tn/max(tn+fp,1)),
                      'predicted_occupancy':float(a.sum()/max(support[:,i].sum(),1)),'source_occupancy':float(b.sum()/max(support[:,i].sum(),1)),
                      'scored_voxels':int(support[:,i].sum())}
    result['mean_iou']=float(np.mean([result[n]['iou'] for n in ['walking_surface','mesh_surface']]))
    return result

def interpolate_baseline(y):
    result=y.astype(np.float32).copy()
    for row in range(10,22):
        for col in range(10,22):
            h=((22-col)*y[:,:,:,row,9]+(col-9)*y[:,:,:,row,22])/13
            v=((22-row)*y[:,:,:,9,col]+(row-9)*y[:,:,:,22,col])/13
            result[:,:,:,row,col]=(h+v)/2
    return result

def retrieval_baseline(y,training,valid=None,training_valid=None):
    known=masked_input(y,valid=valid)[:,2:];result=[];neighbors=[]
    # Entire center hidden in the retrieval distance, for every channel and height.
    for i,target in enumerate(y):
        common=known[i] if training_valid is None else known[i]*training_valid
        diff=(((training.astype(np.float32)-target)*common)**2).sum(axis=(1,2,3,4))/np.maximum(np.sum(np.broadcast_to(common,training.shape),axis=(1,2,3,4)),1)
        winner=int(np.argmin(diff));result.append(training[winner]);neighbors.append(winner)
    return np.stack(result).astype(np.float32),neighbors

def infer(model,y,device,valid=None):
    result=[];model.eval()
    with torch.no_grad():
        for start in range(0,len(y),12):
            x=torch.from_numpy(masked_input(y[start:start+12],valid=None if valid is None else valid[start:start+12])).to(device)
            with torch.autocast(device_type='cuda',dtype=torch.float16):p=model(x)
            result.append(p.sigmoid().float().cpu().numpy())
    return np.concatenate(result)

def passage_scores(pred,y):
    """Undirected local voxel passage proxy; not the original directed NAV or collision."""
    totals={'source_connected_pairs':0,'retained_connected_pairs':0,'source_disconnected_pairs':0,'introduced_connections':0}
    def reachable(v,a,b):
        if not v[a] or not v[b]:return False
        seen={a};todo=[a]
        while todo:
            z,row,col=todo.pop()
            if (z,row,col)==b:return True
            for dr,dc in [(1,0),(-1,0),(0,1),(0,-1)]:
                for dz in [-1,0,1]:
                    n=(z+dz,row+dr,col+dc)
                    if 0<=n[0]<16 and 0<=n[1]<14 and 0<=n[2]<14 and n not in seen and v[n]:seen.add(n);todo.append(n)
        return False
    for i,target in enumerate(y):
        truth=target[0,:,9:23,9:23].astype(bool);assembled=target[0].copy();assembled[:,10:22,10:22]=pred[i,0,:,10:22,10:22]>=.5
        built=assembled[:,9:23,9:23].astype(bool)
        border=np.zeros_like(truth);border[:,0,:]=True;border[:,-1,:]=True;border[:,:,0]=True;border[:,:,-1]=True
        points=list(map(tuple,np.argwhere(truth&border)))
        if len(points)<2:continue
        # Fixed spatial spread using source border positions, not prediction quality.
        anchors=[points[0]]
        while len(anchors)<min(6,len(points)):
            remaining=[p for p in points if p not in anchors]
            anchors.append(max(remaining,key=lambda p:min(np.linalg.norm(np.array(p)-q) for q in anchors)))
        for j,a in enumerate(anchors):
            for b in anchors[j+1:]:
                t=reachable(truth,a,b);p=reachable(built,a,b)
                if t:totals['source_connected_pairs']+=1;totals['retained_connected_pairs']+=int(p)
                else:totals['source_disconnected_pairs']+=1;totals['introduced_connections']+=int(p)
    totals['retained_source_connections_fraction']=totals['retained_connected_pairs']/max(totals['source_connected_pairs'],1)
    totals['introduced_false_connections_fraction']=totals['introduced_connections']/max(totals['source_disconnected_pairs'],1)
    return totals

def panel(a,unknown=False):
    walking=a[0]>=.5;present=walking.any(axis=0);height=np.max(np.where(walking,np.arange(16)[:,None,None],-1),axis=0)
    rgb=np.full((32,32,3),[19,29,40],dtype=np.uint8)
    for z in range(16):rgb[present&(height==z)]=[min(65+z*11,240),min(125+z*6,235),max(205-z*9,55)]
    # One stated slice at +64 units relative to the anchor floor layer.
    rgb[a[1,6]>=.5]=[190,133,65]
    if unknown:rgb[10:22,10:22]=[55,55,68]
    im=Image.fromarray(rgb).resize((224,224),Image.Resampling.NEAREST);d=ImageDraw.Draw(im);d.rectangle((70,70,153,153),outline='white',width=1)
    return im

def comparison(path,y,pred,baseline,baseline_name,records,valid):
    # Fixed first eight test examples, not selected by score or appearance.
    count=min(8,len(y));im=Image.new('RGB',(1020,100+count*270),'#101923');d=ImageDraw.Draw(im)
    try:font=ImageFont.truetype('arial.ttf',17);small=ImageFont.truetype('arial.ttf',12)
    except OSError:font=small=ImageFont.load_default()
    d.text((20,10),'Train excluded from training: missing-volume reconstruction',font=font,fill='white')
    d.text((20,37),'Blue/green: walking height. Orange: source surface at one height slice. White square: hidden volume.',font=small,fill='#b9c8d6')
    for j,name in enumerate(['Incomplete input',baseline_name,'Trained 3D model','Original source']):d.text((20+j*250,68),name,font=font,fill='white')
    for i in range(count):
        x=masked_input(y[i:i+1],valid=valid[i:i+1])[0,:2];known=valid[i].copy();known[:,:,10:22,10:22]=0
        built=(pred[i]*(1-known)+y[i]*known)*valid[i];b=(baseline[i]*(1-known)+y[i]*known)*valid[i]
        for j,a in enumerate([x,b,built,y[i]*valid[i]]):im.paste(panel(a,j==0),(20+j*250,100+i*270))
        scores=score(pred[i:i+1],y[i:i+1],valid[i:i+1]);d.text((20,328+i*270),f"Example {i+1}, anchor {np.round(records[i]['anchor_xyz']).astype(int).tolist()} | hidden IoU: walk {scores['walking_surface']['iou']:.2f}, mesh {scores['mesh_surface']['iou']:.2f}",font=small,fill='#b9c8d6')
    im.save(path)

def run(dataset,out,epochs,wait=False):
    if out.exists():raise ValueError('Choose a new experiment directory')
    waited=0
    while wait and not (dataset/'manifest.json').exists():
        if waited%60==0:print(f'Waiting for fixed geometry dataset ({waited}s)',flush=True)
        if waited>=14400:raise TimeoutError('Dataset build did not finish')
        time.sleep(5);waited+=5
    manifest=json.loads((dataset/'manifest.json').read_text())
    if manifest['splits']!=SPLITS:raise ValueError('Unexpected map split')
    ys={};supports={}
    for split in SPLITS:
        p=dataset/(split+'.npz')
        if sha(p)!=manifest['samples'][split]['sha256']:raise ValueError('Dataset changed')
        with np.load(p) as a:ys[split]=a['y'].astype(np.float32);supports[split]=a['valid'].astype(np.float32)
    if not torch.cuda.is_available():raise RuntimeError('Authorized GPU training requires CUDA')
    device='cuda';torch.manual_seed(20261009);np.random.seed(20261009);torch.set_num_threads(4)
    out.mkdir(parents=True);model=GeometryNet().to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=.0015,weight_decay=.0001)
    scaler=torch.amp.GradScaler('cuda')
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,epochs)
    train=torch.from_numpy(ys['train']).to(device);val=torch.from_numpy(ys['validation']).to(device)
    tv=torch.from_numpy(supports['train']).to(device);vv=torch.from_numpy(supports['validation']).to(device)
    vx=torch.from_numpy(masked_input(ys['validation'],valid=supports['validation'])).to(device)
    prevalence=(train[:,:,:,10:22,10:22]*tv[:,:,:,10:22,10:22]).sum((0,2,3,4))/tv[:,:,:,10:22,10:22].sum((0,2,3,4));weights=((1-prevalence)/prevalence).clamp(1,30).view(2,1,1,1)
    history=[];best=None;best_loss=float('inf');best_epoch=0;started=time.time()
    print(json.dumps({'gpu':torch.cuda.get_device_name(),'parameters':sum(p.numel() for p in model.parameters()),'class_weights':weights.flatten().tolist(),'samples':{k:len(v) for k,v in ys.items()}}),flush=True)
    for epoch in range(1,epochs+1):
        model.train();values=[]
        for ids in torch.randperm(len(train),device=device).split(12):
            y=train[ids];valid=tv[ids];k=int(torch.randint(0,4,()).item());y=torch.rot90(y,k,(-2,-1));valid=torch.rot90(valid,k,(-2,-1))
            start=int(torch.randint(8,13,()).item());width=int(torch.randint(10,15,()).item());end=min(start+width,26)
            known=valid.clone();known[:,:,:,start:end,start:end]=0;x=torch.cat([y*known,known],1)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type='cuda',dtype=torch.float16):value=loss(model(x),y,known,weights,valid)
            scaler.scale(value).backward();scaler.unscale_(optimizer);nn.utils.clip_grad_norm_(model.parameters(),2);scaler.step(optimizer);scaler.update();values.append(value.item())
        scheduler.step();model.eval()
        with torch.no_grad(),torch.autocast(device_type='cuda',dtype=torch.float16):vl=float(np.mean([loss(model(vx[i:i+12]),val[i:i+12],vx[i:i+12,2:],weights,vv[i:i+12]).item() for i in range(0,len(val),12)]))
        row={'epoch':epoch,'training_loss':float(np.mean(values)),'validation_loss':vl};history.append(row)
        if vl<best_loss:best_loss=vl;best_epoch=epoch;best=copy.deepcopy(model.state_dict())
        if epoch==1 or epoch%5==0:print(json.dumps(row),flush=True)
    model.load_state_dict(best);checkpoint={'state_dict':best,'architecture':'GeometryNet3D-8-16-32-64','selected_epoch':best_epoch,
        'selection':'minimum Cobblestone validation loss; Train test not used for training or checkpoint selection',
        'dataset_sha256':sha(dataset/'manifest.json'),'seed':20261009,'class_weights':weights.cpu()}
    torch.save(checkpoint,out/'model.pt');(out/'history.json').write_text(json.dumps(history,indent=2))
    # Test predictions are computed only after checkpoint selection is final.
    scores={};predictions={};retrieved={};neighbors={}
    training_bank=np.concatenate([np.rot90(ys['train'],k,(-2,-1)) for k in range(4)])
    support_bank=np.concatenate([np.rot90(supports['train'],k,(-2,-1)) for k in range(4)])
    for split in ['validation','test']:
        y=ys[split];valid=supports[split];p=infer(model,y,device,valid);retrieval,ids=retrieval_baseline(y,training_bank,valid,support_bank);interp=interpolate_baseline(y);empty=y.copy();empty[:,:,:,10:22,10:22]=0
        predictions[split]=p;retrieved[split]=retrieval;neighbors[split]=ids
        scores[split]={'model':score(p,y,valid),'nearest_training_section':score(retrieval,y,valid),'boundary_interpolation':score(interp,y,valid),'empty':score(empty,y,valid)}
        np.savez_compressed(out/(split+'-predictions.npz'),model=p,nearest_training=retrieval,interpolation=interp,empty=empty)
    (out/'retrieval-neighbors.json').write_text(json.dumps({'bank':'Training examples at four XY rotations only','indices':neighbors,'training_examples_per_rotation':len(ys['train'])},indent=2))
    baseline_name=max(['nearest_training_section','boundary_interpolation','empty'],key=lambda n:scores['validation'][n]['mean_iou'])
    archive=np.load(out/'test-predictions.npz');baseline=archive[{'nearest_training_section':'nearest_training','boundary_interpolation':'interpolation','empty':'empty'}[baseline_name]]
    # Reload the serialized model and verify numerical agreement on the test tensors.
    loaded=GeometryNet().to(device);loaded.load_state_dict(torch.load(out/'model.pt',map_location=device,weights_only=False)['state_dict'])
    error=float(np.max(np.abs(infer(loaded,ys['test'],device,supports['test'])-predictions['test'])))
    routes={'model':passage_scores(predictions['test'],ys['test']),'validation_selected_baseline':passage_scores(baseline,ys['test'])}
    records=json.loads((dataset/'test-records.json').read_text());comparison(out/'comparison.png',ys['test'],predictions['test'],baseline,baseline_name,records,supports['test'])
    result={'task':'masked_3D_geometry_reconstruction','map_splits':SPLITS,'gpu':torch.cuda.get_device_name(),'epochs':epochs,
        'selected_epoch':best_epoch,'checkpoint_selection_used_test':False,'class_weights_from_training_only':weights.cpu().flatten().tolist(),
        'scores':scores,'validation_selected_baseline':baseline_name,'test_voxel_passage_proxy':routes,
        'checkpoint_reload_max_absolute_error':error,'checkpoint_sha256':sha(out/'model.pt'),
        'dataset_manifest_sha256':sha(dataset/'manifest.json'),'elapsed_seconds':time.time()-started,
        'test_predictions_fixed_examples':list(range(min(8,len(records)))),'whole_map_generation_trained':False,
        'limits':manifest['limits']+['Passage metric is an undirected voxel proxy with at most one 32-unit height step, not source NAV, collision or ladder traversal.',
            'Five reference maps and one held-out map section do not establish broad generalization. No gameplay quality certification.',
            'Source triangles include decorative/render geometry. Missing/unsupported models and sampling error can affect targets.']}
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    lines=['# Held-out Train geometry completion','','Actual local GPU training; not a whole-map generator.',
        '',f"Training: Dust2, Anubis, Cache. Validation: Cobblestone. Test: reconstructed Train section. Selected epoch {best_epoch} of {epochs} by validation loss.",
        '', '| Method | Walking IoU | Mesh IoU | Mean IoU |','|---|---:|---:|---:|']
    for name,s in scores['test'].items():lines.append(f"| {name} | {s['walking_surface']['iou']:.3f} | {s['mesh_surface']['iou']:.3f} | {s['mean_iou']:.3f} |")
    lines+=['',f"Baseline displayed: {baseline_name}, chosen on validation. First eight test examples shown without cherry-picking.",
        '', '## Limits','']+['- '+l for l in result['limits']]
    (out/'report.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'selected_epoch':best_epoch,'test_scores':scores['test'],'baseline':baseline_name,'reload_error':error}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=60);p.add_argument('--wait-for-dataset',action='store_true');a=p.parse_args();run(a.dataset,a.output,a.epochs,a.wait_for_dataset)
