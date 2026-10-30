"""Protect full-hour editing/export against legitimate large transcript payloads."""
import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from beta.backend import FileBackend
from beta.server import create_app


class LongBatchEditTests(unittest.TestCase):
    def test_1200_utterance_60min_edit_export(self):
        with tempfile.TemporaryDirectory() as folder:
            memory={}
            backend=FileBackend(folder,memory,launch=lambda *args:None,probe=lambda p:3595.0)
            app=create_app(backend,password='test-password-strong-16',
                           session_secret='integration-test-signed-key-keep-private-42')
            with TestClient(app,base_url='https://example.org') as client:
                login=client.post('/login',data={'password':'test-password-strong-16'},follow_redirects=False)
                self.assertEqual(login.status_code,303)
                headers={'X-CSRF':client.get('/api/session').json()['csrf']}
                r=client.post('/api/jobs',headers=headers,json={
                    'filename':'public-60min.mp3','size':1,'diarization':True,'speakers':2})
                self.assertEqual(r.status_code,200,r.text)
                id=r.json()['id']
                self.assertEqual(client.put('/api/jobs/'+id+'/chunks?offset=0',
                                            headers=headers,content=b'a').status_code,200)
                self.assertEqual(client.post('/api/jobs/'+id+'/finish',headers=headers).status_code,200)
                state=memory['job:'+id];state['status']='complete';memory['job:'+id]=state
                records=[{'start':round(i*2.95,3),'end':round(i*2.95+2.3,3),
                          'speaker':('話者1' if i%2 else '話者2'),
                          'text':'日本語の会議音声の長い文字起こしを修正します。'} for i in range(1200)]
                records[-1]['end']=3540.0
                (Path(folder)/id/'results.json').write_text(json.dumps(records,ensure_ascii=False))
                response=client.put('/api/jobs/'+id+'/rows',headers=headers,json={'rows':records})
                self.assertEqual(response.status_code,200,response.text[:100])
                self.assertEqual(len(client.get('/api/jobs/'+id+'/rows').json()['rows']),1200)
                downloaded=client.get('/api/jobs/'+id+'/download')
                self.assertEqual(downloaded.status_code,200)
                self.assertTrue(downloaded.content.startswith(b'PK'))
                self.assertEqual(client.delete('/api/jobs/'+id,headers=headers).status_code,200)

    def test_strict_rejects_zero_length_utterance(self):
        from beta.core import normalize_edits
        with self.assertRaises(ValueError):
            normalize_edits([{'start':2.0,'end':2.0,'speaker':'話者1','text':'はい'}],3600.0)


if __name__=='__main__':
    unittest.main()
