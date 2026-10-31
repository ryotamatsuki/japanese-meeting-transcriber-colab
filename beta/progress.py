"""Aggregate-only progress snapshots for long-running ASR jobs.

No transcript, speaker identity, audio waveform, or secrets are tracked.
Stage percentages represent progress within that stage, NEVER the whole job.
"""
from __future__ import annotations

import math
import time

PHASES = {"preparing", "asr", "diarization", "formatting", "saving"}
ORDER = {"preparing": 0, "asr": 1, "diarization": 2, "formatting": 3, "saving": 4}


def progress_snapshot(previous, phase, *, done=None, total=None, now=None):
    """Create a monotone and honest phase-local snapshot from measured data.

    Invalid or regressive phase updates are rejected rather than displayed as
    misleading motion. A missing valid audio duration means indeterminate.
    """
    if phase not in PHASES:
        raise ValueError("Unknown processing stage")
    previous = previous if isinstance(previous, dict) else {}
    before = previous.get("phase")
    if before in ORDER and ORDER[phase] < ORDER[before]:
        return previous.copy()
    now = time.time() if now is None else float(now)
    if not math.isfinite(now):
        raise ValueError("Invalid event time")
    started = previous.get("phase_started_at") if phase == before else now
    snapshot = {"phase": phase, "phase_started_at": started, "updated_at": now}
    if phase == "asr" and done is not None and total is not None:
        done, total = float(done), float(total)
        if math.isfinite(done) and math.isfinite(total) and total > 0:
            old = previous.get("audio_done", 0) if before == phase else 0
            snapshot["audio_total"] = total
            snapshot["audio_done"] = min(total, max(float(old), 0, done))
    return snapshot
