import unittest

from coarse_layout import coarsen, interface_support
from test_whole_map_layout import area, graph


class CoarseLayoutTests(unittest.TestCase):
    def test_bidirectional_merge_conserves_members(self):
        source = graph([area(1,0,[2]),area(2,600,[1])])
        result = coarsen(source,minimum_support=32)
        self.assertEqual(len(result['nodes']),1)
        self.assertEqual(result['nodes'][0]['nav_area_ids'],[1,2])
        self.assertEqual(result['edges'],[])

    def test_one_way_interface_not_merged(self):
        source = graph([area(1,0,[2]),area(2,600)])
        result = coarsen(source,minimum_support=0)
        self.assertEqual(len(result['nodes']),2)
        self.assertEqual(result['edges'][0]['witnesses'],source['edges'][0]['witnesses'])

    def test_conflicting_labels_not_merged(self):
        source = graph([area(1,0,[2]),area(2,600,[1])])
        source['nodes'][0]['label']='SiteA'; source['nodes'][1]['label']='CTSpawn'
        self.assertEqual(len(coarsen(source,minimum_support=0)['nodes']),2)

    def test_size_and_height_caps(self):
        source = graph([area(1,0,[2]),area(2,600,[1])])
        self.assertEqual(len(coarsen(source,minimum_support=0,maximum_span=500)['nodes']),2)
        source = graph([area(1,0,[2]),area(2,0,[1],z=256)])
        self.assertEqual(len(coarsen(source,minimum_support=0)['nodes']),2)

    def test_duplicate_edge_support_not_double_counted(self):
        w = {'source_nav_area':1,'source_edge':0,'source_edge_length_xy':128,'target_edge_length_xy':64}
        self.assertEqual(interface_support([w,w]),64)

    def test_external_directed_witnesses_survive_merge(self):
        source = graph([area(1,0,[2]),area(2,600,[1,3]),area(3,1200)])
        result = coarsen(source,minimum_support=32)
        self.assertEqual(len(result['nodes']),2)
        self.assertEqual(len(result['edges']),1)
        self.assertEqual(result['edges'][0]['witnesses'][0]['source_nav_area'],2)
        self.assertEqual(result['edges'][0]['witnesses'][0]['target_nav_area'],3)


if __name__=='__main__': unittest.main()
