from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from train_patch import patch_input
from evaluate_topology import analyze,remove_islands,components


class TopologyEvaluationTests(unittest.TestCase):
    def fixture(self):
        target=np.zeros((1,32,32),dtype=np.float32); target[0,15,11:21]=1
        return patch_input(target[None])[0],target

    def test_break_in_corridor_is_detected(self):
        context,target=self.fixture(); prediction=target.copy(); prediction[0,15,16]=0
        result=analyze(context,target,prediction)
        self.assertEqual(result['required_pairs'],1)
        self.assertEqual(result['broken_pairs'],1)

    def test_shortcut_between_separate_ports_is_detected(self):
        context,target=self.fixture(); target[0,15,16]=0
        prediction=target.copy(); prediction[0,15,16]=1
        result=analyze(context,target,prediction)
        self.assertEqual(result['extra_connections'],1)

    def test_island_cleanup_uses_no_target_and_preserves_rim(self):
        context,target=self.fixture(); prediction=target.copy(); prediction[0,18,18]=1
        self.assertEqual(analyze(context,target,prediction)['isolated_predicted_components'],1)
        cleaned=remove_islands(context,prediction)
        self.assertEqual(cleaned[0,18,18],0)
        self.assertEqual(analyze(context,target,cleaned)['broken_pairs'],0)
        self.assertTrue(np.array_equal(cleaned[:,:12],prediction[:,:12]))

    def test_corner_touch_does_not_count_as_connection(self):
        grid=np.eye(2,dtype=bool)
        self.assertEqual(len(components(grid)[1]),2)
