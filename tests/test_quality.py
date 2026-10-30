"""Safety checks for optional diarization stabilization. Not an acoustic accuracy benchmark."""
import unittest
from transcriber.quality import collapse_short_islands, find_overlap_windows
from transcriber.processor import Config


def seg(start, end, speaker):
    return {"start": start, "end": end, "speaker_id": speaker}


class QualityTests(unittest.TestCase):
    def test_removes_only_contiguous_short_aba(self):
        data = [seg(0, 1, "A"), seg(1, 1.067, "B"), seg(1.067, 2, "A")]
        output, audit = collapse_short_islands(data)
        self.assertEqual(output, [seg(0, 2, "A")])
        self.assertEqual(len(audit["changed_fragments"]), 1)
        self.assertEqual(data[1]["speaker_id"], "B")

    def test_preserves_real_short_backchannels_at_conservative_limit(self):
        data = [seg(0, 1, "A"), seg(1, 1.19, "B"), seg(1.19, 2, "A")]
        output, audit = collapse_short_islands(data)
        self.assertEqual(output, data)
        self.assertEqual(audit["raw_switches"], 2)

    def test_preserves_unlabelled_gap_and_non_island(self):
        data = [seg(0, 1, "A"), seg(1.09, 1.12, "B"), seg(1.12, 2, "A")]
        self.assertEqual(collapse_short_islands(data)[0], data)
        data2 = [seg(0, 1, "A"), seg(1, 1.04, "B"), seg(1.04, 2, "C")]
        self.assertEqual(collapse_short_islands(data2)[0], data2)

    def test_does_not_cascade_through_original_sequence(self):
        data = [seg(0, 1, "A"), seg(1, 1.04, "B"), seg(1.04, 1.08, "A"),
                seg(1.08, 1.12, "B"), seg(1.12, 2, "A")]
        out, audit = collapse_short_islands(data)
        self.assertTrue(audit["changed_fragments"])
        self.assertTrue(all(s["end"] > s["start"] for s in out))

    def test_preserves_real_speech_coverage(self):
        data = [seg(0, 1, "A"), seg(1, 1.04, "B"), seg(1.04, 2, "A"),
                seg(3, 4, "B")]
        out, _ = collapse_short_islands(data)
        self.assertEqual(sum(s["end"]-s["start"] for s in data),
                         sum(s["end"]-s["start"] for s in out))
        self.assertEqual(out[-1], seg(3, 4, "B"))

    def test_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            collapse_short_islands([seg(0, 2, "A"), seg(1, 3, "B")])
        with self.assertRaises(ValueError):
            collapse_short_islands([seg(-1, 0, "A")])
        with self.assertRaises(ValueError):
            collapse_short_islands([], max_island_seconds=1)

    def test_overlap_windows_are_not_artificial_speaker_relabels(self):
        regular = [seg(0, 10, "A"), seg(1, 1.6, "B"),
                   seg(3, 3.08, "B"), seg(5, 6, "B"), seg(6, 7, "B")]
        windows = find_overlap_windows(regular)
        self.assertEqual([(round(w["start"],2),round(w["end"],2)) for w in windows],
                         [(1,1.6),(5,7)])
        self.assertTrue(all(w["speaker_ids"] == ["A","B"] for w in windows))
        self.assertEqual(len(regular), 5)

    def test_overlap_requires_two_different_speakers(self):
        self.assertEqual(find_overlap_windows([seg(0,2,"A"), seg(1,3,"A")]), [])
        self.assertEqual(find_overlap_windows([]), [])
        with self.assertRaises(ValueError):
            find_overlap_windows([seg(-1, 2, "A")])

    def test_flag_is_opt_in(self):
        self.assertFalse(Config().quality_experiment)
        self.assertEqual(Config().speaker_cleanup_ms, 0)
        self.assertEqual(Config(quality_experiment=True, speaker_cleanup_ms=100).speaker_cleanup_ms, 100)
        with self.assertRaises(ValueError):
            Config(speaker_cleanup_ms=100)
        with self.assertRaises(ValueError):
            Config(quality_experiment=True, speaker_cleanup_ms=301)
        with self.assertRaises(ValueError):
            Config(enable_diarization=False, quality_experiment=True, speaker_cleanup_ms=100)


if __name__ == "__main__":
    unittest.main()
