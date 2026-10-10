import copy,json,unittest
from pathlib import Path
import networkx as nx
from map_design_spec import validate_spec,mid_strategy,SpecificationError
from map_composer import generate,validate
from playable_composition import compile_composition
ROOT=Path(__file__).resolve().parents[1]
class DistributedMidTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.specs={};cls.programs={};cls.reports={}
  for name in ('street','courts-handoff'):
   s=validate_spec(json.loads((ROOT/f'output/distributed-mid-001/{name}-spec.json').read_text()));p=generate(s,s['seed']);cls.specs[name]=s;cls.programs[name]=p;cls.reports[name]=validate(s,p,compile_composition(p))
 def test_street_is_one_space_not_two_role_rooms(self):
  p=self.programs['street'];self.assertEqual(p['mid_spaces'],['mid_street']);self.assertTrue(self.reports['street']['physical_pass'])
 def test_mid_branches_have_intermediate_territory(self):
  for p in self.programs.values():
   g=nx.Graph()
   for route in p['strategic_network'].values():g.add_edges_from(zip(map(tuple,route),map(tuple,route[1:])))
   for site,b in p['mid_program']['branches'].items():
    route=p['strategic_network']['Mid-'+site];tail=route[route.index(b['branch_node']):];self.assertGreaterEqual(len(tail),4)
    self.assertLessEqual(g.degree(tuple(b['branch_node'])),3)
 def test_handoff_has_two_arrivals_but_one_final_entry(self):
  v=self.reports['courts-handoff'];self.assertTrue(v['physical_pass']);self.assertTrue(v['request_pass']);self.assertEqual(len(v['handoff_junctions']),1)
  for j in v['handoff_junctions'].values():self.assertNotEqual(j['primary_arrival'],j['mid_arrival']);self.assertEqual(j['counted_final_entries'],1)
 def test_undeclared_handoff_rejected(self):
  s=copy.deepcopy(self.specs['courts-handoff']);s['gameplay']['mid_access_mode']='separate_entries';p=self.programs['courts-handoff'];v=validate(s,p,compile_composition(p));self.assertFalse(v['request_pass'])
 def test_strategic_choice_fixed_across_spatial_attempts(self):
  s=self.specs['courts-handoff'];self.assertEqual(mid_strategy(s,1),mid_strategy(s,2))
  p=self.programs['courts-handoff'];self.assertEqual(p['mid_handoffs'],[mid_strategy(s,s['seed'])['handoff_site']])
 def test_absent_mid_conflict_reported(self):
  with self.assertRaises(SpecificationError):validate_spec({'gameplay':{'mid':'absent','mid_access_mode':'one_approach_handoff'}})
