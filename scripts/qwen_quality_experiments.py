"""Qwen fixed-weights research helpers; no audio, text or PII logging.

All thresholds are pre-registered experiment flags, not model confidence scores.
This module is not connected to the public Studio.
"""
from __future__ import annotations

from collections import defaultdict
import math
import random
import re
import statistics

from scripts.evaluate_asr_cer import normalized_ja


def checked_context(value: str | None, *, max_length: int = 300) -> str:
    """Keep user-provided context bounded; do not log or persist the contents."""
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
        raise ValueError("Invalid context")
    return value.strip()


def diagnose_review_candidates(words, *, overlap_ranges=(), diarization=(),
                               min_speech_chars_per_second=0.35,
                               max_silence_gap=4.0, boundary_seconds=0.5):
    """Return metadata-only indices/reasons. Never call them confirmed errors.

    Time gap is a *review flag*, not proof of an omitted utterance.
    """
    flags = defaultdict(set)
    for i, row in enumerate(words):
        begin = float(row["start"])
        finish = float(row["end"])
        if not (math.isfinite(begin) and math.isfinite(finish) and 0 <= begin <= finish):
            raise ValueError("Invalid word timing")
        text = str(row["text"])
        if finish - begin >= 3 and len(normalized_ja(text)) / max(0.1, finish-begin) < min_speech_chars_per_second:
            flags[i].add("long_low_text")
        if re.search(r"[0-9０-９]|[¥￥$]|[万億円]|[年月日]", text):
            flags[i].add("important_number")
        if i > 0:
            prev = words[i-1]
            gap = begin - float(prev["end"])
            if gap > max_silence_gap:
                flags[i].add("long_gap_review")
            if gap < -0.05:
                flags[i].add("timestamp_overlap_review")
            if row.get("speaker") != prev.get("speaker") and gap < boundary_seconds:
                flags[i].add("speaker_boundary_review")
        if any(max(begin, a) < min(finish, b) for a,b in overlap_ranges):
            flags[i].add("overlap_speech_review")
        if any(abs(begin-float(t["start"])) <= boundary_seconds or
               abs(finish-float(t["end"])) <= boundary_seconds
               for t in diarization):
            flags[i].add("diarization_boundary_review")
    return [{"index":i, "reasons":sorted(reason)} for i,reason in sorted(flags.items())]


def oracle_exclusive_intervals(reference, duration):
    """Diagnostic speaker truth used only for comparison; overlap is ambiguous.

    Picks latest-starting active reference turn for overlap segments.
    This is *not* a strict upper bound or reference transcript for overlap ASR.
    """
    endpoints = {0.0, float(duration)}
    for row in reference:
        a,b = float(row["start"]),float(row["end"])
        if 0 <= a < b <= duration:
            endpoints.add(a)
            endpoints.add(b)
    edges = sorted(endpoints)
    result = []
    ambiguous_seconds = 0.0
    for a,b in zip(edges,edges[1:]):
        mid = (a+b)/2
        active = [r for r in reference if float(r["start"]) <= mid < float(r["end"])]
        if not active:
            continue
        if len({r["speaker_id"] for r in active}) > 1:
            ambiguous_seconds += b-a
        selected = max(active,key=lambda r:(float(r["start"]),str(r["speaker_id"])))
        identity = str(selected["speaker_id"])
        if result and result[-1]["speaker_id"]==identity and abs(result[-1]["end"]-a)<1e-5:
            result[-1]["end"]=b
        else:
            result.append({"start":a,"end":b,"speaker_id":identity})
    return result, ambiguous_seconds


def edit_components(reference: str, hypothesis: str) -> dict:
    """Real text-edit decomposition, never inferred from length differences."""
    from rapidfuzz.distance import Levenshtein
    r,h=normalized_ja(reference),normalized_ja(hypothesis)
    ops=Levenshtein.editops(r,h)
    counter=defaultdict(int)
    for op in ops:
        counter[{"insert":"insertions","delete":"deletions","replace":"substitutions"}[op.tag]]+=1
    return {"reference_characters":len(r),"hypothesis_characters":len(h),
            "insertions":counter["insertions"],"deletions":counter["deletions"],
            "substitutions":counter["substitutions"],"edit_distance":len(ops),
            "cer":len(ops)/len(r) if r else None}


def paired_median_bootstrap(baseline, candidate, *, n_boot=4000, seed=20261031):
    """Recorder-level paired changes, percentile CI, sign test; no pseudoreplication."""
    if len(baseline)!=len(candidate) or len(baseline)<2 or n_boot<200:
        raise ValueError("Need matching multiple recordings")
    changes=[float(c)-float(b) for b,c in zip(baseline,candidate)]
    if not all(math.isfinite(x) for x in changes):
        raise ValueError("Nonfinite scores")
    rng=random.Random(seed)
    n=len(changes)
    boot=sorted(statistics.median(changes[rng.randrange(n)] for _ in range(n))
                for _ in range(n_boot))
    improved=sum(d<0 for d in changes)
    worsened=sum(d>0 for d in changes)
    nn=improved+worsened
    from math import comb
    sign_p=min(1.0,2*sum(comb(nn,k) for k in range(min(improved,worsened)+1))/2**nn) if nn else 1.
    return {"n":n,"n_improved":improved,"n_worsened":worsened,
            "median_candidate_minus_baseline":statistics.median(changes),
            "ci95":[boot[int(0.025*n_boot)],boot[min(n_boot-1,int(0.975*n_boot))]],
            "paired_sign_test_p_two_sided":sign_p,
            "per_record_change":changes,
            "unit":"recording","interval":"exploratory bootstrap; not independent holdout"}


def prefer_original_if_uncertain(original, alternative, *, validated):
    """Candidate transcription must never overwrite canonical text without review."""
    if not validated:
        return original, "preserved"
    # Automatic adoption is intentionally forbidden pending independent evidence.
    return original, "review_alternative_only"



def retain_distinct_overlap_tokens(tokens, *, tolerance_sec=0.12):
    """Conservative boundary overlap reconciliation for research-only hypotheses.

    Only drop exact duplicate normalized text with near-identical timestamps
    and the SAME speaker. Keep different simultaneous utterances and repeated
    backchannels. Record dropped count; never infer omissions from this function.
    """
    if not 0 <= tolerance_sec <= 0.25:
        raise ValueError("Unbounded duplicate matching tolerance")
    result = []
    removed = 0
    for raw in tokens:
        item = dict(raw)
        start, end = float(item["start"]),float(item["end"])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
            raise ValueError("Invalid overlapping token timing")
        duplicate = any(
            normalized_ja(str(old["text"])) == normalized_ja(str(item["text"]))
            and normalized_ja(str(item["text"])) != ""
            and old.get("speaker")==item.get("speaker")
            and abs(float(old["start"])-start)<=tolerance_sec
            and abs(float(old["end"])-end)<=tolerance_sec
            for old in result[-8:])
        if duplicate:
            removed += 1
        else:
            result.append(item)
    return result,removed


def build_bounded_review_queue(rows, flags, *, max_share=0.15, hard_cap=12):
    """Research-only, metadata-only priority queue; not proof of error.

    Reviewing every speaker boundary is impractical. This function limits
    alerts and keeps original text untouched, even if alternatives exist.
    """
    if not 0 < max_share <= 0.3 or not 1 <= hard_cap <= 40:
        raise ValueError("Invalid review budget")
    budget=min(hard_cap,max(1,int(math.ceil(len(rows)*max_share)))) if rows else 0
    priorities={
        "overlap_speech_review":0,
        "timestamp_overlap_review":1,
        "important_number":2,
        "long_low_text":3,
        "long_gap_review":4,
        "speaker_boundary_review":5,
        "diarization_boundary_review":6,
    }
    options=[]
    for f in flags:
        index=f.get("index")
        if not isinstance(index,int) or not 0 <= index < len(rows):
            raise ValueError("Review index outside transcript")
        reasons=sorted(set(f.get("reasons") or []))
        if not reasons:
            continue
        row=rows[index]
        options.append((min(priorities.get(r,9) for r in reasons),index,{
           "utterance_index":index,
           "start":float(row["start"]),
           "end":float(row["end"]),
           "reasons":reasons,"status":"要確認",
        }))
    options.sort(key=lambda item:(item[0],item[1]))
    return [row for _,__,row in options[:budget]]

def research_summary(records):
    """Keep artifact numeric-only; reject accidental transcript fields."""
    deny=("text","transcript","speaker_name","audio","filename","path","context","token",
          "secret","original")
    for row in records:
        for key in row:
            if any(term in key.lower() for term in deny) and key not in ("audio_seconds","context_mode"):
                raise ValueError("Unapproved content in public research metrics")
    return records
