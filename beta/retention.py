"""Testable physical-retention sweep for the single-user private beta.

This is a filesystem deletion routine, not a substitute for job authorization.
Never label a job deleted if its underlying directory could not be removed.
"""
from __future__ import annotations
import os
import shutil
import time
from pathlib import Path
from .core import JOB_TTL_SECONDS,valid_job_id


def purge_expired(root, job_state, *, now=None):
    now=time.time() if now is None else float(now)
    root=Path(root)
    result={'expired_removed':0,'orphan_removed':0,'active_expired_skipped':0,'stale_active_reclaimed':0}
    for folder in root.iterdir() if root.is_dir() else []:
        if not folder.is_dir() or not valid_job_id(folder.name):
            continue
        record=job_state.get('job:'+folder.name)
        if not record:
            # No index record: do not leak orphan files forever. Allow an
            # additional safety hour for any in-flight job that might have
            # been created before the state record was committed.
            if now-folder.stat().st_mtime>JOB_TTL_SECONDS+3600:
                shutil.rmtree(folder)
                result['orphan_removed']+=1
            continue
        if now-float(record.get('created',now))<JOB_TTL_SECONDS:
            continue
        status=record.get('status')
        if status in ('queued','running'):
            # A GPU execution cannot outlive its enforced 3600s timeout.
            # Still, avoid deleting a legitimate function that only recently
            # started after waiting in the provider queue.
            started=record.get('started_at')
            try:
                started=float(started) if started is not None else None
            except (TypeError,ValueError):
                started=None
            if status=='running' and started is not None and 0<=now-started<=4200:
                result['active_expired_skipped']+=1
                continue
            if (started is None and
                    now-float(record.get('created',now))<=JOB_TTL_SECONDS+7200):
                result['active_expired_skipped']+=1
                continue
            # Terminal stale queued/running record. The source file is past
            # retention; any late GPU start must reject status != queued.
            result['stale_active_reclaimed']+=1
        # Raise if deletion failed instead of writing a false deleted state.
        shutil.rmtree(folder)
        record=dict(record)
        record['status']='deleted'
        job_state['job:'+folder.name]=record
        result['expired_removed']+=1
    job_state['job_index']=[
        id for id in job_state.get('job_index',[])
        if (job_state.get('job:'+id) or {}).get('status')!='deleted']
    return result
