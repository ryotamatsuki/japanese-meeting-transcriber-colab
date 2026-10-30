"""Isolated Qwen3-ASR 1.7B Japanese research inference, NOT the beta application.

Pinned Qwen inference package. No HTTP, no credentials, no persistent audio or
transcripts. Run only licensed public corpus in a dedicated Modal GPU function.
"""
from pathlib import Path
import modal

app=modal.App('japanese-meeting-transcriber-stage10-qwen-research')
weights=modal.Volume.from_name('meeting-transcriber-models-v1',create_if_missing=True)
image=(modal.Image.debian_slim(python_version='3.11')
       .apt_install('ffmpeg','libsndfile1')
       .pip_install_from_requirements('requirements-modal.lock',
                                     extra_index_url='https://download.pytorch.org/whl/cu128')
       .pip_install('qwen-asr==0.0.6')
       .env({'HF_HOME':'/models/hf','HF_HUB_CACHE':'/models/hf/hub',
             'HF_HUB_DISABLE_TELEMETRY':'1'})
       .add_local_python_source('scripts'))


@app.function(image=image,gpu='A10',memory=8192,cpu=2,
              timeout=1100,max_containers=1,
              scaledown_window=2,single_use_containers=True,
              volumes={'/models':weights})
def evaluate_public_clip(raw_audio:bytes,human_reference:str,ref_sha:str,record_id:str):
    import io,json,subprocess,tempfile,time
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ASRModel
    from scripts.evaluate_asr_cer import evaluate
    if len(raw_audio)>24*1024*1024:
        raise ValueError('Audio exceeds 24MiB research cap')
    if not human_reference or len(human_reference)>150000:
        raise ValueError('Missing human reference')
    if not torch.cuda.is_available():
        raise RuntimeError('GPU required')
    with tempfile.TemporaryDirectory(prefix='qwen-ja-eval-') as tmp:
        wav=Path(tmp)/'in.mp3'
        decoded=Path(tmp)/'in.wav'
        wav.write_bytes(raw_audio)
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
                       '-i',str(wav),'-ac','1','-ar','16000','-c:a','pcm_s16le',
                        str(decoded)],check=True)
        audio,sr=sf.read(decoded,dtype='float32',always_2d=False)
        if sr!=16000 or audio.ndim!=1:
            raise ValueError('Expected 16k mono')
        started=time.perf_counter()
        model=Qwen3ASRModel.from_pretrained('Qwen/Qwen3-ASR-1.7B',
            dtype=torch.bfloat16,device_map='cuda:0',
            attn_implementation='sdpa',
            max_inference_batch_size=1,
            max_new_tokens=256)
        load_seconds=time.perf_counter()-started
        started=time.perf_counter()
        outputs=model.transcribe(audio=(np.asarray(audio,dtype=np.float32),16000),
                                 language='Japanese')
        inference_seconds=time.perf_counter()-started
        if len(outputs)!=1:raise ValueError('Qwen ASR expected one result')
        transcript=outputs[0].text
        score=evaluate(human_reference,transcript)
        weights.commit()
        return {'id':record_id,'eaf_sha256':ref_sha,'model':'Qwen/Qwen3-ASR-1.7B',
                'normalization':'NFKC+casefold; strip Unicode whitespace/punctuation',
                'cer':score['normalized_cer'],'reference_characters':score['reference_characters'],
                'hypothesis_characters':score['hypothesis_characters'],
                'load_seconds':load_seconds,'inference_seconds':inference_seconds,
                'audio_seconds':len(audio)/16000,
                'license':'IngCrowd CC BY-NC 4.0 for noncommercial evaluation',
                'note':'Flattened full-dialogue rough CER; not cpCER. No user audio.'}


@app.local_entrypoint()
def main(audio:str,eaf:str,output:str='local_runs/qwen-score.json',id:str='pilot'):
    import json
    from scripts.eval_elan_ja import load_elan
    reference,sha=load_elan(Path(eaf))
    record=evaluate_public_clip.remote(Path(audio).read_bytes(),
                 ''.join(x['text'] for x in reference),sha,id)
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('QWEN_RESEARCH_METRIC_ONLY',json.dumps({
        'id':id,'cer':record['cer'],'model':record['model'],
        'inference_seconds':record['inference_seconds']}))
