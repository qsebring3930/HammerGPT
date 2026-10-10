import copy,json,unittest
from pathlib import Path
from shapely.geometry import box,Point
from route_composition import program,assemble
from map_design_spec import validate_spec
from map_composer import generate,validate
from playable_composition import compile_composition

ROOT=Path(__file__).resolve().parents[1]
class RouteCompositionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.spec=validate_spec(json.loads((ROOT/'config/map-spec-compact.json').read_text()))
  cls.p=generate(cls.spec,927611);cls.c=compile_composition(cls.p)
 def test_many_to_many_roles_have_physical_support(self):
  roles={r['id']:r for r in self.p['role_bindings']}
  self.assertGreater(len(roles['A-main']['spaces']),3)
  self.assertEqual(roles['A-staging']['spaces'],roles['A-execute']['spaces'])
  self.assertTrue(all(r['connected_support'] for r in validate(self.spec,self.p,self.c)['role_support_checks']))
 def test_callout_text_does_not_allocate_geometry(self):
  p=copy.deepcopy(self.p)
  for r in p['role_bindings']:r['callout']='Secret'
  c=compile_composition(p)
  self.assertTrue(c['walkable'].equals(self.c['walkable']))
  self.assertEqual(p['openings'],self.p['openings'])
 def test_disconnected_role_is_rejected(self):
  p=copy.deepcopy(self.p);p['role_bindings'][0]['spaces']=['A_site','B_site']
  # IDs come from annotations' containing spaces, not assumed names.
  p['role_bindings'][0]['spaces']=[next(sid for sid,g in self.c['spaces'].items() if g.covers(Point(p['annotations'][x]['point']))) for x in ('A','B')]
  v=validate(self.spec,p,self.c)
  self.assertFalse(v['request_pass']);self.assertTrue(v['physical_pass'])
 def test_low_complexity_preserves_straight_profile(self):
  spec=copy.deepcopy(self.spec);spec['soft_preferences']['route_complexity']=0
  episodes,sequences=program(self.p['strategic_network'],{},spec,927611)
  self.assertFalse(episodes);self.assertTrue(all(s['profile']=='frontage-street' for s in sequences.values()))
 def test_high_complexity_changes_actual_split_connectivity(self):
  spec=copy.deepcopy(self.spec);spec['soft_preferences']['route_complexity']=1
  p=generate(spec,927611)
  for site in ('A','B'):
   main=p['strategic_network']['T-'+site+'-main'];alt=p['strategic_network']['local-'+site]
   self.assertEqual(alt[0],main[-3] if len(main)>=4 else main[-2])
   self.assertNotEqual(alt[0],main[-2])
 def test_building_wrap_preserves_exclusion_and_shared_boundaries(self):
  parts,openings,center,building=assemble({'profile':'building-wrap'},box(0,0,24,24),[(1,0),(-1,0)],[12,12],4)
  from shapely.ops import unary_union
  self.assertTrue(unary_union([g for _,g in parts]).equals(box(0,0,24,24).difference(building)))
  self.assertTrue(any(g.covers(Point(center)) for _,g in parts))
  for a,b,line in openings:self.assertGreater(line.length,0);self.assertTrue(dict(parts)[a].boundary.covers(line));self.assertTrue(dict(parts)[b].boundary.covers(line))
 def test_polygon_hole_is_not_walkable(self):
  p={'spaces':[{'id':'court','boundary':list(box(0,0,24,24).exterior.coords),'holes':[list(box(9,9,15,15).exterior.coords)]}],
     'envelope':list(box(-1,-1,25,25).exterior.coords),'boundary_thickness':.3,'openings':[],'internal_masses':[]}
  c=compile_composition(p);self.assertFalse(c['walkable'].covers(Point(12,12)));self.assertTrue(c['solid'].covers(Point(12,12)))
