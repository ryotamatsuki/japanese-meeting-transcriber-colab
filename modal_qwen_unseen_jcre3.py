"""One-off, non-production Qwen baseline on a newly acquired J-CRe3 pilot."""
from pathlib import Path
import modal
from modal_qwen_quality_ablation import image, weights

APP_NAME='kiroku-jcre3-unseen-pilot-20261031-01'
INPUT_VOLUME='kiroku-jcre3-unseen-inputs-20261031-01'
BUNDLE_SHA='ec83653e440a2707781443298549c3f92cb22c1930294eec10f9a83c03f15d31'
BUNDLE_SIZE=5670036
app=modal.App(APP_NAME)
inputs=modal.Volume.from_name(INPUT_VOLUME,create_if_missing=True)
cpu_image=modal.Image.debian_slim(python_version='3.11').pip_install('fastapi==0.115.12').add_local_python_source('scripts')


@app.function(image=cpu_image,volumes={'/inputs':inputs},cpu=.25,memory=256,
              max_containers=1,scaledown_window=2,timeout=30)
@modal.concurrent(max_inputs=1)
@modal.asgi_app()
def intake():
    from scripts.unseen_intake import create_intake
    return create_intake(inputs,'/inputs',BUNDLE_SHA,BUNDLE_SIZE)


@app.function(image=image,volumes={'/inputs':inputs,'/models':weights},gpu='A10',cpu=2,
              memory=8192,max_containers=1,scaledown_window=2,timeout=600,
              single_use_containers=True,retries=0,
              secrets=[modal.Secret.from_name('transcriber-hf',required_keys=['HF_TOKEN'])])
def evaluate():
    import hashlib,json,os,statistics,subprocess,tempfile,time,zipfile
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks
    from transcriber.processor import Config
    from transcriber.diarization import diarize
    from scripts.jcre3_reference import load_reference
    from scripts.qwen_chunk_retry import infer_chunk
    from scripts.qwen_timing_bridge import attribute_qwen
    from scripts.qwen_quality_experiments import edit_components
    from scripts.evaluate_attributed_transcript import permutation_cer
    started=time.perf_counter()
    data=Path('/inputs/eval.zip').read_bytes()
    if len(data)!=BUNDLE_SIZE or hashlib.sha256(data).hexdigest()!=BUNDLE_SHA:
        raise ValueError('Corpus identity changed')
    with tempfile.TemporaryDirectory(prefix='jcre3-pilot-') as directory:
        root=Path(directory)
        archive=zipfile.ZipFile(Path('/inputs/eval.zip'))
        manifest=json.loads(archive.read('manifest.json'))
        ids=('20220302-56130322-0','20220303-56130205-1','20220304-56132112-1')
        if tuple(r['id'] for r in manifest['records'])!=ids or manifest['license']!='CC BY-SA 4.0':
            raise ValueError('Unexpected corpus manifest')
        allowed={'manifest.json','ATTRIBUTION.txt'}|{f'{i}/{name}' for i in ids for name in ('preview.mp3','reference.txt')}
        if set(archive.namelist())!=allowed or sum(v.file_size for v in archive.infolist())>8*1024*1024:
            raise ValueError('Unexpected corpus archive layout')
        prepared=[]
        findings=[]
        # Diarize before loading Qwen, as in the frozen baseline runner.
        for record in manifest['records']:
            stage='decode_reference_diarization';begin=time.perf_counter()
            item={'record_id':record['id'],'status':'failed'}
            try:
                audio_data=archive.read(record['id']+'/preview.mp3')
                reference_data=archive.read(record['id']+'/reference.txt')
                reference,sha=load_reference(reference_data)
                if sha!=record['reference_sha256'] or hashlib.sha256(audio_data).hexdigest()!=record['audio_sha256']:
                    raise ValueError('Record identity changed')
                out=root/record['id'];out.mkdir()
                audio=out/'input.mp3';audio.write_bytes(audio_data)
                pcm=out/'input.wav'
                subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
                    '-i',str(audio),'-ar','16000','-ac','1','-c:a','pcm_s16le',str(pcm)],check=True,timeout=30)
                signal,sr=sf.read(pcm,dtype='float32')
                duration=len(signal)/sr
                if sr!=16000 or signal.ndim!=1 or not 30<=duration<=240:
                    raise ValueError('Unexpected pilot audio')
                config=Config(enable_diarization=True,language='ja',expected_speakers=2,overlap_review=True)
                job={'path':audio,'sha256':record['audio_sha256'],'outdir':out,'prefix':'pilot'}
                metrics={};diarize(job,config,os.environ['HF_TOKEN'],metrics)
                automatic=job['diar_segments']
                speech_end=max(float(v['end']) for v in automatic)
                item.update({'audio_seconds':duration,'audio_sha256':record['audio_sha256'],
                    'reference_sha256':sha,'reference_turns':len(reference),
                    'detected_speech_end_seconds':speech_end,
                    'reference_speech_end_seconds_diagnostic':max(v['end'] for v in reference),
                    'diarization_seconds':time.perf_counter()-begin})
                prepared.append((item,signal,reference,automatic,duration,speech_end))
            except Exception as exc:
                item.update({'failure_stage':stage,'error_class':type(exc).__name__})
            findings.append(item)
        loaded=time.perf_counter()
        model=Qwen3ASRModel.from_pretrained('Qwen/Qwen3-ASR-1.7B',dtype=torch.bfloat16,
            device_map='cuda:0',attn_implementation='sdpa',max_inference_batch_size=1,max_new_tokens=512,
            forced_aligner='Qwen/Qwen3-ForcedAligner-0.6B',forced_aligner_kwargs={
                'dtype':torch.bfloat16,'device_map':'cuda:0','attn_implementation':'sdpa'})
        load_seconds=time.perf_counter()-loaded
        for item,signal,reference,automatic,duration,speech_end in prepared:
            begin=time.perf_counter();stage='asr_alignment'
            try:
                collected=[];retries=0
                chunks=split_audio_into_chunks(np.asarray(signal,dtype=np.float32),sr=16000,max_chunk_sec=30.)
                for chunk,offset in chunks:
                    rows,meta=infer_chunk(model,np.asarray(chunk,dtype=np.float32),float(offset))
                    collected.extend(rows);retries+=meta['retries']
                stage='attribution'
                utterances,integrity=attribute_qwen(collected,automatic,duration,
                    speech_end_seconds=min(duration,speech_end))
                stage='evaluation'
                cp=permutation_cer(reference,utterances)
                cer=edit_components(''.join(r['text'] for r in reference),''.join(r['text'] for r in collected))
                item.update({'status':'success','chunks':len(chunks),'bounded_retries':retries,
                    'cpcer':cp['cpcer'],'cpcer_edits':cp['edit_distance'],
                    'reference_normalized_characters':cp['reference_characters'],
                    'flattened_cer':cer['cer'],'insertions':cer['insertions'],
                    'deletions':cer['deletions'],'substitutions':cer['substitutions'],
                    'aligned_tokens':integrity['aligned_tokens'],'tail_seconds':integrity['final_word_end_seconds']})
            except Exception as exc:
                item.update({'status':'failed','failure_stage':stage,'error_class':type(exc).__name__})
            item['inference_and_eval_seconds']=time.perf_counter()-begin
        good=[r for r in findings if r['status']=='success']
        return {'dataset':'J-CRe3','source_revision':manifest['revision'],'bundle_sha256':BUNDLE_SHA,
            'license':'CC BY-SA 4.0','audio_representation':manifest['audio_representation'],
            'scope':manifest['scope'],'model_training_exposure':'unknown',
            'model':'Qwen/Qwen3-ASR-1.7B','chunk_seconds':30,'context_used':False,
            'records':findings,'successful_records':len(good),
            'median_cpcer':statistics.median(r['cpcer'] for r in good) if good else None,
            'micro_cpcer':sum(r['cpcer_edits'] for r in good)/sum(r['reference_normalized_characters'] for r in good) if good else None,
            'model_load_seconds':load_seconds,'gpu_function_seconds':time.perf_counter()-started,
            'commercial_ready':False,'warning':'New project-level pilot recordings; acted household dialogue and transcoded previews, not an administrative meeting acceptance test.'}


@app.local_entrypoint()
def main(output:str):
    import json
    result=evaluate.remote()
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('JCRE3_NUMERIC_RESULT',json.dumps({'successful_records':result['successful_records'],
        'median_cpcer':result['median_cpcer'],'gpu_function_seconds':result['gpu_function_seconds']}))
