"""Evaluate local four-neighbor footprint connections around a missing patch."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

from train_patch import interpolation,patch_scores


def components(grid):
    labels=np.full(grid.shape,-1,dtype=int); groups=[]
    for row,col in zip(*np.where(grid)):
        if labels[row,col]>=0: continue
        label=len(groups); members=[]; todo=[(int(row),int(col))]; labels[row,col]=label
        while todo:
            r,c=todo.pop(); members.append((r,c))
            for rr,cc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                if 0<=rr<grid.shape[0] and 0<=cc<grid.shape[1] and grid[rr,cc] and labels[rr,cc]<0:
                    labels[rr,cc]=label; todo.append((rr,cc))
        groups.append(members)
    return labels,groups


def local_view(context,completion):
    result=(context[0,11:21,11:21]>=.5).copy()
    result[1:9,1:9]=completion[0,12:20,12:20]>=.5
    return result


def analyze(context,target,prediction):
    known=local_view(context,np.zeros_like(target)); port_labels,port_groups=components(known)
    truth=local_view(context,target); predicted=local_view(context,prediction)
    true_labels,_=components(truth); pred_labels,pred_groups=components(predicted)
    pairs=[]
    for a,b in itertools.combinations(range(len(port_groups)),2):
        pa=port_groups[a][0]; pb=port_groups[b][0]
        expected=bool(true_labels[pa]==true_labels[pb]); actual=bool(pred_labels[pa]==pred_labels[pb])
        pairs.append({'ports':[a,b],'reference_connected':expected,'prediction_connected':actual})
    isolated=[g for g in pred_groups if all(1<=r<9 and 1<=c<9 for r,c in g)]
    _,truth_groups=components(truth)
    true_isolated=[g for g in truth_groups if all(1<=r<9 and 1<=c<9 for r,c in g)]
    return {'port_groups':len(port_groups),'port_pair_comparisons':len(pairs),
            'required_pairs':sum(p['reference_connected'] for p in pairs),
            'preserved_pairs':sum(p['reference_connected'] and p['prediction_connected'] for p in pairs),
            'broken_pairs':sum(p['reference_connected'] and not p['prediction_connected'] for p in pairs),
            'separate_pairs':sum(not p['reference_connected'] for p in pairs),
            'extra_connections':sum(not p['reference_connected'] and p['prediction_connected'] for p in pairs),
            'isolated_predicted_components':len(isolated),'isolated_predicted_pixels':sum(map(len,isolated)),
            'isolated_reference_components':len(true_isolated),'pairs':pairs,
            'port_cells':[[list(p) for p in group] for group in port_groups]}


def remove_islands(context,prediction):
    result=prediction.copy(); grid=local_view(context,prediction); _,groups=components(grid)
    for group in groups:
        if all(1<=r<9 and 1<=c<9 for r,c in group):
            for r,c in group: result[0,r+11,c+11]=0
    return result


def aggregate(records):
    keys=['port_pair_comparisons','required_pairs','preserved_pairs','broken_pairs','separate_pairs','extra_connections',
          'isolated_predicted_components','isolated_predicted_pixels','isolated_reference_components']
    result={key:sum(r[key] for r in records) for key in keys}
    result.update({'examples':len(records),'examples_with_required_pairs':sum(r['required_pairs']>0 for r in records),
                   'examples_with_broken_connection':sum(r['broken_pairs']>0 for r in records),
                   'examples_with_extra_connection':sum(r['extra_connections']>0 for r in records),
                   'examples_with_isolated_prediction':sum(r['isolated_predicted_components']>0 for r in records),
                   'port_pair_preservation_rate':result['preserved_pairs']/result['required_pairs'] if result['required_pairs'] else None,
                   'extra_connection_rate':result['extra_connections']/result['separate_pairs'] if result['separate_pairs'] else None})
    return result


def render(context,target,prediction,analysis,path):
    from PIL import Image,ImageDraw
    tile=200; scale=20; canvas=Image.new('RGB',(3*220+20,300),'#101827'); draw=ImageDraw.Draw(canvas)
    draw.text((20,10),'Diagnostic patch: known rim | predicted completion | recorded target',fill='white')
    grids=[local_view(context,np.zeros_like(target)),local_view(context,prediction),local_view(context,target)]
    for col,grid in enumerate(grids):
        left=20+col*220; top=45
        for r in range(10):
            for c in range(10):
                color='#638fa6' if grid[r,c] else '#202d3c'
                if col==0 and 1<=r<9 and 1<=c<9: color='#41404c'
                draw.rectangle((left+c*scale,top+r*scale,left+(c+1)*scale-1,top+(r+1)*scale-1),fill=color)
        for number,port in enumerate(analysis['port_cells']):
            r,c=port[len(port)//2]; draw.text((left+c*scale+4,top+r*scale+3),str(number),fill='#ffb454')
    draw.text((20,260),f"Broken pairs: {analysis['broken_pairs']} | Extra connections: {analysis['extra_connections']} | Isolated islands: {analysis['isolated_predicted_components']}",fill='white')
    canvas.save(path)


def evaluate(predictions_path,output):
    if output.exists(): raise ValueError('Choose a new output directory')
    with np.load(predictions_path) as data: x=data['x']; y=data['y']; local=data['local']; context=data['context']
    methods={'local':local,'context':context,'edge_interpolation':interpolation(x),
             'local_remove_islands':np.stack([remove_islands(xx,pp) for xx,pp in zip(x,local)])}
    results={}; details={}
    for name,pred in methods.items():
        records=[{'example_index':i,**analyze(xx,yy,pp)} for i,(xx,yy,pp) in enumerate(zip(x,y,pred))]
        details[name]=records; results[name]={**aggregate(records),'pixel_metrics':patch_scores(pred,y)}
    output.mkdir(parents=True)
    result={'schema_version':1,'validation_map':'Office','test_evaluated':False,
            'prediction_archive_sha256':hashlib.sha256(predictions_path.read_bytes()).hexdigest(),'methods':results,
            'definition':'Four-neighbor connectivity within the central 8x8 patch plus one-cell known rim. Ports are connected components of the known rim. Reference target defines expected port pair connectivity only for evaluation.',
            'limits':['This evaluates raster footprint topology, not recorded directed NAV traversal or gameplay.',
                      'Corner-only contact is not a route; projected layers, ladders, and heights remain unmodeled.',
                      'Preservation is relative to the recorded target; another completion could be valid under different design intent.',
                      'Island cleanup uses context and prediction only. It does not use hidden target pixels or restore missing routes.',
                      'These are correlated Office development examples, not an untouched test or deployment approval.']}
    (output/'metrics.json').write_text(json.dumps(result,indent=2)); (output/'per-example.json').write_text(json.dumps(details,indent=2))
    # Select a failure explicitly for diagnosis, not a representative success preview.
    candidates=[r for r in details['local'] if r['broken_pairs'] or r['extra_connections'] or r['isolated_predicted_components']]
    example=candidates[0] if candidates else details['local'][0]; index=example['example_index']
    render(x[index],y[index],local[index],example,output/'diagnostic.png')
    np.savez_compressed(output/'cleaned_local_predictions.npz',x=x,y=y,prediction=methods['local_remove_islands'])
    lines=['# Patch topology evaluation','','Office development set, 256 examples. Test data were not used.','','| Method | Required pairs preserved | Examples with broken routes | Examples with extra connections | Examples with isolated islands | Patch IoU |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,r in results.items(): lines.append(f"| {name} | {r['preserved_pairs']}/{r['required_pairs']} | {r['examples_with_broken_connection']} | {r['examples_with_extra_connection']} | {r['examples_with_isolated_prediction']} | {r['pixel_metrics']['hidden_pixel_iou']:.3f} |")
    lines+=['',result['definition'],'','The diagnostic preview is the first local-model failure in dataset order. It is deliberately failure-selected, not a representative sample.','','## Limits','']+['- '+limit for limit in result['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps(results)); return result


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--predictions',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); evaluate(args.predictions,args.output)


if __name__=='__main__': main()
