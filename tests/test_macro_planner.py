import unittest
import numpy as np
from train_macro_planner import connected_edges,N,PAIRS
from export_macro_graybox import manifold_cells


class MacroPlannerTests(unittest.TestCase):
    def test_disconnected_prediction_gets_explicit_minimum_repairs(self):
        edges,repairs=connected_edges(np.zeros(len(PAIRS)))
        self.assertEqual(len(edges),N-1);self.assertEqual(edges,repairs)
        reached={0}
        while True:
            new=reached|{b for a,b in edges if a in reached}|{a for a,b in edges if b in reached}
            if new==reached:break
            reached=new
        self.assertEqual(len(reached),N)

    def test_predicted_edges_retained_without_duplicates(self):
        edges,repairs=connected_edges(np.ones(len(PAIRS)))
        self.assertEqual(set(edges),set(PAIRS));self.assertEqual(repairs,[])

    def test_corner_repair_retains_all_original_floor(self):
        original={(0,0),(1,1)};cells,added=manifold_cells(original)
        self.assertTrue(original<=cells);self.assertEqual(added,[(1,0)])
        self.assertEqual(manifold_cells(cells),(cells,[]))


if __name__=='__main__':unittest.main()
