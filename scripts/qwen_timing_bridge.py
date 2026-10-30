"""Research-only bridge: Qwen3-ASR forced-aligned Japanese tokens -> existing diarized utterances.

No inference or external dependencies here. Fail closed on timestamp/text loss:
the goal is to test whether Qwen can be used in the existing editor, not to
change an application default or silently discard unmatched transcript text.
"""
from __future__ import annotations
import math
from transcriber.alignment import assign_and_group
from scripts.evaluate_asr_cer import normalized_ja


def qwen_segments(chunks: list[dict], duration: float) -> tuple[list[dict],dict]:
    if not chunks or not (0 < float(duration) <= 3600):
        raise ValueError("Invalid audio or empty Qwen chunks")
    if len(chunks)>240:
        raise ValueError("Too many Qwen chunks")
    result=[]
    words_count=0
    lexical_input=[]
    lexical_alignment=[]
    maximum=0.
    previous_offset=-1.
    for chunk in chunks:
        offset=float(chunk['offset_sec'])
        chunk_duration=float(chunk['duration_sec'])
        if not (math.isfinite(offset) and math.isfinite(chunk_duration)
                and 0 <= offset <= duration and 0 < chunk_duration <= 38
                and offset>previous_offset and offset+chunk_duration<=duration+0.8):
            raise ValueError("Invalid chunk offsets / durations")
        previous_offset=offset
        text=str(chunk['text'])
        lexical_input.append(text)
        stamps=chunk.get('items') or []
        if text.strip() and not stamps:
            raise ValueError("No alignment for nonempty Qwen transcript")
        sub=[]
        last_start=-1.0
        for item in stamps:
            a=float(item['start_time'])
            b=float(item['end_time'])
            token=str(item['text'])
            if not (math.isfinite(a) and math.isfinite(b) and
                    0 <= a <= b <= chunk_duration+0.8 and
                    a+0.04>=last_start and token.strip()):
                raise ValueError("Invalid/nonmonotonic Qwen aligned token")
            last_start=a
            absolute_a=round(max(0.0,offset+a),3)
            absolute_b=round(min(duration,offset+max(a+0.01,b)),3)
            if absolute_b <= absolute_a: continue
            sub.append({'text':token,'start':absolute_a,'end':absolute_b})
            lexical_alignment.append(token)
            words_count+=1
            maximum=max(maximum,absolute_b)
        if sub:
            result.append({'text':text,'start':sub[0]['start'],
                           'end':max(t['end'] for t in sub),'words':sub})
    joined=normalized_ja(''.join(lexical_input))
    aligned=normalized_ja(''.join(lexical_alignment))
    if not joined:
        raise ValueError("Qwen produced empty speech for this evaluation")
    if joined != aligned:
        raise ValueError("Qwen forced alignment did not preserve all normalized speech characters")
    if words_count<4 or maximum < 0.8*duration:
        raise ValueError("Qwen timestamps are missing or do not cover most of recording")
    return result,{'aligned_tokens':words_count,
        'normalized_text_characters':len(joined),
        'text_preserved':True,'final_word_end_seconds':maximum,
        'chunk_count':len(chunks)}


def attribute_qwen(chunks: list[dict], diarization: list[dict], duration: float):
    if not diarization:
        raise ValueError("Diarization is required")
    asr_segments, integrity=qwen_segments(chunks,duration)
    utterances,speaker_map,words=assign_and_group(asr_segments,diarization,True)
    if words != integrity['aligned_tokens']:
        raise ValueError("Word attribution omitted aligned tokens")
    expected=normalized_ja(''.join(x['text'] for x in chunks))
    whole=normalized_ja(''.join(x['text'] for x in utterances))
    repairs=0
    if whole != expected:
        # The existing editor sorts words by inferred onset. Forced-aligned
        # adjacent chunk boundaries sometimes overlap slightly; reordering
        # those words changes the original ASR lexical sequence.
        # Only small <=0.8s inversions can be stabilized. Never alter text.
        previous=-1.0
        for segment in asr_segments:
            for item in segment['words']:
                onset=item['start']
                if onset <= previous:
                    adjusted=round(previous+0.001,3)
                    if adjusted-onset > 0.8 or adjusted >= duration:
                        raise ValueError("Forced-alignment times cannot be stabilized safely")
                    item['start']=adjusted
                    item['end']=round(max(item['end'],adjusted+0.001),3)
                    if item['end']>duration:
                        raise ValueError("Stabilization exceeds audio duration")
                    repairs+=1
                previous=item['start']
            segment['start']=segment['words'][0]['start']
            segment['end']=max(item['end'] for item in segment['words'])
        if not repairs:
            raise ValueError("Speaker assignment changed or deleted normalized Qwen text")
        utterances,speaker_map,words=assign_and_group(asr_segments,diarization,True)
        whole=normalized_ja(''.join(x['text'] for x in utterances))
    if whole != expected or words != integrity['aligned_tokens']:
        raise ValueError("Speaker assignment changed or deleted normalized Qwen text")
    return utterances, {**integrity,'utterance_count':len(utterances),
        'speaker_count':len(speaker_map),'all_normalized_text_preserved':True,
        'small_temporal_order_repairs':repairs}
