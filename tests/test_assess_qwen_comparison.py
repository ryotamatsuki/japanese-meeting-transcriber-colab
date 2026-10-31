import unittest
from scripts.assess_qwen_comparison import assess


def metrics():
    return {'record_id':'01','experiment_mode':'boundary','audio_sha256':'a'*64,
            'reference_eaf_sha256':'b'*64,'model':'Qwen/Qwen3-ASR-1.7B',
            'conditions':[
                {'name':'baseline_30','status':'success','cpcer':.27,
                 'flattened_cer':.22,'inference_and_eval_seconds':60},
                {'name':'candidate_boundary_1s','status':'success','cpcer':.23,
                 'flattened_cer':.21,'inference_and_eval_seconds':65}]}


class PairedScreenTests(unittest.TestCase):
    def test_strong_screen_never_certifies_commercial_quality(self):
        report=assess(metrics())
        self.assertTrue(report['screening_pass'])
        self.assertFalse(report['commercial_ready'])
        self.assertTrue(report['commercial_blockers'])

    def test_cpcer_improvement_does_not_hide_cer_regression(self):
        data=metrics();data['conditions'][1]['flattened_cer']=.23
        self.assertFalse(assess(data)['screening_pass'])
        data=metrics();data['conditions'][1]['cpcer']=.265
        self.assertFalse(assess(data)['screening_pass'])

    def test_failure_is_not_scored_as_zero_error(self):
        data=metrics();data['conditions'][1]={'name':'candidate','status':'failed',
                                            'failure_stage':'attribution','error_class':'ValueError'}
        report=assess(data)
        self.assertFalse(report['screening_pass'])
        self.assertNotIn('cpcer_improvement_pp',report)
        self.assertEqual(report['failures'][0]['stage'],'attribution')

    def test_invalid_inputs_cannot_pass(self):
        for value in (float('nan'),float('inf'),-.1,True):
            data=metrics();data['conditions'][1]['cpcer']=value
            with self.assertRaises(ValueError): assess(data)
        for field,value in [('audio_sha256',''),('model','another-model'),
                            ('experiment_mode','unregistered')]:
            data=metrics();data[field]=value
            with self.assertRaises(ValueError): assess(data)
