import copy
import json
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch
from semantic_pipeline import digest
from playable_composition import compile_composition
from procedural_p04 import ROOT,generate,local_rules,arrangement,run_batch
from procedural_p04_checks import validate

OUT=ROOT/'output/p04-procedural-001'

class ProceduralP04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=json.loads((ROOT/'config/p04-procedural-v3.json').read_text())
        cls.plan=json.loads((ROOT/cls.cfg['strategy']).read_text())
        cls.saved={s:json.loads((OUT/f'r3/seed-{s}/composition.json').read_text()) for s in [104,208,312,416]}
        # Independent regeneration, without importing any authored layout builder.
        with patch('p04_comparison_round.build003',side_effect=AssertionError('Authored layout imported')),patch('p04_comparison_round.build004',side_effect=AssertionError('Authored layout imported')):
            cls.regenerated=generate(cls.plan,416,cls.cfg)

    def test_exact_seed_reproduction(self):
        self.assertEqual(digest(self.regenerated),digest(self.saved[416]))
        for seed in self.saved:
            record=json.loads((OUT/f'r3/seed-{seed}/reproducibility.json').read_text())
            self.assertTrue(record['same_seed_same_composition'])
            self.assertEqual(record['first_sha256'],digest(self.saved[seed]))
            self.assertEqual(record['first_sha256'],record['second_sha256'])

    def test_unchanged_strategy_is_required(self):
        changed=copy.deepcopy(self.plan);changed['name']='A different strategy'
        with self.assertRaises(ValueError):generate(changed,416,self.cfg)
        self.assertTrue(all(p['plan_sha256']==digest(self.plan) for p in self.saved.values()))

    def test_macro_stream_is_separate_from_local_dimensions(self):
        other=copy.deepcopy(self.cfg);other['court_width_choices']=[22]
        sizes={s:local_rules(s,416,self.cfg)[1] for s in ('A','B')}
        changed_sizes={s:local_rules(s,416,other)[1] for s in ('A','B')}
        left=arrangement(416,self.cfg,sizes);right=arrangement(416,other,changed_sizes)
        for key in ('axis','B_facing_relationship','rotations','depth_offsets','routing_order'):
            self.assertEqual(left[key],right[key])

    def test_macro_variation_is_not_only_whole_layout_rotation(self):
        # Different relative site-facing angles cannot result from rotating or
        # mirroring the whole plan. This is variation evidence, not a quality score.
        orientations=[p['decision_log'][0]['choices']['rotations'] for p in self.saved.values()]
        differences={(x['B']-x['A'])%4 for x in orientations}
        self.assertIn(0,differences);self.assertTrue(1 in differences or 3 in differences)

    def test_overlong_connectors_are_not_emitted_as_floor(self):
        cap=self.cfg['maximum_spawn_connector_plan_length']
        rejected=0
        for p in self.saved.values():
            space_ids={x['id'] for x in p['spaces']}
            for decision in p['decision_log']:
                if decision['stage']!='circulation':continue
                if decision['status']=='placed':self.assertLessEqual(decision['length_plan_units'],cap)
                elif decision['status']=='rejected_length':
                    rejected+=1;self.assertGreater(decision['length_plan_units'],cap)
                    self.assertNotIn(decision['team']+'_'+decision['site']+'_circulation',space_ids)
        self.assertGreater(rejected,0)

    def test_complete_candidate_passes_physical_checks_but_not_timing(self):
        p=self.saved[416];r=validate(self.plan,p,compile_composition(p),self.cfg)
        self.assertFalse(r['violations']);self.assertEqual(r['walkable_components'],1)
        self.assertTrue(all(x['player_clearance_connected'] for x in r['strategic_routes'].values()))
        self.assertFalse(r['timing_verified']);self.assertFalse(r['gameplay_quality_accepted'])
        self.assertTrue(r['warnings']);self.assertIsNone(r['attacker_CT_access_with_both_sites_blocked'])

    def test_failed_generation_cases_remain_rejected(self):
        for seed in (104,208,312):
            p=self.saved[seed];r=validate(self.plan,p,compile_composition(p),self.cfg)
            self.assertTrue(p['composition_errors']);self.assertTrue(r['violations'])

    def test_original_failures_are_regression_cases(self):
        for seed,reason in [(104,'Non-rear rotation shortcut'),(208,'Wrong observed alt entry: B')]:
            p=json.loads((OUT/f'r1/seed-{seed}/composition.json').read_text())
            cfg=json.loads((OUT/'r1/configuration.json').read_text())
            r=validate(self.plan,p,compile_composition(p),cfg)
            self.assertIn(reason,r['violations'])

    def test_attempt_revisions_cannot_be_overwritten(self):
        args=Namespace(config=ROOT/'config/p04-procedural-v3.json',seeds=ROOT/'config/p04-procedural-seeds.json',output=OUT,revision='r3')
        with self.assertRaises(ValueError):run_batch(args)

if __name__=='__main__':unittest.main()
