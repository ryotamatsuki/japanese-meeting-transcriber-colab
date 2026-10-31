"""Strict noncommercial research reader for IngCrowd spontaneous Japanese dialogue.

Only use with separately cleared CC BY-NC-4.0 research data. No auto transcript
normalization chosen by looking at model output. Never log reference text.
"""
from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET

ALLOWED_IDS = ("japanese-themed-dialogue01",
               "japanese-themed-dialogue04",
               "japanese-themed-dialogue07")
EXPECTED_LICENSE = "cc-by-nc-4.0"
MAX_EAF_BYTES = 2 * 1024 * 1024
SPEAKERS = ("speaker_1", "speaker_2")
ANNOTATION_TAG = re.compile(r"\((?:F|D|R)\s+([^()]*)\)")


def clean_annotation(s):
    """Remove explicit annotation tags, not spoken filler content."""
    t = ANNOTATION_TAG.sub(r"\1", str(s))
    return t.strip()


def load_ingcrowd_eaf(raw: bytes, *, duration: float):
    if (not 50 < len(raw) <= MAX_EAF_BYTES or b"<!DOCTYPE" in raw.upper()
            or b"<!ENTITY" in raw.upper()):
        raise ValueError("EAF not a bounded trusted XML document")
    if not math.isfinite(duration) or not 30 <= duration <= 1800:
        raise ValueError("Recording duration outside allowed full-length corpus")
    root = ET.fromstring(raw)
    if root.tag != "ANNOTATION_DOCUMENT":
        raise ValueError("Not ELAN EAF")
    header = root.find("HEADER")
    if header is None or header.attrib.get("TIME_UNITS") != "milliseconds":
        raise ValueError("Unexpected EAF time unit")
    slots = {}
    for node in root.findall("./TIME_ORDER/TIME_SLOT"):
        name, value = node.get("TIME_SLOT_ID"), node.get("TIME_VALUE")
        if not name or not value or name in slots:
            raise ValueError("Invalid EAF time slot")
        t = int(value) / 1000
        if not math.isfinite(t) or not 0 <= t <= duration + 1.0:
            raise ValueError("Annotation outside recording")
        slots[name] = t
    if len(slots)<20:
        raise ValueError("Missing timeline annotations")
    all_rows = []
    for tier in root.findall("./TIER"):
        speaker = tier.get("TIER_ID")
        if speaker not in SPEAKERS:
            continue
        for node in tier.findall("./ANNOTATION/ALIGNABLE_ANNOTATION"):
            first = node.get("TIME_SLOT_REF1")
            last = node.get("TIME_SLOT_REF2")
            if first not in slots or last not in slots:
                raise ValueError("Dangling EAF time slot")
            begin, end = slots[first], slots[last]
            if not begin < end:
                raise ValueError("Non-positive annotation interval")
            value = node.find("ANNOTATION_VALUE")
            if value is None:
                raise ValueError("Missing transcript annotation value")
            spoken = clean_annotation("".join(value.itertext()))
            if spoken:
                all_rows.append({"start":begin,"end":end,
                                 "speaker_id":speaker,"text":spoken})
    all_rows.sort(key=lambda x:(x["start"],x["end"],x["speaker_id"]))
    if len(all_rows)<40 or set(x["speaker_id"] for x in all_rows)!=set(SPEAKERS):
        raise ValueError("Not 2-speaker multi-turn human transcription")
    if max(x["end"] for x in all_rows) < duration*0.75:
        raise ValueError("Human transcript covers too little of audio")
    return all_rows, {
        "reference_sha256":hashlib.sha256(raw).hexdigest(),
        "turns":len(all_rows),
        "speakers":2,
        "reference_last_end":max(x["end"] for x in all_rows),
        "has_overlap":any(
            a["start"] < b["end"] and b["start"] < a["end"]
            and a["speaker_id"] != b["speaker_id"]
            for i,a in enumerate(all_rows) for b in all_rows[i+1:i+40])}


def safe_text_metrics(records):
    from scripts.evaluate_asr_cer import normalized_ja
    return {"reference_characters":sum(len(normalized_ja(x["text"])) for x in records),
            "speaker_count":len({x["speaker_id"] for x in records}),
            "rows":len(records)}
