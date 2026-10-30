"""WhisperX-inspired, evidence-only audit of word -> speaker assignment.

Do not silently change speaker IDs: overlap scores are *not* calibrated
probabilities. Flag suspect words for audio review while retaining the original
speaker attribution. Standard diarization may contain simultaneous speakers.
"""
from __future__ import annotations

from collections import Counter
from bisect import bisect_right
from .quality import find_overlap_windows
import math


def _intersection(a, b, c, d):
    return max(0.0, min(b, d) - max(a, c))


def audit_word_speaker_assignments(asr_segments, exclusive, standard=None,
                                   *, margin=0.18, minimum_coverage=0.55,
                                   overlap_seconds=0.06):
    """Compute deterministic review flags. Labels are diagnostics, not edits.

    Args:
        asr_segments: Whisper segments with zero or more word timestamps.
        exclusive: exclusive Community-1 segments used by the main exporter.
        standard: optional regular diarization which preserves overlapping speech.
    Returns:
        JSON-safe dict with word-level flags, aggregate counts and settings.
    """
    if not 0 <= margin <= 0.5 or not 0 <= minimum_coverage <= 1 or not 0 <= overlap_seconds <= 1:
        raise ValueError("Invalid review thresholds")
    standard = standard or []
    exclusive = sorted(exclusive, key=lambda x: (x['start'], x['end']))
    end_times = [float(s['end']) for s in exclusive]
    overlap_windows = find_overlap_windows(standard, minimum_seconds=0)
    overlap_ends = [float(w['end']) for w in overlap_windows]
    rows = []
    counts = Counter()
    for seg in asr_segments:
        terms = seg.get("words") or []
        if not terms and str(seg.get("text", "")).strip():
            terms = [seg]
        for w in terms:
            if not str(w.get("text", "")).strip():
                continue
            start = float(w["start"])
            end = float(w["end"])
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
                raise ValueError("ASR word has invalid time interval")
            length = end - start
            scores = {}
            if length:
                cursor = bisect_right(end_times, start)
                for s in exclusive[cursor:]:
                    if float(s['start']) >= end:
                        break
                    overlap = _intersection(start, end, float(s['start']), float(s['end']))
                    if overlap > 0:
                        name = str(s['speaker_id'])
                        scores[name] = scores.get(name, 0.0) + overlap
            ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            winner = ordered[0][0] if ordered else None
            total = sum(scores.values())
            ratio = ordered[0][1] / total if total else None
            coverage = min(1.0, total / length) if length else 0.0
            flags = []
            if length < 0.05:
                flags.append("short_or_zero_word_timestamp")
            if not ordered:
                flags.append("no_exclusive_overlap")
            elif coverage < minimum_coverage:
                flags.append("low_exclusive_coverage")
            if len(ordered) > 1:
                flags.append("word_crosses_speaker_boundary")
                if ratio is not None and ratio - (1 - ratio) <= margin:
                    flags.append("close_speaker_overlap_scores")
            # Precomputed overlap windows avoid quadratic pairwise comparison.
            overlap_cursor = bisect_right(overlap_ends, start)
            for window in overlap_windows[overlap_cursor:]:
                if window['start'] >= end:
                    break
                if _intersection(start, end, window['start'], window['end']) >= overlap_seconds:
                    flags.append('regular_diarization_overlap_candidate')
                    break
            for flag in flags:
                counts[flag] += 1
            rows.append({
                "start": start, "end": end, "text": str(w["text"]),
                "exclusive_speaker_candidate": winner,
                "exclusive_coverage_ratio": round(coverage, 6),
                "overlap_vote_share_not_probability": round(ratio, 6) if ratio is not None else None,
                "review_required": bool(flags), "review_reasons": flags,
            })
    return {
        "method": "word-duration-overlap audit inspired by WhisperX; not an accuracy estimate",
        "version": 1,
        "settings": {"close_score_margin": margin, "minimum_coverage": minimum_coverage,
                     "minimum_concurrent_overlap_seconds": overlap_seconds},
        "word_count": len(rows),
        "review_words": sum(w["review_required"] for w in rows),
        "reason_counts": dict(sorted(counts.items())),
        "words": rows,
    }
