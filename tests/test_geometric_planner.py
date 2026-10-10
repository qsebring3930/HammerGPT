import unittest
import numpy as np
import torch

from geometric_planner import geometry_inputs,rank_cost,proposal_plans,GeometryPlanner
from train_connection_planner import pair_inputs
from train_patch import patch_input
from improve_connection_planner import transform_features


class GeometricPlannerTests(unittest.TestCase):
    def example(self):
        y=np.zeros((1,1,32,32),dtype=np.float32); y[0,0,15,8:24]=1
        return y,patch_input(y)

    def test_geometry_cannot_leak_hidden_pixels(self):
        _,x=self.example(); altered=x.copy(); altered[:,0,12:20,12:20]=1
        _,indices,_=pair_inputs(x)
        np.testing.assert_array_equal(geometry_inputs(x,indices),geometry_inputs(altered,indices))

    def test_pair_features_symmetric_and_rotation_reflection_invariant(self):
        _,x=self.example(); original=geometry_inputs(x,[(0,0,1)])
        np.testing.assert_allclose(original,geometry_inputs(x,[(0,1,0)]),atol=1e-6)
        transformed=transform_features(torch.tensor(x).repeat(8,1,1,1),torch.arange(8)).numpy()
        for value in transformed:
            _,indices,_=pair_inputs(value[None])
            np.testing.assert_allclose(original,geometry_inputs(value[None],indices),atol=1e-6)

    def test_geometry_empty_pair_queries(self):
        _,x=self.example(); self.assertEqual(geometry_inputs(x,[]).shape,(0,12))

    def test_ranking_penalizes_unfulfilled_plan_and_thin_floor(self):
        y,x=self.example(); p=np.array([[1,.5],[.5,1]])
        thin=rank_cost(x[0],y[0],[0,0],p)
        invalid=rank_cost(x[0],y[0],[0,1],p)
        self.assertEqual(thin['plan_violation_fraction'],0)
        self.assertEqual(invalid['plan_violation_fraction'],1)
        self.assertGreater(invalid['total'],thin['total'])
        thick=y[0].copy(); thick[0,14:17,12:20]=1
        wider=rank_cost(x[0],thick,[0,0],p)
        self.assertLess(wider['narrow_cell_fraction'],thin['narrow_cell_fraction'])

    def test_candidates_unique_and_valid_equivalence_groups(self):
        p=np.array([[1,.8,.4],[.8,1,.6],[.4,.6,1]])
        plans,info=proposal_plans(p)
        self.assertEqual(len(plans),len({tuple(plan) for plan in plans})); self.assertEqual(len(plans),len(info))
        self.assertIn([0,0,0],plans); self.assertIn([0,1,2],plans)
        self.assertEqual(proposal_plans(np.empty((0,0)))[0],[[]])

    def test_model_responds_to_geometry_and_preserves_shape(self):
        torch.manual_seed(1); model=GeometryPlanner(); x=torch.ones(2,3,32,32); g=torch.ones(2,12,requires_grad=True)
        result=model(x,g); self.assertEqual(result.shape,(2,)); result.sum().backward()
        self.assertGreater(g.grad.abs().sum().item(),0)


if __name__=='__main__': unittest.main()
