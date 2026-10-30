"""Stage v0.1-7: model-estimated overlap review must never rewrite ASR or diarization."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from beta.backend import FileBackend
from beta.review import review_candidates_from_archive
from beta.server import create_app
from transcriber.processor import Config


def archive_for(candidates=None):
    stream=io.BytesIO()
    with ZipFile(stream,'w') as z:
        if candidates is not None:
            z.writestr('pyannote_重複発話確認候補.json',
                       json.dumps({'segments':candidates},ensure_ascii=False))
    return stream.getvalue()


class OverlapReviewUnitTests(unittest.TestCase):
    def test_opt_in_does_not_change_default_model_config(self):
        self.assertFalse(Config().overlap_review)
        self.assertFalse(Config().quality_experiment)
        self.assertTrue(Config(enable_diarization=True,overlap_review=True).overlap_review)
        with self.assertRaises(ValueError):
            Config(enable_diarization=False,overlap_review=True)

    def test_validates_and_sanitizes_model_overlap(self):
        z=archive_for([
            {'start':3.0,'end':4.0,'speaker_ids':['raw01','raw02']},
            {'start':0.1,'end':0.4,'speaker_ids':['s1','s2']},
            {'start':1.0,'end':1.1,'speaker_ids':['s1','s2']}])
        result=review_candidates_from_archive(z,10.0)
        self.assertTrue(result['available'])
        self.assertEqual(result['total_candidates'],2)
        self.assertEqual([w['start'] for w in result['windows']],[0.1,3.0])
        self.assertEqual([w['id'] for w in result['windows']],['ov-00000','ov-00001'])
        self.assertNotIn('raw01',json.dumps(result))
        self.assertFalse(review_candidates_from_archive(archive_for(),10.0)['available'])
        with self.assertRaises(ValueError):
            review_candidates_from_archive(archive_for([{'start':0,'end':1,'speaker_ids':['single']}]),10.0)
        with self.assertRaises(ValueError):
            review_candidates_from_archive(archive_for([{'start':0,'end':11,'speaker_ids':['a','b']}]),10.0)


class OverlapReviewWebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.state={}
        self.backend=FileBackend(self.temp.name,self.state,launch=lambda *args:None,probe=lambda p:12)
        self.app=create_app(self.backend,password='a-very-strong-test-password-123',
                            session_secret='test-secret-very-long-abcdefghijklmnopqrstuvwxyz')
        self.client=TestClient(self.app,base_url='https://example.org')
        self.client.post('/login',data={'password':'a-very-strong-test-password-123'})
        self.csrf=self.client.get('/api/session').json()['csrf']
        headers={'X-CSRF':self.csrf}
        r=self.client.post('/api/jobs',headers=headers,
                           json={'filename':'public.wav','size':3,'diarization':True,'speakers':2})
        self.assertEqual(r.status_code,200,r.text)
        self.id=r.json()['id']
        self.client.put('/api/jobs/'+self.id+'/chunks?offset=0',content=b'abc',headers=headers)
        self.client.post('/api/jobs/'+self.id+'/finish',headers=headers)
        state=self.state['job:'+self.id]
        state['status']='complete'
        self.state['job:'+self.id]=state
        self.folder=Path(self.temp.name)/self.id
        self.rows=[{'start':1,'end':2,'speaker':'話者1','text':'はい'}]
        (self.folder/'results.json').write_text(json.dumps(self.rows,ensure_ascii=False))
        review=review_candidates_from_archive(archive_for([
            {'start':1.1,'end':1.6,'speaker_ids':['s1','s2']},
            {'start':6.1,'end':6.7,'speaker_ids':['s1','s2']}]),12.0)
        (self.folder/'review_candidates.json').write_text(json.dumps(review,ensure_ascii=False))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_review_restricted_to_auth_and_csrf(self):
        url='/api/jobs/'+self.id+'/review'
        self.assertEqual(self.client.get(url).status_code,200)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(url).status_code,401)
        self.client.post('/login',data={'password':'a-very-strong-test-password-123'})
        self.assertEqual(self.client.put(url+'/ov-00000',json={'reviewed':True}).status_code,403)

    def test_review_persists_and_never_modifies_transcript(self):
        url='/api/jobs/'+self.id+'/review'
        initial=self.client.get(url).json()
        self.assertEqual(len(initial['windows']),2)
        headers={'X-CSRF':self.csrf}
        self.assertEqual(self.client.put(url+'/ov-99999',headers=headers,json={'reviewed':True}).status_code,404)
        self.assertEqual(self.client.put(url+'/ov-00000',headers=headers,json={'reviewed':'yes'}).status_code,400)
        self.assertEqual(self.client.put(url+'/ov-00000',headers=headers,json={'reviewed':True}).status_code,200)
        self.assertEqual(self.client.get(url).json()['reviewed_ids'],['ov-00000'])
        backend2=FileBackend(self.temp.name,self.state,probe=lambda p:12)
        self.assertEqual(backend2.review_windows(self.id)['reviewed_ids'],['ov-00000'])
        self.assertEqual(self.client.get('/api/jobs/'+self.id+'/rows').json()['rows'],self.rows)
        self.assertNotIn(b'review_checked.json',self.client.get('/api/jobs/'+self.id+'/download').content)
        self.assertEqual(self.client.put(url+'/ov-00000',headers=headers,json={'reviewed':False}).status_code,200)
        self.assertEqual(self.client.get(url).json()['reviewed_ids'],[])
        self.assertEqual(self.client.delete('/api/jobs/'+self.id,headers=headers).status_code,200)
        self.assertEqual(self.client.get(url).status_code,404)

    def test_old_job_without_review_has_safe_empty_response(self):
        (self.folder/'review_candidates.json').unlink()
        r=self.client.get('/api/jobs/'+self.id+'/review')
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['available'])
        self.assertEqual(r.json()['windows'],[])


if __name__=='__main__':
    unittest.main()
