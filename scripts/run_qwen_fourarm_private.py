"""Private OFFLINE four-arm study using original Qwen transcription ZIP and audio.

Requires actual user-authorized audio + same recording's Qwen transcript.
Reference/human labels are loaded ONLY AFTER all four arms have finished.
Never uploads audio to GitHub. Local LLM endpoint only by default.

Example:
  python scripts/run_qwen_fourarm_private.py --archive original.zip \
    --audio original.mp3 --record-id pilot-01 \
    --endpoint http://127.0.0.1:8000/v1/chat/completions \
    --out /private/fourarm.json --annotation /private/worksheet.json
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from beta.core import parse_original_archive
from scripts.qwen_boundary_fourarm import (
    MODEL, audio_features, candidate_universe, evaluate_four_arms,
    label_template, score_four_arms,
)
from scripts.jcre3_boundary_adjudication import verified_labels_from_review
from scripts.qwen_text_boundary_cli import local_or_secure, request_qwen


def decode_mono_pcm(audio_path: Path):
    """Exact 16k mono s16 PCM; input never read from untrusted URL."""
    if audio_path.suffix.lower() not in {".wav",".mp3",".m4a",".flac",".ogg"}:
        raise ValueError("Unapproved audio extension")
    if not audio_path.is_file() or audio_path.stat().st_size > 180*1024*1024:
        raise ValueError("Invalid audio input")
    command=["ffmpeg","-nostdin","-v","error","-i",str(audio_path),
             "-map","0:a:0","-ac","1","-ar","16000","-f","s16le","-"]
    result=subprocess.run(command,capture_output=True,timeout=240,check=False)
    if result.returncode!=0 or not 0 < len(result.stdout) <= 120*1024*1024:
        raise ValueError("Audio decoding failure")
    if len(result.stdout)%2:
        raise ValueError("Unaligned PCM bytes")
    raw=array("h")
    raw.frombytes(result.stdout)
    if sys.byteorder!="little":
        raw.byteswap()
    # array('h') suffices for RMS; convert to float only around each boundary
    # using a scaled sequence view to avoid >50 MB unnecessary conversion.
    class NormalizedPCM:
        def __len__(self):
            return len(raw)
        def __getitem__(self, key):
            if isinstance(key,slice):
                return [x/32768.0 for x in raw[key]]
            return raw[key]/32768.0
    return NormalizedPCM(),len(raw)/16000


def check_audio_pin(path: Path, manifest: Path | None, record_id: str):
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest is not None:
        entries=json.loads(manifest.read_text(encoding="utf-8"))["records"]
        expected={entry["id"]:entry["audio_sha256"] for entry in entries}
        if record_id not in expected or expected[record_id]!=sha:
            raise ValueError("Pinned audio mismatch")
    return sha


def conduct(archive: Path, audio: Path, record_id: str, *, endpoint: str,
            model: str=MODEL, allow_remote=False,
            manifest: Path | None=None, label_sheet: Path | None=None,
            one_reviewer=False):
    local_or_secure(endpoint,allow_remote)
    if not archive.is_file() or archive.stat().st_size > 250*1024*1024:
        raise ValueError("Invalid Qwen archive")
    if not record_id or len(record_id)>120:
        raise ValueError("Invalid record ID")
    rows=parse_original_archive(archive.read_bytes())["rows"]
    candidates=candidate_universe(rows)
    pin=check_audio_pin(audio,manifest,record_id)
    pcm,duration=decode_mono_pcm(audio)
    if any(float(row["end"])>duration+.5 for row in rows):
        raise ValueError("ASR row after audio end")
    feats=audio_features(pcm,16000,rows,candidates)
    result=evaluate_four_arms(
        rows,lambda arm,messages: request_qwen(messages,endpoint=endpoint,
                                               model=model,allow_remote=allow_remote),
        features=feats)
    result["record_id"]=record_id
    result["audio_sha256"]=pin
    result["audio_seconds"]=duration
    result["archive_sha256"]=hashlib.sha256(archive.read_bytes()).hexdigest()
    result["number_of_rows"]=len(rows)
    result["number_of_candidates"]=len(candidates)
    result["candidate_coverage_rate"]=len(candidates)/(len(rows)-1)
    result["source_rows_persisted_unchanged"]=True
    result["model"]=model
    result["audio_representation"]="original input (caller-specified); no unseen guarantee"
    # Do not load gold before predictions are frozen.
    if label_sheet is not None:
        sheet=json.loads(label_sheet.read_text(encoding="utf-8"))
        if sheet.get("record_id")!=record_id:
            raise ValueError("Wrong reference recording")
        labels=verified_labels_from_review(
            sheet,annotators_required=1 if one_reviewer else 2)
        if set(labels)!={str(i) for i in candidates}:
            raise ValueError("Human labels do not cover candidates")
        result["human_scores"]=score_four_arms(result,labels)
        result["labeling_protocol"]=(
            "one_annotator_pilot" if one_reviewer else "two_annotator_adjudicated")
    else:
        result["human_scores"]=None
        result["labeling_protocol"]="no_human_labels_not_scored"
    return result, label_template(record_id,rows,candidates)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--audio",type=Path,required=True)
    p.add_argument("--record-id",required=True)
    p.add_argument("--endpoint",default="http://127.0.0.1:8000/v1/chat/completions")
    p.add_argument("--model",default=MODEL)
    p.add_argument("--manifest",type=Path)
    p.add_argument("--labels",type=Path)
    p.add_argument("--one-reviewer",action="store_true")
    p.add_argument("--allow-remote",action="store_true")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--annotation",type=Path)
    args=p.parse_args()
    if args.out.resolve() in {args.archive.resolve(),args.audio.resolve()}:
        p.error("Never overwrite source audio/archive")
    result,sheet=conduct(args.archive,args.audio,args.record_id,
                         endpoint=args.endpoint,model=args.model,
                         allow_remote=args.allow_remote,manifest=args.manifest,
                         label_sheet=args.labels,one_reviewer=args.one_reviewer)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                        encoding="utf-8")
    if args.annotation is not None:
        if args.annotation.resolve() in {args.audio.resolve(),args.archive.resolve(),args.out.resolve()}:
            p.error("Invalid private annotation output")
        args.annotation.parent.mkdir(parents=True,exist_ok=True)
        args.annotation.write_text(json.dumps(sheet,ensure_ascii=False,indent=2)+"\n",
                                   encoding="utf-8")
    print("FOUR_ARM_PRIVATE_COMPLETE " + json.dumps({
        "candidate_count":result["number_of_candidates"],
        "labeling_protocol":result["labeling_protocol"],
        "audio_sha256":result["audio_sha256"]},sort_keys=True))


if __name__=="__main__":
    main()
