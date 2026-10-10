import unittest
from gameplay_backbone import build,polygon_cells,route

class GameplayBackboneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan,cls.cells=build()

    def test_built_ct_access_does_not_need_other_objective(self):
        regions={r['id']:r for r in self.plan['design_choices']['regions']}
        for site,other in [('SiteA','SiteB'),('SiteB','SiteA')]:
            self.assertTrue(route(self.cells,regions['CTSpawn']['center'][:2],regions[site]['center'][:2],
                                  polygon_cells(regions[other]['footprint_polygon_xy'])))

    def test_unrelated_streets_and_spaces_do_not_join(self):
        self.assertEqual(self.plan['geometry_audit']['unrelated_street_space_contacts'],[])
        widths={e['width_units'] for e in self.plan['design_choices']['connections']}
        self.assertGreater(len(widths),2)

    def test_attack_alternatives_remain_when_main_entry_is_closed(self):
        regions={r['id']:r for r in self.plan['design_choices']['regions']}
        for site,main,other in [('SiteA','AMain','SiteB'),('SiteB','BMain','SiteA')]:
            blocked=polygon_cells(regions[main]['footprint_polygon_xy'])|polygon_cells(regions[other]['footprint_polygon_xy'])
            # Test existence of a central alternative, not whether an unconstrained
            # shortest path chooses it. A footprint mask does not close its entire street.
            mid=regions['Mid']['center'][:2]
            self.assertTrue(route(self.cells,regions['TSpawn']['center'][:2],mid,blocked))
            self.assertTrue(route(self.cells,mid,regions[site]['center'][:2],blocked))

if __name__=='__main__':unittest.main()
