"""Four explicit stages. Tactical facts are contracts/evidence, not graph labels.

Validation certifies stated strategic contracts, not actual CS2 fun or balance.
Unknown observations block geometry. Coordinates never enter StrategicPlanner.
"""
import copy
from enum import Enum
import hashlib
import itertools
import json
import math
from pathlib import Path

import networkx as nx

ROOT=Path(__file__).resolve().parent


class PlaceKind(str,Enum):
    T_SPAWN='T_spawn'
    CT_SPAWN='CT_spawn'
    A_SITE='A_site'
    B_SITE='B_site'
    STAGING='attacker_staging'
    ENTRY='site_entry'
    DEFENSE='defender_position'
    FALLBACK='fallback'
    RETAKE='retake_staging'
    MID='mid_candidate'
    CONNECTOR='connector'
    ENCOUNTER='encounter_space'
    CHOKE='chokepoint'
    VERTICAL='vertical_transition'


class Purpose(str,Enum):
    DEPLOY='deployment_assignment'
    PRIMARY='primary_attack'
    SECONDARY='secondary_attack'
    DEFENSE='defensive_access'
    ROTATE='rotation'
    CONTEST='contest'
    CONNECT='connector_access'
    RETREAT='retreat'
    FLANK='flank'
    VERTICAL='vertical_transition'
    ENGAGE='engagement'
    PRESSURE='control_pressure'


FACTS=('destination','timing','engagement','entry_angle','elevation','defender_bypass',
       'engagement_range','information','retreat_capability','rotation_capability')
SUPPORTED={'reviewed','observed','design_contract'}
COORDINATE_KEYS={'position','center','coordinates','floor','polygon','xyz','xy','x','y','z','width'}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def check_generation_policy(legacy=False):
    policy=json.loads((ROOT/'generation-policy.json').read_text())
    if policy['geometry_paused'] or (legacy and policy['legacy_spatial_sampler_disabled']):
        raise RuntimeError('Floorplan generation is paused: semantic validation must precede embedding/geometry.')


def fact(value=None,status='unknown',source=None):
    return {'value':value,'status':status,'source':str(source) if source is not None else None}


def supported(value):
    return isinstance(value,dict) and value.get('status') in SUPPORTED and bool(value.get('source')) and value.get('value') is not None


class StrategicPlanner:
    """Compile a typed gameplay brief; inputs describe intentions, not positions.

    Every relationship specifies team, phase and a tactical purpose. A route is
    an ordered sequence of these relationships plus its tactical outcome. Sites
    and deployments are structured objects, not end-node roles.
    """
    def plan(self,brief):
        def no_coordinates(value):
            if isinstance(value,dict):
                if COORDINATE_KEYS & value.keys():raise ValueError('Strategic brief cannot contain spatial geometry.')
                for v in value.values():no_coordinates(v)
            elif isinstance(value,list):
                for v in value:no_coordinates(v)
        no_coordinates(brief)
        result=copy.deepcopy(brief)
        result.setdefault('places',[]);result.setdefault('relationships',[]);result.setdefault('routes',[])
        result.setdefault('sites',[]);result.setdefault('deployments',[]);result.setdefault('cycles',[])
        result.setdefault('mid_claims',[]);result.setdefault('brief',{'contest_gap_seconds':4,'latest_initial_contest_seconds':45})
        places={p['id']:p for p in result['places']}
        if len(places)!=len(result['places']):raise ValueError('Duplicate strategic place identity.')
        for p in places.values():PlaceKind(p['kind'])
        ids=set()
        for r in result['relationships']:
            if r['id'] in ids:raise ValueError('Duplicate relationship identity.')
            ids.add(r['id']);Purpose(r['purpose'])
            if r['from'] not in places or r['to'] not in places:raise ValueError('Relationship references missing place.')
            if not r.get('team') or not r.get('phase') or not r.get('why'):
                raise ValueError('Connection requires team, phase and tactical purpose explanation.')
        result['stage']='strategic_plan';result['schema_version']=1
        return result

    def generate(self,brief):
        """Expand gameplay route intentions into typed relationships.

        This is an explicit semantic-contract proposal mechanism, not a trained
        model. Intentions specify deployment/phase/waypoints/outcomes; spatial
        proximity and generic complexity quotas never choose connections.
        """
        result=copy.deepcopy(brief);intents=result.pop('route_intents',[])
        result.setdefault('routes',[]);result.setdefault('relationships',[])
        for intent in intents:
            route=copy.deepcopy(intent);route['relationships']=[]
            for index,(a,b) in enumerate(zip(route['places'],route['places'][1:])):
                rid=f"{route['id']}:relationship:{index}"
                result['relationships'].append({'id':rid,'from':a,'to':b,
                    'team':route['team'],'phase':route['phase'],'purpose':route['purpose'],
                    'why':route.get('why',''), 'purpose_evidence':route.get('purpose_evidence',fact())})
                route['relationships'].append(rid)
            result['routes'].append(route)
        return self.plan(result)

    def propose(self,starting_condition,seed):
        """Sample composable gameplay rules, not a coordinate/floor template."""
        from semantic_organizations import organization_brief,finish_proposal
        return finish_proposal(self.generate(organization_brief(starting_condition,seed)))


def compare_outcomes(a,b,timing_tolerance=2,angle_tolerance=30):
    """No geometric path IDs or route names participate in equivalence.

    Equivalence requires *all* outcome dimensions to be supported and close.
    One supported meaningful difference proves distinction. Missing facts never
    establish equivalence. Overlapping uncertain timing intervals are not equal.
    """
    different=[];same=[];unknown=[]
    for name in FACTS:
        left,right=a.get(name),b.get(name)
        if not supported(left) or not supported(right):unknown.append(name);continue
        lv,rv=left['value'],right['value']
        if name=='timing':
            lo,hi=map(float,lv);otherlo,otherhi=map(float,rv)
            if lo>hi or otherlo>otherhi:raise ValueError('Invalid timing interval.')
            gap=max(lo,otherlo)-min(hi,otherhi)
            if gap>timing_tolerance:different.append(name)
            elif max(hi,otherhi)-min(lo,otherlo)<=timing_tolerance:same.append(name)
            else:unknown.append(name)
        elif name=='entry_angle':
            delta=abs((float(lv)-float(rv)+180)%360-180)
            uncertainty=float(left.get('uncertainty',0))+float(right.get('uncertainty',0))
            if delta-uncertainty>angle_tolerance:different.append(name)
            elif delta+uncertainty<=angle_tolerance:same.append(name)
            else:unknown.append(name)
        elif name=='elevation' and isinstance(lv,(int,float)) and isinstance(rv,(int,float)):
            if abs(lv-rv)>=64:different.append(name)
            elif lv==rv:same.append(name)
            else:unknown.append(name)
        else:
            # These values are semantic identities/capabilities with provenance.
            if name in ('defender_bypass','information','retreat_capability','rotation_capability'):
                def capability_set(v):
                    return {json.dumps(i,sort_keys=True) for i in v} if isinstance(v,list) else {json.dumps(v,sort_keys=True)}
                equal=capability_set(lv)==capability_set(rv)
            else:equal=lv==rv
            if equal:same.append(name)
            else:different.append(name)
    return {'status':'distinct' if different else 'equivalent' if not unknown else 'unverified',
            'changes':different,'same':same,'unknown':unknown}


class GameplayValidator:
    def validate(self,plan):
        places={p['id']:p for p in plan['places']}
        relationships={r['id']:r for r in plan['relationships']}
        routes={r['id']:r for r in plan['routes']}
        issues=[];comparisons=[];roles={};first_contacts=[]
        def issue(code,subject,detail,status='invalid'):
            issues.append({'code':code,'subject':subject,'status':status,'detail':detail})
        network=nx.Graph();network.add_nodes_from(places)
        for relation in relationships.values():
            if relation['purpose'] not in (Purpose.ENGAGE.value,Purpose.PRESSURE.value):
                network.add_edge(relation['from'],relation['to'])
            if not supported(relation.get('purpose_evidence')):
                issue('unsupported_connection_purpose',relation['id'],'A reason string does not validate tactical purpose.','unverified')
            if relation['purpose']==Purpose.VERTICAL.value:
                if relation.get('movement') not in ('stairs','ramp','drop','boost') or relation.get('direction') not in ('one_way','two_way'):
                    issue('invalid_vertical_transition',relation['id'],'Movement type and direction are required.')
        for route in routes.values():
            path=route.get('places',[]);relations=route.get('relationships',[])
            if len(path)<2 or len(relations)!=len(path)-1:
                issue('invalid_route_witness',route['id'],'Route must identify every ordered, purposeful relationship.');continue
            for i,rid in enumerate(relations):
                rel=relationships.get(rid)
                if not rel or (rel['from'],rel['to'])!=(path[i],path[i+1]) or rel['team'] not in (route['team'],'both') or rel['phase'] not in (route['phase'],'any'):
                    issue('route_relationship_mismatch',route['id'],f'Invalid directed team/phase witness {rid}.')
            if route.get('purpose') not in [p.value for p in Purpose]:issue('generic_route',route['id'],'A primary/secondary/rotation/etc. purpose is required.')
            if route['purpose'] in ('primary_attack','secondary_attack') and places.get(path[-1],{}).get('kind') in ('A_site','B_site'):
                issue('site_as_endpoint',route['id'],'Attack ends at an entry/engagement interface, not at the objective object.')
            if route['purpose']=='flank' and not route.get('condition'):
                issue('unconditional_flank',route['id'],'State when the flank is available or useful.')
            if not supported(route.get('purpose_evidence')):issue('unsupported_route_purpose',route['id'],'Purpose requires evidence or an explicit design contract.','unverified')
            for name in FACTS:
                if not supported(route.get('outcome',{}).get(name)):
                    issue('unknown_tactical_outcome',route['id'],name,'unverified')
            if route.get('alternative_to'):
                base=routes.get(route['alternative_to'])
                if not base:issue('missing_primary_route',route['id'],'Alternative has no identified comparison route.')
                else:
                    result=compare_outcomes(base.get('outcome',{}),route.get('outcome',{}));comparisons.append({'routes':[base['id'],route['id']],**result})
                    if result['status']!='distinct':issue('redundant_alternative' if result['status']=='equivalent' else 'unproven_alternative',route['id'],result,result['status'])
            elif route['purpose']=='secondary_attack':issue('uncompared_secondary_route',route['id'],'Secondary attack must identify its primary alternative.')
            contact=route.get('first_contact')
            if supported(contact) and contact['value'] in path:
                first_contacts.append({'route':route['id'],'place':contact['value'],'status':contact['status']})
        # Collapse equivalent paths conservatively with complete-link grouping;
        # timing tolerance is not transitive, so union-find would be misleading.
        equivalence_classes=[]
        for route in routes.values():
            bucket=next((b for b in equivalence_classes if all(
                routes[r]['team']==route['team'] and routes[r]['phase']==route['phase'] and
                compare_outcomes(routes[r].get('outcome',{}),route.get('outcome',{}))['status']=='equivalent' for r in b)),None)
            if bucket is None:equivalence_classes.append([route['id']])
            else:bucket.append(route['id'])
        for team,kind in [('T','T_spawn'),('CT','CT_spawn')]:
            deployment=next((d for d in plan['deployments'] if d['team']==team),None)
            if not deployment or places.get(deployment.get('area'),{}).get('kind')!=kind:
                issue('spawn_as_endpoint',team,'Missing deployment-area object and assignment divergence.');continue
            assignments=deployment.get('assignments',[])
            if len({a.get('intent') for a in assignments})<2:issue('no_deployment_decision',team,'At least two distinct strategic assignments are required.')
            for assignment in assignments:
                route=routes.get(assignment.get('route'))
                if not route or route['team']!=team or route['places'][0]!=deployment['area']:
                    issue('invalid_deployment_assignment',team,'Assignment needs its own valid outgoing route witness.')
                if team=='CT':
                    commitment=assignment.get('commitment',{})
                    switch=routes.get(commitment.get('switch_route'))
                    if not route or not supported(commitment.get('tradeoff')) or not switch or switch['purpose']!='rotation' or switch['places'][0]!=route['places'][-1] or not supported(switch.get('outcome',{}).get('timing')):
                        issue('unvalidated_defender_commitment',assignment.get('intent'),'State the sacrifice and a witnessed switch/rotation cost.','unverified')
            for a,b in itertools.combinations(assignments,2):
                ra,rb=routes.get(a.get('route')),routes.get(b.get('route'))
                if ra and rb:
                    distinction=compare_outcomes(ra.get('outcome',{}),rb.get('outcome',{}))
                    if distinction['status']!='distinct':
                        issue('duplicate_deployment_assignment',team,'Renaming assignments does not create a tactical deployment choice.',distinction['status'])
        for site,kind in [('A','A_site'),('B','B_site')]:
            contract=next((s for s in plan['sites'] if s['id']==site),None)
            if not contract or places.get(contract.get('objective'),{}).get('kind')!=kind:
                issue('incomplete_site_system',site,'Missing objective with surrounding gameplay components.');continue
            fields={'approach_staging':'attacker_staging','entry_zones':'site_entry','defender_access':'defender_position',
                    'fallback':'fallback','retake':'retake_staging'}
            for field,expected in fields.items():
                values=contract.get(field,[])
                if not values or any(places.get(v,{}).get('kind')!=expected for v in values):
                    issue('incomplete_site_system',site,f'{field} must identify typed places.')
            engagements=contract.get('engagements',[])
            if len(engagements)<2 or any(relationships.get(r,{}).get('purpose')!='engagement' for r in engagements):
                issue('site_missing_engagement_relationships',site,'Entry/defender and retake/occupant engagement relationships are required.')
            for role,purpose,starts,ends in [
                ('defense','defensive_access',None,contract.get('defender_access',[])),
                ('fallback','retreat',contract.get('defender_access',[]),contract.get('fallback',[])),
                ('retake','defensive_access',contract.get('retake',[]),contract.get('entry_zones',[]))]:
                if not any(r['purpose']==purpose and r['places'][-1] in ends and (starts is None or r['places'][0] in starts) for r in routes.values()):
                    issue('site_missing_phase_path',site,role)
        for p in places.values():
            if p['kind']=='mid_candidate':
                claim=next((m for m in plan['mid_claims'] if m['place']==p['id']),None)
                mid_issues=[]
                if not claim:mid_issues.append('no control/contest contract')
                else:
                    arrivals=[]
                    for team in ('T','CT'):
                        route=routes.get(claim.get('access',{}).get(team))
                        deployment=next((d for d in plan['deployments'] if d['team']==team),{})
                        if not route or route['team']!=team or route['places'][0]!=deployment.get('area') or route['places'][-1]!=p['id'] or any(
                            places.get(k,{}).get('kind') in ('A_site','B_site','CT_spawn' if team=='T' else 'T_spawn') for k in route['places']):
                            mid_issues.append(f'{team} lacks independent access')
                        elif supported(route.get('outcome',{}).get('timing')):arrivals.append(route['outcome']['timing']['value'])
                        else:mid_issues.append(f'{team} arrival timing unknown')
                    if len(arrivals)==2:
                        envelope=max(v[1] for v in arrivals)-min(v[0] for v in arrivals)
                        if envelope>plan['brief']['contest_gap_seconds'] or max(v[1] for v in arrivals)>plan['brief']['latest_initial_contest_seconds']:
                            mid_issues.append('opening contest timing outside declared brief')
                    pressure=[relationships.get(i,{}) for i in claim.get('pressure_relationships',[])]
                    destinations={r.get('to') for r in pressure if r.get('from')==p['id'] and r.get('purpose')=='control_pressure' and supported(r.get('purpose_evidence'))
                                  and places.get(r.get('to'),{}).get('kind') in ('A_site','B_site','site_entry','defender_position','retake_staging')}
                    if len(destinations)<2:mid_issues.append('control does not unlock/pressure multiple meaningful destinations')
                    if plan.get('require_pressure_witnesses'):
                        for destination in destinations:
                            if not any(p['id'] in route['places'] and destination in route['places'] and
                                       route['places'].index(p['id'])<route['places'].index(destination)
                                       for route in routes.values()):
                                mid_issues.append('claimed pressure lacks a witnessed access/engagement consequence')
                roles[p['id']]={'claimed':'Mid','validated':not mid_issues,'reasons':mid_issues}
                if mid_issues:issue('invalid_mid_claim',p['id'],mid_issues)
            if p['kind'] in ('encounter_space','chokepoint','attacker_staging'):
                roles.setdefault(p['id'],{'claimed':p['kind'],'validated':False})
                witnessed=supported(p.get('role_evidence'))
                uses=[r for r in routes.values() if p['id'] in r.get('places',[])]
                reasons=[]
                if p['kind']=='attacker_staging':
                    if not any(r['team']=='T' and r['purpose'] in ('primary_attack','secondary_attack') and p['id'] in r['places'][1:-1] for r in uses):
                        reasons.append('no attacker preparation-to-entry route')
                elif p['kind']=='encounter_space':
                    windows=[]
                    for team in ('T','CT'):
                        arrivals=[r.get('arrivals',{}).get(p['id']) for r in uses if r['team']==team]
                        evidence=next((v for v in arrivals if supported(v)),None)
                        if evidence:windows.append(evidence['value'])
                        else:reasons.append(f'{team} local contest arrival unverified')
                    if len(windows)==2 and max(v[1] for v in windows)-min(v[0] for v in windows)>plan['brief']['contest_gap_seconds']:
                        reasons.append('local contest arrivals outside declared timing brief')
                elif p['kind']=='chokepoint':
                    constraint=p.get('access_constraint',{})
                    if not supported(constraint.get('effect')) or not constraint.get('relationships') or any(
                        rid not in relationships or p['id'] not in (relationships[rid]['from'],relationships[rid]['to']) for rid in constraint.get('relationships',[])):
                        reasons.append('no witnessed local access constraint')
                witnessed=witnessed and not reasons
                roles[p['id']]['validated']=witnessed
                roles[p['id']]['reasons']=reasons
                if not witnessed:issue('unsupported_place_role',p['id'],[p['kind'],*reasons],'unverified')
        for claim in plan.get('control_claims',[]):
            owner=claim.get('owner');pid=claim.get('place');access=claim.get('access',{})
            windows={}
            for team in ('T','CT'):
                route=routes.get(access.get(team));deployment=next((d for d in plan['deployments'] if d['team']==team),{})
                if not route or route['team']!=team or route['places'][0]!=deployment.get('area') or route['places'][-1]!=pid:
                    issue('invalid_territory_control',pid,f'{team} needs a witnessed arrival route.');continue
                arrival=route.get('outcome',{}).get('timing')
                if not supported(arrival):issue('invalid_territory_control',pid,f'{team} arrival unknown.','unverified')
                else:windows[team]=arrival['value']
            if owner not in ('T','CT') or not supported(claim.get('effect')):
                issue('invalid_territory_control',pid,'Owner and supported tactical consequence required.')
            elif len(windows)==2 and windows[owner][1]+plan['brief']['contest_gap_seconds']>=windows['CT' if owner=='T' else 'T'][0]:
                issue('invalid_territory_control',pid,'Claimed early ownership is not supported by separated arrival targets.')
        for route in routes.values():
            contact=route.get('first_contact')
            if supported(contact):
                pid=contact['value']
                opponent='CT' if route['team']=='T' else 'T'
                if not any(other['team']==opponent and pid in other.get('places',[]) and
                           supported(other.get('arrivals',{}).get(pid)) for other in routes.values()):
                    # Older source observations may omit local arrival supervision.
                    if plan.get('require_contact_witnesses'):
                        issue('unsupported_first_contact',route['id'],'Opponent local arrival witness is missing.','unverified')
        # Every independent cycle needs branch-local outcomes. A tactical
        # difference *after* the branches rejoin cannot justify the detour.
        cycle_results=[]
        # A union of opposing-team/opening/retake intents is not an actor's
        # choice network. Diagnose that union, validate available choices per
        # actor and phase; phase='any' participates in every declared phase.
        contexts={(r['team'],r['phase']) for r in routes.values()}
        contextual_cycles=[]
        for team,phase in sorted(contexts):
            available=nx.Graph()
            for r in relationships.values():
                if r['team'] in (team,'both') and r['phase'] in (phase,'any') and r['purpose'] not in ('engagement','control_pressure'):
                    available.add_edge(r['from'],r['to'])
            for cycle in nx.cycle_basis(available):contextual_cycles.append((team,phase,cycle))
        for actor,active_phase,cycle in contextual_cycles:
            edges={frozenset(e) for e in zip(cycle,cycle[1:]+cycle[:1])}
            proof=None
            for certificate in plan['cycles']:
                branches=certificate.get('branches',[])
                if len(branches)!=2:continue
                paths=[b.get('places',[]) for b in branches]
                if any(len(path)<2 for path in paths) or paths[0][0]!=paths[1][0] or paths[0][-1]!=paths[1][-1]:continue
                if set(paths[0][1:-1])&set(paths[1][1:-1]):continue
                coverage={frozenset(e) for path in paths for e in zip(path,path[1:])}
                if coverage!=edges:continue
                team,phase=certificate.get('team'),certificate.get('phase')
                if team!=actor or phase!=active_phase:continue
                # An undirected cycle is only a diagnostic. Its tactical
                # branches must actually be traversable by this actor/phase.
                if any(not any(r['from']==a and r['to']==b and
                    r['team'] in (team,'both') and r['phase'] in (phase,'any') and
                    r['purpose'] not in ('engagement','control_pressure')
                    for r in relationships.values())
                    for path in paths for a,b in zip(path,path[1:])):continue
                result=compare_outcomes(branches[0].get('outcome',{}),branches[1].get('outcome',{}))
                if result['status']=='distinct' and certificate.get('purpose') and supported(certificate.get('purpose_evidence')):
                    proof={'purpose':certificate['purpose'],'changes':result['changes'],'branches':paths}
                    break
            cycle_results.append({'team':actor,'phase':active_phase,'places':cycle,'status':'purpose_validated' if proof else 'unjustified','proof':proof})
            if not proof:issue('unjustified_reconnecting_cycle',cycle,'Rejoining branches have no supported branch-local tactical benefit.')
        convergences=[]
        for a,b in itertools.combinations(routes.values(),2):
            shared=[p for p in a.get('places',[])[1:] if p in b.get('places',[])[1:]]
            if shared:convergences.append({'routes':[a['id'],b['id']],'shared_places':shared})
        return {'stage':'gameplay_validation','plan_sha256':digest(plan),'passed':not issues,
                'issues':issues,'route_comparisons':comparisons,'strategic_route_classes':equivalence_classes,
                'validated_roles':roles,'cycle_purposes':cycle_results,'convergences':convergences,
                'union_cycles_diagnostic':[c for c in nx.cycle_basis(network)],
                'cycle_scope':'Declared team/phase availability; physical availability across phases still requires verification.',
                'first_contact_opportunities':first_contacts,
                'rotations':[r['id'] for r in routes.values() if r['purpose']=='rotation'],
                'scope':'Strategic contract validation only. No claim of simulated combat/competitive quality.',
                'statistics_are_quality_scores':False}


class SpatialEmbedder:
    def compose(self,plan,validation,seed=None,*,space_program=None):
        if not validation['passed'] or validation['plan_sha256']!=digest(plan):
            raise ValueError('Composition requires passing validation of this exact strategic plan.')
        if space_program is None:
            raise ValueError('The failed patch/travel-band sampler is retired. Provide an explicit space/mass/opening program; batch generation awaits visual review.')
        if space_program.get('plan_sha256')!=digest(plan):
            raise ValueError('Space program must bind to the unchanged strategic plan.')
        from playable_composition import compile_composition
        return compile_composition(space_program)

    def embed(self,plan,validation,relative_constraints):
        if not validation['passed'] or validation['plan_sha256']!=digest(plan):
            raise ValueError('Embedding requires passing validation of this exact strategic plan.')
        from ortools.sat.python import cp_model
        model=cp_model.CpModel();ids=[p['id'] for p in plan['places']]
        x={i:model.new_int_var(-20,20,f'x_{i}') for i in ids}
        y={i:model.new_int_var(-20,20,f'y_{i}') for i in ids}
        level={i:model.new_int_var(-3,3,f'level_{i}') for i in ids}
        for r in plan['relationships']:
            if r['purpose']=='vertical_transition':
                if r.get('movement')=='drop':model.add(level[r['from']]>=level[r['to']]+1)
                else:model.add(level[r['from']]!=level[r['to']])
            elif r['purpose'] not in ('engagement','control_pressure'):
                model.add(level[r['from']]==level[r['to']])
        for rule in relative_constraints:
            a,b=rule['a'],rule['b'];kind=rule['relation']
            if a not in x or b not in x:raise ValueError('Unknown relative-position place.')
            if kind=='east_of':model.add(x[a]>=x[b]+1)
            elif kind=='north_of':model.add(y[a]>=y[b]+1)
            elif kind=='above':model.add(level[a]>=level[b]+1)
            elif kind=='same_level':model.add(level[a]==level[b])
            else:raise ValueError('Unknown embedding relationship.')
        for a,b in itertools.combinations(ids,2):
            differ=[model.new_bool_var(f'{axis}_{a}_{b}') for axis in ('x','y','level')]
            for flag,values in zip(differ,(x,y,level)):model.add(values[a]!=values[b]).only_enforce_if(flag)
            model.add_bool_or(differ)
        solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=5
        result=solver.solve(model)
        if result not in (cp_model.FEASIBLE,cp_model.OPTIMAL):raise ValueError('Relative embedding infeasible.')
        embedding={'stage':'spatial_embedding','plan_sha256':digest(plan),'positions':{
            i:[solver.value(x[i]),solver.value(y[i]),solver.value(level[i])] for i in ids},
            'relationship_ids':[r['id'] for r in plan['relationships']],
            'relative_constraints':relative_constraints,'units':'abstract placement units; not floor geometry',
            'passed':True}
        for r in plan['relationships']:
            delta=embedding['positions'][r['to']][2]-embedding['positions'][r['from']][2]
            if r['purpose']=='vertical_transition':
                if delta==0 or (r.get('movement')=='drop' and delta>=0):
                    raise ValueError('Embedding violates vertical transition intent.')
            elif r['purpose'] not in ('engagement','control_pressure') and delta!=0:
                raise ValueError('Elevation change lacks an explicit vertical transition.')
        return embedding


class GeometryGenerator:
    def generate(self,plan,validation,embedding,backend):
        check_generation_policy()
        if not validation['passed'] or validation['plan_sha256']!=digest(plan) or not embedding['passed'] or embedding['plan_sha256']!=digest(plan):
            raise ValueError('Geometry requires the exact validated strategy and embedding.')
        if set(embedding['relationship_ids'])!={r['id'] for r in plan['relationships']}:
            raise ValueError('Embedding changed gameplay relationships.')
        return backend(plan,embedding)


def blueprint(plan,report):
    lines=[f"# Strategic blueprint: {plan.get('name','unnamed')}",
           f"Status: {'PASS' if report['passed'] else 'BLOCKED'} — no geometry authorized.",
           '', '## Purposeful routes','']
    names={p['id']:p.get('name',p['id']) for p in plan['places']}
    for r in plan['routes']:
        lines.append(f"- {r['id']} ({r['team']}, {r['phase']}, {r['purpose']}): "+' → '.join(names.get(p,p) for p in r['places']))
    lines+=['','## Tactical distinction and equivalence','']
    for c in report['route_comparisons']:lines.append(f"- {c['routes']}: {c['status']}; changes={c['changes']}; unknown={c['unknown']}.")
    lines+=['','## Route convergence','']
    for c in report['convergences']:lines.append(f"- {c['routes']}: "+', '.join(names.get(p,p) for p in c['shared_places']))
    lines+=['','## First contact and rotations','']
    for contact in report['first_contact_opportunities']:
        lines.append(f"- {contact['route']}: first-contact opportunity at {names.get(contact['place'],contact['place'])} ({contact['status']}).")
    if not report['first_contact_opportunities']:lines.append('No supported first-contact claim; timing/contact remains unverified.')
    lines+=['Rotations: '+(', '.join(report['rotations']) or 'none evidenced'), '', '## Cycle purposes','']
    for c in report['cycle_purposes']:lines.append(f"- {c['places']}: {c['status']} — {c['proof']}.")
    lines+=['','## Blocking findings','']
    grouped={}
    for finding in report['issues']:grouped.setdefault(finding['code'],[]).append(finding)
    for code,findings in grouped.items():
        examples='; '.join(f"{i['subject']}: {i['detail']}" for i in findings[:2])
        lines.append(f"- {code} ({len(findings)} findings): {examples}")
    if report['issues']:lines.append('\nFull per-route evidence gaps are retained in validation.json.')
    return '\n'.join(lines)+'\n'
