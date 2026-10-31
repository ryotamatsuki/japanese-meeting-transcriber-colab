"""Stage36: isolated, nonpersonal Modal Volume + Dict retention integration probe.

Never points to production Volumes or Dicts, uses only run-scoped resources.
No GPU, no model, no human recording, no external network payload.
"""
from __future__ import annotations
import os
import re
import modal

suffix=os.environ.get("STAGE36_RUN_ID","")
if not re.fullmatch(r"[0-9]{5,20}",suffix):
    raise RuntimeError("STAGE36_RUN_ID must be a valid Actions run ID")

volume=modal.Volume.from_name(f"stage36-retention-{suffix}",create_if_missing=True)
state=modal.Dict.from_name(f"stage36-retention-state-{suffix}",create_if_missing=True)
app=modal.App("stage36-transcriber-retention-validation")
image=modal.Image.debian_slim(python_version="3.11").add_local_python_source("beta")

@app.function(image=image,volumes={"/data":volume},timeout=180,cpu=1,memory=256,
              retries=0,single_use_containers=True)
def seed_and_sweep():
    import os
    import time
    from pathlib import Path
    from beta.core import JOB_TTL_SECONDS
    from beta.retention import purge_expired
    now=time.time()
    root=Path("/data/jobs")
    root.mkdir(parents=True,exist_ok=True)
    ids={"expired":"a"*32,"orphan":"e"*32,
         "stale_running":"7"*32,"stale_queued":"8"*32,
         "active":"9"*32,"fresh":"c"*32}
    for name,jid in ids.items():
        folder=root/jid
        folder.mkdir(mode=0o700)
        (folder/"source.wav").write_bytes(b"fictitious, non-personal test content")
        if name=="orphan":
            past=now-JOB_TTL_SECONDS-3601
            os.utime(folder,(past,past))
            continue
        created=now-JOB_TTL_SECONDS-8000
        status="complete"
        if name=="stale_running":status="running"
        if name=="stale_queued":status="queued"
        if name=="active":status="running"
        if name=="fresh":
            status="complete"
            created=now-15
        info={"created":created,"status":status}
        if name=="stale_running":info["started_at"]=now-8000
        if name=="active":info["started_at"]=now-300
        state["job:"+jid]=info
    state["job_index"]=[ids[k] for k in ids if k!="orphan"]
    volume.commit()
    out=purge_expired(root,state,now=now)
    assert out["expired_removed"]==3,out
    assert out["orphan_removed"]==1,out
    assert out["stale_active_reclaimed"]==2,out
    assert out["active_expired_skipped"]==1,out
    assert (root/ids["active"]).is_dir()
    assert (root/ids["fresh"]).is_dir()
    for name in ("expired","orphan","stale_running","stale_queued"):
        assert not (root/ids[name]).exists(),name
    volume.commit()
    return {"sweep":out,"expected_persistent_files":2,
            "live_volume_and_dict":True,"uses_real_user_recording":False}

@app.function(image=image,volumes={"/data":volume},timeout=120,cpu=1,memory=256,
              retries=0,single_use_containers=True)
def verify_from_fresh_container():
    from pathlib import Path
    volume.reload()
    root=Path("/data/jobs")
    persisted={p.name for p in root.iterdir() if p.is_dir()}
    assert persisted=={"9"*32,"c"*32},len(persisted)
    assert state["job:"+"a"*32]["status"]=="deleted"
    assert state["job:"+"7"*32]["status"]=="deleted"
    assert state["job:"+"8"*32]["status"]=="deleted"
    assert state["job:"+"9"*32]["status"]=="running"
    assert state["job:"+"c"*32]["status"]=="complete"
    assert set(state["job_index"])==persisted
    return {"persisted_file_count":len(persisted),"state_consistent":True,
            "fresh_container_reopen":True}

@app.local_entrypoint()
def main():
    one=seed_and_sweep.remote()
    assert one["live_volume_and_dict"] and not one["uses_real_user_recording"]
    two=verify_from_fresh_container.remote()
    assert two["state_consistent"] and two["fresh_container_reopen"]
    print("STAGE36_REAL_MODAL_VOLUME_DICT_RETENTION_PASS")
    print("STAGE36_STALE_QUEUED_AND_RUNNING_RECLAIMED")
    print("STAGE36_LIVE_RUNNING_AND_FRESH_PRESERVED")
    print("STAGE36_PHYSICAL_DELETION_PERSISTS_IN_FRESH_CONTAINER")
