import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from beta.backend import FileBackend
from beta.server import create_app

class BetaWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.jobs={}
        self.backend=FileBackend(self.tmp.name, self.jobs, launch=lambda *args: None,probe=lambda p:12)
        self.client=TestClient(create_app(self.backend,password='correct-horse-battery-staple',session_secret='my-secret-very-long-for-hmac-and-session-2026'),base_url='https://example.org')
    def tearDown(self):
        self.client.close();self.tmp.cleanup()
    def auth(self):
        x=self.client.post('/login',data={'password':'correct-horse-battery-staple'},follow_redirects=False)
        self.assertEqual(x.status_code,303)
        return self.client.get('/api/session').json()['csrf']
    def test_security(self):
        self.assertEqual(self.client.get('/',follow_redirects=False).status_code,303)
        self.assertEqual(self.client.get('/api/jobs').status_code,401)
        self.assertEqual(self.client.post('/login',data={'password':'wrong'}).status_code,401)
        self.assertEqual(self.client.get('/api/session').status_code,401)
        csrf=self.auth()
        self.assertEqual(self.client.post('/api/jobs',json={'filename':'a.wav','size':10}).status_code,403)
        self.assertEqual(self.client.get('/api/jobs').status_code,200)
        self.assertEqual(self.client.post('/api/jobs',headers={'X-CSRF':csrf,'Origin':'https://attack.example'},json={'filename':'a.wav','size':10}).status_code,403)
        self.assertEqual(self.client.get('/api/jobs/not-a-uuid').status_code,404)
    def test_upload_edit_download_delete(self):
        csrf=self.auth();h={'X-CSRF':csrf}
        r=self.client.post('/api/jobs',json={'filename':'public.wav','size':6,'diarization':True,'speakers':2},headers=h)
        self.assertEqual(r.status_code,200,r.text)
        id=r.json()['id']
        self.assertEqual(self.client.put('/api/jobs/'+id+'/chunks?offset=1',content=b'abcdef',headers=h).status_code,409)
        self.assertEqual(self.client.put('/api/jobs/'+id+'/chunks?offset=0',content=b'abcdef',headers=h).status_code,200)
        r=self.client.post('/api/jobs/'+id+'/finish',headers=h)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['status'],'queued')
        self.assertEqual(self.client.get('/api/jobs/'+id+'/audio').content,b'abcdef')
        self.assertEqual(self.client.get('/api/jobs/'+id+'/rows').status_code,409)
        j=self.jobs['job:'+id];j['status']='complete';self.jobs['job:'+id]=j
        folder=Path(self.tmp.name)/id
        (folder/'results.json').write_text(json.dumps([{'start':0,'end':1,'speaker':'話者1','text':'こんにちは'}]))
        self.assertEqual(self.client.get('/api/jobs/'+id+'/rows').json()['rows'][0]['text'],'こんにちは')
        r=self.client.put('/api/jobs/'+id+'/rows',headers=h,json={'rows':[{'start':0,'end':1,'speaker':'話者A','text':'確認します。'}]})
        self.assertEqual(r.status_code,200,r.text)
        self.assertIn(b'PK\x03\x04',self.client.get('/api/jobs/'+id+'/download').content)
        self.assertEqual(self.client.delete('/api/jobs/'+id,headers=h).status_code,200)
        self.assertEqual(self.client.get('/api/jobs/'+id).status_code,404)
    def test_size_and_quota(self):
        h={'X-CSRF':self.auth()}
        self.assertEqual(self.client.post('/api/jobs',headers=h,json={'filename':'a.wav','size':200*1024*1024}).status_code,400)
        self.assertEqual(self.client.post('/api/jobs',headers=h,json={'filename':'e.exe','size':10}).status_code,400)
        r=self.client.post('/api/jobs',headers=h,json={'filename':'a.wav','size':3});self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.post('/api/jobs',headers=h,json={'filename':'b.wav','size':3}).status_code,429)
    def test_daily_gpu_quota_survives_job_deletion(self):
        headers={'X-CSRF':self.auth()}
        for count in range(4):
            r=self.client.post('/api/jobs',headers=headers,json={'filename':'public.mp3','size':1})
            self.assertEqual(r.status_code,200,r.text)
            id=r.json()['id']
            self.assertEqual(self.client.put('/api/jobs/'+id+'/chunks?offset=0',headers=headers,content=b'x').status_code,200)
            self.assertEqual(self.client.post('/api/jobs/'+id+'/finish',headers=headers).status_code,200)
            state=self.jobs['job:'+id]
            state['status']='complete'
            self.jobs['job:'+id]=state
            self.assertEqual(self.client.delete('/api/jobs/'+id,headers=headers).status_code,200)
        r=self.client.post('/api/jobs',headers=headers,json={'filename':'fifth.mp3','size':1})
        self.assertEqual(r.status_code,200,r.text)
        id=r.json()['id']
        self.client.put('/api/jobs/'+id+'/chunks?offset=0',headers=headers,content=b'x')
        self.assertEqual(self.client.post('/api/jobs/'+id+'/finish',headers=headers).status_code,429)

    def test_login_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.client.post('/login',data={'password':'bad'}).status_code,401)
        self.assertEqual(self.client.post('/login',data={'password':'bad'}).status_code,429)
        self.assertEqual(self.client.get('/api/jobs').status_code,401)

if __name__=='__main__': unittest.main()