"""Research-only 1-60min Qwen3 ASR + Japanese ForcedAligner + Community-1.

Must be called from the *separately authenticated isolated* Qwen research Modal
application. Not a beta default. Do not send audio/transcripts to logs/artifacts.
"""
from __future__ import annotations

import gc
import json
import subprocess
import time
from pathlib import Path

from .files import safe_name, sha256_file
from .exporters import export


def transcribe_qwen_research(path, output_root, model_cache, config, token, progress=None):
    progress=progress or (lambda phase: None)
    progress('starting')
    if not config.enable_diarization or not token:
        raise ValueError('Qwen research requires Community-1 and an HF token')
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks
    from .diarization import diarize
    from scripts.qwen_timing_bridge import attribute_qwen, qwen_segments

    if not torch.cuda.is_available():
        raise RuntimeError('GPU is required for Qwen research')
    audio = Path(path)
    out_root = Path(output_root)
    if not audio.is_file():
        raise ValueError('Missing source audio')
    out_root.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(audio)
    prefix = f'{safe_name(audio.stem)}_{digest[:10]}'
    outdir = out_root / prefix
    outdir.mkdir(parents=True, exist_ok=True)
    job = {'path':audio,'sha256':digest,'prefix':prefix,'outdir':outdir}
    metrics = {'stage':'research_qwen_web','model':'Qwen/Qwen3-ASR-1.7B'}
    began = time.perf_counter()

    progress('decode')
    wav = outdir / 'temporary_qwen_mono16k.wav'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin',
                    '-y','-i',str(audio),'-vn','-ac','1','-ar','16000',
                    '-c:a','pcm_s16le',str(wav)],check=True,timeout=150)
    samples, sr = sf.read(wav,dtype='float32',always_2d=False)
    if sr != 16000 or samples.ndim != 1:
        raise ValueError('Expected 16kHz mono')
    duration = len(samples)/sr
    if not 1 <= duration <= 3600:
        raise ValueError('Research audio must be 1-60 minutes')
    audio_chunks = split_audio_into_chunks(np.asarray(samples,dtype=np.float32),
                                           sr=16000,max_chunk_sec=30.0)
    del samples
    wav.unlink(missing_ok=True)
    if not 1 <= len(audio_chunks) <= 240:
        raise ValueError('Too many Qwen audio chunks')
    progress('load_qwen')
    t=time.perf_counter()
    model=Qwen3ASRModel.from_pretrained(
        'Qwen/Qwen3-ASR-1.7B',dtype=torch.bfloat16,device_map='cuda:0',
        attn_implementation='sdpa',max_inference_batch_size=1,max_new_tokens=512,
        forced_aligner='Qwen/Qwen3-ForcedAligner-0.6B',
        forced_aligner_kwargs={'dtype':torch.bfloat16,'device_map':'cuda:0',
                               'attn_implementation':'sdpa'})
    metrics['qwen_load_seconds']=time.perf_counter()-t
    t=time.perf_counter()
    progress('infer_qwen')
    chunks=[]
    for waveform,offset in audio_chunks:
        one=model.transcribe(
            audio=(np.asarray(waveform,dtype=np.float32),16000),
            language='Japanese',return_time_stamps=True)
        if len(one)!=1 or (one[0].text.strip() and not getattr(one[0].time_stamps,'items',None)):
            raise ValueError('Missing Qwen aligned text')
        aligned=one[0].time_stamps
        tokens=[{'text':word.text,'start_time':float(word.start_time),
                 'end_time':float(word.end_time)}
                for word in (aligned.items if aligned is not None else [])]
        chunks.append({'offset_sec':float(offset),'duration_sec':len(waveform)/sr,
                       'text':one[0].text,'items':tokens})
    metrics['qwen_inference_seconds']=time.perf_counter()-t
    progress('align_validate')
    job['asr_segments'],integrity=qwen_segments(chunks,duration)
    metrics['qwen_integrity']={k:v for k,v in integrity.items()
                               if k not in ('text',)}
    # Save transcript only to the ephemeral user-private job directory.
    asr_name='qwen_asr.json'
    (outdir/asr_name).write_text(json.dumps(
        {'source_sha256':digest,'model':'Qwen/Qwen3-ASR-1.7B',
         'aligner':'Qwen/Qwen3-ForcedAligner-0.6B','segments':job['asr_segments']},
        ensure_ascii=False),encoding='utf-8')
    job['asr_json_name']=asr_name
    del model,audio_chunks
    gc.collect()
    torch.cuda.empty_cache()

    progress('diarization')
    diar_settings=diarize(job,config,token,metrics)
    # Refuse an empty diarization rather than returning anonymous transcripts.
    if not job.get('diar_segments'):
        raise ValueError('Community-1 produced no speaker boundaries')
    # Attribute original Qwen token order, applying only bounded repair
    # already covered by Stage12 lexical/order integrity guards.
    progress('speaker_attribution')
    rows,quality=attribute_qwen(chunks,job['diar_segments'],duration)
    count=quality['aligned_tokens']
    speaker_map={seg['speaker_id']:f'話者{i+1}' for i,seg in enumerate(
        {seg['speaker_id']:None for seg in job['diar_segments']})}
    metrics['attribution_repairs']=quality.get('small_temporal_order_repairs',0)
    del chunks
    job['utterances'],job['speaker_map'],job['word_count']=rows,speaker_map,count
    metrics['estimated_speakers']=len(speaker_map)
    metrics['attributed_utterances']=len(rows)
    progress('export')
    zip_path=export(job,out_root,config,
        {'model':'Qwen/Qwen3-ASR-1.7B',
         'aligner':'Qwen/Qwen3-ForcedAligner-0.6B',
         'research_only':True,'language':'Japanese'},
        diar_settings)
    metrics['audio_seconds']=duration
    metrics['pipeline_seconds']=time.perf_counter()-began
    return zip_path,metrics
