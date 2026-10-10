import unittest
import numpy as np
from train_reviewed_context import label_coverage

def polygon(key,x=0):
    return {'id':key,'region_id':str(key),'corners':[[x,0,0],[x+10,0,0],[x+10,10,0],[x,10,0]]}

class ReviewedContextTests(unittest.TestCase):
    def test_unreviewed_areas_are_masked_not_negative_examples(self):
        g={'map':'Train','nav_polygons':[polygon(1),polygon(2,20)]}
        a={'meeting_targets':[{'surface_pieces':[{'nav_area_id':1,'corners':polygon(1)['corners']}]}], 'choke_targets':[]}
        y,mask=label_coverage(g,a)
        self.assertEqual(mask.tolist(),[True,False])
        np.testing.assert_array_equal(y[0],[1,0])

    def test_overlapping_reviewed_footprints_do_not_double_count_coverage(self):
        g={'map':'Train','nav_polygons':[polygon(1)]}
        piece={'nav_area_id':1,'corners':[[0,0,0],[5,0,0],[5,10,0],[0,10,0]]}
        a={'meeting_targets':[{'surface_pieces':[piece]},{'surface_pieces':[piece]}], 'choke_targets':[]}
        y,mask=label_coverage(g,a)
        self.assertEqual(y[0,0],.5)
        self.assertTrue(mask[0])

    def test_cache_named_context_is_not_all_map_meeting_supervision(self):
        g={'map':'Cache','nav_polygons':[polygon(1),polygon(2,20)]}
        a={'battleground_contexts':[{'region_ids':['1']}],'choke_targets':[]}
        y,mask=label_coverage(g,a)
        self.assertEqual(mask.tolist(),[True,False])
        self.assertEqual(y[0,0],1)

if __name__=='__main__':unittest.main()
