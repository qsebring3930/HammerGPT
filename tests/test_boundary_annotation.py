import unittest

from annotate_boundaries import clip_polygon


class BoundaryClipTests(unittest.TestCase):
    def test_clipping_preserves_sloping_surface_elevation(self):
        polygon=[[0,0,0],[100,0,100],[100,100,100],[0,100,0]]
        clipped=clip_polygon(polygon,[25,20,0,75,80,100])
        area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(clipped,clipped[1:]+clipped[:1])))/2
        self.assertAlmostEqual(area,3000)
        for x,y,z in clipped:
            self.assertAlmostEqual(x,z)
            self.assertTrue(25<=x<=75 and 20<=y<=80)

    def test_overlapping_xy_on_another_floor_is_excluded(self):
        polygon=[[0,0,128],[100,0,128],[100,100,128],[0,100,128]]
        self.assertEqual(clip_polygon(polygon,[-1,-1,-32,101,101,32]),[])


if __name__=='__main__':unittest.main()
