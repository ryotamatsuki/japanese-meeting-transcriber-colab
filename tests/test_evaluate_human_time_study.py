import copy
import unittest
from scripts.evaluate_human_time_study import assess


def sample(n=5):
    return {'method':'human_timed_crossover',
      'pairs':[{'record_id':f'authorized-{i}', 'order':('manual_first' if i%2 else 'assisted_first'),
                'manual_seconds':1000.0,'assisted_seconds':480.0,
                'manual_quality_pass':True,'assisted_quality_pass':True}
               for i in range(n)]}


class HumanTimeGateTests(unittest.TestCase):
    def test_complete_synthetic_only_demonstrates_logic(self):
        r=assess(sample())
        self.assertEqual(r['efficiency_gate'],'PASS')
        self.assertEqual(r['release_status'],'NO_GO')
        self.assertEqual(r['median_human_time_saving_percent'],52)

    def test_no_actual_user_samples_not_passed(self):
        with self.assertRaises(ValueError):assess(sample(3))

    def test_fabricated_estimate_or_missing_quality_rejected(self):
        d=sample();d['method']='gpu_runtime_estimate'
        with self.assertRaises(ValueError):assess(d)
        d=sample();d['pairs'][0]['assisted_quality_pass']=False
        with self.assertRaises(ValueError):assess(d)

    def test_missing_timing_rejected(self):
        d=sample();d['pairs'][0]['assisted_seconds']=None
        with self.assertRaises(ValueError):assess(d)

    def test_bad_result_is_not_a_release_authorization(self):
        d=sample()
        for row in d['pairs']:row['assisted_seconds']=900
        self.assertEqual(assess(d)['efficiency_gate'],'NOT_MET')


if __name__=='__main__':unittest.main()
