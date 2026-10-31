"""2-4 speaker reference-loader safety and fidelity tests."""
import tempfile
import unittest
from pathlib import Path

from scripts.v1_meeting_reference import load_meeting_eaf


def eaf(tiers=("speaker_1", "speaker_2", "speaker_3")):
    times = "".join(
        '<TIME_SLOT TIME_SLOT_ID="ts{}" TIME_VALUE="{}"/>'.format(i+1, i*1000)
        for i in range(len(tiers)+1))
    bodies = "".join(
        '<TIER TIER_ID="{}"><ANNOTATION><ALIGNABLE_ANNOTATION TIME_SLOT_REF1="ts{}" TIME_SLOT_REF2="ts{}"><ANNOTATION_VALUE>{}</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION></TIER>'.format(
            speaker, i+1, i+2, "こんにちは" if i==0 else "はい")
        for i, speaker in enumerate(tiers))
    return ('<?xml version="1.0"?><ANNOTATION_DOCUMENT><TIME_ORDER>'
            + times + '</TIME_ORDER>' + bodies + '</ANNOTATION_DOCUMENT>').encode()


class ReferenceLoaderTests(unittest.TestCase):
    def load_bytes(self, data, tiers=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"reference.eaf"
            path.write_bytes(data)
            return load_meeting_eaf(path, speaker_tiers=tiers)

    def test_three_human_speakers_with_timing(self):
        turns, sha, meta = self.load_bytes(eaf())
        self.assertEqual(meta["reference_speakers"], 3)
        self.assertEqual(meta["reference_turns"], 3)
        self.assertEqual([t["speaker_id"] for t in turns],
                         ["speaker_1", "speaker_2", "speaker_3"])
        self.assertEqual(turns[1]["start"], 1.0)
        self.assertEqual(len(sha), 64)

    def test_four_and_explicit_nonstandard_tiers(self):
        names = ("A", "B", "C", "D")
        rows, _, meta = self.load_bytes(eaf(names), tiers=names)
        self.assertEqual(meta["reference_speakers"], 4)
        self.assertEqual(len(rows), 4)
        with self.assertRaisesRegex(ValueError, "Require"):
            self.load_bytes(eaf(names))

    def test_missing_human_tier_rejected(self):
        with self.assertRaises(ValueError):
            self.load_bytes(eaf(), tiers=["speaker_1", "speaker_2", "speaker_4"])

    def test_xml_entity_and_doctype_rejected(self):
        injection = b'<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        with self.assertRaises(ValueError):
            self.load_bytes(injection + eaf())

    def test_corrupt_timing_rejected(self):
        bad = eaf().replace(b'TIME_VALUE="1000"', b'TIME_VALUE="0"')
        with self.assertRaisesRegex(ValueError, "nonpositive"):
            self.load_bytes(bad)

    def test_one_speaker_cannot_pass_as_multi_speaker(self):
        with self.assertRaisesRegex(ValueError, "Require"):
            self.load_bytes(eaf(("speaker_1",)))


if __name__ == "__main__":
    unittest.main()
