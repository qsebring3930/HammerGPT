import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hammergpt import add_prop, create_room, get, parse, walk


class PropTests(unittest.TestCase):
    def setUp(self):
        _, roots = parse((Path(__file__).parent / 'fixtures/box_light.vmap.txt').read_text(encoding='utf-8'))
        self.room = create_room(roots)

    def test_append_preserves_map_and_clears_light_properties(self):
        result = add_prop(self.room, 'models/test_crate.vmdl', [216, 216, 0], [0, 45, 0], .5)
        world = get(next(r for r in result if r.kind == 'CMapRootElement'), 'world')
        original = get(next(r for r in self.room if r.kind == 'CMapRootElement'), 'world')
        children = get(world, 'children')
        self.assertEqual(children[:-1], get(original, 'children'))
        self.assertEqual(len(get(original, 'children')), 7)
        prop = children[-1]
        self.assertEqual(get(prop, 'origin'), '216 216 0')
        self.assertEqual(get(prop, 'angles'), '0 45 0')
        self.assertEqual(get(prop, 'scales'), '0.5 0.5 0.5')
        props = get(prop, 'entity_properties')
        self.assertEqual(get(props, 'classname'), 'prop_static')
        self.assertNotIn('brightness', props.attrs)
        ids = [get(n, 'id') for r in result for n in walk(r) if 'id' in n.attrs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_invalid_asset_and_transform(self):
        for model in ('../file.vmdl', 'models/../file.vmdl', 'models/file.txt'):
            with self.assertRaises(ValueError):
                add_prop(self.room, model, [0, 0, 0])
        for position in ([0, 0], [0, float('nan'), 0]):
            with self.assertRaises(ValueError):
                add_prop(self.room, 'models/crate.vmdl', position)


if __name__ == '__main__':
    unittest.main()
