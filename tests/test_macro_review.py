import unittest

from review_macro_layout import audit, distances, revise


class MacroReviewTests(unittest.TestCase):
    def test_floor_distance_respects_obstacle(self):
        cells = {(0,0),(0,1),(1,1),(2,1),(2,0),(8,8)}
        result = distances(cells, (0,0))
        self.assertEqual(result[(2,0)], 256)
        self.assertNotIn((8,8), result)

    def test_revision_preserves_original_and_model_provenance(self):
        plan = {'design_choices': {'regions': [{'id': 'Area1'}, {'id': 'Area8'}],
                'connections': [{'source': 'Area1', 'target': 'Area8'}]},
                'model_checkpoint_sha256': 'same-model', 'learned_outputs': {'raw': [1,2]}}
        result = revise(plan)
        self.assertEqual(len(plan['design_choices']['regions']), 2)
        self.assertEqual(result['design_choices']['connections'], [])
        self.assertEqual(result['model_checkpoint_sha256'], 'same-model')
        self.assertEqual(result['learned_outputs'], plan['learned_outputs'])
        self.assertFalse(result['design_review']['retraining_performed'])

    def test_crossing_corridors_are_flagged(self):
        points = {'TSpawn': [-512,0,0], 'CTSpawn': [512,0,0],
                  'SiteA': [0,-512,0], 'SiteB': [0,512,0]}
        plan = {'design_choices': {'regions': [{'id': k, 'center': v, 'size': [128,128,256]} for k,v in points.items()],
            'connections': [{'source': 'TSpawn', 'target': 'CTSpawn'},
                            {'source': 'SiteA', 'target': 'SiteB'}], 'corridor_width_units': 128}}
        result = audit(plan)
        self.assertEqual(len(result['nonincident_corridor_overlaps']), 1)
        # Graph components are disconnected, while crossing floor corridors connect them.
        route = next(r for r in result['routes'] if r['from']=='TSpawn' and r['to']=='SiteA')
        self.assertIsNone(route['graph_elbow_centerline_units'])
        self.assertIsNotNone(route['floor_grid_units'])


if __name__ == '__main__':
    unittest.main()
