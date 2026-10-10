import copy
import unittest

from shapely.geometry import box,mapping

from preference_scorer import train,score


class PreferenceScorerTests(unittest.TestCase):
    def candidate(self,sharing):
        return {'nodes':[{},{}],'edges':[{'width':352}],
                'descriptors':{'opening_sharing':sharing,'rotation_ratio':1.5},
                'timings':{f'{t}-{s}':{'seconds_proxy':20} for t in ('T','CT') for s in ('A','B')},
                'floor':mapping(box(0,0,1024,1024))}

    def test_explicit_preference_changes_ranking_in_its_stated_direction(self):
        a,b=self.candidate(.2),self.candidate(.8)
        forward=train({'a':a,'b':b},[('a','b')])
        reverse=train({'a':a,'b':b},[('b','a')])
        self.assertGreater(score(forward,a),score(forward,b))
        self.assertGreater(score(reverse,b),score(reverse,a))

    def test_no_human_choice_cannot_be_presented_as_training(self):
        with self.assertRaises(ValueError):train({'a':self.candidate(.5)},[])

    def test_scorer_training_does_not_modify_geometry(self):
        candidates={'a':self.candidate(.2),'b':self.candidate(.8)};original=copy.deepcopy(candidates)
        model=train(candidates,[('a','b')])
        self.assertEqual(candidates,original)
        self.assertFalse(model['generator_weights_updated'])


if __name__=='__main__':unittest.main()
