"""Research-only word/speaker switch diagnostics and conservative optional smoothing.

Same frozen Whisper words and pyannote Community-1 speaker intervals.
No model change, no text edits, no inferred confidence probabilities.

A short B island in an A-B-A pattern is an *anomaly candidate*, not proof
that B is wrong: brief authentic replies, overlap and imperfect timestamps
must be protected. Disabled by default; holdout metrics are required.
"""
from __future__ import annotations

import math
import re

_UNKNOWN = {"話者不明", "話者未設定", "unknown", "unassigned", ""}
_SHORT_REAL_REPLIES = {
    "はい", "うん", "ええ", "いや", "そう", "そうですね",
    "なるほど", "ああ", "はいはい", "そうです", "そうそう",
    "違います", "え", "えっ", "あ", "うんうん",
}


def _finite_word(word):
    try:
        start, end = float(word["start"]), float(word["end"])
        return math.isfinite(start) and math.isfinite(end) and 0 <= start < end
    except (KeyError, TypeError, ValueError):
        return False


def _utterance_runs(words, max_same_speaker_gap=0.45):
    """Never cross a gap, temporal regression or unknown label."""
    runs = []
    for index, word in enumerate(words):
        if not _finite_word(word):
            # An invalid timestamp is a hard boundary; do not reinterpret it.
            runs.append({"start": index, "end": index, "speaker": None,
                         "first": None, "last": None, "valid": False})
            continue
        speaker = str(word.get("speaker", "")).strip()
        if speaker.casefold() in _UNKNOWN:
            runs.append({"start": index, "end": index, "speaker": None,
                         "first": word["start"], "last": word["end"], "valid": False})
            continue
        prior = runs[-1] if runs else None
        if (prior and prior["valid"] and prior["speaker"] == speaker
                and 0 <= float(word["start"]) - float(prior["last"]) <= max_same_speaker_gap):
            prior["end"] = index
            prior["last"] = max(float(prior["last"]), float(word["end"]))
        else:
            runs.append({"start": index, "end": index, "speaker": speaker,
                         "first": float(word["start"]), "last": float(word["end"]),
                         "valid": True})
    return runs


def short_switch_candidates(words, *, max_island_seconds=0.45,
                            max_edge_gap=0.20, min_anchor_seconds=0.65,
                            protect_backchannels=True):
    """Identify A-B-A anomalies whose neighbours are sustained speech.

    Each returned candidate contains positions and timing, not recognized text.
    This is a review hypothesis; false-positive rate is unknown.
    """
    if not (0.05 <= max_island_seconds <= 0.80):
        raise ValueError("Island threshold must be 50..800 ms")
    if not (0 <= max_edge_gap <= 0.25):
        raise ValueError("Edge gap threshold must be 0..250 ms")
    if not (0.25 <= min_anchor_seconds <= 2.0):
        raise ValueError("Stable context threshold must be 250..2000 ms")
    ordered = list(words)
    runs = _utterance_runs(ordered)
    flagged = []
    for i in range(1, len(runs)-1):
        left, mid, right = runs[i-1:i+2]
        if not all(r["valid"] for r in (left, mid, right)):
            continue
        if not left["speaker"] == right["speaker"] != mid["speaker"]:
            continue
        if mid["end"]-mid["start"]+1 > 2:
            continue
        if float(mid["last"])-float(mid["first"]) > max_island_seconds:
            continue
        if float(left["last"])-float(left["first"]) < min_anchor_seconds:
            continue
        if float(right["last"])-float(right["first"]) < min_anchor_seconds:
            continue
        gap_a = float(mid["first"])-float(left["last"])
        gap_b = float(right["first"])-float(mid["last"])
        if not (0 <= gap_a <= max_edge_gap and 0 <= gap_b <= max_edge_gap):
            continue
        phrase = "".join(str(w.get("text", "")).strip() for w in ordered[mid["start"]:mid["end"]+1])
        phrase = re.sub(r"[。、.,!?！？\s]", "", phrase)
        if protect_backchannels and phrase in _SHORT_REAL_REPLIES:
            continue
        flagged.append({
            "first_index": mid["start"], "last_index": mid["end"],
            "start": float(mid["first"]), "end": float(mid["last"]),
            "before_speaker": left["speaker"],
            "candidate_speaker": mid["speaker"],
            "proposed_speaker": right["speaker"],
        })
    return flagged


def stabilize_short_switches(words, **kwargs):
    """Copy and relabel only flagged micro-islands, never change lexical text/times.

    Research candidate ONLY. Caller must compare against human audio reference.
    """
    original = [dict(w) for w in words]
    output = [dict(w) for w in original]
    candidates = short_switch_candidates(original, **kwargs)
    for candidate in candidates:
        for i in range(candidate["first_index"], candidate["last_index"]+1):
            output[i]["speaker"] = candidate["proposed_speaker"]
    return output, {"examined_words": len(original),
                    "island_candidates": len(candidates),
                    "relabeled_words": sum(c["last_index"]-c["first_index"]+1
                                           for c in candidates),
                    "candidate_spans": [
                        {"start":c["start"], "end":c["end"],
                         "first_index":c["first_index"],
                         "last_index":c["last_index"]} for c in candidates]}
