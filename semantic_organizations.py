"""Composable, seeded strategic-intention grammar. No embedding or floors.

Starting conditions constrain ownership/commitment decisions, not full layouts.
All outcomes are provisional contracts, never measured source-map facts.
"""
import random

from semantic_pipeline import fact

DOMAINS={
    'control':['contested','optional','scout','none','T_owned','CT_owned','vertical'],
    'deployment':['independent','shared_staging','split_recombine','recombine_after_contact'],
    'defender_rotation':['rear','deployment','central','vertical','exposed'],
    'attacker_rotation':['redeploy','staging','control','site_capture'],
    'site_commitment':['both_staged','one_immediate','one_territorial'],
    'retake':['separate','shared_regroup','front_recovery'],
    'secondary':['local','control','mixed'],
}


def choose_rules(condition,seed):
    rng=random.Random(seed)
    rules={key:rng.choice(condition.get(key,values) if isinstance(condition.get(key,values),list)
                               else [condition[key]]) for key,values in DOMAINS.items()}
    # Compatibility constraints arise from gameplay function, not target counts.
    if rules['control']=='none':
        if rules['secondary']=='control':rules['secondary']='local'
        if rules['attacker_rotation']=='control':rules['attacker_rotation']='redeploy'
    if rules['control']=='CT_owned' and rules['secondary']=='control':rules['secondary']='local'
    if rules['control']=='CT_owned':rules['defender_rotation']='central'
    if rules['control']=='vertical':rules['defender_rotation']='vertical'
    return rules


def organization_brief(condition,seed):
    rules=choose_rules(condition,seed);rng=random.Random(seed)
    source=f'Seed {seed}: provisional gameplay contract, not measured or human-approved'
    def cf(v):return fact(v,'design_contract',source)
    brief={'name':f'Strategic organization seed {seed}','places':[],'route_intents':[],
           'relationships':[],'deployments':[],'sites':[],'mid_claims':[],'cycles':[],
           'control_claims':[],'require_contact_witnesses':True,'require_pressure_witnesses':True,'seed':seed,
           'starting_condition':condition,'sampled_rules':rules,
           'evidence_scope':'Seeded rule-based proposal. All tactical effects are intended contracts; physical verification and human approval pending.'}
    places={};routes={}
    def place(pid,kind,intention,**extra):
        if pid in places:return pid
        row={'id':pid,'name':pid.replace('_',' '),'kind':kind,'role_evidence':cf(intention),'intention':intention,**extra}
        places[pid]=row;brief['places'].append(row);return pid
    def route(rid,team,purpose,path,dest,time,why,engagement=(),angle=0,elevation='ground',
              bypass=(),information=(),retreat=(),rotations=(),phase='opening',alternative=None,
              condition=None,contact=None,arrivals=None,requirements=None):
        outcome={'destination':dest,'timing':time,'engagement':list(engagement),'entry_angle':angle,
                 'elevation':elevation,'defender_bypass':list(bypass),'engagement_range':'medium',
                 'information':list(information),'retreat_capability':list(retreat),'rotation_capability':list(rotations)}
        row={'id':rid,'team':team,'purpose':purpose,'phase':phase,'places':path,'why':why,
             'purpose_evidence':cf(why),'outcome':{k:cf(v) for k,v in outcome.items()},
             'timing_basis':'round_start' if phase=='opening' else 'route_elapsed'}
        if alternative:row['alternative_to']=alternative
        if condition:row['condition']=condition
        if contact:row['first_contact']=cf(contact)
        if arrivals:row['arrivals']={k:cf(v) for k,v in arrivals.items()}
        if requirements:row['requirements']=requirements
        routes[rid]=row;brief['route_intents'].append(row);return row
    def relation(rid,a,b,purpose,why):
        brief['relationships'].append({'id':rid,'from':a,'to':b,'purpose':purpose,
            'team':'both','phase':'any','why':why,'purpose_evidence':cf(why)})

    place('T','T_spawn','Allocate attack squads; path choice carries commitment and switching consequences.')
    place('CT','CT_spawn','Deploy site defenders; initial assignment costs coverage elsewhere.')
    for s in ('A','B'):
        for suffix,kind,why in [('',f'{s}_site','Objective belongs to a multi-phase gameplay system.'),
            ('_prep','attacker_staging','Prepare an entry; withdrawing preserves an execute reset.'),
            ('_entry','site_entry','Main entry engages the front defensive assignment.'),
            ('_side','site_entry','Secondary entry presents another local attack sector.'),
            ('_hold','defender_position','Commit a defender to the site entry system.'),
            ('_rear','fallback','Disengage while retaining the selected rotation/retake options.'),
            ('_retake','retake_staging','Gather before reengaging occupied site space.'),
            ('_fight','encounter_space','Both teams can deliberately contest this approach before site commitment.')]:
            place(s+suffix,kind,why)
    dep=rules['deployment'];ctrl=rules['control'];rot=rules['defender_rotation'];atkrot=rules['attacker_rotation']
    if dep=='shared_staging':place('shared_prep','attacker_staging','T-controlled preparation lets attackers change targets before either site fight.')
    if dep=='split_recombine':
        place('left_deploy','connector','One deployment subgroup bypasses the first observation angle.')
        place('right_deploy','connector','Second subgroup takes an exposed observation angle before regrouping.')
        place('regroup','attacker_staging','Recombine split squads before a common execute preparation decision.')
    if dep=='recombine_after_contact':place('regroup','attacker_staging','Two differently exposed approach squads reunite after their first contests.')
    if rot in ('rear','exposed'):place('transfer','connector','Rear protected rotation.' if rot=='rear' else 'Cross an exposed site-side transfer to switch defense assignments.')
    if rot in ('central','vertical'):place('defender_hub','connector','CT-owned distribution space connects defense assignments and retake access.')
    if rot=='vertical':place('rotation_stairs','vertical_transition','Controlling the level-change access is required for defender transfers.')
    has_control=ctrl!='none'
    if has_control:
        kind='mid_candidate' if ctrl in ('contested','vertical') else 'encounter_space' if ctrl in ('optional','scout') else 'attacker_staging' if ctrl=='T_owned' else 'connector'
        place('control',kind,'Control function is established by witnessed access and consequential destination pressure, not location.')
        if ctrl=='vertical':place('control_stairs','vertical_transition','Contest access requires an explicit level change.')
    contact_time=[10,12]
    primary={};secondary={}
    staged_site=rng.choice(['A','B'])
    for s in ('A','B'):
        prep=f'{s}_prep';fight=f'{s}_fight'
        if dep=='independent':prefix=['T',prep]
        elif dep=='shared_staging':prefix=['T','shared_prep',prep]
        elif dep=='split_recombine':prefix=['T','left_deploy' if s=='A' else 'right_deploy','regroup',prep]
        else:prefix=['T',prep]
        if ctrl=='T_owned':prefix=prefix[:1]+['control']+prefix[1:]
        if rules['site_commitment']=='one_territorial' and s==staged_site:
            place(f'{s}_territory','attacker_staging','Win forward territory, retain it, then prepare the final site execute.')
            tail=[fight,f'{s}_territory',f'{s}_entry'];time=[24,26]
            requirement=[{'place':fight,'state':'secured','effect':'Final execute preparation is unavailable until this approach has been won.'}]
        else:tail=[fight,f'{s}_entry'];time=[17,19];requirement=[]
        if rules['site_commitment']=='one_immediate' and s!=staged_site:time=[11,13]
        if dep=='recombine_after_contact':tail=[fight,'regroup',f'{s}_entry']
        primary[s]=route(f'T-{s}-main','T','primary_attack',prefix+tail,s,time,
            'Commit through the site approach fight; the preparation/territory condition controls when entry is possible.',
            engagement=[fight,f'{s}_hold'],contact=fight,arrivals={fight:contact_time},
            retreat=[prefix[-1]],rotations=['T'] if atkrot=='redeploy' else ['shared_prep' if dep=='shared_staging' else 'control' if atkrot=='control' and has_control else prep],requirements=requirement)
        use_control=has_control and ctrl!='CT_owned' and (rules['secondary']=='control' or rules['secondary']=='mixed' and s==staged_site)
        if use_control:
            path=['T','control']+(['control_stairs'] if ctrl=='vertical' else [])+[f'{s}_side']
            if ctrl=='T_owned':path=['T','control',prep,f'{s}_side']
            events=[] if ctrl=='T_owned' else ['control']
            if ctrl=='T_owned':events=[f'{s}_hold']
            first= 'control' if ctrl!='T_owned' else fight
            if ctrl=='T_owned':path=['T','control',prep,fight,f'{s}_side']
            st=route(f'T-{s}-alt','T','secondary_attack',path,s,[22,24],
                'Use control-space ownership for another site entry; the ownership investment is the cost.',
                engagement=events+[f'{s}_hold'],angle=90,elevation='raised' if ctrl=='vertical' else 'ground',
                bypass=[fight] if ctrl!='T_owned' else [],information=['control'],retreat=['control'],
                rotations=[other for other in ('A','B') if other!=s] if ctrl in ('contested','vertical','T_owned') else [],
                alternative=primary[s]['id'],contact=first,arrivals={first:contact_time})
        else:
            path=prefix+[fight,f'{s}_side']
            st=route(f'T-{s}-alt','T','secondary_attack',path,s,[18,20],
                'Same approach investment but a separate site entry sector; angle and defender assignment, not an extra corridor, justify this choice.',
                engagement=[fight,f'{s}_hold'],angle=90,retreat=[prefix[-1]],alternative=primary[s]['id'],contact=fight,arrivals={fight:contact_time})
        secondary[s]=st

    defender_paths={}
    for s in ('A','B'):
        hub='control' if ctrl=='CT_owned' else 'defender_hub'
        path=['CT']+([hub] if rot in ('central','vertical') else [])+[f'{s}_rear',f'{s}_hold']
        defender_paths[s]=path
        route(f'CT-{s}-deploy','CT','defensive_access',path,s,[6,8],
              'Establish the site hold; switching consumes time and abandons its entry coverage.',
              engagement=[f'{s}_hold'],retreat=[f'{s}_rear'],rotations=[f'{s}_rear'])
        route(f'CT-{s}-contest','CT','contest',['CT']+path[1:]+[f'{s}_fight'],f'{s}_fight',contact_time,
              'A forward defender can meet the designated attacker approach; committing forward sacrifices site hold coverage.',
              engagement=[f'{s}_fight'],contact=f'{s}_fight',arrivals={f'{s}_fight':contact_time},retreat=[f'{s}_hold'])
        route(f'CT-{s}-withdraw','CT','retreat',[f'{s}_hold',f'{s}_rear'],f'{s}_rear',[3,5],
              'Surrender the front hold to survive and retain a recovery option.',retreat=[f'{s}_rear'],phase='defense')
        other='B' if s=='A' else 'A'
        transfer=['CT'] if rot=='deployment' else [hub] if rot=='central' else ['rotation_stairs',hub] if rot=='vertical' else ['transfer']
        route(f'CT-{s}-switch','CT','rotation',[f'{s}_hold',f'{s}_rear']+transfer+[f'{other}_rear',f'{other}_hold'],other,
              [17,19] if rot=='deployment' else [10,12] if rot in ('exposed','vertical') else [7,9],
              'Switch via deployment after a long withdrawal.' if rot=='deployment' else 'Cross the exposed transfer; site control can interrupt reinforcement.' if rot=='exposed' else 'Switch through owned rear/control space, giving up the original hold.',
              engagement=[f'{s}_hold',f'{other}_hold'] if rot=='exposed' else [],elevation='level_change' if rot=='vertical' else 'ground',
              information=['defender_hub'] if rot=='central' else [],retreat=[f'{s}_rear'],phase='rotation',
              requirements=[{'place':'rotation_stairs','state':'controlled','effect':'Level-change access must remain secure.'}] if rot=='vertical' else [])

    if rules['retake']=='shared_regroup':place('retake_union','retake_staging','Combine surviving defenders before choosing which occupied site to recover.')
    for s in ('A','B'):
        dest='retake_union' if rules['retake']=='shared_regroup' else f'{s}_retake'
        route(f'CT-{s}-regather','CT','connector_access',[f'{s}_rear',dest],dest,[5,7],
              'Join surviving defenders for coordinated recovery.' if rules['retake']=='shared_regroup' else 'Preserve independent site recovery.',phase='retake')
        entry=f'{s}_entry' if rules['retake']=='front_recovery' else f'{s}_side'
        route(f'CT-{s}-recover','CT','defensive_access',[dest,entry],s,[6,8],
              'Reclear the lost main entry; no free rear retake shortcut.' if rules['retake']=='front_recovery' else 'Reenter via a secondary engagement after regrouping.',
              engagement=[entry],angle=0 if rules['retake']=='front_recovery' else 180,retreat=[dest],phase='retake')
        engagements=[]
        for pid in (f'{s}_entry',f'{s}_side'):
            rid=f'engage-{s}-{pid}';engagements.append(rid)
            relation(rid,f'{s}_hold',pid,'engagement','Site defender must decide which entry sector to cover.')
        rid=f'retake-engage-{s}';engagements.append(rid)
        relation(rid,dest,entry,'engagement','Retake players challenge the occupied entry from the specified recovery direction.')
        staging=[p for p in primary[s]['places'][1:-1]+secondary[s]['places'][1:-1] if places[p]['kind']=='attacker_staging']
        brief['sites'].append({'id':s,'objective':s,'approach_staging':sorted(set(staging)),
            'entry_zones':[f'{s}_entry',f'{s}_side'],'defender_access':[f'{s}_hold'],'fallback':[f'{s}_rear'],
            'retake':[dest],'engagements':engagements})

    t_assign=[{'intent':f'Prepare {s} entry','route':primary[s]['id']} for s in ('A','B')]
    ct_assign=[{'intent':f'Hold {s}','route':f'CT-{s}-deploy','commitment':{
        'tradeoff':cf('Assignment sacrifices other-site and forward-control coverage; switching has a witnessed cost.'),
        'switch_route':f'CT-{s}-switch'}} for s in ('A','B')]
    if has_control:
        owned=ctrl in ('T_owned','CT_owned')
        tpath=['T','control'];ctpath=['CT','control']
        if ctrl=='CT_owned':tpath=['T','A_prep','A_side','A_hold','A_rear','control']
        if ctrl=='T_owned':ctpath=['CT','A_rear','A_hold','A_side','control']
        ttime=[4,6] if ctrl=='T_owned' else [27,29] if ctrl=='CT_owned' else contact_time
        ctime=[4,6] if ctrl=='CT_owned' else [27,29] if ctrl=='T_owned' else contact_time
        for team,path,time in [('T',tpath,ttime),('CT',ctpath,ctime)]:
            row=route(f'{team}-control',''+team,'connector_access' if owned else 'contest',path,'control',time,
                'Owned distribution territory is reached earlier by its owner; invading it requires cleared approaches.' if owned else 'Contest observation/connector choice independently from the site front entries.',
                engagement=[] if owned else ['control'],information=['control'],retreat=[team],
                contact=None if owned else 'control',arrivals={} if owned else {'control':contact_time})
            if owned:row['ownership_arrival_basis']='round_start_targets_with_clearance_condition_for_invader'
        destinations=('A','B') if ctrl in ('contested','vertical','T_owned','CT_owned') else (staged_site,) if ctrl=='optional' else ()
        for s in destinations:relation(f'control-pressure-{s}','control',f'{s}_hold' if ctrl=='CT_owned' else f'{s}_side','control_pressure','Control enables/denies the corresponding site entry or rotation interface.')
        if ctrl in ('contested','vertical'):
            brief['mid_claims'].append({'place':'control','access':{'T':'T-control','CT':'CT-control'},
                'pressure_relationships':[f'control-pressure-{s}' for s in ('A','B')]})
        if owned:brief['control_claims'].append({'place':'control','owner':'T' if ctrl=='T_owned' else 'CT',
            'access':{'T':'T-control','CT':'CT-control'},'effect':cf('Early ownership changes preparation/rotation freedom; enemy access needs territory clearance.')})
        if not owned:
            t_assign.append({'intent':'Contest independent control assignment','route':'T-control'})
            route('CT-control-switch','CT','rotation',['control','CT','A_rear','A_hold'],'A',[11,13],
                  'Abandon the control-space assignment and reinforce one site through deployment.',phase='rotation')
            ct_assign.append({'intent':'Contest control assignment','route':'CT-control','commitment':{
                'tradeoff':cf('Control contest removes a site defender and must be surrendered before reinforcement.'),'switch_route':'CT-control-switch'}})
    brief['deployments']=[{'team':'T','area':'T','assignments':t_assign},{'team':'CT','area':'CT','assignments':ct_assign}]

    if atkrot=='staging' and dep=='shared_staging':switchpoint='shared_prep'
    elif atkrot=='staging' and dep in ('split_recombine','recombine_after_contact'):switchpoint='regroup'
    elif atkrot=='control' and has_control and ctrl!='CT_owned':switchpoint='control'
    else:switchpoint='T'
    for s in ('A','B'):
        p=primary[s]['places'];idx=p.index(switchpoint) if switchpoint in p else 0
        route(f'T-{s}-reset','T','retreat',list(reversed(p[idx:])),switchpoint,[7,9] if idx else [13,15],
              'Keep shared preparation and switch before another commitment.' if idx else 'Yield approach control and redeploy before a target switch.',
              engagement=[f'{s}_fight'],retreat=[switchpoint],rotations=['B' if s=='A' else 'A'],phase='reset')
    # A single conditional flank has a different causal prerequisite, selected
    # by ownership/rotation decisions, not an arbitrary perimeter connector.
    if atkrot=='site_capture':
        flankpath=['A_side','A_hold','A_rear','B_rear','B_hold'];prereq='Capture A defense/rear; A execute stalled; enough round time remains.'
        bypass=['B_fight'];flankinfo=['A_hold'];flanktime=[16,18]
    elif ctrl=='T_owned':
        flankpath=['control','B_prep','B_side','B_hold'];prereq='Retain attacker preparation ownership and confirm B front defenders committed.'
        bypass=['B_entry'];flankinfo=['control'];flanktime=[12,14]
    elif ctrl=='vertical':
        flankpath=['control','control_stairs','B_side','B_hold'];prereq='Win raised control and secure its level-change access before exploitation.'
        bypass=['B_fight'];flankinfo=['control_stairs'];flanktime=[10,12]
    else:
        flankpath=['A_side','A_hold','A_rear','B_rear','B_hold'];prereq='Clear A side and rear; enemy defense transfer is exposed or vacated.'
        bypass=['B_fight'];flankinfo=['A_rear'];flanktime=[20,22] if rot=='deployment' else [14,16]
    route('T-exploit','T','flank',flankpath,'B_hold',flanktime,
          'Exploit specific cleared/controlled space to bypass the original B fight; unavailable as a default opening.',
          engagement=['B_hold'],angle=180,bypass=bypass,information=flankinfo,retreat=[flankpath[0]],phase='conditional_flank',condition=prereq)

    # Unused per-site scaffolding is not a gameplay role. Remove it, rather than
    # accepting a stage/retake label simply because it was allocated by a helper.
    used={p for r in brief['route_intents'] for p in r['places']}|{'T','CT','A','B'}
    brief['places']=[p for p in brief['places'] if p['id'] in used]
    return brief


def finish_proposal(plan):
    """Attach explicit vertical and branch-local witnesses, never new routes."""
    from semantic_pipeline import compare_outcomes
    source=f"Seed {plan['seed']}: branch-local intended outcomes"
    places={p['id']:p for p in plan['places']}
    for r in plan['relationships']:
        if places[r['from']]['kind']=='vertical_transition':
            r.update(purpose='vertical_transition',movement='stairs',direction='two_way')
    # Certificates are derived from existing route intentions between actual
    # divergence/rejoin points. No cycle-local random benefit is invented.
    routes=plan['routes']
    for i,left in enumerate(routes):
        for right in routes[i+1:]:
            if (left['team'],left['phase'])!=(right['team'],right['phase']):continue
            common=set(left['places'])&set(right['places'])
            for start in sorted(common):
                for end in sorted(common-{start}):
                    branches=[]
                    for r in (left,right):
                        a,b=r['places'].index(start),r['places'].index(end)
                        if b<=a:break
                        path=r['places'][a:b+1]
                        values={k:v['value'] for k,v in r['outcome'].items()}
                        # Mid is itself a witnessed contest. Explicit entry
                        # engagements count only within this branch, never
                        # after rejoining or merely because an entry is named.
                        declared=set(values.get('engagement',[]))
                        values.update(destination=end,engagement=[p for p in path[1:-1] if places[p]['kind'] in ('encounter_space','mid_candidate') or p in declared and places[p]['kind'] in ('site_entry','defender_position')],
                                      information=[],defender_bypass=[],retreat_capability=[],rotation_capability=[],
                                      timing=[0,0],entry_angle=0,elevation='ground',engagement_range='medium')
                        branches.append({'places':path,'outcome':{k:fact(v,'design_contract',source) for k,v in values.items()}})
                    if len(branches)!=2 or set(branches[0]['places'][1:-1])&set(branches[1]['places'][1:-1]):continue
                    if compare_outcomes(branches[0]['outcome'],branches[1]['outcome'])['status']=='distinct':
                        plan['cycles'].append({'team':left['team'],'phase':left['phase'],
                            'purpose':'Different witnessed first-contest contexts before rejoining the same preparation.',
                            'purpose_evidence':fact('Branch encounters are explicitly assigned opposing arrivals.','design_contract',source),
                            'branches':branches})
    return plan
