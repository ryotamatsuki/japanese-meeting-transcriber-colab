"""Independent natural Japanese dialogue evaluation, noncommercial research only.

New IngCrowd Zoom recordings, real but NOT workplace meetings.
Separate from all previously evaluated J-CRe3.
Source text/audio are never included in output/logs or committed to GitHub.
"""
import modal
from pathlib import Path

if modal.is_local():
    from modal_qwen_quality_ablation import image
else:
    image=modal.Image.debian_slim(python_version="3.11")

APP_NAME="kiroku-ingcrowd-holdout-20261031-01"
VOLUME="kiroku-ingcrowd-holdout-20261031-01"
app=modal.App(APP_NAME)
inputs=modal.Volume.from_name(VOLUME,create_if_missing=True)
weights=modal.Volume.from_name("meeting-transcriber-models-v1",create_if_missing=False)


@app.function(image=image,gpu="A10",cpu=2,memory=12288,timeout=1200,
              max_containers=1,scaledown_window=2,retries=0,
              single_use_containers=True,
              volumes={"/inputs":inputs,"/models":weights},
              secrets=[modal.Secret.from_name("transcriber-hf",
                                             required_keys=["HF_TOKEN"])])
def freeze_qwen():
    import gc,hashlib,json,os,subprocess,tempfile,time,zipfile
    import numpy as np
    import torch
    import soundfile as sf
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks
    from transcriber.processor import Config
    from transcriber.diarization import diarize
    from scripts.ingcrowd_eaf_reference import load_ingcrowd_eaf,ALLOWED_IDS
    from scripts.qwen_chunk_retry import infer_chunk
    from scripts.qwen_short_tail import coalesce_short_tail
    from scripts.qwen_timing_bridge import attribute_qwen,qwen_segments
    from scripts.qwen_error_decomposition import compare_arms,mark_qwen_timing_origins
    from scripts.qwen_time_diarization_sensitivity import evaluate_sensitivity
    from scripts.evaluate_diarization import compare as compare_diarization
    from scripts.evaluate_asr_cer import evaluate as evaluate_cer
    from scripts.evaluate_attributed_transcript import permutation_cer

    start=time.perf_counter()
    archive_path=Path("/inputs/eval.zip")
    if not archive_path.is_file() or archive_path.stat().st_size>115*1024*1024:
        raise ValueError("Expected licensed pinned private input package")
    report=[]
    with zipfile.ZipFile(archive_path) as archive:
        manifest=json.loads(archive.read("manifest.json"))
        if manifest.get("license")!="cc-by-nc-4.0" or manifest.get("dataset")!="IngCrowd/japanese-themed-dialogue" or manifest.get("use")!="noncommercial_research_only" or tuple(x["id"] for x in manifest["records"])!=ALLOWED_IDS:
            raise ValueError("Unexpected source/license")
        jobs=[]
        with tempfile.TemporaryDirectory(prefix="kiroku-open-decomposition-") as directory:
            root=Path(directory)
            for item in manifest["records"]:
                row={"record_id":item["id"],"status":"error"}
                report.append(row)
                try:
                    audio=archive.read(item["id"]+"/"+item["id"]+"_audio.wav")
                    human=archive.read(item["id"]+"/"+item["id"]+".eaf")
                    if (hashlib.sha256(audio).hexdigest()!=item["audio_sha256"]
                        or hashlib.sha256(human).hexdigest()!=item["reference_sha256"]):
                        raise ValueError("Audio/reference SHA mismatch")
                    out=root/item["id"];out.mkdir()
                    wav=out/"mono.wav";wav.write_bytes(audio)
                    wave,sr=sf.read(wav,dtype="float32")
                    seconds=len(wave)/sr
                    if sr!=16000 or wave.ndim!=1 or not 120<=seconds<=900:
                        raise ValueError("Invalid full-length original WAV")
                    reference,meta=load_ingcrowd_eaf(human,duration=seconds)
                    config=Config(enable_diarization=True,language="ja",
                                  expected_speakers=2,overlap_review=True,
                                  quality_experiment=True)
                    dj={"path":wav,"sha256":item["audio_sha256"],
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
                    from scripts.evaluate_asr_cer import normalized_ja
                    from scripts.qwen_error_decomposition import extract_words
                    text=normalized_ja("".join(w["text"] for w in extract_words(segmented)))
                    lex_sha=hashlib.sha256(text.encode()).hexdigest()
                    direct=permutation_cer(reference,baseline)
                    if direct["reference_characters"] < 500:
                        raise ValueError("Unexpectedly short human reference")
                    der=compare_diarization(reference,exclusive,collar=0.0)
                    assert len(reference)>=4
                    rid=row["record_id"]
                    freeze={"reference":reference,
                            "qwen_segments":segmented,
                            "qwen_normalized_sha256":lex_sha,
                            "duration":seconds,"community":exclusive,
                            "pin":row["source_sha256"],
                            "baseline_edits":direct["edit_distance"],
                            "reference_chars":direct["reference_characters"],
                            "baseline_DER":der["der_percent"]}
                    private_root=Path("/inputs/frozen")
                    private_root.mkdir(exist_ok=True)
                    (private_root/(rid+".json")).write_text(
                        json.dumps(freeze,ensure_ascii=False))
                    sf.write(private_root/(rid+".wav"),wave,16000,subtype="PCM_16")
                    row.update({"status":"success",
                        "baseline_cpcer":direct["cpcer"],
                        "baseline_DER":der["der_percent"],
                        "reference_chars":direct["reference_characters"],
                        "normalized_lexical_sha256":lex_sha,
                        "tokens":integrity["aligned_tokens"],
                        "frozen_private":True})
                except Exception as exc:
                    row.update({"failure_stage":"qwen_attribution_decomposition",
                                "failure_class":type(exc).__name__})
                finally:
                    gc.collect()
            del model
            torch.cuda.empty_cache()
    if all(r["status"]=="success" for r in report):
        inputs.commit()
    return {"completed":all(r["status"]=="success" for r in report),
        "dataset":"IngCrowd spontaneous Zoom dialogue (2 speakers, NOT a workplace meeting)",
        "license":"CC BY-NC 4.0 (research-only)",
        "previously_development_data":False,
        "reference_is_human":True,
        "audio_format":"official original 16kHz PCM WAV",
        "model":"Qwen3-ASR-1.7B + ForcedAligner-0.6B + Community-1 frozen input (PRIVATE)",
        "gpu_function_seconds":round(time.perf_counter()-start,3),
        "records":report,
        "human_edit_time_minutes":None,
        "warning":"No workplace meeting, only 2 speakers. CC BY-NC noncommercial R&D only. Editing time not measured. Not a production acceptance test."}


@app.local_entrypoint()
def main(output:str):
    import json
    result=freeze_qwen.remote()
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("FROZEN_QWEN_PRIVATE_EVIDENCE_NUMERIC_ONLY "+json.dumps(result,ensure_ascii=False))
