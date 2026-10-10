from pathlib import Path
import unittest
import numpy as np

from model_geometry import descriptor, entity_frames, transformed, resolve_source, dmx_meshes
from hammergpt import Element, serialize
from prop_observations import PropIndex


class ModelGeometryTests(unittest.TestCase):
    def test_dmx_mapping_and_counted_degenerate_face(self):
        state=Element('DmeVertexData',{'id':('elementid','state'),
             'position$0':('vector3_array',['0 0 0','1 0 0','0 1 0']),
             'position$0Indices':('int_array',['2','0','1'])})
        material=Element('DmeMaterial',{'id':('elementid','material'),'mtlName':('string','test.vmat')})
        face=Element('DmeFaceSet',{'id':('elementid','faces'),'faces':('int_array',['0','1','2','-1','0','0','0','-1']),
                                 'material':('DmeMaterial',material)})
        mesh=Element('DmeMesh',{'id':('elementid','mesh'),'name':('string','draw0'),
                              'currentState':('DmeVertexData',state),'faceSets':('element_array',[face])})
        result=dmx_meshes(serialize('<!-- dmx encoding keyvalues2 4 format model 22 -->',[mesh]))['draw0']
        self.assertEqual(len(result[0]),1)
        self.assertEqual(result[1],['test.vmat'])
        self.assertEqual(result[2],1)
        np.testing.assert_allclose(result[0][0,0],[0,1,0])
        duplicate=serialize('<!-- dmx encoding keyvalues2 4 format model 22 -->',[mesh,mesh])
        with self.assertRaises(ValueError):dmx_meshes(duplicate)
        retained=dmx_meshes(duplicate,merge_duplicate_names=True)['draw0']
        self.assertEqual(len(retained[0]),2)
        self.assertEqual(retained[1],['test.vmat','test.vmat'])
        self.assertEqual(retained[2],2)

    def test_prop_ray_culls_other_height_and_respects_limit(self):
        triangles=np.array([[[10,-1,-1],[10,1,-1],[10,0,1]],[[5,-1,99],[5,1,99],[5,0,101]]])
        index=PropIndex(triangles)
        self.assertAlmostEqual(index.ray([0,0,0],[1,0,0],20)['distance_units'],10)
        self.assertIsNone(index.ray([0,0,0],[1,0,0],8))

    def test_descriptor_filter_and_translation(self):
        mesh,translation,_=descriptor('''{rootNode={_class="RootNode" children=[
        {_class="RenderMeshFile" filename="mesh.dmx" import_filter={exclude_by_default=true exception_list=["draw1",]}},
        {_class="ModelModifier_Translate" translation=[1,2,-3]},]}}''')
        self.assertEqual(mesh['import_filter']['exception_list'],['draw1'])
        np.testing.assert_equal(translation,[1,2,-3])

    def test_unsupported_modifier_is_rejected(self):
        with self.assertRaises(ValueError):descriptor('{rootNode={_class="ModelModifier_Rotate"}}')

    def test_render_only_physics_descriptor_does_not_claim_collision(self):
        text='{rootNode={_class="RootNode" children=[{_class="RenderMeshFile" filename="mesh.dmx"},{_class="PhysicsHullFile" filename="physics.dmx"}]}}'
        with self.assertRaises(ValueError):descriptor(text)
        mesh,_,classes=descriptor(text,allow_physics=True)
        self.assertEqual(mesh['filename'],'mesh.dmx')
        self.assertIn('PhysicsHullFile',classes)

    def test_entity_frames_capture_exact_transforms(self):
        text='''"CMapEntity"
{
"nodeID" "int" "5"
"origin" "vector3" "10 20 30"
"angles" "qangle" "0 90 0"
"scales" "vector3" "2 3 4"
"entity_properties" "EditGameClassProps"
{
"classname" "string" "prop_static"
"model" "string" "model.vmdl"
}
}'''
        result=entity_frames(text.splitlines())['5']
        self.assertEqual(result['angles'],[0,90,0])
        self.assertEqual(result['scales'],[2,3,4])
        self.assertEqual(result['properties']['model'],'model.vmdl')

    def test_descriptor_translation_before_entity_rotation(self):
        triangles=np.array([[[0,0,0],[1,0,0],[0,1,0]]])
        result=transformed(triangles,[2,0,0],{'origin':[10,0,0],'angles':[0,90,0],'scales':[2,2,2]})
        np.testing.assert_allclose(result[0],[[10,4,0],[10,6,0],[8,4,0]],atol=1e-5)

    def test_no_path_escape(self):
        for path in ('../mesh.dmx','C:/mesh.dmx','/mesh.dmx'):
            with self.assertRaises(ValueError):resolve_source(path,[Path('.')])


if __name__=='__main__':unittest.main()
