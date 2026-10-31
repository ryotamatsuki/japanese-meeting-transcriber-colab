"""Two-competitor NeMo diarization on frozen Qwen tokens, research only.

Private intermediate stays in the dedicated Modal volume. Numeric-only return.
Model order and 30.4s latency operating point fixed before inspection.
No default, user audio, or public Kiroku Studio code is modified.
"""
from pathlib import Path
import modal

APP_NAME="kiroku-nvidia-diarizer-headtohead-20261031-01"
VOLUME="kiroku-nvidia-diarizer-compare-20261031-01"
app=modal.App(APP_NAME)
inputs=modal.Volume.from_name(VOLUME,create_if_missing=False)

image=(modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg","libsndfile1","build-essential","git")
    .pip_install("nemo_toolkit[asr]==3.0.0",
                 "pyannote.metrics==4.0.0","soundfile>=0.13.1",
                 "numpy>=1.26.0","rapidfuzz>=3.14.0")
    .add_local_python_source("scripts","transcriber","beta")
    .env({"PYANNOTE_METRICS_ENABLED":"0","HF_HUB_DISABLE_TELEMETRY":"1"}))


@app.function(image=image,gpu="A10",cpu=4,memory=20000,
    max_containers=1,retries=0,single_use_containers=True,timeout=1200,
    scaledown_window=2,volumes={"/inputs":inputs})
def evaluate_models():
    import gc,hashlib,json,math,time
    import torch
    from pathlib import Path
    from nemo.collections.asr.models import SortformerEncLabelModel
    from scripts.diarizer_nvidia_matched_eval import (
        MODELS, SETTINGS, parse_nemo_segments, score_model,
        assert_frozen_baseline)

    ids=("20220302-56130322-0","20220303-56130205-1",
         "20220304-56132112-1")
    frozen=[]
    root=Path("/inputs/frozen")
    for rid in ids:
        pin=json.loads((root/(rid+".json")).read_text(encoding="utf8"))
        audio=root/(rid+".wav")
        if pin["pin"] not in (
            "f77a1ce6ae752db0977cf891c69408cdbfee56a293146f3d46b0f2a31707fcbd",
            "daad08e15393d3e118a7d06e3795b85b80ace4d7d32339af8d983204e41453a1",
            "f6b196ff54881daee4df022d9eb96bb143212d98a3fa306c5cdeaeb5fdd398da",
        ):
            raise ValueError("Source audio is not pinned")
        if not 0<audio.stat().st_size<16*1024*1024:
            raise ValueError("Audio missing or too large")
        from scripts.evaluate_asr_cer import normalized_ja
        from scripts.qwen_error_decomposition import extract_words
        lexical=normalized_ja("".join(w["text"] for w in
                           extract_words(pin["qwen_segments"])))
        if hashlib.sha256(lexical.encode()).hexdigest()!=pin["qwen_normalized_sha256"]:
            raise ValueError("Qwen fixed lexical sequence changed")
        original=score_model(pin["reference"],pin["qwen_segments"],
                             pin["community"],
                             original_hash=pin["qwen_normalized_sha256"])
        assert_frozen_baseline(original,pin)
        frozen.append((rid,audio,pin,original))

    report={rid:{"record_id":rid,
                "reference_chars":baseline["reference_chars"],
                "community":{
                    "cpcer":baseline["cpcer"],
                    "cpcer_edits":baseline["cpcer_edits"],
                    "DER":baseline["DER"],"JER":baseline["JER"],
                    "missed_detection_seconds":baseline["missed_detection_seconds"],
                    "speaker_confusion_seconds":baseline["speaker_confusion_seconds"],
                    "false_alarm_seconds":baseline["false_alarm_seconds"],
                    "predicted_speakers":baseline["predicted_speakers"]}}
                for rid,_,_,baseline in frozen}
    model_info={}
    for model_name in MODELS:
        start=time.perf_counter()
        try:
            model=SortformerEncLabelModel.from_pretrained(model_name)
            model=model.to("cuda").eval()
            params=model.sortformer_modules
            params.chunk_len=340
            params.chunk_right_context=40
            params.fifo_len=40
            params.spkcache_update_period=300
            params.spkcache_len=264 if "Nemotron" in model_name else 188
            if hasattr(model,"_check_streaming_parameters"):
                model._check_streaming_parameters()
            elif hasattr(params,"_check_streaming_parameters"):
                params._check_streaming_parameters()
            load_s=round(time.perf_counter()-start,3)
            model_info[model_name]={"load_seconds":load_s,
                                     "status":"loaded"}
            for rid,audio,pin,baseline in frozen:
                item=report[rid]
                t=time.perf_counter()
                try:
                    with torch.inference_mode():
                        raw=model.diarize(audio=[str(audio)],batch_size=1)
                    if not isinstance(raw,(list,tuple)) or len(raw)!=1:
                        raise ValueError("Expected one diarization sample")
                    regions=parse_nemo_segments(raw[0],
                        duration=float(pin["duration"]),model_name=model_name)
                    s=score_model(pin["reference"],pin["qwen_segments"],
                                  regions,original_hash=pin["qwen_normalized_sha256"])
                    item[model_name]={**s,"status":"success",
                        "inference_seconds":round(time.perf_counter()-t,3)}
                except Exception as exc:
                    item[model_name]={"status":"failed",
                        "error_type":type(exc).__name__}
            del model
        except Exception as exc:
            model_info[model_name]={"status":"failed",
                                    "error_type":type(exc).__name__}
            for rid in ids:
                report[rid][model_name]={"status":"failed",
                                       "error_type":type(exc).__name__}
        finally:
            gc.collect()
            torch.cuda.empty_cache()
    return {
        "dataset":"J-CRe3 prior-development acted household dialogues, NOT meetings",
        "models":list(MODELS),"training_exposure":"unknown",
        "fixed_Qwen_text_and_times":True,
        "exclusive_region_scoring":"safe maximum overlap with 1.2s nearest fallback",
        "comparison_collared_seconds":0.0,
        "score_overlap_in_DER":True,
        "model_info":model_info,
        "records":[report[i] for i in ids],
        "all_completed":all(all(report[i][m]["status"]=="success" for m in MODELS)
                            for i in ids),
        "human_editor_time_minutes":None,
        "warnings":"No held-out authentic meeting. No model accepted without repeated independent test. "
                   "Only metric dictionaries returned. Frozen Qwen words stay in private Modal volume."
    }


@app.local_entrypoint()
def main(output:str):
    import json
    result=evaluate_models.remote()
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("NVIDIA_DIA_MATCHED_NUMERIC_ONLY "+json.dumps(result,ensure_ascii=False))
