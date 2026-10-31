"""One-shot, research-only, fixed-ASR attribution ablation on open J-CRe3.

The 3 public recordings are ACTED HOUSEHOLD DIALOGUE, NOT MEETINGS.
They have already been used for research: developmental diagnostics ONLY.
Source text/audio are never included in output/logs or committed to GitHub.
"""
import modal
from pathlib import Path

if modal.is_local():
    from modal_qwen_quality_ablation import image
else:
    image=modal.Image.debian_slim(python_version="3.11")

APP_NAME="kiroku-open-audio-decomposition-20261031-01"
VOLUME="kiroku-open-audio-decomposition-20261031-01"
app=modal.App(APP_NAME)
inputs=modal.Volume.from_name(VOLUME,create_if_missing=True)
weights=modal.Volume.from_name("meeting-transcriber-models-v1",create_if_missing=False)


@app.function(image=image,gpu="A10",cpu=2,memory=12288,timeout=600,
              max_containers=1,scaledown_window=2,retries=0,
              single_use_containers=True,
              volumes={"/inputs":inputs,"/models":weights},
              secrets=[modal.Secret.from_name("transcriber-hf",
                                             required_keys=["HF_TOKEN"])])
def evaluate():
    import gc,hashlib,json,os,subprocess,tempfile,time,zipfile
    import numpy as np
    import torch
    import soundfile as sf
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks
    from transcriber.processor import Config
    from transcriber.diarization import diarize
    from scripts.jcre3_reference import load_reference
    from scripts.qwen_chunk_retry import infer_chunk
    from scripts.qwen_short_tail import coalesce_short_tail
    from scripts.qwen_timing_bridge import attribute_qwen,qwen_segments
    from scripts.qwen_error_decomposition import compare_arms,mark_qwen_timing_origins
    from scripts.evaluate_asr_cer import evaluate as evaluate_cer
    from scripts.evaluate_attributed_transcript import permutation_cer

    start=time.perf_counter()
    archive_path=Path("/inputs/eval.zip")
    if not archive_path.is_file() or archive_path.stat().st_size>10*1024*1024:
        raise ValueError("Expected licensed pinned private input package")
    report=[]
    with zipfile.ZipFile(archive_path) as archive:
        manifest=json.loads(archive.read("manifest.json"))
        if manifest.get("license")!="CC BY-SA 4.0" or len(manifest["records"])!=3:
            raise ValueError("Unexpected source/license")
        jobs=[]
        with tempfile.TemporaryDirectory(prefix="kiroku-open-decomposition-") as directory:
            root=Path(directory)
            for item in manifest["records"]:
                row={"record_id":item["id"],"status":"error"}
                report.append(row)
                try:
                    audio=archive.read(item["id"]+"/preview.mp3")
                    human=archive.read(item["id"]+"/reference.txt")
                    if (hashlib.sha256(audio).hexdigest()!=item["audio_sha256"]
                        or hashlib.sha256(human).hexdigest()!=item["reference_sha256"]):
                        raise ValueError("Audio/reference SHA mismatch")
                    reference,_=load_reference(human)
                    out=root/item["id"];out.mkdir()
                    mp3=out/"clip.mp3";mp3.write_bytes(audio)
                    wav=out/"mono.wav"
                    subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                         "-i",str(mp3),"-ar","16000","-ac","1",
                         "-c:a","pcm_s16le",str(wav)],check=True,timeout=60)
                    wave,sr=sf.read(wav,dtype="float32")
                    seconds=len(wave)/sr
                    if sr!=16000 or wave.ndim!=1 or not 30<=seconds<=240:
                        raise ValueError("Invalid pilot audio")
                    config=Config(enable_diarization=True,language="ja",
                                  expected_speakers=2,overlap_review=True,
                                  quality_experiment=True)
                    dj={"path":mp3,"sha256":item["audio_sha256"],
                        "outdir":out,"prefix":"pilot"}
                    diarize(dj,config,os.environ["HF_TOKEN"],{})
                    exclusive=dj["diar_segments"]
                    standard_path=out/"pyannote_通常話者区間.json"
                    regular=json.loads(standard_path.read_text())["segments"]
                    speech_end=min(seconds,max(v["end"] for v in exclusive))
                    jobs.append((row,wave,seconds,reference,exclusive,regular,speech_end))
                    row.update({"source_sha256":item["audio_sha256"],
                                "reference_sha256":item["reference_sha256"],
                                "audio_seconds":round(seconds,3)})
                except Exception as error:
                    row["failure_stage"]="source_and_diarization"
                    row["failure_class"]=type(error).__name__
            if len(jobs)!=3:
                return {"completed":False,"records":report,
                        "warning":"Incomplete source data. No partial improvement claim."}

            model=Qwen3ASRModel.from_pretrained(
                "Qwen/Qwen3-ASR-1.7B",dtype=torch.bfloat16,device_map="cuda:0",
                attn_implementation="sdpa",max_inference_batch_size=1,
                max_new_tokens=512,
                forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B",
                forced_aligner_kwargs={"dtype":torch.bfloat16,
                    "device_map":"cuda:0","attn_implementation":"sdpa"})
            for row,wave,seconds,reference,exclusive,regular,speech_end in jobs:
                try:
                    chunks=split_audio_into_chunks(
                        np.asarray(wave,dtype=np.float32),
                        sr=16000,max_chunk_sec=30.)
                    chunks=coalesce_short_tail(wave,chunks)
                    collected=[]
                    for part,offset in chunks:
                        segments,_=infer_chunk(
                            model,np.asarray(part,dtype=np.float32),float(offset))
                        collected.extend(segments)
                    baseline,integrity=attribute_qwen(
                        collected,exclusive,seconds,
                        speech_end_seconds=speech_end)
                    segmented,_=qwen_segments(
                        collected,seconds,speech_end_seconds=speech_end)
                    segmented=mark_qwen_timing_origins(collected,segmented,seconds)
                    comparison=compare_arms(
                        reference,segmented,exclusive,regular=regular,oracle=True)
                    direct=permutation_cer(reference,baseline)
                    flattened=evaluate_cer(
                        "".join(t["text"] for t in reference),
                        "".join(c["text"] for c in collected))
                    arms={k:{"cpcer":v["cpcer"],
                             "edit_distance":v["edit_distance"],
                             "abstained_normalized_characters":v.get(
                                 "abstained_normalized_characters"),
                             "review_word_count":v.get("review_word_count"),
                             "timing_origin_counts":v.get("timing_origin_counts")}
                          for k,v in comparison["arms"].items()}
                    row.update({"status":"success",
                        "baseline_original_cpcer":direct["cpcer"],
                        "baseline_original_edits":direct["edit_distance"],
                        "reference_chars":direct["reference_characters"],
                        "flattened_cer":flattened["normalized_cer"],
                        "tokens":integrity["aligned_tokens"],
                        "arms":arms,
                        "attribution_content_fixed":True})
                except Exception as exc:
                    row.update({"failure_stage":"qwen_attribution_decomposition",
                                "failure_class":type(exc).__name__})
                finally:
                    gc.collect()
            del model
            torch.cuda.empty_cache()
    return {"completed":all(r["status"]=="success" for r in report),
        "dataset":"J-CRe3 (ACTED HOUSEHOLD DIALOGUE, NOT REAL MEETING)",
        "license":"CC BY-SA 4.0",
        "previously_development_data":True,
        "reference_is_human":True,
        "audio_format":"official transcoded Box preview MP3",
        "model":"Qwen3-ASR-1.7B + ForcedAligner-0.6B + Community-1",
        "gpu_function_seconds":round(time.perf_counter()-start,3),
        "records":report,
        "human_edit_time_minutes":None,
        "warning":"No unseen real meeting, no edit-time observer, no release acceptance."}


@app.local_entrypoint()
def main(output:str):
    import json
    result=evaluate.remote()
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("OPEN_AUDIO_ATTRIBUTION_METRICS "+json.dumps(result,ensure_ascii=False))
