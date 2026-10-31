"""One-shot A10 J-CRe3 real-audio boundary ablation, RESEARCH ONLY.

Same licensed public Box preview MP3 and human ELAN as pilot PR #6.
Audio/text live solely in temporary Modal volume + GPU memory; result
contains numbers only. Human turns provide *automatic diagnostic proxy*,
not independently verified display-boundary gold labels.
"""
from pathlib import Path
import modal

if modal.is_local():
    from modal_qwen_quality_ablation import image
else:
    image=modal.Image.debian_slim(python_version="3.11")

APP_NAME="kiroku-jcre3-fourarm-real-20261031-01"
VOLUME_NAME="kiroku-jcre3-fourarm-audio-20261031-01"
app=modal.App(APP_NAME)
inputs=modal.Volume.from_name(VOLUME_NAME,create_if_missing=True)
weights=modal.Volume.from_name("meeting-transcriber-models-v1",create_if_missing=False)


@app.function(image=image,gpu="A10",cpu=2,memory=12288,
              volumes={"/inputs":inputs,"/models":weights},
              timeout=600,max_containers=1,scaledown_window=2,
              retries=0,single_use_containers=True,
              secrets=[modal.Secret.from_name("transcriber-hf",required_keys=["HF_TOKEN"])])
def evaluate():
    import gc,hashlib,json,os,statistics,subprocess,tempfile,time,zipfile
    import numpy as np
    import soundfile as sf
    import torch
    from pathlib import Path
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from transcriber.processor import Config
    from transcriber.diarization import diarize
    from scripts.jcre3_reference import load_reference
    from scripts.qwen_chunk_retry import infer_chunk
    from scripts.qwen_short_tail import coalesce_short_tail
    from scripts.qwen_timing_bridge import attribute_qwen
    from scripts.evaluate_attributed_transcript import permutation_cer
    from scripts.qwen_boundary_fourarm import (
        MODEL,audio_features,candidate_universe,evaluate_four_arms,score_four_arms)
    from scripts.jcre3_boundary_adjudication import proxy_boundaries

    started=time.perf_counter()
    zip_path=Path("/inputs/eval.zip")
    if not zip_path.is_file() or zip_path.stat().st_size > 10*1024*1024:
        raise ValueError("Missing private verified corpus")
    with zipfile.ZipFile(zip_path) as archive:
        manifest=json.loads(archive.read("manifest.json"))
        ids=("20220302-56130322-0","20220303-56130205-1","20220304-56132112-1")
        if (manifest["license"]!="CC BY-SA 4.0" or
                tuple(record["id"] for record in manifest["records"])!=ids):
            raise ValueError("Unexpected J-CRe3 source revision or records")
        names={"manifest.json","ATTRIBUTION.txt"}|{
            f"{i}/{name}" for i in ids for name in ("preview.mp3","reference.txt")}
        if set(archive.namelist())!=names:
            raise ValueError("Unexpected archive contents")
        unpacked=[(r,archive.read(r["id"]+"/preview.mp3"),
                      archive.read(r["id"]+"/reference.txt"))
                  for r in manifest["records"]]
    prepared=[]
    report=[]
    with tempfile.TemporaryDirectory(prefix="boundary-fourarm-jcre3-") as temp:
        base=Path(temp)
        # Diarization and original waveform preparation from the real audio.
        for record,audio_data,reference_data in unpacked:
            entry={"record_id":record["id"],"status":"failed"}
            report.append(entry)
            try:
                if (hashlib.sha256(audio_data).hexdigest()!=record["audio_sha256"]
                        or hashlib.sha256(reference_data).hexdigest()!=record["reference_sha256"]):
                    raise ValueError("Source SHA mismatch")
                reference,_=load_reference(reference_data)
                out=base/record["id"];out.mkdir()
                mp3=out/"audio.mp3";mp3.write_bytes(audio_data)
                wav=out/"mono.wav"
                subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
                    "-i",str(mp3),"-ar","16000","-ac","1","-c:a","pcm_s16le",str(wav)],
                    check=True,timeout=60)
                signal,sr=sf.read(wav,dtype="float32")
                duration=len(signal)/sr
                if sr!=16000 or signal.ndim!=1 or not 30<=duration<=240:
                    raise ValueError("Invalid pilot waveform")
                config=Config(enable_diarization=True,language="ja",
                              expected_speakers=2,overlap_review=True)
                job={"path":mp3,"sha256":record["audio_sha256"],
                     "outdir":out,"prefix":"pilot"}
                t=time.perf_counter()
                diarize(job,config,os.environ["HF_TOKEN"],{})
                automatic=job["diar_segments"]
                speech_end=max(float(v["end"]) for v in automatic)
                entry["diarization_seconds"]=round(time.perf_counter()-t,3)
                entry["audio_seconds"]=round(duration,3)
                prepared.append((entry,signal,reference,automatic,duration,speech_end))
            except Exception as exc:
                entry["failure_class"]=type(exc).__name__
                entry["failure_stage"]="decode_or_diarization"
        if len(prepared)!=3:
            return {"all_completed":False,"recording_count":3,"records":report,
                    "warning":"Failed before ASR; no artificial replacement audio."}

        # First-stage Qwen/ForcedAligner is FROZEN to the PR #6 specification.
        t=time.perf_counter()
        asr=Qwen3ASRModel.from_pretrained(
            "Qwen/Qwen3-ASR-1.7B",dtype=torch.bfloat16,
            device_map="cuda:0",attn_implementation="sdpa",
            max_inference_batch_size=1,max_new_tokens=512,
            forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B",
            forced_aligner_kwargs={"dtype":torch.bfloat16,
                "device_map":"cuda:0","attn_implementation":"sdpa"})
        asr_load_seconds=time.perf_counter()-t
        processed=[]
        for entry,signal,reference,automatic,duration,speech_end in prepared:
            t=time.perf_counter()
            try:
                chunks=split_audio_into_chunks(np.asarray(signal,dtype=np.float32),
                                                sr=16000,max_chunk_sec=30.)
                chunks=coalesce_short_tail(signal,chunks)
                collected=[]
                for chunk,offset in chunks:
                    rows,meta=infer_chunk(asr,np.asarray(chunk,dtype=np.float32),
                                          float(offset))
                    collected.extend(rows)
                utterances,integrity=attribute_qwen(
                    collected,automatic,duration,
                    speech_end_seconds=min(duration,speech_end))
                cp=permutation_cer(reference,utterances)
                entry.update({"first_stage_pass":True,
                              "qwen_cpcer":cp["cpcer"],
                              "utterances":len(utterances),
                              "reference_turns":len(reference),
                              "aligned_tokens":integrity["aligned_tokens"],
                              "asr_seconds":round(time.perf_counter()-t,3)})
                processed.append((entry,utterances,signal,reference))
            except Exception as exc:
                entry.update({"failure_stage":"asr_alignment",
                              "failure_class":type(exc).__name__})
        del asr
        gc.collect()
        torch.cuda.empty_cache()
        if len(processed)!=3:
            return {"all_completed":False,"recording_count":3,"records":report,
                    "warning":"One or more baseline ASR runs failed; no partial victory."}

        t=time.perf_counter()
        tokenizer=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=False)
        llm=AutoModelForCausalLM.from_pretrained(
            MODEL,torch_dtype=torch.bfloat16,device_map="auto",trust_remote_code=False)
        llm.eval()
        llm_load_seconds=time.perf_counter()-t

        def infer(arm,messages):
            serialized=tokenizer.apply_chat_template(
                messages,tokenize=False,add_generation_prompt=True)
            inputs=tokenizer(serialized,return_tensors="pt").to(llm.device)
            with torch.inference_mode():
                out=llm.generate(**inputs,max_new_tokens=110,
                                 do_sample=False,pad_token_id=tokenizer.eos_token_id)
            return tokenizer.decode(
                out[0][inputs["input_ids"].shape[-1]:],skip_special_tokens=True)

        for entry,utterances,signal,reference in processed:
            t=time.perf_counter()
            try:
                # Frozen candidate universe BEFORE any human reference is consulted.
                candidates=candidate_universe(utterances)
                features=audio_features(signal,16000,utterances,candidates)
                comparisons=evaluate_four_arms(utterances,infer,features=features)
                # Human turn-alignment is only a diagnostic proxy, NOT human
                # listening verification and not an actual test-set label.
                provisional=proxy_boundaries(reference,utterances,candidates)
                scored=score_four_arms(comparisons,provisional)
                entry.update({
                    "status":"success",
                    "candidate_count":len(candidates),
                    "candidate_coverage":(len(candidates)/(len(utterances)-1)
                                          if len(utterances)>1 else None),
                    "proxy_uncertain":sum(x=="uncertain" for x in provisional.values()),
                    "proxy_merge":sum(x=="merge" for x in provisional.values()),
                    "proxy_keep":sum(x=="keep" for x in provisional.values()),
                    "arms":scored,
                    "human_boundary_gold":False,
                    "source_text_and_speakers_preserved":True,
                    "fourarm_seconds":round(time.perf_counter()-t,3)})
            except Exception as exc:
                entry.update({"status":"failed","failure_stage":"fourarm",
                              "failure_class":type(exc).__name__})
        del llm
        torch.cuda.empty_cache()
        return {
            "recording_count":3,"all_completed":all(r["status"]=="success" for r in report),
            "model_first":"Qwen/Qwen3-ASR-1.7B (unchanged)",
            "model_second":MODEL,
            "dataset":"J-CRe3 CC BY-SA 4.0 (Box preview MP3; household acted dialogues)",
            "source_revision":manifest["revision"],
            "asr_load_seconds":round(asr_load_seconds,3),
            "llm_load_seconds":round(llm_load_seconds,3),
            "gpu_function_seconds":round(time.perf_counter()-started,3),
            "records":report,
            "commercial_ready":False,
            "warning":"ELAN-derived boundary proxy is NOT independently adjudicated display-boundary gold. No real meeting or multi-reviewer scoring."}


@app.local_entrypoint()
def main(output:str):
    import json
    result=evaluate.remote()
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    # Public logs: bounded numeric JSON, no recognized human text or audio.
    print("JCRE3_FOURARM_NUMERIC_RESULT "+json.dumps(result,ensure_ascii=False))
