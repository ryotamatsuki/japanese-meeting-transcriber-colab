"""Human ELAN reference diagnostic: theoretical DER floor of exclusive-only diarization.

For two *different* simultaneous speakers, any system constrained to one
speaker at a time must miss at least one speaker-second for each second of
overlap. This lower bound is independent of speaker IDs and pyannote.
NO transcripts or audio are written.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from scripts.eval_elan_ja import load_elan


def overlap_floor(rows):
    """Piecewise integral of per-speaker activity using an O(NlogN) sweep."""
    if not rows:
        raise ValueError("Empty reference")
    by_speaker = {}
    for row in rows:
        a, b = float(row['start']), float(row['end'])
        speaker = str(row['speaker_id'])
        if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b):
            raise ValueError("Invalid reference interval")
        by_speaker.setdefault(speaker, []).append((a,b))
    events = []
    for speaker, pieces in by_speaker.items():
        merged=[]
        for a,b in sorted(pieces):
            if merged and a <= merged[-1][1]:
                merged[-1]=(merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a,b))
        for a,b in merged:
            events.append((a, 1))
            events.append((b,-1))
    events.sort(key=lambda v:v[0])
    active=0
    prev=events[0][0]
    union=0.0
    speaker_seconds=0.0
    overlap=0.0
    for time,change in events:
        duration=time-prev
        if active>0:
            union+=duration
            speaker_seconds+=active*duration
            if active>1:
                overlap+=(active-1)*duration
        active+=change
        prev=time
    if active:
        raise AssertionError("Unbalanced intervals")
    return {
        "speaker_count":len(by_speaker),
        "reference_speaker_seconds":round(speaker_seconds,6),
        "speech_union_seconds":round(union,6),
        "overlap_excess_speaker_seconds":round(overlap,6),
        "exclusive_diarization_der_floor_percent":round(100*overlap/speaker_seconds,6),
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eaf",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    rows,digest=load_elan(args.eaf)
    record=overlap_floor(rows)
    record["reference_eaf_sha256"]=digest
    record["annotation_turns"]=len(rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(record,sort_keys=True))


if __name__=="__main__":
    main()
