"""Regression for observed Modal reload failure while another request reads results."""
import asyncio
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import httpx
from beta.backend import FileBackend
from beta.server import create_app
from fastapi.responses import FileResponse

class VolumeConcurrencyTests(unittest.TestCase):
    def test_parallel_result_and_export_reads_never_overlap_volume_operations(self):
        async def scenario(root):
            backend=FileBackend(root,{},probe=lambda _:4,require_owner=True)
            app=create_app(backend,session_secret='volume-regression-secret-1234567890abcdef',anonymous=True)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='https://test.local') as client:
                await client.get('/')
                csrf=(await client.get('/api/session')).json()['csrf']
                h={'X-CSRF':csrf}
                job=(await client.post('/api/jobs',headers=h,json={'filename':'fixture.wav','size':4,'diarization':False,'speakers':0})).json()['id']
                await client.put(f'/api/jobs/{job}/chunks?offset=0',headers=h,content=b'wave')
                await client.post(f'/api/jobs/{job}/finish',headers=h)
                backend.state['job:'+job]={**backend.state['job:'+job],'status':'complete'}
                (Path(root)/job/'results.json').write_text(json.dumps([{'start':0,'end':1,'speaker':'test','text':'fixture'}]))
                # Model Volume's process-wide rule: reload fails while another read holds a file.
                original=backend.read_rows
                reading=threading.Event()
                def guarded(*args,**kwargs):
                    if reading.is_set(): raise RuntimeError('there are open files preventing the operation')
                    reading.set()
                    try:
                        time.sleep(.025)
                        return original(*args,**kwargs)
                    finally: reading.clear()
                backend.read_rows=guarded
                responses=await asyncio.gather(*(client.get(f'/api/jobs/{job}'+('/rows' if i%2 else '/download')) for i in range(12)))
                self.assertTrue(all(r.status_code==200 for r in responses))
        with tempfile.TemporaryDirectory() as root: asyncio.run(scenario(root))

    def test_audio_stream_uses_cleaned_local_snapshot_and_preserves_range(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as root:
            backend=FileBackend(root,{},probe=lambda _:4,require_owner=True)
            app=create_app(backend,session_secret='volume-regression-secret-1234567890abcdef',anonymous=True)
            with TestClient(app,base_url='https://test.local') as c:
                c.get('/');h={'X-CSRF':c.get('/api/session').json()['csrf']}
                job=c.post('/api/jobs',headers=h,json={'filename':'fixture.wav','size':4,'diarization':False,'speakers':0}).json()['id']
                c.put(f'/api/jobs/{job}/chunks?offset=0',headers=h,content=b'wave')
                c.post(f'/api/jobs/{job}/finish',headers=h)
                captured=[]
                def response(path,**kwargs):
                    captured.append(Path(path))
                    self.assertNotIn(Path(root),Path(path).parents)
                    self.assertEqual(Path(path).read_bytes(),b'wave')
                    return FileResponse(path,**kwargs)
                with patch('beta.server.FileResponse',side_effect=response):
                    r=c.get(f'/api/jobs/{job}/audio',headers={'Range':'bytes=1-2'})
                self.assertEqual(r.status_code,206)
                self.assertEqual(r.content,b'av')
                self.assertFalse(captured[0].parent.exists(),'Request-local audio snapshot must be removed')
                self.assertTrue((Path(root)/job/'source.wav').is_file())
