"""Private offline review-queue export for a Qwen experiment ZIP.

Never print or publish audio/transcript. Output contains only timestamps, index,
risk reasons, and the '要確認' status. This does not alter the original ZIP.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from beta.core import parse_original_archive
from scripts.qwen_quality_experiments import (
    diagnose_review_candidates, build_bounded_review_queue,
)


def queue_from_original_zip(path: Path, *, max_share: float = 0.15):
    if not path.is_file() or path.stat().st_size > 250*1024*1024:
        raise ValueError("Invalid local private archive")
    parsed = parse_original_archive(path.read_bytes())
    rows=parsed["rows"]
    flags=diagnose_review_candidates(rows)
    return {"schema_version":1,"status":"research_review_only",
            "utterance_count":len(rows),"candidate_count":len(flags),
            "review_queue":build_bounded_review_queue(rows,flags,
                                max_share=max_share),
            "warning":"要確認 means potential issue, never a verified error."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--max-share",type=float,default=0.15)
    options=parser.parse_args()
    result=queue_from_original_zip(options.archive,max_share=options.max_share)
    options.output.parent.mkdir(parents=True,exist_ok=True)
    options.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                              encoding="utf-8")
    print("PRIVATE_REVIEW_QUEUE_READY",{"count":len(result["review_queue"]),
                                      "candidate_count":result["candidate_count"]})


if __name__=="__main__":
    main()
