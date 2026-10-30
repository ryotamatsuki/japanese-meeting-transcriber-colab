"""Tests for Japanese CER normalization / edit distance; all deterministic."""
import unittest
from scripts.evaluate_asr_cer import srt_text, normalized_ja, edit_distance, evaluate


class CERTests(unittest.TestCase):
    def test_reference_srt(self):
        srt = "1\n00:00:01,000 --> 00:00:02,000\n- こんにちは。\n- はい。\n\n2\n00:00:02,000 --> 00:00:03,000\n京都です。\n"
        self.assertEqual(srt_text(srt), "こんにちは。はい。京都です。")

    def test_normalized_japanese_not_dropping_semantic_content(self):
        self.assertEqual(normalized_ja("きょう　は、テスト！"), "きょうはテスト")
        self.assertNotEqual(normalized_ja("大臣"), normalized_ja("大事"))

    def test_exact_and_deletion_cer(self):
        self.assertEqual(edit_distance("abc","abc"),0)
        self.assertEqual(edit_distance("abc","ab"),1)
        self.assertEqual(evaluate("あいうえ","あいう")["normalized_cer"],0.25)

    def test_avoid_empty_reference(self):
        with self.assertRaises(ValueError):
            evaluate("。。","発言")


if __name__ == "__main__":
    unittest.main()
