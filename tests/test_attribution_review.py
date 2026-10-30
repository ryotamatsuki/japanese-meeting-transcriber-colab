"""Regression checks for evidence-only attribution review; not acoustic accuracy proof."""
import unittest
from transcriber.attribution_review import audit_word_speaker_assignments


def iv(s,e,who):
    return {"start":s,"end":e,"speaker_id":who}


def seg(*words):
    return [{"start":0,"end":4,"text":"".join(w[2] for w in words),
             "words":[{"start":w[0],"end":w[1],"text":w[2]} for w in words]}]


class AttributionReviewTests(unittest.TestCase):
    def test_clear_single_speaker_not_flagged(self):
        record=audit_word_speaker_assignments(seg((0.2,0.9,"こんにちは")), [iv(0,1,"A")], [iv(0,1,"A")])
        self.assertEqual(record["review_words"],0)
        self.assertEqual(record["words"][0]["exclusive_speaker_candidate"],"A")

    def test_split_word_and_close_vote_flagged(self):
        record=audit_word_speaker_assignments(seg((0.8,1.2,"はい")), [iv(0,1,"A"),iv(1,2,"B")])
        self.assertEqual(record["review_words"],1)
        self.assertIn("word_crosses_speaker_boundary",record["words"][0]["review_reasons"])
        self.assertIn("close_speaker_overlap_scores",record["words"][0]["review_reasons"])

    def test_standard_overlap_even_if_exclusive_unanimous(self):
        record=audit_word_speaker_assignments(seg((0.3,0.8,"了解")), [iv(0,1,"A")],
            [iv(0,1,"A"),iv(0.4,0.9,"B")])
        self.assertIn("regular_diarization_overlap_candidate",record["words"][0]["review_reasons"])
        self.assertEqual(record["words"][0]["exclusive_speaker_candidate"],"A")

    def test_zero_duration_and_no_overlap(self):
        record=audit_word_speaker_assignments(seg((1,1,"え"),(3,3.1,"はい")),
                                                [iv(0,0.5,"A")])
        self.assertEqual(record["review_words"],2)
        self.assertTrue(all("no_exclusive_overlap" in w["review_reasons"] for w in record["words"]))
        self.assertIn("short_or_zero_word_timestamp",record["words"][0]["review_reasons"])

    def test_fractional_coverage_and_no_mutation(self):
        exclusive=[iv(0,0.2,"A")]
        record=audit_word_speaker_assignments(seg((0,0.8,"おはよう")),exclusive)
        self.assertIn("low_exclusive_coverage",record["words"][0]["review_reasons"])
        self.assertEqual(exclusive,[iv(0,0.2,"A")])

    def test_large_synthetic_audio(self):
        # A few thousand words/segments should be practical; standard speaker
        # overlap is condensed once instead of recomputing all pairs per word.
        intervals=[iv(float(i),float(i+1),"A" if i%2 else "B") for i in range(1000)]
        segments=[{"start":0,"end":1000,"text":"", "words":[
            {"start":i+.2,"end":i+.6,"text":"語"} for i in range(1000)]}]
        record=audit_word_speaker_assignments(segments,intervals)
        self.assertEqual(record["review_words"],0)
        self.assertEqual(record["word_count"],1000)

    def test_reject_invalid_word(self):
        with self.assertRaises(ValueError):
            audit_word_speaker_assignments(seg((-1,0,"悪い")),[])
        with self.assertRaises(ValueError):
            audit_word_speaker_assignments(seg((1,0,"悪い")),[])

if __name__=="__main__":
    unittest.main()
