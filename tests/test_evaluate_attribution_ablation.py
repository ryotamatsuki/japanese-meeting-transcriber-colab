import unittest
from scripts.evaluate_attribution_ablation import annotate_regular


class RegularAttributionTests(unittest.TestCase):
    def test_word_majority_overlap(self):
        asr=[{'start':0,'end':3,'words':[
            {'start':0.1,'end':0.5,'text':'こんにちは'},
            {'start':2.0,'end':2.5,'text':'はい'}]}]
        reg=[{'start':0,'end':1,'speaker_id':'A'},{'start':1,'end':3,'speaker_id':'B'}]
        rows=annotate_regular(asr,reg)
        self.assertEqual([r['speaker'] for r in rows],['話者1','話者2'])
        self.assertEqual(''.join(r['text'] for r in rows),'こんにちははい')

    def test_overlap_tie_is_stable_not_double_transcribed(self):
        asr=[{'start':0,'end':1,'words':[{'start':0.2,'end':0.8,'text':'はい'}]}]
        reg=[{'start':0,'end':1,'speaker_id':'A'},{'start':0,'end':1,'speaker_id':'B'}]
        rows=annotate_regular(asr,reg)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['speaker'],'話者1')

    def test_gap_reports_unknown(self):
        asr=[{'start':3,'end':4,'words':[{'start':3,'end':4,'text':'はい'}]}]
        reg=[{'start':0,'end':1,'speaker_id':'A'}]
        self.assertEqual(annotate_regular(asr,reg)[0]['speaker'],'話者不明')

if __name__=='__main__':
    unittest.main()
