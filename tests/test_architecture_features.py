from pathlib import Path
import unittest
import numpy as np

from architecture_features import FaceScanner, MeshIndex, face_triangles


class ArchitectureFeatureTests(unittest.TestCase):
    def test_fixture_face_loops_and_world_transform(self):
        scanner=FaceScanner()
        for line in (Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text().splitlines():scanner.feed(line)
        triangles,faces,spatial=scanner.geometry()
        self.assertEqual(len(faces),6)
        self.assertEqual(len(triangles),12)
        mesh=spatial['meshes'][0]
        np.testing.assert_allclose(triangles.min(axis=(0,1)),mesh['bounds']['min'])
        np.testing.assert_allclose(triangles.max(axis=(0,1)),mesh['bounds']['max'])
        self.assertTrue(all(f['material']=='materials/dev/reflectivity_30.vmat' for f in faces))

    def test_concave_face_triangulation_preserves_empty_corner(self):
        triangles,_,area,_=face_triangles([[0,0,0],[2,0,0],[2,1,0],[1,1,0],[1,2,0],[0,2,0]])
        self.assertEqual(area,3)
        index=MeshIndex(triangles)
        self.assertIsNone(index.ray([1.5,1.5,1],[0,0,-1],2)['hit_triangle'])
        self.assertIsNotNone(index.ray([.5,.5,1],[0,0,-1],2)['hit_triangle'])

    def test_ray_hits_are_double_sided_and_bounded(self):
        triangles,_,_,_=face_triangles([[10,-1,-1],[10,1,-1],[10,1,1],[10,-1,1]])
        index=MeshIndex(triangles)
        self.assertAlmostEqual(index.ray([0,0,0],[1,0,0],20)['distance_units'],10)
        self.assertAlmostEqual(index.ray([20,0,0],[-1,0,0],20)['distance_units'],10)
        self.assertIsNone(index.ray([0,0,0],[1,0,0],5)['hit_triangle'])

    def test_nonplanar_and_degenerate_faces_rejected(self):
        with self.assertRaises(ValueError):face_triangles([[0,0,0],[1,0,0],[2,0,0]])
        with self.assertRaises(ValueError):face_triangles([[0,0,0],[100,0,0],[100,100,20],[0,100,0]])


if __name__=='__main__':unittest.main()
