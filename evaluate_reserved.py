"""Freeze and run the first five-map confirmation of local connection planning."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch
import ortools

from training_dataset import raster,CELL,SIZE
from train_patch import patch_input,patch_scores,preview,interpolation
from train_conditioned import reference_plan,ConditionedNet,topology
from train_connection_planner import pair_inputs,probabilities,complete,plan_scores
from improve_connection_planner import RegularizedPlanner
from solver_planner import solve_plan


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(registry,development,planner_run,floor_checkpoint,output):
    if output.exists(): raise ValueError('Choose a new evaluation directory')
    reserved=json.loads(registry.read_text())['maps']; dev=json.loads((development/'manifest.json').read_text())
    if len(reserved)!=5 or any(not r['user_approved'] or r['model_evaluated'] or r['training_allowed'] or r['dataset_role']!='evaluation_only' for r in reserved):
        raise ValueError('Expected five approved, unevaluated, evaluation-only maps')
    if {r['name'] for r in reserved} & {n for group in dev['splits'].values() for n in group}: raise ValueError('Development map overlap')
    selection=json.loads((planner_run/'metrics.json').read_text()); arm=selection['selected_arm']; planner=planner_run/(arm+'.pt')
    if selection['dataset_manifest_sha256']!=digest(development/'manifest.json') or selection['floor_checkpoint_sha256']!=digest(floor_checkpoint):
        raise ValueError('Development model provenance mismatch')
    sources=['evaluate_reserved.py','solver_planner.py','training_dataset.py','train_patch.py','train_conditioned.py','train_connection_planner.py','improve_connection_planner.py','evaluate_topology.py']
    protocol={'schema_version':1,'status':'frozen_before_predictions','planner_arm':arm,'planner_checkpoint':str(planner.resolve()),'planner_sha256':digest(planner),
              'floor_checkpoint':str(floor_checkpoint.resolve()),'floor_sha256':digest(floor_checkpoint),'development_manifest':str((development/'manifest.json').resolve()),
              'development_manifest_sha256':digest(development/'manifest.json'),'registry':str(registry.resolve()),'registry_sha256':digest(registry),
              'maps':[{**r,'nav_export_path':str((registry.parent/r['nav_export']).resolve()),'nav_export_sha256':digest(registry.parent/r['nav_export'])} for r in reserved],
              'samples_per_map':256,'seed':20261009,'size':SIZE,'cell_units':CELL,'height_band_units':48,'patch':[12,20],
              'attempt_multiplier':30,'sampling_filter':'same pilot filters: left/right footprint >=16 occupied cells; total occupancy <=0.85',
              'deduplication':'exact full-window fingerprints excluded against every development manifest split and earlier cohort windows',
              'solver_time_limit_seconds':2.,'solver_workers':1,'solver_seed':0,'solver_log_odds_scale':1000000,'floor_threshold':.5,
              'ortools_version':ortools.__version__,'torch_version':str(torch.__version__),'source_sha256':{s:digest(s) for s in sources},
              'cuda_deterministic':True,'cublas_workspace_config':':4096:8',
              'methods':['learned_pipeline','edge_interpolation','interpolated_plan','all_connected','all_separate','reference_plan_diagnostic'],
              'summary':'equal-weight map means; retain per-map rates and denominators','no_training_or_tuning':True}
    output.mkdir(parents=True); (output/'protocol.json').write_text(json.dumps(protocol,indent=2))
    return protocol


def sample_nav(nav,samples,seed,used,attempt_multiplier=30):
    areas=[a for a in nav['areas'] if a['hull']==0 and a['movable_mesh_id']==0xffffffff]
    if not areas: raise ValueError('No static hull-0 areas')
    points=[np.asarray(a['corners'],dtype=float) for a in areas]
    if any(p.ndim!=2 or p.shape[1]!=3 or len(p)<3 or not np.isfinite(p).all() for p in points): raise ValueError('Malformed NAV polygon')
    centers=np.asarray([p.mean(axis=0) for p in points]); minima=np.asarray([p.min(axis=0) for p in points]); maxima=np.asarray([p.max(axis=0) for p in points])
    rng=np.random.default_rng(seed); targets=[]; records=[]; attempts=0
    while len(targets)<samples and attempts<samples*attempt_multiplier:
        attempts+=1; index=int(rng.integers(len(areas))); center=centers[index].copy()
        center[:2]+=rng.integers(-4,5,size=2)*CELL; rotation=int(rng.integers(4))
        # Bounding-box prefilter only accelerates the existing raster operation.
        nearby=(np.abs(centers[:,2]-center[2])<=48)&(maxima[:,0]>=center[0]-SIZE*CELL/2)&(minima[:,0]<=center[0]+SIZE*CELL/2)&(maxima[:,1]>=center[1]-SIZE*CELL/2)&(minima[:,1]<=center[1]+SIZE*CELL/2)
        target=np.rot90(raster([points[i] for i in np.flatnonzero(nearby)],*center),rotation).copy()
        if target[:,:16].sum()<16 or target[:,16:].sum()<16 or target.mean()>.85: continue
        fingerprint=hashlib.sha256(target.astype(np.uint8).tobytes()).hexdigest()
        if fingerprint in used: continue
        used.add(fingerprint); targets.append(target[None])
        records.append({'nav_seed_area':areas[index]['id'],'world_center':center.tolist(),'rotation_quarter_turns':rotation,'footprint_sha256':fingerprint})
    if len(targets)<samples: raise ValueError(f'Only {len(targets)} unique eligible windows after {attempts} attempts; frozen settings were not relaxed')
    return np.asarray(targets,dtype=np.float32),records,attempts


def infer_plans(planner,contexts,device,time_limit):
    features,indices,counts=pair_inputs(contexts); scores=probabilities(planner,features,device)
    matrices=[np.eye(n) for n in counts]
    for (i,a,b),p in zip(indices,scores): matrices[i][a,b]=matrices[i][b,a]=p
    solved=[solve_plan(p,time_limit) for p in matrices]
    return [p for p,info in solved],[info for p,info in solved]


def summarize(maps,methods):
    result={}
    for method in methods:
        rows=[m['methods'][method] for m in maps.values()]
        result[method]={'maps':len(rows),'macro_patch_iou':float(np.mean([r['pixels']['hidden_pixel_iou'] for r in rows])),
                        'macro_required_pair_preservation':float(np.mean([r['topology']['port_pair_preservation_rate'] for r in rows if r['topology']['port_pair_preservation_rate'] is not None])),
                        'macro_extra_pair_rate':float(np.mean([r['topology']['extra_connection_rate'] for r in rows if r['topology']['extra_connection_rate'] is not None])),
                        'broken_route_examples':sum(r['topology']['examples_with_broken_connection'] for r in rows),
                        'extra_connection_examples':sum(r['topology']['examples_with_extra_connection'] for r in rows),
                        'isolated_floor_examples':sum(r['topology']['examples_with_isolated_prediction'] for r in rows)}
    return result


def run(output):
    protocol=json.loads((output/'protocol.json').read_text()); result_path=output/'metrics.json'
    if result_path.exists(): raise ValueError('Evaluation has already completed')
    for path,expected in protocol['source_sha256'].items():
        if digest(path)!=expected: raise ValueError('Frozen evaluator source changed: '+path)
    for path,expected in [(protocol['planner_checkpoint'],protocol['planner_sha256']),(protocol['floor_checkpoint'],protocol['floor_sha256']),
                          (protocol['registry'],protocol['registry_sha256']),(protocol['development_manifest'],protocol['development_manifest_sha256'])]:
        if digest(path)!=expected: raise ValueError('Frozen input changed: '+path)
    if ortools.__version__!=protocol['ortools_version'] or str(torch.__version__)!=protocol['torch_version']: raise ValueError('Runtime changed')
    if not torch.cuda.is_available(): raise RuntimeError('CUDA required')
    os.environ['CUBLAS_WORKSPACE_CONFIG']=protocol['cublas_workspace_config']
    torch.set_num_threads(4); torch.use_deterministic_algorithms(True); device=torch.device('cuda')
    state=torch.load(protocol['planner_checkpoint'],map_location=device,weights_only=True)
    planner=RegularizedPlanner(state['configuration']['dropout']).to(device); planner.load_state_dict(state['state_dict']); planner.eval()
    floor=ConditionedNet().to(device); floor.load_state_dict(torch.load(protocol['floor_checkpoint'],map_location=device,weights_only=True)['state_dict']); floor.eval()
    dev=json.loads(Path(protocol['development_manifest']).read_text()); used={r['footprint_sha256'] for r in dev['examples']}; maps={}
    for index,row in enumerate(protocol['maps']):
        name=row['name']; print('Evaluating '+name+'...',flush=True)
        for path,expected in [(row['source'],row['map_sha256']),(row['nav_source'],row['nav_sha256']),(row['nav_export_path'],row['nav_export_sha256'])]:
            if digest(path)!=expected: raise ValueError('Reserved source changed: '+name)
        y,records,attempts=sample_nav(json.loads(Path(row['nav_export_path']).read_text()),protocol['samples_per_map'],protocol['seed']+index,used,protocol['attempt_multiplier'])
        x=patch_input(y); plans,solver_info=infer_plans(planner,x,device,protocol['solver_time_limit_seconds'])
        # Learned predictions are completed before any reference plans are derived.
        predictions={'learned_pipeline':complete(floor,x,plans,device),'edge_interpolation':interpolation(x)}
        guessed=[reference_plan(a,b) for a,b in zip(x,predictions['edge_interpolation'])]
        truth=[reference_plan(a,b) for a,b in zip(x,y)]
        selected={'interpolated_plan':guessed,'all_connected':[[0]*len(p) for p in plans],
                  'all_separate':[list(range(len(p))) for p in plans],'reference_plan_diagnostic':truth}
        for method,groups in selected.items(): predictions[method]=complete(floor,x,groups,device)
        methods={method:{'pixels':patch_scores(p,y),'topology':topology(x,y,p)} for method,p in predictions.items()}
        for method,groups in {'learned_pipeline':plans,**selected}.items(): methods[method]['plan']=plan_scores(groups,truth)
        maps[name]={'examples':len(y),'sampling_attempts':attempts,'recorded_ladders_excluded':row['ladder_count'],
                    'solver_optimal_examples':sum(i['optimal'] for i in solver_info),'solver_fallback_examples':sum(i['fallback'] is not None for i in solver_info),'methods':methods}
        np.savez_compressed(output/(name.lower()+'-predictions.npz'),x=x,y=y,**predictions)
        (output/(name.lower()+'-samples.json')).write_text(json.dumps({'examples':records,'predicted_plans':plans,'reference_plans_for_scoring':truth,'solver_diagnostics':solver_info},indent=2))
        preview(x,y,predictions['edge_interpolation'],predictions['learned_pipeline'],output/(name.lower()+'-preview.png'),('Hidden patch','Interpolation','Learned pipeline','Recorded target'))
        (output/'progress.json').write_text(json.dumps(maps,indent=2))
        print(json.dumps({'map':name,'learned':methods['learned_pipeline'],'interpolation':methods['edge_interpolation']}),flush=True)
    result={'schema_version':1,'model_training_performed':False,'first_reserved_cohort_evaluation':True,'maps':maps,'summary':summarize(maps,protocol['methods']),
            'protocol_sha256':digest(output/'protocol.json'),'device':torch.cuda.get_device_name(0),'automatic_hammer_generation_enabled':False,
            'limits':['Five user-selected maps are the independent units; sampled windows overlap and are correlated.',
                      'Sampling retains pilot eligibility filters and exact deduplication; it does not represent every location or tactical situation.',
                      'NAV freshness against repaired maps is unverified. Height-band projection can alias layers; ladders and directed traversal are excluded.',
                      'Reference-plan diagnosis uses privileged target connectivity and is not an autonomous baseline.',
                      'This cohort is now observed. Tuning from these results requires fresh maps for another untouched confirmation.',
                      'Pixel agreement and local connectivity do not establish architecture, tactical quality, or playable whole maps.']}
    result_path.write_text(json.dumps(result,indent=2))
    lines=['# First reserved-map evaluation','','Frozen local planner and OR-Tools solver; no training or tuning.','',
           '| Map | Learned IoU | Interpolation IoU | Required pairs preserved | Broken-route examples | Extra-connection examples | Isolated-floor examples |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name,m in maps.items():
        r=m['methods']['learned_pipeline']; t=r['topology']; lines.append(f"| {name} | {r['pixels']['hidden_pixel_iou']:.3f} | {m['methods']['edge_interpolation']['pixels']['hidden_pixel_iou']:.3f} | {t['preserved_pairs']}/{t['required_pairs']} | {t['examples_with_broken_connection']} | {t['examples_with_extra_connection']} | {t['examples_with_isolated_prediction']} |")
    lines+=['','## Equal-weight map averages','','| Method | Patch IoU | Required-pair preservation | Extra-pair rate |','| --- | ---: | ---: | ---: |']
    for method,m in result['summary'].items(): lines.append(f"| {method} | {m['macro_patch_iou']:.3f} | {m['macro_required_pair_preservation']:.3f} | {m['macro_extra_pair_rate']:.3f} |")
    lines+=['','Previews use four fixed indices per map; successes were not selected. Frozen settings and input hashes are in protocol.json.','','## Limits','']+['- '+v for v in result['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps(result['summary']),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('mode',choices=['freeze','run']); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--registry',type=Path); parser.add_argument('--development',type=Path); parser.add_argument('--planner-run',type=Path); parser.add_argument('--floor-checkpoint',type=Path)
    args=parser.parse_args()
    if args.mode=='freeze':
        if not all((args.registry,args.development,args.planner_run,args.floor_checkpoint)): parser.error('Freeze requires all source paths')
        freeze(args.registry,args.development,args.planner_run,args.floor_checkpoint,args.output); print('Protocol frozen; no predictions run.')
    else: run(args.output)
