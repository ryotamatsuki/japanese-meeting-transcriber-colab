"""J-CRe3 boundary adjudication aid: human ELAN reference is NOT a model input.

Outputs a PROXY flag, never a human-verified gold boundary label.
Requires another independent listening pass before commercial conclusions.
The reference can be loaded only AFTER baseline and all four arms are frozen.
"""
from __future__ import annotations
import math
from scripts.jcre3_reference import load_reference


def _match(row, reference):
    a, b = float(row["start"]), float(row["end"])
    length = b - a
    if not (math.isfinite(a) and math.isfinite(b) and length > 0):
        raise ValueError("Invalid predicted row timing")
    spans = []
    for index, turn in enumerate(reference):
        left, right = max(a,float(turn["start"])), min(b,float(turn["end"]))
        ov = max(0.0,right-left)
        if ov > 0:
            spans.append((ov,index))
    if not spans:
        return None
    spans.sort(reverse=True)
    if (spans[0][0]/length < .75 or
            len(spans)>1 and spans[1][0]/length > .20):
        return None
    return spans[0][1]


def proxy_boundaries(reference, rows, candidates):
    """Reference-derived proxy only, with uncertainty for timing mismatch."""
    if not reference or not rows:
        raise ValueError("Missing reference or prediction")
    result = {}
    for index in candidates:
        if type(index) is not int or index < 0 or index+1 >= len(rows):
            raise ValueError("Invalid candidate index")
        a = _match(rows[index],reference)
        b = _match(rows[index+1],reference)
        if a is None or b is None:
            outcome="uncertain"
        elif a==b:
            outcome="merge"
        elif reference[a]["speaker_id"] != reference[b]["speaker_id"]:
            outcome="keep"
        else:
            # Two distinct human turns of one speaker need listening review.
            outcome="uncertain"
        result[str(index)]=outcome
    return result


def verified_labels_from_review(sheet, *, annotators_required=2):
    """Only explicitly adjudicated labels from independent listeners qualify.

    A single reviewer is supported for pilots but must be disclosed.
    """
    if annotators_required not in (1,2) or not isinstance(sheet,dict):
        raise ValueError("Invalid annotation sheet")
    outcomes = {}
    for boundary in sheet.get("boundaries",[]):
        ident = boundary.get("boundary_id")
        if type(ident) is not int or str(ident) in outcomes:
            raise ValueError("Invalid or duplicate boundary")
        a,b = boundary.get("annotator1"),boundary.get("annotator2")
        final = boundary.get("final_label")
        if final not in ("merge","keep","uncertain"):
            raise ValueError("Boundary has not been adjudicated")
        if annotators_required==2:
            if a not in ("merge","keep","uncertain") or b not in ("merge","keep","uncertain"):
                raise ValueError("Two independent labels required")
            if a!=b and not boundary.get("adjudication_note"):
                raise ValueError("Disagreement needs written adjudication")
        elif a not in ("merge","keep","uncertain"):
            raise ValueError("At least one actual reviewer required")
        outcomes[str(ident)] = final
    if not outcomes:
        raise ValueError("No human labels supplied")
    return outcomes


def load_pinned_jcre3(reference_data, sha_expected):
    reference, sha = load_reference(reference_data)
    if sha != sha_expected:
        raise ValueError("Human reference SHA mismatch")
    return reference
