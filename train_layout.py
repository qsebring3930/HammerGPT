"""Train and evaluate a small local NAV footprint completion model."""
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


class LayoutNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.encode=nn.Sequential(nn.Conv2d(2,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,16,3,padding=1),nn.ReLU())
        self.middle=nn.Sequential(nn.Conv2d(16,32,3,stride=2,padding=1),nn.ReLU(),nn.Conv2d(32,32,3,padding=1),nn.ReLU(),nn.Conv2d(32,32,3,padding=1),nn.ReLU())
        self.decode=nn.Sequential(nn.Conv2d(48,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,1,1))

    def forward(self,x):
        skip=self.encode(x); low=self.middle(skip)
        return self.decode(torch.cat((skip,F.interpolate(low,size=skip.shape[-2:],mode='bilinear',align_corners=False)),dim=1))


def scores(prediction,target):
    p=prediction[...,16:]>=.5; y=target[...,16:]>=.5
    intersection=(p&y).sum(); union=(p|y).sum(); positives=p.sum()+y.sum()
    return {'hidden_pixel_iou':float(intersection/max(union,1)),
            'hidden_pixel_f1':float(2*intersection/max(positives,1)),
            'hidden_pixel_accuracy':float((p==y).mean()),'predicted_occupancy':float(p.mean())}


def extrapolate(x):
    result=x[:,0:1].copy()
    # Baseline continues the last visible 4 columns as straight strips.
    rows=(x[:,0:1,:,12:16].mean(axis=-1,keepdims=True)>=.5).astype(np.float32)
    result[:,:,:,16:]=rows
    return result


def load_split(path,device):
    with np.load(path) as data:
        x=data['x']; y=data['y']
    return x,y,torch.tensor(x,device=device),torch.tensor(y,device=device)


def train(dataset,output,epochs=30,require_cuda=False):
    if output.exists(): raise ValueError('Choose a new run directory')
    if require_cuda and not torch.cuda.is_available(): raise RuntimeError('CUDA runtime required but unavailable')
    torch.manual_seed(20261008); np.random.seed(20261008); torch.set_num_threads(4)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu'); output.mkdir(parents=True)
    manifest=json.loads((dataset/'manifest.json').read_text())
    for split,expected in manifest['archive_sha256'].items():
        if hashlib.sha256((dataset/(split+'.npz')).read_bytes()).hexdigest()!=expected: raise ValueError('Dataset archive hash mismatch')
    train_x,train_y,x,y=load_split(dataset/'train.npz',device)
    valid_x,valid_y,vx,vy=load_split(dataset/'validation.npz',device)
    model=LayoutNet().to(device); optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    history=[]; best_loss=float('inf'); best=None; best_epoch=0; start=time.perf_counter()
    mask=1-x[:,1:2]; validation_mask=1-vx[:,1:2]
    for epoch in range(1,epochs+1):
        model.train(); order=torch.randperm(len(x),device=device); total=0
        for indices in order.split(64):
            optimizer.zero_grad(); logits=model(x[indices]); loss=(F.binary_cross_entropy_with_logits(logits,y[indices],reduction='none')*mask[indices]).sum()/mask[indices].sum()
            loss.backward(); optimizer.step(); total+=loss.item()*len(indices)
        model.eval()
        with torch.no_grad():
            validation_loss=((F.binary_cross_entropy_with_logits(model(vx),vy,reduction='none')*validation_mask).sum()/validation_mask.sum()).item()
        history.append({'epoch':epoch,'train_loss':total/len(x),'validation_loss':validation_loss})
        if validation_loss<best_loss:
            best_loss=validation_loss; best_epoch=epoch; best=copy.deepcopy(model.state_dict())
        if epoch==1 or epoch%5==0: print(json.dumps(history[-1]),flush=True)
    model.load_state_dict(best); model.eval()
    torch.save({'state_dict':{k:v.cpu() for k,v in best.items()},'architecture':'LayoutNet-v1','best_epoch':best_epoch,
                'dataset_manifest_sha256':hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()},output/'layout_model.pt')
    # Test data are loaded only after training and validation-based model selection.
    test_x,test_y,tx,ty=load_split(dataset/'test.npz',device)
    with torch.no_grad():
        validation_prediction=torch.sigmoid(model(vx)).cpu().numpy(); test_prediction=torch.sigmoid(model(tx)).cpu().numpy()
    train_frequency=train_y.mean(axis=0,keepdims=True)
    metrics={}
    for name,xx,yy,pred in [('validation',valid_x,valid_y,validation_prediction),('test',test_x,test_y,test_prediction)]:
        metrics[name]={'model':scores(pred,yy),'straight_strip_rule':scores(extrapolate(xx),yy),
                       'training_pixel_frequency':scores(np.broadcast_to(train_frequency,yy.shape),yy)}
    # Verify checkpoint restoration yields the same prediction.
    restored=LayoutNet().to(device); checkpoint=torch.load(output/'layout_model.pt',map_location=device,weights_only=True); restored.load_state_dict(checkpoint['state_dict']); restored.eval()
    with torch.no_grad():
        assert torch.allclose(restored(tx[:1]),model(tx[:1]),atol=1e-6)
    result={'schema_version':1,'model_training_performed':True,'task':manifest['task'],'device':str(device),
            'gpu':torch.cuda.get_device_name(0) if device.type=='cuda' else None,'torch_version':str(torch.__version__),
            'parameters':sum(p.numel() for p in model.parameters()),'epochs':epochs,'best_epoch':best_epoch,
            'seconds':round(time.perf_counter()-start,2),'counts':manifest['counts'],'map_splits':manifest['splits'],
            'dataset_manifest_sha256':checkpoint['dataset_manifest_sha256'],'history':history,'metrics':metrics,
            'evaluation_policy':'Fixed threshold 0.5; checkpoint selected by validation loss; test evaluated once after selection.',
            'limits':manifest['limits']+['Small supervised completion CNN trained from scratch; not an LLM or text-to-map generator.',
                                      'Pixel overlap does not establish connectivity, architectural plausibility, or gameplay quality.']}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    np.savez_compressed(output/'test_predictions.npz',x=test_x,y=test_y,prediction=test_prediction)
    render(test_x,test_y,test_prediction,output/'test-preview.png')
    lines=['# First local training experiment','','A small supervised model was trained to complete hidden halves of NAV footprints. This is actual parameter training, not reference retrieval.','','| Evaluation | Model IoU | Straight-strip rule IoU | Training-frequency IoU |','| --- | ---: | ---: | ---: |']
    for name,values in metrics.items(): lines.append(f"| {name} | {values['model']['hidden_pixel_iou']:.3f} | {values['straight_strip_rule']['hidden_pixel_iou']:.3f} | {values['training_pixel_frequency']['hidden_pixel_iou']:.3f} |")
    lines+=['',f'Best checkpoint: epoch {best_epoch}. Device: {device}. Training examples: {len(x)}. Test map: Vertigo; validation map: Office.','', '## Limits','']+[ '- '+limit for limit in result['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps({'run':str(output),'device':str(device),'metrics':metrics}),flush=True)
    return result


def render(x,y,pred,path):
    from PIL import Image,ImageDraw
    scale=6; tile=32*scale; canvas=Image.new('RGB',(3*(tile+20)+20,4*(tile+50)+50),'#101827'); draw=ImageDraw.Draw(canvas)
    draw.text((20,10),'Vertigo held out: context | predicted hidden half | recorded footprint',fill='white')
    for row in range(4):
        index=row*max(1,len(x)//4)
        for col,values in enumerate((x[index,0],np.where(x[index,1]>0,x[index,0],pred[index,0]>=.5),y[index,0])):
            left=20+col*(tile+20); top=50+row*(tile+50)
            for iy in range(32):
                for ix in range(32):
                    color='#638fa6' if values[iy,ix]>=.5 else '#202d3c'
                    if col==0 and ix>=16: color='#41404c'
                    draw.rectangle((left+ix*scale,top+iy*scale,left+(ix+1)*scale-1,top+(iy+1)*scale-1),fill=color)
            draw.line((left+16*scale,top,left+16*scale,top+tile),fill='#ffb454',width=2)
            draw.text((left,top+tile+7),('Visible / hidden','Model completion','Recorded target')[col],fill='white')
    canvas.save(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--dataset',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--epochs',type=int,default=30); parser.add_argument('--require-cuda',action='store_true')
    args=parser.parse_args()
    if args.epochs<1: parser.error('Positive epoch count required')
    train(args.dataset,args.output,args.epochs,args.require_cuda)


if __name__=='__main__': main()
