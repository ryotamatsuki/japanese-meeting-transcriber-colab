"""Evaluate final Japanese speaker-attributed transcript, independently of DER.

Character-permutation CER (cpCER) follows a per-recording global speaker-label
permutation. It is an evaluation-only metric; its reference is human ELAN
transcription. Unknown speaker text is counted as insertion, not discarded.
The overlap subset uses start/end annotations; it is a *time-localized proxy*
because ASR utterances may straddle overlapping and nonoverlapping speech.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

from beta.core import parse_original_archive
from scripts.eval_elan_ja import load_elan
from scripts.evaluate_asr_cer import normalized_ja, edit_distance
from scripts.evaluate_overlap_review import human_overlap, intersection_seconds, merge

MAX_LABELS=8


def _distance(a, b):
    try:
        from rapidfuzz.distance import Levenshtein
        return Levenshtein.distance(a,b)
    except ImportError:
        return edit_distance(a,b)


def _speaker_texts(rows, *, reference: bool):
    fields='speaker_id' if reference else 'speaker'
    groups={}
    for r in sorted(rows, key=lambda t:(float(t['start']),float(t['end']))):
        text=normalized_ja(r['text'])
        if not text:
            continue
        speaker=str(r[fields])
        if speaker in ('話者不明','話者未設定','', 'None') and not reference:
            speaker='__unassigned__'
        groups.setdefault(speaker,[]).append(text)
    return {speaker:''.join(parts) for speaker,parts in groups.items()}


def permutation_cer(reference, hypothesis):
    """Minimized per-speaker Levenshtein over one-to-one speaker permutations.

    Unassigned text and all unmatched extra predicted speakers remain
    chargeable as insertions. Missing reference speakers remain deletions.
    """
    refs=_speaker_texts(reference,reference=True)
    preds=_speaker_texts(hypothesis,reference=False)
    count=sum(map(len,refs.values()))
    if count==0:
        return {'reference_characters':0,'hypothesis_characters':sum(map(len,preds.values())),
                'edit_distance':None,'cpcer':None,'unassigned_characters':len(preds.get('__unassigned__','')),
                'warning':'Empty human reference'}
    unassigned=preds.pop('__unassigned__','')
    if len(preds)>MAX_LABELS:
        raise ValueError('More than 8 model speaker labels: cannot safely evaluate fixed permutation')
    ref_ids=sorted(refs)
    pred_ids=sorted(preds)
    # Allow some reference speakers to be missing (dummy None) even when
    # number of hypothesis labels >= number of reference speakers.
    choices=pred_ids+[None]*len(ref_ids)
    distances={(r,h):_distance(refs[r],preds[h] if h is not None else '')
               for r in ref_ids for h in pred_ids+[None]}
    best=None
    for assignment in itertools.permutations(choices,len(ref_ids)):
        if len({v for v in assignment if v is not None})!=len([v for v in assignment if v is not None]):
            continue
        accounted={h for h in assignment if h is not None}
        errors=sum(distances[r,h] for r,h in zip(ref_ids,assignment))
        errors+=len(unassigned)+sum(len(text) for h,text in preds.items() if h not in accounted)
        if best is None or errors<best:
            best=errors
    return {'reference_characters':count,
            'hypothesis_characters':sum(len(x) for x in preds.values())+len(unassigned),
            'edit_distance':best,'cpcer':best/count,
            'unassigned_characters':len(unassigned),
            'reference_speakers':len(ref_ids),'hypothesis_speakers':len(pred_ids),
            'method':'global 1:1 speaker permutation; NFKC/casefold; whitespace/punctuation stripped'}


def localized_rows(reference, hypothesis, *, min_overlap=0.10):
    """Time-local overlap/no-overlap diagnostic using the human overlap reference.

    This approximates where *whole utterance text* belongs and is NOT exact
    overlap-only cpCER. Each utterance appears in one bucket based on its
    intersection with overlapping speech, so straddling utterances contaminate
    both concepts. Never use this estimate alone for model selection.
    """
    regions=human_overlap(reference)
    def intersects(row):
        duration=intersection_seconds([(row['start'],row['end'])],regions)
        return duration>=min_overlap
    return {
        'reference_overlap': [r for r in reference if intersects(r)],
        'reference_other': [r for r in reference if not intersects(r)],
        'hypothesis_overlap': [r for r in hypothesis if intersects(r)],
        'hypothesis_other': [r for r in hypothesis if not intersects(r)],
        'human_overlap_seconds':sum(b-a for a,b in regions),
        'overlap_count':len(regions),
    }


def evaluate(eaf_path: Path, original_zip: Path):
    reference,eaf_sha=load_elan(eaf_path)
    parsed=parse_original_archive(original_zip.read_bytes())
    hypothesis=parsed['rows']
    full=permutation_cer(reference,hypothesis)
    buckets=localized_rows(reference,hypothesis)
    # No ungrounded claims from naive overlapped utterance text buckets.
    # Don't compute overlap-only "cpCER": many ELAN turns straddle speech
    # overlaps and the whole-utterance bucket will include non-overlap text.
    # Initial metric-only pilot established that this produces unstable scores.
    # Report annotation incidence and speech time instead; per-word overlap
    # accuracy requires reliable word-level human reference alignment.
    return {'eaf_sha256':eaf_sha,'reference_turns':len(reference),
            'hypothesis_utterances':len(hypothesis),'full_cpcer':full,
            'human_overlap_seconds':round(buckets['human_overlap_seconds'],3),
            'overlap_regions':buckets['overlap_count'],
            'overlap_reference_turns_touched':len(buckets['reference_overlap']),
            'overlap_hypothesis_utterances_touched':len(buckets['hypothesis_overlap']),
            'reference_license':'IngCrowd CC BY-NC 4.0 noncommercial',
            'overlap_text_score':None,
            'warning':'Overlap/non-overlap cpCER intentionally NOT scored: utterance spans straddle overlap windows, invalidating text partition. Need word-level human reference for precise overlap ASR metrics.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eaf',required=True,type=Path)
    p.add_argument('--zip',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    record=evaluate(a.eaf,a.zip)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(json.dumps({'eaf_sha256':record['eaf_sha256'],
                      'reference_turns':record['reference_turns'],
                      'hypothesis_utterances':record['hypothesis_utterances'],
                      'cpcer':record['full_cpcer']['cpcer'],
                      'overlap_text_score':None,
                      'reference_overlap_seconds':record['human_overlap_seconds']},sort_keys=True))


if __name__=='__main__':
    main()
