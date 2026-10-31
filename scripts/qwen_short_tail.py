"""Preserve original samples when the upstream splitter pads a tiny tail.

Upstream qwen-asr 0.0.6 pads a short final chunk to 0.5 seconds, while
our alignment wrapper requires >=1 second. Reconstruct from original sample
boundaries and merge that tail into its predecessor (or move the boundary
when the maximum duration would be exceeded). No VAD/gold text is used.
"""
import math


def coalesce_short_tail(waveform, chunks, *, sample_rate=16000, max_seconds=38):
    if sample_rate != 16000 or not chunks or not 3 <= max_seconds <= 50:
        raise ValueError('Invalid chunk layout')
    offsets=[float(offset) for _,offset in chunks]
    if any(not math.isfinite(o) for o in offsets):
        raise ValueError('Invalid chunk offset')
    starts=[round(o*sample_rate) for o in offsets]
    end=len(waveform)
    if starts[0]!=0 or any(a>=b for a,b in zip(starts,starts[1:])) or starts[-1]>=end:
        raise ValueError('Invalid chunk boundaries')
    if end-starts[-1]<sample_rate and len(starts)>1:
        if end-starts[-2] <= max_seconds*sample_rate:
            starts.pop()
        else:
            starts[-1]=end-sample_rate
    stops=starts[1:]+[end]
    if any(not sample_rate<=b-a<=max_seconds*sample_rate for a,b in zip(starts,stops)):
        raise ValueError('Unsupported chunk duration')
    return [(waveform[a:b],a/sample_rate) for a,b in zip(starts,stops)]
