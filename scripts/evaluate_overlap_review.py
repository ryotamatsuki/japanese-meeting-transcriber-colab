"""Evaluate time-localized *candidate* overlap precision/recall against human ELAN.

The metrics refer to overlapping speech activity only. They do not evaluate
speaker IDs or transcript correctness. No audio/transcripts are ever emitted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from scripts.eval_elan_ja import load_elan


def merge(intervals):
    merged=[]
    for start,end in sorted((float(a),float(b)) for a,b in intervals):
        if not 0<=start<end:
            raise ValueError('Invalid window')
        if merged and start<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else:
            merged.append((start,end))
    return merged


def human_overlap(reference_rows):
    intervals={}
    for row in reference_rows:
        intervals.setdefault(row['speaker_id'],[]).append((row['start'],row['end']))
    events=[]
    for spans in intervals.values():
        for a,b in merge(spans):
            events.extend([(a,1),(b,-1)])
    events.sort(key=lambda x:(x[0],x[1]))
    active=0;previous=None;result=[]
    for t,delta in events:
        if previous is not None and t>previous and active>=2:
            result.append((previous,t))
        active+=delta
        previous=t
    return merge(result)


def intersection_seconds(a,b):
    i=j=0;total=0.0
    while i<len(a) and j<len(b):
        start=max(a[i][0],b[j][0]);end=min(a[i][1],b[j][1])
        total+=max(0,end-start)
        if a[i][1]<b[j][1]:i+=1
        else:j+=1
    return total


def metrics(eaf_path,review_record):
    human,sha=load_elan(Path(eaf_path))
    truth=human_overlap(human)
    candidates=merge((w['start'],w['end']) for w in review_record['windows'])
    length=lambda spans:sum(b-a for a,b in spans)
    tp=intersection_seconds(truth,candidates)
    positive=length(candidates);actual=length(truth)
    return {
        'reference_eaf_sha256':sha,
        'reference_overlap_seconds':round(actual,3),
        'model_predicted_overlap_seconds':round(positive,3),
        'matched_overlap_seconds':round(tp,3),
        'overlap_time_precision':round(tp/positive,6) if positive else None,
        'overlap_time_recall':round(tp/actual,6) if actual else None,
        'candidate_count':len(review_record['windows']),
        'warning':'Overlap candidate time localization only; not DER, cpCER or speaker-attributed ASR accuracy.',
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eaf',required=True,type=Path)
    p.add_argument('--review',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    record=metrics(a.eaf,json.loads(a.review.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':
    main()
