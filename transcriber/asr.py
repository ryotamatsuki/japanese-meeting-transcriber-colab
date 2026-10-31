"""Notebook cell 12, parameterized for a single job; GPU only."""
import time

def transcribe(job, config, model_cache, metrics, progress=None):
    jobs = [job]
    WHISPER_MODEL, LANGUAGE, GLOSSARY = config.asr_model, config.language, config.glossary
    import json, gc
    import torch, av
    from faster_whisper import WhisperModel
    DEVICE = 'cuda'
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU is required; CPU fallback is disabled.')
    COMPUTE = 'float16'
    ASR_SETTINGS = {'model': WHISPER_MODEL, 'language': LANGUAGE, 'glossary': GLOSSARY.strip(), 'beam_size': config.asr_beam_size, 'vad_filter': True, 'min_silence_duration_ms': 550, 'word_timestamps': True, 'condition_on_previous_text': False}
    if progress:
        progress('asr', 0.0, None)
    pending = []
    for job in jobs:
        dest = job['outdir'] / 'whisper_asr.json'
        cached = None
        if dest.is_file():
            try:
                cached = json.loads(dest.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                pass
        if isinstance(cached, dict) and cached.get('source_sha256') == job['sha256'] and (cached.get('settings') == ASR_SETTINGS) and isinstance(cached.get('segments'), list):
            job['asr_segments'] = cached['segments']
            if progress:
                progress('asr', max((float(row['end']) for row in cached['segments']), default=0.0),
                         max((float(row['end']) for row in cached['segments']), default=1.0))
        else:
            pending.append(job)
    metrics["asr_result_cache_hit"] = not bool(pending)
    if pending:
        load_started = time.perf_counter()
        model = WhisperModel(WHISPER_MODEL, device=DEVICE, compute_type=COMPUTE, download_root=str(model_cache))
        metrics["asr_model_load_seconds"] = time.perf_counter() - load_started
        infer_started = time.perf_counter()
        for number, job in enumerate(pending, 1):
            segments, info = model.transcribe(str(job['path']), language=None if LANGUAGE == 'auto' else LANGUAGE, task='transcribe', beam_size=config.asr_beam_size, vad_filter=True, vad_parameters={'min_silence_duration_ms': 550}, initial_prompt=GLOSSARY.strip() or None, condition_on_previous_text=False, word_timestamps=True)
            metrics["audio_seconds"] = float(info.duration)
            rows = []
            last_report = time.monotonic()
            if progress:
                progress('asr', 0.0, float(info.duration))
            partial = job['outdir'] / 'whisper_asr_partial.json'
            for seg in segments:
                rows.append({'start': float(seg.start), 'end': float(seg.end), 'text': seg.text, 'words': [{'start': float(w.start), 'end': float(w.end), 'text': w.word} for w in seg.words or []]})
                if progress:
                    # faster-whisper returns decoded segments lazily. Only
                    # confirmed audio endpoints are reported (never elapsed-time animation).
                    audio_end = min(float(info.duration), max(0.0, float(seg.end)))
                    report_now = time.monotonic()
                    if report_now - last_report >= 3 or audio_end >= float(info.duration):
                        progress('asr', audio_end, float(info.duration))
                        last_report = report_now
                if len(rows) % 100 == 0:
                    partial.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            if progress:
                progress('asr', float(info.duration), float(info.duration))
            job['asr_segments'] = rows
            record = {'source_name': job['path'].name, 'source_sha256': job['sha256'], 'settings': ASR_SETTINGS, 'segments': rows}
            (job['outdir'] / 'whisper_asr.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            partial.unlink(missing_ok=True)
        metrics["asr_inference_seconds"] = time.perf_counter() - infer_started
        del model
        gc.collect()
        if DEVICE == 'cuda':
            torch.cuda.empty_cache()
    return ASR_SETTINGS
