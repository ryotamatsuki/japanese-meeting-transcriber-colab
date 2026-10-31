import unittest
from scripts.qwen_boundary_context import context_window, own_aligned_tokens


class BoundaryContextTests(unittest.TestCase):
    def test_context_preserves_samples_and_clips_audio_edges(self):
        signal=list(range(3*16000))
        window,offset,core=context_window(signal,0,16000)
        self.assertEqual(window,signal[:32000])
        self.assertEqual((offset,core),(0,(0,1)))
        window,offset,core=context_window(signal,2,16000)
        self.assertEqual(window,signal[16000:])
        self.assertEqual((offset,core),(1,(2,3)))

    def test_midpoints_have_one_owner_and_repeated_words_are_preserved(self):
        row={'offset_sec':0.,'duration_sec':3.,'text':'はいはいはい',
             'items':[{'text':'はい','start_time':v,'end_time':v+.2}
                      for v in (.4,.9,1.4)]}
        left,dl=own_aligned_tokens([row],(0,1))
        right,dr=own_aligned_tokens([row],(1,2),final=True)
        self.assertEqual([len(v[0]['items']) for v in (left,right)],[1,2])
        self.assertEqual(''.join(v[0]['text'] for v in (left,right)),row['text'])
        self.assertEqual(dl+dr,3)

    def test_offsets_and_final_boundary(self):
        row={'offset_sec':10.,'duration_sec':2.,'text':'末尾',
             'items':[{'text':'末尾','start_time':1.8,'end_time':2.2}]}
        self.assertEqual(own_aligned_tokens([row],(11,12))[0],[])
        kept,_=own_aligned_tokens([row],(11,12),final=True)
        self.assertEqual(kept[0]['text'],'末尾')

    def test_invalid_windows_and_times_fail(self):
        for offset,length,pad in [(-1,16000,1),(1,32000,1),(0,16000,3)]:
            with self.assertRaises(ValueError):
                context_window([0]*32000,offset,length,padding=pad)
        with self.assertRaises(ValueError):
            own_aligned_tokens([{'offset_sec':0,'items':[
                {'text':'x','start_time':float('nan'),'end_time':1}]}],(0,1))
