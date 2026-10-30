"""Isolated Modal beta live HTTP smoke. Public CC-BY test audio only.

Requires BETA_SMOKE_URL, BETA_SMOKE_PASSWORD env vars; never prints them.
Runs API authentication, static assets, chunked upload, GPU ASR, edits and deletion.
"""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import sys
import time
from zipfile import ZipFile
import httpx

def expect(condition, label):
    if not condition:
        raise AssertionError(label)

def main():
    url=os.environ['BETA_SMOKE_URL'].strip()
    pwd=os.environ['BETA_SMOKE_PASSWORD']
    path=Path('local_audio/kyoto_two_speakers.ogg')
    expect(url.startswith('https://') and url.endswith('.modal.run'),'Invalid isolated HTTPS URL')
    expect(path.is_file(),'Missing public test recording')
    started=time.monotonic()
    diar=os.environ.get('BETA_SMOKE_DIARIZATION','0')=='1'
    results={'diarization_enabled':diar}
    with httpx.Client(base_url=url,timeout=90.0,follow_redirects=False) as client:
        r=client.get('/api/jobs')
        expect(r.status_code==401,'Unauthenticated API must be denied')
        results['unauthenticated_denied']=True
        r=client.post('/login',data={'password':pwd})
        expect(r.status_code==303,'Private login unsuccessful')
        s=client.get('/api/session')
        expect(s.status_code==200,'Session unavailable')
        csrf=s.json()['csrf']
        headers={'X-CSRF':csrf}
        for name in ('site.css','site.js'):
            r=client.get('/assets/'+name)
            expect(r.status_code==200 and len(r.content)>100,'Missing web static '+name)
        r=client.get('/')
        expect(r.status_code==200 and b'<html' in r.content,'Web HTML missing')
        results['static_assets_and_auth']=True
        r=client.post('/api/jobs',json={'filename':path.name,'size':path.stat().st_size,'diarization':diar,'speakers':2})
        expect(r.status_code==403,'Missing CSRF was allowed')
        r=client.post('/api/jobs',headers=headers,json={'filename':path.name,'size':path.stat().st_size,'diarization':diar,'speakers':2})
        expect(r.status_code==200,'Failed to create job: '+str(r.status_code))
        job=r.json()['id']
        content=path.read_bytes()
        for pos in range(0,len(content),4*1024*1024):
            r=client.put(f'/api/jobs/{job}/chunks?offset={pos}',content=content[pos:pos+4*1024*1024],headers=headers)
            expect(r.status_code==200,'Failed chunk upload')
        r=client.post(f'/api/jobs/{job}/finish',headers=headers)
        expect(r.status_code==200,'Failed to enqueue GPU work: '+str(r.status_code))
        expect(r.json()['status'] in ('queued','running','complete'),'Unexpected state after launch')
        results['upload_and_queue']=True
        last=''
        for _ in range(140):
            r=client.get('/api/jobs/'+job)
            expect(r.status_code==200,'Job status inaccessible')
            status=r.json()['status']
            if status in ('complete','failed'):
                break
            if status!=last:
                print('state_changed_to',status,flush=True)
                last=status
            time.sleep(4)
        else:
            raise AssertionError('GPU inference timed out in smoke')
        expect(status=='complete','GPU job did not complete (status='+status+')')
        r=client.get(f'/api/jobs/{job}/rows')
        expect(r.status_code==200,'Completed transcript not readable')
        rows=r.json()['rows']
        expect(rows and all('start' in row and 'speaker' in row for row in rows),'Missing utterances')
        results['utterance_count']=len(rows)
        if diar:
            observed={row['speaker'] for row in rows if row['speaker'] not in ('話者未設定','話者不明')}
            expect(len(observed)==2, 'Diarization-on did not produce two speaker labels')
            results['detected_speakers']=len(observed)
        results['gpu_job_completed']=True
        r=client.get(f'/api/jobs/{job}/audio',headers={'Range':'bytes=0-1023'})
        expect(r.status_code in (200,206),'Audio playback fetch failed')
        expect(r.content[:4]==content[:4],'Audio data integrity mismatch')
        results['audio_access']=True
        rows[0]['text']='テスト用の修正済み発話。'
        r=client.put(f'/api/jobs/{job}/rows',headers=headers,json={'rows':rows})
        expect(r.status_code==200,'Failed to save corrected text')
        r=client.get(f'/api/jobs/{job}/download')
        expect(r.status_code==200,'Failed export')
        with ZipFile(io.BytesIO(r.content)) as z:
            expect(z.testzip() is None,'Export corrupted ZIP')
            expect(len(z.namelist())==4,'Missing output formats')
            expect('テスト用の修正済み発話。' in z.read('文字起こし.txt').decode('utf-8'),
                   'Corrected content not exported')
        results['edited_zip_exported']=True
        r=client.delete(f'/api/jobs/{job}',headers=headers)
        expect(r.status_code==200,'Failed deletion')
        expect(client.get(f'/api/jobs/{job}').status_code==404,'Deleted job still accessible')
        results['deleted']=True
    results['elapsed_seconds']=round(time.monotonic()-started,2)
    Path('local_runs').mkdir(exist_ok=True)
    Path('local_runs/smoke_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print('ISOLATED_PRIVATE_BETA_E2E_PASS',json.dumps(results,sort_keys=True))

if __name__=='__main__':
    main()
