import unittest
import numpy as np
import torch
from train_graph_state_layout import GraphStateProgressive,measures


class GraphStateTests(unittest.TestCase):
    def data(self,n=6):
        torch.manual_seed(22)
        return {'x':torch.randn(1,n,5),'role':torch.arange(n)[None]%16,'edge':torch.zeros(1,n,n,2),'valid':torch.ones(1,n,dtype=torch.bool)}

    def test_future_graph_changes_do_not_leak_into_prediction_state(self):
        model=GraphStateProgressive().eval();data=self.data()
        with torch.no_grad():h,_=model(data)
        changed={k:v.clone() for k,v in data.items()};changed['x'][:,3:]+=30;changed['role'][:,3:]=15
        changed['edge'][:,3:]=1;changed['edge'][:,:,3:]=1
        with torch.no_grad():again,_=model(changed)
        torch.testing.assert_close(h[:,:4],again[:,:4],rtol=0,atol=0)

    def test_sampling_and_teacher_forcing_use_same_prefix_context(self):
        model=GraphStateProgressive().eval();data=self.data()
        data['edge'][:,2,0,0]=1;data['edge'][:,0,2,1]=1
        with torch.no_grad():
            all_steps=model.representation(data['x'],data['role'],data['edge'])
            for i in range(6):
                step=model.sampling_input(data['x'],data['role'],data['edge'],i,6)
                torch.testing.assert_close(step[:,0],all_steps[:,i],rtol=1e-5,atol=1e-6)

    def test_equal_degree_different_neighbors_changes_graph_context(self):
        model=GraphStateProgressive().eval();data=self.data()
        first=data['edge'].clone();second=data['edge'].clone()
        first[:,3,0,0]=1;first[:,0,3,1]=1
        second[:,3,1,0]=1;second[:,1,3,1]=1
        with torch.no_grad():
            a=model.representation(data['x'],data['role'],first)
            b=model.representation(data['x'],data['role'],second)
        torch.testing.assert_close(a[:,3,:18],b[:,3,:18])
        self.assertGreater(float((a[:,3,18:]-b[:,3,18:]).abs().max()),1e-6)

    def test_generated_graph_is_repeatable_without_supplied_graph(self):
        model=GraphStateProgressive().eval()
        with torch.no_grad():model.count_logits.fill_(-100);model.count_logits[7]=100
        a=model.sample(7,np.zeros(5),np.ones(5),'cpu');b=model.sample(7,np.zeros(5),np.ones(5),'cpu')
        self.assertEqual(a,b);self.assertEqual(np.trace(a['adjacency']),0)

    def test_access_metric_respects_direction(self):
        sample={'roles':[1,2,4,8],'descriptors':np.ones((4,5)).tolist(),'adjacency':[[0,0,1,1],[0,0,1,1],[0,0,0,0],[0,0,0,0]]}
        self.assertTrue(measures(sample)['all_four_directed_access_pairs'])
        sample['adjacency']=np.array(sample['adjacency']).T.tolist()
        self.assertFalse(measures(sample)['all_four_directed_access_pairs'])


if __name__=='__main__':unittest.main()
