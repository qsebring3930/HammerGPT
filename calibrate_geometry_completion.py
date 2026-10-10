"""Freeze a Cobblestone-only surface decoder before applying it to Train."""
import argparse
import json
from pathlib import Path
import numpy as np
from geometry_completion_dataset import sha
from train_geometry_completion import score,comparison,passage_scores

def thin_peaks(prob,threshold):
    result=np.zeros_like(prob,dtype=np.float32)
    # Keep one height per contiguous above-threshold run; separate floors remain separate.
    for sample in range(len(prob)):
        for row in range(prob.shape[-2]):
            for col in range(prob.shape[-1]):
                p=prob[sample,0,:,row,col];active=np.flatnonzero(p>=threshold)
                for cluster in np.split(active,np.where(np.diff(active)>1)[0]+1):
                    if len(cluster):result[sample,0,cluster[np.argmax(p[cluster])],row,col]=1
    return result

def decode(p,config):
    result=(p>=np.array(config['thresholds'])[None,:,None,None,None]).astype(np.float32)
    if config['walking_decoder']=='thin_contiguous_surface_peaks':result[:,0]=thin_peaks(p,config['thresholds'][0])[:,0]
    return result

def run(dataset,experiment,out):
    if out.exists():raise ValueError('Choose a new calibration directory')
    out.mkdir(parents=True)
    # No Train arrays, predictions or metrics are read during parameter selection.
    with np.load(dataset/'validation.npz') as a:y=a['y'];valid=a['valid']
    p=np.load(experiment/'validation-predictions.npz')['model'];trials=[];best_walk=None;best_mesh=None
    for threshold in np.arange(.5,.951,.05):
        for method in ['binary_threshold','thin_contiguous_surface_peaks']:
            cfg={'thresholds':[float(threshold),.5],'walking_decoder':method}
            s=score(decode(p,cfg),y,valid)
            row={'channel':'walking_surface','threshold':float(threshold),'decoder':method,'iou':s['walking_surface']['iou']};trials.append(row)
            if best_walk is None or row['iou']>best_walk['iou']:best_walk=row
        cfg={'thresholds':[.5,float(threshold)],'walking_decoder':'binary_threshold'}
        s=score(decode(p,cfg),y,valid);row={'channel':'mesh_surface','threshold':float(threshold),'iou':s['mesh_surface']['iou']};trials.append(row)
        if best_mesh is None or row['iou']>best_mesh['iou']:best_mesh=row
    config={'thresholds':[best_walk['threshold'],best_mesh['threshold']],
        'walking_decoder':best_walk['decoder'],'selection_map':'Cobblestone',
        'selection_metric':'per-channel hidden supported voxel IoU','selected_validation_walking_iou':best_walk['iou'],
        'selected_validation_mesh_iou':best_mesh['iou'],'checkpoint_sha256':sha(experiment/'model.pt'),
        'validation_predictions_sha256':sha(experiment/'validation-predictions.npz'),
        'test_used_for_parameter_selection':False}
    (out/'decoder.json').write_text(json.dumps(config,indent=2));(out/'validation-trials.json').write_text(json.dumps(trials,indent=2))
    print(json.dumps({'validation_selected_decoder':config}),flush=True)
    # Decoder is now frozen. Train is read only after that file has been saved.
    with np.load(dataset/'test.npz') as a:y=a['y'];valid=a['valid']
    p=np.load(experiment/'test-predictions.npz')['model'];prediction=decode(p,config)
    original=json.loads((experiment/'summary.json').read_text());name=original['validation_selected_baseline']
    archive=np.load(experiment/'test-predictions.npz');baseline=archive[{'nearest_training_section':'nearest_training','boundary_interpolation':'interpolation','empty':'empty'}[name]]
    s=score(prediction,y,valid);np.savez_compressed(out/'test-predictions.npz',model=prediction)
    records=json.loads((dataset/'test-records.json').read_text());comparison(out/'comparison.png',y,prediction,baseline,name,records,valid)
    result={'training_checkpoint':str(experiment/'model.pt'),'decoder':config,'calibrated_test_scores':s,
        'fixed_threshold_test_scores':original['scores']['test']['model'],'baseline_name':name,
        'baseline_test_scores':original['scores']['test'][name],
        'voxel_passage_proxy':{'model':passage_scores(prediction,y),'baseline':passage_scores(baseline,y)},
        'new_training_performed':False,'test_previously_observed_in_v2':True,
        'assessment':'Development comparison after observing v2. Train remains excluded from gradients and parameter selection; this is not a fresh blind test.',
        'limits':original['limits']}
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    lines=['# Validation-calibrated geometry completion','',
        'Same trained checkpoint; decoder selected on Cobblestone only and saved before loading Train predictions.',
        'Train was already observed in v2; this follow-up is development evidence, not a fresh blind test.',
        '', '| Method | Walking IoU | Mesh IoU | Mean IoU |','|---|---:|---:|---:|']
    for label,t in [('Fixed 0.5 model',result['fixed_threshold_test_scores']),('Validation-calibrated model',s),(name,result['baseline_test_scores'])]:
        lines.append(f"| {label} | {t['walking_surface']['iou']:.3f} | {t['mesh_surface']['iou']:.3f} | {t['mean_iou']:.3f} |")
    lines+=['','## Limits','']+['- '+x for x in result['limits']];(out/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'test_scores':s,'passages':result['voxel_passage_proxy']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--experiment',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.dataset,a.experiment,a.output)
