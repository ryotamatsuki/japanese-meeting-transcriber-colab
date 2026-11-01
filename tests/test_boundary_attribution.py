"""Bounded, privacy-safe research tests. Synthetic speech timing, no real audio."""
import copy
import unittest
from transcriber.boundary_attribution import guarded_boundary_repair


def w(a,b,text,speaker):
    return {"start":a,"end":b,"text":text,"speaker":speaker}


def s(a,b,speaker):
    return {"start":a,"end":b,"speaker_id":speaker}


class GuardedBoundaryAttributionTests(unittest.TestCase):
    def setUp(self):
        self.words=[w(.1,.80,"債務負担","話者1"),
                    w(.85,1.15,"行為","話者2"),
                    w(1.20,2.05,"の話です","話者1")]
        self.exclusive=[s(0.,.99,"rawA"),s(.99,1.16,"rawB"),
                        s(1.16,2.20,"rawA")]
        self.regular=list(self.exclusive)

    def test_repair_straddling_token_only(self):
        frozen=copy.deepcopy((self.words,self.exclusive,self.regular))
        out,audit=guarded_boundary_repair(self.words,self.exclusive,regular=self.regular)
        self.assertEqual([x["speaker"] for x in out],["話者1"]*3)
        self.assertEqual(audit["relabeled_words"],1)
        self.assertEqual((self.words,self.exclusive,self.regular),frozen)
        self.assertEqual([x["text"] for x in out],[x["text"] for x in self.words])
        self.assertNotIn("債務",str(audit))

    def test_protect_actual_backchannel(self):
        words=copy.deepcopy(self.words)
        words[1]["text"]="はい"
        out,a=guarded_boundary_repair(words,self.exclusive,regular=self.regular)
        self.assertEqual(out[1]["speaker"],"話者2")
        self.assertEqual(a["rejected"]["protected_backchannel"],1)

    def test_preserve_true_multi_speaker_overlap(self):
        regular=[s(0,2.2,"rawA"),s(.95,1.25,"rawB")]
        out,a=guarded_boundary_repair(self.words,self.exclusive,regular=regular)
        self.assertEqual(out[1]["speaker"],"話者2")
        self.assertEqual(a["rejected"]["concurrent_speech"],1)

    def test_reject_confident_wrong_island_when_boundary_evidence_absent(self):
        diar=[s(0,.86,"rawA"),s(.86,1.16,"rawB"),s(1.16,2.2,"rawA")]
        out,a=guarded_boundary_repair(self.words,diar,regular=diar)
        self.assertEqual(out[1]["speaker"],"話者2")
        self.assertEqual(a["rejected"]["high_margin_or_no_target_overlap"],1)

    def test_no_relabel_across_long_silence(self):
        words=copy.deepcopy(self.words)
        words[2]["start"]=1.60
        out,a=guarded_boundary_repair(words,self.exclusive,regular=self.regular)
        self.assertEqual(out[1]["speaker"],"話者2")
        self.assertEqual(a["rejected"]["gap_or_overlapping_word_time"],1)

    def test_unknown_or_no_regular_is_fail_closed(self):
        with self.assertRaises(ValueError):
            guarded_boundary_repair(self.words,self.exclusive)
        words=copy.deepcopy(self.words)
        words[0]["speaker"]="話者不明"
        out,a=guarded_boundary_repair(words,self.exclusive,regular=self.regular)
        self.assertEqual(out[1]["speaker"],"話者2")

    def test_empty_regular_diarization_never_changes_labels(self):
        out,audit=guarded_boundary_repair(
            self.words,self.exclusive,regular=[])
        self.assertEqual(out,self.words)
        self.assertEqual(audit["relabeled_words"],0)
        self.assertIn("regular_diarization_missing",audit["rejected"])

    def test_invalid_regions_and_word_order_rejected(self):
        with self.assertRaises(ValueError):
            guarded_boundary_repair(self.words,[s(0,1.1,"rawA"),s(1.0,2.2,"rawB")],
                                    regular=self.regular)
        words=copy.deepcopy(self.words)
        words[2]["start"]=.0
        with self.assertRaises(ValueError):
            guarded_boundary_repair(words,self.exclusive,regular=self.regular)


if __name__=="__main__":
    unittest.main()
