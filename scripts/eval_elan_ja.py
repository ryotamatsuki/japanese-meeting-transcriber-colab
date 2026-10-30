"""Evaluation-only ELAN Japanese 2-speaker reference reader (CC BY-NC 4.0 dataset).

Dataset: https://huggingface.co/datasets/IngCrowd/japanese-themed-dialogue
Never publish original audio or raw human transcripts in CI logs/artifacts.
Evaluates diarization and ASR separately; aggregate CER across overlapping
speech is only a coarse baseline and *not* speaker-attributed cpCER.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from scripts.evaluate_asr_cer import evaluate


def load_elan(path: Path):
    content=path.read_bytes()
    if len(content)>4*1024*1024 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('Unexpected EAF size or XML DTD')
    root=ET.fromstring(content)
    if root.tag!='ANNOTATION_DOCUMENT':
        raise ValueError('Not an ELAN annotation document')
    slots={}
    for slot in root.findall('./TIME_ORDER/TIME_SLOT'):
        key=slot.get('TIME_SLOT_ID')
        milliseconds=slot.get('TIME_VALUE')
        if key and milliseconds:
            slots[key]=int(milliseconds)/1000.0
    if not slots:
        raise ValueError('No ELAN time slots')
    turns=[]
    for tier in root.findall('TIER'):
        speaker=tier.get('TIER_ID','')
        if speaker not in ('speaker_1','speaker_2'):
            continue
        for annotation in tier.findall('.//ALIGNABLE_ANNOTATION'):
            t1=slots.get(annotation.get('TIME_SLOT_REF1'))
            t2=slots.get(annotation.get('TIME_SLOT_REF2'))
            if t1 is None or t2 is None or t2<=t1:
                continue
            raw=(annotation.findtext('ANNOTATION_VALUE') or '').strip()
            # Remove nonlexical ELAN markup such as <la> (laughter);
            # keep speech intervals for DER even when content is a nonlexical marker.
            text=re.sub(r'<[^>]+>','',raw)
            turns.append({'start':t1,'end':t2,'speaker_id':speaker,'text':text})
    speakers={s['speaker_id'] for s in turns}
    if speakers!={'speaker_1','speaker_2'} or len(turns)<10:
        raise ValueError('Expected two speaker tiers with multiple annotated turns')
    return sorted(turns,key=lambda r:(r['start'],r['end'],r['speaker_id'])),hashlib.sha256(content).hexdigest()


def evaluate_archive(eaf_path: Path, archive_path: Path):
    turns,eaf_sha=load_elan(eaf_path)
    with ZipFile(archive_path) as z:
        ref_chars=''.join(t['text'] for t in turns)
        asr=json.loads(z.read('whisper_asr.json'))
        pred_chars=''.join(s.get('text','') for s in asr['segments'])
        diar=json.loads(z.read('pyannote_話者区間.json'))['segments']
    asr_result=evaluate(ref_chars,pred_chars)
    # DER/JER requires pyannote.metrics; keep its use localized to evaluation.
    from scripts.evaluate_diarization import compare
    diar_result=compare(turns,diar,collar=0.0)
    return {'source':'IngCrowd/japanese-themed-dialogue',
            'source_license':'CC BY-NC 4.0 (noncommercial research evaluation only)',
            'eaf_sha256':eaf_sha,'input_annotation_turns':len(turns),
            'reference_speaker_count':2,'reference_text_chars':len(ref_chars),
            'asr':asr_result,'diarization':diar_result,
            'warning':'CER is full-dialogue rough order alignment, not speaker-attributed cpCER; ELAN start times used for overlapping turns.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eaf',type=Path,required=True)
    parser.add_argument('--zip',dest='archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    record=evaluate_archive(args.eaf,args.archive)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'eaf_sha256':record['eaf_sha256'],
                      'annotation_turns':record['input_annotation_turns'],
                      'reference_speaker_count':2,
                      'cer_percent':round(record['asr']['normalized_cer']*100,3),
                      'der_percent':round(record['diarization']['der_percent'],3),
                      'jer_percent':round(record['diarization']['jer_percent'],3)},sort_keys=True))

if __name__=='__main__':
    main()
