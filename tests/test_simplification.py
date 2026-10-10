from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simplify_section import boundary,simple,simplify,signed_area,triangulate,plan_simplification
from extract_sections import inside
from surface_geometry import create_surface_blockout
from hammergpt import parse


class SimplificationTests(unittest.TestCase):
    def test_concave_floor_triangulation_preserves_area(self):
        points=[[0,0],[256,0],[256,128],[128,128],[128,256],[0,256]]
        triangles=triangulate(points)
        self.assertEqual(len(triangles),len(points)-2)
        self.assertAlmostEqual(sum(signed_area([points[i] for i in t]) for t in triangles),signed_area(points))
        self.assertFalse(simple([[0,0],[128,128],[0,128],[128,0]]))

    def test_zero_tolerance_removes_only_collinear_vertices(self):
        points=[[0,0],[64,0],[128,0],[128,128],[0,128]]
        result=simplify(points,[[64,64]],0)
        self.assertEqual(len(result),4)
        self.assertEqual(signed_area(result),signed_area(points))

    def test_holes_are_rejected_instead_of_filled(self):
        cells={(x,y) for x in range(3) for y in range(3)}-{(1,1)}
        with self.assertRaisesRegex(ValueError,'holes'): boundary(cells)

    def test_route_markers_and_generated_mesh_survive_smoothing(self):
        cells={(x,y) for x in range(5) for y in range(3)}|{(5,1)}
        plan={'design_choices':{'floor_cell_override':[list(c) for c in cells],
              'regions':[{'id':'Marker','center':[352,96,0],'size':[64,64,256]}],
              'connections':[],'corridor_width_units':192},'adaptations':[]}
        clean=plan_simplification(plan)
        outline=clean['design_choices']['floor_polygon_override']
        self.assertTrue(inside(352,96,outline))
        self.assertLessEqual(abs(signed_area(outline)/signed_area(boundary(cells))-1),.15)
        _,roots=parse((Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text())
        _,manifest,stats=create_surface_blockout(roots,clean)
        self.assertEqual(len(manifest),1)
        self.assertEqual(stats['faces'],2*len(outline)-2)
