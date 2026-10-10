import json,unittest
from pathlib import Path
from free_mid_layout import generate
from playable_composition import compile_composition
from map_composer import validate
from semantic_pipeline import digest

ROOT=Path(__file__).resolve().parents[1]
class FreeMidTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  folder=ROOT/'output/distributed-mid-001/r4/courts-handoff'
  cls.base=json.loads((folder/'composition.json').read_text())
  cls.spec=json.loads((folder/'resolved-specification.json').read_text())
  cls.p=generate(cls.base,cls.spec,1004821)
  cls.c=compile_composition(cls.p)
  cls.v=validate(cls.spec,cls.p,cls.c)
 def test_seed_reproduces_full_architectural_program(self):
  self.assertEqual(digest(self.p),digest(generate(self.base,self.spec,1004821)))
 def test_direct_anchor_links_include_real_gallery(self):
  for route in self.v['routes'].values():self.assertIsNotNone(route['path'])
 def test_retains_distinct_A_ingresses_and_B_handoff(self):
  self.assertTrue(self.v['request_pass'])
  a=self.v['actual_site_ingresses']['A'];self.assertNotEqual(a['primary'],a['secondary'])
  b=self.v['actual_site_ingresses']['B'];self.assertEqual(b['primary'],b['secondary'])
 def test_candidate_is_not_accepted_with_remaining_physical_failures(self):
  self.assertFalse(self.v['physical_pass'])
  self.assertIn('Disconnected walkable components',self.v['physical_violations'])
  self.assertIn('Opening below requested width: free_opening_14',self.v['physical_violations'])
  self.assertIn('Opening below requested width: free_opening_15',self.v['physical_violations'])

if __name__=='__main__':unittest.main()
