import copy
import json
import unittest
from pathlib import Path
from shapely.geometry import Point
from playable_composition import compile_composition
from p04_comparison_round import build003,build004,validate,frozen_hashes,REVIEW,STRATEGY

class ComparisonRoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads(STRATEGY.read_text())
        cls.programs=[build003(),build004()]
        cls.compiled=[compile_composition(p) for p in cls.programs]
        cls.results=[validate(p,c,cls.plan) for p,c in zip(cls.programs,cls.compiled)]

    def test_frozen_candidates_remain_byte_identical(self):
        self.assertEqual(frozen_hashes(),json.loads((REVIEW/'frozen-001-002.json').read_text()))

    def test_same_strategy_and_scale(self):
        first=json.loads((STRATEGY.parents[2]/'p04-playable-composition-001/composition.json').read_text())
        for p in self.programs:
            self.assertEqual(p['plan_sha256'],first['plan_sha256'])
            self.assertEqual(p['engine_scale'],first['engine_scale'])

    def test_routes_and_player_footprint_are_connected(self):
        for r in self.results:
            self.assertEqual(r['walkable_components'],1)
            self.assertEqual(len(r['strategic_routes']),19)
            self.assertTrue(all(x['path'] and x['player_clearance_connected'] for x in r['strategic_routes'].values()))

    def test_no_unintended_opening_or_site_free_bypass(self):
        for r in self.results:
            self.assertFalse(r['opening_audit']['unintended_openings'])
            self.assertIsNone(r['attacker_CT_access_with_both_sites_blocked'])

    def test_actual_apertures_match_and_entries_remain_distinct(self):
        for r in self.results:
            self.assertEqual(len(r['openings']),16)
            for o in r['openings']:
                self.assertAlmostEqual(o['actual_clear_HU'],o['nominal_HU'])
            for entry in r['entry_sectors'].values():
                self.assertEqual(entry['secondary_delta_degrees'],90)
                self.assertEqual(entry['retake_delta_degrees'],180)

    def test_interfering_building_is_reported(self):
        p=copy.deepcopy(self.programs[0]);p['internal_masses'].append(dict(id='bad_extension',boundary=[[79,70],[81,70],[81,72],[79,72]],height_source_units=160))
        result=validate(p,compile_composition(p),self.plan)
        self.assertIn('Aperture interference: B_main',result['violations'])

    def test_arrival_conflicts_are_not_silently_passed(self):
        for r in self.results:
            self.assertTrue(all(x['same_contact_distance_conflict'] for x in r['arrival_distance_checks']))
            self.assertTrue(r['design_warnings'])
            self.assertFalse(r['visually_accepted'])
            self.assertFalse(r['automatic_composition_generation'])

    def test_defenders_have_contact_visibility_without_spawn_marker_visibility(self):
        for r,c in zip(self.results,self.compiled):
            self.assertTrue(all(c['walkable'].covers(Point(v)) for v in r['defender_positions'].values()))
            for site in ('A','B'):
                self.assertTrue(any(x['site']==site and x['standing_line_to_contact'] for x in r['contact_sightline_checks']))
            self.assertFalse(any(x['standing_line_to_T_spawn_marker'] for x in r['spawn_marker_sightline_checks']))

if __name__=='__main__':unittest.main()
