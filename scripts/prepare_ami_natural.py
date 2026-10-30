"""Prepare no-signup AMI real 3/4 person meetings for blinded diarization evaluation.

Human NXT word timings are used strictly as an approximate speech-activity
reference. Do not claim word-timing-derived DER equals manually labeled RTTM.
The meetings are in ENGLISH: this cannot certify Japanese ASR/CER/cpCER.
Source CC BY 4.0: https://groups.inf.ed.ac.uk/ami/download/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

MEETINGS = {"EN2003a": 3, "EN2004a": 4}
ANNOT_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"
AUDIO_ROOT = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
MAX_AUDIO_BYTES = 160_000_000


def download(url: str, target: Path, *, limit: int):
    if not url.startswith("https://groups.inf.ed.ac.uk/ami/"):
        raise ValueError("Only official AMI source is allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "Meeting-Research-Diarization/1.0"})
    with urllib.request.urlopen(request, timeout=160) as resp, target.open("wb") as out:
        size = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError("AMI source exceeded capped download size")
            out.write(chunk)
    if not size:
        raise ValueError("Empty AMI source file")


def parse_word_times(zip_file: ZipFile, meeting: str) -> list[dict]:
    word_files = [p for p in zip_file.namelist()
                  if re.search(rf"(?:^|/){re.escape(meeting)}\.[A-D]\.words\.xml$", p)]
    if len(word_files) != 4:
        raise ValueError("Expected four AMI speaker channels including empty ones")
    rows = []
    for p in sorted(word_files):
        speaker = re.search(r"\.([A-D])\.words\.xml$", p).group(1)
        raw = zip_file.read(p)
        if len(raw) > 15_000_000 or b"<!ENTITY" in raw.upper() or b"<!DOCTYPE" in raw.upper():
            raise ValueError("Unexpected XML content")
        root = ET.fromstring(raw)
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "w":
                continue
            try:
                a, b = float(element.attrib["starttime"]), float(element.attrib["endtime"])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= 10800:
                rows.append({"start": a, "end": b, "speaker_id": speaker})
    return sorted(rows, key=lambda r: (r["start"], r["end"], r["speaker_id"]))


def choose_real_window(words: list[dict], expected: int, window: int = 300):
    speakers = {w["speaker_id"] for w in words}
    if len(speakers) != expected:
        raise ValueError(f"Human annotation speaker count {len(speakers)} != {expected}")
    if not words or max(w["end"] for w in words) < window:
        raise ValueError("Meeting too short")
    best = None
    for start in range(0, int(max(w["end"] for w in words) - window) + 1, 60):
        chosen = [w for w in words if w["start"] < start+window and w["end"] > start]
        counts = Counter(w["speaker_id"] for w in chosen)
        if len(counts) != expected or min(counts.values()) < 30:
            continue
        score = (min(counts.values()), len(chosen))
        if best is None or score > best[0]:
            best = (score, start, chosen, counts)
    if best is None:
        raise ValueError("No five-minute window with active all human-annotated speakers")
    _, start, chosen, counts = best
    # Word-timestamp reference is NOT hand-corrected RTTM speaker-turn boundaries.
    # Merge close words of same speaker but preserve all true cross-speaker overlap.
    per_sp = defaultdict(list)
    for w in chosen:
        a = round(max(w["start"], start)-start, 3)
        b = round(min(w["end"], start+window)-start, 3)
        if 0 <= a < b <= window:
            per_sp[w["speaker_id"]].append((a, b))
    intervals = []
    for sid, seq in per_sp.items():
        seq.sort()
        if not seq:
            continue
        a, b = seq[0]
        for x, y in seq[1:]:
            if x <= b + 0.15:
                b = max(b, y)
            else:
                intervals.append((a, b, sid))
                a, b = x, y
        intervals.append((a, b, sid))
    intervals.sort()
    if len(intervals) < expected * 10:
        raise ValueError("Insufficient reference turns")
    return start, intervals, dict(counts)


def prepare(meeting: str, root: Path, ffmpeg: str):
    if meeting not in MEETINGS:
        raise ValueError("Only preregistered natural meetings are allowed")
    root.mkdir(parents=True, exist_ok=True)
    annotations = root / "manual_1.6.2.zip"
    if not annotations.exists():
        download(ANNOT_URL, annotations, limit=40_000_000)
    with ZipFile(annotations) as z:
        words = parse_word_times(z, meeting)
    start, turns, counts = choose_real_window(words, MEETINGS[meeting])
    source = root / f"{meeting}.Mix-Headset.wav"
    audio_url = f"{AUDIO_ROOT}/{meeting}/audio/{meeting}.Mix-Headset.wav"
    download(audio_url, source, limit=MAX_AUDIO_BYTES)
    clip = root / f"{meeting}.mp3"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-y", "-ss", str(start), "-t", "300", "-i", str(source),
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame",
                    "-b:a", "64k", str(clip)], check=True, timeout=150)
    if not (200_000 < clip.stat().st_size < 25*1024*1024):
        raise ValueError("Invalid trimmed meeting audio")
    source.unlink()
    rttm = root / f"{meeting}.rttm"
    rttm.write_text("".join(f"SPEAKER {meeting} 1 {a:.3f} {b-a:.3f} <NA> <NA> {sid} <NA> <NA>\n"
                            for a, b, sid in turns), encoding="utf-8")
    info = {
        "meeting_id": meeting,
        "language": "en",
        "meeting_type": "naturally_occurring_not_scenario",
        "reference_type": "human_NXT_word_timing_derived_proxy_RTTM",
        "human_speaker_count": MEETINGS[meeting],
        "speech_word_counts": counts,
        "reference_intervals": len(turns),
        "clip_source_start_seconds": start,
        "clip_seconds": 300,
        "audio_sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
        "rttm_sha256": hashlib.sha256(rttm.read_bytes()).hexdigest(),
        "license": "CC BY 4.0",
        "reference": "https://groups.inf.ed.ac.uk/ami/download/",
        "limitation": "English meetings, human word timestamps as diarization proxy; not Japanese recognition benchmark",
    }
    (root / f"{meeting}.metadata.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True, choices=sorted(MEETINGS))
    parser.add_argument("--out", type=Path, default=Path("local_audio/ami"))
    parser.add_argument("--ffmpeg", required=True)
    args = parser.parse_args()
    record = prepare(args.meeting, args.out, args.ffmpeg)
    print("AMI_SOURCE_VERIFIED", json.dumps({
        k:record[k] for k in ("meeting_id", "language", "human_speaker_count",
                             "reference_intervals", "clip_seconds", "speech_word_counts",
                             "clip_source_start_seconds")}, sort_keys=True))


if __name__ == "__main__":
    main()
