import copy
import json
import unittest
from pathlib import Path
from shapely.geometry import box
from map_design_spec import validate_spec,json_schema
from map_composer import generate,validate
from map_architecture_metrics import assess
from playable_composition import compile_composition

ROOT=Path(__file__).resolve().parents[1]

class ArchitectureMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=validate_spec(json.loads((ROOT/'config/map-spec-compact.json').read_text()))
        cls.p=generate(cls.spec,884201);cls.c=compile_composition(cls.p);cls.v=validate(cls.spec,cls.p,cls.c)

    def test_soft_compact_failure_does_not_change_gates(self):
        self.assertTrue(self.v['physical_pass']);self.assertTrue(self.v['request_pass']);self.assertFalse(self.v['compactness']['achieved'])
        failures=[r['measurement'] for r in self.v['compactness']['checks'] if not r['achieved']]
        self.assertIn('T-A-main',failures);self.assertIn('T-A-secondary',failures)

    def test_connector_is_subset_not_complete_distance(self):
        rows=self.v['compactness']['route_distances']
        for r in rows:self.assertLessEqual(r['connector_only_HU'],r['complete_ordered_HU']+1e-5)
        rotation=next(r for r in rows if r['route']=='CT-rotate')
        self.assertGreater(rotation['complete_ordered_HU']-rotation['connector_only_HU'],500)

    def test_repeated_connector_traversal_counted_as_walked_distance(self):
        p={'spaces':[{'id':'circulation_gallery_0'}],'defender_positions':{}}
        c={'spaces':{'circulation_gallery_0':box(-1,-1,6,1)},'walkable':box(-1,-1,6,1)}
        v={'routes':{'T-A-main':{'path':{'points':[[0,0],[5,0],[0,0],[5,0]],'length_HU':480},'unrestricted_shortest_length_HU':160}}}
        r=assess(self.spec,p,c,v)['route_distances'][0]
        self.assertEqual(r['connector_only_HU'],480)

    def test_corner_masses_not_repeated_and_cover_does_not_block_entries(self):
        self.assertFalse(any(m['height_source_units']>=160 for m in self.p['internal_masses']))
        self.assertTrue(self.v['physical_pass'])
        self.assertEqual(len(self.c['walkable'].geoms) if hasattr(self.c['walkable'],'geoms') else 1,1)

    def test_only_authorized_complexity_control_added(self):
        old=json.loads((ROOT/'output/specification-to-image-003/compact/specification-schema.json').read_text())
        current=json_schema()
        self.assertIn('route_complexity',current['properties']['soft_preferences']['properties'])
        del current['properties']['soft_preferences']['properties']['route_complexity']
        current['properties']['soft_preferences']['required'].remove('route_complexity')
        del current['properties']['gameplay']['properties']['mid_organization']
        current['properties']['gameplay']['required'].remove('mid_organization')
        del current['properties']['gameplay']['properties']['mid_access_mode']
        current['properties']['gameplay']['required'].remove('mid_access_mode')
        self.assertEqual(current,old)

if __name__=='__main__':unittest.main()
