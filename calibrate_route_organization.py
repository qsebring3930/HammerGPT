"""Validation-only decoder follow-up after the fixed 0.5 development test."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from PIL import Image,ImageDraw,ImageFont
from train_route_organization import TRAIN,VALIDATION,TEST,N,encode,mask_example,batch,GraphPlanner,FlatPlanner,metrics,sha


def choose_threshold(probabilities,examples):
    trials=[]
    for threshold in np.linspace(.05,.995,190):
        score=metrics((probabilities>=threshold).astype(np.float32),examples)
        trials.append({'threshold':float(threshold),**score})
    return max(trials,key=lambda r:(r['hidden_directed_edge_IoU'],r['precision'])),trials


def draw(record,examples,geometry,graph,output):
    im=Image.new('RGB',(1800,1650),'#101a26');p=ImageDraw.Draw(im)
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n)
    p.text((20,15),'Train: validation-calibrated connection reconstruction',font=font(29),fill='#eef3fa')
    p.text((20,58),'Fixed first four cases. Area positions are supplied; this is not a generated map.',font=font(18),fill='#bbcbd9')
    count=int(record['valid'].sum());pos=record['x'][:count,:2];lo=pos.min(0);hi=pos.max(0)
    scale=min(340/max(hi[0]-lo[0],.1),265/max(hi[1]-lo[1],.1))
    for row,e in enumerate(examples[:4]):
        for col,title in enumerate(['Observed links','Geometry-only baseline','Trained graph planner','Original source']):
            ox,oy=20+col*450,105+row*370
            p.text((ox,oy),title,font=font(20),fill='#edf3fa')
            def xy(i):return ox+30+(pos[i,0]-lo[0])*scale,oy+45+(hi[1]-pos[i,1])*scale
            truth=e['target']>0
            pred=e['observed']>0 if col==0 else geometry[row]>.5 if col==1 else graph[row]>.5 if col==2 else truth
            assembled=np.where(e['known']>0,e['observed']>0,pred) if col else pred
            for a in range(count):
                for b in range(count):
                    if a==b:continue
                    exists=assembled[a,b];miss=truth[a,b] and not exists and e['hidden'][a,b]
                    if not exists and (not miss or col==0):continue
                    color='#536a79' if e['known'][a,b] else '#77d6a1' if exists and truth[a,b] else '#ec777f' if exists else '#d8b550'
                    p.line([xy(a),xy(b)],fill=color,width=2)
            for i in range(count):
                x,y=xy(i);p.ellipse((x-3,y-3,x+3,y+3),fill='#f4d368' if e['holes'][i] else '#bfd0de')
            for role,ids in record['roles'].items():
                if ids:
                    x,y=xy(ids[0]);p.text((x+4,y),role,font=font(14),fill='#ffffff')
            if col in (1,2):
                score=metrics((geometry if col==1 else graph)[row:row+1],[e])
                p.text((ox,oy+320),f"Hidden edge IoU {score['hidden_directed_edge_IoU']:.2f}",font=font(17),fill='#b9cadb')
    p.text((20,1610),'Green: recovered hidden link | Red: extra link | Yellow: missed link | Grey: supplied connection',font=font(18),fill='#bbcbd9')
    im.save(output)


def run(root,source,output):
    output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(4)
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    original_summary=json.loads((source/'summary.json').read_text())
    expected_training=original_summary['training_maps']
    if set(expected_training)&{VALIDATION,TEST}:raise ValueError('Whole-map split overlap')
    val_record=encode(root,VALIDATION);validation=[mask_example(val_record,220000+i) for i in range(32)]
    val=batch(validation,device);config={};models={};hashes={}
    for name,cls in [('flat_MLP',FlatPlanner),('graph_planner',GraphPlanner)]:
        path=source/f'{name}.pt';checkpoint=torch.load(path,map_location=device,weights_only=False)
        if checkpoint['training_maps']!=expected_training:raise ValueError('Unexpected fitting maps')
        model=cls().to(device);model.load_state_dict(checkpoint['state_dict']);model.eval()
        with torch.no_grad():prob=model(val['x'],val['observed'],val['known'],val['valid']).sigmoid().cpu().numpy()
        selected,trials=choose_threshold(prob,validation);config[name]=selected;models[name]=model;hashes[name]=sha(path)
        (output/f'{name}-validation-trials.json').write_text(json.dumps(trials,indent=2),encoding='utf-8')
    (output/'decoder.json').write_text(json.dumps({'validation_map':VALIDATION,'test_previously_observed':True,'fresh_blind_test':False,'model_weights_changed':False,'decoders':config,'checkpoint_hashes':hashes},indent=2),encoding='utf-8')
    # Decoder configuration is persisted before opening Train predictions or targets.
    test_record=encode(root,TEST);examples=[mask_example(test_record,330000+i) for i in range(32)]
    test=batch(examples,device);predictions={}
    for name,model in models.items():
        with torch.no_grad():prob=model(test['x'],test['observed'],test['known'],test['valid']).sigmoid().cpu().numpy()
        predictions[name]=(prob>=config[name]['threshold']).astype(np.float32)
    original=np.load(source/'test-predictions.npz')
    for name in ('nearest_training_map','geometric_neighbors','empty_hidden'):predictions[name]=original[name]
    scores={name:metrics(p,examples) for name,p in predictions.items()}
    passed=all(scores['graph_planner']['hidden_directed_edge_IoU']>scores[n]['hidden_directed_edge_IoU'] for n in ('flat_MLP','nearest_training_map','geometric_neighbors'))
    summary={'scores':scores,'training_maps':expected_training,'validation_selected_decoders':config,'beats_all_three_nonempty_baselines':passed,'test_previously_observed':True,
             'fresh_blind_test':False,'new_training_performed':False,'new_map_generated':False,'checkpoint_hashes':hashes}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    np.savez_compressed(output/'test-predictions.npz',**predictions)
    draw(test_record,examples,predictions['geometric_neighbors'],predictions['graph_planner'],output/'comparison.png')
    lines=['# Topology decoder development follow-up','','The fixed 0.5 graph planner failed the geometry-only baseline. These results retain the same trained weights and choose thresholds only on Cobblestone validation. Train was already observed in the first experiment, so this is a development follow-up, not a fresh blind test.', '',
           '| Method | Hidden edge IoU | Precision | Recall |','|---|---:|---:|---:|']
    for name,s in scores.items():lines.append(f"| {name} | {s['hidden_directed_edge_IoU']:.3f} | {s['precision']:.3f} | {s['recall']:.3f} |")
    lines += ['',f'Graph planner beats all three nonempty baselines: **{passed}**.', '',
              'Area positions and positive reviewed context are supplied. This is conditional directed-interface reconstruction, not empty-canvas map generation or tactical quality. Thresholds were saved before loading Train predictions. No graph repairs or new Hammer maps were produced. Unknown route purposes stay unsupervised; the corrected Ivy-to-CT-to-B flank is not an opening attack label.', '',
              '![First four fixed Train cases](comparison.png)']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(Path(__file__).resolve().parent,args.source,args.output)
