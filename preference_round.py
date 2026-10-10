"""Five physical proposals for explicit human preference review.

Uses procedural geometry, not neural graph weights. Reviews become pairwise
examples for a future preference scorer; recording them is not model training.
"""
import argparse
import hashlib
import json
from pathlib import Path

import networkx as nx
from PIL import Image, ImageDraw, ImageFont

from strategic_floorplan import ROOT, audit_saved, canonical_strategy, realize, render, save


def graph_of(candidate):
    graph=nx.Graph()
    graph.add_nodes_from(n['id'] for n in candidate['nodes'])
    graph.add_edges_from(e['places'] for e in candidate['edges'])
    roles={n['id']:n['role'] for n in candidate['nodes'] if n['role'] in ('T','CT','A','B')}
    return canonical_strategy(graph,roles)


def generate(folder,first_seed,attempts,model_path=None):
    from semantic_pipeline import check_generation_policy
    check_generation_policy(legacy=True)
    if folder.exists():raise ValueError('Choose a new round folder; existing rounds are immutable.')
    folder.mkdir(parents=True)
    previous=ROOT/'output/strategic-floorplan-v6'
    old=[json.loads((previous/f'candidate-{i}/layout.json').read_text()) for i in range(1,4)]
    save(folder/'prior-feedback.json',{
        'user_statement':'I only think candidate 2 is good.',
        'source_round':'output/strategic-floorplan-v6',
        'labels':[{'seed':c['seed'],'acceptable':i==2,
                   'layout_sha256':hashlib.sha256((previous/f'candidate-{i}/layout.json').read_bytes()).hexdigest()}
                  for i,c in enumerate(old,1)],
        'use':'Explicit preference evidence; not a mandate to copy candidate 2 or its numeric features.'})
    excluded=[graph_of(c) for c in old]
    match=nx.algorithms.isomorphism.categorical_node_match('role','')
    records=[];candidates=[]
    model=json.loads(model_path.read_text()) if model_path else None
    pool_size=15 if model else 5
    for seed in range(first_seed,first_seed+attempts):
        try:
            candidate,graph=realize(seed)
            if any(nx.is_isomorphic(graph,g,node_match=match) for g in excluded):
                raise ValueError('strategic_duplicate_of_reviewed_or_batch_layout')
            audit=audit_saved(candidate)
        except ValueError as e:
            records.append({'seed':seed,'accepted':False,'reason':str(e)})
            continue
        excluded.append(graph);candidates.append(candidate)
        i=len(candidates)
        records.append({'seed':seed,'accepted':True,'pool_number':i})
        print(f'Valid review proposal {i}/{pool_size} ready (seed {seed})',flush=True)
        if i==pool_size:break
    save(folder/'unedited-proposal-pool.json',candidates)
    if model:
        from preference_scorer import score
        candidates=sorted(candidates,key=lambda c:score(model,c),reverse=True)
        # Four favored proposals plus one lower-ranked exploration proposal.
        candidates=candidates[:4]+candidates[4:5]
        if len(json.loads((folder/'unedited-proposal-pool.json').read_text()))>5:
            pool=json.loads((folder/'unedited-proposal-pool.json').read_text())
            remaining=[c for c in pool if c['seed'] not in [v['seed'] for v in candidates[:4]]]
            candidates=candidates[:4]+[min(remaining,key=lambda c:score(model,c))]
    for i,candidate in enumerate(candidates,1):
        sub=folder/f'candidate-{i}';sub.mkdir()
        save(sub/'layout.json',candidate);save(sub/'audit.json',audit_saved(candidate))
        render(candidate,sub/'radar.png');render(candidate,sub/'routes.png',True)
    save(folder/'search-log.json',records)
    save(folder/'manifest.json',{
        'generator':'procedural strategic_floorplan prototype; no neural checkpoint used',
        'selection':'four preference-ranked plus one exploration proposal' if model else
                    'first five independently audited, structurally distinct proposals from fixed seed sequence',
        'ranked_by_preference_model':bool(model),'training_performed':False,
        'preference_model_path':str(model_path) if model_path else None,
        'seed_start':first_seed,'attempted':len(records),'count':len(candidates),
        'candidate_ids':[{'number':i,'seed':c['seed'],
            'layout_sha256':hashlib.sha256((folder/f'candidate-{i}/layout.json').read_bytes()).hexdigest()}
            for i,c in enumerate(candidates,1)],
        'review_status':'awaiting_user_choice_and_comments',
        'scope':'Flat physical proposals; CS2 collision and competitive quality unverified.'})
    (folder/'generation-script.py').write_bytes(Path(__file__).read_bytes())
    (folder/'geometry-script.py').write_bytes((ROOT/'strategic_floorplan.py').read_bytes())
    if candidates:
        canvas=Image.new('RGB',(2400,1810),'#080f18');draw=ImageDraw.Draw(canvas)
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32)
        for i,c in enumerate(candidates,1):
            row,col=divmod(i-1,3);x,y=col*800,row*890
            image=Image.open(folder/f'candidate-{i}'/'radar.png').resize((790,790),Image.Resampling.LANCZOS)
            canvas.paste(image,(x+5,y+55))
            draw.text((x+35,y+15),f'RADAR {i}',font=font,fill='#e6f0f8')
        draw.text((1650,1030),'Choose your favorite.',font=font,fill='#e6f0f8')
        draw.text((1650,1090),'What works?',font=font,fill='#b7cbd9')
        draw.text((1650,1150),'What would you change?',font=font,fill='#b7cbd9')
        draw.text((35,1750),'Human review round 1 · procedural floor geometry · your preference is pending',font=font,fill='#b7cbd9')
        canvas.save(folder/'comparison.png')
    print(json.dumps({'output':str(folder),'radars':len(candidates)}))


def record_review(folder,best,comments,acceptable=None):
    manifest=json.loads((folder/'manifest.json').read_text())
    ids={c['number']:c for c in manifest['candidate_ids']}
    if best not in ids:raise ValueError('Choice must identify a displayed candidate.')
    if not comments.strip():raise ValueError('Preserve the user comments explicitly.')
    if acceptable is not None and (any(i not in ids for i in acceptable) or best not in acceptable):
        raise ValueError('Acceptability must identify displayed candidates and include the selected best.')
    for i,identity in ids.items():
        if hashlib.sha256((folder/f'candidate-{i}/layout.json').read_bytes()).hexdigest()!=identity['layout_sha256']:
            raise ValueError('Reviewed layout changed since display; do not attach feedback to different geometry.')
    output=folder/'human-review.json'
    if output.exists():raise ValueError('Review exists; preserve it before adding a correction.')
    review={'best_candidate':ids[best],'verbatim_comments':comments,
            'pairwise_examples':[{'preferred':ids[best],'less_preferred':c}
                                 for i,c in ids.items() if i!=best],
            'interpretation':'Best within this batch; no absolute quality labels inferred for other candidates.',
            'model_training_performed':False}
    if acceptable is not None:
        review['acceptability_labels']=[{'candidate':identity,'acceptable':i in acceptable} for i,identity in ids.items()]
        review['interpretation']='Relative choice and explicit acceptable/unacceptable labels provided by user.'
    save(output,review)
    manifest['review_status']='reviewed';save(folder/'manifest.json',manifest)
    fit_review_history(folder)
    review['preference_scorer_trained']=True
    review['model_training_performed']=True
    review['generator_weights_updated']=False
    save(output,review)
    manifest['preference_scorer_trained']=True;save(folder/'manifest.json',manifest)
    print(json.dumps(review,indent=2))


def fit_review_history(folder):
    """Accumulate explicit comparisons instead of forgetting previous rounds."""
    from preference_scorer import train,score
    training={};pairs=[]
    prior=json.loads((folder/'prior-feedback.json').read_text())
    oldfolder=ROOT/prior['source_round']
    def load(key,path,expected_hash):
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected_hash:
            raise ValueError('Preference source geometry changed; cannot reuse its label.')
        training[key]=json.loads(raw)
    for i,label in enumerate(prior['labels'],1):
        load(f'prior-{i}',oldfolder/f'candidate-{i}/layout.json',label['layout_sha256'])
    accepted=[i for i,l in enumerate(prior['labels'],1) if l['acceptable']]
    rejected=[i for i,l in enumerate(prior['labels'],1) if not l['acceptable']]
    pairs.extend((f'prior-{a}',f'prior-{b}') for a in accepted for b in rejected)
    for reviewfile in sorted((ROOT/'output').glob('preference-round-*/human-review.json')):
        record=json.loads(reviewfile.read_text())
        for pair in record['pairwise_examples']:
            keys=[]
            for side in ('preferred','less_preferred'):
                identity=pair[side];n=identity['number'];key=f'{reviewfile.parent.name}-{n}'
                load(key,reviewfile.parent/f'candidate-{n}/layout.json',identity['layout_sha256'])
                keys.append(key)
            pairs.append(tuple(keys))
    model=train(training,pairs)
    save(folder/'training-data.json',{'candidates':training,'pairs':pairs})
    model['training_data_path']=str((folder/'training-data.json').resolve())
    save(folder/'preference-model.json',model)
    manifest=json.loads((folder/'manifest.json').read_text())
    save(folder/'fitted-round-scores.json',[
        {'number':identity['number'],'score':score(model,training[f"{folder.name}-{identity['number']}"]),
         'scope':'Training examples; not an independent quality evaluation.'}
        for identity in manifest['candidate_ids']])
    return model


def main():
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='command',required=True)
    generate_parser=commands.add_parser('generate')
    generate_parser.add_argument('--seed',type=int,default=12000)
    generate_parser.add_argument('--attempts',type=int,default=5000)
    generate_parser.add_argument('--output',default='output/preference-round-001')
    generate_parser.add_argument('--model',type=Path,help='Optional fitted preference-model.json from a reviewed round.')
    review_parser=commands.add_parser('review')
    review_parser.add_argument('--output',default='output/preference-round-001')
    review_parser.add_argument('--best',type=int,required=True)
    comment_args=review_parser.add_mutually_exclusive_group(required=True)
    comment_args.add_argument('--comments')
    comment_args.add_argument('--comments-file',type=Path)
    review_parser.add_argument('--acceptable',nargs='*',type=int,default=None)
    args=parser.parse_args();folder=ROOT/args.output
    if args.command=='generate':generate(folder,args.seed,args.attempts,args.model)
    else:record_review(folder,args.best,args.comments_file.read_text(encoding='utf-8') if args.comments_file else args.comments,args.acceptable)


if __name__=='__main__':main()
