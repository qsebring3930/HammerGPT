import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from evaluate_reserved import sample_nav,freeze,summarize,digest
from training_dataset import raster


class ReservedEvaluationTests(unittest.TestCase):
    def nav(self):
        return {'areas':[{'id':1,'hull':0,'movable_mesh_id':0xffffffff,
                          'corners':[[-1024,-1024,0],[0,-1024,0],[0,1024,0],[-1024,1024,0]]},
                         {'id':2,'hull':1,'movable_mesh_id':0xffffffff,
                          'corners':[[5000,5000,0],[6000,5000,0],[6000,6000,0],[5000,6000,0]]}]}

    def test_sampling_deterministic_and_matches_unfiltered_raster(self):
        nav=self.nav(); a,records,_=sample_nav(nav,2,42,set()); b,other,_=sample_nav(nav,2,42,set())
        np.testing.assert_array_equal(a,b); self.assertEqual(records,other)
        for target,record in zip(a,records):
            expected=np.rot90(raster([nav['areas'][0]['corners']],*record['world_center']),record['rotation_quarter_turns'])
            np.testing.assert_array_equal(target[0],expected)
            self.assertEqual(record['nav_seed_area'],1)

    def test_deduplication_excludes_previously_seen_windows(self):
        _,records,_=sample_nav(self.nav(),1,42,set())
        blocked={records[0]['footprint_sha256']}
        _,new,attempts=sample_nav(self.nav(),1,42,blocked)
        self.assertNotEqual(records[0]['footprint_sha256'],new[0]['footprint_sha256']); self.assertGreater(attempts,1)

    def test_freeze_writes_protocol_without_predictions_and_rejects_observed_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); dev=root/'dev'; planner=root/'planner'; dev.mkdir(); planner.mkdir()
            (dev/'manifest.json').write_text(json.dumps({'splits':{'train':['Dust2'],'validation':['Office'],'test':['Vertigo']}}))
            floor=root/'floor.pt'; floor.write_bytes(b'frozen floor'); (planner/'augmentation.pt').write_bytes(b'frozen planner')
            (planner/'metrics.json').write_text(json.dumps({'selected_arm':'augmentation','dataset_manifest_sha256':digest(dev/'manifest.json'),'floor_checkpoint_sha256':digest(floor)}))
            rows=[]
            for i in range(5):
                nav=root/f'nav{i}.json'; nav.write_text('{}')
                rows.append({'name':f'M{i}','user_approved':True,'model_evaluated':False,'training_allowed':False,'dataset_role':'evaluation_only','nav_export':nav.name})
            registry=root/'registry.json'; registry.write_text(json.dumps({'maps':rows}))
            output=root/'run'; protocol=freeze(registry,dev,planner,floor,output)
            self.assertEqual(protocol['status'],'frozen_before_predictions'); self.assertEqual(list(output.iterdir()),[output/'protocol.json'])
            rows[0]['model_evaluated']=True; registry.write_text(json.dumps({'maps':rows}))
            with self.assertRaisesRegex(ValueError,'unevaluated'): freeze(registry,dev,planner,floor,root/'second')

    def test_macro_score_weights_maps_equally(self):
        def row(iou):
            return {'methods':{'m':{'pixels':{'hidden_pixel_iou':iou},'topology':{'port_pair_preservation_rate':.5,'extra_connection_rate':.2,
                    'examples_with_broken_connection':1,'examples_with_extra_connection':2,'examples_with_isolated_prediction':0}}}}
        score=summarize({'a':row(.2),'b':row(.8)},['m'])['m']
        self.assertEqual(score['macro_patch_iou'],.5); self.assertEqual(score['maps'],2)


if __name__=='__main__': unittest.main()
