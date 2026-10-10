import unittest
import numpy as np
import torch
from train_progressive_layout import Progressive,pack,statistics


class GenerationTests(unittest.TestCase):
    def test_future_targets_cannot_change_current_prediction_state(self):
        torch.manual_seed(3);model=Progressive().eval()
        data={'x':torch.randn(1,6,5),'role':torch.zeros(1,6,dtype=torch.long),
              'edge':torch.zeros(1,6,6,2),'valid':torch.ones(1,6,dtype=torch.bool)}
        with torch.no_grad():h,_=model(data)
        changed={k:v.clone() for k,v in data.items()};changed['x'][:,3:]+=20;changed['role'][:,3:]=15;changed['edge'][:,3:]=1
        with torch.no_grad():again,_=model(changed)
        torch.testing.assert_close(h[:,:4],again[:,:4],rtol=0,atol=0)

    def test_generated_graph_has_no_diagonal_edges_and_repeats_seed(self):
        model=Progressive().eval()
        with torch.no_grad():model.count_logits.fill_(-100);model.count_logits[7]=100
        a=model.sample(41,np.zeros(5),np.ones(5),'cpu');b=model.sample(41,np.zeros(5),np.ones(5),'cpu')
        self.assertEqual(a,b);self.assertEqual(a['node_count'],8)
        self.assertEqual(np.trace(a['adjacency']),0)
        self.assertTrue((np.asarray(a['descriptors'])[:,3:]>0).all())

    def test_padding_does_not_add_fitting_edges_or_nodes(self):
        r={'x':np.zeros((3,5),np.float32),'roles':np.array([1,2,4]),'edges':np.zeros((3,3,2),np.float32)}
        data=pack([r],[3],np.zeros(5),np.ones(5),'cpu')
        loss,_=Progressive().losses(data);self.assertTrue(torch.isfinite(loss));loss.backward()

    def test_disconnected_terminals_are_reported(self):
        s={'roles':[1,2,4,8],'adjacency':np.zeros((4,4)).tolist(),'descriptors':np.zeros((4,5)).tolist()}
        stats=statistics(s);self.assertTrue(stats['all_terminals_present']);self.assertFalse(stats['terminals_share_component'])


if __name__=='__main__':unittest.main()
