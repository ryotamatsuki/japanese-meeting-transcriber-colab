"""Deployable private beta: modal deploy beta_modal.py.

Requires Modal Secrets:
  transcriber-beta-auth: BETA_PASSWORD, BETA_SESSION_SECRET
  transcriber-hf: HF_TOKEN (Community-1 license access)
Do not deploy until a test workspace, policy-approved audio, and cost cap exist.
The web Function has no access to HF_TOKEN, and the GPU worker has no web auth.
"""
from pathlib import Path
import os
import modal

app=modal.App('japanese-meeting-transcriber-private-beta')
data=modal.Volume.from_name('meeting-transcriber-beta-files-v1',create_if_missing=True)
weights=modal.Volume.from_name('meeting-transcriber-models-v1',create_if_missing=True)
jobs=modal.Dict.from_name('meeting-transcriber-beta-jobs-v1',create_if_missing=True)

web_image=(modal.Image.debian_slim(python_version='3.11')
    .apt_install('ffmpeg')
    .pip_install('fastapi==0.115.12','uvicorn==0.34.2')
    .add_local_dir('beta', remote_path='/root/beta'))

gpu_image=(modal.Image.debian_slim(python_version='3.11')
    .apt_install('ffmpeg','libsndfile1')
    .pip_install_from_requirements('requirements-modal.lock',extra_index_url='https://download.pytorch.org/whl/cu128')
    .run_commands(
        "python -c \"import pathlib,site; p=pathlib.Path(site.getsitepackages()[0])/'nvidia'; "
        "pathlib.Path('/etc/ld.so.conf.d/99-transcriber.conf').write_text('\\n'.join(str(d) for d in p.glob('*/lib')))\"",
        'ldconfig','python -m pip check')
    .env({'HF_HOME':'/models/hf','HF_HUB_CACHE':'/models/hf/hub',
          'HF_HUB_DISABLE_TELEMETRY':'1','PYANNOTE_METRICS_ENABLED':'0'})
    .add_local_python_source('beta','transcriber'))


@app.function(image=gpu_image,gpu='A10',cpu=2,memory=8192,
              volumes={'/models':weights,'/data':data},
              timeout=3600,max_containers=1,scaledown_window=2,
              retries=0,single_use_containers=True,
              secrets=[modal.Secret.from_name('transcriber-hf',required_keys=['HF_TOKEN'])])
def transcribe_job(job_id: str, extension: str, diarization: bool, speakers: int):
    """Real long-form inference. No audio or transcripts written to logs."""
    import json
    import tempfile
    from beta.core import valid_job_id, parse_original_archive
    from beta.review import review_candidates_from_archive
    from transcriber.processor import Config, process
    if not valid_job_id(job_id) or extension not in ('.mp3','.m4a','.wav','.flac','.ogg','.mp4','.webm'):
        raise ValueError('Invalid job identifier or audio extension')
    key='job:'+job_id
    job=jobs.get(key)
    if not job or job['status']!='queued' or job['extension']!=extension:
        raise ValueError('Invalid or canceled work item')
    job['status']='running'
    jobs[key]=job
    try:
        data.reload()
        audio=Path('/data/jobs')/job_id/('source'+extension)
        if not audio.is_file() or audio.stat().st_size!=job['expected_size']:
            raise ValueError('Source audio missing or inconsistent')
        config=Config(enable_diarization=diarization,expected_speakers=speakers,
                      language='ja',quality_experiment=False,overlap_review=diarization,asr_beam_size=5)
        # The input is read from shared storage, not passed as an oversized RPC argument.
        with tempfile.TemporaryDirectory(prefix='transcriber-beta-') as tmp:
            archive,metrics=process(audio,Path(tmp)/'results','/models/whisper',config,
                                     token=os.environ.get('HF_TOKEN') if diarization else None,
                                     stage='full')
            weights.commit()
            raw_archive=archive.read_bytes()
            parsed=parse_original_archive(raw_archive)
            review=review_candidates_from_archive(raw_archive,job['duration'])
            folder=Path('/data/jobs')/job_id
            (folder/'original.zip').write_bytes(raw_archive)
            (folder/'review_candidates.json').write_text(json.dumps(review,ensure_ascii=False),encoding='utf-8')
            (folder/'results.json').write_text(json.dumps(parsed['rows'],ensure_ascii=False),encoding='utf-8')
            # Only aggregate technical metrics; no transcript text or model token.
            (folder/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False),encoding='utf-8')
            data.commit()
        job=jobs.get(key) or job
        if job['status']=='deleted':
            return
        job['status']='complete'
        job['utterances']=len(parsed['rows'])
        job['pipeline_seconds']=metrics.get('pipeline_seconds')
        jobs[key]=job
    except Exception:
        job=jobs.get(key) or job
        job['status']='failed'
        job['error']='Transcription failed; consult protected GPU logs'
        jobs[key]=job
        # Do not log or return raw content in the exception message.
        raise


@app.function(image=web_image,cpu=1,memory=1024,
              volumes={'/data':data},max_containers=1,timeout=120,
              secrets=[modal.Secret.from_name('transcriber-beta-auth',required_keys=[
                  'BETA_PASSWORD','BETA_SESSION_SECRET'])])
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def private_web():
    from beta.backend import FileBackend
    from beta.server import create_app
    backend=FileBackend('/data/jobs',jobs,
        launch=lambda job_id,ext,diar,sp: transcribe_job.spawn(job_id,ext,diar,sp),
        commit=data.commit,refresh=data.reload)
    return create_app(backend,password=os.environ['BETA_PASSWORD'],
                      session_secret=os.environ['BETA_SESSION_SECRET'])


@app.function(image=web_image,cpu=1,memory=512,volumes={'/data':data},
              schedule=modal.Period(hours=1),timeout=240)
def purge_expired_jobs():
    """Automatic 24h deletion. Protect active jobs until GPU function finishes."""
    from beta.retention import purge_expired
    data.reload()
    outcome=purge_expired('/data/jobs',jobs)
    # Commit after verified physical removal. On a storage failure, the
    # scheduled task fails visibly rather than claiming data was deleted.
    data.commit()
    # Aggregates only; never log filenames, contents or individual IDs.
    print('Retention sweep:',outcome)