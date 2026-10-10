import json
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from reconstruct_train_section import SectionScanner, nav_section, select_triangles, write_glb, slice_segments
from audit_train_reconstruction import sample_nav

class SectionReconstructionTests(unittest.TestCase):
    def test_repeated_node_ids_do_not_drop_meshes(self):
        text=(Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text()
        scanner=SectionScanner(np.array([[-10000]*3,[10000]*3]))
        for line in (text+'\n'+text).splitlines():scanner.feed(line)
        triangles,faces,spatial=scanner.geometry()
        self.assertEqual(len(triangles),24)
        self.assertEqual(len({f['node_id'] for f in faces}),2)
        self.assertEqual(len({e['node_id'] for e in spatial['entities']}),len(spatial['entities']))

    def test_elevation_directed_edges_and_external_ports_retained(self):
        def area(k,z,x=0):return {'id':k,'hull':0,'movable_mesh_id':0xffffffff,
            'corners':[[x,0,z],[x+50,0,z],[x+50,50,z],[x,50,z]],'flags':k,
            'connections':[],'ladders_above':[7] if k==1 else [],'ladders_below':[]}
        a,b,c=area(1,-200),area(2,100),area(3,0,5000)
        a['connections']=[{'target':2,'source_edge':0,'target_edge':2}]
        c['connections']=[{'target':1,'source_edge':3,'target_edge':1}]
        section=nav_section({'areas':[a,b,c],'ladder_count':1})
        self.assertEqual(section['areas'],[a,b])
        self.assertEqual(len(section['directed_connections']),1)
        self.assertEqual(section['boundary_connections'][0]['direction'],'incoming')
        self.assertEqual(section['ladder_references'][0]['above'],[7])

    def test_glb_preserves_3d_coordinates_and_separate_layers(self):
        t=np.array([[[1,2,3],[10,2,3],[1,2,12]]],dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'section.glb';write_glb(p,t,t,np.empty((0,3,3)))
            raw=p.read_bytes();magic,version,total=struct.unpack_from('<III',raw)
            self.assertEqual((magic,version,total),(0x46546c67,2,len(raw)))
            size,_=struct.unpack_from('<II',raw,12);doc=json.loads(raw[20:20+size])
            self.assertEqual(len(doc['meshes']),2)
            positions=np.frombuffer(raw,dtype='<f4',count=9,offset=20+size+8).reshape(3,3)
            np.testing.assert_array_equal(positions,np.stack([t[0,:,0],t[0,:,2],-t[0,:,1]],axis=1))

    def test_triangle_selection_never_flattens_or_clips(self):
        t=np.array([[[0,0,-200],[2000,0,100],[0,50,-200]],[[5000,0,0],[5001,0,0],[5001,1,0]]])
        np.testing.assert_array_equal(select_triangles(t),[True,False])
        np.testing.assert_array_equal(t[select_triangles(t)][0],t[0])

    def test_layered_input_keeps_stacked_surfaces_and_small_areas(self):
        a={'id':1,'corners':[[0,0,0],[32,0,32],[32,32,32],[0,32,0]]}
        b={'id':2,'corners':[[0,0,128],[32,0,128],[32,32,128],[0,32,128]]}
        c={'id':3,'corners':[[1,1,200],[2,1,200],[2,2,200],[1,2,200]]}
        samples,fallback=sample_nav([a,b,c])
        self.assertEqual(samples[:,0].tolist(),[1,2])
        self.assertEqual(samples[:,3].tolist(),[16,128])
        self.assertEqual(fallback[:,0].tolist(),[3])

    def test_height_slice_intersects_walls_without_floor_triangle_edges(self):
        t=np.array([[[0,0,-10],[0,10,-10],[0,0,10]],[[0,0,-20],[10,0,-20],[0,10,-20]]])
        lines=slice_segments(t,0)
        self.assertEqual(len(lines),1)
        np.testing.assert_allclose(np.asarray(lines)[:,:,2],0)

if __name__=='__main__':unittest.main()
