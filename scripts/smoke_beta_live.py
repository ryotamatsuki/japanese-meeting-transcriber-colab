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
    path=Path(os.environ.get('BETA_SMOKE_AUDIO_PATH','local_audio/kyoto_two_speakers.ogg'))
    min_duration=float(os.environ.get('BETA_SMOKE_MIN_DURATION_SECONDS','0'))
    max_polls=int(os.environ.get('BETA_SMOKE_MAX_POLLS','140'))
    expect(0 <= min_duration <= 3600 and 10 <= max_polls <= 600, 'Invalid test limits')
    expect(url.startswith('https://') and url.endswith('.modal.run'),'Invalid isolated HTTPS URL')
    expect(path.is_file(),'Missing public test recording')
    started=time.monotonic()
    diar=os.environ.get('BETA_SMOKE_DIARIZATION','0')=='1'
    results={'diarization_enabled':diar, 'long_form':min_duration>0, 'audio_size_bytes':path.stat().st_size}
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
        for _ in range(max_polls):
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
        job_result=r.json()
        results['audio_duration_seconds']=job_result.get('duration')
        results['gpu_pipeline_seconds']=job_result.get('pipeline_seconds')
        if min_duration:
            expect(float(job_result.get('duration') or 0)>=min_duration,'Incorrect uploaded audio duration')
            expect(float(job_result.get('pipeline_seconds') or 10**6)<1800,'GPU pipeline exceeds 30 min')

        r=client.get(f'/api/jobs/{job}/rows')
        expect(r.status_code==200,'Completed transcript not readable')
        rows=r.json()['rows']
        expect(rows and all('start' in row and 'speaker' in row for row in rows),'Missing utterances')
        results['utterance_count']=len(rows)
        results['last_utterance_end_seconds']=round(max(float(x['end']) for x in rows),3)
        if min_duration:
            expect(results['last_utterance_end_seconds']>=min_duration-60,'Last minute missing from final transcript')
        if diar:
            observed={row['speaker'] for row in rows if row['speaker'] not in ('話者未設定','話者不明')}
            expect(len(observed)==2, 'Diarization-on did not produce two speaker labels')
            results['detected_speakers']=len(observed)
        if diar:
            review_response=client.get(f'/api/jobs/{job}/review')
            expect(review_response.status_code==200, 'Overlap review endpoint failed')
            review=review_response.json()
            expect(review['available'], 'New diarization job did not produce overlap review estimates')
            count=len(review['windows'])
            results['overlap_review_candidates']=count
            results['overlap_review_total']=review['total_candidates']
            if os.environ.get('BETA_REQUIRE_OVERLAP_CANDIDATES','0')=='1':
                expect(count>0,'Known-overlapping two-speaker audio yielded no review windows')
            if count:
                first=review['windows'][0]
                expect(first['speaker_count']>=2 and first['start']<first['end'], 'Malformed overlap candidate')
                put=client.put(f"/api/jobs/{job}/review/{first['id']}",
                               headers=headers,json={'reviewed':True})
                expect(put.status_code==200,'Could not mark overlap candidate reviewed')
                again=client.get(f'/api/jobs/{job}/review').json()
                expect(first['id'] in again['reviewed_ids'], 'Review status did not persist')
                put=client.put(f"/api/jobs/{job}/review/{first['id']}",
                               headers=headers,json={'reviewed':False})
                expect(put.status_code==200,'Could not undo overlap review check')
                results['overlap_review_mark_and_reopen']=True
            eaf=os.environ.get('BETA_SMOKE_REF_EAF')
            if eaf:
                from scripts.evaluate_overlap_review import metrics
                ground=metrics(Path(eaf),review)
                results['overlap_ground_truth_metrics']=ground
        results['gpu_job_completed']=True
        r=client.get(f'/api/jobs/{job}/audio',headers={'Range':'bytes=0-1023'})
        expect(r.status_code in (200,206),'Audio playback fetch failed')
        expect(r.content[:4]==content[:4],'Audio data integrity mismatch')
        results['audio_access']=True
        rows[0]['text']='テスト用の修正済み発話。'
        r=client.put(f'/api/jobs/{job}/rows',headers=headers,json={'rows':rows})
        if r.status_code != 200:
            # Store numeric diagnostics only, never source speech/transcripts.
            import math
            duration=float(job_result.get('duration') or 0)
            invalid_time=sum(
                not (0<=float(x['start'])<float(x['end'])<=duration+0.5)
                for x in rows)
            invalid_field=sum(
                not isinstance(x.get('text'),str) or not isinstance(x.get('speaker'),str)
                or len(str(x.get('text','')))>6000 or len(str(x.get('speaker','')))>80
                for x in rows)
            diagnostic={'status_code':r.status_code,'row_count':len(rows),
                        'json_payload_bytes':len(json.dumps({'rows':rows},ensure_ascii=False).encode()),
                        'invalid_timestamp_rows':invalid_time,
                        'invalid_text_or_speaker_rows':invalid_field,
                        'max_end_seconds':max(float(x['end']) for x in rows),
                        'audio_duration_seconds':duration}
            results['save_failure_diagnostics']=diagnostic
            Path('local_runs').mkdir(exist_ok=True)
            Path('local_runs/smoke_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
            print('SANITIZED_LONG_FORM_SAVE_FAILURE',json.dumps(diagnostic,sort_keys=True),flush=True)
        expect(r.status_code==200,'Failed to save corrected text (status='+str(r.status_code)+')')
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
    if min_duration:
        expect(results['elapsed_seconds'] < 1800,'End-to-end processing exceeds 30 minutes')
    Path('local_runs').mkdir(exist_ok=True)
    Path('local_runs/smoke_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print('ISOLATED_PRIVATE_BETA_E2E_PASS',json.dumps(results,sort_keys=True))

if __name__=='__main__':
    main()
