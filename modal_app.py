"""Private modal run entrypoint. No HTTP endpoints; no retained audio volume."""
from pathlib import Path
import modal

app = modal.App('japanese-meeting-transcriber-stage1')
weights = modal.Volume.from_name('meeting-transcriber-models-v1', create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version='3.11')
    .apt_install('ffmpeg', 'libsndfile1')
    .pip_install_from_requirements('requirements-modal.lock', extra_index_url='https://download.pytorch.org/whl/cu128')
    # Expose torch's pinned CUDA12/cuDNN9 wheels to CTranslate2 at process startup.
    .run_commands(
        "python -c \"import pathlib,site; p=pathlib.Path(site.getsitepackages()[0])/'nvidia'; "
        "pathlib.Path('/etc/ld.so.conf.d/99-transcriber.conf').write_text('\\n'.join(str(d) for d in p.glob('*/lib')))\"",
        'ldconfig',
        'python -m pip check',
        'python -m pip freeze > /opt/transcriber-pip-freeze.txt',
        'python -c "import torch, torchaudio, torchcodec, av, ctranslate2, faster_whisper, soundfile, pyannote.audio"',
    )
    .env({'HF_HOME': '/models/hf', 'HF_HUB_CACHE': '/models/hf/hub',
          'HF_HUB_DISABLE_TELEMETRY': '1', 'PYANNOTE_METRICS_ENABLED': '0'})
    .add_local_python_source('transcriber')
)
options = dict(image=image, gpu='L4', cpu=(2, 2), memory=(8192, 8192),
               volumes={'/models': weights}, timeout=900, max_containers=1,
               scaledown_window=2, retries=0, single_use_containers=True)


@app.function(**options)
def gpu_check():
    from transcriber.runtime import diagnostics
    return diagnostics()


def _execute(audio, input_name, config_dict, stage, repeat, result_cache):
    import json
    import os
    import tempfile
    import time
    from dataclasses import asdict
    from transcriber.processor import Config, process
    from transcriber.runtime import diagnostics, MemorySampler
    config = Config(**config_dict)
    token = os.environ.get('HF_TOKEN') if config.enable_diarization and stage != 'asr' else None
    if config.enable_diarization and stage != 'asr' and not token:
        raise RuntimeError('Modal Secret transcriber-hf must contain HF_TOKEN')
    started = time.perf_counter()
    env = diagnostics()
    records, archives = [], []
    with tempfile.TemporaryDirectory(prefix='transcriber-') as folder:
        base = Path(folder)
        # Keep Colab-compatible source/output names; never print the name.
        path = base / Path(input_name).name
        path.write_bytes(audio)
        for idx in range(repeat):
            # These switches are read during import by HF; update constants too for warm process.
            import huggingface_hub.constants as hf_constants
            os.environ['HF_HUB_OFFLINE'] = '1' if idx else '0'
            hf_constants.HF_HUB_OFFLINE = bool(idx)
            output = base / ('results' if result_cache else f'results-{idx}')
            with MemorySampler() as sampler:
                archive, metrics = process(path, output, '/models/whisper', config, token, stage)
            weights.commit()
            metrics.update({'run': idx + 1, 'model_downloads_disabled': bool(idx),
                            'sampled_gpu_peak_mib': sampler.peak_mib,
                            'gpu_memory_sample_errors': sampler.errors})
            records.append(metrics)
            archives.append(archive.read_bytes())
        # Model snapshots/versions are useful for comparing repeated invocations.
        snapshots = sorted(str(p.relative_to('/models')) for p in Path('/models').rglob('snapshots/*') if p.is_dir())
    return {'environment': env, 'config': asdict(config), 'runs': records,
            'model_snapshots': snapshots, 'archives': archives,
            'remote_function_seconds': time.perf_counter() - started}


# ASR-only never references a Secret, even when it doesn't exist in the account.
@app.function(**options)
def asr_only(audio: bytes, input_name: str, config: dict, stage: str, repeat: int, result_cache: bool):
    return _execute(audio, input_name, config, stage, repeat, result_cache)


@app.function(**options, secrets=[modal.Secret.from_name('transcriber-hf', required_keys=['HF_TOKEN'])])
def with_diarization(audio: bytes, input_name: str, config: dict, stage: str, repeat: int, result_cache: bool):
    return _execute(audio, input_name, config, stage, repeat, result_cache)


@app.local_entrypoint()
def main(audio: str = '', output: str = 'local_runs', stage: str = 'full',
         no_diarization: bool = False, expected_speakers: int = 0,
         min_speakers: int = 0, max_speakers: int = 0, glossary: str = '',
         language: str = 'ja', repeat: int = 1, result_cache: bool = False):
    import json
    import time
    from dataclasses import asdict
    from transcriber.processor import Config
    if stage not in ('gpu', 'asr', 'diarization', 'full'):
        raise ValueError('stage: gpu/asr/diarization/full')
    if repeat not in (1, 2):
        raise ValueError('repeat is limited to 1 or 2 for this PoC')
    config = Config(enable_diarization=not no_diarization, language=language, glossary=glossary,
                    expected_speakers=expected_speakers, min_speakers=min_speakers,
                    max_speakers=max_speakers)
    if stage == 'diarization' and no_diarization:
        raise ValueError('diarization stage requires diarization enabled')
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if stage == 'gpu':
        result = {'environment': gpu_check.remote()}
    else:
        if Path(audio).stat().st_size > 25 * 1024 * 1024:
            raise ValueError('Stage 1 is limited to short test audio of at most 25 MiB')
        data = Path(audio).read_bytes()
        function = with_diarization if config.enable_diarization and stage != 'asr' else asr_only
        result = function.remote(data, Path(audio).name, asdict(config), stage, repeat, result_cache)
        for idx, archive in enumerate(result.pop('archives'), 1):
            (target / f'run-{idx}.zip').write_bytes(archive)
    result['client_wall_seconds'] = time.perf_counter() - started
    result['timing_note'] = 'client wall includes build/queue/upload/download; not pure container startup time'
    (target / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Evidence saved; inspect ZIP and evidence.json locally. No transcript printed.')
