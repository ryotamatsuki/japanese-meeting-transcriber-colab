import copy
import unittest
from scripts.whisper_speaker_timing_audit import evaluate, _assign, _frozen_words, _validate_regions


def word(a,b,text):
    return {"start":a,"end":b,"text":text}


class WordSpeakerTimingAuditTests(unittest.TestCase):
    def setUp(self):
        self.ref=[{"start":0,"end":1.95,"speaker_id":"A","text":"こんにちは"},
                  {"start":2.05,"end":4.0,"speaker_id":"B","text":"よろしく"}]
        self.asr=[
            {"start":0.2,"end":1.8,"text":"こんにちは",
             "words":[word(.2,.8,"こんに"),word(.8,1.8,"ちは")]},
            {"start":2.1,"end":3.4,"text":"よろしく",
             "words":[word(2.1,2.7,"よろ"),word(2.7,3.4,"しく")]}]
        self.diar=[{"start":0.0,"end":2.0,"speaker_id":"A"},
                   {"start":2.0,"end":4.0,"speaker_id":"B"}]

    def test_all_policies_preserve_input_and_reproduce_legacy(self):
        frozen=copy.deepcopy((self.ref,self.asr,self.diar))
        result=evaluate(self.ref,self.asr,self.diar,duration=4.0)
        self.assertEqual(result["word_count"],4)
        self.assertEqual(result["rules"]["legacy"]["edits"],0)
        self.assertEqual(result["rules"]["midpoint"]["edits"],0)
        self.assertEqual(result["rules"]["onset"]["edits"],0)
        self.assertEqual(result["rules"]["end"]["edits"],0)
        self.assertEqual(result["shift_sensitivity_diagnostic_only"]["0.0"]["edits"],0)
        self.assertEqual((self.ref,self.asr,self.diar),frozen)
        self.assertFalse(result["claims"]["human_word_time_accuracy_measured"])

    def test_alternative_assignments_differ_on_boundary_straddling_word(self):
        words=[word(.70,1.3,"あ"),word(1.05,1.5,"い")]
        intervals=[{"start":0,"end":1.0,"speaker_id":"A"},
                   {"start":1.0,"end":2.0,"speaker_id":"B"}]
        onset,_=_assign(words,intervals,"onset")
        midpoint,_=_assign(words,intervals,"midpoint")
        self.assertNotEqual(onset[0]["speaker"],midpoint[0]["speaker"])

    def test_lexical_inversion_frozen_in_exact_legacy_timeline_order(self):
        source=[{"start":2.0,"end":2.2,"words":[word(2,2.2,"遅")]},
                {"start":1.0,"end":1.2,"words":[word(1,1.2,"早")]}]
        original=copy.deepcopy(source)
        ordered,frozen,moves=_frozen_words(source)
        self.assertEqual([w["text"] for w in ordered],["早","遅"])
        self.assertEqual(frozen,"早遅")
        self.assertEqual(moves,2)
        self.assertEqual(source,original)

    def test_overlapping_input_for_exclusive_is_rejected(self):
        data=copy.deepcopy(self.diar)
        data[1]["start"]=1.5
        with self.assertRaises(ValueError):
            _validate_regions(data)

    def test_never_return_text_or_raw_speaker_identifiers(self):
        data=evaluate(self.ref,self.asr,self.diar,duration=4.0)
        keys=str(data)
        self.assertNotIn("こんにちは",keys)
        self.assertNotIn("よろしく",keys)
        self.assertIn("lexical_sha256",keys)

    def test_cumulative_same_speaker_overlap_reproduces_production(self):
        from transcriber.alignment import assign_and_group
        diar=[{"start":0.0,"end":1.0,"speaker_id":"A"},
              {"start":1.0,"end":1.4,"speaker_id":"B"},
              {"start":1.4,"end":1.8,"speaker_id":"A"}]
        seg=[{"start":.8,"end":1.7,"text":"合算",
              "words":[word(.8,1.7,"合算")]}]
        raw=assign_and_group(seg,diar,True)[0]
        assigned,_=_assign(_frozen_words(seg)[0],diar,"legacy")
        self.assertEqual(raw[0]["speaker"],assigned[0]["speaker"])
        self.assertEqual(assigned[0]["speaker"],"話者1")

    def test_zero_duration_word_is_preserved_through_timing_evaluation(self):
        data=copy.deepcopy(self.asr)
        data[0]["words"][0]["end"]=data[0]["words"][0]["start"]
        # The legacy production assigner allows a point-timestamp token
        # and does not delete its lexical content.
        result=evaluate(self.ref,data,self.diar,duration=4.)
        self.assertEqual(result["word_count"],4)

    def test_missing_region_marks_unknown_instead_of_inventing_long_distance(self):
        w=[word(10,11,"離れた")]
        _,d=_assign(w,self.diar,"vote_no_fallback")
        self.assertEqual(d["unknown_words"],1)


if __name__=="__main__":
    unittest.main()
