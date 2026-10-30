"""Validate paired Qwen/Whisper Japanese cpCER evidence, never authorize a release.

Consumes numeric-only summaries; does not load audio, EAF, or transcript content.
Stage12's gate is a *research extension* gate and cannot promote Qwen to beta.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

EXPECTED_MODEL = 'Qwen/Qwen3-ASR-1.7B'
EXPECTED_ALIGNER = 'Qwen/Qwen3-ForcedAligner-0.6B'
EXPECTED_DIARIZER = 'pyannote/speaker-diarization-community-1 exclusive'
EXPECTED_IDS = tuple(f'{i:02}' for i in range(1, 11))


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label}: not numeric')
    val = float(value)
    if not math.isfinite(val) or val < 0 or (positive and val <= 0):
        raise ValueError(f'{label}: invalid numeric value')
    return val


def _int(value: object, label: str, *, min_value: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < min_value:
        raise ValueError(f'{label}: invalid integer')
    return value


def _verified_id(value: object) -> str:
    if not isinstance(value, str) or value not in EXPECTED_IDS:
        raise ValueError('Unrecognized recording ID')
    return value


def _validate_hash(value: object) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in '0123456789abcdef' for c in value)):
        raise ValueError('Invalid EAF SHA256')
    return value


def audit(baseline: dict, qwen: dict, *, expected_ids: tuple[str, ...] = EXPECTED_IDS) -> dict:
    if baseline.get('schema_version') != 1:
        raise ValueError('Unknown Whisper baseline schema')
    if baseline.get('baseline_run_id') != 41054900339:
        raise ValueError('Baseline run does not match pre-registered Stage8 benchmark')
    if baseline.get('dataset') != 'IngCrowd/japanese-themed-dialogue':
        raise ValueError('Unexpected benchmark data')
    if qwen.get('attempted') != len(expected_ids) or qwen.get('complete') != len(expected_ids):
        raise ValueError('Incomplete Qwen trial: success of GitHub job is not enough')
    if qwen.get('failed') != []:
        raise ValueError('Some Qwen trials failed')
    if qwen.get('no_web_or_production_code_changes') is not True:
        raise ValueError('Experiment must not mutate production defaults')

    base = {}
    for row in baseline['records']:
        rid = _verified_id(row['id'])
        if rid in base:
            raise ValueError(f'Duplicate Whisper baseline: {rid}')
        _validate_hash(row['eaf_sha256'])
        _int(row['reference_characters'], 'Whisper reference characters', min_value=1)
        _number(row['whisper_attributed_cpcer_percent'], 'Whisper cpCER')
        base[rid] = row
    if set(base) != set(EXPECTED_IDS):
        raise ValueError('Whisper benchmark is missing one or more of 10 records')

    observed = {}
    for row in qwen['per_record']:
        # Workflow summary records are sorted by trial index, but they do not
        # include an id. Match by BOTH the unique human EAF hash and count.
        sha = _validate_hash(row.get('eaf_sha256'))
        candidates = [rid for rid in expected_ids if base[rid]['eaf_sha256'] == sha]
        if len(candidates) != 1:
            raise ValueError('Qwen EAF hash is unrecognized or not unique')
        rid = candidates[0]
        if rid in observed:
            raise ValueError('Duplicate Qwen recording')
        if _int(row.get('reference_characters'), 'Qwen reference characters', min_value=1) != base[rid]['reference_characters']:
            raise ValueError('Reference text normalization mismatch')
        if row.get('text_preserved') is not True:
            raise ValueError('Qwen transcript text not preserved')
        if row.get('model') != EXPECTED_MODEL or row.get('aligner') != EXPECTED_ALIGNER:
            raise ValueError('Qwen model identity mismatch')
        if row.get('diarizer') != EXPECTED_DIARIZER:
            raise ValueError('Qwen diarization mode mismatch')
        if _int(row.get('qwen_speaker_count'), 'Qwen speaker count', min_value=1) != 2:
            raise ValueError('Speaker-count mismatch in 2-speaker benchmark')
        _int(row.get('aligned_tokens'), 'Aligned word count', min_value=4)
        _int(row.get('utterances'), 'Utterance count', min_value=1)
        duration = _number(row.get('audio_duration_seconds'), 'Duration', positive=True)
        last_word = _number(row.get('last_word_end_seconds'), 'Last aligned word end')
        if last_word > duration + 0.002 or last_word < 0.8*duration:
            raise ValueError('Alignment does not reach the recording tail')
        _number(row.get('qwen_alignment_seconds'), 'Alignment inference seconds', positive=True)
        _number(row.get('qwen_model_load_seconds'), 'Model load seconds')
        cpcer = _number(row.get('qwen_attributed_cpcer_percent'), 'Qwen cpCER')
        observed[rid] = {'id':rid,'reference_characters':base[rid]['reference_characters'],
                         'whisper_cpcer_percent':base[rid]['whisper_attributed_cpcer_percent'],
                         'qwen_cpcer_percent':cpcer,
                         'paired_change_pp':cpcer-base[rid]['whisper_attributed_cpcer_percent'],
                         'text_preserved':True,'eaf_sha256':sha,
                         'qwen_alignment_seconds':row['qwen_alignment_seconds'],
                         'duration_seconds':duration}
    if set(observed) != set(expected_ids):
        raise ValueError('Missing Qwen results for requested recordings')
    rows = [observed[rid] for rid in expected_ids]
    wh = [r['whisper_cpcer_percent'] for r in rows]
    qw = [r['qwen_cpcer_percent'] for r in rows]
    changes = [r['paired_change_pp'] for r in rows]
    improvement_count = sum(delta < 0 for delta in changes)
    # Exploratory promotion criterion only: evidence for deeper research,
    # NOT a sufficient condition for changing beta's default ASR or release.
    research_gate = (len(rows)==10 and improvement_count>=8 and
                     statistics.median(changes) <= -5.0 and max(changes) <= 2.0)
    return {
        'stage':12,'metric':'Japanese speaker-attributed cpCER (global speaker permutation)',
        'baseline_run_id':41054900339,
        'tested':len(rows),'expected':len(expected_ids),'failed':0,
        'improved_records':improvement_count,'regressed_records':sum(d>0 for d in changes),
        'median_whisper_cpcer_percent':statistics.median(wh),
        'median_qwen_cpcer_percent':statistics.median(qw),
        'median_paired_change_pp':statistics.median(changes),
        'difference_of_medians_pp':statistics.median(qw)-statistics.median(wh),
        'worst_paired_change_pp':max(changes),
        'median_alignment_inference_seconds':statistics.median(r['qwen_alignment_seconds'] for r in rows),
        'per_record':rows,
        'research_extension_gate':'PASS' if research_gate else 'NOT_MET',
        'release_status':'NO_GO',
        'production_model_changed':False,
        'limitations':('Unpaired GPU inference runs share the same human EAF and scoring method, '
                       'but do not hold diarization inference and environment constant. '
                       'Two-person noncommercial dialogue is not a 3–4 person administrative meeting. '
                       'Web E2E, edit effort, 60-minute Qwen and cost controls still unverified.'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--qwen-summary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exploratory-two',action='store_true',
                        help='Allow exactly two SHA-matched recordings (01 and 05); not a 10-recording gate')
    args=parser.parse_args()
    expected=('01','05') if args.exploratory_two else EXPECTED_IDS
    baseline=json.loads(args.baseline.read_text(encoding='utf-8'))
    qwen=json.loads(args.qwen_summary.read_text(encoding='utf-8'))
    report=audit(baseline,qwen,expected_ids=expected)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    safe={k:v for k,v in report.items() if k != 'per_record'}
    print('STAGE12_NUMERIC_AUDIT',json.dumps(safe,ensure_ascii=False))


if __name__=='__main__':
    main()
