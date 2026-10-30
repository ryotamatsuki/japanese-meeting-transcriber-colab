"""Notebook cell 14; waveform conversion and exclusive diarization unchanged."""
import time

def diarize(job, config, token, metrics):
    jobs = [job]
    ENABLE_DIARIZATION = config.enable_diarization
    EXPECTED_SPEAKERS = config.expected_speakers
    MIN_SPEAKERS, MAX_SPEAKERS = config.min_speakers, config.max_speakers
    HF_TOKEN, DEVICE = token, "cuda"
    import csv, gc, json, subprocess
    import numpy as np
    import soundfile as sf
    import torch
    DIAR_SETTINGS = {'model': 'pyannote/speaker-diarization-community-1', 'expected': int(EXPECTED_SPEAKERS), 'min': int(MIN_SPEAKERS) if not EXPECTED_SPEAKERS else 0, 'max': int(MAX_SPEAKERS) if not EXPECTED_SPEAKERS else 0}
    if ENABLE_DIARIZATION:
        if not token:
            raise RuntimeError('HF_TOKEN is required: configure Modal Secret transcriber-hf and accept Community-1 conditions.')
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA GPU is required for diarization.')
        todo = []
        for job in jobs:
            dest = job['outdir'] / 'pyannote_話者区間.json'
            cached = None
            if dest.exists():
                try:
                    cached = json.loads(dest.read_text(encoding='utf-8'))
                except (ValueError, OSError):
                    pass
            if isinstance(cached, dict) and cached.get('source_sha256') == job['sha256'] and (cached.get('settings') == DIAR_SETTINGS) and isinstance(cached.get('segments'), list):
                job['diar_segments'] = cached['segments']
            else:
                todo.append(job)
        metrics["diarization_result_cache_hit"] = not bool(todo)
        if todo:
            from pyannote.audio import Pipeline
            from huggingface_hub.errors import HfHubHTTPError
            load_started = time.perf_counter()
            try:
                pipeline = Pipeline.from_pretrained(DIAR_SETTINGS['model'], token=HF_TOKEN)
            except HfHubHTTPError:
                raise RuntimeError('Community-1 load failed: verify HF_TOKEN read permission, model access conditions, network and dependency versions.') from None
            if pipeline is None:
                raise RuntimeError('Community-1 returned no pipeline; verify model access conditions.')
            if torch.cuda.is_available():
                pipeline.to(torch.device('cuda'))
            metrics["diarization_model_load_seconds"] = time.perf_counter() - load_started
            infer_started = time.perf_counter()
            diar_params = {}
            if EXPECTED_SPEAKERS:
                diar_params['num_speakers'] = int(EXPECTED_SPEAKERS)
            else:
                if MIN_SPEAKERS:
                    diar_params['min_speakers'] = int(MIN_SPEAKERS)
                if MAX_SPEAKERS:
                    diar_params['max_speakers'] = int(MAX_SPEAKERS)
            for number, job in enumerate(todo, 1):
                wav_path = job['outdir'] / 'temporary_16k_mono.wav'
                try:
                    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', str(job['path']), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(wav_path)], check=True)
                    samples, sample_rate = sf.read(wav_path, dtype='float32', always_2d=False)
                    if sample_rate != 16000 or samples.ndim != 1:
                        raise ValueError('16kHz・モノラルへの変換に失敗しました。')
                    waveform = torch.from_numpy(np.ascontiguousarray(samples)).unsqueeze(0)
                    del samples
                    diar_output = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **diar_params)
                    annotation = diar_output.exclusive_speaker_diarization
                    intervals = [{'start': float(turn.start), 'end': float(turn.end), 'speaker_id': str(speaker)} for turn, _, speaker in annotation.itertracks(yield_label=True)]
                    intervals.sort(key=lambda x: (x['start'], x['end']))
                    job['diar_segments'] = intervals
                    record = {'source_sha256': job['sha256'], 'settings': DIAR_SETTINGS, 'segments': intervals}
                    (job['outdir'] / 'pyannote_話者区間.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
                    del waveform, diar_output, annotation
                    gc.collect()
                    if DEVICE == 'cuda':
                        torch.cuda.empty_cache()
                finally:
                    wav_path.unlink(missing_ok=True)
            metrics["diarization_inference_seconds"] = time.perf_counter() - infer_started
            del pipeline
            gc.collect()
            if DEVICE == 'cuda':
                torch.cuda.empty_cache()
        for job in jobs:
            path = job['outdir'] / 'pyannote_話者区間.csv'
            with path.open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['start', 'end', 'speaker_id'])
                writer.writeheader()
                writer.writerows(job['diar_segments'])
    else:
        for job in jobs:
            job['diar_segments'] = []
    return DIAR_SETTINGS
