"""Experimental word-level speaker attribution ablation; NEVER changes production ASR.

Compare exported exclusive labels with maximum-overlap labels from Community-1
regular speaker intervals, on the SAME Whisper words and SAME audio.
Both use globally permuted cpCER against human ELAN labels. No re-ASR.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from zipfile import ZipFile

from beta.core import parse_original_archive
from scripts.eval_elan_ja import load_elan
from scripts.evaluate_attributed_transcript import permutation_cer
from scripts.evaluate_asr_cer import normalized_ja


def annotate_regular(asr_segments, regular_segments, max_nearest_seconds=1.2):
    intervals=sorted((dict(s) for s in regular_segments), key=lambda x:(x['start'],x['end'],x['speaker_id']))
    if not intervals:
        raise ValueError('Missing regular diarization')
    for s in intervals:
        if not 0<=float(s['start'])<float(s['end']) or not math.isfinite(float(s['end'])):
            raise ValueError('Malformed regular diarization')
    speakers={s['speaker_id']:f'話者{i+1}' for i,s in enumerate(
        sorted({x['speaker_id'] for x in intervals},
               key=lambda v:min(x['start'] for x in intervals if x['speaker_id']==v)))}
    rows=[]
    for segment in asr_segments:
        words=segment.get('words') or []
        if not words and segment.get('text','').strip():
            words=[segment]
        for w in words:
            text=str(w.get('text',''))
            if not text.strip():
                continue
            a,b=float(w['start']),float(w['end'])
            if not (math.isfinite(a) and math.isfinite(b) and 0<=a<=b):
                raise ValueError('Malformed ASR word timestamp')
            scores={}
            for s in intervals:
                if s['start']>=b:break
                overlap=max(0.0,min(b,s['end'])-max(a,s['start']))
                if overlap>0:
                    speaker=s['speaker_id']
                    scores[speaker]=scores.get(speaker,0.0)+overlap
            if scores:
                picked=max(scores,key=lambda v:(scores[v],-list(speakers.keys()).index(v)))
                label=speakers[picked]
            else:
                center=(a+b)/2
                nearby=min(intervals,key=lambda s:max(s['start']-center,0,center-s['end']))
                d=max(nearby['start']-center,0,center-nearby['end'])
                label=speakers[nearby['speaker_id']] if d<=max_nearest_seconds else '話者不明'
            rows.append({'start':a,'end':b,'speaker':label,'text':text})
    return rows


def compare(eaf_path, archive):
    reference,sha=load_elan(eaf_path)
    raw=archive.read_bytes()
    baseline=parse_original_archive(raw)['rows']
    with ZipFile(archive) as z:
        files=set(z.namelist())
        if 'whisper_asr.json' not in files or 'pyannote_通常話者区間.json' not in files:
            raise ValueError('Need ASR words and same-run standard diarization for a valid ablation')
        asr=json.loads(z.read('whisper_asr.json'))['segments']
        normal=json.loads(z.read('pyannote_通常話者区間.json'))['segments']
    alternative=annotate_regular(asr,normal)
    flat_asr=normalized_ja(''.join(s.get('text','') for s in asr))
    baseline_len=sum(len(normalized_ja(t['text'])) for t in baseline)
    alternative_len=sum(len(normalized_ja(t['text'])) for t in alternative)
    if alternative_len!=baseline_len or alternative_len<len(flat_asr)*0.90:
        # Fallback word text concatenation must not be compared if different
        # content is present. The same ASR should have same normalized char count.
        raise ValueError('ASR transcription content mismatch: cannot isolate speaker attribution')
    old=permutation_cer(reference,baseline)
    new=permutation_cer(reference,alternative)
    return {'reference_eaf_sha256':sha,'reference_turns':len(reference),
            'baseline_exclusive_cpcer':old,'regular_max_overlap_cpcer':new,
            'delta_cpcer_percentage_points':100*(new['cpcer']-old['cpcer']),
            'asr_content_same':True,
            'comparison':'same ASR words, standard vs exclusive diarization speaker voting',
            'model_training_changed':False,
            'notes':'Research ablation. Regular overlap activity does not uniquely determine true speaker of a word; no application labels modified.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eaf',type=Path,required=True)
    p.add_argument('--zip',dest='archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=compare(args.eaf,args.archive)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'eaf_sha256':result['reference_eaf_sha256'],
        'exclusive_cpcer':result['baseline_exclusive_cpcer']['cpcer'],
        'regular_max_overlap_cpcer':result['regular_max_overlap_cpcer']['cpcer'],
        'delta_pp':result['delta_cpcer_percentage_points']},sort_keys=True))


if __name__=='__main__':
    main()
