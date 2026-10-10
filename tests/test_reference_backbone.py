import unittest

from annotate_reference_backbone import build
from review_anubis_control import reviewed
from tests.test_anubis_control import fixture


class ReferenceBackboneTests(unittest.TestCase):
    def test_rejected_independent_access_keeps_diagnostic_but_no_control_targets(self):
        graph = fixture()
        graph.update(map='Example', dataset_role='training')
        result = build(graph)
        route = result['routes'][0]
        self.assertEqual(route['status'], 'unresolved')
        self.assertEqual(route['unrestricted_connectivity_diagnostic']['region_path'], ['ct','b','a'])
        self.assertTrue(all(g['initial_control_target'] is None and not g['supervision_mask']
                            for g in result['place_groups']))
        self.assertFalse(result['training_eligible'])

    def test_reserved_evaluation_reference_rejected(self):
        graph = fixture()
        graph.update(map='Example', dataset_role='reserved_evaluation')
        with self.assertRaises(ValueError):
            build(graph)

    def test_review_enables_only_resolved_context_and_preserves_original_draft(self):
        draft = {'regions': [
            {'initial_control_proposed': 'ct_first', 'supervision_mask': False},
            {'initial_control_proposed': 'unresolved', 'supervision_mask': False}],
            'spatial_subdivision_proposals': [{'supervision_mask': False}],
            'front_proposals': [], 'route_evidence': []}
        result = reviewed(draft)
        self.assertTrue(result['regions'][0]['supervision_mask'])
        self.assertFalse(result['regions'][1]['supervision_mask'])
        self.assertTrue(result['spatial_subdivision_proposals'][0]['supervision_mask'])
        self.assertFalse(draft['regions'][0]['supervision_mask'])
        self.assertFalse(result['model_training_performed'])


if __name__ == '__main__': unittest.main()
