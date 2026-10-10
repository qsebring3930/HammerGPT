import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import combine, inspect_map, inspect_stream
from hammergpt import Element, parse, serialize


class CatalogTests(unittest.TestCase):
    def test_stream_matches_native_reference(self):
        text = (Path(__file__).parent / 'fixtures/box_light.vmap.txt').read_text(encoding='utf-8')
        _, roots = parse(text)
        full = inspect_map(roots, 'test')
        streamed = inspect_stream(text.splitlines(), 'test')
        self.assertEqual(streamed['node_types'], full['node_types'])
        self.assertEqual(streamed['assets'], full['assets'])
        for classname, entry in full['entities'].items():
            other = streamed['entities'][classname]
            self.assertEqual(other['count'], entry['count'])
            self.assertEqual(other['property_names'], entry['property_names'])
            self.assertEqual(other['examples'][0]['properties'], entry['examples'][0]['properties'])

    def test_nested_entities_assets_and_sample_limit(self):
        entities = []
        for i in range(5):
            props = Element('EditGameClassProps', {'classname': ('string', 'prop_static'), 'model': ('string', 'models/test.vmdl'), 'id': ('elementid', str(i))})
            entities.append(Element('CMapEntity', {'entity_properties': ('EditGameClassProps', props), 'nodeID': ('int', str(i))}))
        root = Element('CMapGroup', {'children': ('element_array', entities + ['external-prefab-id'])})
        record = inspect_map([root], 'example.vmap')
        entry = record['entities']['prop_static']
        self.assertEqual(entry['count'], 5)
        self.assertEqual(len(entry['examples']), 3)
        self.assertNotIn('id', entry['property_names'])
        self.assertEqual(record['assets'], ['models/test.vmdl'])
        result = combine([record], [{'source': 'broken', 'error': 'conversion failed'}])
        self.assertEqual(result['summary']['entity_instances'], 5)
        self.assertEqual(result['summary']['maps_failed'], 1)
        self.assertEqual(result['entity_classes']['prop_static']['maps'], ['example.vmap'])


if __name__ == '__main__':
    unittest.main()
