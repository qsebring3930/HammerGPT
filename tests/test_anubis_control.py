import unittest

from annotate_anubis_control import build_routes


def fixture():
    labels = {'ct': 'CTSideUpper', 'decoy': 'CTSpawn', 't': 'TSpawn',
              'a': 'BombsiteA', 'b': 'BombsiteB'}
    return {
        'nodes': [{'id': key, 'label': label, 'position': [i*100, 0, 0],
                   'nav_area_ids': [i]} for i, (key, label) in enumerate(labels.items())],
        'edges': [{'source': a, 'target': b, 'witnesses': [{'source_nav_area': a, 'target_nav_area': b}],
                   'reverse_edge_exists': False} for a, b in [('ct', 'b'), ('b', 'a'), ('decoy', 'a')]],
        'anchors': [{'id': key, 'classname': classname, 'region_ids': [region],
                     'association': 'nearest_nav_centroid_diagnostic_only'}
                    for key, classname, region in [
                        ('ct_entity', 'info_player_counterterrorist', 'ct'),
                        ('t_entity', 'info_player_terrorist', 't'),
                        ('site_a', 'func_bomb_target', 'a'),
                        ('site_b', 'func_bomb_target', 'b')]],
    }


class AnubisControlTests(unittest.TestCase):
    def test_ct_access_through_other_site_does_not_pass(self):
        routes = {r['title']: r for r in build_routes(fixture())}
        self.assertEqual(routes['CT to A without B']['status'], 'unresolved')
        self.assertEqual(routes['CT to B without A']['region_path'], ['ct', 'b'])

    def test_anchor_association_overrides_spawn_place_name_and_retains_uncertainty(self):
        routes = build_routes(fixture())
        self.assertEqual(routes[0]['start_region'], 'ct')
        self.assertEqual(routes[0]['spawn_anchor_evidence'][0]['association'],
                         'nearest_nav_centroid_diagnostic_only')

    def test_rotation_reverse_direction_not_assumed(self):
        routes = {r['title']: r for r in build_routes(fixture())}
        self.assertEqual(routes['B to A defender rotation']['status'], 'recorded_directed_route')
        self.assertEqual(routes['A to B defender rotation']['status'], 'unresolved')


if __name__ == '__main__':
    unittest.main()
