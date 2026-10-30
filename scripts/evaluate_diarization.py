"""Evaluate speaker diarization against independently annotated RTTM ground truth.

This script deliberately refuses to report DER/JER without an RTTM.
Install pyannote.metrics in the evaluation environment. A known speaker
count or transcript subtitles are *not* timestamped speaker ground truth.
"""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile


def load_rttm(path):
    """Return (start, end, speaker) tuples from standard SPEAKER RTTM rows."""
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 10 or parts[0] != "SPEAKER":
            raise ValueError(f"Invalid RTTM SPEAKER row at line {number}")
        start, duration = float(parts[3]), float(parts[4])
        if not (start >= 0 and duration > 0 and parts[7]):
            raise ValueError(f"Invalid RTTM interval at line {number}")
        rows.append({"start": start, "end": start + duration, "speaker_id": parts[7]})
    if not rows:
        raise ValueError("No RTTM speaker annotations supplied")
    return rows


def annotation(intervals, name):
    from pyannote.core import Annotation, Segment
    ann = Annotation(uri=name)
    for idx, seg in enumerate(intervals):
        ann[Segment(seg["start"], seg["end"]), idx] = seg["speaker_id"]
    return ann


def compare(reference_rows, candidate_rows, collar=0.0):
    from pyannote.metrics.diarization import DiarizationErrorRate, JaccardErrorRate
    ref, hyp = annotation(reference_rows, "reference"), annotation(candidate_rows, "hypothesis")
    # Collar fixed by caller; overlapping speech is not suppressed.
    der = DiarizationErrorRate(collar=collar, skip_overlap=False)
    jer = JaccardErrorRate(collar=collar, skip_overlap=False)
    score = der(ref, hyp, detailed=True)
    return {"der_percent": float(score["diarization error rate"] * 100),
            "jer_percent": float(jer(ref, hyp) * 100),
            "collar_seconds": collar, "skip_overlap": False,
            "false_alarm_seconds": float(score["false alarm"]),
            "missed_detection_seconds": float(score["missed detection"]),
            "speaker_confusion_seconds": float(score["confusion"]),
            "reference_speaker_count": len({s["speaker_id"] for s in reference_rows}),
            "candidate_speaker_count": len({s["speaker_id"] for s in candidate_rows})}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rttm", type=Path, required=True,
                   help="Human-verified speaker-labelled reference RTTM")
    p.add_argument("--zip", dest="archive", type=Path, required=True)
    p.add_argument("--candidate", choices=["exclusive", "unmodified", "standard"],
                   default="exclusive")
    p.add_argument("--collar", type=float, default=0.0, choices=[0.0, 0.25])
    args = p.parse_args()
    files = {"exclusive":"pyannote_話者区間.json",
             "unmodified":"pyannote_補正前話者区間.json",
             "standard":"pyannote_通常話者区間.json"}
    with ZipFile(args.archive) as z:
        predicted = json.loads(z.read(files[args.candidate]))["segments"]
    result = compare(load_rttm(args.rttm), predicted, args.collar)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
