"""Regression tests for research-only, fixed-text attribution diagnosis."""
import copy
import unittest

from scripts.qwen_error_decomposition import (
    IntervalIndex, annotate_words, compare_arms, compare_frozen_timing,
    extract_words, group_words, mark_qwen_timing_origins,
)


def one_word(text, start, end, origin=None):
    word = {"text": text, "start": start, "end": end}
    if origin:
        word["timing_origin"] = origin
    return {"words": [word]}


class QwenErrorDecompositionTests(unittest.TestCase):
    def test_nested_regular_intervals_are_not_skipped_by_end_bisect(self):
        # End times are [10, 2, 3]; bisecting that list is incorrect.
        index = IntervalIndex([
            {"start": 0, "end": 10, "speaker_id": "A"},
            {"start": 1, "end": 2, "speaker_id": "B"},
            {"start": 2, "end": 3, "speaker_id": "C"}])
        self.assertEqual(
            {speaker for _, _, speaker in index.overlapping(6, 7)}, {"A"})

    def test_regular_overlap_tie_stays_unknown_and_keeps_text(self):
        diar = [{"start": 0, "end": 1, "speaker_id": "A"},
                {"start": 0, "end": 1, "speaker_id": "B"}]
        out = annotate_words([one_word("はい", 0.2, 0.8)], diar)
        self.assertEqual(out[0]["speaker"], "話者不明")
        self.assertIn("ambiguous_speaker_vote", out[0]["review_reasons"])
        self.assertEqual(group_words(out)[0]["text"], "はい")

    def test_silence_abstains_without_legacy_nearest_1p2_second(self):
        out = annotate_words([one_word("はい", 1.3, 1.6)],
            [{"start": 0, "end": 1, "speaker_id": "A"}])
        self.assertEqual(out[0]["speaker"], "話者不明")
        self.assertEqual(out[0]["nearest_review_only"]["speaker_candidate"], "話者1")
        self.assertIn("no_speaker_overlap", out[0]["review_reasons"])

    def test_tiny_or_estimated_timing_cannot_force_speaker(self):
        diar = [{"start": 0, "end": 10, "speaker_id": "A"}]
        tiny = annotate_words([one_word("はい", 0.3, 0.301)], diar)[0]
        estimated = annotate_words([one_word("ええ", 8, 9, "estimated")], diar)[0]
        self.assertEqual(tiny["speaker"], "話者不明")
        self.assertEqual(estimated["speaker"], "話者不明")
        self.assertIn("timing_estimated", estimated["review_reasons"])

    def test_same_speaker_duplicate_intervals_are_not_double_counted(self):
        diar = [{"start": 0, "end": 1, "speaker_id": "A"},
                {"start": 0, "end": 1, "speaker_id": "A"},
                {"start": 0, "end": 0.2, "speaker_id": "B"}]
        row = annotate_words([one_word("はい", 0, 1)], diar)[0]
        # A 1 second, B .2 seconds => share 1/1.2, not 2/2.2.
        self.assertEqual(row["overlap_share_not_probability"], 0.833333)

    def test_unknown_words_are_charged_as_insertions(self):
        reference = [{"start": 0, "end": 1, "speaker_id": "A", "text": "はい"},
                     {"start": 1, "end": 2, "speaker_id": "B", "text": "そう"}]
        asr = [one_word("はい", 0, 0.6), one_word("そう", 1.2, 1.8)]
        diar = [{"start": 0, "end": 1, "speaker_id": "A"},
                {"start": 1, "end": 2, "speaker_id": "B"}]
        result = compare_arms(reference, asr, diar, oracle=True)
        self.assertEqual(result["flattened_cer"], 0)
        self.assertEqual(result["arms"]["conservative_exclusive"]["cpcer"], 0)
        self.assertIn("human_turn_regions_diagnostic_only", result["arms"])
        self.assertEqual(result["word_count"], 2)

    def test_frozen_timing_comparison_rejects_changed_tokens(self):
        ref = [{"start": 0, "end": 1, "speaker_id": "A", "text": "はい"}]
        diar = [{"start": 0, "end": 1, "speaker_id": "A"}]
        with self.assertRaisesRegex(ValueError, "changes words"):
            compare_frozen_timing(ref, [one_word("はい", 0, 1)],
                                  [one_word("別", 0, 1)], diar)

    def test_frozen_timing_comparison_has_same_text(self):
        ref = [{"start": 0, "end": 1, "speaker_id": "A", "text": "はい"}]
        diar = [{"start": 0, "end": 1, "speaker_id": "A"}]
        result = compare_frozen_timing(
            ref, [one_word("はい", 0, 0.8)],
            [one_word("はい", 0.1, 0.9)], diar)
        self.assertEqual(result["word_count"], 1)

    def test_invalid_timing_or_provenance_rejected(self):
        with self.assertRaises(ValueError):
            extract_words([one_word("はい", float("nan"), 1)])
        with self.assertRaises(ValueError):
            extract_words([one_word("はい", 0, 1, "certain")])

    def test_provenance_marks_reallocated_and_tail_estimated(self):
        chunks = [
            {"offset_sec": 0, "text": "こんにちは",
             "items": [{"text": "こんにちわ", "start_time": 0.1, "end_time": 0.8}]},
            {"offset_sec": 2, "text": "はい",
             "items": [{"text": "はい", "start_time": 1.01, "end_time": 1.2}]}]
        aligned = [{"words": [{"text": "こんにちは", "start": .1, "end": .8}]},
                   {"words": [{"text": "はい", "start": 2.999, "end": 3.0}]}]
        flagged = mark_qwen_timing_origins(chunks, aligned, 3.0)
        self.assertEqual(flagged[0]["words"][0]["timing_origin"], "realigned")
        self.assertEqual(flagged[1]["words"][0]["timing_origin"], "estimated")
        self.assertNotIn("timing_origin", aligned[0]["words"][0])


if __name__ == "__main__":
    unittest.main()
