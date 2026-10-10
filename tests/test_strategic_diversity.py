import copy
import json
import unittest
from unittest.mock import patch

from semantic_pipeline import StrategicPlanner,GameplayValidator,digest
from strategic_similarity import strategic_signature,compare_strategies
from benchmark_strategic_diversity import CONDITIONS,SEEDS


def rewrite(value,mapping):
    if isinstance(value,dict):return {mapping.get(k,k):rewrite(v,mapping) for k,v in value.items()}
    if isinstance(value,list):return [rewrite(v,mapping) for v in value]
    if isinstance(value,str):return mapping.get(value,value)
    return value


class StrategicDiversityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans=[StrategicPlanner().propose(c,s) for (_,c),s in zip(CONDITIONS,SEEDS)]

    def test_repeat_seed_and_condition_is_deterministic(self):
        self.assertEqual(digest(self.plans[0]),digest(StrategicPlanner().propose(CONDITIONS[0][1],SEEDS[0])))

    def test_ids_and_human_names_supply_no_novelty(self):
        plan=self.plans[0]
        ids=[p['id'] for p in plan['places']]+[r['id'] for r in plan['routes']]+[r['id'] for r in plan['relationships']]
        mapping={pid:f'anonymous_{i}' for i,pid in enumerate(ids) if pid not in ('A','B','T','CT')}
        other=rewrite(plan,mapping)
        for p in other['places']:p['name']='a completely new name';p['intention']='a rewritten description'
        other['name']='New title';other['seed']=999;other['sampled_rules']={}
        other['starting_condition']={'human label':'different'}
        self.assertEqual(strategic_signature(plan),strategic_signature(other))

    def test_swapping_sites_supplies_no_novelty(self):
        plan=self.plans[0];mapping={}
        ids=[p['id'] for p in plan['places']]+[r['id'] for r in plan['routes']]+[r['id'] for r in plan['relationships']]
        for pid in ids:
            if pid=='A' or pid.startswith('A_'):mapping[pid]='B'+pid[1:]
            elif pid=='B' or pid.startswith('B_'):mapping[pid]='A'+pid[1:]
            elif '-A-' in pid:mapping[pid]=pid.replace('-A-','-B-')
            elif '-B-' in pid:mapping[pid]=pid.replace('-B-','-A-')
        other=rewrite(plan,mapping)
        for p in other['places']:
            if p['kind']=='A_site':p['kind']='B_site'
            elif p['kind']=='B_site':p['kind']='A_site'
        self.assertEqual(strategic_signature(plan),strategic_signature(other))

    def test_equivalent_duplicate_route_supplies_no_novelty(self):
        plan=self.plans[0];other=copy.deepcopy(plan)
        route=copy.deepcopy(next(r for r in plan['routes'] if r['purpose']=='primary_attack'))
        route['id']='duplicate-main';other['routes'].append(route)
        self.assertEqual(strategic_signature(plan),strategic_signature(other))

    def test_invalid_mid_and_redundant_alternative_still_rejected(self):
        plan=copy.deepcopy(self.plans[0]);plan['mid_claims'][0]['pressure_relationships']=[]
        self.assertIn('invalid_mid_claim',[i['code'] for i in GameplayValidator().validate(plan)['issues']])
        plan=copy.deepcopy(self.plans[0]);alt=next(r for r in plan['routes'] if r.get('alternative_to'))
        base=next(r for r in plan['routes'] if r['id']==alt['alternative_to']);alt['outcome']=copy.deepcopy(base['outcome'])
        self.assertIn('redundant_alternative',[i['code'] for i in GameplayValidator().validate(plan)['issues']])

    def test_mid_pressure_label_cannot_invent_a_missing_secondary_access(self):
        report=GameplayValidator().validate(self.plans[15])
        self.assertFalse(report['passed'])
        self.assertIn('invalid_mid_claim',[i['code'] for i in report['issues']])

    def test_territory_ownership_needs_separated_arrival_witnesses(self):
        plan=copy.deepcopy(self.plans[5]);claim=plan['control_claims'][0]
        route=next(r for r in plan['routes'] if r['id']==claim['access']['T'])
        route['outcome']['timing']['value']=[4,6]
        self.assertIn('invalid_territory_control',[i['code'] for i in GameplayValidator().validate(plan)['issues']])

    def test_contact_needs_opponent_arrival(self):
        plan=copy.deepcopy(self.plans[0])
        for route in plan['routes']:
            if route['team']=='CT':route['arrivals']={}
        self.assertIn('unsupported_first_contact',[i['code'] for i in GameplayValidator().validate(plan)['issues']])

    def test_batch_is_coordinate_free_and_stages_three_four_never_called(self):
        with patch('semantic_pipeline.SpatialEmbedder.embed',side_effect=AssertionError('embedding forbidden')),patch('semantic_pipeline.GeometryGenerator.generate',side_effect=AssertionError('geometry forbidden')):
            for (_,condition),seed in zip(CONDITIONS,SEEDS):
                plan=StrategicPlanner().propose(condition,seed)
                StrategicPlanner().plan(plan) # recursively rejects spatial keys
                GameplayValidator().validate(plan)

    def test_survivors_differ_in_relationship_families_not_only_names(self):
        surviving=[p for p in self.plans if GameplayValidator().validate(p)['passed']]
        self.assertGreaterEqual(len(surviving),10)
        self.assertGreaterEqual(len({json.dumps(strategic_signature(p),sort_keys=True) for p in surviving}),10)
        result=compare_strategies(self.plans[0],self.plans[3])
        self.assertFalse(result['same_strategic_signature'])
        self.assertIn('control_function',result['changed_families'])
        self.assertIn('rotation',result['changed_families'])

    def test_purpose_free_split_branches_are_not_rescued_to_meet_survivor_count(self):
        report=GameplayValidator().validate(self.plans[7])
        self.assertFalse(report['passed'])
        self.assertIn('unjustified_reconnecting_cycle',[i['code'] for i in report['issues']])


if __name__=='__main__':unittest.main()
