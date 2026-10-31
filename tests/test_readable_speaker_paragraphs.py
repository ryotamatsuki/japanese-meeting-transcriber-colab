import io
import csv
import json
import unittest
import zipfile

from beta.readable import join_text, readable_paragraphs
from beta.core import build_export


class ReadableParagraphTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"start":0.0,"end":2.0,"speaker":"話者1","text":"本日の会議を"},
            {"start":2.1,"end":3.5,"speaker":"話者1","text":"始めます。"},
            {"start":3.6,"end":5.0,"speaker":"話者2","text":"承知しました。"},
            {"start":5.1,"end":7.2,"speaker":"話者1","text":"次の議題です。"},
            {"start":7.2,"end":8.3,"speaker":"話者1","text":"予算です。"},
        ]

    def test_only_contiguous_same_speaker_and_no_modification(self):
        before=json.dumps(self.rows,ensure_ascii=False,sort_keys=True)
        grouped=readable_paragraphs(self.rows)
        self.assertEqual([x["row_count"] for x in grouped],[2,1,2])
        self.assertEqual(grouped[0]["text"],"本日の会議を始めます。")
        self.assertEqual(grouped[0]["start"],0)
        self.assertEqual(grouped[0]["end"],3.5)
        self.assertEqual(grouped[2]["text"],"次の議題です。予算です。")
        self.assertEqual(json.dumps(self.rows,ensure_ascii=False,sort_keys=True),before)

    def test_unknown_and_blank_rows_not_joined(self):
        rows=[
            {"start":0,"end":1,"speaker":"話者不明","text":"a"},
            {"start":1,"end":2,"speaker":"話者不明","text":"b"},
            {"start":2,"end":3,"speaker":"話者1","text":"う"},
            {"start":3,"end":4,"speaker":"話者1","text":"  "},
            {"start":4,"end":5,"speaker":"話者1","text":"え"},
        ]
        self.assertEqual(len(readable_paragraphs(rows)),4)

    def test_english_boundary_and_no_llm_rewrite(self):
        self.assertEqual(join_text("hello","world"),"hello world")
        self.assertEqual(join_text("予算は","増えます"),"予算は増えます")
        self.assertEqual(join_text("あ。","はい"),"あ。はい")

    def test_export_only_human_readable_txt_changes(self):
        result=build_export(self.rows,source_name="nonconfidential")
        with zipfile.ZipFile(io.BytesIO(result)) as z:
            readable=z.read("文字起こし.txt").decode()
            original=z.read("文字起こし_発言単位.txt").decode()
            raw=json.loads(z.read("文字起こし.json"))
            raw_csv=z.read("文字起こし.csv").decode("utf-8-sig")
            srt=z.read("文字起こし.srt").decode()
        self.assertIn("話者1: 本日の会議を始めます。",readable)
        self.assertIn("話者1: 本日の会議を",original)
        self.assertNotIn("話者1: 本日の会議を始めます。",original)
        self.assertEqual(raw["utterances"],self.rows)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(raw_csv)))),5)
        self.assertIn("話者1: 始めます。",srt)

if __name__=="__main__":unittest.main()
