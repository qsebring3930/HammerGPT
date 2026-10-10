import copy
import json
import unittest
from pathlib import Path

from shapely.geometry import LineString,Point,box
from playable_composition import compile_composition,DerivedNavigation,observed_openings
from p04_space_mass_demo import program,directed_delta,site_ingress
from semantic_pipeline import digest,SpatialEmbedder,GameplayValidator

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/p04-playable-composition-001'


class PlayableCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=program();cls.c=compile_composition(cls.p)
        cls.r=json.loads((OUT/'validation.json').read_text())

    def test_walkable_and_solid_partition_envelope(self):
        self.assertAlmostEqual(self.c['walkable'].intersection(self.c['solid']).area,0)
        self.assertAlmostEqual(self.c['walkable'].union(self.c['solid']).area,self.c['envelope'].area)
        self.assertFalse(self.c['walkable'].covers(Point(73,57)))

    def test_annotations_add_no_floor(self):
        p=copy.deepcopy(self.p);p['annotations']={};p['allocations']=[]
        self.assertTrue(compile_composition(p)['walkable'].equals(self.c['walkable']))

    def test_opening_must_be_on_actual_shared_boundary(self):
        p=copy.deepcopy(self.p);p['openings'][0]['aperture']=[[70,50],[75,50]]
        with self.assertRaises(ValueError):compile_composition(p)

    def test_overlapping_partition_rejected(self):
        p=copy.deepcopy(self.p);p['spaces'][0]['boundary']=[[15,5],[122,5],[122,50],[15,50]]
        with self.assertRaises(ValueError):compile_composition(p)

    def test_undeclared_hole_detected_from_free_space(self):
        c=dict(self.c);c['walkable']=c['walkable'].union(box(47,64.5,49,66.5))
        self.assertTrue(observed_openings(self.p,c)['unintended_openings'])
        self.assertFalse(observed_openings(self.p,self.c)['unintended_openings'])

    def test_closing_opening_changes_navigation(self):
        nav=DerivedNavigation(self.c);closed=DerivedNavigation(self.c,blocked=box(20,57,30,59))
        start,end=[25,56],[25,60]
        direct=nav.path(start,end);detour=closed.path(start,end)
        self.assertIsNotNone(direct);self.assertIsNotNone(detour)
        self.assertGreater(detour['length'],direct['length']+20)

    def test_every_measured_route_stays_inside_actual_walkable_space(self):
        for rid,result in self.r['derived_routes'].items():
            with self.subTest(route=rid):
                self.assertIsNotNone(result)
                self.assertTrue(self.c['walkable'].covers(LineString(result['points'])))

    def test_independence_is_not_a_rear_access_detour(self):
        for a in self.r['approaches']:
            self.assertTrue(a['independent_openings'])
            self.assertIn(a['main_opening'],a['main_crossings_with_side_closed'])
            self.assertIn(a['side_opening'],a['side_crossings_with_main_closed'])
            self.assertNotIn(a['site']+'_rear',a['side_crossings_with_main_closed'])

    def test_failed_budget_remains_visible_and_stage4_paused(self):
        before=json.loads((OUT/'before/validation.json').read_text())
        self.assertFalse(before['physical_checks_passed'])
        self.assertFalse(self.r['stage_4_authorized'])
        self.assertIn('recovery_distance_budget',[i['code'] for i in before['issues']])
        self.assertTrue(before['violations'])
        self.assertTrue(all(x['clearance_duration'] is None for x in self.r['budget_ledger']))

    def test_architecture_does_not_hide_frozen_budget_misses(self):
        self.assertFalse(self.r['physical_checks_passed'])
        self.assertTrue(self.r['issues'])
        self.assertTrue(all(x['code'] in ('recovery_area_budget','recovery_distance_budget') for x in self.r['issues']))
        self.assertFalse(self.r['violations'])
        self.assertFalse(self.r['candidate_accepted'])
        self.assertFalse(self.r['original_requirements_all_preserved'])
        self.assertFalse(self.r['acceptance']['visual_accepted'])
        self.assertFalse(self.r['acceptance']['batch_authorized'])

    def test_recovery_budgets_not_relaxed(self):
        before=json.loads((OUT/'before/composition.json').read_text())
        self.assertEqual(before['distance_budgets'],self.p['distance_budgets'])
        self.assertEqual(before['allocations'],self.p['allocations'])
        measured=json.loads((OUT/'architecture-before/validation.json').read_text())
        a=next(x for x in measured['distance_allocations'] if x['route']=='CT-A-recover')
        self.assertGreaterEqual(a['travel_length'],40)
        self.assertLessEqual(a['travel_length'],75)

    def test_service_access_cannot_bypass_both_sites(self):
        audit=self.r['architecture_audit']
        self.assertTrue(audit['service_shortcut_removed'])
        for service in audit['service_routes']:
            self.assertIsNotNone(service['before_site_avoiding_route'])
            self.assertIsNone(service['after_site_avoiding_route'])
            self.assertIn(service['site']+'_side',service['after_crossings'])
            self.assertIn(service['site']+'_rear',service['after_crossings'])
            self.assertTrue(service['defender_contest']['line_of_sight'])

    def test_workshop_boundaries_break_lobby_to_site_sight(self):
        a=self.p['annotations']
        for source in ('B_prep','B_fight'):
            self.assertFalse(self.c['walkable'].covers(LineString([a[source]['point'],a['B_entry']['point']])))
        self.assertIn('B_lobby',[o['id'] for o in self.p['openings']])

    def test_sightlines_are_actual_walkable_segments(self):
        for line in self.r['architecture_audit']['long_sightlines']:
            self.assertTrue(self.c['visibility_standing'].covers(LineString(line['points'])))

    def test_objective_zones_are_inside_site_architecture(self):
        from shapely.geometry import Polygon
        for zone in self.p['objective_zones'].values():
            self.assertTrue(self.c['visibility_standing'].covers(Polygon(zone)))
            self.assertGreater(Polygon(zone).intersection(self.c['walkable']).area,0)

    def test_low_cover_collides_but_does_not_block_standing_eye(self):
        crossing=LineString([[25,58],[35,84]])
        self.assertFalse(self.c['walkable'].covers(Point(31,81)))
        self.assertTrue(self.c['visibility_standing'].covers(crossing))
        self.assertFalse(self.c['visibility_crouched'].covers(crossing))

    def test_engine_scale_and_widths_remain_provisional(self):
        scale=self.p['engine_scale']
        self.assertEqual(scale['source_units_per_plan_unit'],32)
        self.assertIn('not verified',scale['status'])
        main=next(x for x in self.r['spatial_usefulness']['doorways'] if x['opening']=='B_main')
        self.assertEqual(main['nominal_source_units'],128)
        self.assertEqual(main['clear_source_units'],128)
        self.assertEqual(main['player_centre_span_source_units'],96)
        self.assertFalse(self.r['spatial_usefulness']['remaining_clearance_problems'])

    def test_aperture_fix_does_not_redesign_architecture(self):
        before=json.loads((OUT/'aperture-before/composition.json').read_text())
        for field in ('spaces','internal_masses','annotations','objective_zones','allocations','distance_budgets','budget_revision_proposals','distance_revision_proposals','engine_scale'):
            self.assertEqual(before[field],self.p[field])
        for old,new in zip(before['openings'],self.p['openings']):
            if old['id']!='B_main':self.assertEqual(old,new)
            else:
                self.assertEqual(old['aperture'],[[111,74],[118,74]])
                self.assertEqual(new['aperture'],[[114,74],[118,74]])

    def test_allocation_history_is_not_current_annotation_area(self):
        expected={'A_rear':72,'A_retake':31.5,'B_rear':64,'B_retake':54}
        for row in self.r['allocation_reconciliation']['rows']:
            self.assertEqual(row['current_annotation_area'],expected[row['role']])
            self.assertFalse(row['proposed_budget_approved'])
            current=next(x for x in self.r['area_allocations'] if x['role']==row['role'])
            self.assertEqual(current['walkable_area'],row['current_annotation_area'])
        a=next(x for x in self.r['allocation_reconciliation']['rows'] if x['role']=='A_retake')
        self.assertEqual(a['original_snapshot_area'],96)
        self.assertAlmostEqual(a['legacy_rectangle_intersection_with_current_space'],3.96)
        self.assertEqual(a['current_annotation_area'],31.5)

    def test_graybox_is_only_a_bound_proposal(self):
        spec=json.loads((OUT/'graybox-proposal.json').read_text())
        serialized=json.loads((OUT/'composition.json').read_text())
        self.assertEqual(spec['composition_sha256'],digest(serialized))
        self.assertFalse(spec['stage4_authorized'])
        self.assertFalse(spec['batch_authorized'])
        self.assertFalse(spec['generator_evidence'])
        self.assertEqual(len(spec['spawns']),10)
        self.assertEqual(len(spec['bombsites']),2)
        self.assertFalse(Path(spec['destination']).exists())
        self.assertTrue(all(s['provisional_footprint_clear'] for s in spec['spawns']))

    def test_proposed_budget_regions_annotate_existing_walkable_space(self):
        for row in self.r['spatial_usefulness']['proposed_area_allocations']:
            self.assertTrue(row['entire_region_walkable'])
            self.assertTrue(row['within_proposed_budget'])
        self.assertEqual(self.p['distance_budgets']['CT-A-recover'],[40,75])
        self.assertEqual(self.p['distance_revision_proposals'][0]['budget'],[24,36])
        self.assertIn('Proposals',self.p['budget_revision_status'])

    def test_removed_pockets_do_not_remain_walkable(self):
        for point in ([14,79],[44,60],[100,46]):
            self.assertFalse(self.c['walkable'].covers(Point(point)))
        self.assertIn('B_side_threshold',[o['id'] for o in self.p['openings']])

    def test_player_footprint_rejects_narrow_aperture(self):
        p={'spaces':[{'id':'left','boundary':[[0,0],[4,0],[4,4],[0,4]]},
                     {'id':'right','boundary':[[4,0],[8,0],[8,4],[4,4]]}],
           'envelope':[[0,0],[8,0],[8,4],[0,4]],'boundary_thickness':.8,'internal_masses':[],
           'openings':[{'id':'pinch','spaces':['left','right'],'aperture':[[4,1.8],[4,2.2]]}]}
        c=compile_composition(p)
        self.assertEqual(c['walkable'].geom_type,'Polygon')
        centre=c['walkable'].buffer(-.5,join_style=2)
        self.assertEqual(centre.geom_type,'MultiPolygon')

    def test_directed_angle_distinguishes_opposite_from_parallel(self):
        self.assertEqual(directed_delta([0,1],[0,-1]),180)
        self.assertEqual(directed_delta([0,1],[0,1]),0)
        self.assertEqual(directed_delta([0,1],[-1,0]),90)

    def test_actual_recovery_and_attack_openings_not_assigned_by_label(self):
        for row in self.r['entry_angle_checks']:
            self.assertTrue(row['passed'])
            expected='rear' if row['route'].startswith('CT-') else 'side'
            site=row['route'].split('-')[1]
            self.assertEqual(row['observed_ingress']['opening'],site+'_'+expected)
            self.assertAlmostEqual(row['measured'],row['expected'])
        # Opening endpoint ordering cannot reverse the measured inward normal.
        p=copy.deepcopy(self.p)
        for opening in p['openings']:opening['aperture'].reverse()
        observed=site_ingress(self.r['derived_routes']['CT-B-recover'],p,self.c,'east_assembly')
        self.assertEqual(observed['inward_approach_vector'],[0,-1])

    def test_rotation_shortcut_measured_without_phase_gates(self):
        r=self.r['rotation'];self.assertTrue(r['passes_CT_deployment'])
        self.assertGreater(r['shortest_avoiding_CT_deployment'],r['shortest_length'])
        self.assertLess(r['shortest_length'],r['ordered_via_deployment_length'])

    def test_regression_set_unchanged_and_inadequate_schema_rejected(self):
        records=json.loads((OUT/'failed-batch-regression.json').read_text())
        self.assertEqual(len(records),16)
        for r in records:
            pid,e=r['candidate'].split('-')
            old=json.loads((ROOT/f'output/spatial-composition-001/{pid}/{e}-embedding.json').read_text())
            self.assertEqual(digest(old),r['input_sha256'])
            self.assertFalse(r['new_complete_space_schema_satisfied'])

    def test_original_strategy_bound_and_old_sampler_retired(self):
        plan=json.loads((ROOT/'output/strategic-diversity-001/P04/plan.json').read_text())
        self.assertEqual(digest(plan),self.r['plan_sha256'])
        v=GameplayValidator().validate(plan)
        with self.assertRaises(ValueError):SpatialEmbedder().compose(plan,v,1)
        p=copy.deepcopy(self.p);p['plan_sha256']=digest(plan)
        self.assertTrue(SpatialEmbedder().compose(plan,v,space_program=p)['walkable'].equals(self.c['walkable']))


if __name__=='__main__':unittest.main()
