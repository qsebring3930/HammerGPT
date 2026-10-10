import unittest
import numpy as np
from train_conditioned import reference_plan, encode_plan, annotated, ConditionedNet
from train_patch import patch_input


class ConnectionInputTests(unittest.TestCase):
    def example(self):
        target=np.zeros((1,1,32,32),dtype=np.float32)
        target[0,0,15,11:21]=1
        return target

    def test_geometry_with_same_plan_has_identical_input(self):
        a=self.example(); b=a.copy(); b[0,0,16,13:19]=1
        ax,ap=annotated(a); bx,bp=annotated(b)
        self.assertEqual(ap,bp)
        np.testing.assert_array_equal(ax,bx)
        self.assertFalse(ax[:,2:,12:20,12:20].any())

    def test_connection_change_is_encoded_without_target_pixels(self):
        y=self.example(); context=patch_input(y)[0]
        connected=reference_plan(context,y[0]); broken=y[0].copy(); broken[0,15,16]=0
        separate=reference_plan(context,broken)
        self.assertEqual(connected,[0,0]); self.assertEqual(separate,[0,1])
        a=encode_plan(context,connected); b=encode_plan(context,separate)
        np.testing.assert_array_equal(a[:2],b[:2])
        self.assertFalse(np.array_equal(a[2:],b[2:]))
        self.assertFalse(b[2:,12:20,12:20].any())

    def test_label_names_do_not_change_encoding(self):
        context=patch_input(self.example())[0]
        np.testing.assert_array_equal(encode_plan(context,[0,1]),encode_plan(context,[42,7]))
        with self.assertRaises(ValueError): encode_plan(context,[0])
        with self.assertRaises(ValueError): encode_plan(context,[-1,0])

    def test_empty_ports(self):
        x,plans=annotated(np.zeros((1,1,32,32),dtype=np.float32))
        self.assertEqual(plans,[[]]); self.assertFalse(x[:,2:].any())


if __name__=='__main__': unittest.main()
