from pathlib import Path
import sys
import unittest
import json
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from training_dataset import masked,raster,SPLITS,build
from train_layout import LayoutNet,scores,extrapolate


class TrainingTests(unittest.TestCase):
    def test_reserved_evaluation_map_cannot_enter_development_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); corpus=root/'corpus.json'
            corpus.write_text(json.dumps({'maps':[{'name':'Dust2','user_approved':True,
                                                   'nav_available':True,'dataset_role':'evaluation_only'}]}))
            with self.assertRaisesRegex(ValueError,'Reserved evaluation map'):
                build(corpus,root/'dataset',samples=1)

    def test_input_cannot_leak_hidden_target(self):
        a=np.ones((32,32),dtype=np.float32); b=a.copy(); b[:,16:]=0
        self.assertTrue(np.array_equal(masked(a),masked(b)))
        self.assertEqual(masked(a)[1,:,16:].sum(),0)

    def test_map_splits_are_disjoint(self):
        names=[name for group in SPLITS.values() for name in group]
        self.assertEqual(len(names),len(set(names)))
        self.assertNotIn('Vertigo',SPLITS['train'])
        self.assertNotIn('Office',SPLITS['train'])

    def test_raster_filters_other_elevation(self):
        floor=[[-1024,-1024,0],[0,-1024,0],[0,1024,0],[-1024,1024,0]]
        above=[[p[0]+1024,p[1],p[2]+256] for p in floor]
        result=raster([floor,above],0,0,0)
        self.assertEqual(result[:,:16].sum(),512)
        self.assertEqual(result[:,16:].sum(),0)

    def test_metrics_ignore_visible_half(self):
        target=np.ones((1,1,32,32)); prediction=target.copy(); prediction[:,:,:,:16]=0
        self.assertEqual(scores(prediction,target)['hidden_pixel_iou'],1)
        prediction[:,:,:,16:]=0
        self.assertEqual(scores(prediction,target)['hidden_pixel_iou'],0)

    def test_model_has_trainable_completion_output(self):
        torch.manual_seed(1); model=LayoutNet(); x=torch.zeros((2,2,32,32)); x[:,1,:,:16]=1
        output=model(x); self.assertEqual(tuple(output.shape),(2,1,32,32))
        output[:,:,:,16:].mean().backward()
        self.assertTrue(any(p.grad is not None and p.grad.abs().sum()>0 for p in model.parameters()))
