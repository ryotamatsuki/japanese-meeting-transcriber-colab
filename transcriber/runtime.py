"""GPU/import diagnostics and sampled device memory (includes CTranslate2)."""
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


def diagnostics():
    import torch
    import av
    import ctranslate2
    import faster_whisper
    import soundfile
    import pyannote.audio
    import torchcodec
    if not torch.cuda.is_available():
        raise RuntimeError('torch.cuda.is_available() is False; GPU validation failed')
    name = torch.cuda.get_device_name(0)
    if 'L4' not in name or 'L40' in name:
        raise RuntimeError('Expected NVIDIA L4, received ' + name)
    # Actually allocate and calculate on CUDA, not only query the driver.
    result = (torch.ones(8, device='cuda') * 2).sum().item()
    torch.cuda.synchronize()
    if result != 16:
        raise RuntimeError('CUDA tensor calculation failed')
    data = {'python': sys.version, 'gpu': name, 'cuda_available': True,
            'torch_cuda': torch.version.cuda, 'cudnn': torch.backends.cudnn.version(),
            'gpu_total_bytes': torch.cuda.get_device_properties(0).total_memory,
            'ctranslate2_cuda_devices': ctranslate2.get_cuda_device_count(),
            'versions': {n: importlib.metadata.version(n) for n in
                         ('torch', 'torchaudio', 'torchcodec', 'faster-whisper',
                          'ctranslate2', 'pyannote.audio', 'av', 'soundfile')},
            'nvidia_smi': subprocess.check_output(['nvidia-smi'], text=True),
            'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0]}
    if data['ctranslate2_cuda_devices'] < 1:
        raise RuntimeError('CTranslate2 cannot see CUDA')
    freeze = Path('/opt/transcriber-pip-freeze.txt')
    if freeze.exists():
        data['pip_freeze'] = freeze.read_text()
    return data


class MemorySampler:
    """Sample nvidia-smi every 200ms; observed peak is a lower bound."""
    def __enter__(self):
        self.stop = threading.Event()
        self.peak_mib = 0
        self.errors = 0
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()
        return self

    def _sample(self):
        while not self.stop.is_set():
            try:
                output = subprocess.check_output(
                    ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                    text=True, timeout=5)
                self.peak_mib = max(self.peak_mib, int(output.splitlines()[0]))
            except (OSError, ValueError, subprocess.SubprocessError):
                self.errors += 1
            self.stop.wait(0.2)

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=6)
