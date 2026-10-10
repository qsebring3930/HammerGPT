from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from train_patch import patch_input,patch_scores,interpolation,ContextNet


class PatchTrainingTests(unittest.TestCase):
    def test_patch_input_has_no_hidden_target_leak(self):
        a=np.ones((2,1,32,32),dtype=np.float32); b=a.copy(); b[:,:,12:20,12:20]=0
        self.assertTrue(np.array_equal(patch_input(a),patch_input(b)))
        self.assertEqual(patch_input(a)[:,1].sum(),2*(1024-64))

    def test_metrics_score_only_the_missing_patch(self):
        y=np.ones((1,1,32,32)); p=np.zeros_like(y); p[:,:,12:20,12:20]=1
        self.assertEqual(patch_scores(p,y)['hidden_pixel_iou'],1)

    def test_interpolation_uses_context_not_target(self):
        x=patch_input(np.ones((1,1,32,32),dtype=np.float32))
        result=interpolation(x)
        self.assertTrue(np.allclose(result,1))

    def test_context_output_depends_on_distant_context(self):
        torch.manual_seed(7); model=ContextNet(); x=torch.ones((1,2,32,32),requires_grad=True)
        model(x)[0,0,16,16].backward()
        self.assertGreater(x.grad[0,0,:4,:4].abs().sum().item(),0)
