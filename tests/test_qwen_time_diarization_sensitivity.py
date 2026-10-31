import unittest
from scripts.qwen_time_diarization_sensitivity import (
    OFFSETS_SECONDS, shifted_intervals, evaluate_sensitivity
)

def region(a,b,sp):
    return {"start":a,"end":b,"speaker_id":sp}

def word(a,b,text):
    return {"start":a,"end":b,"text":text}

class TimingSpeakerSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.reference=[
            {**region(0,2,"A"),"text":"あいう"},
            {**region(2,4,"B"),"text":"えお"},
        ]
        self.asr=[{"text":"あいう","start":0,"end":2,"words":[
            word(.1,.5,"あ"),word(.6,1.0,"い"),word(1.2,1.6,"う")]},
            {"text":"えお","start":2,"end":4,"words":[
            word(2.3,2.7,"え"),word(3.0,3.4,"お")]}]
        self.diar=[region(0,2,"S1"),region(2,4,"S2")]
    def test_zero_shift_matches_original(self):
        out=evaluate_sensitivity(self.reference,self.asr,self.diar,self.diar,4)
        self.assertEqual(out["baseline_legacy_exclusive"]["cpcer"],0)
        self.assertEqual(out["auto_safe_max_overlap"]["cpcer"],0)
        self.assertEqual(out["human_regions_safe_max_overlap_diagnostic"]["cpcer"],0)
        self.assertEqual(len(out["relative_time_shift_sensitivity"]),7)
        self.assertEqual(out["relative_time_shift_sensitivity"][3]["relative_shift_seconds"],0)
    def test_shifted_diar_perturbation_not_transcript(self):
        shifted,meta=shifted_intervals(self.diar,-.3,4)
        self.assertEqual(shifted[0]["start"],0)
        self.assertEqual(shifted[1]["start"],1.7)
        self.assertEqual(meta["clipped_regions"],1)
        out=evaluate_sensitivity(self.reference,self.asr,self.diar,self.diar,4)
        self.assertEqual(out["frozen_word_count"],5)
        self.assertNotIn("あいう",str(out))
    def test_nested_intervals_not_invalid_end_bisect(self):
        asr=[{"words":[word(.1,.5,"あ"),word(6,7,"い"),word(8,9,"う"),
                       word(9.1,9.4,"え")]}]
        ref=[{**region(0,10,"A"),"text":"あいうえ"},
             {**region(1,2,"B"),"text":"お"}]
        diar=[region(0,10,"A"),region(1,2,"B"),region(2,3,"C")]
        out=evaluate_sensitivity(ref,asr,diar,diar,10)
        self.assertTrue(out["auto_safe_max_overlap"]["cpcer"] >= 0)
    def test_refuse_changed_offsets_or_invalid_bounds(self):
        with self.assertRaises(ValueError):
            evaluate_sensitivity(self.reference,self.asr,self.diar,self.diar,4,offsets=(0,))
        with self.assertRaises(ValueError):
            shifted_intervals([region(1,0,"A")],0,4)
        with self.assertRaises(ValueError):
            shifted_intervals(self.diar,float("nan"),4)
    def test_ambiguous_oracle_not_deployment(self):
        out=evaluate_sensitivity(self.reference,self.asr,self.diar,self.diar,4)
        self.assertIn("NOT select a production",out["warning"])

if __name__=="__main__":
    unittest.main()
