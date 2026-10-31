"""Research-only evaluation: Qwen forced-aligned words + Community-1 exclusive labels.

The Qwen text is imported from a temporary file and immediately validated.
No transcript, audio, or original annotation is saved in the final metric JSON.
"""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile
from scripts.qwen_timing_bridge import attribute_qwen
from scripts.eval_elan_ja import load_elan
from scripts.evaluate_attributed_transcript import permutation_cer
from scripts.evaluate_asr_cer import evaluate


def score(eaf:Path,qwen_timed:Path,diar_archive:Path):
    reference,digest=load_elan(eaf)
    prediction=json.loads(qwen_timed.read_text(encoding='utf-8'))
    with ZipFile(diar_archive) as z:
        diar=json.loads(z.read('pyannote_話者区間.json'))['segments']
    duration=float(prediction['duration_seconds'])
    rows,quality=attribute_qwen(prediction['chunks'],diar,duration)
    ref_flat=''.join(x['text'] for x in reference)
    qwen_flat=''.join(x['text'] for x in prediction['chunks'])
    cp=permutation_cer(reference,rows)
    rough=evaluate(ref_flat,qwen_flat)
    # Referenced baseline Whisper stage8 values measured separately and must
    # only be compared by SHA and same normalization. No oracle speakers here.
    return {'eaf_sha256':digest,
        'audio_duration_seconds':duration,
        'reference_characters':cp['reference_characters'],
        'qwen_flattened_cer_percent':100*rough['normalized_cer'],
        'qwen_attributed_cpcer_percent':100*cp['cpcer'],
        'qwen_speaker_count':quality['speaker_count'],
        'utterances':quality['utterance_count'],
        'aligned_tokens':quality['aligned_tokens'],
        'text_preserved':quality['all_normalized_text_preserved'],
        'lexical_redistribution_chunks':quality.get('lexical_redistribution_chunks',0),
        'last_word_end_seconds':quality['final_word_end_seconds'],
        'qwen_alignment_seconds':prediction['qwen_alignment_inference_seconds'],
        'qwen_model_load_seconds':prediction['qwen_model_load_seconds'],
        'model':prediction['model'],
        'aligner':prediction['aligner'],
        'diarizer':'pyannote/speaker-diarization-community-1 exclusive',
        'license':'IngCrowd CC BY-NC 4.0; noncommercial',
        'warning':'Small experiment. Separate GPU Qwen and diar calls; not Web end-to-end or 60-minute validation.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eaf',type=Path,required=True)
    p.add_argument('--qwen-private',type=Path,required=True)
    p.add_argument('--diar-zip',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    record=score(a.eaf,a.qwen_private,a.diar_zip)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('QWEN_ATTRIBUTION_METRIC_ONLY',json.dumps(record,ensure_ascii=False))


if __name__=='__main__':
    main()
