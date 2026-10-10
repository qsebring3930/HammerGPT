import unittest
import networkx as nx
from compare_gameplay_structure import best_route, connected_places, pendant_cycles, site_exchange_symmetry


class StructureTests(unittest.TestCase):
    def test_remote_or_one_way_same_names_are_not_collapsed(self):
        graph = nx.DiGraph([(1,2),(2,1),(2,3),(3,4)])
        nodes = {i: {'label':'Hall'} for i in range(1,5)}
        owner, groups = connected_places(graph,nodes)
        self.assertEqual(owner[1],owner[2])
        self.assertNotEqual(owner[2],owner[3])
        self.assertNotEqual(owner[3],owner[4])
        self.assertEqual(len(groups),3)

    def test_other_site_exclusion_exposes_bad_defender_access(self):
        graph = nx.DiGraph()
        graph.add_weighted_edges_from([('CT','A',1),('A','B',1)])
        self.assertIsNotNone(best_route(graph,['CT'],['B']))
        self.assertIsNone(best_route(graph,['CT'],['B'],['A']))

    def test_cycle_connected_through_one_junction_is_not_through_route(self):
        graph = nx.Graph([('T','J'),('J','A'),('J','X'),('X','Y'),('Y','J')]).to_directed()
        lobes = pendant_cycles(graph,{'T','A'})
        self.assertEqual(lobes,[{'attachment':'J','members':['X','Y'],'cycle_rank':1}])

    def test_site_exchange_fixes_spawns_and_ignores_room_names(self):
        graph=nx.Graph([('T','left'),('T','right'),('left','A'),('right','B'),('CT','A'),('CT','B')]).to_directed()
        terminals={key:[key] for key in ('T','CT','A','B')}
        self.assertTrue(site_exchange_symmetry(graph,terminals))
        graph.add_edge('CT','left')
        graph.add_edge('left','CT')
        self.assertFalse(site_exchange_symmetry(graph,terminals))


if __name__ == '__main__':
    unittest.main()
