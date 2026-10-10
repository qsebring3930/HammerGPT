import copy
import json
import unittest

from semantic_pipeline import (FACTS,StrategicPlanner,GameplayValidator,SpatialEmbedder,
    GeometryGenerator,compare_outcomes,fact,check_generation_policy)


def outcome(destination='A',**changes):
    values={'destination':destination,'timing':[10,11],'engagement':['front'],
            'entry_angle':0,'elevation':0,'defender_bypass':[], 'engagement_range':'medium',
            'information':[],'retreat_capability':['staging'],'rotation_capability':['B']}
    values.update(changes)
    return {k:fact(v,'design_contract','Explicit synthetic test contract') for k,v in values.items()}


def valid_brief():
    brief={'name':'Supported contract fixture','places':[],'relationships':[],'routes':[],
           'sites':[],'deployments':[],'cycles':[],'mid_claims':[]}
    kinds={'T':'T_spawn','CT':'CT_spawn','stage':'attacker_staging','mid':'mid_candidate'}
    for s in ('A','B'):
        kinds.update({s:f'{s}_site',f'entry{s}':'site_entry',f'def{s}':'defender_position',
                      f'fall{s}':'fallback',f'retake{s}':'retake_staging'})
    for key,kind in kinds.items():brief['places'].append({'id':key,'kind':kind,'role_evidence':fact(kind,'design_contract','fixture')})
    def route(key,team,purpose,path,phase='opening',effect=None):
        ids=[]
        for i,(a,b) in enumerate(zip(path,path[1:])):
            rid=f'{key}:{i}';ids.append(rid)
            brief['relationships'].append({'id':rid,'from':a,'to':b,'purpose':purpose,
                'team':team,'phase':phase,'why':'Stated fixture gameplay assignment',
                'purpose_evidence':fact(purpose,'design_contract','fixture')})
        row={'id':key,'team':team,'purpose':purpose,'phase':phase,'places':path,'relationships':ids,
             'purpose_evidence':fact(purpose,'design_contract','fixture'),'outcome':effect or outcome()}
        brief['routes'].append(row)
        return row
    route('attackA','T','primary_attack',['T','stage','mid','defA','entryA'])
    route('attackB','T','primary_attack',['T','stage','mid','defB','entryB'],effect=outcome('B'))
    route('Tmid','T','contest',['T','stage','mid'],effect=outcome('mid',timing=[8,9]))
    route('CTmid','CT','contest',['CT','mid'],effect=outcome('mid',timing=[8,9]))
    for s in ('A','B'):
        route(f'defend{s}','CT','defensive_access',['CT','mid',f'def{s}'],effect=outcome(s))
        route(f'fallback{s}','CT','retreat',[f'def{s}',f'fall{s}'],'defense',outcome(f'fall{s}'))
        route(f'retake{s}','CT','defensive_access',[f'retake{s}',f'entry{s}'],'retake',outcome(s))
        engagements=[]
        for start in (f'def{s}',f'retake{s}'):
            rid=f'engagement:{start}';engagements.append(rid)
            brief['relationships'].append({'id':rid,'from':start,'to':f'entry{s}',
                'purpose':'engagement','team':'both','phase':'any','why':'Attack/defense or retake engagement interface',
                'purpose_evidence':fact('engagement','design_contract','fixture')})
        brief['sites'].append({'id':s,'objective':s,'approach_staging':['stage'],'entry_zones':[f'entry{s}'],
            'defender_access':[f'def{s}'],'fallback':[f'fall{s}'],'retake':[f'retake{s}'],'engagements':engagements})
        brief['relationships'].append({'id':f'pressure{s}','from':'mid','to':s,'purpose':'control_pressure',
            'team':'both','phase':'any','why':f'Mid control pressures the {s} entry system',
            'purpose_evidence':fact(s,'design_contract','fixture')})
    route('rotate','CT','rotation',['defA','mid','defB'],'rotation',outcome('B'))
    route('rotate_back','CT','rotation',['defB','mid','defA'],'rotation',outcome('A'))
    brief['deployments']=[{'team':'T','area':'T','assignments':[{'intent':'attack A','route':'attackA'},{'intent':'attack B','route':'attackB'}]},
        {'team':'CT','area':'CT','assignments':[
            {'intent':'defend A','route':'defendA','commitment':{'switch_route':'rotate','tradeoff':fact('Leave A hold to rotate to B','design_contract','fixture')}},
            {'intent':'defend B','route':'defendB','commitment':{'switch_route':'rotate_back','tradeoff':fact('Leave B hold to rotate to A','design_contract','fixture')}}]}]
    brief['mid_claims']=[{'place':'mid','access':{'T':'Tmid','CT':'CTmid'},'pressure_relationships':['pressureA','pressureB']}]
    return brief


class SemanticPipelineTests(unittest.TestCase):
    def validate(self,brief):
        return GameplayValidator().validate(StrategicPlanner().plan(brief))

    def test_supported_contract_can_pass_without_complexity_score(self):
        report=self.validate(valid_brief())
        self.assertTrue(report['passed'],report['issues'])
        self.assertTrue(report['validated_roles']['mid']['validated'])
        self.assertFalse(report['statistics_are_quality_scores'])

    def test_planner_refuses_coordinate_first_brief(self):
        brief=valid_brief();brief['places'][0]['center']=[0,0,0]
        with self.assertRaisesRegex(ValueError,'spatial geometry'):StrategicPlanner().plan(brief)

    def test_intentions_expand_to_team_phase_purpose_relationships_without_positions(self):
        brief={'name':'Intent proposal','places':[{'id':'T','kind':'T_spawn'},{'id':'lobby','kind':'attacker_staging'}],
            'route_intents':[{'id':'deploy','team':'T','phase':'opening','purpose':'deployment_assignment',
                'places':['T','lobby'],'why':'Prepare A approach without committing into its entry',
                'purpose_evidence':fact('deployment','design_contract','fixture'),'outcome':outcome()}]}
        plan=StrategicPlanner().generate(brief)
        self.assertEqual(plan['relationships'][0]['purpose'],'deployment_assignment')
        self.assertEqual(plan['routes'][0]['relationships'],['deploy:relationship:0'])

    def test_defensive_assignment_requires_a_commitment_not_only_a_name(self):
        brief=valid_brief();brief['deployments'][1]['assignments'][0].pop('commitment')
        self.assertIn('unvalidated_defender_commitment',[i['code'] for i in self.validate(brief)['issues']])

    def test_generic_connection_reason_is_not_a_purpose(self):
        brief=valid_brief();brief['relationships'][0]['purpose']='connection'
        with self.assertRaises(ValueError):StrategicPlanner().plan(brief)

    def test_different_path_names_do_not_create_strategic_distinction(self):
        self.assertEqual(compare_outcomes(outcome(),outcome())['status'],'equivalent')

    def test_every_supported_tactical_dimension_can_make_a_distinct_choice(self):
        alternatives={'destination':'B','timing':[15,16],'engagement':['different front'],'entry_angle':90,
            'elevation':128,'defender_bypass':['long defender'],'engagement_range':'long',
            'information':['B entry seen'],'retreat_capability':['safe lobby'],'rotation_capability':['A','B']}
        for dimension,value in alternatives.items():
            with self.subTest(dimension=dimension):
                result=compare_outcomes(outcome(),outcome(**{dimension:value}))
                self.assertEqual(result['status'],'distinct');self.assertIn(dimension,result['changes'])

    def test_unknown_fights_cannot_be_declared_equivalent(self):
        a,b=outcome(),outcome();a['information']=fact();b['information']=fact()
        self.assertEqual(compare_outcomes(a,b)['status'],'unverified')

    def test_reordering_capabilities_is_not_a_new_tactical_option(self):
        self.assertEqual(compare_outcomes(outcome(information=['A','B']),outcome(information=['B','A']))['status'],'equivalent')

    def test_uncertain_overlapping_timing_is_not_equivalence(self):
        self.assertEqual(compare_outcomes(outcome(timing=[2,20]),outcome(timing=[10,30]))['status'],'unverified')

    def test_angle_comparison_handles_circular_wraparound(self):
        self.assertEqual(compare_outcomes(outcome(entry_angle=355),outcome(entry_angle=5))['status'],'equivalent')

    def test_nearby_central_hallway_cannot_self_label_mid(self):
        brief=valid_brief();brief['mid_claims'][0]['pressure_relationships']=['pressureA']
        report=self.validate(brief)
        self.assertFalse(report['validated_roles']['mid']['validated'])

    def test_mid_requires_independent_team_access_and_plausible_arrivals(self):
        brief=valid_brief();next(r for r in brief['routes'] if r['id']=='CTmid')['outcome']['timing']=fact([25,26],'design_contract','fixture')
        self.assertIn('invalid_mid_claim',[i['code'] for i in self.validate(brief)['issues']])

    def test_site_endpoint_and_spawn_endpoint_are_not_complete_systems(self):
        brief=valid_brief();brief['sites']=[];brief['deployments']=[]
        codes={i['code'] for i in self.validate(brief)['issues']}
        self.assertIn('incomplete_site_system',codes);self.assertIn('spawn_as_endpoint',codes)

    def add_loop(self,brief,meaningful=False):
        brief['places'].append({'id':'detour','kind':'connector'})
        for rid,a,b in [('detour1','stage','detour'),('detour2','detour','mid')]:
            brief['relationships'].append({'id':rid,'from':a,'to':b,'purpose':'secondary_attack','team':'T','phase':'opening',
                'why':'Candidate alternate','purpose_evidence':fact('alternative','design_contract','fixture')})
        brief['cycles'].append({'team':'T','phase':'opening','purpose':'gain different information before reconnecting',
            'purpose_evidence':fact('information choice','design_contract','fixture'),
            'branches':[{'places':['stage','mid'],'outcome':outcome('mid')},
                        {'places':['stage','detour','mid'],'outcome':outcome('mid',information=['B entrance observed']) if meaningful else outcome('mid')}]})

    def test_reconnecting_loop_without_branch_local_change_is_rejected(self):
        brief=valid_brief();self.add_loop(brief)
        self.assertIn('unjustified_reconnecting_cycle',[i['code'] for i in self.validate(brief)['issues']])

    def test_loop_with_supported_information_difference_is_accepted(self):
        brief=valid_brief();self.add_loop(brief,True)
        report=self.validate(brief);self.assertTrue(report['passed'],report['issues'])

    def test_cycle_cannot_use_an_opposite_direction_or_team_witness(self):
        for mismatch in ('direction','team'):
            brief=valid_brief();self.add_loop(brief,True)
            edge=next(r for r in brief['relationships'] if r['id']=='detour2')
            if mismatch=='direction':edge['from'],edge['to']=edge['to'],edge['from']
            else:edge['team']='CT'
            with self.subTest(mismatch=mismatch):
                report=self.validate(brief)
                if mismatch=='direction':self.assertIn('unjustified_reconnecting_cycle',[i['code'] for i in report['issues']])
                else:self.assertFalse(report['cycle_purposes'])

    def test_opposing_team_and_phase_union_is_not_an_alternate_choice(self):
        brief=valid_brief();self.add_loop(brief)
        next(r for r in brief['relationships'] if r['id']=='detour2')['phase']='retake'
        report=self.validate(brief)
        self.assertTrue(report['union_cycles_diagnostic'])
        self.assertFalse(report['cycle_purposes'])

    def test_authored_proposal_is_coordinate_free_and_contract_only(self):
        from propose_semantic_blueprint import build_proposal
        plan=build_proposal();report=GameplayValidator().validate(plan)
        self.assertTrue(report['passed'],report['issues'])
        self.assertTrue(report['validated_roles']['mid']['validated'])
        for route in plan['routes']:
            self.assertTrue(all(v['status']=='design_contract' for v in route['outcome'].values()))
        self.assertTrue(all(c['status']=='distinct' for c in report['route_comparisons']))

    def test_route_equivalence_collapses_an_extra_geometric_branch(self):
        brief=valid_brief();self.add_loop(brief)
        base=next(r for r in brief['routes'] if r['id']=='attackA')
        alt=copy.deepcopy(base);alt['id']='alternateA';alt['purpose']='secondary_attack';alt['alternative_to']='attackA'
        alt['places']=['T','stage','detour','mid','defA','entryA']
        alt['relationships']=[base['relationships'][0],'detour1','detour2',*base['relationships'][2:]]
        brief['routes'].append(alt);report=self.validate(brief)
        self.assertTrue(any({'attackA','alternateA'}<=set(c) for c in report['strategic_route_classes']))
        self.assertIn('redundant_alternative',[i['code'] for i in report['issues']])

    def test_tactical_change_after_rejoin_cannot_justify_a_useless_detour(self):
        brief=valid_brief();self.add_loop(brief)
        next(r for r in brief['routes'] if r['id']=='attackA')['outcome']=outcome(entry_angle=90)
        self.assertIn('unjustified_reconnecting_cycle',[i['code'] for i in self.validate(brief)['issues']])

    def test_embedding_rejects_a_changed_plan_even_with_old_pass_report(self):
        plan=StrategicPlanner().plan(valid_brief());report=GameplayValidator().validate(plan)
        plan['name']='changed'
        with self.assertRaises(ValueError):SpatialEmbedder().embed(plan,report,[])

    def test_relative_embedding_preserves_relationships(self):
        plan=StrategicPlanner().plan(valid_brief());report=GameplayValidator().validate(plan)
        rules=[{'a':p['id'],'b':'mid','relation':'same_level'} for p in plan['places'] if p['id']!='mid']
        rules+=[{'a':'A','b':'B','relation':'east_of'}]
        result=SpatialEmbedder().embed(plan,report,rules)
        self.assertGreater(result['positions']['A'][0],result['positions']['B'][0])
        self.assertEqual(set(result['relationship_ids']),{r['id'] for r in plan['relationships']})

    def test_geometry_pause_prevents_backend_from_running(self):
        calls=[]
        with self.assertRaises(RuntimeError):GeometryGenerator().generate({}, {}, {},lambda *args:calls.append(args))
        self.assertEqual(calls,[])

    def test_legacy_generation_is_disabled(self):
        with self.assertRaises(RuntimeError):check_generation_policy(legacy=True)

    def test_five_rejected_layouts_fail_for_structural_semantic_reasons(self):
        from benchmark_semantics import ROOT,rejected_plan
        for i in range(1,6):
            path=ROOT/f'output/preference-round-002/candidate-{i}/layout.json'
            report=GameplayValidator().validate(rejected_plan(json.loads(path.read_text()),path))
            with self.subTest(radar=i):
                self.assertFalse(report['passed'])
                codes={r['code'] for r in report['issues']}
                self.assertTrue({'incomplete_site_system','spawn_as_endpoint','invalid_mid_claim','unjustified_reconnecting_cycle'}<=codes)

    def test_train_reviewed_ivy_flank_is_not_reclassified_as_opening(self):
        from benchmark_semantics import reference_analysis
        rows=reference_analysis('train')['routes']
        flank=next(r for r in rows if r['id']=='T-B-3')
        self.assertEqual(flank['phase'],'conditional_later_flank');self.assertFalse(flank['opening_role_validated'])

    def test_references_have_distinct_observed_organizations_without_fabricated_timing(self):
        from benchmark_semantics import reference_analysis,reference_plan
        references=[reference_analysis(n) for n in ('dust2','anubis','cache','train','cobblestone')]
        self.assertEqual(len({r['observed_context_signature'] for r in references}),5)
        for reference in references:
            self.assertGreater(reference['distinct_context_opportunity_pairs'],0)
            self.assertTrue(all(r['outcome']['timing']['status']=='proxy' for r in reference['routes']))
            report=GameplayValidator().validate(reference_plan(reference))
            self.assertFalse(report['passed'])  # Masked source facts cannot authorize geometry.


if __name__=='__main__':unittest.main()
