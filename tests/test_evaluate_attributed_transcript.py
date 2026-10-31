"""Stage8 speaker-attributed Japanese CER implementation and non-overlap proxy tests."""
import unittest

from scripts.evaluate_attributed_transcript import permutation_cer,localized_rows


def r(sp,text,start=0,end=1):
    return {'speaker_id':sp,'text':text,'start':start,'end':end}

def h(sp,text,start=0,end=1):
    return {'speaker':sp,'text':text,'start':start,'end':end}


class AttributedTranscriptTests(unittest.TestCase):
    def test_speaker_swapped_labels_are_not_penalized(self):
        ref=[r('A','こんにちは'),r('B','ありがとう')]
        hyp=[h('話者1','ありがとう'),h('話者2','こんにちは')]
        score=permutation_cer(ref,hyp)
        self.assertEqual(score['cpcer'],0)
        self.assertEqual(score['reference_speakers'],2)

    def test_wrong_speaker_cannot_be_mapped_twice(self):
        ref=[r('A','ああ'),r('B','いい')]
        hyp=[h('話者1','ああいい')]
        score=permutation_cer(ref,hyp)
        self.assertGreater(score['cpcer'],0)

    def test_unknown_speaker_counts_as_insertion(self):
        ref=[r('A','こんにちは')]
        hyp=[h('話者1','こんにちは'),h('話者不明','余分な発話')]
        score=permutation_cer(ref,hyp)
        self.assertGreater(score['cpcer'],0)
        self.assertEqual(score['unassigned_characters'],len('余分な発話'))

    def test_overlap_diagnostic_references_human_timing(self):
        ref=[r('A','あ',0,5),r('B','い',2,3),r('A','う',6,8)]
        hyp=[h('話者1','あ',0,5),h('話者2','い',2,3),h('話者1','う',6,8)]
        d=localized_rows(ref,hyp)
        self.assertEqual(d['human_overlap_seconds'],1)
        self.assertEqual(len(d['reference_overlap']),2)
        self.assertEqual(len(d['reference_other']),1)
        self.assertEqual(len(d['hypothesis_overlap']),2)

    def test_empty_reference_returns_unscored(self):
        s=permutation_cer([],[])
        self.assertIsNone(s['cpcer'])
        self.assertEqual(s['reference_characters'],0)

    def test_nfkc_and_punctuation_normalization(self):
        ref=[r('A','ＡＢＣ。')]
        hyp=[h('X','abc')]
        self.assertEqual(permutation_cer(ref,hyp)['cpcer'],0)


if __name__=='__main__':
    unittest.main()
