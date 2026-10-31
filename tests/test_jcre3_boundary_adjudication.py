import unittest
from scripts.jcre3_boundary_adjudication import proxy_boundaries,verified_labels_from_review


def r(start,end,speaker,text="test"):
    return {"start":start,"end":end,"speaker_id":speaker,"text":text}


class JCre3BoundaryAdjudicationTests(unittest.TestCase):
    def test_same_reference_turn_is_only_a_proxy_merge(self):
        human=[r(0,4,"主人"),r(4,7,"ロボット"),r(7,10,"主人")]
        rows=[{"start":0,"end":1.7},{"start":1.8,"end":3.7},
              {"start":4.1,"end":6.8}]
        self.assertEqual(proxy_boundaries(human,rows,[0,1]),{"0":"merge","1":"keep"})

    def test_same_speaker_different_human_turn_is_uncertain(self):
        human=[r(0,2,"主人"),r(2.1,4,"主人")]
        rows=[{"start":0,"end":1.9},{"start":2.2,"end":3.9}]
        self.assertEqual(proxy_boundaries(human,rows,[0]),{"0":"uncertain"})

    def test_alignment_mismatch_is_uncertain(self):
        human=[r(0,2,"主人"),r(2,4,"ロボット")]
        rows=[{"start":1.7,"end":2.3},{"start":2.5,"end":3.9}]
        self.assertEqual(proxy_boundaries(human,rows,[0]),{"0":"uncertain"})

    def test_requires_real_adjudicators(self):
        sheet={"boundaries":[{"boundary_id":0,"annotator1":None,"annotator2":None,
                              "final_label":None}]}
        with self.assertRaises(ValueError):
            verified_labels_from_review(sheet)
        sheet["boundaries"][0].update(
            {"annotator1":"merge","annotator2":"keep","final_label":"keep"})
        with self.assertRaises(ValueError):
            verified_labels_from_review(sheet)
        sheet["boundaries"][0]["adjudication_note"]="Listened and compared timestamps"
        self.assertEqual(verified_labels_from_review(sheet),{"0":"keep"})

    def test_does_not_allow_proxy_to_masquerade_as_manual_annotation(self):
        with self.assertRaises(ValueError):
            verified_labels_from_review({"boundaries":[{
                "boundary_id":1, "proxy":"merge", "final_label":"merge"}]})


if __name__=="__main__":
    unittest.main()
