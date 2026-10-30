"""Select fully annotated two-speaker overlap windows for Stage9 offline evaluation.

This is an ORACLE evaluation-set selector based on *human* ELAN labels. It MUST
NOT be interpreted as an inference-time overlap detector; deployed code uses
Community-1 candidate estimates instead. Selected windows exclude truncated
human utterances to prevent scoring spurious boundary deletions.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from scripts.eval_elan_ja import load_elan
from scripts.evaluate_asr_cer import normalized_ja


def windows(turns, *, max_seconds=7.0, min_overlap=0.40, max_count=2):
    rows=sorted((dict(t) for t in turns if normalized_ja(t['text'])),
                key=lambda t:(t['start'],t['end']))
    results=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if b['start']>=a['end']: break
            if a['speaker_id']==b['speaker_id']:continue
            intersection=min(a['end'],b['end'])-max(a['start'],b['start'])
            if intersection<min_overlap:continue
            lo=min(a['start'],b['start'])
            hi=max(a['end'],b['end'])
            # Grow window to encompass every nontrivial intersecting ELAN turn.
            for _ in range(20):
                expanded=[x for x in rows if x['start']<hi and x['end']>lo]
                nlo=min(x['start'] for x in expanded)
                nhi=max(x['end'] for x in expanded)
                if nhi-nlo>max_seconds:break
                if nlo==lo and nhi==hi:break
                lo,hi=nlo,nhi
            if hi-lo>max_seconds or lo<0:continue
            picked=[x for x in rows if x['start']>=lo and x['end']<=hi]
            if any(x['start']<hi and x['end']>lo and x not in picked for x in rows):
                continue
            if not {'speaker_1','speaker_2'}.issubset({x['speaker_id'] for x in picked}):continue
            if any(max(lo,z['start'])<min(hi,z['end']) for z in results):continue
            by={s:''.join(x['text'] for x in picked if x['speaker_id']==s)
                for s in ('speaker_1','speaker_2')}
            if any(len(normalized_ja(x))<2 for x in by.values()):continue
            results.append({'start':round(lo,3),'end':round(hi,3),
                            'speaker_text':by, 'oracle_overlap_seconds':round(intersection,3),
                            'annotated_turns':len(picked)})
            if len(results)>=max_count:return results
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eaf',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-count',type=int,default=2)
    a=p.parse_args()
    rows,sha=load_elan(a.eaf)
    out={'reference_sha256':sha,'windows':windows(rows,max_count=a.max_count),
         'selection':'oracle-selected from ELAN for offline evaluation only; NOT an inference candidate detector'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,ensure_ascii=False))
    # Do not print original reference Japanese speech.
    print(json.dumps({'reference_sha256':sha,'selected_windows':len(out['windows']),
                      'durations_seconds':[round(w['end']-w['start'],3) for w in out['windows']]}))


if __name__=='__main__':
    main()
