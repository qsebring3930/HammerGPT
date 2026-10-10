import unittest
import numpy as np
import torch

from train_connection_planner import pair_inputs,pair_targets,partition,plan_scores,ConnectionPlanner,predict_plans
from train_patch import patch_input


class ConnectionPlannerTests(unittest.TestCase):
    def context(self):
        y=np.zeros((1,1,32,32),dtype=np.float32); y[0,0,15,11:21]=1
        return patch_input(y)

    def test_pair_features_cannot_include_hidden_values(self):
        a=self.context(); b=a.copy(); b[:,0,12:20,12:20]=1
        ax,ai,ac=pair_inputs(a); bx,bi,bc=pair_inputs(b)
        np.testing.assert_array_equal(ax,bx); self.assertEqual(ai,bi); self.assertEqual(ac,bc)
        self.assertEqual(ai,[(0,0,1)]); self.assertEqual(ac,[2])
        self.assertFalse(ax[:,0,12:20,12:20].any()); self.assertFalse(ax[:,2,12:20,12:20].any())

    def test_connection_labels_are_separate_from_input(self):
        x,indices,_=pair_inputs(self.context())
        self.assertEqual(pair_targets(indices,[[0,0]]).tolist(),[1])
        self.assertEqual(pair_targets(indices,[[0,1]]).tolist(),[0])
        self.assertEqual(x.shape,(1,3,32,32))

    def test_decoder_does_not_merge_through_a_rejected_pair(self):
        p=np.array([[1,.9,.1],[.9,1,.8],[.1,.8,1]])
        self.assertEqual(partition(p),[0,0,1])
        np.testing.assert_array_equal(p,np.array([[1,.9,.1],[.9,1,.8],[.1,.8,1]]))

    def test_decoder_transitivity_and_empty_cases(self):
        self.assertEqual(partition(np.ones((3,3))),[0,0,0])
        self.assertEqual(partition(np.eye(3)),[0,1,2])
        self.assertEqual(partition(np.eye(1)),[0])
        self.assertEqual(partition(np.empty((0,0))),[])
        with self.assertRaises(ValueError): partition(np.array([[1,.9],[.1,1]]))

    def test_plan_scoring_ignores_arbitrary_group_names(self):
        scores=plan_scores([[8,8,2],[],[3]],[[0,0,1],[],[0]])
        self.assertEqual(scores['accuracy'],1)
        self.assertEqual(scores['exact_partition_examples'],1)
        self.assertEqual(scores['examples_with_two_or_more_ports'],1)

    def test_inference_handles_empty_and_single_port_without_forward(self):
        class NeverCalled:
            def eval(self): raise AssertionError('No pair queries should be evaluated')
        empty=np.zeros((2,2,32,32),dtype=np.float32); empty[:,1]=1; empty[:,1,12:20,12:20]=0
        empty[1,0,15,11]=1
        plans,scores,indices=predict_plans(NeverCalled(),empty,'cpu')
        self.assertEqual(plans,[[],[0]]); self.assertEqual(len(scores),0); self.assertEqual(indices,[])

    def test_model_output_has_context_gradient(self):
        torch.manual_seed(1); model=ConnectionPlanner(); x=torch.ones(1,3,32,32,requires_grad=True)
        model(x).sum().backward()
        self.assertGreater(x.grad[:,:,0:4,0:4].abs().sum().item(),0)


if __name__=='__main__': unittest.main()
