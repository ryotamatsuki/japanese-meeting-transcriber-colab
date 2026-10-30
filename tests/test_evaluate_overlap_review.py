import unittest
from scripts.evaluate_overlap_review import merge,human_overlap,intersection_seconds


class OverlapLocalizationTests(unittest.TestCase):
    def test_human_overlap_and_intersection(self):
        rows=[{'speaker_id':'A','start':0,'end':6},
              {'speaker_id':'B','start':2,'end':4},
              {'speaker_id':'B','start':5,'end':8}]
        self.assertEqual(human_overlap(rows),[(2.0,4.0),(5.0,6.0)])
        candidate=merge([(3,4.5),(5.5,7)])
        self.assertEqual(intersection_seconds(human_overlap(rows),candidate),1.5)

    def test_duplicate_speaker_intervals_do_not_create_overlap(self):
        rows=[{'speaker_id':'A','start':0,'end':2},
              {'speaker_id':'A','start':1,'end':3}]
        self.assertEqual(human_overlap(rows),[])

    def test_invalid_review_window_rejected(self):
        with self.assertRaises(ValueError):
            merge([(3,1)])

if __name__=='__main__':
    unittest.main()
