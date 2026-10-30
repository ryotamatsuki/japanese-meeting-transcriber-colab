import unittest
from scripts.qwen_timing_bridge import qwen_segments, attribute_qwen


def sample():
    return [
     {'offset_sec':0,'duration_sec':3,'text':'こんにちは。はい',
      'items':[{'text':'こんにちは','start_time':0.1,'end_time':1.0},
               {'text':'はい','start_time':2.0,'end_time':2.7}]},
     {'offset_sec':3,'duration_sec':3,'text':'ありがとうございます。',
      'items':[{'text':'ありがとう','start_time':0.2,'end_time':1.8},
               {'text':'ございます','start_time':1.8,'end_time':2.8}]}
    ]


class QwenTimingTests(unittest.TestCase):
    def test_keeps_normalized_text_and_absolute_time(self):
        seg,metrics=qwen_segments(sample(),6)
        self.assertEqual(metrics['aligned_tokens'],4)
        self.assertEqual(seg[1]['words'][0]['start'],3.2)
        self.assertEqual(seg[-1]['end'],5.8)

    def test_speaker_attribution_cannot_remove_words(self):
        diar=[{'start':0,'end':3,'speaker_id':'A'},
              {'start':3,'end':6,'speaker_id':'B'}]
        rows,meta=attribute_qwen(sample(),diar,6)
        self.assertEqual(meta['speaker_count'],2)
        self.assertTrue(meta['all_normalized_text_preserved'])
        self.assertEqual(''.join(x['text'] for x in rows),'こんにちははいありがとうございます')

    def test_rejects_timestamp_nonmonotonic(self):
        data=sample()
        data[0]['items'][1]['start_time']=-1
        with self.assertRaises(ValueError):
            qwen_segments(data,6)

    def test_rejects_truncated_alignment(self):
        data=sample()
        data[0]['items'].pop()
        with self.assertRaisesRegex(ValueError,'did not preserve'):
            qwen_segments(data,6)

    def test_rejects_late_missing_tail(self):
        data=sample()
        data.pop()
        with self.assertRaises(ValueError):
            qwen_segments(data,6)

    def test_rejects_unknown_speaker_model(self):
        with self.assertRaises(ValueError):
            attribute_qwen(sample(),[],6)

if __name__=='__main__':
    unittest.main()
