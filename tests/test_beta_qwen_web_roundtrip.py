"""Qwen3 research output compatibility with beta API, and safe physical deletion."""
import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from beta.backend import FileBackend, StoreError
from beta.core import normalize_edits
from beta.server import create_app
from scripts.qwen_timing_bridge import attribute_qwen


def sample_rows():
    chunks=[{'offset_sec':0,'duration_sec':3,'text':'こんにちは。はい',
      'items':[{'text':'こんにちは','start_time':0.1,'end_time':1.0},
               {'text':'はい','start_time':2.0,'end_time':2.7}]},
      {'offset_sec':3,'duration_sec':3,'text':'ありがとうございます。',
       'items':[{'text':'ありがとう','start_time':0.2,'end_time':1.8},
                {'text':'ございます','start_time':1.8,'end_time':2.8}]}]
    diar=[{'start':0,'end':3,'speaker_id':'A'},
          {'start':3,'end':6,'speaker_id':'B'}]
    return attribute_qwen(chunks,diar,6)


class QwenWebRoundtrip(unittest.TestCase):
    def state_for(self,jid):
        return {'job_index':[jid],'job:'+jid:{
            'id':jid,'status':'complete','created':time.time(),
            'duration':6.0,'filename':'public.mp3'}}

    def test_qwen_web_edit_export_reload_delete(self):
        rows,quality=sample_rows()
        self.assertTrue(quality['all_normalized_text_preserved'])
        self.assertEqual(quality['speaker_count'],2)
        with tempfile.TemporaryDirectory() as tmp:
            jid='1'*32
            folder=Path(tmp)/jid
            folder.mkdir()
            (folder/'results.json').write_text(json.dumps(rows,ensure_ascii=False))
            backend=FileBackend(tmp,self.state_for(jid))
            app=create_app(backend,password='test-password-strong-16',
                           session_secret='integration-test-signed-key-keep-private-42')
            with TestClient(app,base_url='https://example.org') as client:
                self.assertEqual(client.post('/login',
                   data={'password':'test-password-strong-16'},
                   follow_redirects=False).status_code,303)
                csrf=client.get('/api/session').json()['csrf']
                got=client.get('/api/jobs/'+jid+'/rows').json()['rows']
                self.assertEqual(got,rows)
                revised=[dict(row) for row in got]
                revised[0]['speaker']='参加者A'
                revised[0]['text']='こんにちは。修正しました。'
                resp=client.put('/api/jobs/'+jid+'/rows',
                    headers={'X-CSRF':csrf},json={'rows':revised})
                self.assertEqual(resp.status_code,200,resp.text[:200])
                self.assertEqual(client.get('/api/jobs/'+jid+'/rows').json()['rows'],revised)
                archive=client.get('/api/jobs/'+jid+'/download')
                self.assertEqual(archive.status_code,200)
                with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
                    self.assertEqual(len(z.namelist()),4)
                    self.assertEqual(json.loads(z.read('文字起こし.json'))['utterances'],revised)
                    self.assertIn('参加者A: こんにちは。修正しました。',
                        z.read('文字起こし.srt').decode('utf-8'))
                self.assertEqual(client.delete('/api/jobs/'+jid,
                    headers={'X-CSRF':csrf}).status_code,200)
                self.assertFalse(folder.exists())

    def test_tiny_positive_span_survives_millisecond_save(self):
        source=[{'start':2.00001,'end':2.00009,'speaker':'話者1','text':'はい'}]
        norm=normalize_edits(source,6)
        self.assertEqual(norm[0]['start'],2.0)
        self.assertEqual(norm[0]['end'],2.001)
        with self.assertRaises(ValueError):
            normalize_edits([{**source[0],'start':2.0,'end':2.0}],6)
        with self.assertRaises(ValueError):
            normalize_edits([{**source[0],'start':2.1,'end':2.0}],6)

    def test_storage_error_keeps_job_visible_and_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            jid='2'*32
            folder=Path(tmp)/jid
            folder.mkdir()
            (folder/'source.mp3').write_bytes(b'dummy')
            state=self.state_for(jid)
            backend=FileBackend(tmp,state)
            with patch('beta.backend.shutil.rmtree',side_effect=OSError('simulated disk failure')):
                with self.assertRaises(StoreError) as exc:
                    backend.delete(jid)
            self.assertEqual(exc.exception.code,500)
            self.assertTrue(folder.exists())
            self.assertEqual(state['job:'+jid]['status'],'complete')
            backend.delete(jid)
            self.assertFalse(folder.exists())
            self.assertEqual(state['job:'+jid]['status'],'deleted')

    def test_no_delete_during_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            jid='3'*32
            folder=Path(tmp)/jid
            folder.mkdir()
            state=self.state_for(jid)
            state['job:'+jid]['status']='running'
            backend=FileBackend(tmp,state)
            with self.assertRaises(StoreError) as exc:backend.delete(jid)
            self.assertEqual(exc.exception.code,409)
            self.assertTrue(folder.exists())


if __name__=='__main__':
    unittest.main()
