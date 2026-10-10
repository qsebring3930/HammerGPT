import itertools
import unittest
import numpy as np
import torch

from improve_connection_planner import transform_features,candidate_partitions,maximum_likelihood_partition,RegularizedPlanner
from train_connection_planner import partition,ConnectionPlanner,pair_inputs
from train_conditioned import reference_plan
from train_patch import patch_input


class PlannerImprovementTests(unittest.TestCase):
    def test_symmetries_keep_all_channels_aligned_and_are_reversible(self):
        x=torch.arange(3*32*32,dtype=torch.float32).reshape(1,3,32,32).repeat(8,1,1,1)
        codes=torch.arange(8); transformed=transform_features(x,codes)
        for code in range(8):
            value=transformed[code]
            if code>=4: value=torch.flip(value,(-1,))
            value=torch.rot90(value,-(code%4),(-2,-1))
            self.assertTrue(torch.equal(value,x[code]))
        with self.assertRaises(ValueError): transform_features(x,torch.tensor([8]*8))

    def test_symmetry_preserves_connection_label_without_hidden_leak(self):
        target=np.zeros((1,1,32,32),dtype=np.float32); target[0,0,15,11:21]=1
        features,_,_=pair_inputs(patch_input(target))
        transformed=transform_features(torch.tensor(features).repeat(8,1,1,1),torch.arange(8))
        targets=transform_features(torch.tensor(target).repeat(8,1,1,1),torch.arange(8))
        for x,y in zip(transformed.numpy(),targets.numpy()):
            plan=reference_plan(x[:2],y)
            self.assertEqual(plan,[0,0])
            self.assertFalse(x[0,12:20,12:20].any())
            self.assertFalse(x[2,12:20,12:20].any())

    def test_partitions_are_unique_and_complete(self):
        for n,expected in [(0,1),(1,1),(2,2),(3,5),(4,15),(8,4140)]:
            candidates,_=candidate_partitions(n)
            self.assertEqual(len(candidates),expected); self.assertEqual(len(set(candidates)),expected)

    def test_global_decoder_can_accept_a_pair_to_improve_whole_plan(self):
        p=np.array([[1,.9,.4],[.9,1,.8],[.4,.8,1]])
        self.assertEqual(partition(p),[0,0,1])
        self.assertEqual(maximum_likelihood_partition(p),[0,0,0])
        p[0,2]=p[2,0]=.1
        self.assertEqual(maximum_likelihood_partition(p),[0,0,1])

    def test_decoder_score_matches_independent_exhaustive_search(self):
        p=np.array([[1,.8,.3,.2],[.8,1,.7,.1],[.3,.7,1,.6],[.2,.1,.6,1]])
        pairs=list(itertools.combinations(range(4),2))
        def score(labels):
            return sum(np.log(p[a,b] if labels[a]==labels[b] else 1-p[a,b]) for a,b in pairs)
        best=max(score(labels) for labels in itertools.product(range(4),repeat=4))
        self.assertAlmostEqual(score(maximum_likelihood_partition(p)),best,places=10)

    def test_decoder_empty_tie_invalid_and_fallback_cases(self):
        self.assertEqual(maximum_likelihood_partition(np.empty((0,0))),[])
        self.assertEqual(maximum_likelihood_partition(np.full((3,3),.5)),[0,1,2])
        self.assertEqual(maximum_likelihood_partition(np.eye(9)),partition(np.eye(9)))
        with self.assertRaises(ValueError): maximum_likelihood_partition(np.array([[1,np.nan],[np.nan,1]]))

    def test_regularized_model_eval_preserves_original_checkpoint_behavior(self):
        torch.manual_seed(1); original=ConnectionPlanner().eval(); regularized=RegularizedPlanner(.25).eval()
        regularized.load_state_dict(original.state_dict()); x=torch.randn(2,3,32,32)
        with torch.no_grad(): self.assertTrue(torch.allclose(original(x),regularized(x),atol=1e-6))


if __name__=='__main__': unittest.main()
