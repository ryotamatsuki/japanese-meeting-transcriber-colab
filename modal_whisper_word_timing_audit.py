"""One-shot J-CRe3 Whisper large-v3 × Community-1 timing audit, research only.

Public CC BY-SA 4.0 acted two-person household conversations, NOT real meetings.
Input archive stored only in dedicated private Modal Volume; output metric-only.
Never deploy the model service or expose an endpoint. No user jobs accessed.
"""
from pathlib import Path
import modal

from beta_modal_anonymous import gpu_image
image=gpu_image.add_local_python_source('scripts')
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
                    result=evaluate(ref,job["asr_segments"],job["diar_segments"],
                                    duration=duration)
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
