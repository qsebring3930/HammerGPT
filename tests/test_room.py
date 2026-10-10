import math
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hammergpt import create_room, get, parse, positions, serialize, walk


class RoomTests(unittest.TestCase):
    def test_element_array_reference_roundtrip(self):
        text = '<!-- test -->\n"Root"\n{\n"children" "element_array"\n[\n"element" "mesh-id",\n"element" ""\n]\n}\n'
        header, roots = parse(text)
        self.assertEqual(get(roots[0], 'children'), ['mesh-id', ''])
        self.assertEqual(parse(serialize(header, roots))[1], roots)

    def setUp(self):
        self.header, self.roots = parse((Path(__file__).parent / 'fixtures/box_light.vmap.txt').read_text(encoding='utf-8'))

    def test_room_bounds_and_identity(self):
        room = create_room(self.roots, 640, 384, 192, 16)
        world = get(next(r for r in room if r.kind == 'CMapRootElement'), 'world')
        nodes = get(world, 'children')
        bounds = []
        for mesh in nodes[:6]:
            origin = list(map(float, get(mesh, 'origin').split()))
            points = [list(map(float, p.split())) for p in get(positions(mesh), 'data')]
            bounds.append(tuple((min(p[i] for p in points) + origin[i], max(p[i] for p in points) + origin[i]) for i in range(3)))
        self.assertEqual(bounds[0], ((-336, 336), (-208, 208), (-16, 0)))
        self.assertEqual(bounds[1][2], (192, 208))
        self.assertEqual(bounds[2][0], (-336, -320))
        self.assertEqual(bounds[3][0], (320, 336))
        self.assertEqual(bounds[4][1], (-208, -192))
        self.assertEqual(bounds[5][1], (192, 208))
        self.assertEqual(get(nodes[6], 'origin'), '0 0 144')
        ids = [get(n, 'id') for r in room for n in walk(r) if 'id' in n.attrs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len({get(n, 'referenceID') for n in nodes}), 7)
        _, reread = parse(serialize(self.header, room))
        self.assertEqual(room, reread)
        original = get(next(r for r in self.roots if r.kind == 'CMapRootElement'), 'world')
        self.assertEqual(len(get(original, 'children')), 3)

    def test_invalid_dimensions(self):
        for dimension in (0, -1, math.nan, math.inf, 20000):
            with self.assertRaises(ValueError):
                create_room(self.roots, width=dimension)
        with self.assertRaises(ValueError):
            create_room(self.roots, thickness=256)

    def test_missing_cube(self):
        world = get(next(r for r in self.roots if r.kind == 'CMapRootElement'), 'world')
        world.attrs['children'] = ('element_array', [])
        with self.assertRaisesRegex(ValueError, 'Save a cube'):
            create_room(self.roots)


if __name__ == '__main__':
    unittest.main()
