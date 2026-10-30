"""Stage15 live Modal Volume/Dict 24h retention experiment (isolated environment).

No real user content or credentials. No permanent deployed app. Reports counts only.
"""
from pathlib import Path
import os
import modal

app=modal.App("transcriber-retention-audit-cpu")
vol=modal.Volume.from_name("stage15-retention-audit-files",create_if_missing=True)
dict_state=modal.Dict.from_name("stage15-retention-audit-state",create_if_missing=True)
image=modal.Image.debian_slim(python_version="3.11").add_local_python_source("beta")


@app.function(image=image,volumes={"/data":vol},cpu=1,memory=512,timeout=120)
def audit_retention_volume() -> dict:
    import time
    from beta.core import JOB_TTL_SECONDS
    from beta.retention import purge_expired
    root=Path("/data/jobs")
    root.mkdir(parents=True,exist_ok=True)
    now=time.time()
    expired,active,orphan=("a"*32,"b"*32,"c"*32)
    for jid in (expired,active,orphan):
        directory=root/jid
        directory.mkdir(exist_ok=True)
        (directory/"source.mp3").write_bytes(b"synthetic-test-only")
    dict_state["job_index"]=[expired,active]
    dict_state["job:"+expired]={"created":now-JOB_TTL_SECONDS-30,"status":"complete"}
    dict_state["job:"+active]={"created":now-JOB_TTL_SECONDS-60,"status":"running"}
    old=now-JOB_TTL_SECONDS-3601
    os.utime(root/orphan,(old,old))
    vol.commit()
    vol.reload()
    result=purge_expired(root,dict_state,now=now)
    vol.commit()
    vol.reload()
    if root.joinpath(expired).exists() or root.joinpath(orphan).exists():
        raise AssertionError("Expired files persisted on real Modal Volume")
    if not root.joinpath(active).exists():
        raise AssertionError("Running GPU source unexpectedly deleted")
    if dict_state["job:"+expired]["status"]!="deleted":
        raise AssertionError("Expired record not marked deleted")
    if dict_state.get("job_index")!=[active]:
        raise AssertionError("Index not reconciled")
    if result!={"expired_removed":1,"orphan_removed":1,"active_expired_skipped":1}:
        raise AssertionError("Unexpected physical deletion outcome")
    # Return only privacy-safe counts; the ephemeral environment is destroyed.
    return {"physical_deletion_verified":True,"index_update_verified":True,
            "active_protected":True,"expired_removed":1,
            "orphan_removed":1,"active_expired_skipped":1,
            "runtime":"Modal CPU with real Volume and Dict"}


@app.local_entrypoint()
def main():
    import json
    result=audit_retention_volume.remote()
    if not result.get("physical_deletion_verified"):
        raise SystemExit("Retention audit failed")
    print("STAGE15_MODAL_RETENTION_AUDIT",json.dumps(result,sort_keys=True))
