"""Strict research ELAN reader for independent 2-4-speaker Japanese meetings.

The older IngCrowd parser intentionally accepts only speaker_1 and speaker_2.
This parser also accepts an explicit list of tier IDs, and never assumes a
media file or a reference is licensed for commercial/Modal processing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def load_meeting_eaf(path: Path, *, speaker_tiers=None):
    raw = Path(path).read_bytes()
    if (not raw or len(raw) > 4*1024*1024
            or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper()):
        raise ValueError("Unsafe or oversized EAF")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("Invalid EAF XML") from error
    if root.tag != "ANNOTATION_DOCUMENT":
        raise ValueError("Expected ELAN annotation document")
    slot_nodes = root.findall("./TIME_ORDER/TIME_SLOT")
    stamps = {}
    for node in slot_nodes:
        key, value = node.get("TIME_SLOT_ID"), node.get("TIME_VALUE")
        if key is None or value is None or not value.isdecimal():
            raise ValueError("Invalid ELAN time slot")
        if key in stamps:
            raise ValueError("Duplicate ELAN time slot")
        stamps[key] = int(value) / 1000.0
    if not stamps:
        raise ValueError("Missing ELAN timestamps")

    tiers = root.findall("./TIER")
    ids = [tier.get("TIER_ID") for tier in tiers]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate or missing ELAN tiers")
    selected = list(speaker_tiers) if speaker_tiers is not None else [
        name for name in ids if name and re.fullmatch(r"speaker_[1-4]", name)]
    if len(selected) not in (2, 3, 4) or len(set(selected)) != len(selected):
        raise ValueError("Require distinct 2-4 human speaker tiers")
    if set(selected) - set(ids):
        raise ValueError("Selected human speaker tier not present")
    out = []
    for tier in tiers:
        speaker = tier.get("TIER_ID")
        if speaker not in selected:
            continue
        for annotation in tier.findall(".//ALIGNABLE_ANNOTATION"):
            a = stamps.get(annotation.get("TIME_SLOT_REF1"))
            b = stamps.get(annotation.get("TIME_SLOT_REF2"))
            if a is None or b is None or b <= a:
                raise ValueError("Missing or nonpositive human reference interval")
            raw_text = (annotation.findtext("ANNOTATION_VALUE") or "").strip()
            text = re.sub(r"<[^>]+>", "", raw_text)
            out.append({"start": a, "end": b,
                        "speaker_id": speaker, "text": text})
    used = {r["speaker_id"] for r in out}
    if used != set(selected):
        raise ValueError("Speaker tier has no human reference turns")
    if len(out) < len(selected):
        raise ValueError("Missing human reference")
    out.sort(key=lambda r: (r["start"], r["end"], r["speaker_id"]))
    return out, hashlib.sha256(raw).hexdigest(), {
        "reference_speakers": len(selected),
        "reference_turns": len(out),
        "tier_names_sha256": hashlib.sha256(
            "\n".join(sorted(selected)).encode("utf-8")).hexdigest(),
        "warning": "Human turn intervals are NOT word-level timestamps; lexical reference may have annotator omissions."}
