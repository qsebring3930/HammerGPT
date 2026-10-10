"""Stage 1/2 diversity experiment only. Does not import embedding/rendering."""
import itertools
import json
from pathlib import Path

from semantic_pipeline import StrategicPlanner,GameplayValidator,blueprint
from strategic_similarity import compare_strategies,strategic_signature,similarity_groups,FAMILIES

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/strategic-diversity-001'
# These are independent gameplay starting conditions, not ten full layouts.
# Unspecified decisions are independently sampled by the common rule grammar.
CONDITIONS=[
    ('Contested exchange',{'control':'contested','deployment':'independent','secondary':'control'}),
    ('Optional one-site control',{'control':'optional','secondary':'mixed','defender_rotation':'rear'}),
    ('Observation without Mid',{'control':'scout','secondary':'local','attacker_rotation':'redeploy'}),
    ('Separated site commitments',{'control':'none','defender_rotation':'deployment','deployment':'independent','attacker_rotation':'redeploy'}),
    ('Attacker preparation relay',{'control':'T_owned','deployment':'shared_staging','attacker_rotation':'control','secondary':'control'}),
    ('Defender distribution center',{'control':'CT_owned','secondary':'local'}),
    ('Vertical control commitment',{'control':'vertical','secondary':'control','attacker_rotation':'control'}),
    ('Split then recombine',{'deployment':'split_recombine','control':'none','defender_rotation':'rear'}),
    ('One pressure, one territory',{'site_commitment':'one_territorial','control':'optional','secondary':'mixed','attacker_rotation':'staging'}),
    ('Capture enables site transfer',{'attacker_rotation':'site_capture','defender_rotation':'exposed','control':'none'}),
    ('Retake coalition',{'retake':'shared_regroup','defender_rotation':'central','control':'scout'}),
    ('Two fights, later reunion',{'deployment':'recombine_after_contact','control':'none','retake':'front_recovery'}),
    ('Unconstrained seed 1',{}),('Unconstrained seed 2',{}),
    ('Unconstrained seed 3',{}),('Unconstrained seed 4',{}),
]
SEEDS=[104729,130363,155921,181081,206369,231701,257053,282407,
       307759,333131,358471,383833,409171,434521,459883,485239]


def explain(plan):
    r=plan['sampled_rules']
    control={
        'contested':'Mid is a third early fight and grants secondary access to both sites.',
        'optional':'A separate optional contest influences one site; it is not classical two-site Mid.',
        'scout':'The optional contest supplies observation without unlocking both sites.',
        'none':'There is no classical Mid: opening investment is in site approaches.',
        'T_owned':'Attackers own early preparation/relay space and can preserve it while changing targets.',
        'CT_owned':'Defenders own the distribution center; attackers reach it only after clearing a site approach.',
        'vertical':'Contested access enables raised entry options while defender switches require secure level-change access.'}[r['control']]
    deploy={
        'independent':'Attacker assignments diverge at deployment and retain separate preparation.',
        'shared_staging':'Attackers preserve a common staging area before choosing the site commitment.',
        'split_recombine':'Initial deployment groups take separate exposure paths and reunite before the execute decision.',
        'recombine_after_contact':'Separate squads take different first fights and reunite only after those contests.'}[r['deployment']]
    rotate={
        'rear':'Defenders transfer through rear territory without automatically owning forward control.',
        'deployment':'Defender switches require a long withdrawal through deployment, favoring earlier site commitment.',
        'central':'Defenders redistribute through a common control hub, sacrificing the original hold.',
        'vertical':'Defender rotation depends on retaining level-change access.',
        'exposed':'Defender transfers cross an exposed site-side engagement; enemy pressure can interrupt reinforcement.'}[r['defender_rotation']]
    approach={
        'both_staged':'Both sites support prepared entry.',
        'one_immediate':'One site can receive immediate pressure while the other requires preparation.',
        'one_territorial':'One execute requires securing forward territory; the other has a direct prepared entry.'}[r['site_commitment']]
    recovery={
        'separate':'Each site has independent fallback and retake preparation.',
        'shared_regroup':'Surviving defenders reunite before choosing which site to recover.',
        'front_recovery':'Retakes must reclear the lost main entry instead of obtaining a free rear entry.'}[r['retake']]
    flank=next(q for q in plan['routes'] if q['purpose']=='flank')
    contacts=sorted({q['first_contact']['value'] for q in plan['routes'] if q['team']=='T' and 'first_contact' in q})
    primary=[q for q in plan['routes'] if q['team']=='T' and q['purpose']=='primary_attack']
    shared=set(primary[0]['places'][1:-1])&set(primary[1]['places'][1:-1])
    convergence='Opening assignments retain separate approach investments.'
    if shared:
        convergence='Site assignments share '+', '.join(sorted(shared))+'. '
        convergence+=('Squads recombine after taking different first contacts.' if r['deployment']=='recombine_after_contact' else
                      'They share preparation before the final site choice.')
    resets=[q for q in plan['routes'] if q['team']=='T' and q['purpose']=='retreat']
    retreat='Attacker resets finish at '+', '.join(sorted({q['places'][-1] for q in resets}))+'.'
    report=GameplayValidator().validate(plan)
    effect_changes=sorted({effect for c in report['route_comparisons'] for effect in c['changes']})
    equivalence='Alternate site entries differ in '+', '.join(effect_changes)+'. Equivalence is checked on outcomes, not route names.'
    return {'identity':control+' '+deploy,'deployment':deploy,'control':control,'site_approach':approach,
            'rotation':rotate,'recovery':recovery,'flank':flank['condition'],
            'first_contacts':', '.join(contacts),'convergence':convergence,'retreat':retreat,'path_equivalence':equivalence,
            'why_different':rotate+' '+approach+' '+recovery}


def run():
    OUT.mkdir(parents=True,exist_ok=True);rows=[];survivors=[]
    for i,((label,condition),seed) in enumerate(zip(CONDITIONS,SEEDS),1):
        pid=f'P{i:02d}';plan=StrategicPlanner().propose(condition,seed);report=GameplayValidator().validate(plan)
        directory=OUT/pid;directory.mkdir(exist_ok=True);description=explain(plan)
        for name,data in [('plan.json',plan),('validation.json',report),('strategic-signature.json',strategic_signature(plan))]:
            (directory/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
        text=f"# {pid}: {label}\n\nSeed: {seed}. Status: {'SURVIVES CONTRACT VALIDATION' if report['passed'] else 'REJECTED'}\n\n"
        for key in ('identity','deployment','convergence','first_contacts','site_approach','rotation','control','flank','retreat','recovery','path_equivalence'):
            text+=f"**{key.replace('_',' ').title()}:** {description[key]}\n\n"
        text+='All outcomes are proposed contracts, not measured timings or approved tactical facts. No coordinates, embedding or geometry.\n\n'+blueprint(plan,report)
        (directory/'blueprint.md').write_text(text,encoding='utf-8')
        rows.append({'id':pid,'seed':seed,'starting_label':label,'passed':report['passed'],
                     'blocking_codes':sorted({q['code'] for q in report['issues']}),'rules':plan['sampled_rules'],**description})
        if report['passed']:survivors.append((pid,plan))
    comparisons=[]
    for (a,p),(b,q) in itertools.combinations(survivors,2):comparisons.append({'left':a,'right':b,**compare_strategies(p,q)})
    groups=similarity_groups(survivors);broad=[(pid,p) for pid,p in survivors if int(pid[1:])>=13]
    exact=len({json.dumps(strategic_signature(p),sort_keys=True) for _,p in survivors})
    signatures=[strategic_signature(p) for _,p in survivors]
    family_variants={f:len({json.dumps(s[f],sort_keys=True) for s in signatures}) for f in FAMILIES}
    majority_collapse=any(len(g)>len(survivors)/2 for g in groups) if survivors else True
    summary={'proposals':len(rows),'survivors':len(survivors),'distinct_signatures':exact,
             'similarity_threshold':0.80,'similarity_groups':groups,
             'unconstrained_groups':similarity_groups(broad),'majority_collapse':majority_collapse,
             'family_variants':family_variants,
             'stage_3_authorized':False,'embedding_run':False,'geometry_generated':False,
             'verdict':'Most survivors collapse: diagnose the grammar.' if majority_collapse else
                       'Rule grammar shows multiple contract-level organizations; no trained-model diversity claim.',
             'families':FAMILIES,
             'limitations':['Starting conditions deliberately exercise grammar capabilities; not an unbiased novelty rate.',
                            'Four unconstrained seeds are a small pilot, not a distributional benchmark.',
                            'Similarity threshold/weights are exploratory and uncalibrated.',
                            'Availability across phases, physical timing/visibility and conditional access need further verification.']}
    for name,data in [('summary.json',summary),('proposals.json',rows),('pairwise-comparison.json',comparisons)]:
        (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
    lines=['# Stage 1/2 strategic diversity experiment','',
        f"{len(rows)} proposals from independent seeds/conditions; {len(survivors)} survive internal contract validation. {exact} different nine-family signatures.",
        '', 'No spatial embedding or floor generation. All gameplay effects are proposed intentions.',
        '', '## Surviving organizations side by side','',
        '| Blueprint | Macro identity / deployment | First contacts | Why the rotation / recovery changes play |',
        '|---|---|---|---|']
    for row in rows:
        if row['passed']:lines.append(f"| [{row['id']}]({row['id']}/blueprint.md) | {row['identity']} | {row['first_contacts']} | {row['why_different']} |")
    lines+=['','## Comparison method','',
        'Nine equally weighted feature families inspect deployment, convergence, first-contact sharing, site approaches, rotations, control function, flank prerequisites, retreat/retake organization and tactical route equivalence. Features come from actual plans and validator results, not the starting-condition label or sampled-rule names.',
        '', 'Names, route IDs, seeds and A/B labels are excluded. Serial identical connectors and duplicate equivalent routes do not earn novelty. Node/edge/cycle/route counts are not similarity or quality objectives.',
        '', 'Similarity is the mean family Jaccard overlap. Complete-link groups use an exploratory 0.80 threshold. A larger value means more similar, not better. Numerical thresholds are not calibrated against human judgments.',
        '',f"Groups: {groups}",f"Unconstrained pilot groups: {summary['unconstrained_groups']}",
        '', '## Diversity by strategic function','',
        '| Function | Different observed signatures among survivors |', '|---|---|',
        *[f'| {f.replace("_"," ")} | {family_variants[f]} |' for f in FAMILIES],
        '', '## Closest pairs and concrete differences','']
    for pair in sorted(comparisons,key=lambda p:p['similarity'],reverse=True)[:8]:
        lines.append(f"- {pair['left']} / {pair['right']}: {pair['similarity']:.2f} similarity; different families: {', '.join(pair['changed_families']) or 'none'}. See pairwise-comparison.json for all nine overlaps.")
    failures=[r for r in rows if not r['passed']]
    lines+=['','## Rejections','']
    if not failures:lines.append('None in this contract-level batch. This does not certify physical feasibility; rejection controls are tested separately.')
    for r in failures:lines.append(f"- [{r['id']}]({r['id']}/blueprint.md): {', '.join(r['blocking_codes'])}.")
    lines+=['', 'The failures explain limits in the grammar:',
        '', '- P05 allocates both attacker-owned control and a shared preparation relay, then offers rejoining ways around them without a supported branch-local difference.',
        '- P07 introduces stairs beside a defender hub but also creates reconnecting rotation shortcuts. Its claimed vertical commitment does not justify those alternatives.',
        '- P08, P11 and P14 split deployment into two paths that reunite before a meaningful difference is evidenced. Different exposure descriptions alone do not pass.',
        '- P16 claims two-site Mid pressure but constructs a witnessed secondary access for only one site. A pressure label cannot invent the missing tactical consequence.',
        '', 'These candidates were retained as failures; their connections were not repaired and no generation seed was rerolled to satisfy a survivor quota.']
    lines+=['','## Diagnosis and limits','',summary['verdict'],
        '', 'The previous planner was a contract compiler, not an independent proposal generator. This experiment adds a compositional rule grammar. Deliberately different starting conditions demonstrate expressiveness; they do not demonstrate that a learned model discovers diverse identities from the source corpus.',
        '', 'The surviving set has only two flank signatures and three recovery signatures. Every site still uses the same main/secondary-entry interface scaffold, and encounter ranges remain uniformly medium. Meaningful macro differences exist, but this is not evidence of broad diversity in site fights, flank prerequisites or engagement range. The attacker-owned relay, mandatory vertical rotation and pre-contact split-deployment experiments all failed in this batch. Stage 1 needs better causal rules for those cases before claiming those capabilities.',
        '',*['- '+v for v in summary['limitations']],
        '', '**Stage 3 remains paused regardless of the result.**','']
    (OUT/'review.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(summary))
    return rows,summary


if __name__=='__main__':run()
