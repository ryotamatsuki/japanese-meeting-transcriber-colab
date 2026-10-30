"""Small dependency-free Japanese ASR CER evaluator for frozen reference subtitles.

A third-party subtitle is a *weak* reference and may paraphrase dialect speech.
Do not interpret CER as human-verified word accuracy or cpCER.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from zipfile import ZipFile


def srt_text(content: str) -> str:
    lines = []
    for line in content.splitlines():
        value = line.strip()
        if not value or value.isdecimal() or re.match(r"^\d\d:\d\d:\d\d[,\.]\d+\s+-->", value):
            continue
        lines.append(re.sub(r"^\s*-\s*", "", value))
    return "".join(lines)


def normalized_ja(text: str) -> str:
    expanded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in expanded if not ch.isspace()
                   and not unicodedata.category(ch).startswith(("P", "S")))


def edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ch in enumerate(a, 1):
        row = [i]
        for j, other in enumerate(b, 1):
            row.append(min(row[-1] + 1, prev[j] + 1, prev[j-1] + (ch != other)))
        prev = row
    return prev[-1]


def evaluate(reference: str, hypothesis: str) -> dict:
    ref = normalized_ja(reference)
    hyp = normalized_ja(hypothesis)
    if not ref:
        raise ValueError("Empty normalized reference")
    errors = edit_distance(ref, hyp)
    return {
        "normalized_cer": errors / len(ref),
        "edit_distance": errors,
        "reference_characters": len(ref),
        "hypothesis_characters": len(hyp),
        "normalization": "NFKC+casefold; strip whitespace and Unicode punctuation/symbols",
        "reference_warning": "Wikimedia volunteer subtitles, not expert verbatim meeting ground truth",
    }


def read_asr(archive: Path) -> str:
    with ZipFile(archive) as z:
        record = json.loads(z.read("whisper_asr.json"))
        return "".join(s.get("text", "") for s in record["segments"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference-srt", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    raw = args.reference_srt.read_bytes()
    reference = srt_text(raw.decode("utf-8-sig"))
    result = {
        "reference_source": "https://commons.wikimedia.org/wiki/TimedText:Kyoto_women_conversation_in_1964.ogg.ja.srt",
        "reference_sha256": hashlib.sha256(raw).hexdigest(),
        "baseline": evaluate(reference, read_asr(args.baseline)),
        "candidate": evaluate(reference, read_asr(args.candidate)),
    }
    result["candidate_beats_baseline_on_this_excerpt"] = (
        result["candidate"]["normalized_cer"] < result["baseline"]["normalized_cer"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
