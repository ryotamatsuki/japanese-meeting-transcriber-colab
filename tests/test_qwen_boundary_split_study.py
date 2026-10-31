import json
import unittest
from array import array
from scripts.qwen_boundary_split_study import (
    split_candidates,run_split_arms,split_proxy,split_scores)


def fixture():
    return [{"start":0.1,"end":2.9,"speaker":"話者1",
             "text":"質問です。回答します。",
             "words":[{"start":0.1,"end":1.0,"text":"質問です。"},
                      {"start":1.4,"end":2.9,"text":"回答します。"}]}]


class QwenSplitSeparateTests(unittest.TestCase):
    def test_four_arms_are_distinct_from_merge(self):
        rows=fixture()
        pcm=array("f",[.05])*(4*16000)
        def invoke(arm,messages):
            task=json.loads(messages[1]["content"])
            return json.dumps({"row_index":task["row_index"],
                 "word_index":task["word_index"],"decision":"split"})
        result=run_split_arms(rows,pcm,invoke)
        self.assertEqual(result["candidates"],["0:0"])
        self.assertEqual(result["decisions"]["baseline"]["0:0"],"keep")
        self.assertEqual(result["decisions"]["rules"]["0:0"],"split")
        self.assertEqual(result["decisions"]["audio_qwen"]["0:0"],"split")
        self.assertEqual(split_scores(result,{"0:0":"split"})["audio_qwen"]["true_splits"],1)
        self.assertEqual(rows,fixture())

    def test_human_proxy_is_not_gold(self):
        rows=fixture()
        human=[{"start":0.0,"end":1.1,"speaker_id":"主人"},
               {"start":1.3,"end":3.0,"speaker_id":"主人"}]
        self.assertEqual(split_proxy(human,rows,[(0,0)]),{"0:0":"split"})

    def test_no_timed_words_no_candidates(self):
        self.assertEqual(split_candidates([{"start":0,"end":2,"text":"文章"}]),[])

    def test_wrong_aligned_text_rejected(self):
        rows=fixture()
        rows[0]["text"]="改ざん"
        with self.assertRaises(ValueError):
            split_candidates(rows)

    def test_invalid_model_output_holds(self):
        result=run_split_arms(fixture(),array("f",[.01])*(4*16000),
                              lambda arm,msg:'{"decision":"split","extra":"wrong"}')
        self.assertEqual(result["decisions"]["text_qwen"]["0:0"],"hold")

if __name__=="__main__":
    unittest.main()
