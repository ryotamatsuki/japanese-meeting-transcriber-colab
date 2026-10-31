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
    def test_45s_research_chunk_requires_consistent_explicit_limit(self):
        data=[{'offset_sec':0,'duration_sec':45,'text':'あいうえ',
               'items':[{'text':c,'start_time':i*10.,'end_time':i*10.+9.}
                        for i,c in enumerate('あいうえ')]}]
        diar=[{'start':0,'end':45,'speaker_id':'A'}]
        with self.assertRaisesRegex(ValueError,'Invalid chunk'):
            attribute_qwen(data,diar,45)
        rows,meta=attribute_qwen(data,diar,45,max_chunk_seconds=50)
        self.assertEqual(meta['aligned_tokens'],4)
        self.assertEqual(''.join(r['text'] for r in rows),'あいうえ')
        for limit in (0,51,float('nan')):
            with self.assertRaises(ValueError):
                qwen_segments(data,45,max_chunk_seconds=limit)

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

    def test_recording_silence_is_not_mistaken_for_missing_speech(self):
        data=sample()
        with self.assertRaises(ValueError):qwen_segments(data,10)
        _,metrics=qwen_segments(data,10,speech_end_seconds=6)
        self.assertEqual(metrics['aligned_tokens'],4)
        for boundary in (9,11,0,float('nan')):
            with self.assertRaises(ValueError):qwen_segments(data,10,speech_end_seconds=boundary)

    def test_rejects_late_missing_tail(self):
        data=sample()
        data.pop()
        with self.assertRaises(ValueError):
            qwen_segments(data,6)

    def test_limited_cross_chunk_time_overlap_keeps_original_text_order(self):
        data=sample()
        data[0]['items'][1]['start_time']=3.2
        data[0]['items'][1]['end_time']=3.4
        data[1]['items'][0]['start_time']=0.0
        diar=[{'start':0,'end':3.0,'speaker_id':'A'},
              {'start':3.0,'end':6.0,'speaker_id':'B'}]
        rows,quality=attribute_qwen(data,diar,6)
        self.assertTrue(quality['all_normalized_text_preserved'])
        self.assertGreater(quality['small_temporal_order_repairs'],0)
        self.assertEqual(''.join(x['text'] for x in rows),
                         'こんにちははいありがとうございます')

    def test_large_time_inversion_rejected(self):
        data=sample()
        data[0]['items'][1]['start_time']=3.2
        data[0]['items'][1]['end_time']=3.4
        data[1]['items'][0]['start_time']=0.0
        # Should be normalized for source text but refuse far timestamps.
        data[1]['items'][0]['start_time']=-1.0
        with self.assertRaises(ValueError):
            attribute_qwen(data,[{'start':0,'end':6,'speaker_id':'A'}],6)

    def test_safe_lexical_redistribution_preserves_qwen_original(self):
        data=sample()
        data[0]['items'][0]['text']='こんにちわ'
        rows,meta=attribute_qwen(data,[{'start':0,'end':3,'speaker_id':'A'},
                                        {'start':3,'end':6,'speaker_id':'B'}],6)
        self.assertEqual(meta['lexical_redistribution_chunks'],1)
        self.assertTrue(meta['all_normalized_text_preserved'])
        self.assertEqual(''.join(x['text'] for x in rows),
                         'こんにちは。はいありがとうございます')

    def test_large_lexical_difference_is_not_silently_repaired(self):
        data=sample()
        data[0]['items'][0]['text']='かかかかか'
        with self.assertRaises(ValueError):
            qwen_segments(data,6)

    def test_clamped_final_token_preserves_content_and_marks_review(self):
        data=sample()
        data[1]['items'][1]['start_time']=3.2
        data[1]['items'][1]['end_time']=3.4
        rows,meta=attribute_qwen(data,[{'start':0,'end':3,'speaker_id':'A'},
                                        {'start':3,'end':6,'speaker_id':'B'}],6)
        self.assertEqual(meta['tail_timestamp_review_tokens'],1)
        self.assertTrue(meta['all_normalized_text_preserved'])
        self.assertEqual(''.join(x['text'] for x in rows),
                         'こんにちははいありがとうございます')
        self.assertEqual(rows[-1]['end'],6.0)

    def test_submillisecond_tail_rounding_keeps_lexical_text(self):
        data=sample()
        data[1]['items'][1]['start_time']=2.9996
        data[1]['items'][1]['end_time']=3.1
        _,meta=qwen_segments(data,6)
        self.assertEqual(meta['tail_timestamp_review_tokens'],1)

    def test_multiple_bounded_tail_tokens_maintain_original_order(self):
        data=sample()
        data[1]['text']='あ'*6
        data[1]['items']=[{'text':'あ','start_time':3.1,
                           'end_time':3.2} for _ in range(6)]
        words,meta=qwen_segments(data,6)
        self.assertEqual(meta['tail_timestamp_review_tokens'],6)
        self.assertEqual(meta['aligned_tokens'],8)
        self.assertEqual(''.join(w['text'] for seg in words for w in seg['words']),
                         'こんにちははい'+'あ'*6)

    def test_excessive_hallucinated_tail_tokens_fail_closed(self):
        data=sample()
        data[1]['text']='あ'*13
        data[1]['items']=[{'text':'あ','start_time':3.1,
                           'end_time':3.2} for _ in range(13)]
        with self.assertRaisesRegex(ValueError,'Too many Qwen inferred'):
            qwen_segments(data,6)

    def test_excessive_tail_offset_must_fail_not_drop_text(self):
        data=sample()
        data[1]['items'][1]['start_time']=3.9
        data[1]['items'][1]['end_time']=3.95
        with self.assertRaises(ValueError):
            qwen_segments(data,6)

    def test_rejects_unknown_speaker_model(self):
        with self.assertRaises(ValueError):
            attribute_qwen(sample(),[],6)

if __name__=='__main__':
    unittest.main()
