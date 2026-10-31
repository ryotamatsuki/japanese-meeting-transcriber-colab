"""Independent word-boundary split experiment; never mixed with join metrics.

Uses frozen Qwen forced-aligned token timestamps, no text rewriting,
no speaker relabeling, and no human reference in candidate selection.
"""
from __future__ import annotations

import copy
import json
import random

from scripts.qwen_boundary_fourarm import audio_features
from scripts.qwen_timing_bridge import qwen_segments


def attach_aligned_words(utterances, chunks, duration, speech_end):
    segments,_=qwen_segments(chunks,duration,speech_end_seconds=speech_end)
    words=sorted((w for s in segments for w in s["words"]),
                 key=lambda w:(w["start"],w["end"]))
    out=copy.deepcopy(utterances)
    cursor=0
    for row in out:
        needed=row["text"]
        joined=""
        chosen=[]
        while cursor<len(words) and len(joined)<len(needed):
            w=words[cursor]
            joined+=w["text"]
            chosen.append(w)
            cursor+=1
            if not needed.startswith(joined):
                raise ValueError("Timed word text does not match original row")
        if joined!=needed or not chosen:
            raise ValueError("Timed words do not preserve original row")
        row["words"]=chosen
    if cursor!=len(words):
        raise ValueError("Unconsumed words")
    return out


def split_candidates(rows,*,seed=20261031,cap=16):
    if not 2<=cap<=40:
        raise ValueError("Invalid candidate cap")
    targeted=[]
    controls=[]
    for ri,row in enumerate(rows):
        words=row.get("words")
        if not words:
            continue
        if "".join(w["text"] for w in words)!=row["text"]:
            raise ValueError("Word text conservation failed")
        for wi in range(len(words)-1):
            a,b=words[wi],words[wi+1]
            gap=float(b["start"])-float(a["end"])
            if gap<0 or gap>3:
                continue
            candidate=(ri,wi)
            if a["text"].rstrip().endswith(("。","！","？","!","?")) or gap>=.4:
                targeted.append(candidate)
            else:
                controls.append(candidate)
    targeted=sorted(set(targeted))
    controls=sorted(set(controls))
    rng=random.Random(seed)
    # Fixed selection based only on ASR boundary timestamps and punctuation.
    # Reserve at least one-third of the budget for no-punctuation controls.
    n_control=min(len(controls),max(1,cap//3))
    n_target=min(len(targeted),cap-n_control)
    selected_target=targeted[:n_target]
    selected_controls=sorted(rng.sample(controls,n_control))
    return sorted(selected_target+selected_controls)


def split_rule(row, wi):
    left,right=row["words"][wi:wi+2]
    gap=float(right["start"])-float(left["end"])
    return ("split" if left["text"].rstrip().endswith(
        ("。","！","？","!","?")) or gap>=.8 else "keep")


def make_prompt(rows, ri, wi, feature=None):
    row=rows[ri]
    words=row["words"]
    context=[{"index":j,"text":words[j]["text"],"start":words[j]["start"],
              "end":words[j]["end"]} for j in range(max(0,wi-3),min(len(words),wi+5))]
    task={"row_index":ri,"word_index":wi,"speaker":row["speaker"],
          "text":row["text"],"context":context}
    if feature is not None:
        task["observed_audio"]=feature
    return [
        {"role":"system","content":(
            "これは認識済み日本語の1発言の内部境界です。次の語の前に表示上の"
            "発言分割を置くか split, keep, hold のどれかを判定してください。"
            "文面・話者・単語時刻は変更禁止。曖昧ならhold。"
            'JSONのみ: {"row_index":整数,"word_index":整数,"decision":"split|keep|hold"}'
        )},
        {"role":"user","content":json.dumps(task,ensure_ascii=False)}
    ]


def parse_choice(raw,ri,wi):
    try:
        if not isinstance(raw,str) or len(raw)>2000:
            return "hold"
        item=json.loads(raw)
        if (type(item) is dict and set(item)=={"row_index","word_index","decision"}
                and type(item["row_index"]) is int
                and type(item["word_index"]) is int
                and item["row_index"]==ri and item["word_index"]==wi
                and item["decision"] in ("split","keep","hold")):
            return item["decision"]
    except (TypeError,ValueError):
        pass
    return "hold"


def run_split_arms(rows,pcm,infer,*,cap=16):
    source=copy.deepcopy(rows)
    indices=split_candidates(source,cap=cap)
    decisions={a:{} for a in ("baseline","rules","text_qwen","audio_qwen")}
    for ri,wi in indices:
        key=f"{ri}:{wi}"
        row=source[ri]
        decisions["baseline"][key]="keep"
        decisions["rules"][key]=split_rule(row,wi)
        left,right=row["words"][wi:wi+2]
        pair=[{"start":left["start"],"end":left["end"],
               "speaker":row["speaker"],"text":left["text"]},
              {"start":right["start"],"end":right["end"],
               "speaker":row["speaker"],"text":right["text"]}]
        feat=audio_features(pcm,16000,pair,[0])["0"]
        for arm in ("text_qwen","audio_qwen"):
            try:
                raw=infer(arm,make_prompt(source,ri,wi,
                                         feat if arm=="audio_qwen" else None))
                decisions[arm][key]=parse_choice(raw,ri,wi)
            except Exception:
                decisions[arm][key]="hold"
    if rows!=source:
        raise ValueError("Source text changed")
    return {"candidates":[f"{ri}:{wi}" for ri,wi in indices],
            "decisions":decisions,"source_preserved":True}


def split_proxy(reference,rows,indices):
    """Only strict time-local proxy, NOT independently reviewed human gold."""
    from scripts.jcre3_boundary_adjudication import _match
    labels={}
    for ri,wi in indices:
        a,b=rows[ri]["words"][wi:wi+2]
        left=_match(a,reference)
        right=_match(b,reference)
        if left is None or right is None:
            label="uncertain"
        else:
            label="keep" if left==right else "split"
        labels[f"{ri}:{wi}"]=label
    return labels


def split_scores(output, labels):
    if set(labels)!=set(output["candidates"]):
        raise ValueError("Split label mismatch")
    if any(v not in ("split","keep","uncertain") for v in labels.values()):
        raise ValueError("Bad split label")
    result={}
    for arm,actions in output["decisions"].items():
        if set(actions)!=set(labels):
            raise ValueError("Inconsistent candidate universe")
        positive=[k for k,v in labels.items() if v=="split"]
        negative=[k for k,v in labels.items() if v=="keep"]
        result[arm]={
            "positive":len(positive),"negative":len(negative),
            "true_splits":sum(actions[k]=="split" for k in positive),
            "false_splits":sum(actions[k]=="split" for k in negative),
            "missed_splits":sum(actions[k]!="split" for k in positive),
            "holds":sum(actions[k]=="hold" for k in positive+negative),
            "uncertain":len(labels)-len(positive)-len(negative)}
    return result
