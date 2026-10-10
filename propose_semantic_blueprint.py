"""One authored semantic proposal. Never samples positions or invokes geometry."""
import json
from pathlib import Path

from semantic_pipeline import StrategicPlanner, GameplayValidator, fact, blueprint, compare_outcomes

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/strategic-proposal-001'
SOURCE = 'strategic-proposal-001: proposed design intention, pending human review and physical verification'


def contract(value):
    return fact(value, 'design_contract', SOURCE)


def build_proposal():
    brief = {'name': 'Split commitment / contested exchange', 'places': [],
             'route_intents': [], 'relationships': [], 'sites': [],
             'deployments': [], 'mid_claims': [], 'cycles': [],
             'provenance': {'method': 'Authored semantic proposal compiled by StrategicPlanner; not a trained-model sample.',
                            'references': [
                                'Dust2: separately reviewed Long, Middle and tunnel encounters',
                                'Cache: A Main, B Main and Mid encounters with distinct site-entry chokes',
                                'Train: reviewed Ivy conditional later flank and upper-to-back-B encounter'],
                            'transfer': 'Organizational ideas only; no copied coordinates or measured timings.'}}

    def place(key, name, kind, why):
        brief['places'].append({'id': key, 'name': name, 'kind': kind,
                                'role_evidence': contract(why), 'intention': why})

    place('T', 'T deployment', 'T_spawn', 'Assign separate A preparation, B preparation or Mid contest squads.')
    place('CT', 'CT deployment', 'CT_spawn', 'Choose an A hold, B hold or exposed Mid contest; switching costs time.')
    place('mid_prep', 'T exchange preparation', 'attacker_staging', 'Prepare a Mid fight before choosing a site connector.')
    place('mid', 'Contested exchange', 'mid_candidate', 'Independent team access; ownership pressures side entries at both sites.')
    place('ct_mid', 'CT exchange access', 'connector', 'Separate Mid assignment; does not pass through either site defense position.')
    for s in ('A', 'B'):
        place(s, f'{s} objective', f'{s}_site', 'Objective belongs to an entry/defense/fallback/retake system, not a terminal route.')
        place(f'{s}_prep', f'{s} attacker preparation', 'attacker_staging', 'Stage an execute and retain a retreat before committing.')
        place(f'{s}_front', f'{s} main entry', 'site_entry', 'Primary entry engaging the front site hold.')
        place(f'{s}_side', f'{s} secondary entry', 'site_entry', 'Separate engagement angle reached through Mid control.')
        place(f'{s}_hold', f'{s} defender assignment', 'defender_position', 'Hold site access; choosing it sacrifices immediate control of the other site.')
        place(f'{s}_rear', f'{s} fallback / rotation access', 'fallback', 'Disengage from the front hold and join the defender rotation.')
        place(f'{s}_retake', f'{s} retake preparation', 'retake_staging', 'Assemble a retake after falling back; reenter through a different engagement.')
    place('A_door', 'A execute choke', 'chokepoint', 'Concentrate the direct A approach before an offset entry.')
    place('B_court', 'B forward contest', 'encounter_space', 'A defender may contest attackers before their final site entry.')
    place('B_gate', 'B commitment choke', 'chokepoint', 'Crossing commits the main attack from contested approach into the site.')
    place('A_link', 'Exchange to A side entry', 'connector', 'Mid control bypasses the main A execute choke.')
    place('B_stairs', 'Exchange to B raised access', 'vertical_transition', 'Stairs expose movement before reaching a raised site entry.')
    place('B_gallery', 'B raised entry access', 'connector', 'Trade a slower Mid-dependent attack for elevation and a second entry angle.')
    place('rotate', 'Defender transfer', 'connector', 'Rotate between site fallback systems without granting free Mid control.')

    def route(key, team, purpose, path, destination, timing, engagement, angle=0,
              elevation='ground', bypass=(), information=(), retreat=(), rotations=(),
              phase='opening', why='', alternative=None, condition=None, first=None, arrivals=None):
        values = dict(destination=destination, timing=timing, engagement=engagement,
                      entry_angle=angle, elevation=elevation, defender_bypass=list(bypass),
                      engagement_range='medium', information=list(information),
                      retreat_capability=list(retreat), rotation_capability=list(rotations))
        row = {'id': key, 'team': team, 'phase': phase, 'purpose': purpose, 'places': path,
               'why': why, 'purpose_evidence': contract(why),
               'outcome': {k: contract(v) for k, v in values.items()}}
        if alternative: row['alternative_to'] = alternative
        if condition: row['condition'] = condition
        if first: row['first_contact'] = contract(first)
        if arrivals: row['arrivals'] = {k: contract(v) for k, v in arrivals.items()}
        brief['route_intents'].append(row)

    route('T-A-main', 'T', 'primary_attack', ['T','A_prep','A_door','A_front'], 'A', [17,19],
          ['A execute choke','A front hold'], retreat=['A preparation'], why='Direct execute: preserve utility preparation and avoid a compulsory Mid fight.', first='A_door')
    route('T-A-exchange', 'T', 'secondary_attack', ['T','mid_prep','mid','A_link','A_side'], 'A', [24,26],
          ['Exchange contest','A side hold'], angle=90, bypass=['A front choke'],
          information=['Exchange occupancy'], retreat=['Exchange preparation'], rotations=['B raised access'],
          why='Win Mid to pressure A from another angle; pay for that freedom with an extra contested fight.', alternative='T-A-main', first='mid')
    route('T-B-main', 'T', 'primary_attack', ['T','B_prep','B_court','B_gate','B_front'], 'B', [18,20],
          ['B forward contest','B main hold'], retreat=['B preparation'],
          why='Contest forward space, then choose whether to commit through the B gate.', first='B_court', arrivals={'B_court':[12,14]})
    route('T-B-raised', 'T', 'secondary_attack', ['T','mid_prep','mid','B_stairs','B_gallery','B_side'], 'B', [26,28],
          ['Exchange contest','B raised entry'], angle=90, elevation='raised', bypass=['B forward contest','B gate'],
          information=['Exchange occupancy'], retreat=['Exchange preparation'], rotations=['A side access'],
          why='A slower elevated B entry bypasses the main B fight; the exposed stairs are its cost.', alternative='T-B-main', first='mid')
    route('T-mid', 'T', 'contest', ['T','mid_prep','mid'], 'Exchange', [11,13], ['Exchange contest'],
          information=['Exchange occupancy'], retreat=['Exchange preparation'], rotations=['A side access','B raised access'],
          why='Obtain connector choice by winning a separate contested assignment.', first='mid')
    route('CT-mid', 'CT', 'contest', ['CT','ct_mid','mid'], 'Exchange', [11,13], ['Exchange contest'],
          information=['Exchange occupancy'], retreat=['CT exchange access'], rotations=['CT deployment'],
          why='Contest Mid independently; this player cannot simultaneously hold a site.', first='mid')
    for s in ('A','B'):
        route(f'CT-{s}-hold','CT','defensive_access',['CT',f'{s}_rear',f'{s}_hold'],s,[8,10],
              [f'{s} front and side defense'],retreat=[f'{s} fallback'],rotations=[f'{s} rear transfer'],
              why=f'Commit to the {s} entry system before attacker arrival.')
        route(f'CT-{s}-fallback','CT','retreat',[f'{s}_hold',f'{s}_rear'],f'{s} fallback',[3,5],
              [f'{s} disengagement'],retreat=[f'{s} rear'],rotations=['Defender transfer'],phase='defense',
              why='Survive a lost site entry and preserve the option to rotate or retake.')
        route(f'CT-{s}-assemble','CT','connector_access',[f'{s}_rear',f'{s}_retake'],f'{s} retake',[3,5],
              [f'{s} retake preparation'],retreat=[f'{s} rear'],phase='retake',why='Assemble before reengaging the planted site.')
        route(f'CT-{s}-retake','CT','defensive_access',[f'{s}_retake',f'{s}_side'],s,[5,7],
              [f'{s} occupied-site retake'],angle=180,retreat=[f'{s} retake preparation'],phase='retake',
              why='Retake through the side interface rather than blindly replaying the lost front hold.')
    route('CT-B-forward','CT','contest',['B_hold','B_gate','B_court'],'B forward space',[12,14],
          ['B forward contest'],retreat=['B hold','B fallback'],phase='opening',
          why='Optional forward information/fight; leaving the hold exposes the secondary entry.',first='B_court',arrivals={'B_court':[12,14]})
    for s,other in [('A','B'),('B','A')]:
        route(f'CT-{s}-to-{other}','CT','rotation',[f'{s}_hold',f'{s}_rear','rotate',f'{other}_rear',f'{other}_hold'],other,[9,11],
              ['Rear transfer','Destination site defense'],retreat=[f'{s} rear',f'{other} rear'],phase='rotation',
              why=f'Abandon the {s} hold to reinforce {other}; rotation does not automatically contest Mid.')
    route('CT-mid-to-A','CT','rotation',['mid','ct_mid','CT','A_rear','A_hold'],'A',[10,12],
          ['Withdraw from Exchange','A reinforcement'],retreat=['CT deployment'],phase='rotation',
          why='Give up Mid control and return through deployment to reinforce A; no universal junction shortcut.')
    route('T-disengage-A','T','retreat',['A_front','A_door','A_prep','T'],'T deployment',[12,14],
          ['A choke withdrawal'],retreat=['A preparation'],rotations=['B main preparation'],phase='later',
          why='If the A execute stalls, retreat to change assignment instead of a free universal cross-connection.')
    route('T-disengage-B','T','retreat',['B_front','B_gate','B_court','B_prep','T'],'T deployment',[13,15],
          ['B contest withdrawal'],retreat=['B preparation'],rotations=['A main preparation'],phase='later',
          why='Preserve a slower site switch by giving up contested B approach space.')
    route('T-late-flank','T','flank',['A_side','A_hold','A_rear','rotate','B_rear','B_hold'],'B defense rear',[16,18],
          ['Cleared A defense','Rear transfer','B rear defense'],angle=180,bypass=['B gate','B raised entry'],
          information=['A rear cleared'],retreat=['A rear'],rotations=['B retake preparation'],phase='later',
          condition='A side and rear have been cleared; direct A attack is stalled; sufficient round time remains.',
          why='Conditional exploitation of cleared defense space, not an opening B route.')

    for s in ('A','B'):
        engagement_ids=[]
        for source,target,label in [(f'{s}_hold',f'{s}_front','front hold'),
                                    (f'{s}_hold',f'{s}_side','side hold'),
                                    (f'{s}_retake',f'{s}_side','retake')]:
            rid=f'engage-{s}-{label}';engagement_ids.append(rid)
            brief['relationships'].append({'id':rid,'from':source,'to':target,'team':'both','phase':'any',
                 'purpose':'engagement','why':f'{s} {label} is a separately specified fight interface.',
                 'purpose_evidence':contract(f'{s} {label}')})
        brief['sites'].append({'id':s,'objective':s,'approach_staging':[f'{s}_prep','mid_prep'],
            'entry_zones':[f'{s}_front',f'{s}_side'],'defender_access':[f'{s}_hold'],
            'fallback':[f'{s}_rear'],'retake':[f'{s}_retake'],'engagements':engagement_ids})
        brief['relationships'].append({'id':f'mid-pressure-{s}','from':'mid','to':f'{s}_side','team':'both','phase':'any',
            'purpose':'control_pressure','why':f'Mid ownership enables/denies the secondary {s} entry.',
            'purpose_evidence':contract(f'{s} secondary entry access')})
    brief['deployments']=[{'team':'T','area':'T','assignments':[
        {'intent':'Prepare A execute','route':'T-A-main'}, {'intent':'Contest B approach','route':'T-B-main'},
        {'intent':'Contest Exchange','route':'T-mid'}]},
        {'team':'CT','area':'CT','assignments':[
            {'intent':f'Hold {s}','route':f'CT-{s}-hold','commitment':{
                'tradeoff':contract(f'Sacrifices immediate other-site and Mid presence; switching takes 9–11 target seconds.'),
                'switch_route':f'CT-{s}-to-{other}'}} for s,other in [('A','B'),('B','A')]]}]
    brief['deployments'][1]['assignments'].append({'intent':'Contest Exchange','route':'CT-mid','commitment':{
        'tradeoff':contract('Leaves one fewer site defender; withdrawing to reinforce A costs a target 10–12 seconds.'),
        'switch_route':'CT-mid-to-A'}})
    brief['mid_claims']=[{'place':'mid','access':{'T':'T-mid','CT':'CT-mid'},
                          'pressure_relationships':['mid-pressure-A','mid-pressure-B']}]
    plan=StrategicPlanner().generate(brief)
    for p in plan['places']:
        if p['kind']=='chokepoint':
            p['access_constraint']={'effect':contract('Commitment through a localized entry with a defender engagement; exact clearance awaits geometry.'),
                'relationships':[r['id'] for r in plan['relationships'] if p['id'] in (r['from'],r['to'])]}
    for r in plan['relationships']:
        if r['from']=='B_stairs':r.update(purpose='vertical_transition',movement='stairs',direction='two_way')
    # Intended cycles are named here; do not invent a tactical benefit simply
    # because an undirected graph algorithm finds additional closed paths.
    plan['intended_cycles']=[
        {'purpose':'A main versus Exchange side pressure','branches':['T-A-main','T-A-exchange'],
         'difference':'Extra Mid contest, slower arrival and a separate A entry; converge at the site system, not a shared corridor.'},
        {'purpose':'B main versus raised entry','branches':['T-B-main','T-B-raised'],
         'difference':'Forward contest versus exposed stairs and elevation; require physical entry-angle verification.'},
        {'purpose':'Lost-site recovery','branches':['CT-A-to-B','CT-B-to-A'],
         'difference':'A rear transfer enables an assignment switch after surrendering the original hold; not a second opening attack.'}]
    return StrategicPlanner().plan(plan)


def write_proposal():
    plan=build_proposal();report=GameplayValidator().validate(plan)
    OUT.mkdir(parents=True,exist_ok=True)
    for name,value in [('strategic-plan.json',plan),('validation.json',report)]:
        (OUT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')
    (OUT/'technical-blueprint.md').write_text(blueprint(plan,report),encoding='utf-8')
    routes={r['id']:r for r in plan['routes']}
    comparisons={key:compare_outcomes(routes[a]['outcome'],routes[b]['outcome']) for key,a,b in
                 [('A approaches','T-A-main','T-A-exchange'),('B approaches','T-B-main','T-B-raised')]}
    (OUT/'approach-comparisons.json').write_text(json.dumps(comparisons,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'contract_passed':report['passed'],
                      'blocking_codes':sorted({i['code'] for i in report['issues']}),
                      'geometry_generated':False,'learned_model_sample':False}))


if __name__=='__main__':write_proposal()
