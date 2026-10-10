import unittest
import numpy as np
import torch
from geometry_completion_dataset import SPLITS,crop,raster_surfaces
from train_geometry_completion import GeometryNet,masked_input,retrieval_baseline,score,passage_scores
from calibrate_geometry_completion import thin_peaks

class GeometryCompletionTests(unittest.TestCase):
    def test_map_splits_are_disjoint_and_train_held_out(self):
        self.assertFalse(set(SPLITS['train'])&set(SPLITS['validation']))
        self.assertFalse(set(SPLITS['train'])&set(SPLITS['test']))
        self.assertEqual(SPLITS['test'],['Train'])

    def test_hidden_targets_cannot_enter_model_input(self):
        a=np.zeros((1,2,16,32,32),np.float32);b=a.copy();b[:,:,:,10:22,10:22]=1
        np.testing.assert_array_equal(masked_input(a),masked_input(b))
        self.assertTrue(np.all(masked_input(b)[:,2,:,10:22,10:22]==0))

    def test_retrieval_uses_only_visible_context(self):
        a=np.zeros((1,2,16,32,32),np.float32);bank=np.concatenate([a,a.copy()]);bank[1,:,:,10:22,10:22]=1
        a[:,:,:,10:22,10:22]=1
        _,ids=retrieval_baseline(a,bank)
        self.assertEqual(ids,[0])

    def test_surface_voxels_keep_height_and_diagonal_empty_space(self):
        v=np.zeros((8,8,8),np.uint8)
        t=np.array([[[0,0,64],[128,0,64],[0,128,64]]],np.float32)
        raster_surfaces(t,v,np.zeros(3))
        self.assertTrue(v[2,0,0])
        self.assertFalse(v[2,3,3])
        self.assertFalse(v[0].any())

    def test_crop_preserves_stacked_walking_surfaces(self):
        v=np.zeros((2,24,64,64),np.uint8);v[0,8,32,32]=1;v[0,12,32,32]=1
        a=crop(v,np.array([8,32,32]))
        self.assertEqual(a.shape,(2,16,32,32))
        self.assertTrue(a[0,4,16,16]);self.assertTrue(a[0,8,16,16])

    def test_model_outputs_both_full_height_channels(self):
        torch.set_num_threads(2)
        model=GeometryNet();a=torch.zeros(1,4,16,32,32)
        self.assertEqual(tuple(model(a).shape),(1,2,16,32,32))

    def test_passage_proxy_detects_a_severed_route(self):
        y=np.zeros((1,2,16,32,32),np.float32);y[0,0,4,16,9:23]=1
        perfect=passage_scores(y,y);broken=y.copy();broken[0,0,4,16,16]=0
        poor=passage_scores(broken,y)
        self.assertGreater(perfect['retained_source_connections_fraction'],poor['retained_source_connections_fraction'])
        self.assertEqual(score(y,y)['walking_surface']['iou'],1)

    def test_uncovered_geometry_is_not_scored_as_empty(self):
        y=np.zeros((1,2,16,32,32),np.float32);p=y.copy();p[:,1,:,10:22,10:22]=1
        valid=np.ones_like(y);valid[:,1,:,10:22,10:22]=0
        a=score(p,y,valid)
        self.assertEqual(a['mesh_surface']['scored_voxels'],0)
        self.assertTrue(np.all(masked_input(y,valid=valid)[:,3,:,10:22,10:22]==0))

    def test_thin_decoder_retains_two_separate_floors(self):
        p=np.zeros((1,2,16,1,1),np.float32)
        p[0,0,3:5,0,0]=[.7,.9];p[0,0,10:12,0,0]=[.95,.6]
        result=thin_peaks(p,.5)
        self.assertEqual(np.flatnonzero(result[0,0,:,0,0]).tolist(),[4,10])

    def test_uncovered_target_cannot_change_training_loss(self):
        from train_geometry_completion import loss
        y=torch.zeros(1,2,16,32,32);valid=torch.ones_like(y);valid[:,1]=0
        known=torch.zeros_like(y);a=torch.zeros_like(y);b=a.clone();b[:,1]=10
        weights=torch.ones(2,1,1,1)
        self.assertAlmostEqual(loss(a,y,known,weights,valid).item(),loss(b,y,known,weights,valid).item())

if __name__=='__main__':unittest.main()
