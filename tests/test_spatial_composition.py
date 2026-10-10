import copy
import json
import unittest
from pathlib import Path

from semantic_pipeline import SpatialEmbedder,GameplayValidator
from spatial_validation import spatial_equivalence,equivalence_controls,validate_preservation,transformed_copy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/spatial-composition-001'


class SpatialCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads((OUT/'P01/original-strategy.json').read_text())
        cls.e=json.loads((OUT/'P01/E2-embedding.json').read_text())

    def test_transform_controls_are_rejected_as_novelty(self):
        for control in equivalence_controls(self.e):
            with self.subTest(control=control['control']):self.assertTrue(control['equivalent'])

    def test_different_seed_is_not_an_exact_coordinate_transform(self):
        other=json.loads((OUT/'P01/E4-embedding.json').read_text())
        self.assertFalse(spatial_equivalence(self.e,other)['rigid_or_scaled_copy'])

    def test_stale_strategy_cannot_be_composed(self):
        report=GameplayValidator().validate(self.plan);changed=copy.deepcopy(self.plan);changed['name']='changed'
        with self.assertRaises(ValueError):SpatialEmbedder().compose(changed,report,1)

    def test_relationship_loss_fails_preservation(self):
        e=copy.deepcopy(self.e);e['relationship_ids'].pop()
        self.assertIn('relationship_coverage',[i['code'] for i in validate_preservation(self.plan,e)['issues']])

    def test_same_entry_direction_does_not_preserve_an_angle_alternative(self):
        e=copy.deepcopy(self.e);base=e['routes']['T-A-main'];alt=e['routes']['T-A-alt'];alt['points'][-3:]=copy.deepcopy(base['points'][-3:])
        self.assertIn('entry_directions_noncoincident',[i['code'] for i in validate_preservation(self.plan,e)['issues']])

    def test_independent_mid_access_damage_is_detected(self):
        e=json.loads((OUT/'P01/E1-embedding.json').read_text())
        self.assertIn('independent_mid_access',[i['code'] for i in validate_preservation(self.plan,e)['issues']])

    def test_transfer_exposure_is_not_certified_by_a_dotted_line(self):
        p=json.loads((OUT/'P10/original-strategy.json').read_text());e=json.loads((OUT/'P10/E2-embedding.json').read_text())
        self.assertIn('exposed_transfer_not_bypassed',[i['code'] for i in validate_preservation(p,e)['issues']])

    def test_same_site_system_has_multiple_subspaces_not_independent_squares(self):
        self.assertEqual(self.e['anchors']['A_entry']['region'],'A')
        self.assertEqual(self.e['anchors']['A_side']['region'],'A')
        self.assertEqual(self.e['anchors']['A_hold']['region'],'A')
        self.assertEqual(self.e['anchors']['A']['region'],'A')

    def test_flank_does_not_create_a_new_physical_transfer_chord(self):
        p=json.loads((OUT/'P04/E1-embedding.json').read_text())
        self.assertTrue(p['segments']['A_rear|B_rear']['shared_implementation_with'])
        self.assertNotIn('A_rear|B_rear',p['travel_envelopes'])

    def test_schematic_pass_never_claims_verified_tactical_quality(self):
        r=validate_preservation(self.plan,self.e)
        self.assertTrue(r['schematic_checks_passed'])
        self.assertFalse(r['semantic_claims_fully_verified']);self.assertFalse(r['stage_4_authorized'])

    def test_all_sixteen_exist_and_none_is_floor_geometry(self):
        for pid in ('P01','P04','P06','P10'):
            for i in range(1,5):
                e=json.loads((OUT/pid/f'E{i}-embedding.json').read_text())
                self.assertEqual(e['stage'],'spatial_embedding')
                self.assertFalse(e['passed'])
                self.assertNotIn('floor_mesh',e)
        self.assertFalse(list(OUT.rglob('*.vmap')))


if __name__=='__main__':unittest.main()
