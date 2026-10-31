"""Synthetic multi-speaker test fixtures; no licensed corpus committed."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_multispeaker_ja import load_reference
from scripts.evaluate_attributed_transcript import permutation_cer


def fixture(n=4):
    return {'source':'synthetic-unlicensed-fixture','license_approved':True,
            'human_verified':True,'expected_speakers':n,
            'turns':[{'start':i*2.0,'end':i*2.0+1.5,
                      'speaker_id':f'Person{i%n}','text':f'発言{i}番目です。'}
                     for i in range(4*n)]}


class MultiSpeakerReferenceTests(unittest.TestCase):
    def test_four_speaker_synthetic_exact_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'annotation.json'
            path.write_text(json.dumps(fixture(),ensure_ascii=False))
            rows,meta=load_reference(path)
            hypothesis=[{**row,'speaker':row['speaker_id']} for row in rows]
            self.assertEqual(meta['expected_speakers'],4)
            self.assertEqual(permutation_cer(rows,hypothesis)['cpcer'],0)

    def test_three_speakers_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'annotation.json'
            path.write_text(json.dumps(fixture(3),ensure_ascii=False))
            self.assertEqual(load_reference(path)[1]['expected_speakers'],3)

    def test_two_speaker_reference_cannot_satisfy_gate(self):
        d=fixture(3);d['expected_speakers']=2
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'annotation.json'
            p.write_text(json.dumps(d,ensure_ascii=False))
            with self.assertRaises(ValueError):load_reference(p)

    def test_unapproved_or_nonhuman_reference_rejected(self):
        for key in ('license_approved','human_verified'):
            d=fixture()
            d[key]=False
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'annotation.json'
                p.write_text(json.dumps(d,ensure_ascii=False))
                with self.assertRaises(ValueError):load_reference(p)

    def test_invalid_intervals_rejected(self):
        d=fixture()
        d['turns'][0]['end']=d['turns'][0]['start']
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'annotation.json'
            p.write_text(json.dumps(d,ensure_ascii=False))
            with self.assertRaises(ValueError):load_reference(p)


if __name__=='__main__':unittest.main()
