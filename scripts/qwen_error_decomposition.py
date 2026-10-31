"""Research-only Qwen timing/speaker error decomposition; never writes Studio output.

No oracle result may be presented as deployable accuracy. Neither a speaker
overlap share nor a ForcedAligner timestamp is a calibrated confidence score.
Only aggregate metrics are returned: never print word content or reference text.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from scripts.evaluate_asr_cer import evaluate, normalized_ja
from scripts.evaluate_attributed_transcript import permutation_cer
from scripts.v1_meeting_reference import load_meeting_eaf
from scripts.qwen_timing_bridge import qwen_segments
from transcriber.alignment import assign_and_group


UNKNOWN = "話者不明"
ALLOWED_ORIGINS = frozenset(("aligned_unverified", "realigned", "estimated", "invalid"))


def _validate_time(start, end, *, allow_zero=False):
    a, b = float(start), float(end)
    if not (math.isfinite(a) and math.isfinite(b) and 0 <= a <= b and (allow_zero or a < b)):
        raise ValueError("Invalid or nonfinite time interval")
    return a, b


def _union_length(intervals):
    """Measure duration without double-counting duplicated diarization regions."""
    if not intervals:
        return 0.0
    total = 0.0
    left, right = sorted(intervals)[0]
    for a, b in sorted(intervals)[1:]:
        if a > right:
            total += right-left
            left, right = a, b
        else:
            right = max(right, b)
    return total + right-left


class IntervalIndex:
    """Start-sorted interval lookup with monotonic prefix-max ends.

    Bisecting the raw end array is invalid for overlapping Regular intervals:
    sorted starts do NOT imply sorted ends.
    """

    def __init__(self, regions):
        self.regions = []
        for r in regions:
            a, b = _validate_time(r["start"], r["end"])
            speaker = str(r["speaker_id"])
            if not speaker or speaker == "None":
                raise ValueError("Missing diarization speaker")
            self.regions.append((a, b, speaker))
        self.regions.sort(key=lambda r: (r[0], r[1], r[2]))
        self.starts = [r[0] for r in self.regions]
        self.prefix_max_end = []
        largest = -1.0
        for _, end, _ in self.regions:
            largest = max(largest, end)
            self.prefix_max_end.append(largest)
        speakers = dict.fromkeys(r[2] for r in self.regions)
        self.labels = {s: "話者" + str(i+1) for i, s in enumerate(speakers)}

    def overlapping(self, start, end):
        start, end = _validate_time(start, end, allow_zero=True)
        if start == end:
            return []
        first = bisect_right(self.prefix_max_end, start)
        stop = bisect_left(self.starts, end)
        return [(max(start, a), min(end, b), s)
                for a, b, s in self.regions[first:stop] if b > start]

    def nearest(self, start, end):
        """Only a review suggestion; never assigns a speaker from nearby silence."""
        center = (start + end)/2
        if not self.regions:
            return None
        best = min(self.regions, key=lambda r: (max(r[0]-center, 0, center-r[1]), r[0], r[2]))
        d = max(best[0]-center, 0, center-best[1])
        return {"speaker_candidate": self.labels[best[2]], "distance_seconds": round(d, 6)}


def extract_words(asr_segments):
    words = []
    for seg in asr_segments:
        pieces = seg.get("words") or ([seg] if str(seg.get("text", "")).strip() else [])
        for piece in pieces:
            value = str(piece.get("text", ""))
            if not value.strip():
                continue
            a, b = _validate_time(piece["start"], piece["end"], allow_zero=True)
            origin = str(piece.get("timing_origin", "aligned_unverified"))
            if origin not in ALLOWED_ORIGINS:
                raise ValueError("Unrecognized timing provenance")
            words.append({"start": a, "end": b, "text": value, "timing_origin": origin})
    if not words:
        raise ValueError("Missing timed ASR words")
    return words


def annotate_words(asr_segments, diarization, *, minimum_coverage=0.55,
                   minimum_share=0.70):
    """Emit conservative attribution, candidate and reason codes.

    No nearest-speaker assignment. Unknown text remains in output and scores.
    'realigned' is a provenance flag, not proof of timestamp correctness.
    """
    if not (0 <= minimum_coverage <= 1 and 0.5 < minimum_share <= 1):
        raise ValueError("Invalid conservative attribution thresholds")
    index = IntervalIndex(diarization)
    out = []
    for word in extract_words(asr_segments):
        start, end = word["start"], word["end"]
        origin = word["timing_origin"]
        intersects = index.overlapping(start, end)
        by_speaker = defaultdict(list)
        for a, b, speaker in intersects:
            if b > a:
                by_speaker[speaker].append((a, b))
        durations = {s: _union_length(spans) for s, spans in by_speaker.items()}
        length = end-start
        all_duration = _union_length([(a, b) for a, b, _ in intersects])
        coverage = min(1.0, all_duration/length) if length else 0.0
        ranked = sorted(durations, key=lambda s: (-durations[s], index.labels[s]))
        best = ranked[0] if ranked else None
        total_vote = sum(durations.values())
        share = durations[best]/total_vote if total_vote else None
        reasons = []
        if length < 0.05:
            reasons.append("short_or_zero_timestamp")
        if origin != "aligned_unverified":
            reasons.append("timing_" + origin)
        if not ranked:
            reasons.append("no_speaker_overlap")
        if ranked and coverage < minimum_coverage:
            reasons.append("low_time_coverage")
        if len(ranked) > 1:
            reasons.append("multiple_speakers_active")
        if share is not None and share < minimum_share:
            reasons.append("ambiguous_speaker_vote")
        # A small synthetic end-of-file stamp must not force attribution.
        abstain = (not ranked or length < 0.05 or origin in ("estimated", "invalid")
                   or coverage < minimum_coverage or (share is not None and share < minimum_share))
        out.append({**word, "speaker": UNKNOWN if abstain else index.labels[best],
                    "speaker_candidate": index.labels[best] if best else None,
                    "time_coverage_ratio": round(coverage, 6),
                    "overlap_share_not_probability": round(share, 6) if share is not None else None,
                    "review_reasons": reasons,
                    "nearest_review_only": index.nearest(start, end) if not ranked else None})
    return out


def group_words(words, *, max_chars=110, max_seconds=22, max_pause=1.5):
    """Keep lexical sequence; never reorder tokens to manufacture time precision."""
    if not words:
        return []
    rows = []
    current = None
    for word in words:
        start, end = word["start"], word["end"]
        speaker, text = word["speaker"], word["text"]
        if (current is not None and
            (current["speaker"] != speaker or start-current["end"] > max_pause
             or end-current["start"] > max_seconds
             or len(current["text"])+len(text) > max_chars)):
            rows.append(current)
            current = None
        if current is None:
            current = {"start": start, "end": end, "speaker": speaker, "text": text}
        else:
            current["end"] = max(current["end"], end)
            current["text"] += text
    if current:
        rows.append(current)
    return rows


def _same_text(rows, frozen):
    return normalized_ja("".join(r["text"] for r in rows)) == frozen


def _rate(reference, rows):
    result = permutation_cer(reference, rows)
    return {"cpcer": result["cpcer"],
            "edit_distance": result["edit_distance"],
            "reference_characters": result["reference_characters"],
            "hypothesis_characters": result["hypothesis_characters"],
            "unassigned_characters": result["unassigned_characters"],
            "hypothesis_speakers": result["hypothesis_speakers"]}


def compare_arms(reference, asr_segments, exclusive, *, regular=None, oracle=False):
    """Frozen text and timestamps across attribution arms.

    Oracle uses human TURN regions as speaker activity. This is NOT oracle
    word timing, nor product accuracy, particularly in overlapping turns.
    """
    words = extract_words(asr_segments)
    frozen = normalized_ja("".join(w["text"] for w in words))
    if not frozen:
        raise ValueError("Empty normalized transcript")
    legacy, _, count = assign_and_group(asr_segments, exclusive, True)
    if count != len(words) or not _same_text(legacy, frozen):
        raise ValueError("Legacy attribution reordered/lost text; cannot isolate attribution")
    alternatives = {"legacy_exclusive": (legacy, None)}
    alternatives["conservative_exclusive"] = (
        None, annotate_words(asr_segments, exclusive))
    if regular is not None:
        alternatives["conservative_regular"] = (
            None, annotate_words(asr_segments, regular))
    if oracle:
        alternatives["human_turn_regions_diagnostic_only"] = (
            None, annotate_words(asr_segments, reference_to_regions(reference)))
    outputs = {}
    for key, (rows, annotated) in alternatives.items():
        if annotated is not None:
            rows = group_words(annotated)
        if not _same_text(rows, frozen):
            raise ValueError("Attribution arm changed normalized ASR text")
        # The cpCER evaluator chronologically sorts utterances. A time inversion
        # can silently change its lexical sequence, so refuse such comparisons.
        chronological = sorted(rows, key=lambda r: (r["start"], r["end"]))
        if not _same_text(chronological, frozen):
            raise ValueError("Timestamp ordering altered the evaluated transcript")
        metrics = _rate(reference, rows)
        if annotated is not None:
            reason_counts = Counter(reason for w in annotated for reason in w["review_reasons"])
            metrics.update({
                "review_word_count": sum(bool(w["review_reasons"]) for w in annotated),
                "abstained_word_count": sum(w["speaker"] == UNKNOWN for w in annotated),
                "abstained_normalized_characters": sum(
                    len(normalized_ja(w["text"])) for w in annotated if w["speaker"] == UNKNOWN),
                "review_reason_counts": dict(sorted(reason_counts.items())),
                "timing_origin_counts": dict(sorted(Counter(w["timing_origin"] for w in annotated).items()))})
        outputs[key] = metrics
    reference_flat = "".join(r["text"] for r in sorted(reference,
        key=lambda t: (t["start"], t["end"], t["speaker_id"])))
    flat = evaluate(reference_flat, "".join(w["text"] for w in words))
    return {
        "method": "paired speaker attribution with fixed ASR text and word timestamps",
        "normalized_asr_sha256": hashlib.sha256(frozen.encode("utf-8")).hexdigest(),
        "word_count": len(words),
        "flattened_cer": flat["normalized_cer"],
        "flattened_cer_warning": "Time-sorted ELAN turn text; overlap changes reference ordering",
        "arms": outputs,
        "warning": "cpCER minus CER is not a speaker error estimate. Human-turn arms are diagnostic only; no forced aligner precision is implied."}


def reference_to_regions(reference):
    return [{"start": r["start"], "end": r["end"], "speaker_id": r["speaker_id"]}
            for r in reference if r["end"] > r["start"]]


def _read_segments(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    return obj["segments"] if isinstance(obj, dict) else obj


def compare_frozen_timing(reference, original, alternative, exclusive):
    """Timing-only comparison; same source characters AND same lexical token units."""
    first, second = extract_words(original), extract_words(alternative)
    if len(first) != len(second) or any(
        a["text"] != b["text"] for a, b in zip(first, second)
    ):
        raise ValueError("Timing comparison changes words; refuses confounded result")
    return {"before": compare_arms(reference, original, exclusive)["arms"]["conservative_exclusive"],
            "after": compare_arms(reference, alternative, exclusive)["arms"]["conservative_exclusive"],
            "word_count": len(first),
            "warning": "No human word timestamps: change in cpCER is a downstream diagnostic, not timing accuracy."}


def mark_qwen_timing_origins(chunks, segments, duration):
    """Annotate aligner provenance WITHOUT claiming accuracy or changing times.

    Only direct aligner output is 'aligned_unverified'. Equal-length lexical
    substitutions are 'realigned'; end-of-file placeholders are 'estimated'.
    Invalid tokens should already be rejected by qwen_segments.
    """
    result = [{**s, "words": [dict(w) for w in s["words"]]} for s in segments]
    cursor = 0
    for chunk in chunks:
        items = chunk.get("items") or []
        if not items:
            continue
        if cursor >= len(result) or len(items) != len(result[cursor]["words"]):
            raise ValueError("Chunk-to-alignment token mapping cannot be proven")
        realigned = normalized_ja(chunk["text"]) != normalized_ja(
            "".join(str(item["text"]) for item in items))
        for word, raw in zip(result[cursor]["words"], items):
            offset = float(chunk["offset_sec"])
            onset = float(raw["start_time"])
            raw_end = max(onset+0.01, float(raw["end_time"]))
            # Exactly mirror qwen_segments' clamping/rounding trigger.
            clamped_a = round(max(0.0, offset+onset), 3)
            clamped_b = round(min(float(duration), offset+raw_end), 3)
            tail_placeholder = clamped_b <= clamped_a
            word["timing_origin"] = ("estimated" if tail_placeholder
                                     else "realigned" if realigned
                                     else "aligned_unverified")
        cursor += 1
    if cursor != len(result):
        raise ValueError("Unmapped aligned segment, cannot attest provenance")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eaf", type=Path, required=True)
    p.add_argument("--speaker-tiers", nargs="+", help="explicit 2-4 speaker ELAN tier IDs")
    p.add_argument("--qwen", type=Path, required=True,
                   help="private JSON with duration_seconds and chunks")
    p.add_argument("--exclusive", type=Path, required=True)
    p.add_argument("--regular", type=Path)
    p.add_argument("--timing-alternative", type=Path,
                   help="private JSON matching original lexical word units")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    reference, reference_sha, reference_meta = load_meeting_eaf(
        a.eaf, speaker_tiers=a.speaker_tiers)
    raw = json.loads(a.qwen.read_text(encoding="utf-8"))
    segments, integrity = qwen_segments(raw["chunks"], raw["duration_seconds"],
        speech_end_seconds=raw.get("speech_end_seconds"))
    segments = mark_qwen_timing_origins(raw["chunks"], segments, raw["duration_seconds"])
    exclusive = _read_segments(a.exclusive)
    regular = _read_segments(a.regular) if a.regular else None
    result = compare_arms(reference, segments, exclusive, regular=regular, oracle=True)
    result["reference_sha256"] = reference_sha
    result["reference_metadata"] = reference_meta
    result["alignment_integrity"] = integrity
    if a.timing_alternative:
        alt = json.loads(a.timing_alternative.read_text(encoding="utf-8"))
        alt_segments, _ = qwen_segments(alt["chunks"], alt["duration_seconds"],
            speech_end_seconds=alt.get("speech_end_seconds"))
        alt_segments = mark_qwen_timing_origins(alt["chunks"], alt_segments, alt["duration_seconds"])
        result["timing_comparison"] = compare_frozen_timing(reference, segments, alt_segments, exclusive)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reference_sha256": reference_sha, "word_count": result["word_count"],
                      "arms": {k: v["cpcer"] for k, v in result["arms"].items()},
                      "timing_comparison": "timing_comparison" in result}, sort_keys=True))


if __name__ == "__main__":
    main()
