import hashlib
import unittest
from unittest.mock import patch
from scripts.diarizer_nvidia_matched_eval import (
    MODELS,parse_nemo_segments,score_model,assert_frozen_baseline)


def reg(a,b,s):
    return {"start":a,"end":b,"speaker_id":s}

class NvidiaDiarizerMatchedContract(unittest.TestCase):
    def test_triplet_parse_and_bound(self):
        seg=parse_nemo_segments(
            ["0.10 0.30 speaker_0","0.20 0.40 speaker_1"],
            duration=1.0,model_name=MODELS[0])
        self.assertEqual(len(seg),2)
        self.assertEqual(seg[0]["speaker_id"],"nvidia_0")
        self.assertEqual(seg[1]["speaker_id"],"nvidia_1")
    def test_accepts_triplet_numeric_format(self):
        seg=parse_nemo_segments([[0.0,.4,0],[.6,1.0,1]],
            duration=1.0,model_name=MODELS[1])
        self.assertEqual(len(seg),2)
    def test_rejects_invalid_or_uncertain_output(self):
        for rows in ([["x",.4,0]],["0.1 0.5 badspeaker"],
                     ["0.2 1.9 speaker_1"], ["0.2 0.3 speaker_9"],[]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    parse_nemo_segments(rows,duration=1.0,model_name=MODELS[1])
        with self.assertRaises(ValueError):
            parse_nemo_segments([],duration=1.0,model_name="unknown")
    def test_matched_token_integrity_rejects_edits(self):
        ref=[{**reg(0,1,"A"),"text":"あ"},{"start":1,"end":2,
              "speaker_id":"B","text":"い"}]
        asr=[{"words":[{"start":.1,"end":.6,"text":"あ"},
                        {"start":1.2,"end":1.7,"text":"い"}]}]
        digest=hashlib.sha256("あい".encode()).hexdigest()
        with patch("scripts.diarizer_nvidia_matched_eval.evaluate_der",
                   return_value={"der_percent":0.0,"jer_percent":0.0,
                      "false_alarm_seconds":0.0,"missed_detection_seconds":0.0,
                      "speaker_confusion_seconds":0.0,"candidate_speaker_count":2}):
            out=score_model(ref,asr,[reg(0,1,"X"),reg(1,2,"Y")],
                            original_hash=digest)
            self.assertEqual(out["cpcer"],0)
            self.assertEqual(out["predicted_speakers"],2)
            with self.assertRaises(ValueError):
                score_model(ref,asr,[reg(0,1,"X"),reg(1,2,"Y")],
                            original_hash=hashlib.sha256("違う".encode()).hexdigest())
    def test_baseline_drift_is_fatal(self):
        fixed={"reference_chars":2,"cpcer_edits":0,"DER":12.0}
        self.assertTrue(assert_frozen_baseline(fixed,
            {"reference_chars":2,"baseline_edits":0,"baseline_DER":12.0}))
        with self.assertRaises(ValueError):
            assert_frozen_baseline(fixed,
              {"reference_chars":2,"baseline_edits":1,"baseline_DER":12.0})
        with self.assertRaises(ValueError):
            assert_frozen_baseline(fixed,
              {"reference_chars":2,"baseline_edits":0,"baseline_DER":13.0})

if __name__=="__main__":unittest.main()
