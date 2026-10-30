"""Regression tests: compare exclusive and regular from the same inference ZIP."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile
from scripts.evaluate_diarization_modes import evaluate_pair


class PairedModeTests(TestCase):
    @staticmethod
    def write_reference(path):
        time_slots=''.join(f'<TIME_SLOT TIME_SLOT_ID="t{i}" TIME_VALUE="{i*1000}"/>' for i in range(1,25))
        tiers=[]
        for speaker, numbers in (('speaker_1',range(1,13,2)), ('speaker_2',range(13,25,2))):
            annotations=''.join(
                f'<ANNOTATION><ALIGNABLE_ANNOTATION TIME_SLOT_REF1="t{i}" '
                f'TIME_SLOT_REF2="t{i+1}"><ANNOTATION_VALUE>はい</ANNOTATION_VALUE>'
                f'</ALIGNABLE_ANNOTATION></ANNOTATION>' for i in numbers)
            tiers.append(f'<TIER TIER_ID="{speaker}">{annotations}</TIER>')
        path.write_text('<ANNOTATION_DOCUMENT><TIME_ORDER>'+time_slots+
                        '</TIME_ORDER>'+''.join(tiers)+'</ANNOTATION_DOCUMENT>')

    def test_one_zip_two_modes_with_identical_reference(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            eaf=d/'sample.eaf'
            archive=d/'sample.zip'
            self.write_reference(eaf)
            with ZipFile(archive,'w') as z:
                z.writestr('pyannote_話者区間.json',json.dumps({'segments':[{'start':1.0,'end':2.0,'speaker_id':'A'}]}))
                z.writestr('pyannote_通常話者区間.json',json.dumps({'segments':[{'start':1.0,'end':2.0,'speaker_id':'A'},{'start':1.3,'end':1.9,'speaker_id':'B'}]}))
            def score(reference,hypothesis,collar):
                self.assertEqual(collar,0.0)
                self.assertEqual(len(reference),12)
                return {'der_percent':30 if len(hypothesis)==1 else 20,
                        'jer_percent':40 if len(hypothesis)==1 else 22}
            with patch('scripts.evaluate_diarization_modes.compare',side_effect=score) as mock:
                result=evaluate_pair(eaf,archive)
                self.assertEqual(mock.call_count,2)
                self.assertEqual(result['der_regular_minus_exclusive_percentage_points'],-10)
                self.assertEqual(result['regular_intervals'],2)
                self.assertEqual(result['reference_overlap_floor']['speaker_count'],2)

    def test_missing_standard_output_is_rejected(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp); eaf=d/'sample.eaf'; archive=d/'sample.zip'
            self.write_reference(eaf)
            with ZipFile(archive,'w') as z:
                z.writestr('pyannote_話者区間.json','{"segments":[]}')
            with self.assertRaisesRegex(ValueError,'SAME quality-experiment run'):
                evaluate_pair(eaf,archive)
