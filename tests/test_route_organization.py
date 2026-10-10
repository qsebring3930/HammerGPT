import unittest
import numpy as np
import torch
from train_route_organization import N,FEATURES,mask_example,retrieval,GraphPlanner,FlatPlanner,loss_for,geometric_neighbors
from calibrate_route_organization import choose_threshold


def record():
    x=np.zeros((N,FEATURES),np.float32);x[:16,0]=np.arange(16)*.1
    valid=np.arange(N)<16;y=np.zeros((N,N),np.float32)
    for i in range(15):y[i,i+1]=1
    return {'map':'reference','x':x,'y':y,'valid':valid}


class OrganizationTests(unittest.TestCase):
    def test_mask_and_inputs_do_not_expose_hidden_labels(self):
        r=record();a=mask_example(r,33);changed={**r,'y':r['y'].copy()};changed['y'][a['hidden']]=1-changed['y'][a['hidden']]
        b=mask_example(changed,33)
        for key in ('x','known','observed','hidden','holes'):np.testing.assert_array_equal(a[key],b[key])

    def test_retrieval_does_not_rank_by_hidden_query_truth(self):
        r=record();e=mask_example(r,44);p,n=retrieval([e],[r]);e['target']=1-e['target'];q,m=retrieval([e],[r])
        np.testing.assert_array_equal(p,q);self.assertEqual(n,m)

    def test_model_shapes_and_no_loss_on_padding(self):
        e=mask_example(record(),55);t=lambda k:torch.as_tensor(e[k])[None]
        for cls in (GraphPlanner,FlatPlanner):
            model=cls();out=model(t('x'),t('observed'),t('known'),t('valid'))
            self.assertEqual(out.shape,(1,N,N))
        target=t('target');hidden=t('hidden');pred=torch.zeros_like(target)
        first=loss_for(pred,target,hidden,2);target[:,32:,32:]=1
        self.assertEqual(float(first),float(loss_for(pred,target,hidden,2)))

    def test_geometry_baseline_does_not_use_hidden_target(self):
        e=mask_example(record(),77);a=geometric_neighbors([e],.2,3)
        e['target']=1-e['target'];b=geometric_neighbors([e],.2,3)
        np.testing.assert_array_equal(a,b)
        self.assertFalse(a[:,16:,:].any())

    def test_threshold_selection_ignores_unscored_padding(self):
        e=mask_example(record(),88);prob=e['target'][None]*.9+(1-e['target'][None])*.1
        selected,_=choose_threshold(prob,[e]);prob[:,32:,32:]=1
        again,_=choose_threshold(prob,[e]);self.assertEqual(selected,again)


if __name__=='__main__':unittest.main()
