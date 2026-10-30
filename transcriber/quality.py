"""Conservative, opt-in cleanup for exclusive speaker segments.

Never deletes speech or fills silence. Only a short A-B-A *island* surrounded
by contiguous A speech can be relabelled. This is an experimental heuristic,
NOT proof of improved diarization accuracy.
"""
from __future__ import annotations

import math


def _validate(segments):
    ordered = sorted((dict(s) for s in segments), key=lambda x: (x["start"], x["end"]))
    for i, s in enumerate(ordered):
        if not all(k in s for k in ("start", "end", "speaker_id")):
            raise ValueError("Missing required diarization segment keys")
        if not (math.isfinite(float(s["start"])) and math.isfinite(float(s["end"]))
                and 0 <= float(s["start"]) < float(s["end"])):
            raise ValueError("Invalid diarization timestamp")
        if i and ordered[i-1]["end"] > s["start"] + 1e-6:
            raise ValueError("Exclusive diarization must not overlap")
    return ordered


def collapse_short_islands(segments, *, max_island_seconds=0.10, max_gap_seconds=0.06):
    """Return (cleaned, audit) without modifying caller input.

    One simultaneous pass avoids cascaded merges which can destroy legitimate
    alternating short utterances. An island B is relabelled A only if A spans
    the immediate neighbours and gaps between all three are small.
    """
    if not (0 <= max_island_seconds <= 0.30 and 0 <= max_gap_seconds <= 0.10):
        raise ValueError("Conservative island/gap thresholds required")
    original = _validate(segments)
    changed = [dict(s) for s in original]
    replacements = []
    for i in range(1, len(original)-1):
        prev, cur, nxt = original[i-1:i+2]
        if (prev["speaker_id"] == nxt["speaker_id"] != cur["speaker_id"]
            and cur["end"] - cur["start"] <= max_island_seconds
            and 0 <= cur["start"] - prev["end"] <= max_gap_seconds
            and 0 <= nxt["start"] - cur["end"] <= max_gap_seconds):
            changed[i]["speaker_id"] = prev["speaker_id"]
            replacements.append({"start": cur["start"], "end": cur["end"],
                                 "from": cur["speaker_id"], "to": prev["speaker_id"]})
    result = []
    for s in changed:
        if result and result[-1]["speaker_id"] == s["speaker_id"] and abs(result[-1]["end"] - s["start"]) <= 1e-6:
            result[-1]["end"] = s["end"]
        else:
            result.append(dict(s))
    old_turns = sum(a["speaker_id"] != b["speaker_id"] for a,b in zip(original, original[1:]))
    new_turns = sum(a["speaker_id"] != b["speaker_id"] for a,b in zip(result, result[1:]))
    return result, {"original_intervals": len(original), "clean_intervals": len(result),
                    "raw_switches": old_turns, "clean_switches": new_turns,
                    "changed_fragments": replacements,
                    "parameters": {"max_island_seconds": max_island_seconds,
                                   "max_gap_seconds": max_gap_seconds}}


def find_overlap_windows(standard_segments, *, minimum_seconds=0.10):
    """Find concurrent different-speaker activity from regular diarization.

    Uses all start/end events instead of quadratic pairwise comparisons.
    Returns review candidates only; it is not ground-truth overlap detection.
    """
    if not 0 <= minimum_seconds <= 2.0:
        raise ValueError("Invalid overlap threshold")
    events = []
    for s in standard_segments:
        start, end = float(s["start"]), float(s["end"])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError("Invalid standard diarization segment")
        who = str(s["speaker_id"])
        events.extend([(start, 1, who), (end, -1, who)])
    events.sort(key=lambda x: (x[0], x[1]))
    if not events:
        return []
    from collections import Counter
    active, windows, previous = Counter(), [], None
    i = 0
    while i < len(events):
        t = events[i][0]
        participants = sorted(k for k, n in active.items() if n > 0)
        if previous is not None and t > previous and len(participants) >= 2:
            candidate = {"start": previous, "end": t, "speaker_ids": participants}
            if windows and windows[-1]["speaker_ids"] == participants and abs(windows[-1]["end"] - previous) <= 1e-6:
                windows[-1]["end"] = t
            else:
                windows.append(candidate)
        while i < len(events) and events[i][0] == t:
            _, delta, speaker = events[i]
            active[speaker] += delta
            i += 1
        previous = t
    return [w for w in windows if w["end"] - w["start"] >= minimum_seconds]
