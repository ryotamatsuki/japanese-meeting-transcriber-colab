"""Structural safety checks only, not a Modal GPU test."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ModalStructureTests(unittest.TestCase):
    def test_no_public_endpoint_or_cpu_fallback(self):
        code = (ROOT/'modal_app.py').read_text()
        ast.parse(code)
        for endpoint in ('fastapi_endpoint', 'web_endpoint', 'asgi_app', 'wsgi_app', 'web_server'):
            self.assertNotIn(endpoint, code)
        self.assertIn("gpu='L4'", code)
        asr = (ROOT/'transcriber/asr.py').read_text()
        self.assertIn("COMPUTE = 'float16'", asr)
        self.assertNotIn("else 'cpu'", asr)

    def test_secret_only_on_diarization_function(self):
        tree = ast.parse((ROOT/'modal_app.py').read_text())
        functions = {n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
        self.assertNotIn('secrets', ast.unparse(functions['asr_only'].decorator_list[0]))
        self.assertIn('secrets', ast.unparse(functions['with_diarization'].decorator_list[0]))
        self.assertEqual(functions['with_diarization'].decorator_list[0].func.value.id,
                         'diarization_app')
        for name in ('gpu_check', 'asr_only'):
            self.assertEqual(functions[name].decorator_list[0].func.value.id, 'app')
        self.assertNotIn('google.colab', '\n'.join(p.read_text() for p in (ROOT/'transcriber').glob('*.py')))

    def test_pins_and_notebook_versions(self):
        pins = (ROOT/'requirements-modal.lock').read_text()
        for version in ('faster-whisper==1.2.1','pyannote-audio==4.0.7','av==18.1.0',
                        'torch==2.9.1+cu128','ctranslate2==4.6.2','nvidia-cudnn-cu12==9.10.2.21'):
            self.assertIn(version, pins)
        self.assertIn('huggingface-hub==0.36.0', pins)


if __name__ == '__main__': unittest.main()
