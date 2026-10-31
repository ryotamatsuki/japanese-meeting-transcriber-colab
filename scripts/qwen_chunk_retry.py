"""Fail-closed bounded Qwen forced alignment retries for research Web jobs.

A chunk may have good ASR text but incomplete/altered ForcedAligner tokens.
Instead of silently losing characters, retry *that chunk only* with smaller
audio windows (30->15->7.5s). The newly generated Qwen text then becomes the
reference for lexical conservation; this is NOT equivalent to restoring
transcription from the original 30-second text.
"""
from __future__ import annotations
import math

from scripts.evaluate_asr_cer import normalized_ja
from scripts.qwen_timing_bridge import _restore_qwen_text_at_aligned_token_boundaries


def infer_chunk(model, waveform, offset, *, sample_rate=16000, max_retries=2,
                max_chunk_seconds=38, context=''):
    if sample_rate != 16000 or len(waveform)<sample_rate:
        raise ValueError('Invalid audio chunk duration')
    seconds=len(waveform)/sample_rate
    if not (math.isfinite(offset) and 0<=offset<=3600 and seconds<=max_chunk_seconds and 3<=max_chunk_seconds<=50):
        raise ValueError('Invalid audio chunk bounds')
    if type(max_retries) is not int or not 0<=max_retries<=2:
        raise ValueError('Retry bound exceeded')
    from scripts.qwen_quality_experiments import checked_context
    context=checked_context(context)
    try:
        kwargs={'audio':(waveform,16000),'language':'Japanese',
                'return_time_stamps':True}
        if context:
            kwargs['context']=context
        result=model.transcribe(**kwargs)
        if len(result)!=1:
            raise ValueError('Qwen returned multiple predictions')
        one=result[0]
        text=one.text
        aligned=one.time_stamps
        items=[{'text':item.text,'start_time':float(item.start_time),
                'end_time':float(item.end_time)}
               for item in (aligned.items if aligned is not None else [])]
        items,repaired=_restore_qwen_text_at_aligned_token_boundaries(text,items)
        if text.strip() and not items:
            raise ValueError('Aligned token list missing')
        if normalized_ja(text)!=normalized_ja(''.join(x['text'] for x in items)):
            raise ValueError('Qwen aligner changed recognized text')
        last_start=-1.0
        for item in items:
            a,b=item['start_time'],item['end_time']
            token=str(item['text'])
            # Mirror qwen_segments' full validation *before* returning a
            # chunk. Otherwise one bad token would invalidate an entire hour
            # only after all GPU inference had finished.
            if not (math.isfinite(a) and math.isfinite(b)
                    and 0<=a<=b<=seconds+0.8 and
                    a+0.04>=last_start and token.strip()
                    and a<seconds):
                raise ValueError('Invalid token timing')
            last_start=a
        return [{'offset_sec':float(offset),'duration_sec':seconds,
                 'text':text,'items':items}],{'retries':0,'lexical_repair':int(repaired)}
    except (ValueError,AttributeError,TypeError):
        if max_retries==0 or seconds<3:
            raise ValueError('Qwen alignment failed after bounded retries') from None
        cut=len(waveform)//2
        left,meta_l=infer_chunk(model,waveform[:cut],offset,
                                sample_rate=sample_rate,max_retries=max_retries-1,
                                 max_chunk_seconds=max_chunk_seconds,context=context)
        right,meta_r=infer_chunk(model,waveform[cut:],offset+cut/sample_rate,
                                 sample_rate=sample_rate,max_retries=max_retries-1,
                                 max_chunk_seconds=max_chunk_seconds,context=context)
        return left+right,{
            'retries':meta_l['retries']+meta_r['retries']+1,
            'lexical_repair':meta_l['lexical_repair']+meta_r['lexical_repair']}
