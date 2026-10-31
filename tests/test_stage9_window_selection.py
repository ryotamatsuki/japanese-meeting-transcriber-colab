"""Stage9 oracle-window selection regression: do not clip truncated utterances."""
from unittest import TestCase
from scripts.stage9_select_eval_windows import windows

def row(s,e,person,text='こんにちは'):
    return {'start':s,'end':e,'speaker_id':person,'text':text}

class WindowsTests(TestCase):
    def test_selects_and_expands_to_include_other_annotations(self):
        rows=[row(1,4,'speaker_1'),row(2,4.5,'speaker_2'),
              row(4,5,'speaker_1')]
        x=windows(rows,max_seconds=7,max_count=2)
        self.assertEqual(len(x),1)
        self.assertEqual((x[0]['start'],x[0]['end']),(1,5))
        self.assertEqual(x[0]['annotated_turns'],3)

    def test_skips_when_long_crossing_utterance_cannot_be_included(self):
        rows=[row(0,10,'speaker_1'),row(1,2,'speaker_2')]
        self.assertEqual(windows(rows,max_seconds=7),[])

    def test_does_not_report_nonoverlap(self):
        self.assertEqual(windows([row(1,2,'speaker_1'),row(2,3,'speaker_2')]),[])

    def test_rejects_short_bare_interjections(self):
        rows=[row(1,3,'speaker_1','はい'),row(2,3,'speaker_2','あ')]
        self.assertEqual(windows(rows),[])
