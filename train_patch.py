"""Validation-only comparison of local and broad-context patch completion models."""
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

from train_layout import LayoutNet


def patch_input(target):
    known=np.ones_like(target,dtype=np.float32); known[:,:,12:20,12:20]=0
    return np.concatenate((target*known,known),axis=1)


def interpolation(x):
    result=x[:,:1].copy()
    for row in range(12,20):
        for col in range(12,20):
            horizontal=((20-col)*x[:,0,row,11]+(col-11)*x[:,0,row,20])/9
            vertical=((20-row)*x[:,0,11,col]+(row-11)*x[:,0,20,col])/9
            result[:,0,row,col]=(horizontal+vertical)/2
    return result


def patch_scores(pred,target):
    p=pred[:,:,12:20,12:20]>=.5; y=target[:,:,12:20,12:20]>=.5
    intersection=(p&y).sum(); union=(p|y).sum()
    return {'hidden_pixel_iou':float(intersection/max(union,1)),
            'hidden_pixel_f1':float(2*intersection/max(p.sum()+y.sum(),1)),
            'hidden_pixel_accuracy':float((p==y).mean()),'predicted_occupancy':float(p.mean()),
            'target_occupancy':float(y.mean())}


def convolutions(a,b):
    return nn.Sequential(nn.Conv2d(a,b,3,padding=1),nn.ReLU(),nn.Conv2d(b,b,3,padding=1),nn.ReLU())


class ContextNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc1=convolutions(2,16); self.enc2=convolutions(16,32); self.enc3=convolutions(32,64)
        self.bottom=convolutions(64,128)
        self.dec3=convolutions(192,64); self.dec2=convolutions(96,32); self.dec1=convolutions(48,16)
        self.output=nn.Conv2d(16,1,1)

    def forward(self,x):
        a=self.enc1(x); b=self.enc2(F.max_pool2d(a,2)); c=self.enc3(F.max_pool2d(b,2)); low=self.bottom(F.max_pool2d(c,2))
        d=self.dec3(torch.cat((c,F.interpolate(low,size=c.shape[-2:],mode='bilinear',align_corners=False)),dim=1))
        e=self.dec2(torch.cat((b,F.interpolate(d,size=b.shape[-2:],mode='bilinear',align_corners=False)),dim=1))
        return self.output(self.dec1(torch.cat((a,F.interpolate(e,size=a.shape[-2:],mode='bilinear',align_corners=False)),dim=1)))


def load_target(dataset,split,manifest):
    path=dataset/(split+'.npz')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['archive_sha256'][split]: raise ValueError('Dataset hash mismatch')
    with np.load(path) as data: return data['y']


def fit(model,x,y,vx,vy,epochs,device):
    torch.manual_seed(20261009); model=model.to(device); optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    mask=1-x[:,1:2]; vmask=1-vx[:,1:2]; best_loss=float('inf'); best=None; best_epoch=0; history=[]
    for epoch in range(1,epochs+1):
        model.train(); total=0
        for batch in torch.randperm(len(x),device=device).split(64):
            optimizer.zero_grad(); logits=model(x[batch]); loss=(F.binary_cross_entropy_with_logits(logits,y[batch],reduction='none')*mask[batch]).sum()/mask[batch].sum()
            loss.backward(); optimizer.step(); total+=loss.item()*len(batch)
        model.eval()
        with torch.no_grad():
            validation_loss=((F.binary_cross_entropy_with_logits(model(vx),vy,reduction='none')*vmask).sum()/vmask.sum()).item()
        history.append({'epoch':epoch,'train_loss':total/len(x),'validation_loss':validation_loss})
        if validation_loss<best_loss: best_loss=validation_loss; best=copy.deepcopy(model.state_dict()); best_epoch=epoch
        if epoch==1 or epoch%10==0: print(json.dumps({'model':type(model).__name__,**history[-1]}),flush=True)
    model.load_state_dict(best); model.eval()
    with torch.no_grad(): prediction=torch.sigmoid(model(vx)).cpu().numpy()
    return model,prediction,history,best_epoch


def preview(x,y,local,context,path,labels=None):
    from PIL import Image,ImageDraw
    scale=5; tile=160; canvas=Image.new('RGB',(4*180+20,4*210+50),'#101827'); draw=ImageDraw.Draw(canvas)
    labels=labels or ('Hidden patch','Local CNN','Context CNN','Recorded target')
    draw.text((20,10),'Office development: '+ ' | '.join(labels),fill='white')
    for row in range(4):
        index=row*max(1,len(y)//4)
        values=[x[index,0],np.where(x[index,1]>0,x[index,0],local[index,0]>=.5),np.where(x[index,1]>0,x[index,0],context[index,0]>=.5),y[index,0]]
        for col,value in enumerate(values):
            left=20+180*col; top=50+210*row
            for iy in range(32):
                for ix in range(32):
                    color='#638fa6' if value[iy,ix]>=.5 else '#202d3c'
                    if col==0 and x[index,1,iy,ix]==0: color='#41404c'
                    draw.rectangle((left+ix*scale,top+iy*scale,left+(ix+1)*scale-1,top+(iy+1)*scale-1),fill=color)
            draw.rectangle((left+12*scale,top+12*scale,left+20*scale,top+20*scale),outline='#ffb454',width=2)
            draw.text((left,top+tile+7),labels[col],fill='white')
    canvas.save(path)


def experiment(dataset,output,epochs=40):
    if output.exists(): raise ValueError('Choose a new output directory')
    if not torch.cuda.is_available(): raise RuntimeError('GPU environment required')
    torch.set_num_threads(4); device=torch.device('cuda'); manifest=json.loads((dataset/'manifest.json').read_text())
    train_maps=set(manifest['splits']['train']); validation_maps=set(manifest['splits']['validation'])
    if train_maps&validation_maps: raise ValueError('Map leakage between training and validation')
    # Intentionally never read test.npz in this experiment.
    train_y=load_target(dataset,'train',manifest); valid_y=load_target(dataset,'validation',manifest)
    train_x=patch_input(train_y); valid_x=patch_input(valid_y)
    x=torch.tensor(train_x,device=device); y=torch.tensor(train_y,device=device); vx=torch.tensor(valid_x,device=device); vy=torch.tensor(valid_y,device=device)
    output.mkdir(parents=True); start=time.perf_counter(); results={}; predictions={}; history={}; checkpoints={}
    manifest_hash=hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()
    for name,constructor in [('local',LayoutNet),('context',ContextNet)]:
        torch.manual_seed(20261009); model=constructor()
        model,prediction,records,best_epoch=fit(model,x,y,vx,vy,epochs,device)
        predictions[name]=prediction; history[name]=records; results[name]=patch_scores(prediction,valid_y)
        checkpoint={'architecture':name,'state_dict':{k:v.detach().cpu() for k,v in model.state_dict().items()},'best_epoch':best_epoch,'task':'central 8x8 patch completion','dataset_manifest_sha256':manifest_hash}
        torch.save(checkpoint,output/(name+'_model.pt')); checkpoints[name]={'best_epoch':best_epoch,'parameters':sum(p.numel() for p in model.parameters())}
        restored=constructor().to(device); restored.load_state_dict(torch.load(output/(name+'_model.pt'),map_location=device,weights_only=True)['state_dict']); restored.eval()
        with torch.no_grad():
            if not torch.allclose(restored(vx[:1]),model(vx[:1]),atol=1e-6): raise RuntimeError('Checkpoint reload mismatch')
    results['edge_interpolation']=patch_scores(interpolation(valid_x),valid_y)
    results['training_pixel_frequency']=patch_scores(np.broadcast_to(train_y.mean(axis=0,keepdims=True),valid_y.shape),valid_y)
    result={'schema_version':1,'model_training_performed':True,'task':'central 8x8 patch completion from surrounding NAV footprint',
            'device':torch.cuda.get_device_name(0),'epochs_per_model':epochs,'seconds':round(time.perf_counter()-start,2),
            'training_maps':manifest['splits']['train'],'validation_maps':manifest['splits']['validation'],
            'training_examples':len(train_y),'validation_examples':len(valid_y),'test_evaluated':False,
            'dataset_manifest_sha256':manifest_hash,'validation_metrics':results,'checkpoints':checkpoints,'history':history,
            'policy':'Same fixed patch, dataset, BCE loss, optimizer and epoch budget; checkpoint selected by validation BCE; fixed threshold 0.5.',
            'limits':['This is an easier and different task than hidden-half completion; its scores cannot be compared directly to run-v1.',
                      'Office is a development validation map, not an untouched test set. Results guide research, not a generalization claim.',
                      'Vertigo test data were not read; a fresh confirmatory map is needed before deployment.',
                      'NAV completion is not architectural design, text-conditioned generation, or gameplay validation.',
                      'The footprint data retain the initial projection, height-band, and overlapping-window limitations.']}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    np.savez_compressed(output/'validation_predictions.npz',x=valid_x,y=valid_y,local=predictions['local'],context=predictions['context'])
    preview(valid_x,valid_y,predictions['local'],predictions['context'],output/'validation-preview.png')
    lines=['# Patch completion experiment','','Validation-only development comparison on Office. Vertigo was not evaluated.','','| Method | Hidden patch IoU | F1 |','| --- | ---: | ---: |']
    lines += [f"| {name} | {score['hidden_pixel_iou']:.3f} | {score['hidden_pixel_f1']:.3f} |" for name,score in results.items()]
    lines+=['','The local CNN and deeper encoder/decoder were retrained on the same smaller missing patch. This isolates architecture under the new task; it does not establish improvement on the old hidden-half task.','','## Limits','']+['- '+limit for limit in result['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps(results),flush=True); return result


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--dataset',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--epochs',type=int,default=40)
    args=parser.parse_args()
    if args.epochs<1: parser.error('Positive epoch count required')
    experiment(args.dataset,args.output,args.epochs)


if __name__=='__main__': main()
