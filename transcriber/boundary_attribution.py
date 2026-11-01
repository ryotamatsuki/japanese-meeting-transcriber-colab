"""Research-only conservative repair for word/Community-1 time-boundary ambiguity.

No model inference, no resegmentation, no text edits. A-B-A islands are only
eligible when the audio time overlap cannot support a confident B word label.
True backchannels, audible multi-speaker overlap, unknown labels and time gaps
are fail-closed. This policy is NOT a calibrated speaker confidence model.

Requires human-reference cpCER plus direct listening for release consideration.
"""
from __future__ import annotations
import math
import re

BACKCHANNELS={"はい","うん","ええ","いや","そう","そうですね","なるほど",
              "ああ","はいはい","そうです","そうそう","違います","え","えっ",
              "あ","うんうん","そうか","そうなんですか"}


def _overlap(a,b,c,d):
    return max(0.,min(b,d)-max(a,c))


def guarded_boundary_repair(words, exclusive, *, regular=None,
                            max_island_words=2, max_island_seconds=.65,
                            max_gap_seconds=.20, min_anchor_seconds=.55,
                            max_competing_advantage_seconds=.08):
    """Conservatively repair only ambiguous single-/two-word A-B-A labels.

    `words` are ordered source word dicts each containing legacy 'speaker'.
    `exclusive` are original raw Community-1 Exclusive intervals (not gold).
    `regular`, if provided, are unmodified Community-1 Regular overlapping
    segments; actual audio overlap cannot be inferred from Exclusive alone.
    When `regular` isn't provided, no flip is performed (fail closed).
    """
    if (type(max_island_words) is not int or not 1<=max_island_words<=2
        or not .05<=max_island_seconds<=.8
        or not 0<=max_gap_seconds<=.25
        or not .25<=min_anchor_seconds<=2.
        or not 0<=max_competing_advantage_seconds<=.20):
        raise ValueError("Unsafe parameter settings")
    if regular is None:
        raise ValueError("Regular diarization required to detect acoustic overlap")
    ordered=[dict(w) for w in words]
    if not regular:
        # Missing Regular acoustic evidence is not proof that there was no
        # simultaneous speech; therefore do not rewrite any speaker label.
        return ordered,{"examined_words":len(ordered),"relabeled_words":0,
                        "island_candidates":0,
                        "rejected":{"regular_diarization_missing":1}}
    region=sorted(exclusive,key=lambda x:(float(x["start"]),float(x["end"])))
    regular=sorted(regular,key=lambda x:(float(x["start"]),float(x["end"])))
    if not region or not ordered:
        return ordered,{"examined_words":len(ordered),"relabeled_words":0,
                        "island_candidates":0,"rejected":{}}
    for i,r in enumerate(region):
        a,b=float(r["start"]),float(r["end"])
        if not (math.isfinite(a) and math.isfinite(b) and 0<=a<b
                and (i==0 or float(region[i-1]["end"])<=a+1e-6)):
            raise ValueError("Invalid Exclusive speaker region")
    for r in regular:
        if not (0<=float(r["start"])<float(r["end"])
                and math.isfinite(float(r["start"])) and math.isfinite(float(r["end"]))):
            raise ValueError("Invalid Regular region")
    for i,w in enumerate(ordered):
        a,b=float(w["start"]),float(w["end"])
        if not (math.isfinite(a) and math.isfinite(b) and 0<=a<b
                and (i==0 or a>=float(ordered[i-1]["start"]))):
            raise ValueError("Invalid or unordered word timestamp")
    speaker_ids={}
    for r in region:
        raw=str(r["speaker_id"])
        if raw not in speaker_ids:
            speaker_ids[raw]="話者"+str(len(speaker_ids)+1)
    label_to_raw={v:k for k,v in speaker_ids.items()}
    def wins(w):
        a,b=float(w["start"]),float(w["end"])
        scores={}
        for r in region:
            if float(r["start"])>=b:
                break
            o=_overlap(a,b,float(r["start"]),float(r["end"]))
            if o:
                label=speaker_ids[str(r["speaker_id"])]
                scores[label]=scores.get(label,0.)+o
        return scores
    def has_real_overlap(a,b):
        # Require intersecting Regular segments from >=2 speakers across a
        # nonzero interval, not merely two labels at non-overlapping edges.
        spans=[]
        for r in regular:
            c,d=float(r["start"]),float(r["end"])
            c,d=max(c,a),min(d,b)
            if d>c:
                spans.append((c,d,str(r["speaker_id"])))
        for i,v in enumerate(spans):
            if any(v[2]!=x[2] and _overlap(v[0],v[1],x[0],x[1])>=.03
                   for x in spans[i+1:]):
                return True
        return False
    def duration(i,j):
        return max(float(ordered[k]["end"]) for k in range(i,j+1))-float(ordered[i]["start"])
    def anchor_left(i):
        # Bounded recent A continuity; don't bridge other speakers or silence.
        j=i-1
        if j<0:
            return 0.
        who=ordered[j]["speaker"]
        k=j
        while k>0 and ordered[k-1]["speaker"]==who and (
            0<=float(ordered[k]["start"])-float(ordered[k-1]["end"])<=.40):
            k-=1
        return duration(k,j)
    def anchor_right(i):
        j=i
        if j>=len(ordered):
            return 0.
        who=ordered[j]["speaker"]
        k=j
        while k+1<len(ordered) and ordered[k+1]["speaker"]==who and (
            0<=float(ordered[k+1]["start"])-float(ordered[k]["end"])<=.40):
            k+=1
        return duration(j,k)
    rejections={}
    def reject(reason):
        rejections[reason]=rejections.get(reason,0)+1
    proposals=[]
    i=1
    while i<len(ordered)-1:
        j=i
        while (j+1<len(ordered)-1 and ordered[j+1]["speaker"]==ordered[i]["speaker"]
               and j-i+1<max_island_words
               and 0<=float(ordered[j+1]["start"])-float(ordered[j]["end"])<=.20):
            j+=1
        if (ordered[i-1]["speaker"]==ordered[j+1]["speaker"]
             and ordered[i]["speaker"]!=ordered[i-1]["speaker"]
             and ordered[i]["speaker"] in label_to_raw
             and ordered[i-1]["speaker"] in label_to_raw):
            a,b=float(ordered[i]["start"]),max(float(x["end"]) for x in ordered[i:j+1])
            target=ordered[i-1]["speaker"]
            if duration(i,j)>max_island_seconds:
                reject("island_too_long")
            elif any(str(x["text"]).strip() in BACKCHANNELS for x in ordered[i:j+1]) or (
                re.sub(r"[。、.,!?！？\s]","","".join(x["text"] for x in ordered[i:j+1])) in BACKCHANNELS):
                reject("protected_backchannel")
            elif not (0<=a-float(ordered[i-1]["end"])<=max_gap_seconds
                      and 0<=float(ordered[j+1]["start"])-b<=max_gap_seconds):
                reject("gap_or_overlapping_word_time")
            elif anchor_left(i)<min_anchor_seconds or anchor_right(j+1)<min_anchor_seconds:
                reject("weak_flanking_anchor")
            elif has_real_overlap(a,b):
                reject("concurrent_speech")
            else:
                ambiguous=True
                for k in range(i,j+1):
                    scores=wins(ordered[k])
                    other=ordered[k]["speaker"]
                    # Need actual acoustic evidence that the target label is
                    # competitive; a high-margin B word is never overridden.
                    if (target not in scores or other not in scores
                            or scores[other]-scores[target]>max_competing_advantage_seconds):
                        ambiguous=False
                        break
                if not ambiguous:
                    reject("high_margin_or_no_target_overlap")
                else:
                    proposals.append((i,j,target))
        i=j+1
    output=[dict(w) for w in ordered]
    for i,j,target in proposals:
        for k in range(i,j+1):
            output[k]["speaker"]=target
    if [w["text"] for w in output]!=[w["text"] for w in words] or any(
        (w["start"],w["end"])!=(x["start"],x["end"]) for w,x in zip(output,words)):
        raise AssertionError("Speaker repair must not touch word text/timestamps")
    return output,{
        "examined_words":len(words),"island_candidates":len(proposals),
        "relabeled_words":sum(j-i+1 for i,j,_ in proposals),
        "rejected":dict(sorted(rejections.items())),
        "annotation":"overlap votes are not calibrated speaker probabilities",
    }
