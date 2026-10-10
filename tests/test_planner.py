import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from planner import propose, preview


def profile(name, height, span):
    return {'name': name, 'map_source': name+'.vmap', 'nav_source': name+'.nav',
            'measurements': {'nav_center_z_p10_p90_span_units': height,
                             'nav_center_x_span_units': span, 'nav_center_y_span_units': span},
            'top_prop_models': [{'model': 'maps/baked.vmdl'}, {'model': 'models/crate.vmdl'}],
            'top_material_references': [], 'example_routes': []}


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.profiles=[profile('Dust2',219,4000), profile('Cobblestone',260,5000), profile('Vertigo',302,2700)]

    def test_broad_requests_select_different_references(self):
        for prompt, expected in [('medieval fortress','Cobblestone'), ('warm desert courtyard','Dust2'), ('compact vertical industrial map','Vertigo')]:
            self.assertEqual(propose(prompt,self.profiles)['selected_reference']['name'],expected)

    def test_proposal_is_connected_and_assets_reusable(self):
        plan=propose('compact vertical industrial map',self.profiles)
        design=plan['design_choices']
        seen={'TSpawn'}
        while True:
            previous=set(seen)
            for edge in design['connections']:
                if edge['source'] in seen or edge['target'] in seen:
                    seen.update((edge['source'],edge['target']))
            if seen==previous:
                break
        self.assertEqual(seen,{r['id'] for r in design['regions']})
        self.assertEqual(plan['asset_candidates']['props'],[{'model':'models/crate.vmdl'}])
        self.assertFalse(plan['model_training_performed'])
        self.assertIn('proposed blockout',preview(plan))

    def test_empty_request_rejected(self):
        with self.assertRaises(ValueError):
            propose(' ',self.profiles)
