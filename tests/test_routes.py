from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_routes import build_graph


def area(key, x, links):
    return {'id': key, 'hull': 0, 'movable_mesh_id': 0xffffffff,
            'corners': [[x, 0, 0], [x + 1, 0, 0], [x + 1, 1, 0], [x, 1, 0]],
            'connections': [{'target': target} for target in links]}


def volume(name, low, high):
    return {'classname': 'env_cs_place', 'properties': {'place_name': name},
            'geometry_bounds': {'min': [low, -1, -1], 'max': [high, 2, 2]}}


class RouteTests(unittest.TestCase):
    def test_unknown_path_and_one_way_are_retained(self):
        nav = {'areas': [area(1, 0, [2]), area(2, 5, [3]), area(3, 10, [])], 'ladder_count': 0}
        reference = {'spatial': {'gameplay_anchors': [volume('TSpawn', 0, 2), volume('BombsiteA', 10, 12)]}}
        graph = build_graph(nav, reference)
        self.assertEqual(graph['summary']['nav_areas_labeled'], 2)
        self.assertEqual(len(graph['edges']), 2)
        self.assertTrue(all(not e['reverse_edge_exists'] for e in graph['edges']))
        self.assertEqual(graph['example_routes'][0]['nav_area_path'], [1, 2, 3])

    def test_disconnected_nearby_areas_do_not_create_edges(self):
        nav = {'areas': [area(1, 0, []), area(2, 1, [])], 'ladder_count': 0}
        reference = {'spatial': {'gameplay_anchors': [volume('Middle', -1, 5)]}}
        graph = build_graph(nav, reference)
        self.assertEqual(len(graph['nodes']), 2)
        self.assertEqual(graph['edges'], [])

    def test_same_label_one_way_is_not_collapsed(self):
        nav = {'areas': [area(1, 0, [2]), area(2, 1, [])], 'ladder_count': 0}
        reference = {'spatial': {'gameplay_anchors': [volume('Middle', -1, 5)]}}
        graph = build_graph(nav, reference)
        self.assertEqual(len(graph['nodes']), 2)
        self.assertEqual(len(graph['edges']), 1)

    def test_bidirectional_same_label_is_collapsed(self):
        nav = {'areas': [area(1, 0, [2]), area(2, 1, [1])], 'ladder_count': 0}
        reference = {'spatial': {'gameplay_anchors': [volume('Middle', -1, 5)]}}
        self.assertEqual(len(build_graph(nav, reference)['nodes']), 1)


if __name__ == '__main__':
    unittest.main()
