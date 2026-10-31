"""Meeting-clustered paired evaluation: metrics only, no audio or speech text.

An independent observation is a MEETING, not each word, utterance or chunk.
Bootstrap percentile intervals are descriptive, especially at small N.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import random
from statistics import mean


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Nonfinite or nonnumeric metric")
    return float(value)


def paired_meeting_report(rows, *, metric="cpcer", samples=5000, seed=20261031):
    if type(samples) is not int or not 1000 <= samples <= 100000:
        raise ValueError("Invalid bootstrap count")
    if not rows:
        raise ValueError("No paired evaluation records")
    seen = set()
    groups = defaultdict(list)
    split_by_meeting = {}
    for row in rows:
        mid, rid = str(row["meeting_id"]), str(row["recording_id"])
        if not mid.strip() or not rid.strip() or (mid, rid) in seen:
            raise ValueError("Missing/duplicate meeting-recording pair")
        seen.add((mid, rid))
        split = row.get("split", "development")
        if split not in ("development", "heldout"):
            raise ValueError("Invalid split")
        if mid in split_by_meeting and split_by_meeting[mid] != split:
            raise ValueError("A meeting cannot cross development and heldout")
        split_by_meeting[mid] = split
        before, after = _number(row["baseline"][metric]), _number(row["candidate"][metric])
        if not (0 <= before <= 5 and 0 <= after <= 5):
            raise ValueError("Unexpected CER range")
        groups[mid].append(after-before)

    per_meeting = {mid: mean(deltas) for mid, deltas in groups.items()}
    names = sorted(per_meeting)
    diffs = [per_meeting[mid] for mid in names]
    n = len(diffs)
    point = mean(diffs)
    result = {
        "metric": metric,
        "sign": "candidate minus baseline; negative improves",
        "n_independent_meetings": n,
        "n_recordings": len(rows),
        "n_development_meetings": sum(split_by_meeting[mid] == "development" for mid in names),
        "n_heldout_meetings": sum(split_by_meeting[mid] == "heldout" for mid in names),
        "mean_delta": point,
        "improved_meetings": sum(x < 0 for x in diffs),
        "worsened_meetings": sum(x > 0 for x in diffs),
        "equal_meetings": sum(x == 0 for x in diffs),
        "worst_meeting_regression": max(diffs),
        "best_meeting_improvement": min(diffs),
        "warning": "Exploratory percentile cluster bootstrap, not a product approval or adjustment for repeated development trials."}
    if n < 2:
        result["ci95"] = None
        result["decision"] = "INSUFFICIENT_MEETINGS"
        return result
    rng = random.Random(seed)
    boot = sorted(mean(diffs[rng.randrange(n)] for _ in range(n))
                  for _ in range(samples))
    lo = boot[int(.025*(samples-1))]
    hi = boot[int(.975*(samples-1))]
    result["ci95"] = [lo, hi]
    result["bootstrap_samples"] = samples
    result["leave_one_meeting_out_deltas"] = {
        mid: mean([per_meeting[other] for other in names if other != mid])
        for mid in names} if n > 2 else None
    result["decision"] = ("EXPLORATORY_ONLY" if n < 20 or result["n_heldout_meetings"] < 20
                          else "ELIGIBLE_FOR_PRE_REGISTERED_GATE_REVIEW")
    return result


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True,
                   help="private metric-only JSON list of paired meeting records")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--metric", default="cpcer")
    p.add_argument("--samples", type=int, default=5000)
    a = p.parse_args()
    rows = json.loads(a.input.read_text(encoding="utf-8"))
    result = paired_meeting_report(rows, metric=a.metric, samples=a.samples)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps({k: result[k] for k in
                      ("metric", "n_independent_meetings", "mean_delta", "ci95", "decision")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
