"""Research-only audio context windows with exclusive token ownership.

Recognition sees extra audio; each token is retained only by its core window
using the aligned midpoint. This avoids fuzzy text deletion of repetitions.
It cannot guarantee correctness when adjacent alignments disagree.
"""
import math


def context_window(signal, offset, core_length, *, sample_rate=16000, padding=1.0):
    if sample_rate != 16000 or not math.isfinite(padding) or not 0 <= padding <= 2:
        raise ValueError("Invalid context bounds")
    if not math.isfinite(offset) or offset < 0 or type(core_length) is not int or core_length < sample_rate:
        raise ValueError("Invalid core bounds")
    first=round(offset*sample_rate)
    last=first+core_length
    if last > len(signal):
        raise ValueError("Core outside audio")
    pad=round(padding*sample_rate)
    start=max(0,first-pad)
    end=min(len(signal),last+pad)
    return signal[start:end],start/sample_rate,(first/sample_rate,last/sample_rate)


def own_aligned_tokens(rows, core, *, final=False):
    """Half-open core intervals assign an exact-boundary midpoint to the right."""
    a,b=core
    if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b):
        raise ValueError("Invalid ownership bounds")
    result=[]
    discarded=0
    for row in rows:
        offset=float(row['offset_sec'])
        kept=[]
        for item in row['items']:
            start=float(item['start_time']);end=float(item['end_time'])
            if not (math.isfinite(offset) and math.isfinite(start) and math.isfinite(end)
                    and offset >= 0 and 0 <= start <= end):
                raise ValueError("Invalid aligned time")
            midpoint=offset+(start+end)/2
            if a <= midpoint < b or (final and midpoint == b):
                kept.append(dict(item))
            else:
                discarded+=1
        if kept:
            result.append({**row,'items':kept,'text':''.join(x['text'] for x in kept)})
    return result,discarded
