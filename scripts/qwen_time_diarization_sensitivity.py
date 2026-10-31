"""Research-only factorial diagnostic of speaker intervals vs Qwen token timing.

Uses exactly the same recognized token text and timestamps across speakers.
Human speaker regions are privileged diagnostic data, NOT product inference.
Time perturbations are LEAKAGE-PRONE sensitivity checks, never candidate tuning.
No transcripts or word-level text appear in metric output.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import math

from scripts.evaluate_asr_cer import normalized_ja
from scripts.evaluate_attributed_transcript import permutation_cer
from scripts.qwen_error_decomposition import (
    annotate_words, extract_words, group_words, reference_to_regions)
from transcriber.alignment import assign_and_group

# Predeclared before running new GPU ablations.
OFFSETS_SECONDS = (-0.6, -0.3, -0.15, 0.0, 0.15, 0.3, 0.6)


def shifted_intervals(intervals, shift, duration):
    """Shift only diarization boundaries, clip to recording and report losses."""
    if not (math.isfinite(float(shift)) and math.isfinite(float(duration))
            and duration > 0 and abs(float(shift)) <= 2.0):
        raise ValueError("Invalid shift or recording duration")
    result = []
    clipped = 0
    lost = 0
    for region in intervals:
        a, b = float(region["start"]), float(region["end"])
        if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b
                and b <= duration + .8):
            raise ValueError("Bad diarization segment")
        new_a = max(0.0, min(duration, a + shift))
        new_b = max(0.0, min(duration, b + shift))
        clipped += int(new_a != a + shift or new_b != b + shift)
        if new_b <= new_a:
            lost += 1
            continue
        result.append({"start": new_a, "end": new_b,
                       "speaker_id": region["speaker_id"]})
    if not result:
        raise ValueError("No speaker intervals remain after time shift")
    return result, {"clipped_regions": clipped, "lost_regions": lost}


def _fixed_text(segments):
    words = extract_words(segments)
    text = normalized_ja("".join(w["text"] for w in words))
    if not text:
        raise ValueError("No lexical content")
    return text, len(words)


def _legacy_cpcer(reference, asr, diar, frozen, word_count):
    rows, _, seen = assign_and_group(asr, diar, True)
    if seen != word_count or normalized_ja("".join(r["text"] for r in rows)) != frozen:
        raise ValueError("Legacy arm changed or reordered recognized text")
    chron = sorted(rows, key=lambda r: (r["start"], r["end"]))
    if normalized_ja("".join(r["text"] for r in chron)) != frozen:
        raise ValueError("Evaluation time-sort reorders recognized tokens")
    c = permutation_cer(reference, rows)
    return {"cpcer": c["cpcer"], "edit_distance": c["edit_distance"],
            "unassigned_characters": c["unassigned_characters"]}


def _conservative_cpcer(reference, asr, diar, frozen):
    words = annotate_words(asr, diar)
    rows = group_words(words)
    if normalized_ja("".join(r["text"] for r in rows)) != frozen:
        raise ValueError("Conservative arm altered original Qwen text")
    c = permutation_cer(reference, rows)
    flags = Counter(reason for w in words for reason in w["review_reasons"])
    return {"cpcer": c["cpcer"], "edit_distance": c["edit_distance"],
            "unassigned_characters": c["unassigned_characters"],
            "review_word_count": sum(bool(w["review_reasons"]) for w in words),
            "review_reasons": dict(sorted(flags.items()))}


def evaluate_sensitivity(reference, asr_segments, exclusive, regular, duration,
                         *, offsets=OFFSETS_SECONDS):
    """Reference-blind zero shift; shifted scores are diagnostic only.

    Compare 2x2 baseline timing x diarization source using *legacy* attribution.
    Regular is examined with conservative safe intervals (legacy bisect is invalid
    for nested intervals) and NEVER treated as legacy-equivalent.
    """
    frozen, count = _fixed_text(asr_segments)
    oracle = reference_to_regions(reference)
    if len({r["speaker_id"] for r in oracle}) < 2:
        raise ValueError("No multi-speaker human reference")
    if tuple(offsets) != OFFSETS_SECONDS:
        raise ValueError("Study offsets must be pre-registered")
    baseline = _legacy_cpcer(reference, asr_segments, exclusive, frozen, count)
    oracle_legacy = _legacy_cpcer(reference, asr_segments, oracle, frozen, count)
    auto_cons = _conservative_cpcer(reference, asr_segments, exclusive, frozen)
    oracle_cons = _conservative_cpcer(reference, asr_segments, oracle, frozen)
    regular_cons = _conservative_cpcer(reference, asr_segments, regular, frozen)
    sweeps = []
    for shift in offsets:
        auto_intervals, auto_meta = shifted_intervals(exclusive, shift, duration)
        oracle_intervals, oracle_meta = shifted_intervals(oracle, shift, duration)
        auto = _legacy_cpcer(reference, asr_segments, auto_intervals, frozen, count)
        human = _legacy_cpcer(reference, asr_segments, oracle_intervals, frozen, count)
        sweeps.append({"relative_shift_seconds": shift,
                       "auto_legacy_cpcer": auto["cpcer"],
                       "auto_legacy_edits": auto["edit_distance"],
                       "human_regions_legacy_cpcer": human["cpcer"],
                       "human_regions_legacy_edits": human["edit_distance"],
                       "auto_interval_clipping": auto_meta,
                       "human_interval_clipping": oracle_meta})
    assert sweeps[3]["relative_shift_seconds"] == 0.0
    if (sweeps[3]["auto_legacy_edits"] != baseline["edit_distance"]
            or sweeps[3]["human_regions_legacy_edits"] != oracle_legacy["edit_distance"]):
        raise AssertionError("Zero-shift arm does not replicate frozen baseline")
    return {
        "study": "matched Qwen-ASR text, matched Qwen token timing; varying only speaker regions",
        "normalized_lexical_sha256": hashlib.sha256(frozen.encode("utf8")).hexdigest(),
        "frozen_word_count": count,
        "reference_characters": permutation_cer(reference, group_words(
            annotate_words(asr_segments, exclusive)))["reference_characters"],
        "baseline_legacy_exclusive": baseline,
        "human_regions_legacy_diagnostic": oracle_legacy,
        "auto_conservative_exclusive": auto_cons,
        "auto_conservative_regular": regular_cons,
        "human_regions_conservative_diagnostic": oracle_cons,
        "relative_time_shift_sensitivity": sweeps,
        "warning": (
            "Shifted arms use gold reference scoring and must NOT select a production "
            "offset. Human region arms are privileged diagnosis, not real-time feasible; "
            "turn regions do not establish human WORD timestamp truth. "
            "No CER uplift or edit-time savings is implied.")
    }
