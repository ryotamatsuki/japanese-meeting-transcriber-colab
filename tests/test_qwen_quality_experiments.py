"""CPU tests. No speech samples or model weights required."""
import unittest

from scripts.qwen_quality_experiments import (
    checked_context, diagnose_review_candidates, oracle_exclusive_intervals,
    edit_components, paired_median_bootstrap, prefer_original_if_uncertain,
    research_summary,
)


class QualityResearchTests(unittest.TestCase):
    def test_context_opt_in_and_bound(self):
        self.assertEqual(checked_context(None), "")
        self.assertEqual(checked_context("  愛媛県 ゼロ県債  "), "愛媛県 ゼロ県債")
        with self.assertRaises(ValueError):
            checked_context("x"*301)
        with self.assertRaises(ValueError):
            checked_context("unsafe\x00value")

    def test_edit_operations_are_not_character_count_differences(self):
        r=edit_components("愛媛の計画", "愛知の計画")
        self.assertEqual(r["substitutions"],1)
        self.assertEqual(r["insertions"],0)
        self.assertEqual(r["deletions"],0)
        self.assertEqual(r["edit_distance"],1)
        r=edit_components("こんにちは", "こんちは")
        self.assertEqual(r["deletions"],1)

    def test_review_not_confirmed_error(self):
        words=[
            {"start":0.0,"end":6.0,"text":"はい","speaker":"話者1"},
            {"start":6.05,"end":6.65,"text":"100円","speaker":"話者2"},
            {"start":11.0,"end":11.2,"text":"はい","speaker":"話者1"},
        ]
        flags=diagnose_review_candidates(words,overlap_ranges=[(6.0,6.4)])
        self.assertIn("long_low_text",flags[0]["reasons"])
        self.assertIn("important_number",flags[1]["reasons"])
        self.assertIn("speaker_boundary_review",flags[1]["reasons"])
        self.assertIn("overlap_speech_review",flags[1]["reasons"])
        self.assertIn("long_gap_review",flags[2]["reasons"])

    def test_oracle_overlap_is_ambiguous_not_magic(self):
        rows=[
            {"start":0.0,"end":4.0,"speaker_id":"s1"},
            {"start":2.0,"end":6.0,"speaker_id":"s2"},
        ]
        intervals,amb=oracle_exclusive_intervals(rows,6.0)
        self.assertAlmostEqual(amb,2)
        self.assertEqual(intervals,[{"start":0.0,"end":2.0,"speaker_id":"s1"},
                                    {"start":2.0,"end":6.0,"speaker_id":"s2"}])

    def test_paired_bootstrap_is_repeatable_and_recording_level(self):
        base=[.32,.39,.42,.46]
        cand=[.30,.42,.38,.44]
        first=paired_median_bootstrap(base,cand,n_boot=1000)
        second=paired_median_bootstrap(base,cand,n_boot=1000)
        self.assertEqual(first,second)
        self.assertEqual(first["n"],4)
        self.assertEqual(first["n_improved"],3)
        self.assertEqual(first["n_worsened"],1)
        self.assertEqual(len(first["ci95"]),2)

    def test_selection_cannot_automatically_replace_original(self):
        for valid in (True,False):
            result,_=prefer_original_if_uncertain("source","hallucination",validated=valid)
            self.assertEqual(result,"source")

    def test_public_metrics_reject_raw_content(self):
        self.assertEqual(research_summary([{"cpcer":.25,"audio_seconds":600}])[0]["cpcer"],.25)
        for key in ("transcript","context","token_value","raw_text","original_filename"):
            with self.assertRaises(ValueError,msg=key):
                research_summary([{key:"secret"}])

    def test_invalid_timing_fail_closed(self):
        with self.assertRaises(ValueError):
            diagnose_review_candidates([{"start":2.0,"end":1.0,"text":"test"}])


if __name__=="__main__":
    unittest.main()
