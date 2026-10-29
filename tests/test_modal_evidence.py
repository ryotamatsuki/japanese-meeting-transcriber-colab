"""Synthetic evidence contract tests; never assert GPU inference happened in CI."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('validate_evidence', ROOT/'scripts'/'validate_evidence.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def fixture(stage='full', off=False, repeat=False, cache=False):
    metrics = []
    for i in range(2 if repeat else 1):
        cached = cache and i == 1
        m = {'run': i+1, 'stage': stage, 'pipeline_seconds': 10,
             'model_downloads_disabled': bool(i),
             'sampled_gpu_peak_mib': 2000, 'gpu_memory_sample_errors': 0}
        if stage != 'diarization':
            m.update(asr_result_cache_hit=cached)
            if not cached:
                m.update(asr_model_load_seconds=3, asr_inference_seconds=6)
        if stage != 'asr' and not off:
            m.update(diarization_result_cache_hit=cached)
            if not cached:
                m.update(diarization_model_load_seconds=4, diarization_inference_seconds=7)
        if stage == 'full':
            m['alignment_export_seconds'] = 1
        metrics.append(m)
    return {'environment': {'gpu':'NVIDIA L4','cuda_available': True,
                            'ctranslate2_cuda_devices': 1,
                            'torch_cuda':'12.8','cudnn': 91002},
            'client_wall_seconds': 28,
            'remote_function_seconds': 20,
            'config': {'enable_diarization':not off},
            'runs':metrics}


class EvidenceValidationTests(unittest.TestCase):
    def test_gpu_diagnostics_only(self):
        x = fixture()
        x.pop('runs')
        x.pop('config')
        x.pop('remote_function_seconds')
        self.assertIn('PASS', validator.validate(x, 'gpu'))

    def test_full(self):
        self.assertIn('PASS', validator.validate(fixture(), 'full'))

    def test_off(self):
        self.assertIn('PASS', validator.validate(fixture(off=True), 'full', off=True))

    def test_asr_and_diarization(self):
        for stage in ('asr', 'diarization'):
            self.assertIn('PASS', validator.validate(fixture(stage=stage), stage))

    def test_model_and_result_cache(self):
        for mode in ('model','result'):
            data = fixture(repeat=True,cache=(mode=='result'))
            self.assertIn('PASS', validator.validate(data, 'full', cache_mode=mode))

    def test_missing_real_inference(self):
        x = fixture()
        x['runs'][0].pop('asr_inference_seconds')
        with self.assertRaisesRegex(validator.EvidenceError, 'inference'):
            validator.validate(x, 'full')

    def test_wrong_cache_claim(self):
        x = fixture(repeat=True,cache=False)
        with self.assertRaisesRegex(validator.EvidenceError, 'cache'):
            validator.validate(x, 'full', cache_mode='result')

    def test_gpu_mismatch(self):
        x = fixture()
        x['environment']['gpu'] = 'NVIDIA T4'
        with self.assertRaisesRegex(validator.EvidenceError, 'L4'):
            validator.validate(x,'full')

    def test_sampler_error(self):
        x = fixture()
        x['runs'][0]['gpu_memory_sample_errors'] = 1
        with self.assertRaisesRegex(validator.EvidenceError, 'sampler'):
            validator.validate(x,'full')


if __name__ == '__main__':
    unittest.main()
