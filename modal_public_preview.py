"""Passwordless, read-only Studio UI preview on Modal CPU.

No authentication secret, Modal Volume, Dict, GPU worker, recording uploads,
or personal transcripts are connected. This is NOT the production transcriber.
"""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path

import modal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

app = modal.App("kiroku-public-studio-preview")
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("fastapi==0.115.12", "uvicorn==0.34.2")
         .add_local_dir("beta/react_dist", remote_path="/root/react_dist"))

SAMPLE_ID = "e" * 32
SAMPLE_NAME = "デザイン確認用・架空の会議.wav"
SAMPLE_JOB = {
    "id": SAMPLE_ID,
    "filename": SAMPLE_NAME,
    "status": "complete",
    "received": 200000,
    "expected_size": 200000,
    "duration": 198,
    "speakers": 3,
    "created": 1793399400,
    "utterances": 12,
}
SAMPLE_TEXT = (
    "本日の会議では、今月の進捗状況と来月の計画を確認します。",
    "資料の整理が完了したので、担当者ごとの作業状況を共有します。",
    "ありがとうございます。次の会議までに必要な調整を進めましょう。",
    "発言の色分け、話者ラベルと音声プレーヤーの配置を確認できます。",
)
SAMPLE_ROWS = [
    {"start": i*15.0, "end": i*15.0+12.0,
     "speaker": ("話者A", "話者B", "話者C")[i % 3],
     "text": SAMPLE_TEXT[i % len(SAMPLE_TEXT)]}
    for i in range(12)
]


def create_preview_app(build_dir: str | Path = "/root/react_dist"):
    """Public GET-only UI. Every API mutation is rejected before any state change."""
    root = Path(build_dir).resolve()
    server = FastAPI(
        title="Kiroku public UI preview (sample data only)",
        docs_url=None, redoc_url=None, openapi_url=None,
    )

    @server.middleware("http")
    async def protect(request: Request, call_next):
        # Fail closed for all writes, including audio uploads and deletions.
        if request.method not in ("GET", "HEAD"):
            return JSONResponse({"detail": "Preview is read only"}, status_code=403)
        result = await call_next(request)
        result.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; media-src 'self'; "
            "form-action 'none'; frame-ancestors 'none'; base-uri 'none'")
        result.headers["X-Frame-Options"] = "DENY"
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["Cache-Control"] = "public, max-age=120"
        return result

    @server.get("/healthz")
    def health():
        return {"status": "running", "preview_only": True, "gpu_enabled": False}

    @server.get("/")
    def landing():
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(503, "React public preview build unavailable")
        return HTMLResponse(index.read_text(encoding="utf-8"))

    @server.get("/ui/{asset_path:path}")
    def assets(asset_path: str):
        if not asset_path.startswith("assets/"):
            raise HTTPException(404, "Unknown asset")
        target = (root / asset_path).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404, "Unknown asset")
        if target.suffix not in (".js", ".css", ".svg", ".png", ".ico", ".woff2"):
            raise HTTPException(404, "Unknown asset")
        return FileResponse(target, media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")

    @server.get("/api/session")
    def session():
        return {
            "csrf": "preview-readonly",
            "limits": {"file_bytes": 0, "duration_seconds": 0, "gpu_jobs_24h": 0},
            "preview_only": True,
        }

    @server.get("/api/jobs")
    def jobs():
        return {"jobs": [SAMPLE_JOB]}

    @server.get("/api/jobs/{job_id}")
    def job(job_id: str):
        if job_id != SAMPLE_ID:
            raise HTTPException(404, "Not found")
        return SAMPLE_JOB

    @server.get("/api/jobs/{job_id}/rows")
    def rows(job_id: str):
        if job_id != SAMPLE_ID:
            raise HTTPException(404, "Not found")
        return {"rows": SAMPLE_ROWS}

    @server.get("/api/jobs/{job_id}/review")
    def review(job_id: str):
        if job_id != SAMPLE_ID:
            raise HTTPException(404, "Not found")
        return {"available": True, "total_candidates": 2,
                "windows": [
                    {"id": "sample-overlap-a", "start": 43, "end": 49},
                    {"id": "sample-overlap-b", "start": 89, "end": 95},
                ], "reviewed_ids": []}

    # Explicitly prevent audio and ZIP access even if future route refactoring
    # introduces generic GET handlers.
    @server.get("/api/jobs/{job_id}/audio")
    @server.get("/api/jobs/{job_id}/download")
    def disabled_media(job_id: str):
        raise HTTPException(404, "Preview has no recordings or exports")

    return server


@app.function(image=image, cpu=0.25, memory=256, max_containers=1,
              timeout=60, scaledown_window=2)
@modal.concurrent(max_inputs=10)
@modal.asgi_app()
def public_ui_preview():
    return create_preview_app()
