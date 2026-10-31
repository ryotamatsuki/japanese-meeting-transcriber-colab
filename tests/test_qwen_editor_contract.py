"""Stage11 editor-contract test: Qwen time-aligned records use unchanged private beta APIs.

Uses only a synthetic hand-authored Qwen-shaped fixture: no model download and
no real recordings.
"""
import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from beta.backend import FileBackend
from beta.server import create_app
from scripts.qwen_timing_bridge import attribute_qwen


class QwenWebEditorContractTests(unittest.TestCase):
    def test_import_edit_download_and_delete_qwen_timed_utterances(self):
        chunks=[{'offset_sec':0.0,'duration_sec':2.0,'text':'おはようございます。',
                 'items':[{'text':'おはよう','start_time':0.1,'end_time':0.8},
                          {'text':'ございます','start_time':0.8,'end_time':1.7}]},
                {'offset_sec':2.0,'duration_sec':2.0,'text':'はい、承知しました。',
                 'items':[{'text':'はい','start_time':0.1,'end_time':0.5},
                          {'text':'承知','start_time':0.5,'end_time':1.0},
                          {'text':'しました','start_time':1.0,'end_time':1.9}]}]
        diar=[{'start':0,'end':2,'speaker_id':'A'},
              {'start':2,'end':4,'speaker_id':'B'}]
        utterances,details=attribute_qwen(chunks,diar,4.0)
        self.assertEqual(details['speaker_count'],2)
        with tempfile.TemporaryDirectory() as path:
            state={}
            backend=FileBackend(path,state,launch=lambda *args:None,probe=lambda p:4.0)
            app=create_app(backend,password='long-test-password-123456',
                           session_secret='temporary-secret-0123456789abcdefghijklmnopqrstuvwxyz')
            with TestClient(app,base_url='https://example.org') as client:
                response=client.post('/login',data={'password':'long-test-password-123456'})
                self.assertEqual(response.status_code,200)
                csrf=client.get('/api/session').json()['csrf']
                headers={'X-CSRF':csrf}
                response=client.post('/api/jobs',headers=headers,json={
                    'filename':'synthetic.wav','size':3,'diarization':True,'speakers':2})
                self.assertEqual(response.status_code,200,response.text)
                id=response.json()['id']
                client.put(f'/api/jobs/{id}/chunks?offset=0',headers=headers,content=b'abc')
                client.post(f'/api/jobs/{id}/finish',headers=headers)
                state['job:'+id]={**state['job:'+id],'status':'complete'}
                (Path(path)/id/'results.json').write_text(json.dumps(utterances,ensure_ascii=False))
                rows=client.get(f'/api/jobs/{id}/rows').json()['rows']
                self.assertEqual(len(rows),len(utterances))
                rows[0]['text']='議事録を修正しました。'
                self.assertEqual(client.put(f'/api/jobs/{id}/rows',headers=headers,
                                            json={'rows':rows}).status_code,200)
                result=client.get(f'/api/jobs/{id}/download')
                self.assertEqual(result.status_code,200)
                self.assertTrue(result.content.startswith(b'PK'))
                self.assertEqual(client.delete(f'/api/jobs/{id}',headers=headers).status_code,200)


if __name__=='__main__':
    unittest.main()
