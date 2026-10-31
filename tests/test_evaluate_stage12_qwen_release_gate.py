"""CPU-only evidence gate tests: prevent accidental promotion on truncated runs."""
import copy
import json
import unittest
from pathlib import Path
from scripts.evaluate_stage12_qwen_release_gate import audit, EXPECTED_IDS

BASELINE = Path(__file__).resolve().parents[1]/'docs/evidence/stage8_whisper_cpcer_10_20261030.json'


def fixtures():
    base=json.loads(BASELINE.read_text(encoding='utf-8'))
    rows=[]
    for b in base['records']:
        rows.append({'eaf_sha256':b['eaf_sha256'], 'reference_characters':b['reference_characters'],
                     'audio_duration_seconds':600.0, 'last_word_end_seconds':599.0,
                     'qwen_attributed_cpcer_percent':b['whisper_attributed_cpcer_percent']-6,
                     'qwen_speaker_count':2,'utterances':100,'aligned_tokens':900,'text_preserved':True,
                     'qwen_alignment_seconds':60.0,'qwen_model_load_seconds':8.0,
                     'model':'Qwen/Qwen3-ASR-1.7B','aligner':'Qwen/Qwen3-ForcedAligner-0.6B',
                     'diarizer':'pyannote/speaker-diarization-community-1 exclusive'})
    qwen={'attempted':10,'complete':10,'failed':[],'no_web_or_production_code_changes':True,'per_record':rows}
    return base,qwen


class Stage12GateTests(unittest.TestCase):
    def test_10_record_research_gate_only(self):
        a,b=fixtures()
        out=audit(a,b)
        self.assertEqual(out['research_extension_gate'],'PASS')
        self.assertEqual(out['release_status'],'NO_GO')
        self.assertFalse(out['production_model_changed'])
        self.assertEqual(out['tested'],10)
        self.assertEqual(out['median_paired_change_pp'],-6)

    def test_missing_record_is_not_success(self):
        a,b=fixtures()
        b['per_record'].pop()
        with self.assertRaisesRegex(ValueError,'Missing Qwen'):
            audit(a,b)

    def test_duplicate_record_is_rejected(self):
        a,b=fixtures()
        b['per_record'][1]=copy.deepcopy(b['per_record'][0])
        with self.assertRaisesRegex(ValueError,'Duplicate Qwen'):
            audit(a,b)

    def test_wrong_eaf_is_rejected(self):
        a,b=fixtures()
        b['per_record'][0]['eaf_sha256']='a'*64
        with self.assertRaisesRegex(ValueError,'hash'):
            audit(a,b)

    def test_wrong_reference_characters_is_rejected(self):
        a,b=fixtures()
        b['per_record'][0]['reference_characters']+=1
        with self.assertRaisesRegex(ValueError,'normalization'):
            audit(a,b)

    def test_corrupt_timestamp_is_rejected(self):
        a,b=fixtures()
        b['per_record'][0]['last_word_end_seconds']=1
        with self.assertRaisesRegex(ValueError,'tail'):
            audit(a,b)

    def test_failed_integrity_or_wrong_diarization_is_rejected(self):
        a,b=fixtures()
        b['per_record'][0]['text_preserved']=False
        with self.assertRaisesRegex(ValueError,'not preserved'):
            audit(a,b)
        a,b=fixtures()
        b['per_record'][0]['diarizer']='regular'
        with self.assertRaisesRegex(ValueError,'mode mismatch'):
            audit(a,b)

    def test_no_promotion_when_10_quality_worse(self):
        a,b=fixtures()
        b['per_record'][0]['qwen_attributed_cpcer_percent']+=20
        self.assertEqual(audit(a,b)['research_extension_gate'],'NOT_MET')

    def test_rejects_nan_and_boolean_scores(self):
        a,b=fixtures()
        b['per_record'][0]['qwen_attributed_cpcer_percent']=float('nan')
        with self.assertRaises(ValueError):audit(a,b)
        a,b=fixtures()
        b['per_record'][0]['qwen_attributed_cpcer_percent']=True
        with self.assertRaises(ValueError):audit(a,b)

    def test_partial_two_is_explicit_and_not_passed(self):
        a,b=fixtures()
        b['per_record']=[b['per_record'][0],b['per_record'][4]]
        b['attempted']=b['complete']=2
        out=audit(a,b,expected_ids=('01','05'))
        self.assertEqual(out['tested'],2)
        self.assertEqual(out['research_extension_gate'],'NOT_MET')
        with self.assertRaisesRegex(ValueError,'Incomplete Qwen'):
            audit(a,b,expected_ids=EXPECTED_IDS)


if __name__=='__main__': unittest.main()
