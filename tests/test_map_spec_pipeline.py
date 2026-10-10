import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from shapely.geometry import Polygon
from map_design_spec import validate_spec,resolve_spec,SpecificationError,json_schema
from map_composer import generate,validate
from map_layout import run,interpret
from playable_composition import compile_composition
from semantic_pipeline import digest

ROOT=Path(__file__).resolve().parents[1]

class SpecificationPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs={k:validate_spec(json.loads((ROOT/f'config/map-spec-{k}.json').read_text())) for k in ('compact','mid','interior')}
        cls.programs={k:generate(v,271828) for k,v in cls.specs.items()}
        cls.compiled={k:compile_composition(v) for k,v in cls.programs.items()}
        cls.reports={k:validate(cls.specs[k],v,cls.compiled[k]) for k,v in cls.programs.items()}

    def test_supported_demonstrations_pass_separate_gates(self):
        for r in self.reports.values():
            self.assertTrue(r['physical_pass']);self.assertTrue(r['request_pass']);self.assertFalse(r['timing_verified']);self.assertFalse(r['visually_accepted'])

    def test_unsupported_and_conflicting_requests_not_defaulted(self):
        for v in [{'gameplay':{'mid':'absent','secondary_access':'mid'}},{'architecture':{'verticality':'bridge'}},{'gameplay':{'sites':3}},{'seed':True},{'gameplay':{'sites':2.0}},{'gameplay':{'mid':'contested','secondary_access':'local'}}]:
            with self.assertRaises(SpecificationError):validate_spec(v)

    def test_auto_resolution_honors_explicit_requirements(self):
        s=validate_spec({'gameplay':{'secondary_access':'mid'}});v,log=resolve_spec(s,271828)
        self.assertEqual(v['gameplay']['mid'],'contested');self.assertTrue(log)

    def test_mid_is_physical_connectivity_change(self):
        a,b=self.programs['compact'],self.programs['mid']
        self.assertNotIn('Mid',a['annotations']);self.assertIn('Mid',b['annotations'])
        self.assertGreater(self.compiled['mid']['walkable'].symmetric_difference(self.compiled['compact']['walkable']).area,100)
        self.assertIsNone(self.reports['compact']['site_free_T_CT_path']);self.assertIsNotNone(self.reports['mid']['site_free_T_CT_path'])
        for s in ('A','B'):self.assertNotEqual(self.reports['mid']['actual_site_ingresses'][s]['primary'],self.reports['mid']['actual_site_ingresses'][s]['secondary'])

    def test_architecture_control_is_partition_not_label(self):
        a,b=self.programs['compact'],self.programs['interior']
        self.assertEqual(a['strategic_network'],b['strategic_network'])
        self.assertEqual(a['decision_log'][-1]['role_cells'],b['decision_log'][-1]['role_cells'])
        self.assertGreater(self.compiled['interior']['walls'].symmetric_difference(self.compiled['compact']['walls']).area,20)
        self.assertIn('A_vestibule',self.compiled['interior']['spaces']);self.assertNotIn('A_vestibule',self.compiled['compact']['spaces'])

    def test_deterministic_and_no_authored_builder_import(self):
        for k,s in self.specs.items():self.assertEqual(digest(generate(s,271828)),digest(self.programs[k]))
        source=(ROOT/'map_composer.py').read_text();self.assertNotIn('build001',source);self.assertNotIn('procedural_p04',source)

    def test_staged_control_allocates_real_investment_rooms(self):
        spec=copy.deepcopy(self.specs['compact']);spec['gameplay']['site_commitment']='staged';p=generate(spec,271828);c=compile_composition(p)
        self.assertIn('A_investment',p['annotations']);self.assertIn('B_investment',p['annotations'])
        self.assertGreater(c['walkable'].symmetric_difference(self.compiled['compact']['walkable']).area,5)

    def test_fixture_in_actual_aperture_rejected(self):
        p=copy.deepcopy(self.programs['compact']);o=p['openings'][0];x,y=o['aperture'][0];p['internal_masses'].append(dict(id='interference',boundary=[[x-.3,y-.3],[x+.3,y-.3],[x+.3,y+.3],[x-.3,y+.3]],height_source_units=160))
        c=compile_composition(p);r=validate(self.specs['compact'],p,c)
        self.assertFalse(r['physical_pass']);self.assertTrue(any('Aperture interference' in v for v in r['physical_violations']))

    def test_mid_label_does_not_make_blocked_mid_access_valid(self):
        p=copy.deepcopy(self.programs['mid']);ids=set(p['mid_spaces']);p['openings']=[o for o in p['openings'] if not ids.intersection(o['spaces'])]
        r=validate(self.specs['mid'],p,compile_composition(p));self.assertFalse(r['physical_pass'])

    def test_bounded_failure_has_diagnostic_and_history(self):
        s=copy.deepcopy(self.specs['compact']);s['hard_constraints']['maximum_main_route_HU']=256
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'failure';result=run(s,out,limit=1)
            self.assertEqual(result['total_attempts'],1);self.assertEqual(result['status'],'failed');self.assertTrue((out/'diagnostic.png').exists());self.assertTrue((out/'attempts.jsonl').exists());self.assertFalse((out/'clean.png').exists())

    def test_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):run(self.specs['compact'],Path(d),limit=1)

    def test_missing_credentials_explicit_no_keyword_fallback(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(SpecificationError,'OPENAI_API_KEY'):interpret('Make an unusual courtyard map',None)

    def test_structured_adapter_response_and_refusal(self):
        result={'specification':self.specs['mid'],'unsupported_requests':[],'interpretation_notes':[]}
        def adapter(payload):
            self.assertEqual(payload['text']['format']['type'],'json_schema');self.assertTrue(payload['text']['format']['strict']);return {'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}
        self.assertEqual(interpret('a contested mid with both connectors','test-model',adapter)['specification']['gameplay']['mid'],'contested')
        with self.assertRaises(SpecificationError):interpret('x','test-model',lambda payload:{'output':[{'content':[{'type':'refusal'}]}]})
        result['unsupported_requests']=['moving bridge']
        with self.assertRaisesRegex(SpecificationError,'moving bridge'):interpret('moving bridge','test-model',adapter)

if __name__=='__main__':unittest.main()
