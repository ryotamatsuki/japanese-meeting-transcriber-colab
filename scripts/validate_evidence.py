"""Check Stage 1 Modal evidence without reading or printing transcription content.

This is a structural consistency check, NOT a speech-accuracy certification.
"""
import argparse
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcriber.runtime import gpu_matches


class EvidenceError(ValueError):
    """The submitted Stage 1 evidence is incomplete or inconsistent."""


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def positive_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate(record, stage, off=False, cache_mode='none', expected_gpu='L4'):
    """Validate an already-finished Modal run; never triggers a GPU job."""
    require(stage in ('gpu', 'asr', 'diarization', 'full'), 'Invalid stage')
    require(cache_mode in ('none', 'model', 'result'), 'Invalid cache mode')
    require(not (off and stage in ('gpu', 'diarization')), 'OFF is not applicable to this stage')
    require(cache_mode == 'none' or stage != 'gpu', 'GPU check has no repeat mode')

    require(isinstance(record, dict), 'Evidence must be a JSON object')
    env = record.get('environment')
    require(isinstance(env, dict), 'Missing runtime environment diagnostics')
    name = env.get('gpu')
    require(gpu_matches(name, expected_gpu),
            f'NVIDIA {expected_gpu} identity is not recorded')
    require(env.get('expected_gpu', expected_gpu) == expected_gpu,
            'Requested GPU differs from validator expectation')
    require(env.get('cuda_available') is True, 'CUDA availability not verified')
    count = env.get('ctranslate2_cuda_devices')
    require(type(count) is int and count >= 1, 'CTranslate2 CUDA device missing')
    require(bool(env.get('torch_cuda')) and bool(env.get('cudnn')),
            'Missing torch CUDA or cuDNN runtime information')
    require(positive_number(record.get('client_wall_seconds')),
            'Missing client wall-clock measurement')
    if stage == 'gpu':
        require(not record.get('runs'), 'GPU-only evidence unexpectedly contains inference runs')
        return f'PASS: {expected_gpu}/CUDA diagnostic evidence present; ASR was NOT tested'

    require(positive_number(record.get('remote_function_seconds')),
            'Missing remote function duration')
    config = record.get('config')
    require(isinstance(config, dict), 'Missing run config')
    if stage != 'asr':
        require(config.get('enable_diarization') is (not off),
                'Diarization setting does not match the selected mode')
    runs = record.get('runs')
    expected = 1 if cache_mode == 'none' else 2
    require(isinstance(runs, list) and len(runs) == expected,
            f'Expected {expected} inference run(s)')
    for i, metrics in enumerate(runs):
        require(isinstance(metrics, dict) and metrics.get('run') == i+1,
                f'Run {i+1}: missing or wrong run index')
        require(metrics.get('stage') == stage, f'Run {i+1}: wrong stage')
        require(positive_number(metrics.get('pipeline_seconds')),
                f'Run {i+1}: missing pipeline duration')
        require(metrics.get('model_downloads_disabled') is (i > 0),
                f'Run {i+1}: incorrect offline model-cache flag')
        require(type(metrics.get('sampled_gpu_peak_mib')) is int and
                metrics['sampled_gpu_peak_mib'] > 0,
                f'Run {i+1}: missing GPU-memory observation')
        require(metrics.get('gpu_memory_sample_errors') == 0,
                f'Run {i+1}: GPU-memory sampler reported errors')
        for prefix, applicable in [('asr', stage != 'diarization'),
                                   ('diarization', stage != 'asr' and not off)]:
            if not applicable:
                continue
            cached = metrics.get(prefix + '_result_cache_hit')
            expect_hit = cache_mode == 'result' and i == 1
            require(cached is expect_hit,
                    f'Run {i+1}: unexpected {prefix} result-cache state')
            if not expect_hit:
                require(positive_number(metrics.get(prefix + '_model_load_seconds')),
                        f'Run {i+1}: {prefix} model load was not measured')
                require(positive_number(metrics.get(prefix + '_inference_seconds')),
                        f'Run {i+1}: {prefix} inference was not measured')
        if stage == 'full':
            require(positive_number(metrics.get('alignment_export_seconds')),
                    f'Run {i+1}: missing alignment/export measurement')
    return 'PASS: GPU and stage timing/cache evidence is structurally consistent; listen to the audio to assess accuracy'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--stage', required=True,
                        choices=('gpu','asr','diarization','full'))
    parser.add_argument('--off', action='store_true')
    parser.add_argument('--expected-gpu', default='L4', choices=('L4', 'A10', 'L40S'))
    parser.add_argument('--cache-mode', default='none', choices=('none','model','result'))
    args = parser.parse_args()
    try:
        evidence = json.loads(args.evidence.read_text(encoding='utf-8'))
        print(validate(evidence, args.stage, args.off, args.cache_mode, args.expected_gpu))
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        parser.exit(1, f'FAIL: {exc}\n')


if __name__ == '__main__':
    main()
