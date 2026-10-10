import json,unittest
from pathlib import Path
from organify_layout import relax
from map_composer import validate
from playable_composition import compile_composition
from semantic_pipeline import digest
ROOT=Path(__file__).resolve().parents[1]
class OrganicCompositionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  f=ROOT/'output/mid-frontage-001/after-r1/seed-974021';cls.base=json.loads((f/'composition.json').read_text());cls.spec=json.loads((f/'resolved-specification.json').read_text());cls.p=relax(cls.base,cls.spec,974021);cls.c=compile_composition(cls.p);cls.v=validate(cls.spec,cls.p,cls.c)
 def test_keeps_topology_and_physical_gates(self):
  self.assertEqual(self.base['strategic_network'],self.p['strategic_network'])
  self.assertEqual([o['spaces'] for o in self.base['openings']],[o['spaces'] for o in self.p['openings']])
  self.assertTrue(self.v['physical_pass']);self.assertTrue(self.v['request_pass'])
 def test_retains_aperture_widths_after_compression(self):
  from shapely.geometry import LineString
  before={o['id']:LineString(o['aperture']).length*32 for o in self.base['openings']}
  for row in self.v['opening_widths']:self.assertAlmostEqual(row['actual_HU'],before[row['id']],places=4)
 def test_changes_complete_movement_without_mutating_source(self):
  before=digest(self.base);b=validate(self.spec,self.base,compile_composition(self.base))
  self.assertLess(self.v['routes']['T-A-main']['path']['length_HU'],b['routes']['T-A-main']['path']['length_HU'])
  self.assertEqual(before,digest(self.base))
 def test_reproducible_second_pass(self):self.assertEqual(digest(self.p),digest(relax(self.base,self.spec,974021)))
