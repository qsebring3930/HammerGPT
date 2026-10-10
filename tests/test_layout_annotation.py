import unittest

from annotate_layout import trace_route


def graph():
    return {'nodes':[{'id':str(i),'label':label,'position':[i*100,0,0]} for i,label in enumerate(('Spawn','Choke','Site','OtherSite'))],
        'edges':[{'source':str(a),'target':str(b),'witnesses':[{'source_nav_area':a,'target_nav_area':b}],
                  'reverse_edge_exists':False} for a,b in ((0,1),(1,2),(0,3),(3,2))]}


class LayoutAnnotationTests(unittest.TestCase):
    def test_reverse_route_is_not_invented(self):
        self.assertEqual(trace_route(graph(),'2','0',['Spawn','Choke','Site'])['status'],'unresolved')

    def test_route_restricted_to_intended_places_and_keeps_witnesses(self):
        route=trace_route(graph(),'0','2',['Spawn','Choke','Site'],['Choke'])
        self.assertEqual(route['region_path'],['0','1','2'])
        self.assertEqual(len(route['links']),2)
        self.assertEqual(route['links'][0]['recorded_nav_witness']['target_nav_area'],1)
        self.assertNotIn('OtherSite',route['place_labels'])

    def test_required_choke_missing_is_not_approved_route(self):
        route=trace_route(graph(),'0','2',['Spawn','OtherSite','Site'],['Choke'])
        self.assertEqual(route['status'],'unresolved')


if __name__=='__main__':unittest.main()
