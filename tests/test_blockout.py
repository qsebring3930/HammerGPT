import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from blockout import corridor,create_blockout
from hammergpt import get,parse,positions
from planner import propose


class BlockoutTests(unittest.TestCase):
    def test_planner_connections_have_buildable_ramp_clearance(self):
        profile={'name':'Vertigo','map_source':'map','nav_source':'nav',
                 'measurements':{'nav_center_z_p10_p90_span_units':302,
                                 'nav_center_x_span_units':2700,'nav_center_y_span_units':2700},
                 'top_prop_models':[],'top_material_references':[],'example_routes':[]}
        for prompt in ('compact vertical industrial map','vertical industrial map','industrial map'):
            plan=propose(prompt,[profile]); design=plan['design_choices']
            nodes={n['id']:n for n in design['regions']}
            for edge in design['connections']:
                corridor(nodes[edge['source']],nodes[edge['target']])

    def test_ramp_meets_both_room_edges(self):
        a={'center':[0,0,0],'size':[256,256,256]}
        b={'center':[1024,0,128],'size':[256,256,256]}
        p,q,length,yaw,slope=corridor(a,b)
        self.assertEqual(p,[128,0,0])
        self.assertEqual(q,[896,0,128])
        self.assertAlmostEqual(slope*length,128)
        self.assertEqual(yaw,0)

    def test_steep_ramp_rejected(self):
        with self.assertRaisesRegex(ValueError,'steep'):
            corridor({'center':[0,0,0],'size':[64,64,256]},
                     {'center':[128,0,256],'size':[64,64,256]})

    def test_mesh_ramp_top_matches_landing_heights(self):
        _,roots=parse((Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text())
        plan={'design_choices':{'corridor_width_units':192,'regions':[
            {'id':'A','center':[0,0,0],'size':[256,256,256]},
            {'id':'B','center':[1024,0,128],'size':[256,256,256]}],
            'connections':[{'source':'A','target':'B'}]}}
        result,manifest=create_blockout(roots,plan)
        world=get(next(r for r in result if r.kind=='CMapRootElement'),'world')
        mesh=get(world,'children')[2]
        origin=list(map(float,get(mesh,'origin').split()))
        pts=[list(map(float,p.split())) for p in get(positions(mesh),'data')]
        for x in (-384,384):
            top=max(p[2]+origin[2] for p in pts if p[0]==x)
            self.assertAlmostEqual(top,0 if x<0 else 128,places=4)
        self.assertEqual(len(manifest),3)
