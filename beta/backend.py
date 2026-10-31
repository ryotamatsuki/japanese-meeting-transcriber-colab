"""Session-scoped beta store. Modal Volume + Dict are injected; tests use fakes.

All anonymous operations require an owner key derived from a signed session.
One web container and its async lock serialize index/quota changes for this
limited pilot; this is NOT a distributed transactional queue.
"""
from __future__ import annotations
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from .core import (MAX_AUDIO_BYTES, MAX_JOBS, MAX_SECONDS, JOB_TTL_SECONDS,
                   valid_job_id, validated_extension, normalize_edits, build_export)


class StoreError(Exception):
    def __init__(self, detail, code=400):
        super().__init__(detail)
        self.code = code


class FileBackend:
    def __init__(self, root, state, launch=None, commit=None, refresh=None, probe=None,
                 require_owner=False):
        self.require_owner=require_owner
        self.root=Path(root)
        self.state=state
        self.launch=launch
        self.commit=commit or (lambda:None)
        self.refresh=refresh or (lambda:None)
        self.probe=probe or probe_audio
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, id):
        if not valid_job_id(id):
            raise StoreError('Invalid job ID',404)
        return self.root/id

    def _check_owner(self, owner):
        if self.require_owner and (not isinstance(owner,str) or
                                   not re.fullmatch(r'[a-f0-9]{64}',owner)):
            raise StoreError('Not found',404)

    def info(self, id, *, owner=None):
        self._check_owner(owner)
        if not valid_job_id(id):
            raise StoreError('Not found',404)
        job=self.state.get('job:'+id)
        if not job or job.get('status')=='deleted':
            raise StoreError('Not found',404)
        if self.require_owner and not secrets.compare_digest(job.get('owner',''),owner):
            # Identical response for a nonexistent job and another owner's job.
            raise StoreError('Not found',404)
        if time.time()-job['created']>JOB_TTL_SECONDS:
            raise StoreError('Job has expired',410)
        return dict(job)

    def list_jobs(self, *, owner=None):
        self._check_owner(owner)
        valid=[]
        for id in self.state.get('job_index',[]):
            try:
                valid.append(self.info(id,owner=owner))
            except StoreError:
                continue
        return sorted(valid,key=lambda j:j['created'],reverse=True)

    def new_job(self, name, size, diarization=True, speakers=0, *, owner=None):
        self._check_owner(owner)
        suffix=validated_extension(name)
        if not isinstance(size,int) or type(size) is not int or not 0<size<=MAX_AUDIO_BYTES:
            raise StoreError('File must be 1 byte to 180 MiB')
        if type(diarization) is not bool or type(speakers) is not int or speakers not in (0,2,3,4):
            raise StoreError('Speaker setting must be auto, 2, 3, or 4')
        current=self.list_jobs(owner=owner)
        if self.require_owner:
            # Cap untrusted anonymous uploads *globally*, not just per cookie.
            # The server serializes this check and job creation under one lock.
            live=0
            for key in self.state.get('job_index',[]):
                entry=self.state.get('job:'+key)
                if (entry and entry.get('status')!='deleted' and
                        time.time()-entry['created']<JOB_TTL_SECONDS):
                    live+=1
            if live>=8:
                raise StoreError('Server is busy. Try again after another job finishes.',429)
        if len(current)>=MAX_JOBS:
            raise StoreError('Two saved jobs maximum; delete a job before uploading another',429)
        if any(j['status'] in ('uploading','queued','running') for j in current):
            raise StoreError('One active job at a time in beta',429)
        id=secrets.token_hex(16)
        self.refresh()
        folder=self._path(id)
        folder.mkdir(mode=0o700,parents=True)
        (folder/('source'+suffix)).touch(mode=0o600)
        self.commit()
        job={'id':id,'filename':Path(name).name[:120],'extension':suffix,
             'expected_size':size,'received':0,'status':'uploading','duration':None,
             'diarization':diarization,'speakers':speakers,'created':time.time()}
        if self.require_owner:
            job['owner']=owner
        self.state['job:'+id]=job
        # Keep the global index intact: an owner's filtered list cannot replace it.
        existing=list(self.state.get('job_index',[])) if self.require_owner else [j['id'] for j in current]
        self.state['job_index']=existing+[id]
        return job

    def append_chunk(self,id,offset,data,*,owner=None):
        from .core import CHUNK_BYTES
        job=self.info(id,owner=owner)
        if job['status']!='uploading':
            raise StoreError('Upload is not active',409)
        if type(offset) is not int or offset<0 or not data or len(data)>CHUNK_BYTES:
            raise StoreError('Invalid chunk size or offset')
        self.refresh()
        path=self._path(id)/('source'+job['extension'])
        actual=path.stat().st_size
        if offset!=actual:
            raise StoreError(f'Unexpected offset; expected {actual}',409)
        if actual+len(data)>job['expected_size']:
            raise StoreError('Upload exceeds declared size',413)
        with path.open('ab') as f:
            f.write(data)
        self.commit()
        job['received']=actual+len(data)
        self.state['job:'+id]=job
        return job

    def finish(self,id,*,owner=None):
        job=self.info(id,owner=owner)
        if job['status']!='uploading':
            raise StoreError('Upload is not active',409)
        self.refresh()
        path=self._path(id)/('source'+job['extension'])
        if not path.exists() or path.stat().st_size!=job['expected_size']:
            raise StoreError('Incomplete upload',409)
        duration=self.probe(path)
        if not 1<=duration<=MAX_SECONDS:
            raise StoreError('Audio must be between one second and 60 minutes',400)
        times=[t for t in self.state.get('gpu_job_times',[]) if time.time()-t<86400]
        if len(times)>=4:
            raise StoreError('Daily GPU limit reached (4 jobs per 24 hours)',429)
        self.state['gpu_job_times']=times+[time.time()]
        job['status']='queued'
        job['duration']=duration
        self.state['job:'+id]=job
        if self.launch is None:
            # Local test mode: fake executor is allowed only for tests.
            return job
        try:
            handle=self.launch(id,job['extension'],job['diarization'],job['speakers'])
            current=self.state.get('job:'+id) or job
            if current['status']=='queued':
                current['function_call_id']=str(getattr(handle,'object_id',''))
                self.state['job:'+id]=current
            job=current
        except Exception:
            job['status']='failed'
            job['error']='Unable to start GPU processing'
            self.state['job:'+id]=job
        return job

    def source(self,id,*,owner=None):
        job=self.info(id,owner=owner)
        if job['status']=='uploading':
            raise StoreError('Upload not completed',409)
        self.refresh()
        p=self._path(id)/('source'+job['extension'])
        if not p.is_file():
            raise StoreError('Audio unavailable',410)
        return p

    def read_rows(self,id,*,owner=None):
        job=self.info(id,owner=owner)
        if job['status']!='complete':
            raise StoreError('Results not ready',409)
        self.refresh()
        folder=self._path(id)
        p=(folder/'edits.json') if (folder/'edits.json').is_file() else (folder/'results.json')
        if not p.is_file():
            raise StoreError('Results unavailable',500)
        return json.loads(p.read_text(encoding='utf-8'))

    def save_rows(self,id,rows,*,owner=None):
        job=self.info(id,owner=owner)
        if job['status']!='complete':
            raise StoreError('Results not ready',409)
        valid=normalize_edits(rows,job['duration'])
        self.refresh()
        folder=self._path(id)
        draft=folder/'edits.new'
        draft.write_text(json.dumps(valid,ensure_ascii=False),encoding='utf-8')
        draft.replace(folder/'edits.json')
        self.commit()
        return valid

    def review_windows(self,id,*,owner=None):
        job=self.info(id,owner=owner)
        if job['status']!='complete':
            raise StoreError('Results not ready',409)
        self.refresh()
        folder=self._path(id)
        p=folder/'review_candidates.json'
        if not p.is_file():
            return {'available':False,'total_candidates':0,'windows':[],'reviewed_ids':[],
                    'warning':'This recording was processed without overlap review.'}
        stored=json.loads(p.read_text(encoding='utf-8'))
        review_file=folder/'review_checked.json'
        reviewed=json.loads(review_file.read_text(encoding='utf-8')) if review_file.is_file() else []
        allowed={w['id'] for w in stored['windows']}
        return {**stored,'reviewed_ids':sorted(set(reviewed)&allowed)}

    def set_reviewed(self,id,window_id,reviewed,*,owner=None):
        # Ownership is checked before any candidate or filesystem access.
        self.info(id,owner=owner)
        if type(reviewed) is not bool:
            raise StoreError('reviewed must be boolean')
        if not isinstance(window_id,str):
            raise StoreError('Invalid candidate ID',400)
        record=self.review_windows(id,owner=owner)
        if window_id not in {x['id'] for x in record['windows']}:
            raise StoreError('Candidate not found',404)
        checked=set(record['reviewed_ids'])
        if reviewed:
            checked.add(window_id)
        else:
            checked.discard(window_id)
        file=self._path(id)/'review_checked.json'
        draft=file.with_suffix('.new')
        draft.write_text(json.dumps(sorted(checked)),encoding='utf-8')
        draft.replace(file)
        self.commit()
        return {'id':window_id,'reviewed':reviewed,'reviewed_count':len(checked)}

    def get_download(self,id,*,owner=None):
        job=self.info(id,owner=owner)
        return build_export(self.read_rows(id,owner=owner),source_name=job['filename'])

    def delete(self,id,*,owner=None):
        job=self.info(id,owner=owner)
        if job['status'] in ('running','queued'):
            # Never delete a file a GPU worker may be reading.
            raise StoreError('Processing is active. Delete after completion.',409)
        self.refresh()
        folder=self._path(id)
        # A failed physical delete must not be acknowledged as success.
        try:
            if folder.exists():
                shutil.rmtree(folder)
            if folder.exists():
                raise OSError('Job directory still exists')
            self.commit()
        except OSError as exc:
            raise StoreError('Stored recording could not be deleted',500) from exc
        job['status']='deleted'
        self.state['job:'+id]=job
        self.state['job_index']=[k for k in self.state.get('job_index',[]) if k!=id]


def probe_audio(path):
    """ffprobe with duration and audio stream validation, bounded wall-time."""
    command=['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type',
             '-of','json',str(path)]
    try:
        run=subprocess.run(command,capture_output=True,text=True,timeout=20,check=True)
        result=json.loads(run.stdout)
        if not any(s.get('codec_type')=='audio' for s in result.get('streams',[])):
            raise ValueError('Missing audio stream')
        duration=float(result['format']['duration'])
        import math
        if not math.isfinite(duration):
            raise ValueError('Invalid duration')
        return duration
    except (subprocess.SubprocessError,KeyError,ValueError,OverflowError) as exc:
        raise StoreError('Audio file cannot be decoded or has invalid duration',400) from exc