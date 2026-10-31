import unittest
from scripts.jcre3_reference import load_reference


def fixture():
    return '\n'.join('\t'.join([speaker,'','00:00:01.000','1','1000',
        '00:00:02.000','2','2000','00:00:01.000','1','1000',text])
        for speaker,text in [('主人','(F あの)コップ<H>'),('ロボット','(R はい)(P)'),
                             ('主人','お水を'),('ロボット','どうぞ')]).encode()


class JcreReferenceTests(unittest.TestCase):
    def test_spoken_fillers_and_responses_are_not_deleted(self):
        rows,sha=load_reference(fixture())
        self.assertEqual(len(sha),64)
        self.assertIn('あのコップ',[r['text'] for r in rows])
        self.assertIn('はい',[r['text'] for r in rows])

    def test_unknown_tag_cannot_be_silently_counted_as_speech(self):
        with self.assertRaisesRegex(ValueError,'Unknown'):
            load_reference(fixture().replace('どうぞ'.encode(),b'(UNKNOWN)'))

    def test_bad_timestamp_units_and_nonfinite_values_fail(self):
        for bad in (fixture().replace(b'\t1000\t',b'\t10\t',1),
                    fixture().replace(b'\t1\t1000',b'\tnan\t1000',1)):
            with self.assertRaises(ValueError):load_reference(bad)
