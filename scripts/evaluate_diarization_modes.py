"""Paired reference evaluation of Community-1 exclusive vs ordinary diarization.

This tool does not make speaker identification claims, and does not print audio
or speech transcripts. Original source and model weights are held fixed.
"""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.eval_elan_ja import load_elan
from scripts.evaluate_diarization import compare
from scripts.analyze_reference_overlap import overlap_floor


def evaluate_pair(eaf: Path, archive: Path):
    reference, ref_sha = load_elan(eaf)
    with ZipFile(archive) as z:
        names = set(z.namelist())
        required = {"pyannote_話者区間.json", "pyannote_通常話者区間.json"}
        if not required.issubset(names):
            raise ValueError("Both modes must come from the SAME quality-experiment run")
        exclusive = json.loads(z.read("pyannote_話者区間.json"))["segments"]
        regular = json.loads(z.read("pyannote_通常話者区間.json"))["segments"]
    a = compare(reference, exclusive, collar=0.0)
    b = compare(reference, regular, collar=0.0)
    result = {
        "reference_eaf_sha256": ref_sha,
        "reference_turn_count": len(reference),
        "reference_overlap_floor": overlap_floor(reference),
        "exclusive_intervals": len(exclusive),
        "regular_intervals": len(regular),
        "exclusive": a,
        "regular": b,
        "der_regular_minus_exclusive_percentage_points": b["der_percent"]-a["der_percent"],
        "jer_regular_minus_exclusive_percentage_points": b["jer_percent"]-a["jer_percent"],
        "same_model": "pyannote/speaker-diarization-community-1",
        "oracle_speaker_count": 2,
        "collar_seconds": 0.0,
        "skip_overlap": False,
        "source_license": "IngCrowd CC BY-NC 4.0, noncommercial evaluation only",
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eaf", required=True, type=Path)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate_pair(args.eaf,args.zip)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    # Numeric metrics only. Never print original text or raw model outputs.
    print(json.dumps({
        "reference_eaf_sha256":result["reference_eaf_sha256"],
        "exclusive_der":result["exclusive"]["der_percent"],
        "regular_der":result["regular"]["der_percent"],
        "exclusive_jer":result["exclusive"]["jer_percent"],
        "regular_jer":result["regular"]["jer_percent"]
    }))


if __name__ == "__main__":
    main()
