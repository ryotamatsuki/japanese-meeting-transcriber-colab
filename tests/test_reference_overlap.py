import unittest
from scripts.analyze_reference_overlap import overlap_floor


class HumanReferenceOverlapTests(unittest.TestCase):
    def test_two_speaker_overlap_floor(self):
        rows=[
            {'start':0,'end':5,'speaker_id':'a'},
            {'start':3,'end':7,'speaker_id':'b'},
        ]
        result=overlap_floor(rows)
        self.assertAlmostEqual(result['reference_speaker_seconds'],9.0)
        self.assertAlmostEqual(result['speech_union_seconds'],7.0)
        self.assertAlmostEqual(result['overlap_excess_speaker_seconds'],2.0)
        self.assertAlmostEqual(result['exclusive_diarization_der_floor_percent'],100*2/9,places=6)

    def test_same_speaker_duplicate_annotation_not_double_counted(self):
        rows=[
            {'start':0,'end':3,'speaker_id':'a'},
            {'start':1,'end':4,'speaker_id':'a'},
            {'start':2,'end':5,'speaker_id':'b'},
        ]
        r=overlap_floor(rows)
        self.assertEqual(r['reference_speaker_seconds'],7.0)
        self.assertEqual(r['overlap_excess_speaker_seconds'],2.0)

    def test_no_overlap_floor_zero(self):
        r=overlap_floor([
            {'start':0,'end':1,'speaker_id':'a'},
            {'start':1,'end':3,'speaker_id':'b'}])
        self.assertEqual(r['overlap_excess_speaker_seconds'],0)
        self.assertEqual(r['exclusive_diarization_der_floor_percent'],0)

    def test_ill_formed_is_rejected(self):
        with self.assertRaises(ValueError):
            overlap_floor([{'start':1,'end':1,'speaker_id':'a'}])


if __name__=='__main__':
    unittest.main()
