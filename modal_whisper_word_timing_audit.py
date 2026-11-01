"""One-shot J-CRe3 Whisper large-v3 × Community-1 timing audit, research only.

Public CC BY-SA 4.0 acted two-person household conversations, NOT real meetings.
Input archive stored only in dedicated private Modal Volume; output metric-only.
Never deploy the model service or expose an endpoint. No user jobs accessed.
"""
from pathlib import Path
import modal

# Keep the audit image self-contained. Importing beta_modal_anonymous at GPU
# startup couples this one-shot task to another Modal app and its source files.
# Reuse its pinned CUDA/torch/pyannote requirements and ldconfig setup, but
# mount only the explicitly required packages, including beta.core used by evaluation.
image=(modal.Image.debian_slim(python_version='3.11')
    .apt_install('ffmpeg','libsndfile1')
    .pip_install_from_requirements('requirements-modal.lock',extra_index_url='https://download.pytorch.org/whl/cu128')
    .run_commands(
        "python -c \"import pathlib,site; p=pathlib.Path(site.getsitepackages()[0])/'nvidia'; "
        "pathlib.Path('/etc/ld.so.conf.d/99-transcriber.conf').write_text('\\n'.join(str(d) for d in p.glob('*/lib')))\"",
        'ldconfig','python -m pip check')
    .env({'HF_HOME':'/models/hf','HF_HUB_CACHE':'/models/hf/hub',
          'HF_HUB_DISABLE_TELEMETRY':'1','PYANNOTE_METRICS_ENABLED':'0'})
    .add_local_python_source('beta','transcriber','scripts'))
APP_NAME="kiroku-whisper-timing-audit-20261101"
VOLUME_NAME="kiroku-whisper-timing-audit-inputs-20261101"
app=modal.App(APP_NAME)
inputs=modal.Volume.from_name(VOLUME_NAME,create_if_missing=True)
weights=modal.Volume.from_name("meeting-transcriber-models-v1",create_if_missing=False)


@app.function(image=image,gpu="A10",cpu=2,memory=12288,timeout=900,
              max_containers=1,scaledown_window=2,retries=0,
              single_use_containers=True,
              volumes={"/inputs":inputs,"/models":weights},
              secrets=[modal.Secret.from_name("transcriber-hf",required_keys=["HF_TOKEN"])])
def run_audit():
    import gc,hashlib,json,os,tempfile,time,zipfile
    from transcriber.processor import Config
    from transcriber.asr import transcribe
    from transcriber.diarization import diarize
    from scripts.jcre3_reference import load_reference
    from scripts.whisper_speaker_timing_audit import evaluate

    archive_path=Path("/inputs/eval.zip")
    if not archive_path.is_file() or not 1_000_000<archive_path.stat().st_size<8_000_000:
        raise ValueError("Private licensed input archive is missing or wrong size")
    started=time.perf_counter()
    rows=[]
    with zipfile.ZipFile(archive_path) as archive:
        manifest=json.loads(archive.read("manifest.json"))
        if manifest.get("license")!="CC BY-SA 4.0" or len(manifest.get("records",[]))!=3:
            raise ValueError("Only pinned original J-CRe3 source permitted")
        with tempfile.TemporaryDirectory(prefix="kiroku-whisper-audit-") as d:
            for item in manifest["records"]:
                row={"record_id":item["id"],"status":"failed"}
                rows.append(row)
                try:
                    original=archive.read(item["id"]+"/preview.mp3")
                    human=archive.read(item["id"]+"/reference.txt")
                    if (hashlib.sha256(original).hexdigest()!=item["audio_sha256"]
                        or hashlib.sha256(human).hexdigest()!=item["reference_sha256"]):
                        raise ValueError("Source SHA mismatch")
                    ref,_=load_reference(human)
                    root=Path(d)/item["id"]
                    root.mkdir()
                    audio=root/"input.mp3"
                    audio.write_bytes(original)
                    config=Config(enable_diarization=True,expected_speakers=2,
                                  language="ja",quality_experiment=True,
                                  overlap_review=True,asr_beam_size=5,
                                  asr_model="large-v3",word_stability_ms=0)
                    job={"path":audio,"sha256":item["audio_sha256"],"outdir":root,
                         "prefix":"audit"}
                    asr_metrics={}
                    start=time.perf_counter()
                    transcribe(job,config,Path("/models/whisper"),asr_metrics)
                    asr_seconds=time.perf_counter()-start
                    start=time.perf_counter()
                    diarize(job,config,os.environ["HF_TOKEN"],{})
                    diar_seconds=time.perf_counter()-start
                    # J-CRe3 preview audio duration is provided by Whisper decoding.
                    duration=float(asr_metrics["audio_seconds"])
                    regular_path=root/"pyannote_通常話者区間.json"
                    if not regular_path.is_file():
                        raise ValueError("Community-1 Regular regions required for safe repair")
                    regular=json.loads(regular_path.read_text(encoding="utf-8"))["segments"]
                    result=evaluate(ref,job["asr_segments"],job["diar_segments"],
                                    duration=duration,regular=regular)
                    # Audit text must never enter GitHub metadata or stdout.
                    row.update({"status":"success",
                                "audio_seconds":round(duration,3),
                                "asr_seconds":round(asr_seconds,3),
                                "diarization_seconds":round(diar_seconds,3),
                                **result})
                except BaseException as error:
                    row["failure_class"]=type(error).__name__
                    row["failure_stage"]="whisper_diarization_or_attribution"
                gc.collect()
    done=len(rows)==3 and all(r["status"]=="success" for r in rows)
    return {"completed":done,"dataset":"J-CRe3 previously examined development corpus",
            "model":"faster-whisper large-v3 beam5 VAD550ms + pyannote Community-1 Exclusive 2spk",
            "audio":"official Box preview MP3, not original WAV",
            "human_reference":"turn-level J-CRe3 annotations, NOT word-level timing truth",
            "provenance":"2026-11-01 research-only; exact manifest SHA validation",
            "gpu_function_seconds":round(time.perf_counter()-started,3),
            "rows":rows,"release":"NO-GO until independent real meetings and manual word alignment"}


# Run this inexpensive readiness probe before repeating the full 3-record A10
# evaluation. It cannot access source transcript contents and makes no writes.
@app.function(image=image,gpu="A10",cpu=2,memory=12288,timeout=180,
              max_containers=1,scaledown_window=2,retries=0,
              single_use_containers=True,
              volumes={"/inputs":inputs,"/models":weights},
              secrets=[modal.Secret.from_name("transcriber-hf",required_keys=["HF_TOKEN"])])
def startup_probe():
    import os
    import torch
    from transcriber.processor import Config
    from faster_whisper import WhisperModel
    from pyannote.audio import Pipeline
    from scripts.jcre3_reference import load_reference
    from scripts.whisper_speaker_timing_audit import evaluate
    return {
        "cuda_available":bool(torch.cuda.is_available()),
        "research_archive_mounted":Path("/inputs/eval.zip").is_file(),
        "model_volume_mounted":Path("/models").is_dir(),
        "hf_secret_present":bool(os.environ.get("HF_TOKEN")),
        "research_imports_ok":all((Config,WhisperModel,Pipeline,load_reference,evaluate)),
    }


@app.local_entrypoint()
def startup_check():
    result=startup_probe.remote()
    if not all(result.values()):
        raise RuntimeError("Research GPU startup failed a resource/import check")
    print("WHISPER_AUDIT_GPU_STARTUP_CHECK=PASS")


@app.local_entrypoint()
def main(output:str):
    import json
    data=run_audit.remote()
    Path(output).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("WHISPER_TIMING_AUDIT",json.dumps(
        {"completed":data["completed"],
         "samples":[{"record_id":r["record_id"],"status":r["status"],
                     "reference_characters":r.get("reference_characters"),
                     "legacy_cpcer":r.get("rules",{}).get("legacy",{}).get("cpcer"),
                     "midpoint_cpcer":r.get("rules",{}).get("midpoint",{}).get("cpcer"),
                     "onset_cpcer":r.get("rules",{}).get("onset",{}).get("cpcer"),
                     "end_cpcer":r.get("rules",{}).get("end",{}).get("cpcer"),
                     "failure_class":r.get("failure_class")} for r in data["rows"]]},
        ensure_ascii=False,sort_keys=True))
    if not data["completed"]:
        raise RuntimeError("One or more research samples failed; do not claim full evaluation")
