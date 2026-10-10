import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_map import SpatialScanner, resolve_anchor_hulls, transform, vpk_paths
from hammergpt import Element, create_room, get, parse, serialize


class AnalysisTests(unittest.TestCase):
    def test_hostage_entity_is_a_gameplay_anchor(self):
        text=(Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text().replace('light_omni2','hostage_entity')
        scanner=SpatialScanner()
        for line in text.splitlines():
            scanner.feed(line)
        anchors=scanner.finish()['gameplay_anchors']
        self.assertTrue(any(a['classname']=='hostage_entity' for a in anchors))

    def test_shared_mesh_reference_and_selection_set(self):
        text = '''"CMapEntity"
{
 "id" "elementid" "entity"
 "nodeID" "int" "1"
 "children" "element_array"
 [
  "element" "mesh"
 ]
 "origin" "vector3" "10 20 30"
 "entity_properties" "EditGameClassProps"
 {
  "classname" "string" "env_cs_place"
  "place_name" "string" "Middle"
 }
}
"CMapSelectionSet"
{
 "id" "elementid" "selection"
 "children" "element_array"
 [
  "element" "mesh"
 ]
}
"CMapMesh"
{
 "id" "elementid" "mesh"
 "nodeID" "int" "2"
 "origin" "vector3" "10 20 30"
 "stream" "CDmePolygonMeshDataStream"
 {
  "semanticName" "string" "position"
  "data" "vector3_array"
  [
   "0 0 0",
   "2 4 6"
  ]
 }
}
'''
        scanner = SpatialScanner()
        for line in text.splitlines():
            scanner.feed(line)
        data = scanner.finish()
        self.assertEqual(data['ambiguous_shared_node_parents'], 0)
        self.assertEqual(data['meshes'][0]['owner_entity'], '1')
        self.assertEqual(data['gameplay_anchors'][0]['geometry_bounds'], {'min': [10, 20, 30], 'max': [12, 24, 36]})

    def test_generated_room_bounds(self):
        header, roots = parse((Path(__file__).parent / 'fixtures/box_light.vmap.txt').read_text())
        room = create_room(roots)
        scanner = SpatialScanner()
        for line in serialize(header, room).splitlines():
            scanner.feed(line)
        result = scanner.finish()
        self.assertEqual(result['mesh_count'], 6)
        self.assertEqual(result['vertex_count'], 48)
        self.assertEqual(result['mesh_bounds'], {'min': [-272, -272, -16], 'max': [272, 272, 272]})
        self.assertEqual(result['entities'][0]['position'], [0, 0, 192])

    def test_group_membership_does_not_double_world_transform(self):
        header, roots = parse((Path(__file__).parent / 'fixtures/box_light.vmap.txt').read_text())
        room = create_room(roots)
        world = get(next(r for r in room if r.kind == 'CMapRootElement'), 'world')
        group = Element('CMapGroup', {'children': ('element_array', get(world, 'children')),
                                     'origin': ('vector3', '100 200 300'), 'angles': ('qangle', '0 90 0')})
        world.attrs['children'] = ('element_array', [group])
        scanner = SpatialScanner()
        for line in serialize(header, room).splitlines():
            scanner.feed(line)
        result = scanner.finish()
        self.assertEqual(result['entities'][0]['position'], [0, 0, 192])
        for a, b in zip(result['mesh_bounds']['min'], [-272, -272, -16]):
            self.assertAlmostEqual(a, b)

    def test_vpk_directory_with_preload(self):
        tree = b'vmdl_c\0models\0crate\0' + struct.pack('<IHHIIH', 0, 3, 0x7fff, 0, 0, 0xffff) + b'abc' + b'\0\0\0'
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'example_dir.vpk'
            file.write_bytes(struct.pack('<III', 0x55aa1234, 1, len(tree)) + tree)
            self.assertEqual(list(vpk_paths(file)), ['models/crate.vmdl_c'])

    def test_yaw_scale_translation(self):
        point = transform([1, 0, 0], {'scales': [2, 2, 2], 'angles': [0, 90, 0], 'origin': [10, 20, 30]})
        for a, b in zip(point, [10, 22, 30]):
            self.assertAlmostEqual(a, b)

    def test_material_array_references(self):
        scanner = SpatialScanner()
        root = Element('Root', {'materials': ('string_array', ['materials/a.vmat', 'materials/b.vmat'])})
        for line in serialize('<!-- test -->', [root]).splitlines():
            scanner.feed(line)
        self.assertEqual(scanner.finish()['material_references'], {'materials/a.vmat': 1, 'materials/b.vmat': 1})

    def test_decompiled_anchor_hull(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            addon = temp / 'addon'
            (addon / 'models').mkdir(parents=True)
            (addon / 'models/volume.vmdl').write_text('filename = "models/volume_hull.dmx"')
            (addon / 'models/volume_hull.dmx').write_bytes(b'placeholder')
            anchor = {'node_id': '7', 'classname': 'func_bomb_target', 'properties': {'model': 'models/volume.vmdl'}, 'geometry_bounds': None}
            spatial = {'gameplay_anchors': [anchor]}
            vertices = Element('DmeVertexData', {'position$0': ('vector3_array', ['0 0 0', '32 64 16'])})
            def fake_convert(exe, source, output, encoding):
                output.write_text(serialize('<!-- test -->', [vertices]))
            with patch('analyze_map.convert', fake_convert):
                resolve_anchor_hulls(spatial, [{'nodeID': '7', 'origin': [10, 20, 30]}], temp, addon, temp)
            self.assertEqual(anchor['geometry_bounds'], {'min': [10, 20, 30], 'max': [42, 84, 46]})


if __name__ == '__main__':
    unittest.main()
