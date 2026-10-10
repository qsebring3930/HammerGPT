import copy
import json
import unittest
from shapely.geometry import LineString
from p04_second_composition import build, validate, FIRST, STRATEGY
from playable_composition import compile_composition

class SecondCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=build();cls.c=compile_composition(cls.p)
        cls.r=validate(cls.p,cls.c,json.loads(STRATEGY.read_text()))

    def test_strategy_identical_to_frozen_first(self):
        self.assertEqual(self.p['plan_sha256'],json.loads((FIRST/'composition.json').read_text())['plan_sha256'])

    def test_all_ordered_routes_have_player_clearance(self):
        self.assertEqual(len(self.r['strategic_routes']),19)
        self.assertTrue(all(x['path'] and x['player_clearance_connected'] for x in self.r['strategic_routes'].values()))

    def test_entries_are_observed_distinct_sectors(self):
        for x in self.r['entry_sectors'].values():
            self.assertEqual(x['secondary_delta_degrees'],90)
            self.assertEqual(x['retake_delta_degrees'],180)

    def test_no_hidden_openings_or_site_free_CT_bypass(self):
        self.assertFalse(self.r['opening_audit']['unintended_openings'])
        self.assertIsNone(self.r['attacker_CT_access_with_both_sites_blocked'])

    def test_rear_is_shortest_rotation(self):
        x=self.r['defender_rotation']
        self.assertTrue({'CT_A','CT_B'}.issubset(x['crossed_openings']))
        self.assertLess(x['shortest_path']['length'],x['CT_avoiding_path']['length'])
        self.assertGreater(x['shortest_path']['length'],x['initial_assignment_max_length'])

    def test_aperture_interference_detected(self):
        p=copy.deepcopy(self.p)
        p['internal_masses'].append(dict(id='interference',boundary=[[86,34],[88,34],[88,36],[86,36]],height_source_units=160))
        result=validate(p,compile_composition(p),json.loads(STRATEGY.read_text()))
        self.assertIn('Aperture interference: B_main',result['violations'])

    def test_annotations_cannot_create_floor(self):
        p=copy.deepcopy(self.p);p['annotations']={};p['allocations']=[]
        self.assertTrue(compile_composition(p)['walkable'].equals(self.c['walkable']))

if __name__=='__main__':unittest.main()
