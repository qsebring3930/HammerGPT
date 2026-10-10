import unittest
import numpy as np
import torch
from train_routes import reachability, route_labels, route_loss
from train_conditioned import annotated


class SoftRouteTests(unittest.TestCase):
    def test_bottleneck_and_gradient(self):
        grid=torch.zeros(1,1,10,10)
        grid[0,0,4,1:9]=.9; grid[0,0,4,5]=.2; grid.requires_grad_()
        seeds=torch.zeros_like(grid); seeds[0,0,4,1]=1
        value=reachability(grid,seeds)[0,0,4,8]
        self.assertAlmostEqual(value.item(),.2,places=6)
        value.backward(); self.assertGreater(grid.grad[0,0,4,5].item(),0)

    def test_uses_best_detour(self):
        grid=torch.zeros(1,1,10,10)
        grid[0,0,4,1:9]=.9; grid[0,0,4,5]=.2
        grid[0,0,3,1:9]=.7
        seeds=torch.zeros_like(grid); seeds[0,0,4,1]=1
        self.assertAlmostEqual(reachability(grid,seeds)[0,0,4,8].item(),.7,places=6)

    def test_diagonal_contact_and_padding_are_not_routes(self):
        grid=torch.zeros(1,1,10,10); grid[0,0,0,0]=1; grid[0,0,1,1]=1; grid[0,0,9,0]=1
        seeds=torch.zeros_like(grid); seeds[0,0,0,0]=1
        reached=reachability(grid,seeds)
        self.assertEqual(reached[0,0,1,1].item(),0); self.assertEqual(reached[0,0,9,0].item(),0)

    def test_long_winding_path(self):
        grid=torch.zeros(1,1,10,10)
        grid[0,0,::2,:]=1
        for row in (1,3,5,7): grid[0,0,row,9 if row in (1,5) else 0]=1
        seeds=torch.zeros_like(grid); seeds[0,0,0,0]=1
        self.assertEqual(reachability(grid,seeds)[0,0,8,9].item(),1)

    def test_penalty_tracks_supplied_plan_and_has_gradient(self):
        target=np.zeros((1,1,32,32),dtype=np.float32); target[0,0,15,11:21]=1
        x,plans=annotated(target); context=torch.tensor(x)
        connect=[torch.tensor(a) for a in route_labels(x,plans)]
        separate=[torch.tensor(a) for a in route_labels(x,[[0,1]])]
        low=torch.full((1,1,32,32),-2.,requires_grad=True)
        high=torch.full_like(low,2.)
        self.assertGreater(route_loss(low,context,connect).item(),route_loss(high,context,connect).item())
        self.assertLess(route_loss(low,context,separate).item(),route_loss(high,context,separate).item())
        route_loss(low,context,connect).backward()
        self.assertGreater(low.grad[:,:,12:20,12:20].abs().sum().item(),0)
        self.assertEqual(low.grad[:,:,11,:].abs().sum().item(),0)

    def test_no_ports_is_zero_and_differentiable(self):
        x,plans=annotated(np.zeros((1,1,32,32),dtype=np.float32))
        labels=[torch.tensor(a) for a in route_labels(x,plans)]
        logits=torch.zeros(1,1,32,32,requires_grad=True)
        loss=route_loss(logits,torch.tensor(x),labels)
        self.assertEqual(loss.item(),0); loss.backward()


if __name__=='__main__': unittest.main()
