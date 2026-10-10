import unittest
import numpy as np

from solver_planner import solve_plan
from improve_connection_planner import maximum_likelihood_partition


class ConstraintPlannerTests(unittest.TestCase):
    def test_matches_exhaustive_decoder_on_small_unique_problems(self):
        rng=np.random.default_rng(42)
        for count in (2,3,4,5):
            p=rng.uniform(.05,.95,(count,count)); p=(p+p.T)/2; np.fill_diagonal(p,1)
            result,info=solve_plan(p)
            self.assertTrue(info['optimal']); self.assertEqual(result,maximum_likelihood_partition(p))

    def test_handles_twenty_ports_without_enumerating_partitions(self):
        labels=np.repeat(np.arange(4),5); p=np.where(labels[:,None]==labels[None,:],.95,.05)
        result,info=solve_plan(p)
        self.assertTrue(info['optimal']); self.assertEqual(result,labels.tolist())

    def test_consistency_can_override_one_pair(self):
        p=np.array([[1,.9,.4],[.9,1,.8],[.4,.8,1]])
        result,info=solve_plan(p)
        self.assertEqual(result,[0,0,0]); self.assertTrue(info['optimal'])

    def test_empty_singleton_and_tie(self):
        self.assertEqual(solve_plan(np.empty((0,0)))[0],[])
        self.assertEqual(solve_plan(np.eye(1))[0],[0])
        self.assertEqual(solve_plan(np.full((4,4),.5))[0],[0,1,2,3])

    def test_invalid_inputs_rejected(self):
        for p in (np.array([[1,.9],[.1,1]]),np.array([[np.nan]]),np.eye(21)):
            with self.assertRaises(ValueError): solve_plan(p)
        with self.assertRaises(ValueError): solve_plan(np.eye(2),time_limit=0)


if __name__=='__main__': unittest.main()
