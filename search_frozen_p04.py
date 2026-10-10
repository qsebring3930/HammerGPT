"""Bounded experiment harness; does not change architecture or acceptance rules."""
import argparse
import hashlib
import json
import shutil
import time
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union
from procedural_p04 import ROOT, generate, rotate
from procedural_p04_checks import validate
from playable_composition import compile_composition
from p04_comparison_round import render
from semantic_pipeline import digest, GameplayValidator

def write(path, obj):
    path.write_text(json.dumps(obj, indent=2), encoding='utf-8')

def spatial_identity(p):
    """Conservative categorical comparison, invariant to global rotation/reflection.

    Ignore local motif, dimension, gap, cover and depth-offset variation. Require
    different relative ingress or major deployment/circulation organization.
    Borderline distinctions are collapsed, rather than used to fill the quota.
    """
    m=p['decision_log'][0]['choices']; k=m['rotations']['A']
    centers={s:np.array(rotate(m['complex_centers'][s],-k)) for s in ('A','B')}
    sign=1 if centers['B'][0]>centers['A'][0] else -1
    def canonical(q):
        x,y=rotate(q,-k);return np.array([x*sign,y])
    a=canonical(m['complex_centers']['A']); b=canonical(m['complex_centers']['B'])
    lo,hi=sorted([a[0],b[0]])
    deployment={}
    for team,point in m['deployment'].items():
        q=canonical(point)
        # A generous central band avoids differences caused only by small offsets.
        lateral='outside_A' if q[0]<lo-8 else 'outside_B' if q[0]>hi+8 else 'between_sites'
        depth='attacker_side' if q[1]<min(a[1],b[1])-12 else 'rear_side' if q[1]>max(a[1],b[1])+12 else 'alongside_sites'
        deployment[team]=[lateral,depth]
    roads={}
    for d in p['decision_log']:
        if d['stage']!='circulation' or d['status']!='placed':continue
        # Only substantial travel in the inter-complex central band counts.
        length=0
        pts=[canonical(q) for q in d['points']]
        for u,v in zip(pts,pts[1:]):
            mid=(u+v)/2
            if lo+8<mid[0]<hi-8 and min(a[1],b[1])-12<mid[1]<max(a[1],b[1])+12:
                length+=float(np.linalg.norm(v-u))
        roads[d['team']+'-'+d['site']]='inter_complex' if length>=16 else 'outer_frontage'
    return dict(relative_B_ingress=m['B_facing_relationship'],deployment=deployment,circulation=roads)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'output/p04-frozen-search-001');ap.add_argument('--seed-start',type=int,default=10001);ap.add_argument('--limit',type=int,default=40)
    args=ap.parse_args()
    if not 1<=args.limit<=40:raise ValueError('Search limit must be 1..40')
    if args.output.exists():raise ValueError('Output exists; previous experiments must be preserved')
    seeds=list(range(args.seed_start,args.seed_start+args.limit))
    used=set()
    for f in (ROOT/'output').rglob('composition.json'):
        try:
            value=json.loads(f.read_text()).get('seed')
            if value is not None:used.add(value)
        except (ValueError,OSError):pass
    if set(seeds)&used:raise ValueError('Previously tested seed in requested sequence')
    args.output.mkdir(parents=True);frozen=args.output/'frozen';frozen.mkdir()
    # Snapshot all root Python dependencies, not just the two entry modules.
    inputs=list(ROOT.glob('*.py'))+[ROOT/'config/p04-procedural-v3.json',ROOT/'output/strategic-diversity-001/P04/plan.json']
    hashes={str(f.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}
    for f in inputs:
        target=frozen/f.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
    cfg=json.loads((ROOT/'config/p04-procedural-v3.json').read_text());plan=json.loads((ROOT/cfg['strategy']).read_text())
    write(args.output/'manifest.json',dict(source_hashes=hashes,configuration_sha256=digest(cfg),strategy_sha256=digest(plan),planned_seeds=seeds,max_attempts=args.limit,selection='Four physical/structural passes with different conservative spatial signatures. Physical passes that repeat a signature remain in history.',diversity_policy=spatial_identity.__doc__,stage4_paused=True))
    write(args.output/'configuration.json',cfg);write(args.output/'seeds.json',{'seeds':seeds});write(args.output/'strategy-validation.json',GameplayValidator().validate(plan))
    attempts=[];selected=[];identities=[];bounds=(0,0,*cfg['world']);px=min(1600/cfg['world'][0],1250/cfg['world'][1]);start=time.time()
    for seed in seeds:
        folder=args.output/f'seed-{seed}';folder.mkdir();p=generate(plan,seed,cfg);write(folder/'composition.json',p);write(folder/'decisions.json',p['decision_log'])
        # Repeat construction on every attempt, including rejected ones.
        again=generate(plan,seed,cfg);repro=dict(reproduced=digest(p)==digest(again),first_sha256=digest(p),second_sha256=digest(again));write(folder/'reproducibility.json',repro)
        try:
            c=compile_composition(p);v=validate(plan,p,c,cfg);physical=not v['violations'] and not p['composition_errors'];identity=spatial_identity(p)
            match=next((s for s,i in zip(selected,identities) if i==identity),None)
            distinct=physical and match is None
            status='candidate_for_review' if distinct else 'valid_too_similar' if physical else 'rejected_physical_structural'
            if distinct:selected.append(seed);identities.append(identity)
            v.update(status=status,physical_structural_pass=physical,spatial_diversity=dict(signature=identity,distinct_selection=distinct,similar_to_selected_seed=match))
            display=dict(p,display_title=f'P04 seed {seed} / {status.replace("_"," ")}')
            for overlay,name in [(False,'plan-clean.png'),(True,'plan-encounters.png')]:render(display,c,v,seed,bounds,overlay,px).save(folder/name)
            write(folder/'playable-space.geojson',dict(type='FeatureCollection',features=[dict(type='Feature',properties={'kind':kind},geometry=mapping(c[kind])) for kind in ('walkable','solid','walls','fixtures')]))
        except ValueError as exc:
            physical=False;identity=spatial_identity(p);status='rejected_compile';v=dict(status=status,violations=[str(exc)],warnings=[],physical_structural_pass=False,composition_errors=p['composition_errors'])
            raw=unary_union([Polygon(s['boundary']) for s in p['spaces']]);fake=dict(walkable=raw,spaces={s['id']:Polygon(s['boundary']) for s in p['spaces']})
            display=dict(p,display_title=f'P04 seed {seed} / REJECTED COMPILE — raw proposal')
            render(display,fake,None,seed,bounds,False,px).save(folder/'plan-clean.png')
        write(folder/'validation.json',v)
        m=p['decision_log'][0]['choices'];record=dict(seed=seed,status=status,physical_structural_pass=physical,signature=identity,axis=m['axis'],family=m['B_facing_relationship'],routing_order=m['routing_order'],violations=v['violations'],warnings=v.get('warnings',[]),composition_errors=p['composition_errors'],reproduction=repro)
        attempts.append(record)
        with (args.output/'attempts.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
        print(json.dumps(dict(attempt=len(attempts),seed=seed,status=status,selected=selected,elapsed_seconds=round(time.time()-start))),flush=True)
        if len(selected)==4:break
    changed=[name for name,h in hashes.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    if changed:raise ValueError('Frozen inputs changed during experiment: '+str(changed))
    summary=dict(total_attempts=len(attempts),selected=selected,physical_passes=[x['seed'] for x in attempts if x['physical_structural_pass']],valid_too_similar=[x['seed'] for x in attempts if x['status']=='valid_too_similar'],family_coverage=dict(Counter(x['axis']+'/'+x['family'] for x in attempts)),frozen_inputs_unchanged=True,common_pixels_per_plan_unit=px,stage4_paused=True,attempts=attempts)
    write(args.output/'summary.json',summary)
    for name in ('plan-clean.png','plan-encounters.png'):
        sheet=Image.new('RGB',(3600,3300),'#101923')
        for i,seed in enumerate(selected):sheet.paste(Image.open(args.output/f'seed-{seed}'/name),((i%2)*1800,(i//2)*1650))
        sheet.save(args.output/('selected-'+name))
    report=['# Frozen P04 search — candidates for review','',f'{len(attempts)} attempts; {len(summary["physical_passes"])} physical/structural passes; {len(selected)} spatially distinct selections. Stage 4 remains paused.','', 'The original generator, v3 configuration and checks were copied before search and verified unchanged afterward. No candidate repairs or rule changes. Every attempt was regenerated for a full composition/decision hash comparison.','', '## Spatial comparison','', '| Seed | Relative site ingress | T deployment | CT deployment | Circulation organization |','|---|---|---|---|---|']
    for seed,i in zip(selected,identities):report.append(f'| {seed} | {i["relative_B_ingress"]} | {i["deployment"]["T"]} | {i["deployment"]["CT"]} | {i["circulation"]} |')
    report+=['','Diversity is a conservative categorical screen, not a gameplay or visual quality certificate. It collapses global axis changes, dimensions, cover and local reflections. Borderline variation is deliberately not selected.','', '## Attempts','', '| Seed | Arrangement | Result | Reasons |','|---|---|---|---|']
    for x in attempts:report.append(f'| {x["seed"]} | {x["axis"]}/{x["family"]} | {x["status"]} | {"; ".join(x["violations"]) or "No physical violations; " + ("same spatial signature" if x["status"]=="valid_too_similar" else "selected for review")} |')
    report+=['','## Arrangement coverage','',json.dumps(summary['family_coverage'],indent=2),'','## Remaining limitations','', 'The frozen grammar still packs two site complexes and uses constant-width disjoint connectors. A passing candidate can retain room-chain character. Search does not broaden this rule vocabulary. Timing, balance, encounter control, utility and runtime collision remain unverified. Review each survivor’s warnings and encounter overlay.','', '## Reproduction','',f'`.tools\\training\\Scripts\\python.exe search_frozen_p04.py --seed-start {args.seed_start} --limit {args.limit} --output output/p04-frozen-search-replay`','', 'Use a fresh output directory. The frozen source/configuration files and hashes are retained under frozen/. Individual proposals can be reconstructed with generate(plan, seed, configuration); the per-seed reproducibility.json records both full hashes.','']
    (args.output/'review.md').write_text('\n'.join(report),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='attempts'}),flush=True)

if __name__=='__main__':main()
