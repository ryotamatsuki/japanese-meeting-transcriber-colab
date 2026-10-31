"""Presentation-only deterministic grouping of adjacent same-speaker transcript rows.

Keep editable source rows, speaker IDs and original time boundaries unchanged.
Do not combine unknown/unassigned speakers or cross a blank manual row.
"""
from __future__ import annotations

import re

_UNKNOWN = re.compile(r"^(?:話者不明|話者未設定|不明|unknown|unassigned)$", re.I)
_ASCII_END = re.compile(r"[A-Za-z0-9]$")
_ASCII_START = re.compile(r"^[A-Za-z0-9]")


def join_text(left: str, right: str) -> str:
    a, b = left.rstrip(), right.lstrip()
    if not a:
        return b
    if not b:
        return a
    gap = " " if _ASCII_END.search(a) and _ASCII_START.search(b) else ""
    return a + gap + b


def readable_paragraphs(rows):
    """View/export paragraphs; a new array, never a destructive transcript edit."""
    result = []
    last_input_index = None
    for i, row in enumerate(rows):
        content = row["text"].strip()
        if not content:
            last_input_index = None
            continue
        who = row["speaker"]
        prev = result[-1] if result else None
        adjacent = (prev is not None and last_input_index == i - 1
                    and who == prev["speaker"] and who.strip()
                    and not _UNKNOWN.fullmatch(who.strip())
                    and row["start"] >= rows[i - 1]["start"]
                    and row["end"] >= row["start"])
        if adjacent:
            prev["text"] = join_text(prev["text"], content)
            prev["end"] = max(prev["end"], row["end"])
            prev["last_index"] = i
            prev["row_count"] += 1
        else:
            result.append({"start": row["start"], "end": row["end"],
                           "speaker": who, "text": content,
                           "first_index": i, "last_index": i, "row_count": 1})
        last_input_index = i
    return result
