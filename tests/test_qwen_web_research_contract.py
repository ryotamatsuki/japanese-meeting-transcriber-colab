"""Research-only Qwen export contract; no GPU or real credentials in CI."""
import ast
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from beta.core import parse_original_archive, normalize_edits, build_export
from scripts.qwen_timing_bridge import attribute_qwen
from transcriber.exporters import export
from transcriber.processor import Config
from transcriber.qwen_web_research import speaker_labels

ROOT=Path(__file__).resolve().parents[1]


class QwenWebResearchContract(unittest.TestCase):
    def test_isolated_modal_app_cannot_change_whisper_default(self):
        source=(ROOT/'beta_modal_qwen_research.py').read_text()
        baseline=(ROOT/'beta_modal.py').read_text()
        ast.parse(source)
        self.assertIn('japanese-meeting-transcriber-qwen-web-research',source)
        self.assertIn('transcribe_qwen_research',source)
        self.assertNotIn('transcribe_qwen_research',baseline)
        self.assertIn("process(audio,Path(tmp)/'results'",baseline)
        self.assertIn("quality_experiment=False",baseline)
        self.assertNotIn('modal.asgi_app()', (ROOT/'transcriber/qwen_web_research.py').read_text())

    def test_speaker_labels_follow_first_onset_order(self):
        diar=[{'speaker_id':'SPEAKER_B','start':1,'end':2},
              {'speaker_id':'SPEAKER_A','start':0,'end':1},
              {'speaker_id':'SPEAKER_B','start':2,'end':3}]
        self.assertEqual(speaker_labels(diar),
                         {'SPEAKER_A':'話者1','SPEAKER_B':'話者2'})

    def test_gpu_research_failure_reason_is_allowlisted(self):
        source=(ROOT/'beta_modal_qwen_research.py').read_text()
        self.assertIn("job['failure_reason_code']=safe_codes.get(str(exc),'unclassified')",source)
        self.assertNotIn("job['error']=str(exc)",source)

    def test_qwen_research_export_roundtrip(self):
        chunks=[
            {'offset_sec':0,'duration_sec':3,'text':'こんにちは。はい',
             'items':[{'text':'こんにちは','start_time':0.1,'end_time':1.0},
                      {'text':'はい','start_time':2.0,'end_time':2.7}]},
            {'offset_sec':3,'duration_sec':3,'text':'ありがとうございます。',
             'items':[{'text':'ありがとう','start_time':0.2,'end_time':1.8},
                      {'text':'ございます','start_time':1.8,'end_time':2.8}]}]
        diar=[{'start':0,'end':3,'speaker_id':'A'},
              {'start':3,'end':6,'speaker_id':'B'}]
        rows,integrity=attribute_qwen(chunks,diar,6.0)
        self.assertTrue(integrity['all_normalized_text_preserved'])
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); source=base/'test.wav'
            source.write_bytes(b'synthetic placeholder; no real audio')
            folder=base/'results'; folder.mkdir()
            outdir=folder/'sample';outdir.mkdir()
            (outdir/'qwen_asr.json').write_text(json.dumps({'segments':chunks},ensure_ascii=False))
            (outdir/'pyannote_話者区間.json').write_text(json.dumps({'segments':diar}))
            (outdir/'pyannote_話者区間.csv').write_text('start,end,speaker_id\n')
            job={'path':source,'sha256':'a'*64,'prefix':'sample','outdir':outdir,
                 'asr_segments':chunks,'diar_segments':diar,'asr_json_name':'qwen_asr.json',
                 'utterances':rows,'speaker_map':{'A':'話者1','B':'話者2'},
                 'word_count':integrity['aligned_tokens']}
            config=Config(enable_diarization=True,expected_speakers=2)
            out=export(job,folder,config,
                       {'model':'Qwen/Qwen3-ASR-1.7B','research_only':True},
                       {'model':'pyannote/speaker-diarization-community-1'})
            with ZipFile(out) as z:
                self.assertIn('qwen_asr.json',z.namelist())
                self.assertNotIn('whisper_asr.json',z.namelist())
                self.assertTrue(z.testzip() is None)
            parsed=parse_original_archive(out.read_bytes())
            saved=normalize_edits(parsed['rows'],6.0)
            self.assertEqual(len(saved),len(rows))
            with ZipFile(io.BytesIO(build_export(saved))) as z:
                self.assertIn('文字起こし.srt',z.namelist())
                self.assertIn('文字起こし.json',z.namelist())
            self.assertIn('こんにちは', ''.join(r['text'] for r in saved))


if __name__=='__main__':
    unittest.main()
