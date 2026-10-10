import unittest

from whole_map_layout import extract, shortest_route, contains


def area(key, x, targets=(), z=0):
    return {'id':key,'hull':0,'movable_mesh_id':0xffffffff,
            'corners':[[x,0,z],[x+64,0,z],[x+64,64,z],[x,64,z]],
            'connections':[{'target':t,'source_edge':1,'target_edge':3} for t in targets]}


def graph(areas, anchors=()):
    return extract({'areas':areas}, {'spatial':{'gameplay_anchors':list(anchors)}})


class WholeMapLayoutTests(unittest.TestCase):
    def test_numeric_boundary_tolerance_is_small(self):
        box = {'min':[0,0,10],'max':[64,64,20]}
        self.assertTrue(contains(box,[32,32,9.9999]))
        self.assertFalse(contains(box,[32,32,9.9999],0))
        self.assertFalse(contains(box,[32,32,9.99]))

    def test_nearby_unconnected_polygons_remain_separate(self):
        result = graph([area(1,0),area(2,80)])
        self.assertEqual(len(result['nodes']),2)
        self.assertEqual(result['edges'],[])

    def test_one_way_link_not_contracted_in_same_bin(self):
        result = graph([area(1,0,[2]),area(2,80)])
        self.assertEqual(len(result['nodes']),2)
        self.assertEqual(len(result['edges']),1)
        self.assertFalse(result['edges'][0]['reverse_edge_exists'])
        self.assertEqual(result['edges'][0]['witnesses'][0]['source_nav_area'],1)

    def test_bidirectional_same_bin_contracted(self):
        result = graph([area(1,0,[2]),area(2,80,[1])])
        self.assertEqual(result['nodes'][0]['nav_area_ids'],[1,2])
        self.assertEqual(result['nodes'][0]['summed_nav_polygon_area_xy'],8192)

    def test_elevation_and_spatial_bins_remain_separate(self):
        result = graph([area(1,0,[2]),area(2,0,[1],z=256)])
        self.assertEqual(len(result['nodes']),2)
        self.assertTrue(all(e['reverse_edge_exists'] for e in result['edges']))
        self.assertEqual(result['edges'][0]['witnesses'][0]['centroid_delta'][2],256)

    def test_objective_uses_bounds_not_decompiled_origin(self):
        objective = {'node_id':'goal','classname':'func_bomb_target','position':[0,0,0],
                     'properties':{},'geometry_bounds':{'min':[600,0,-1],'max':[664,64,64]}}
        spawn = {'node_id':'spawn','classname':'info_player_terrorist',
                 'position':[32,32,1],'properties':{},'geometry_bounds':None}
        result = graph([area(1,0,[2]),area(2,600)],[objective,spawn])
        goal = next(a for a in result['anchors'] if a['id']=='goal')
        self.assertEqual(goal['nav_area_ids'],[2])
        self.assertEqual(goal['position'][0],632)
        route = next(r for r in result['spawn_objective_routes'] if r['team_classname']=='info_player_terrorist')
        self.assertEqual(route['route']['nav_area_path'],[1,2])

    def test_dangling_and_movable_links_excluded(self):
        moving = area(2,80); moving['movable_mesh_id']=7
        result = graph([area(1,0,[2,99]),moving])
        self.assertEqual(result['summary']['nav_areas'],1)
        self.assertEqual(len(result['excluded_links']),2)
        self.assertFalse(result['edges'])

    def test_shortest_route_respects_direction(self):
        from collections import defaultdict
        edges = defaultdict(set,{1:{2}}); centers = {1:[0,0,0],2:[10,0,0]}
        self.assertIsNone(shortest_route({2},{1},edges,centers))
        self.assertEqual(shortest_route({1},{2},edges,centers)['centroid_path_distance_units'],10)


if __name__=='__main__': unittest.main()
