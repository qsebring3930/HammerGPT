import copy
import unittest

import networkx as nx
from shapely.geometry import box, mapping

from strategic_floorplan import (canonical_strategy, rasterize, distances,
                                validate_raster_paths, audit_saved)


class StrategicFloorplanTests(unittest.TestCase):
    def graph(self):
        graph=nx.Graph([(0,4),(4,2),(2,1),(1,3),(3,5),(5,0),(4,6),(6,5),(6,1)])
        return graph,{0:'T',1:'CT',2:'A',3:'B'}

    def equivalent(self,a,b):
        return nx.is_isomorphic(a,b,node_match=nx.algorithms.isomorphism.categorical_node_match('role',''))

    def test_connector_subdivision_does_not_create_strategic_novelty(self):
        graph,roles=self.graph();changed=graph.copy()
        changed.remove_edge(4,6);changed.add_edges_from([(4,7),(7,6)])
        self.assertTrue(self.equivalent(canonical_strategy(graph,roles),canonical_strategy(changed,roles)))

    def test_renaming_sites_and_node_ids_does_not_create_novelty(self):
        graph,roles=self.graph();renamed={i:i+30 for i in graph}
        changed=nx.relabel_nodes(graph,renamed)
        swapped={renamed[i]:('B' if r=='A' else 'A' if r=='B' else r) for i,r in roles.items()}
        self.assertTrue(self.equivalent(canonical_strategy(graph,roles),canonical_strategy(changed,swapped)))

    def test_changed_distribution_with_equal_edge_count_is_distinct(self):
        graph,roles=self.graph();changed=graph.copy()
        changed.remove_edge(6,1);changed.add_edge(6,2)
        self.assertEqual(graph.number_of_edges(),changed.number_of_edges())
        self.assertFalse(self.equivalent(canonical_strategy(graph,roles),canonical_strategy(changed,roles)))

    def test_physical_path_detours_around_wall_instead_of_using_euclidean_distance(self):
        floor=box(0,0,1024,1024).difference(box(448,0,576,800))
        safe,mask,xs,ys,index=rasterize(floor)
        mask=validate_raster_paths(safe,mask,xs,ys)
        result,_=distances(mask,index((128,192)))
        self.assertGreater(result[index((896,192))],1500)

    def fixture(self):
        floor=box(0,0,1024,1024)
        return {'nodes':[{'floor':mapping(floor),'center':[512,512,0]}],
                'edges':[],'cover':[],'floor':mapping(floor),
                'spawns':{'T':[[256,256,0],[3000,3000,0]]},'routes':[],'timings':{}}

    def test_bad_individual_spawn_cannot_hide_behind_one_valid_team_spawn(self):
        with self.assertRaisesRegex(ValueError,'spawn_or_terminal_off_floor'):
            audit_saved(self.fixture())

    def test_saved_floor_cannot_silently_differ_from_rendered_components(self):
        candidate=copy.deepcopy(self.fixture());candidate['floor']=mapping(box(0,0,2048,2048))
        with self.assertRaisesRegex(ValueError,'saved_floor_not_component_union'):
            audit_saved(candidate)


if __name__=='__main__':unittest.main()
