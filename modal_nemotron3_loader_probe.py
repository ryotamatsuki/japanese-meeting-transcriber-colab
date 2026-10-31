"""Read-only Nemotron 3 loader smoke on generated SILENCE, no private audio.

Checks published Hugging Face Transformers path as alternative to NeMo 3
InstantiationException. Never measures real speech or claims benchmark quality.
"""
import modal
from pathlib import Path

if modal.is_local():
    from modal_nvidia_diarizer_headtohead import image
else:
    image=modal.Image.debian_slim(python_version="3.12")

app=modal.App("kiroku-nemotron3-model-load-probe-20261031")


@app.function(image=image,gpu="A10",cpu=2,memory=12000,
              timeout=450,retries=0,max_containers=1,
              single_use_containers=True,scaledown_window=2)
def probe():
    import traceback,time
    started=time.perf_counter()
    try:
        import numpy as np
        import torch
        from transformers import AutoProcessor,AutoModelForAudioFrameClassification
        model_id="nvidia/Nemotron-3-Diarization"
        p=AutoProcessor.from_pretrained(model_id)
        m=AutoModelForAudioFrameClassification.from_pretrained(
            model_id).to("cuda")
        m.eval()
        sr=p.feature_extractor.sampling_rate
        assert sr==16000
        silence=np.zeros(16000*6,dtype="float32")
        inputs=p(silence,sampling_rate=sr).to(m.device,dtype=m.dtype)
        with torch.inference_mode():
            logits=m(**inputs).logits
        segments=p.extract_speaker_dict(logits,inputs.attention_mask)[0]
        if not isinstance(segments,list):
            raise ValueError("Unexpected processor output")
        return {"status":"pass",
                "framework":"Hugging Face Transformers",
                "sampling_rate":sr,"frames":int(logits.shape[1]),
                "speaker_logits":int(logits.shape[2]),
                "synthetic_silence_seconds":6,
                "segment_list_type":True,
                "elapsed_seconds":round(time.perf_counter()-started,3),
                "not_real_speech":True}
    except Exception as exc:
        # Public synthetic silence only, safe to expose bounded model exception.
        trace=traceback.extract_tb(exc.__traceback__)[-5:]
        return {"status":"failed","exception_type":type(exc).__name__,
                "exception_message":str(exc)[:700],
                "trace":[{"filename":v.filename.rsplit("/",1)[-1],
                          "function":v.name,"line":v.lineno}
                         for v in trace],
                "elapsed_seconds":round(time.perf_counter()-started,3),
                "not_real_speech":True}


@app.local_entrypoint()
def main(output:str):
    import json
    result=probe.remote()
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("NEMOTRON3_SYNTHETIC_LOADER_PROBE "+json.dumps(result,ensure_ascii=False))
