#!/usr/bin/env python3
"""Offline checks: notebook syntax, clean outputs, and word/speaker merging.

This test never downloads models, accesses Google Colab, or uploads audio.
"""
import ast
import json
import re
import sys
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "meeting_transcriber.ipynb"


def test_notebook_is_clean():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4, "notebook format should be v4"
    code = []
    for idx, cell in enumerate(notebook["cells"]):
        assert cell["cell_type"] in {"code", "markdown"}
        source = "".join(cell.get("source", []))
        if cell["cell_type"] == "code":
            assert cell.get("execution_count") is None, f"execution_count in cell {idx}"
            assert not cell.get("outputs"), f"saved output in cell {idx}"
            ast.parse(source, filename=f"cell-{idx}")
            code.append(source)
    joined = "\n".join(code)
    for sensitive in ("261023_1009", "副知事との意見交換会", "愛媛県", "財政課", "松木"):
        assert sensitive not in joined, f"project-specific text detected: {sensitive}"
    assert not re.search(r"hf_[a-zA-Z0-9]{20,}", joined), "possible Hugging Face token in source"
    assert any("ENABLE_DIARIZATION" in item for item in code)
    assert any("WhisperModel" in item for item in code)
    assert any("assign_and_group" in item for item in code)
    return notebook


def test_speaker_alignment(notebook):
    function = None
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        tree = ast.parse("".join(cell["source"]))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "assign_and_group":
                function = node
                break
    assert function is not None, "assign_and_group function missing"

    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    scope = {"ENABLE_DIARIZATION": True, "bisect_right": bisect_right}
    exec(compile(module, "<speaker-align-test>", "exec"), scope)
    run = scope["assign_and_group"]
    asr = [
        {
            "start": 0,
            "end": 3,
            "text": "おはようございます",
            "words": [
                {"start": 0.0, "end": 0.8, "text": "おはよう"},
                {"start": 2.0, "end": 2.7, "text": "ございます"},
            ],
        }
    ]
    diar = [
        {"start": 0.0, "end": 1.2, "speaker_id": "speaker-A"},
        {"start": 1.8, "end": 3.0, "speaker_id": "speaker-B"},
    ]
    segments, labels, count = run(asr, diar)
    assert count == 2
    assert len(segments) == 2, segments
    assert [r["speaker"] for r in segments] == ["話者1", "話者2"], segments
    assert labels["speaker-A"] == "話者1"

    scope["ENABLE_DIARIZATION"] = False
    text_only, labels, count = run(asr, [])
    assert count == 2
    assert labels == {}
    assert all(row["speaker"] == "話者未設定" for row in text_only)


if __name__ == "__main__":
    notebook = test_notebook_is_clean()
    test_speaker_alignment(notebook)
    print(f"PASS: notebook clean, {len(notebook['cells'])} cells, Python syntax OK, speaker alignment OK")
