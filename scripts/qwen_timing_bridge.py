"""Research-only bridge: Qwen3-ASR forced-aligned Japanese tokens -> existing diarized utterances.

No inference or external dependencies here. Fail closed on timestamp/text loss:
the goal is to test whether Qwen can be used in the existing editor, not to
change an application default or silently discard unmatched transcript text.
"""
from __future__ import annotations
import math
from transcriber.alignment import assign_and_group
from scripts.evaluate_asr_cer import normalized_ja


def _restore_qwen_text_at_aligned_token_boundaries(text: str, items: list[dict]):
    """Research-only: retain Qwen lexical content with aligner-derived spans.

    Allows only low-distance, equal-normalized-length substitutions.
    Token boundaries remain inferred, NOT verified true word boundaries.
    Return unchanged stamps if confidence guards fail.
    """
    from scripts.evaluate_asr_cer import edit_distance
    source=normalized_ja(text)
    predicted=normalized_ja(''.join(str(x['text']) for x in items))
    if source==predicted:
        return items,False
    if not items or not source or len(source)!=len(predicted):
        return items,False
    if edit_distance(source,predicted)>max(2,len(source)//20):
        return items,False
    cursor=0
    rebuilt=[]
    for i,item in enumerate(items):
        required=len(normalized_ja(str(item['text'])))
        if i==len(items)-1:
            end=len(text)
        else:
            end=cursor
            while end<len(text) and len(normalized_ja(text[cursor:end]))<required:
                end+=1
            while end<len(text) and not normalized_ja(text[end]):
                end+=1
        piece=text[cursor:end]
        if len(normalized_ja(piece))!=required:
            return items,False
        rebuilt.append({**item,'text':piece})
        cursor=end
    if cursor!=len(text) or ''.join(x['text'] for x in rebuilt)!=text:
        return items,False
    return rebuilt,True


def qwen_segments(chunks: list[dict], duration: float, *, max_chunk_seconds: float = 38) -> tuple[list[dict],dict]:
    if not math.isfinite(max_chunk_seconds) or not 3 <= max_chunk_seconds <= 50:
        raise ValueError("Invalid research chunk limit")
    if not chunks or not (0 < float(duration) <= 3600):
        raise ValueError("Invalid audio or empty Qwen chunks")
    if len(chunks)>240:
        raise ValueError("Too many Qwen chunks")
    result=[]
    words_count=0
    lexical_redistribution_chunks=0
    tail_timestamp_review_tokens=0
    lexical_input=[]
    lexical_alignment=[]
    maximum=0.
    previous_offset=-1.
    for chunk in chunks:
        offset=float(chunk['offset_sec'])
        chunk_duration=float(chunk['duration_sec'])
        if not (math.isfinite(offset) and math.isfinite(chunk_duration)
                and 0 <= offset <= duration and 0 < chunk_duration <= max_chunk_seconds
                and offset>previous_offset and offset+chunk_duration<=duration+0.8):
            raise ValueError("Invalid chunk offsets / durations")
        previous_offset=offset
        text=str(chunk['text'])
        lexical_input.append(text)
        stamps=chunk.get('items') or []
        stamps,reallocated=_restore_qwen_text_at_aligned_token_boundaries(text,stamps)
        lexical_redistribution_chunks+=int(reallocated)
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
            if absolute_b <= absolute_a:
                # The aligner may place a few final-token onsets up to 0.8s
                # beyond the actual file end. Never *drop* their transcript
                # text: retain it in a 1ms end-of-file REVIEW interval.
                # This is an inferred placeholder, NOT a measured onset.
                # Fail closed for offsets outside the documented tolerance
                # or more than four such tokens.
                overrun=(offset+a)-duration
                if not (-0.001 <= overrun <= 0.8):
                    raise ValueError("Qwen tail token exceeds audio boundary tolerance")
                if tail_timestamp_review_tokens >= 12:
                    raise ValueError("Too many Qwen inferred tail timestamp tokens")
                if offset+chunk_duration < duration-0.8 or round(duration,3)<0.002:
                    raise ValueError("Qwen tail token is outside final audio chunk")
                absolute_b=round(duration,3)
                absolute_a=round(absolute_b-0.001,3)
                tail_timestamp_review_tokens+=1
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
        # Numeric-only diagnostics; never print speech text or aligned tokens.
        import json
        mismatch=[]
        for index, chunk in enumerate(chunks):
            raw=normalized_ja(str(chunk['text']))
            timed=normalized_ja(''.join(str(t['text']) for t in (chunk.get('items') or [])))
            if raw!=timed:
                mismatch.append({'chunk_index':index,'recognized_characters':len(raw),
                    'aligned_characters':len(timed),'same_character_count':len(raw)==len(timed)})
        print('QWEN_ALIGNMENT_NUMERIC_DIAGNOSTIC',json.dumps({
            'mismatch_chunk_count':len(mismatch),'mismatched_chunks':mismatch[:12],
            'total_recognized_chars':len(joined),'total_aligned_chars':len(aligned)},
            ensure_ascii=False),flush=True)
        raise ValueError("Qwen forced alignment did not preserve all normalized speech characters")
    if words_count<4 or maximum < 0.8*duration:
        raise ValueError("Qwen timestamps are missing or do not cover most of recording")
    return result,{'aligned_tokens':words_count,
        'normalized_text_characters':len(joined),
        'text_preserved':True,'final_word_end_seconds':maximum,
        'chunk_count':len(chunks),
        'lexical_redistribution_chunks':lexical_redistribution_chunks,
        'tail_timestamp_review_tokens':tail_timestamp_review_tokens}


def attribute_qwen(chunks: list[dict], diarization: list[dict], duration: float, *,
                   max_chunk_seconds: float = 38):
    if not diarization:
        raise ValueError("Diarization is required")
    asr_segments, integrity=qwen_segments(chunks,duration,max_chunk_seconds=max_chunk_seconds)
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
