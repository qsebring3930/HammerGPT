from pathlib import Path
import unittest

import networkx as nx
import numpy as np

from connected_geometry import floor_cells, elevation, validate_floor
from hammergpt import parse, get, walk
from surface_geometry import create_surface_blockout, validate_topology
from train_route_macro import attach_heights, choose_graph, PAIRS, route_corridors, sample_polyline, audit_floor_graph


class RouteMacroTests(unittest.TestCase):
    def test_unplanned_floor_junction_is_rejected(self):
        regions=[{'id':str(i),'center':[x,y,0],'size':[128,128,256]} for i,(x,y) in enumerate(((-512,0),(512,0),(0,-512),(0,512)))]
        plan={'design_choices':{'regions':regions,'corridor_width_units':128,
            'connections':[{'source':'0','target':'1'},{'source':'2','target':'3'}]}}
        with self.assertRaisesRegex(ValueError,'4 room contacts'):
            audit_floor_graph(plan,floor_cells(plan))

    def test_route_sampling_follows_bend_not_endpoint_chord(self):
        points=[[0,0],[0,100],[100,100]]
        np.testing.assert_allclose(sample_polyline(points,.5),[0,100])

    def test_height_field_has_flat_rooms_and_welded_sloping_mesh(self):
        plan={'design_choices':{'regions':[
            {'id':'A','center':[0,0,0],'size':[256,256,256]},
            {'id':'B','center':[2048,512,128],'size':[256,256,256]}],
            'connections':[{'source':'A','target':'B','path_xy':[[0,0],[2048,0],[2048,512]]}],
            'corridor_width_units':192}}
        cells=floor_cells(plan);record=attach_heights(plan,cells);height=elevation(plan,cells)
        self.assertEqual(record['height_amplitude_retained'],1)
        self.assertEqual(height(0,0),0);self.assertEqual(height(2048,512),128)
        self.assertEqual(height(1984,448),128)
        validate_floor(cells,height)
        _,roots=parse((Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text())
        result,_,_=create_surface_blockout(roots,plan)
        mesh=next(n for r in result for n in walk(r) if n.kind=='CMapMesh')
        self.assertGreater(validate_topology(mesh)['faces'],len(cells)*2)

    def test_unrelated_rooms_are_not_opened_by_corridor(self):
        regions=[{'id':str(i),'center':[x,0,0],'size':[256,256,256]} for i,x in enumerate((0,2048,1024))]
        controls={(0,1):[np.array([0,0]),np.array([2048,0])]}
        edges,cells,lengths=route_corridors(regions,[(0,1)],controls)
        self.assertGreater(lengths[0]['units'],2048)
        route=floor_cells({'design_choices':{'regions':regions[:2],'connections':edges,'corridor_width_units':192}})
        forbidden=floor_cells({'design_choices':{'regions':[regions[2]],'connections':[],'corridor_width_units':192}})
        self.assertFalse(route & forbidden)
        adjacent={(x+dx,y+dy) for x,y in forbidden for dx,dy in ((0,0),(-1,0),(1,0),(0,-1),(0,1))}
        self.assertFalse(route & adjacent)


if __name__=='__main__':unittest.main()
