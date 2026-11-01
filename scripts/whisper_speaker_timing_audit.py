"""Frozen Whisper word timestamps × frozen Community-1 Exclusive speaker regions.

Research diagnostics: compare assignment policy ONLY. Zero time shift is the
predeclared baseline. Human turn annotations are evaluation-only, not word-time
ground truth. Never put raw transcript or per-token text in returned metrics.
"""
from __future__ import annotations

import hashlib
import math
from bisect import bisect_right
from collections import Counter

from scripts.evaluate_asr_cer import normalized_ja
from scripts.evaluate_attributed_transcript import permutation_cer
from scripts.qwen_error_decomposition import extract_words, group_words
from transcriber.alignment import assign_and_group

OFFSETS = (-0.30, -0.15, 0., 0.15, 0.30)
RULES = ("legacy", "midpoint", "onset", "end", "vote_no_fallback")


def _validate_regions(regions, *, exclusive=True):
    arr = sorted(({"start":float(r["start"]),"end":float(r["end"]),
                   "speaker_id":str(r["speaker_id"])} for r in regions),
                 key=lambda s:(s["start"],s["end"],s["speaker_id"]))
    for i, r in enumerate(arr):
        if not (math.isfinite(r["start"]) and math.isfinite(r["end"])
                and 0 <= r["start"] < r["end"] and r["speaker_id"]):
            raise ValueError("Invalid speaker region")
        if exclusive and i and arr[i-1]["end"]>r["start"]+1e-6:
            raise ValueError("Overlapping diarization supplied as Exclusive")
    if not arr:
        raise ValueError("No diarization regions")
    return arr


def _frozen_words(asr):
    original=extract_words(asr)
    # Legacy sorts words by inferred start. Reject word order inversions instead
    # of making a silently different text sequence for another arm.
    ordered=sorted(original,key=lambda w:(w["start"],w["end"]))
    if [w["text"] for w in original]!=[w["text"] for w in ordered]:
        raise ValueError("Word timestamp inversions would change lexical order")
    for w in ordered:
        if not (math.isfinite(w["start"]) and math.isfinite(w["end"])
                and w["start"] >= 0 and w["end"] >= w["start"]):
            raise ValueError("Invalid word timestamp")
    normalized=normalized_ja("".join(w["text"] for w in original))
    if not normalized:
        raise ValueError("Empty lexical output")
    return original,normalized


def _assign(words, regions, rule):
    ordered=_validate_regions(regions)
    labels={}
    for r in ordered:
        if r["speaker_id"] not in labels:
            labels[r["speaker_id"]]="話者"+str(len(labels)+1)
    ends=[r["end"] for r in ordered]
    result=[]
    unknown=0
    gaps=0
    votes_tied=0
    boundary_distances=[]
    for w in words:
        a,b=w["start"],w["end"]
        idx=bisect_right(ends,a)
        overlaps=[]
        for r in ordered[max(0,idx-1):]:
            if r["start"]>=max(a+.01,b):
                break
            overlap=max(0.,min(b,r["end"])-max(a,r["start"]))
            if overlap>0:
                overlaps.append((overlap,r))
        picks=[]
        if rule in ("legacy","vote_no_fallback"):
            best=max((x[0] for x in overlaps),default=0.)
            picks=[x[1] for x in overlaps if abs(x[0]-best)<=1e-9]
        else:
            t = a if rule=="onset" else (a+b)*.5 if rule=="midpoint" else max(a,b-1e-6)
            picks=[r for r in ordered if r["start"]<=t<r["end"]]
        if not overlaps:
            gaps+=1
        if len(picks)>1:
            votes_tied+=1
        if picks:
            who=labels[picks[0]["speaker_id"]]
        elif rule=="vote_no_fallback":
            who="話者不明";unknown+=1
        else:
            # Match the legacy closest-region fallback (1.2 seconds).
            center=(a+b)*.5
            nearest=min(ordered,key=lambda r:max(r["start"]-center,0,center-r["end"]))
            distance=max(nearest["start"]-center,0,center-nearest["end"])
            if distance<=1.2:
                who=labels[nearest["speaker_id"]]
            else:
                who="話者不明";unknown+=1
        result.append({**w,"speaker":who})
        # Measured proximity to automatic speaker turn, NOT word timing accuracy.
        boundary_distances.append(min(
            (abs((a+b)*.5 - r["start"]) for r in ordered[1:]),default=float("inf")))
    return result,{"unknown_words":unknown,"words_without_region_overlap":gaps,
                   "tied_overlap_vote_words":votes_tied,
                   "words_center_within_150ms_of_auto_region_start":sum(x<=.15 for x in boundary_distances),
                   "words_center_within_300ms_of_auto_region_start":sum(x<=.30 for x in boundary_distances)}


def _score(reference, words, frozen):
    grouped=group_words(words)
    if normalized_ja("".join(r["text"] for r in grouped))!=frozen:
        raise ValueError("ASR word text was changed")
    c=permutation_cer(reference,grouped)
    return {"cpcer":c["cpcer"],"edits":c["edit_distance"],
            "unassigned_characters":c["unassigned_characters"],
            "utterances":len(grouped),
            "switches":sum(a["speaker"]!=b["speaker"] for a,b in zip(words,words[1:]))}


def _shift(regions,offset,duration):
    shifted=[]
    for r in regions:
        a=max(0.,min(duration,r["start"]+offset))
        b=max(0.,min(duration,r["end"]+offset))
        if b>a:
            shifted.append({"start":a,"end":b,"speaker_id":r["speaker_id"]})
    return _validate_regions(shifted)


def evaluate(reference,asr,exclusive,*,duration):
    if not (math.isfinite(duration) and 1<=duration<=3600):
        raise ValueError("Invalid recording duration")
    original,frozen=_frozen_words(asr)
    exclusive=_validate_regions(exclusive)
    legacy,_,count=assign_and_group(asr,exclusive,True)
    if count!=len(original) or normalized_ja("".join(r["text"] for r in legacy))!=frozen:
        raise ValueError("Legacy baseline is not lexically identical")
    measured_baseline=permutation_cer(reference,legacy)
    report={}
    chosen_by_rule={}
    for rule in RULES:
        assigned,diag=_assign(original,exclusive,rule)
        scores=_score(reference,assigned,frozen)
        report[rule]={**scores,**diag}
        chosen_by_rule[rule]=[w["speaker"] for w in assigned]
    if report["legacy"]["edits"]!=measured_baseline["edit_distance"]:
        raise ValueError("Independent legacy assignment did not reproduce baseline")
    # Exactly the same policy, replace ONLY automatic speaker regions with
    # human turn-level speaker regions. Diagnostic privileged-information bound.
    gold_regions=_validate_regions(reference,exclusive=False)
    # Gold can overlap: the Exclusive compatibility approximation is a
    # secondary diagnostic, *not* a trustworthy exclusive golden region.
    oracle=None
    if all(a["end"]<=b["start"]+1e-6 for a,b in zip(gold_regions,gold_regions[1:])):
        oracle,_=_assign(original,gold_regions,"legacy")
        oracle=_score(reference,oracle,frozen)
    # Predeclared offsets are sensitivity diagnostics ONLY. Do not select
    # minimum CP-CER and deploy it; reference-guided selection would leak.
    shifts={}
    for offset in OFFSETS:
        shifted=_shift(exclusive,offset,duration)
        assigned,_=_assign(original,shifted,"legacy")
        shifts[str(offset)]=_score(reference,assigned,frozen)
    # The zero-shift arm must be bit-for-bit equivalent under the same scoring.
    if shifts[str(0.)]["edits"]!=report["legacy"]["edits"]:
        raise AssertionError("Zero shift does not reproduce baseline")
    disagree={}
    for rule in RULES[1:]:
        disagree[rule]=sum(a!=b for a,b in zip(chosen_by_rule["legacy"],chosen_by_rule[rule]))
    return {"reference_characters":measured_baseline["reference_characters"],
            "word_count":len(original),
            "lexical_sha256":hashlib.sha256(frozen.encode("utf8")).hexdigest(),
            "rules":report,"disagreement_words_vs_legacy":disagree,
            "shift_sensitivity_diagnostic_only":shifts,
            "human_turn_regions_proxy_not_word_gold":oracle,
            "claims":{"whisper_words_frozen":True,"community_regions_frozen":True,
                      "language_model_or_speaker_weights_changed":False,
                      "human_word_time_accuracy_measured":False,
                      "speaker_boundary_truth_established":False}}
