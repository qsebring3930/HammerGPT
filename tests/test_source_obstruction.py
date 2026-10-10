import unittest
import numpy as np
import torch
from train_source_planner import SourcePlanner,decode
from train_route_organization import GraphPlanner,N
from architecture_features import MeshIndex
from source_obstruction_features import FastIndex,ray_fraction


class ObstructionTests(unittest.TestCase):
    def test_missing_geometry_preserves_base_after_correction_changes(self):
        torch.manual_seed(7)
        base=GraphPlanner().eval();model=SourcePlanner(base).eval()
        with torch.no_grad():model.correction[-1].bias.fill_(3)
        x=torch.randn(1,N,13);edges=torch.zeros(1,N,N);valid=torch.ones(1,N)
        node=torch.randn(1,N,32);pair=torch.zeros(1,N,N,12)
        with torch.no_grad():
            expected=base(x,edges,edges,valid)
            actual=model(x,edges,edges,valid,node,pair)
        torch.testing.assert_close(actual,expected,rtol=0,atol=0)

    def test_unknown_geometry_uses_existing_decoder(self):
        result=decode(np.array([.99,.99]),np.array([.2,.9]),np.array([False,True]),.95,.865)
        np.testing.assert_array_equal(result,[0,1])

    def test_native_wall_is_not_an_unobstructed_ray(self):
        triangles=np.array([[[5,-10,0],[5,10,0],[5,10,100]],[[5,-10,0],[5,10,100],[5,-10,100]]],dtype=np.float32)
        index=FastIndex(triangles);bounds=np.array([[-100,-100,-100],[100,100,100]])
        value,known=ray_fraction(index,np.array([0,0,32.]),np.array([10,0,32.]),bounds)
        self.assertAlmostEqual(value,.5);self.assertEqual(known,1)
        value,known=ray_fraction(index,np.array([0,0,32.]),np.array([-10,0,32.]),bounds)
        self.assertEqual((value,known),(1,1))

    def test_missing_source_region_is_unknown_not_clear(self):
        index=FastIndex(np.empty((0,3,3),np.float32));bounds=np.array([[0,0,0],[10,10,10]])
        self.assertEqual(ray_fraction(index,np.array([1,1,1.]),np.array([20,1,1.]),bounds),(0,0))

    def test_broad_phase_agrees_with_existing_triangle_intersector(self):
        rng=np.random.default_rng(4);triangles=rng.normal(size=(60,3,3)).astype(np.float32)*10
        old=MeshIndex(triangles);new=FastIndex(triangles)
        for _ in range(12):
            origin=rng.normal(size=3)*20;direction=rng.normal(size=3)
            self.assertAlmostEqual(old.ray(origin,direction,60)['distance_units'],new.ray(origin,direction,60)['distance_units'],places=5)


if __name__=='__main__':unittest.main()
