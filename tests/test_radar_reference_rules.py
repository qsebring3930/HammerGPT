import json,unittest,hashlib
from pathlib import Path
from map_composer import generate,validate
from playable_composition import compile_composition
from radar_reference_rules import RULES
ROOT=Path(__file__).resolve().parents[1]
class RadarReferenceTests(unittest.TestCase):
 def test_source_provenance_and_uncertainty_retained(self):
  lib=json.loads((ROOT/'config/radar-reference-observations.json').read_text())
  self.assertEqual(len(lib['observations']),18)
  self.assertEqual(lib['observations'][7]['duplicate_of'],'R07')
  for o in lib['observations']:
   self.assertIsNone(o['scale_metadata']);self.assertTrue(o['uncertainty'])
   self.assertEqual(hashlib.sha256((ROOT/o['source']).read_bytes()).hexdigest(),o['sha256'])
   for sample in o['samples']:
    self.assertTrue(all(0<=v<=1 for xy in sample['normalized_polygon'] for v in xy))
 def test_new_folded_arrangement_preserves_real_independent_entries(self):
  spec=json.loads((ROOT/'config/map-spec-compact.json').read_text());p=generate(spec,927611);v=validate(spec,p,compile_composition(p));roles=p['decision_log'][-1]['role_cells']
  self.assertEqual(roles['A'][0],0);self.assertEqual(roles['B'][1],4)
  self.assertTrue(v['physical_pass']);self.assertTrue(v['request_pass']);self.assertIsNone(v['site_free_T_CT_path'])
  for site in ['A','B']:
   ingress=v['actual_site_ingresses'][site];self.assertEqual(len(set(ingress.values())),3)
  self.assertEqual(p['reference_influences']['observation_library_sha256'],RULES['observation_library_sha256'])
 def test_legacy_compiler_behavior_and_spec_inputs_preserved(self):
  from playable_composition import compile_composition
  from map_design_spec import validate_spec
  folder=ROOT/'output/architecture-quality-001/after-r5/seed-884302'
  p=json.loads((folder/'composition.json').read_text());namespace={};exec((folder/'source/playable_composition.py').read_text(),namespace)
  old=namespace['compile_composition'](p);new=compile_composition(p)
  for key in ['walkable','solid','walls']:self.assertTrue(old[key].equals(new[key]))
  spec=validate_spec(json.loads((folder/'specification.json').read_text()))
  self.assertEqual(spec['gameplay']['mid'],'absent');self.assertEqual(spec['soft_preferences']['route_complexity'],.5)
if __name__=='__main__':unittest.main()
