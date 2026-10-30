"""Experimental Qwen3-ASR + Qwen3-ForcedAligner Japanese timed tokens.

Only public CC BY-NC research inputs, no permanent web endpoint, no audio
or transcript printed. Raw timed transcription crosses the Modal boundary
to the short-lived GitHub runner solely for comparing human-reference cpCER.
"""
from pathlib import Path
import modal

app=modal.App("japanese-meeting-transcriber-qwen-alignment-research")
weights=modal.Volume.from_name('meeting-transcriber-models-v1',create_if_missing=True)
image=(modal.Image.debian_slim(python_version='3.11')
       .apt_install('ffmpeg','libsndfile1')
       .pip_install_from_requirements('requirements-modal.lock',
                                     extra_index_url='https://download.pytorch.org/whl/cu128')
       .pip_install('qwen-asr==0.0.6','nagisa==0.2.11')
       .env({'HF_HOME':'/models/hf','HF_HUB_CACHE':'/models/hf/hub',
             'HF_HUB_DISABLE_TELEMETRY':'1'})
       .add_local_python_source('scripts'))


@app.function(image=image,gpu='A10',cpu=2,memory=8192,timeout=1300,
              max_containers=1,scaledown_window=2,single_use_containers=True,
              volumes={'/models':weights})
def qwen_timed_tokens(audio_bytes:bytes):
    import os,subprocess,tempfile,time
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks
    if len(audio_bytes)>25*1024*1024:
        raise ValueError('Oversized research-only audio')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    with tempfile.TemporaryDirectory(prefix='qwen-timed-ja-') as tmp:
        original=Path(tmp)/'input.mp3'
        converted=Path(tmp)/'mono.wav'
        original.write_bytes(audio_bytes)
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
                        '-i',str(original),'-ac','1','-ar','16000','-c:a','pcm_s16le',
                        str(converted)],check=True)
        audio,sr=sf.read(converted,dtype='float32',always_2d=False)
        if sr!=16000 or audio.ndim!=1 or not 5<len(audio)/sr<=900:
            raise ValueError('Audio must be 5s–15min mono for isolated research')
        duration=float(len(audio)/sr)
        chunks=split_audio_into_chunks(np.asarray(audio,dtype=np.float32),
                                       sr=16000,max_chunk_sec=30.0)
        if not 1<=len(chunks)<=40:
            raise ValueError('Invalid chunk count')
        start=time.perf_counter()
        model=Qwen3ASRModel.from_pretrained(
            'Qwen/Qwen3-ASR-1.7B',dtype=torch.bfloat16,
            device_map='cuda:0',attn_implementation='sdpa',
            max_inference_batch_size=1,max_new_tokens=512,
            forced_aligner='Qwen/Qwen3-ForcedAligner-0.6B',
            forced_aligner_kwargs={'dtype':torch.bfloat16,'device_map':'cuda:0',
                                   'attn_implementation':'sdpa'})
        load_seconds=time.perf_counter()-start
        start=time.perf_counter()
        output=[]
        for waveform,offset in chunks:
            returned=model.transcribe(audio=(np.asarray(waveform,dtype=np.float32),16000),
                                      language='Japanese',return_time_stamps=True)
            if len(returned)!=1:
                raise ValueError('Unexpected Qwen result count')
            one=returned[0]
            aligned=one.time_stamps
            if one.text.strip() and (aligned is None or not aligned.items):
                raise ValueError('Qwen aligner lost a nonempty chunk')
            items=[{'text':w.text,'start_time':float(w.start_time),'end_time':float(w.end_time)}
                   for w in (aligned.items if aligned is not None else [])]
            output.append({'offset_sec':float(offset),'duration_sec':len(waveform)/16000,
                           'text':one.text,'items':items})
        inference_seconds=time.perf_counter()-start
        # Verify text conservation on the GPU before output to a temporary runner.
        from scripts.qwen_timing_bridge import qwen_segments
        segments,quality=qwen_segments(output,duration)
        weights.commit()
        return {'duration_seconds':duration,'chunks':output,
                'model':'Qwen/Qwen3-ASR-1.7B','aligner':'Qwen/Qwen3-ForcedAligner-0.6B',
                'qwen_model_load_seconds':load_seconds,
                'qwen_alignment_inference_seconds':inference_seconds,
                'text_integrity':quality,
                'note':'not approved for beta app; public noncommercial evaluation only'}


@app.local_entrypoint()
def main(audio:str,output:str='local_runs/qwen-private-tokens.json'):
    import json
    result=qwen_timed_tokens.remote(Path(audio).read_bytes())
    target=Path(output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print('QWEN_ALIGNER_NUMERIC_ONLY',json.dumps({
        'duration_seconds':result['duration_seconds'],
        'qwen_alignment_inference_seconds':result['qwen_alignment_inference_seconds'],
        'qwen_model_load_seconds':result['qwen_model_load_seconds'],
        'text_integrity':result['text_integrity']}))
