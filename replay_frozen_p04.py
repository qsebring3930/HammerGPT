"""Reconstruct one recorded candidate using the experiment's frozen sources."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--experiment',type=Path,required=True);ap.add_argument('--seed',type=int,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    exp=args.experiment.resolve();frozen=exp/'frozen';manifest=json.loads((exp/'manifest.json').read_text())
    for name,h in manifest['source_hashes'].items():
        if hashlib.sha256((frozen/name).read_bytes()).hexdigest()!=h:raise ValueError('Frozen source hash mismatch: '+name)
    sys.path.insert(0,str(frozen))
    from procedural_p04 import generate
    from procedural_p04_checks import validate
    from playable_composition import compile_composition
    from p04_comparison_round import render
    from semantic_pipeline import digest
    if args.output.exists():raise ValueError('Use a new reproduction output directory')
    recorded=exp/f'seed-{args.seed}'
    expected=json.loads((recorded/'reproducibility.json').read_text())['first_sha256']
    cfg=json.loads((exp/'configuration.json').read_text());plan=json.loads((frozen/cfg['strategy']).read_text());p=generate(plan,args.seed,cfg)
    if digest(p)!=expected:raise ValueError('Composition hash differs from recorded candidate')
    args.output.mkdir(parents=True);(args.output/'composition.json').write_text(json.dumps(p,indent=2))
    try:
        c=compile_composition(p);v=validate(plan,p,c,cfg)
        (args.output/'validation.json').write_text(json.dumps(v,indent=2))
        px=min(1600/cfg['world'][0],1250/cfg['world'][1])
        for overlay,name in [(False,'plan-clean.png'),(True,'plan-encounters.png')]:render(p,c,v,args.seed,(0,0,*cfg['world']),overlay,px).save(args.output/name)
    except ValueError as exc:(args.output/'compile-error.txt').write_text(str(exc))
    print(json.dumps(dict(seed=args.seed,reproduced=True,composition_sha256=digest(p))))

if __name__=='__main__':main()
