"""Isolated A10 research: same Qwen weights, 30/15/45 s energy-aware chunks.

One voice sample per GPU job. Qwen, ForcedAligner, Community-1 are loaded
once per sample. No text or reference audio is logged or persisted in artifacts.
NEVER deploy; invoke with 'modal run' from the guarded research workflow only.
"""
from pathlib import Path
import modal

app=modal.App("kiroku-qwen-fixed-weights-quality-research")
# Existing cache is reused, no deletes or volume.commit; other Modal apps untouched.
weights=modal.Volume.from_name("meeting-transcriber-models-v1",create_if_missing=False)
image=(modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg","libsndfile1")
    .pip_install_from_requirements("requirements-modal.lock",
      extra_index_url="https://download.pytorch.org/whl/cu128")
    .pip_install("qwen-asr==0.0.6","nagisa==0.2.11","rapidfuzz==3.14.3")
    .run_commands(
      "python -c \"import pathlib,site; p=pathlib.Path(site.getsitepackages()[0])/'nvidia'; pathlib.Path('/etc/ld.so.conf.d/99-transcriber.conf').write_text('\\n'.join(str(d) for d in p.glob('*/lib')))\"",
      "ldconfig","python -m pip check")
    .env({"HF_HOME":"/models/hf","HF_HUB_CACHE":"/models/hf/hub",
          "HF_HUB_DISABLE_TELEMETRY":"1","PYANNOTE_METRICS_ENABLED":"0"})
    .add_local_python_source("beta","transcriber","scripts"))


@app.function(image=image,gpu="A10",cpu=2,memory=8192,
              volumes={"/models":weights},timeout=600,
              max_containers=1,scaledown_window=2,single_use_containers=True,retries=0,
              secrets=[modal.Secret.from_name("transcriber-hf",required_keys=["HF_TOKEN"])])
def screen_record(audio_bytes:bytes,truth_bytes:bytes,expected_sha:str,
                  record_id:str,mode:str="screen",alternative_audio_bytes:bytes=b""):
    import hashlib, os, subprocess, tempfile, time
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks
    from transcriber.processor import Config
    from transcriber.diarization import diarize
    from scripts.qwen_chunk_retry import infer_chunk
    from scripts.qwen_boundary_context import context_window, own_aligned_tokens
    from scripts.qwen_timing_bridge import attribute_qwen
    from scripts.evaluate_attributed_transcript import permutation_cer
    from scripts.eval_elan_ja import load_elan
    from scripts.qwen_quality_experiments import (
        edit_components,oracle_exclusive_intervals,diagnose_review_candidates)
    if record_id not in ("01","05","08") or mode not in ("screen","boundary","longchunk","pcm"):
        raise ValueError("Unsupported preregistered research record")
    if hashlib.sha256(truth_bytes).hexdigest()!=expected_sha:
        raise ValueError("ELAN reference changed")
    if not (0<len(audio_bytes)<=20*1024*1024 and len(truth_bytes)<4*1024*1024):
        raise ValueError("Unexpected data sizes")
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="fixed-qwen-research-") as directory:
        root=Path(directory)
        audio=root/"reference.mp3"
        eaf=root/"reference.eaf"
        audio.write_bytes(audio_bytes)
        eaf.write_bytes(truth_bytes)
        reference,sha=load_elan(eaf)
        assert sha==expected_sha
        pcm=root/"reference.wav"
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-nostdin",
                        "-y","-i",str(audio),"-ar","16000","-ac","1",
                        "-c:a","pcm_s16le",str(pcm)],check=True,timeout=120)
        signal,sr=sf.read(pcm,dtype="float32",always_2d=False)
        if sr!=16000 or signal.ndim!=1:
            raise ValueError("Not 16k mono")
        alternative=None
        if mode=="pcm":
            if not 0<len(alternative_audio_bytes)<=25*1024*1024:
                raise ValueError("Unexpected lossless audio size")
            lossless=root/"alternative.flac"
            lossless.write_bytes(alternative_audio_bytes)
            alternative,alternative_sr=sf.read(lossless,dtype="float32",always_2d=False)
            if alternative_sr!=sr or alternative.ndim!=1 or len(alternative)!=len(signal):
                raise ValueError("Lossless input must have identical sample count and rate")
        duration=len(signal)/sr
        if not 300<=duration<=1300:
            raise ValueError("Outside bounded pilot duration")
        config=Config(enable_diarization=True,language="ja",
                      expected_speakers=2,overlap_review=True)
        job={"path":audio,"sha256":hashlib.sha256(audio_bytes).hexdigest(),
             "outdir":root/"diarization","prefix":"research"}
        job["outdir"].mkdir()
        diar_metrics={}
        t=time.perf_counter()
        diarize(job,config,os.environ["HF_TOKEN"],diar_metrics)
        diar_total=time.perf_counter()-t
        automatic=job["diar_segments"]
        oracle,overlap_ambig_seconds=oracle_exclusive_intervals(reference,duration)
        if not automatic or not oracle:
            raise ValueError("No diarization")
        t=time.perf_counter()
        model=Qwen3ASRModel.from_pretrained(
            "Qwen/Qwen3-ASR-1.7B",dtype=torch.bfloat16,device_map="cuda:0",
            attn_implementation="sdpa",max_inference_batch_size=1,max_new_tokens=512,
            forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B",
            forced_aligner_kwargs={"dtype":torch.bfloat16,"device_map":"cuda:0",
                                   "attn_implementation":"sdpa"})
        model_load=time.perf_counter()-t
        reference_text="".join(x["text"] for x in reference)
        findings=[]
        # Keep baseline first. 45 s can hit token-generation caps: fail is recorded, not suppressed.
        variants=([(30,0.0),(30,1.0)] if mode=="boundary" else
                  [(30,0.0),(45,0.0)] if mode=="longchunk" else
                  [(30,0.0),(30,0.0)] if mode=="pcm" else
                  [(30,0.0),(15,0.0),(45,0.0)])
        for condition_index,(seconds,padding) in enumerate(variants):
            name=("candidate_boundary_1s" if padding else
                  "baseline_30" if seconds==30 else "candidate_"+str(seconds))
            if mode=="pcm" and condition_index==1:
                name="candidate_lossless_pcm"
            item={"max_chunk_seconds":seconds,"boundary_padding_seconds":padding,"name":name}
            begin=time.perf_counter()
            stage="chunking"
            try:
                chunks=split_audio_into_chunks(np.asarray(signal,dtype=np.float32),
                    sr=16000,max_chunk_sec=float(seconds))
                if not chunks or len(chunks)>240:
                    raise ValueError("Invalid chunk count")
                collected=[]
                retries=0
                discarded=0
                stage="asr_alignment"
                for index,(chunk,offset) in enumerate(chunks):
                    core=None
                    if mode=="pcm" and condition_index==1:
                        start=round(float(offset)*sr)
                        chunk=alternative[start:start+len(chunk)]
                    if padding:
                        chunk,offset,core=context_window(signal,float(offset),len(chunk),padding=padding)
                    aligned,meta=infer_chunk(model,np.asarray(chunk,dtype=np.float32),
                        float(offset),max_retries=2,
                        max_chunk_seconds=50 if seconds==45 else 38)
                    if core is not None:
                        aligned,count=own_aligned_tokens(aligned,core,final=index==len(chunks)-1)
                        discarded+=count
                    collected.extend(aligned)
                    retries+=meta["retries"]
                stage="attribution"
                utterances,integrity=attribute_qwen(collected,automatic,duration,
                                                     max_chunk_seconds=50 if seconds==45 else 38)
                oracle_rows,_=attribute_qwen(collected,oracle,duration,
                                               max_chunk_seconds=50 if seconds==45 else 38)
                all_text="".join(row["text"] for row in collected)
                # This aggregate CER is time-flattened; the reference contains overlapping
                # simultaneous talk and is not a clean per-speaker ASR upper bound.
                stage="evaluation"
                cer=edit_components(reference_text,all_text)
                cpcer=permutation_cer(reference,utterances)
                oracle_cpcer=permutation_cer(reference,oracle_rows)
                review=diagnose_review_candidates(utterances)
                item.update({
                  "status":"success",
                  "chunks":len(chunks),
                  "context_tokens_outside_core":discarded,
                  "bounded_retry_count":retries,
                  "cpcer":cpcer["cpcer"],
                  "cpcer_edits":cpcer["edit_distance"],
                  "oracle_diarization_cpcer_diagnostic":oracle_cpcer["cpcer"],
                  "flattened_cer":cer["cer"],
                  "flattened_insertions":cer["insertions"],
                  "flattened_deletions":cer["deletions"],
                  "flattened_substitutions":cer["substitutions"],
                  "hypothesis_characters":cer["hypothesis_characters"],
                  "aligned_tokens":integrity["aligned_tokens"],
                  "tail_coverage_seconds":integrity["final_word_end_seconds"],
                  "estimated_speakers":integrity["speaker_count"],
                  "review_candidate_utterances":len(review),
                  "review_candidate_reason_counts":{
                    reason:sum(reason in v["reasons"] for v in review)
                    for reason in ("long_low_text","important_number",
                                   "speaker_boundary_review","long_gap_review",
                                   "timestamp_overlap_review")}
                })
            except Exception as exc:
                # Exception content might contain transcribed speech; do not log.
                item["status"]="failed"
                item["error_class"]=type(exc).__name__
                item["failure_stage"]=stage
            item["inference_and_eval_seconds"]=time.perf_counter()-begin
            findings.append(item)
        result={
          "record_id":record_id,"experiment_mode":mode,
          "alternative_audio_sha256":hashlib.sha256(alternative_audio_bytes).hexdigest() if alternative_audio_bytes else None,
          "audio_sha256":hashlib.sha256(audio_bytes).hexdigest(),
          "reference_eaf_sha256":expected_sha,"audio_seconds":duration,
          "reference_characters":len(reference_text),
          "reference_speakers":len(set(x["speaker_id"] for x in reference)),
          "oracle_overlap_ambiguous_seconds":round(overlap_ambig_seconds,3),
          "diarization_seconds":diar_total,
          "diarization_inference_seconds":diar_metrics.get("diarization_inference_seconds"),
          "model_load_seconds":model_load,
          "gpu_function_seconds":time.perf_counter()-started,
          "conditions":findings,
          "model":"Qwen/Qwen3-ASR-1.7B","aligner":"Qwen/Qwen3-ForcedAligner-0.6B",
          "diarization":"pyannote Community-1 exclusive; two speakers fixed",
          "qwen_asr_version":"0.0.6",
          "experiment_scope":"research-only; same input for all variants; no commercial acceptance",
          "license":"IngCrowd CC BY-NC 4.0 noncommercial research only",
        }
    return result


@app.local_entrypoint()
def main(audio:str,eaf:str,record_id:str,output:str,mode:str="screen",alternative_audio:str=""):
    import hashlib,json,datetime, time
    references={
       "01":"c59daa71d0ffa34e50b4c532d33f5c0d2a51ceaa8aea4435a68a87d924f61b32",
       "05":"e728b5e9cc74c91dfc2541dee1a404f98e3ff1b71b744512e4622d57a7",
       "08":"36aaf89d33163770e0cbf8310245437a1d9da5f4d779416e2507917a1547392c"}
    if record_id not in references:
       raise ValueError("Record ID not preregistered")
    pcm=Path(audio).read_bytes()
    human=Path(eaf).read_bytes()
    if hashlib.sha256(human).hexdigest()!=references[record_id]:
       raise ValueError("Unexpected reference SHA")
    alternative=Path(alternative_audio).read_bytes() if alternative_audio else b""
    result=screen_record.remote(pcm,human,references[record_id],record_id,mode,alternative)
    # Numeric and hashes only. Never return text or raw audio to CI.
    dest=Path(output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("QWEN_SCREEN_RESULT",json.dumps({
       "record_id":record_id,"condition_scores":[
           {"name":x["name"],"cpcer":x.get("cpcer"),
            "status":x["status"],"seconds":round(x["inference_and_eval_seconds"],2)}
           for x in result["conditions"]]},
       ensure_ascii=False))
