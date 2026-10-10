from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from extract_sections import extract,study,inside
from connected_geometry import floor_cells,validate_floor
from surface_geometry import create_surface_blockout
from hammergpt import parse


class SectionTests(unittest.TestCase):
    def fixture(self):
        areas=[]
        for i in range(12):
            x=i*100; y=0 if i<6 else (i-5)*50
            areas.append({'id':i,'hull':0,'movable_mesh_id':0xffffffff,
                'corners':[[x,y,0],[x+100,y,0],[x+100,y+100,0],[x,y+100,0]],
                'connections':[{'target':i+1}] if i<11 else []})
        nav={'source':'fixture.nav','areas':areas}
        graph={'hull':0,'provenance':{'nav_source':'fixture.nav','map_source':'fixture.vmap'},
               'example_routes':[{'start':'TSpawn','goal':'BombsiteA','nav_area_path':list(range(12))}],
               'area_assignments':[{'area_id':i,'label':'Example'} for i in range(12)]}
        return nav,graph

    def test_only_recorded_edges_are_reference_evidence(self):
        nav,graph=self.fixture(); section=extract(nav,graph)
        links={(a['id'],c['target']) for a in nav['areas'] for c in a['connections']}
        self.assertTrue(all((e['source'],e['target']) in links for e in section['recorded_connections']))
        self.assertGreater(len(section['measurements']['sampled_signed_turn_angles_degrees']),0)
        self.assertFalse(section['model_training_performed'])

    def test_bad_route_and_mismatched_source_rejected(self):
        nav,graph=self.fixture(); graph['example_routes'][0]['nav_area_path']=[0,11]
        with self.assertRaisesRegex(ValueError,'recorded'): extract(nav,graph)
        graph['provenance']['nav_source']='other.nav'
        with self.assertRaisesRegex(ValueError,'mismatch'): extract(nav,graph)

    def test_study_is_connected_and_valid_editable_surface(self):
        nav,graph=self.fixture(); plan=study(extract(nav,graph)); cells=floor_cells(plan)
        self.assertEqual(validate_floor(cells,lambda x:0)['floor_components'],1)
        _,roots=parse((Path(__file__).parent/'fixtures/box_light.vmap.txt').read_text())
        _,manifest,stats=create_surface_blockout(roots,plan)
        self.assertEqual(len(manifest),1)
        self.assertGreater(stats['faces'],0)
        self.assertIn('projected',plan['adaptations'][0])

    def test_polygon_containment_handles_irregular_outline(self):
        polygon=[(0,0),(100,0),(100,40),(40,40),(40,100),(0,100)]
        self.assertTrue(inside(20,80,polygon))
        self.assertFalse(inside(80,80,polygon))

    def test_unnamed_fallback_requires_explicit_selection_and_records_method(self):
        nav,graph=self.fixture(); graph['example_routes']=[]
        with self.assertRaisesRegex(ValueError,'allow-unnamed'): extract(nav,graph)
        section=extract(nav,graph,allow_unnamed=True)
        self.assertIn('no objective association',section['section_selection_method'])
        recorded={(a['id'],c['target']) for a in nav['areas'] for c in a['connections']}
        self.assertTrue(all(pair in recorded for pair in zip(section['route_nav_area_ids'],section['route_nav_area_ids'][1:])))
