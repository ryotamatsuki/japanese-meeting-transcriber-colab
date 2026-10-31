"""Evaluate authorized Japanese 3/4-speaker meetings with private human truth.

No public benchmark supplied here. This script is a local evaluator, *not* a
claim that RWCP-SP01 or other licensed data has been accessed or benchmarked.
Never upload transcript/reference audio to GitHub Actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from zipfile import ZipFile

from scripts.evaluate_attributed_transcript import permutation_cer
from scripts.evaluate_diarization import compare, load_rttm
from beta.core import parse_original_archive


def load_reference(path: Path) -> tuple[list[dict], dict]:
    raw=path.read_bytes()
    if len(raw)>8*1024*1024:
        raise ValueError('Private annotated reference exceeds 8 MiB')
    record=json.loads(raw)
    if record.get('license_approved') is not True or not isinstance(record.get('source'),str) or not record['source'].strip():
        raise ValueError('Document approved source and licensed research permission')
    if record.get('human_verified') is not True:
        raise ValueError('Reference must be human verified (not model pseudo-ground truth)')
    expected=record.get('expected_speakers')
    if type(expected) is not int or expected not in (3,4):
        raise ValueError('Only 3 or 4 speaker research samples are in scope')
    rows=record.get('turns')
    if not isinstance(rows,list) or len(rows)<expected*3 or len(rows)>20000:
        raise ValueError('Insufficient reference turns')
    clean=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError('Invalid reference entry')
        try:
            start,end=float(row['start']),float(row['end'])
            name=row['speaker_id']
            transcript=row['text']
        except (TypeError,KeyError,ValueError):
            raise ValueError('Invalid reference fields') from None
        if not (math.isfinite(start) and math.isfinite(end) and 0<=start<end<=3600
                and isinstance(name,str) and 0<len(name)<90
                and isinstance(transcript,str) and len(transcript)<=6000):
            raise ValueError('Invalid reference content or time')
        clean.append({'start':start,'end':end,'speaker_id':name,'text':transcript})
    speakers={x['speaker_id'] for x in clean}
    if len(speakers)!=expected:
        raise ValueError('Reference speaker count does not match declared count')
    clean.sort(key=lambda x:(x['start'],x['end'],x['speaker_id']))
    return clean, {'expected_speakers':expected,'source':record['source'].strip(),
                   'reference_sha256':hashlib.sha256(raw).hexdigest(),
                   'license_approved':True,'human_verified':True}


def score(reference_json: Path, archive: Path, reference_rttm: Path | None = None) -> dict:
    reference,meta=load_reference(reference_json)
    if not archive.is_file() or archive.stat().st_size>150*1024*1024:
        raise ValueError('Invalid model export ZIP')
    parsed=parse_original_archive(archive.read_bytes())
    with ZipFile(archive) as z:
        if 'pyannote_話者区間.json' not in z.namelist():
            raise ValueError('Missing Community-1 exclusive speaker intervals')
        diar=json.loads(z.read('pyannote_話者区間.json'))['segments']
    if not diar or not isinstance(diar,list):
        raise ValueError('Empty predicted speaker intervals')
    p=permutation_cer(reference,parsed['rows'])
    result={
        'source':meta['source'],'reference_sha256':meta['reference_sha256'],
        'reference_speakers':meta['expected_speakers'],
        'predicted_speakers':p['hypothesis_speakers'],
        'reference_characters':p['reference_characters'],
        'reference_turns':len(reference),'predicted_utterances':len(parsed['rows']),
        'cpcer_percent':round(100*p['cpcer'],6),
        'der_percent':None,'jer_percent':None,'der_human_rttm_verified':False,
        'research_only':True,'release_status':'NO_GO'}
    if reference_rttm is not None:
        manual=load_rttm(reference_rttm)
        if len({x['speaker_id'] for x in manual})!=meta['expected_speakers']:
            raise ValueError('Human RTTM speaker count mismatch')
        dia=compare(manual,diar,collar=0)
        result['der_percent']=round(dia['der_percent'],6)
        result['jer_percent']=round(dia['jer_percent'],6)
        result['der_human_rttm_verified']=True
        result['rttm_sha256']=hashlib.sha256(reference_rttm.read_bytes()).hexdigest()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--human-rttm',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=score(args.reference,args.archive,args.human_rttm)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('MULTISPEAKER_NUMERIC_ONLY',json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
