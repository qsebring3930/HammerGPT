import unittest
import hashlib
import json
import networkx as nx
import numpy as np
from extract_gameplay_routes import triangle_distances, combine_paths, candidate_routes, diversity_select, contexts, route_graph, route_family, apply_purpose_reviews, associations


class GameplayRouteTests(unittest.TestCase):
    def test_surface_distance_uses_polygon_interior_and_edges(self):
        triangles=np.array([[[0,0,0],[100,0,0],[0,100,0]]])
        self.assertAlmostEqual(triangle_distances([1,1,2],triangles)[0],2)
        self.assertAlmostEqual(triangle_distances([-3,0,4],triangles)[0],5)

    def test_stacked_floor_projection_does_not_flatten_height(self):
        triangles=np.array([[[0,0,0],[100,0,0],[0,100,0]],[[0,0,100],[100,0,100],[0,100,100]]])
        self.assertEqual(int(np.argmin(triangle_distances([10,10,102],triangles))),1)

    def test_waypoint_return_loop_is_not_route(self):
        self.assertIsNone(combine_paths([1,2,3],[3,2,4]))
        self.assertEqual(combine_paths([1,2],[2,3]),[1,2,3])

    def test_alternative_preserves_direction_and_excludes_other_objective(self):
        net=nx.DiGraph();net.add_weighted_edges_from([(1,2,1),(2,4,1),(1,3,2),(3,4,2),(1,5,1),(5,4,1)])
        candidates=candidate_routes(net,1,[4],[5],[('left',[2]),('right',[3])],[],[])
        self.assertEqual({tuple(c['path']) for c in candidates},{(1,2,4),(1,3,4)})
        self.assertFalse(candidate_routes(net,4,[1],[],[],[],[]))

    def test_tessellation_variants_are_deduplicated_spatially(self):
        centers={1:[0,0,0],2:[100,0,0],3:[200,0,0],4:[100,0,0]}
        candidates=[{'path':[1,2,3],'cost_units':200},{'path':[1,4,3],'cost_units':200}]
        self.assertEqual(len(diversity_select(candidates,centers)),1)

    def test_partial_annotation_does_not_supervise_entire_nav_polygon(self):
        graph={'nodes':[{'id':'r','nav_area_ids':[1]}]}
        annotation={'meetings':[{'id':'M1','kind':'meeting_area','surface_pieces':[{'nav_area_id':1,'corners':[[0,0,0],[5,0,0],[0,5,0]]}]}]}
        meetings,_=contexts(annotation,graph,{1:[50,50,0]})
        self.assertEqual(meetings[0]['nav_area_ids'],[1])
        self.assertEqual(meetings[0]['centroid_supported_nav_ids'],[])

    def test_defender_may_leave_initial_site_context_but_not_reenter(self):
        net=nx.DiGraph();net.add_weighted_edges_from([(1,2,1),(2,3,1),(3,4,1),(4,2,1),(4,5,1)])
        graph=route_graph(net,1,[1,2])
        self.assertTrue(graph.has_edge(1,2))
        self.assertTrue(graph.has_edge(2,3))
        self.assertFalse(graph.has_edge(4,2))
        self.assertTrue(nx.has_path(graph,1,5))

    def test_route_cannot_continue_past_first_objective_contact(self):
        net=nx.DiGraph();net.add_weighted_edges_from([(1,2,1),(2,3,1),(3,4,1)])
        candidates=candidate_routes(net,1,[2,4],[],[('after-goal',[3])],[],[])
        self.assertEqual([c['path'] for c in candidates],[[1,2]])

    def test_local_site_variants_do_not_become_extra_attack_families(self):
        labels={1:'TSpawn',2:'TMain',3:None,4:'TMain',5:'BombsiteA',6:'ElectricalBox',7:'BombsiteA',8:'Ivy'}
        self.assertEqual(route_family([1,2,3,4,5],labels,'A',[]),route_family([1,2,5,6,7],labels,'A',[]))
        self.assertNotEqual(route_family([1,8,5],labels,'A',[]),route_family([1,2,5],labels,'A',[]))

    def test_role_review_matches_exact_source_and_path_not_route_number(self):
        review={'map':'train','source_nav_sha256':'nav','ordered_nav_path_sha256':hashlib.sha256(json.dumps([1,2],separators=(',',':')).encode()).hexdigest(),
                'tactical_role':'conditional_later_flank','opening_attack_target':False,'condition':'A too dangerous','evidence':'user correction'}
        route={'path':[1,2]};other={'path':[1,3]}
        result={'map':'train','nav_sha256':'nav','route_sets':[{'routes':[route,other]}]}
        apply_purpose_reviews(result,[review])
        self.assertFalse(route['opening_attack_target'])
        self.assertEqual(route['tactical_role'],'conditional_later_flank')
        self.assertFalse(other['tactical_role_supervision_mask'])
        result['nav_sha256']='changed'
        apply_purpose_reviews(result,[review])
        self.assertFalse(route['tactical_role_supervision_mask'])

    def test_unlabeled_map_uses_distinct_source_site_designations(self):
        areas={i:{'corners':[[i*100,0,0],[i*100+20,0,0],[i*100,20,0]]} for i in range(4)}
        centers={i:[i*100+20/3,20/3,0] for i in areas}
        anchors=[{'id':str(i),'classname':role,'properties':{},'position':centers[i],'region_ids':[]} for i,role in [(0,'info_player_terrorist'),(1,'info_player_counterterrorist')]]
        for i,designation in [(2,'0'),(3,'1')]:
            anchors.append({'id':str(i),'classname':'func_bomb_target','properties':{'bomb_site_designation':designation},'bounds':{'min':[i*100,-1,-1],'max':[i*100+30,30,1]}})
        graph={'anchors':anchors,'nodes':[{'label':None,'nav_area_ids':list(areas)}]}
        terminals,_=associations(graph,areas,centers,{i:None for i in areas},64)
        self.assertEqual(terminals['A']['nav_area_ids'],[2])
        self.assertEqual(terminals['B']['nav_area_ids'],[3])
        anchors[-1]['properties']['bomb_site_designation']='0'
        with self.assertRaises(ValueError):associations(graph,areas,centers,{i:None for i in areas},64)


if __name__=='__main__':unittest.main()
