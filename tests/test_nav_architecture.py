import unittest,networkx as nx
from extract_nav_architecture import support_graph,aggregate,portal
from shapely.geometry import box

def area(i,x0,x1,z=0):
 return dict(id=i,hull=0,flags=0,movable_mesh_id=4294967295,ladders_above=[],ladders_below=[],corners=[[x0,0,z],[x1,0,z],[x1,2,z],[x0,2,z]],connections=[])
def pair():
 a,b=area(1,0,2),area(2,2,4);a['connections']=[dict(target=2,source_edge=1,target_edge=3)];b['connections']=[dict(target=1,source_edge=3,target_edge=1)];return a,b
class NavArchitectureTests(unittest.TestCase):
 def test_reciprocal_shared_portal_admitted(self):
  a,b=pair();areas,g,_,_=support_graph({'areas':[a,b]});self.assertEqual(len(g.edges),1);self.assertAlmostEqual(g[1][2]['width_native'],2)
 def test_flagged_ladder_or_movable_support_not_ordinary(self):
  for key,value in [('flags',65536),('ladders_above',[7]),('movable_mesh_id',1),('hull',1)]:
   a,b=pair();b[key]=value;areas,g,_,_=support_graph({'areas':[a,b]});self.assertNotIn(2,areas);self.assertEqual(len(g.edges),0)
 def test_one_way_and_stacked_edges_not_flattened_into_walking(self):
  a,b=pair();b['connections']=[];self.assertEqual(len(support_graph({'areas':[a,b]})[1].edges),0)
  a,b=pair();b['corners']=[[x,y,64] for x,y,z in b['corners']];self.assertIsNone(portal(a,b,a['connections'][0]))
 def test_aggregation_preserves_hole_and_original_members(self):
  shapes=[box(0,0,6,1),box(0,5,6,6),box(0,1,1,5),box(5,1,6,5)];areas={i:dict(id=i,corners=[[x,y,0] for x,y in shape.exterior.coords[:-1]]) for i,shape in enumerate(shapes)};g=nx.Graph();g.add_edges_from([(0,2),(2,1),(1,3),(3,0)]);groups=aggregate(areas,g,{i:'territory' for i in areas},['territory'])
  self.assertEqual(len(groups),1);self.assertEqual(groups[0]['area_ids'],[0,1,2,3]);self.assertEqual(len(groups[0]['shape'].interiors),1);self.assertAlmostEqual(groups[0]['shape'].area,20)
if __name__=='__main__':unittest.main()
