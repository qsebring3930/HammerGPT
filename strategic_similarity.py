"""Nine-family strategic comparison; IDs, names, A/B labels and counts excluded.

Exploratory similarity, not a CS quality score or calibrated equivalence oracle.
Within-plan route equivalence still uses supported outcome comparisons.
"""
import itertools
import json

from semantic_pipeline import GameplayValidator,compare_outcomes

FAMILIES=('deployment','convergence','first_contact','site_approach','rotation',
          'control_function','flank','recovery','path_equivalence')


def strategic_signature(plan):
    p={r['id']:r for r in plan['places']};all_routes=plan['routes']
    # Duplicate equivalent intentions cannot create macro novelty. Keep a
    # representative per actor/phase/purpose/effect before computing features.
    routes=[]
    for route in all_routes:
        if not any((q['team'],q['phase'],q['purpose'])==(route['team'],route['phase'],route['purpose']) and
                   compare_outcomes(q['outcome'],route['outcome'])['status']=='equivalent' for q in routes):routes.append(route)
    site_of={}
    for site in plan['sites']:
        for key in ('objective','entry_zones','approach_staging','defender_access','fallback','retake'):
            values=site.get(key,[]);values=values if isinstance(values,list) else [values]
            for pid in values:site_of.setdefault(pid,set()).add(site['id'])
    report=GameplayValidator().validate(plan)
    owner={c['place']:c['owner'] for c in plan.get('control_claims',[])}
    pressure={pid:{r['to'] for r in plan['relationships'] if r['from']==pid and r['purpose']=='control_pressure'} for pid in p}
    def role(pid,goal=None):
        if pid not in p:return 'capability' # human strings do not supply identity
        kind=p[pid]['kind'];kind='objective' if kind in ('A_site','B_site') else kind
        suffix=''
        if goal in ('A','B') and site_of.get(pid):
            suffix=':own-site' if goal in site_of[pid] and len(site_of[pid])==1 else ':shared-sites' if len(site_of[pid])>1 else ':other-site'
        if pid in owner:suffix+=':early-'+owner[pid]
        return kind+suffix
    def path_roles(route):
        # Serial plain connectors have no automatic novelty value.
        result=[];goal=route['outcome']['destination']['value']
        for pid in route['places']:
            r=role(pid,goal)
            if not result or r!=result[-1]:result.append(r)
        return result
    out={f:set() for f in FAMILIES}
    def add(f,value):out[f].add(json.dumps(value,sort_keys=True,separators=(',',':')))
    for deployment in plan['deployments']:
        selected=[next(r for r in all_routes if r['id']==a['route']) for a in deployment['assignments']]
        unique=[]
        for r in selected:
            if not any(compare_outcomes(r['outcome'],q['outcome'])['status']=='equivalent' for q in unique):unique.append(r)
        selected=unique
        for r in selected:add('deployment',[deployment['team'],r['purpose'],path_roles(r)])
        for a,b in itertools.combinations(selected,2):
            interior=set(a['places'][1:-1])&set(b['places'][1:-1])
            add('deployment',[deployment['team'],'shared-precommitment',sorted({role(i) for i in interior})])
    attack=[r for r in routes if r['team']=='T' and r['purpose'] in ('primary_attack','secondary_attack')]
    for a,b in itertools.combinations(attack,2):
        if a['phase']!=b['phase']:continue
        shared=set(a['places'][1:])&set(b['places'][1:])
        same=a['outcome']['destination']['value']==b['outcome']['destination']['value']
        after=[]
        for pid in shared:
            firsta=a.get('first_contact',{}).get('value');firstb=b.get('first_contact',{}).get('value')
            if firsta in a['places'] and firstb in b['places'] and a['places'].index(pid)>a['places'].index(firsta) and b['places'].index(pid)>b['places'].index(firstb):after.append(role(pid))
        add('convergence',[same,sorted({role(i) for i in shared}),sorted(set(after))])
    for r in routes:
        if r.get('first_contact'):
            contact=r['first_contact']['value'];goal=r['outcome']['destination']['value']
            arrival=r.get('arrivals',{}).get(contact,{}).get('value')
            sharing=any(q['team']==r['team'] and q['id']!=r['id'] and q['outcome']['destination']['value']!=goal and q.get('first_contact',{}).get('value')==contact for q in routes)
            add('first_contact',[r['team'],r['purpose'],role(contact,goal),sharing,
                'early' if arrival and arrival[1]<=14 else 'later' if arrival else 'unknown'])
        if r in attack:
            o=r['outcome'];time=o['timing']['value']
            add('site_approach',[r['purpose'],path_roles(r),
                'immediate' if time[1]<=14 else 'territory-first' if time[0]>=24 else 'prepared',
                o['entry_angle']['value']!=0,o['elevation']['value']!='ground',
                bool(r.get('requirements')),sorted({role(v,o['destination']['value']) for v in o['defender_bypass']['value']})])
        if r['purpose']=='rotation' or r['team']=='T' and r['purpose']=='retreat':
            o=r['outcome'];t=o['timing']['value']
            add('rotation',[r['team'],r['purpose'],path_roles(r),'costly' if t[0]>=13 else 'moderate',
                bool(o['engagement']['value']),bool(r.get('requirements'))])
        if r['purpose']=='flank':
            o=r['outcome'];add('flank',[path_roles(r),bool(r.get('condition')),
                sorted({role(i) for i in o['information']['value']}),sorted({role(i) for i in o['defender_bypass']['value']})])
        if r['phase'] in ('retake','defense'):
            add('recovery',[r['purpose'],path_roles(r),r['outcome']['entry_angle']['value']!=0])
    for pid in p:
        if p[pid]['kind']=='mid_candidate' or pid in owner or pressure[pid] or p[pid]['kind']=='encounter_space' and any(r['places'][-1]==pid and r['team']=='T' and r['purpose']=='contest' for r in routes):
            reachable_sites={s['id'] for s in plan['sites'] if any(v in pressure[pid] for v in [s['objective'],*s['entry_zones'],*s['defender_access']])}
            used_for_rotation=any(pid in r['places'] for r in routes if r['purpose']=='rotation')
            mandatory=any(pid in r['places'] for r in attack if r['purpose']=='primary_attack')
            add('control_function',[role(pid),len(reachable_sites),used_for_rotation,mandatory,
                report['validated_roles'].get(pid,{}).get('validated',False)])
    if not out['control_function']:add('control_function',['no classical or equivalent control assignment'])
    for c in report['route_comparisons']:
        add('path_equivalence',[c['status'],sorted(c['changes']),sorted(c['unknown'])])
    # Redundant-choice diagnostics are separate from macro identity: duplicating
    # an intention does not make a new organization.
    for site in plan['sites']:
        entries=site['entry_zones']
        retakes=[r for r in routes if r['phase']=='retake' and r['places'][-1] in entries]
        shared=any(set(site['retake'])&set(other['retake']) for other in plan['sites'] if other['id']!=site['id'])
        add('recovery',['shared-regather',shared,'front-recovery',any(r['places'][-1]==site['entry_zones'][0] for r in retakes)])
    return {f:sorted(out[f]) for f in FAMILIES}


def compare_strategies(left,right):
    a=strategic_signature(left);b=strategic_signature(right)
    per={}
    for family in FAMILIES:
        x,y=set(a[family]),set(b[family]);per[family]=len(x&y)/len(x|y) if x|y else 1.0
    return {'similarity':sum(per.values())/len(per),'families':per,
            'changed_families':[f for f in FAMILIES if a[f]!=b[f]],
            'same_strategic_signature':a==b,
            'scope':'Equal-weight nine-family exploratory similarity; no names, A/B identity or graph-count quality score.'}


def similarity_groups(plans,threshold=0.80):
    """Complete-link grouping; do not chain A≈B≈C into A≈C."""
    groups=[]
    for key,plan in plans:
        group=next((g for g in groups if all(compare_strategies(plan,p)['similarity']>=threshold for _,p in g)),None)
        if group is None:groups.append([(key,plan)])
        else:group.append((key,plan))
    return [[key for key,_ in group] for group in groups]
