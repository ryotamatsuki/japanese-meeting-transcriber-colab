"""Offline checks: independent Japanese ELAN reference parsing."""
import tempfile
import unittest
from pathlib import Path
from scripts.eval_elan_ja import load_elan


def sample_xml():
    times=''.join('<TIME_SLOT TIME_SLOT_ID="t%d" TIME_VALUE="%d"/>' % (i, i*1000)
                  for i in range(1,25))
    tiers=[]
    for who,ids in [('speaker_1',range(1,13,2)),('speaker_2',range(13,25,2))]:
        notes=''.join('<ANNOTATION><ALIGNABLE_ANNOTATION TIME_SLOT_REF1="t%d" TIME_SLOT_REF2="t%d"><ANNOTATION_VALUE>%s</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION>'
                      % (i,i+1,'あ&lt;la&gt;いう' if i==1 else 'はい。')
                      for i in ids)
        tiers.append('<TIER TIER_ID="%s">%s</TIER>' % (who,notes))
    return ('<?xml version="1.0"?><ANNOTATION_DOCUMENT><TIME_ORDER>%s</TIME_ORDER>%s</ANNOTATION_DOCUMENT>' % (times,''.join(tiers))).encode()


class ELANTests(unittest.TestCase):
    def test_two_speaker_timestamp_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'a.eaf'
            p.write_bytes(sample_xml())
            turns,digest=load_elan(p)
            self.assertEqual(len(turns),12)
            self.assertEqual(turns[0]['start'],1.0)
            self.assertEqual(turns[0]['end'],2.0)
            self.assertEqual(turns[0]['text'],'あいう')
            self.assertEqual({t['speaker_id'] for t in turns},{'speaker_1','speaker_2'})
            self.assertEqual(len(digest),64)

    def test_disallows_doctype(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'a.eaf'
            p.write_bytes(b'<!DOCTYPE annotation [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><ANNOTATION_DOCUMENT/>')
            with self.assertRaises(ValueError):
                load_elan(p)

    def test_fails_if_no_two_speaker_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'a.eaf'
            p.write_text('<ANNOTATION_DOCUMENT><TIME_ORDER><TIME_SLOT TIME_SLOT_ID="t1" TIME_VALUE="0"/></TIME_ORDER></ANNOTATION_DOCUMENT>')
            with self.assertRaises(ValueError):
                load_elan(p)

if __name__=='__main__':
    unittest.main()
