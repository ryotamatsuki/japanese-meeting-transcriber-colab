import unittest
from scripts.v1_paired_analytics import paired_meeting_report


def row(meeting, recording, before, after, split="development"):
    return {"meeting_id": meeting, "recording_id": recording, "split": split,
            "baseline": {"cpcer": before}, "candidate": {"cpcer": after}}


class PairedMeetingEvaluationTests(unittest.TestCase):
    def test_duplicate_chunks_same_meeting_not_independent(self):
        rows = [row("M1", "A", .4, .3), row("M1", "B", .6, .5),
                row("M2", "C", .2, .25)]
        result = paired_meeting_report(rows, samples=1000)
        self.assertEqual(result["n_independent_meetings"], 2)
        self.assertEqual(result["n_recordings"], 3)
        self.assertEqual(result["improved_meetings"], 1)
        self.assertEqual(result["worsened_meetings"], 1)
        self.assertEqual(result["decision"], "EXPLORATORY_ONLY")

    def test_deterministic_cluster_intervals(self):
        records = [row("M"+str(i), "A", .3, .2, "heldout")
                   for i in range(20)]
        x = paired_meeting_report(records, samples=1000)
        y = paired_meeting_report(records, samples=1000)
        self.assertEqual(x["ci95"], y["ci95"])
        self.assertAlmostEqual(x["mean_delta"], -.1)
        self.assertEqual(x["decision"], "ELIGIBLE_FOR_PRE_REGISTERED_GATE_REVIEW")

    def test_one_meeting_cannot_have_ci(self):
        result = paired_meeting_report([row("M", "A", .3, .2)],
                                        samples=1000)
        self.assertIsNone(result["ci95"])
        self.assertEqual(result["decision"], "INSUFFICIENT_MEETINGS")

    def test_no_data_or_invalid_numeric(self):
        with self.assertRaises(ValueError):
            paired_meeting_report([])
        with self.assertRaises(ValueError):
            paired_meeting_report([row("M", "1", .5, float("nan"))])
        with self.assertRaises(ValueError):
            paired_meeting_report([row("M", "1", True, .2)])
        with self.assertRaises(ValueError):
            paired_meeting_report([row("M", "1", .4, .2),
                                   row("M", "1", .4, .3)])
        with self.assertRaises(ValueError):
            paired_meeting_report([row("M", "1", .4, .2, "development"),
                                   row("M", "2", .4, .3, "heldout")])


if __name__ == "__main__":
    unittest.main()
