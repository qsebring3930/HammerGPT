from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hammergpt import get,parse,serialize,walk
from surface_geometry import make_surface,validate_topology,create_surface_blockout
from test_connected_geometry import proposal


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.header,self.roots=parse((Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text())
        self.cube=next(n for r in self.roots for n in walk(r) if n.kind=='CMapMesh')

    def test_single_quad_has_one_face_and_open_boundary(self):
        mesh=make_surface(self.cube,100,[[(0,0,0),(64,0,0),(64,64,0),(0,64,0)]])
        self.assertEqual(validate_topology(mesh),{'vertices':4,'faces':1,'half_edges':8,'boundary_half_edges':4})
        data=get(mesh,'meshData'); corner=get(data,'faceVertexData')
        normals=get(next(s for s in get(corner,'streams') if get(s,'semanticName')=='normal'),'data')
        self.assertTrue(all(n=='0 0 1' for n in normals))

    def test_adjacent_faces_share_vertices_and_edge(self):
        mesh=make_surface(self.cube,100,[[(0,0,0),(64,0,0),(64,64,0),(0,64,0)],
                                      [(64,0,0),(128,0,16),(128,64,16),(64,64,0)]])
        stats=validate_topology(mesh)
        self.assertEqual(stats['vertices'],6)
        self.assertEqual(stats['boundary_half_edges'],6)
        _,checked=parse(serialize(self.header,[mesh]))
        self.assertEqual(mesh,checked[0])

    def test_duplicate_or_reversed_topology_is_rejected(self):
        face=[(0,0,0),(64,0,0),(64,64,0),(0,64,0)]
        with self.assertRaisesRegex(ValueError,'winding'):
            make_surface(self.cube,100,[face,face])

    def test_walls_point_into_walkable_floor(self):
        result,manifest,stats=create_surface_blockout(self.roots,proposal())
        mesh=next(n for r in result for n in walk(r) if n.kind=='CMapMesh')
        data=get(mesh,'meshData'); corner=get(data,'faceVertexData')
        normals=get(next(s for s in get(corner,'streams') if get(s,'semanticName')=='normal'),'data')
        points=[list(map(float,p.split())) for p in get(get(get(data,'vertexData'),'streams')[0],'data')]
        ends=list(map(int,get(data,'edgeVertexIndices')))
        faces=list(map(int,get(data,'edgeFaceIndices')))
        from connected_geometry import floor_cells,GRID
        cells=floor_cells(proposal())
        for e,fi in enumerate(faces):
            if fi<0: continue
            n=list(map(float,normals[e].split())); p=points[ends[e]]
            if abs(n[2])<.001:
                # Move inward from the wall's edge midpoint, avoiding cell corners.
                nxt=int(get(data,'edgeNextIndices')[e]); q=points[ends[nxt]]
                if p[0]==q[0] and p[1]==q[1]: continue
                x=(p[0]+q[0])/2+n[0]; y=(p[1]+q[1])/2+n[1]
                self.assertIn((int(x//GRID),int(y//GRID)),cells)
            else: self.assertGreater(n[2],0)
        self.assertEqual(stats['floor_components'],1)
        self.assertEqual(len(manifest),1)
