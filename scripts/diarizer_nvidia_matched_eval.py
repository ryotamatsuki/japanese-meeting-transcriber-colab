"""Research-only same-text/same-timestamp comparison of 3 diarization backends.

New NVIDIA checkpoint: Nemotron 3 Diarization (OpenMDW 1.1).
Comparator: Streaming Sortformer 4spk v2.1 (NVIDIA Open Model License).
Neither changes default Kiroku Studio. ELAN acts as gold only for scoring.
"""
from __future__ import annotations
import hashlib
import math
from scripts.qwen_time_diarization_sensitivity import _safe_max_overlap_cpcer
from scripts.evaluate_asr_cer import normalized_ja
from scripts.qwen_error_decomposition import extract_words
from scripts.evaluate_diarization import compare as evaluate_der

MODELS = ("nvidia/diar_streaming_sortformer_4spk-v2.1",
          "nvidia/Nemotron-3-Diarization")
SETTINGS = {"chunk_len":340,"chunk_right_context":40,"fifo_len":40,
            "spkcache_update_period":300}
SPEAKER_CAP = {"nvidia/diar_streaming_sortformer_4spk-v2.1":4,
               "nvidia/Nemotron-3-Diarization":8}


def parse_nemo_segments(raw, *, duration, model_name):
    """Validate NeMo's documented triplet output; do not leak or guess text."""
    if model_name not in MODELS or not math.isfinite(duration) or duration<=0:
        raise ValueError("unrecognized diarizer or duration")
    if not isinstance(raw,(list,tuple)) or len(raw)>100000:
        raise ValueError("invalid diarization output type or length")
    out=[]
    for item in raw:
        if isinstance(item,str):
            f=item.strip().split()
        elif isinstance(item,(list,tuple)) and len(item)==3:
            f=list(item)
        else:
            raise ValueError("unexpected diarization segment shape")
        if len(f)!=3:
            raise ValueError("unexpected number of fields")
        a,b=float(f[0]),float(f[1])
        label=str(f[2])
        if label.startswith("speaker_"):
            label=label[8:]
        elif label.startswith("speaker"):
            label=label[7:]
        if not label.isdecimal() or int(label)>=SPEAKER_CAP[model_name]:
            raise ValueError("invalid diarization speaker ID")
        if not (math.isfinite(a) and math.isfinite(b) and
                0<=a<b and b<=duration+0.8):
            raise ValueError("out-of-recording diarization region")
        out.append({"start":max(0,a),"end":min(duration,b),
                    "speaker_id":"nvidia_"+label})
    if not out:
        raise ValueError("no speech regions from diarizer")
    out.sort(key=lambda x:(x["start"],x["end"],x["speaker_id"]))
    return out


def score_model(reference, qwen_words, regions, *, original_hash):
    sequence=normalized_ja("".join(w["text"] for w in extract_words(qwen_words)))
    if not sequence or hashlib.sha256(sequence.encode()).hexdigest()!=original_hash:
        raise ValueError("Qwen tokens changed across diarization runs")
    speaker=evaluate_der(reference,regions,collar=0.0)
    cp=_safe_max_overlap_cpcer(reference,qwen_words,regions,sequence)
    return {"cpcer":cp["cpcer"],"cpcer_edits":cp["edit_distance"],
            "reference_chars":sum(len(normalized_ja(r["text"])) for r in reference),
            "unassigned_characters":cp["unassigned_characters"],
            "DER":speaker["der_percent"],"JER":speaker["jer_percent"],
            "false_alarm_seconds":speaker["false_alarm_seconds"],
            "missed_detection_seconds":speaker["missed_detection_seconds"],
            "speaker_confusion_seconds":speaker["speaker_confusion_seconds"],
            "predicted_speakers":speaker["candidate_speaker_count"],
            "number_of_regions":len(regions)}


def assert_frozen_baseline(actual, expected):
    if actual["reference_chars"]!=expected["reference_chars"] or (
        actual["cpcer_edits"]!=expected["baseline_edits"]
    ):
        raise ValueError("Baseline drift: refuse NVIDIA model comparison")
    if abs(actual["DER"]-expected["baseline_DER"])>0.001:
        raise ValueError("Baseline DER drift: gold or segmentation changed")
    return True
