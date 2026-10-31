"""One-off noncommercial paired ASR/diarization A10 measurement.

Uses IngCrowd CC BY-NC reference audio. Keeps user/benchmark audio and raw
transcripts out of GitHub artifacts, Modal logs and durable storage.
This deliberately never deploys or changes Kiroku Studio.
"""
from pathlib import Path
import modal

app = modal.App("kiroku-asr-paired-cost-research")
weights = modal.Volume.from_name("meeting-transcriber-models-v1", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.11")
         .apt_install("ffmpeg", "libsndfile1")
         .pip_install_from_requirements("requirements-modal.lock",
             extra_index_url="https://download.pytorch.org/whl/cu128")
         .pip_install("qwen-asr==0.0.6", "nagisa==0.2.11")
         .run_commands(
            "python -c \"import pathlib,site; p=pathlib.Path(site.getsitepackages()[0])/'nvidia'; pathlib.Path('/etc/ld.so.conf.d/99-transcriber.conf').write_text('\\n'.join(str(d) for d in p.glob('*/lib')))\"",
            "ldconfig", "python -m pip check")
         .env({"HF_HOME":"/models/hf","HF_HUB_CACHE":"/models/hf/hub",
               "HF_HUB_DISABLE_TELEMETRY":"1","PYANNOTE_METRICS_ENABLED":"0"})
         .add_local_python_source("beta", "transcriber", "scripts"))

@app.function(image=image, gpu="A10", cpu=2, memory=8192,
              volumes={"/models":weights}, timeout=1400, max_containers=1,
              scaledown_window=2, single_use_containers=True, retries=0,
              secrets=[modal.Secret.from_name("transcriber-hf", required_keys=["HF_TOKEN"])])
def compare_one(model: str, audio_bytes: bytes, eaf_bytes: bytes,
                required_audio_sha: str, required_eaf_sha: str):
    import hashlib
    import os
    import tempfile
    import time
    from transcriber.processor import Config, process
    from transcriber.qwen_web_research import transcribe_qwen_research
    from scripts.evaluate_attributed_transcript import evaluate
    if model not in ("whisper","qwen"):
        raise ValueError("Unknown model")
    if hashlib.sha256(audio_bytes).hexdigest() != required_audio_sha:
        raise ValueError("Audio checksum mismatch")
    if hashlib.sha256(eaf_bytes).hexdigest() != required_eaf_sha:
        raise ValueError("Reference checksum mismatch")
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="paired-asr-") as t:
        root = Path(t)
        audio = root / "recording.mp3"
        reference = root / "reference.eaf"
        audio.write_bytes(audio_bytes)
        reference.write_bytes(eaf_bytes)
        config = Config(enable_diarization=True, language="ja", expected_speakers=2,
                        overlap_review=False, asr_beam_size=5)
        if model == "whisper":
            archive, metrics = process(audio, root / "out", "/models/whisper",
                                       config, token=os.environ["HF_TOKEN"])
        else:
            archive, metrics = transcribe_qwen_research(
                audio, root / "out", "/models/hf", config,
                token=os.environ["HF_TOKEN"])
        scored = evaluate(reference, archive)
        weights.commit()
        result = {
            "model": model,
            "audio_sha256": required_audio_sha,
            "eaf_sha256": scored["eaf_sha256"],
            "audio_seconds": metrics.get("audio_seconds"),
            "cpcer": scored["full_cpcer"]["cpcer"],
            "reference_characters": scored["full_cpcer"]["reference_characters"],
            "hypothesis_characters": scored["full_cpcer"]["hypothesis_characters"],
            "reference_speakers": scored["full_cpcer"]["reference_speakers"],
            "predicted_speakers": scored["full_cpcer"]["hypothesis_speakers"],
            "pipeline_seconds": metrics.get("pipeline_seconds"),
            "gpu_invocation_seconds": time.perf_counter()-start,
            "model_load_seconds": metrics.get("asr_model_load_seconds", metrics.get("qwen_load_seconds")),
            "asr_inference_seconds": metrics.get("asr_inference_seconds", metrics.get("qwen_inference_seconds")),
            "diarization_inference_seconds": metrics.get("diarization_inference_seconds"),
            "overlap_review": False, "expected_speakers": 2,
        }
    return result

@app.local_entrypoint()
def main(audio: str, eaf: str, output: str="local_runs/paired_asr_cost.json"):
    import datetime as dt
    import hashlib
    import json
    from pathlib import Path
    p, ref = Path(audio), Path(eaf)
    if not p.is_file() or not ref.is_file():
        raise ValueError("Missing audio or reference")
    content, truth = p.read_bytes(), ref.read_bytes()
    if not content or len(content)>20*1024*1024 or len(truth)>4*1024*1024:
        raise ValueError("Unexpected public sample size")
    audio_hash = hashlib.sha256(content).hexdigest()
    ref_hash = hashlib.sha256(truth).hexdigest()
    expected_ref_hash = "c59daa71d0ffa34e50b4c532d33f5c0d2a51ceaa8aea4435a68a87d924f61b32"
    if ref_hash != expected_ref_hash:
        raise ValueError("Reference hash differs from preregistered public benchmark")
    # Sequential invocations make the exact same audio and EAF available to both.
    results=[]
    for model in ("whisper","qwen"):
        result=compare_one.remote(model, content, truth, audio_hash, ref_hash)
        if result["eaf_sha256"]!=ref_hash or result["audio_sha256"]!=audio_hash:
            raise ValueError("Input/ref pairing was broken")
        results.append(result)
        print("RESEARCH_MODEL_DONE",model,"cpcer",round(100*result["cpcer"],4),
              "gpu_invocation_seconds",round(result["gpu_invocation_seconds"],3))
    report={
        "experiment":"same-source-01-paied-whisper-vs-qwen",
        "time_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "data":"IngCrowd/japanese-themed-dialogue 01 (CC BY-NC 4.0; research only)",
        "input_eaf_sha256":ref_hash,
        "input_audio_sha256":audio_hash,
        "source_audio": "Identical mono MP3 16 kHz 48 kbps for both",
        "gpu":"Modal A10; CPU=2; memory=8192 MiB",
        "num_speakers":2,"diarization":"pyannote Community-1 exclusive",
        "metrics":"cpCER; lower is better; per-recording reference",
        "results":results,
        "scope":"Full pipeline; one 11-minute audio; not a product rollout",
        "cost_disclaimer":"GPU invocation seconds exclude container startup, shutdown idle, and web hosting. Not a billed cost record.",
    }
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("PAIRED_RESEARCH_PASS",json.dumps({
        "whisper_cpcer_percent":round(100*results[0]["cpcer"],3),
        "qwen_cpcer_percent":round(100*results[1]["cpcer"],3),
        "whisper_gpu_invocation_seconds":round(results[0]["gpu_invocation_seconds"],2),
        "qwen_gpu_invocation_seconds":round(results[1]["gpu_invocation_seconds"],2)
    },ensure_ascii=False))
