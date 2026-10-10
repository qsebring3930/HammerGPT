from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connected_geometry import floor_cells,elevation,validate_floor,create_connected_blockout,GRID
from hammergpt import get,parse,positions


def proposal():
    return {'design_choices':{'corridor_width_units':192,'regions':[
        {'id':'A','center':[0,0,0],'size':[256,256,256]},
        {'id':'B','center':[1024,512,128],'size':[256,256,256]}],
        'connections':[{'source':'A','target':'B'}]}}


class ConnectedTests(unittest.TestCase):
    def test_disconnected_islands_fail(self):
        with self.assertRaisesRegex(ValueError,'disconnected'):
            validate_floor({(0,0),(2,0)},lambda x:0)

    def test_elbow_floor_is_connected_with_gentle_elevation(self):
        plan=proposal(); cells=floor_cells(plan); z=elevation(plan,cells)
        self.assertEqual(validate_floor(cells,z)['floor_components'],1)
        self.assertEqual(z(1024),128)
        for x,y in cells:
            self.assertLessEqual(abs(z((x+1)*GRID)-z(x*GRID)),16)

    def test_generated_floor_edges_share_surface_and_walls_are_outside(self):
        _,roots=parse((Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text())
        plan=proposal(); cells=floor_cells(plan); z=elevation(plan,cells)
        result,manifest,validation=create_connected_blockout(roots,plan)
        world=get(next(r for r in result if r.kind=='CMapRootElement'),'world')
        children=get(world,'children')
        for mesh,record in zip(children,manifest):
            if record['label']=='continuous_floor':
                cx,cy,cz=record['center']; width,depth,_=record['size']
                pts=[list(map(float,p.split())) for p in get(positions(mesh),'data')]
                for localx in (-width/2,width/2):
                    top=max(p[2]+cz for p in pts if p[0]==localx)
                    self.assertAlmostEqual(top,z(cx+localx),places=5)
            else:
                x,y,_=record['center']
                self.assertNotIn((int(x//GRID),int(y//GRID)),cells)
        self.assertGreater(validation['wall_segments'],0)
