"""Offline private Qwen LLM boundary study; never modifies Studio or source ZIP.

Example (local vLLM serving Qwen/Qwen3-4B-Instruct-2507):
  python scripts/qwen_text_boundary_cli.py --archive private.zip \
      --endpoint http://127.0.0.1:8000/v1/chat/completions \
      --output private_boundaries.json
Only run with recordings approved for the chosen inference endpoint.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from beta.core import parse_original_archive
from scripts.qwen_text_boundary_postprocess import MODEL, run_second_pass


def local_or_secure(url: str, allow_remote: bool) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and parsed.path.endswith("/chat/completions") and not parsed.username):
        return
    if (allow_remote and parsed.scheme == "https" and parsed.hostname
            and not parsed.username and parsed.path.endswith("/chat/completions")):
        return
    raise ValueError("Only local API, or explicitly opted-in remote HTTPS, allowed")


def request_qwen(messages, *, endpoint, model, allow_remote=False):
    local_or_secure(endpoint, allow_remote)
    data = json.dumps({"model": model, "messages": messages, "temperature": 0,
                       "max_tokens": 320, "stream": False},
                      ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("KIROKU_QWEN_API_KEY", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(endpoint, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=90) as response:
        content = response.read(65537)
        if len(content) > 65536:
            raise ValueError("Oversized provider reply")
    obj = json.loads(content)
    return obj["choices"][0]["message"]["content"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:8000/v1/chat/completions")
    p.add_argument("--model", default=MODEL)
    p.add_argument("--allow-remote", action="store_true",
                   help="Send private transcription to an explicitly approved HTTPS server")
    args = p.parse_args()
    local_or_secure(args.endpoint, args.allow_remote)
    if args.archive.resolve() == args.output.resolve():
        p.error("Never overwrite source ZIP")
    if args.archive.stat().st_size > 250 * 1024 * 1024:
        p.error("Archive exceeds research limit")
    rows = parse_original_archive(args.archive.read_bytes())["rows"]
    outcome = run_second_pass(
        rows, lambda messages: request_qwen(messages, endpoint=args.endpoint,
                                            model=args.model, allow_remote=args.allow_remote))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Private local output includes transcript; never upload to GitHub or CI artifacts.
    args.output.write_text(json.dumps(outcome, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(json.dumps({k: outcome[k] for k in
                      ("status", "merge_count", "split_count", "batches")}, sort_keys=True))


if __name__ == "__main__":
    main()
