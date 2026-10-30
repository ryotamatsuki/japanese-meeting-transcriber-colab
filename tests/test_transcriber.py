"""Offline regression tests. These do NOT establish GPU/model accuracy."""
import ast
from bisect import bisect_right
import csv
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcriber.alignment import assign_and_group
from transcriber.exporters import export
from transcriber.files import safe_name, sha256_file
from transcriber.processor import Config, process

ROOT = Path(__file__).resolve().parents[1]
NB = json.loads((ROOT/'notebooks/meeting_transcriber.ipynb').read_text())


def notebook_function(name, enabled=True):
    nodes = [x for c in NB['cells'] if c['cell_type']=='code'
             for x in ast.parse(''.join(c['source'])).body
             if isinstance(x, ast.FunctionDef) and x.name == name]
    scope = {'ENABLE_DIARIZATION': enabled, 'bisect_right': bisect_right}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<notebook>', 'exec'), scope)
    return scope[name]


class RegressionTests(unittest.TestCase):
    def test_alignment_matches_notebook(self):
        rng = random.Random(89)
        for enabled in (True, False):
            original = notebook_function('assign_and_group', enabled)
            for _ in range(100):
                diar = [{'start': i*3, 'end': i*3+2, 'speaker_id': str(i%2)} for i in range(12)] if enabled else []
                words = [{'start': i*.47, 'end': i*.47+rng.random()*.4,
                          'text': rng.choice(['あ', 'はい。', '内容'*40, ' '])} for i in range(80)]
                asr = [{'start': 0, 'end': 40, 'text': '', 'words': words},
                       {'start': 40, 'end': 41, 'text': '単語なし'}]
                self.assertEqual(original(asr, diar), assign_and_group(asr, diar, enabled))
        # Boundary cases: nearest within/outside 1.2 sec, long utterance and pause splits.
        asr = [{'start': 0, 'end': 10, 'words': [
            {'start': 1.9, 'end': 2.0, 'text': '近い'},
            {'start': 4, 'end': 4.1, 'text': '遠い'}]}]
        diar = [{'start': 0, 'end': 1, 'speaker_id': 'A'}]
        rows, _, _ = assign_and_group(asr, diar)
        self.assertEqual([r['speaker'] for r in rows], ['話者1', '話者不明'])

    def test_export_bytes_match_notebook(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base/'sample.wav'; source.write_bytes(b'fixture')
            out = base/'result'; out.mkdir()
            asr = [{'start': 0., 'end': 1., 'text': '確認します。', 'words': []}]
            job = dict(path=source, sha256=sha256_file(source), prefix='sample', outdir=out,
                       asr_segments=asr, diar_segments=[{'start': 0., 'end': 1., 'speaker_id': 'A'}],
                       utterances=[{'start': 0., 'end': 1., 'speaker': '話者1', 'text': '確認します。'}],
                       speaker_map={'A': '話者1'}, word_count=1)
            (out/'whisper_asr.json').write_text(json.dumps(asr))
            for suffix in ('csv','json'):
                (out/f'pyannote_話者区間.{suffix}').write_text('[]')
            for enabled in (True, False):
                config = Config(enable_diarization=enabled)
                if not enabled:
                    job.update(diar_segments=[], speaker_map={})
                path = export(job, base, config, {'model':'large-v3'}, {'model':'community-1'})
                with ZipFile(path) as archive:
                    expected = {n: archive.read(n) for n in archive.namelist()}
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(len(expected), 8 if enabled else 6)
                    self.assertTrue(expected['sample_文字起こし.csv'].startswith(b'\xef\xbb\xbf'))
                tree = ast.parse(''.join(NB['cells'][18]['source']))
                nodes = [x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.For))][:3]
                scope = dict(jobs=[job], ROOT=base, ENABLE_DIARIZATION=enabled,
                             ASR_SETTINGS={'model':'large-v3'}, DIAR_SETTINGS={'model':'community-1'},
                             csv=csv, json=json, ZipFile=ZipFile, ZIP_DEFLATED=ZIP_DEFLATED, zip_files=[])
                exec(compile(ast.Module(body=nodes,type_ignores=[]), '<original-export>', 'exec'), scope)
                with ZipFile(job['zip_path']) as archive:
                    self.assertEqual(expected, {n: archive.read(n) for n in archive.namelist()})

    def test_config_and_token_validation(self):
        for kw in ({'expected_speakers':-1},{'min_speakers':3,'max_speakers':2},{'language':'xx'}):
            with self.assertRaises(ValueError): Config(**kw)
        with self.assertRaisesRegex(RuntimeError,'HF_TOKEN'):
            process('missing.wav','unused','unused', Config(), stage='full')
        self.assertEqual(safe_name('../bad:name'), '_bad_name')

    def test_processor_off_with_inference_doubles(self):
        # Only orchestration, no inference claims. OFF passes no token and emits no diar files.
        def asr(job, config, cache, metrics):
            job['asr_segments'] = [{'start':0.,'end':1.,'text':'架空発言','words':[]}]
            (job['outdir']/'whisper_asr.json').write_text(json.dumps(job['asr_segments']))
            return {'model':'large-v3'}
        def diar(job, config, token, metrics):
            self.assertFalse(config.enable_diarization); self.assertIsNone(token)
            job['diar_segments'] = []
            return {}
        with tempfile.TemporaryDirectory() as folder, patch('transcriber.asr.transcribe', asr), patch('transcriber.diarization.diarize', diar):
            path = Path(folder)/'audio.wav';path.write_bytes(b'fixture')
            archive, metrics = process(path, Path(folder)/'results', Path(folder)/'models', Config(enable_diarization=False))
            with ZipFile(archive) as z:
                self.assertFalse(any('pyannote' in n for n in z.namelist()))
                report=json.loads(z.read('処理レポート.json'))
                self.assertFalse(report['diarization_enabled'])
                self.assertEqual(report['utterances'],1)



class AsrCacheTests(unittest.TestCase):
    def test_result_cache_reuse_and_invalidation(self):
        from types import SimpleNamespace
        from transcriber.asr import transcribe
        from unittest.mock import MagicMock
        calls = []
        class Model:
            def __init__(self, *args, **kwargs):
                calls.append(kwargs)
            def transcribe(self, *args, **kwargs):
                self.kwargs = kwargs
                self.assert_settings = None
                segment = SimpleNamespace(start=0., end=1., text='架空発言', words=[SimpleNamespace(start=0.,end=1.,word='発言')])
                return iter([segment]), SimpleNamespace(duration=1.)
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:True,empty_cache=lambda:None))
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'torch':torch,'av':MagicMock(),'faster_whisper':SimpleNamespace(WhisperModel=Model)}):
            out = Path(folder)
            job = {'path':out/'audio.wav','outdir':out,'sha256':'first'}
            config = Config(enable_diarization=False)
            m = {};transcribe(job,config,out/'models',m)
            self.assertFalse(m['asr_result_cache_hit'])
            self.assertEqual(calls[0]['device'],'cuda')
            self.assertEqual(calls[0]['compute_type'],'float16')
            m = {};transcribe(job,config,out/'models',m)
            self.assertTrue(m['asr_result_cache_hit']);self.assertEqual(len(calls),1)
            transcribe(job,Config(enable_diarization=False,glossary='専門用語'),out/'models',{})
            self.assertEqual(len(calls),2)
            job['sha256']='second';transcribe(job,config,out/'models',{})
            self.assertEqual(len(calls),3)
            (out/'whisper_asr.json').write_text('{corrupt')
            transcribe(job,config,out/'models',{})
            self.assertEqual(len(calls),4)

if __name__ == '__main__': unittest.main()
