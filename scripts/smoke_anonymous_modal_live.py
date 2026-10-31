"""Live Modal anonymous Studio E2E: two separate cookie jars, real speech, GPU, ZIP.

Set KIROKU_TEST_URL to the isolated anonymous HTTPS endpoint.
Set KIROKU_TEST_AUDIO to an approved 1-60 minute, non-confidential speech recording.
No audio bytes, ASR transcript text, cookies or tokens are printed or saved.
This uses two independent HTTP clients (virtual devices), NOT two physical phones.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

POLL_SECONDS = 5
MAX_SECONDS = 900
CHUNK = 4 * 1024 * 1024


def check(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def app_origin() -> str:
    url = os.environ["KIROKU_TEST_URL"].rstrip("/")
    parsed = urlparse(url)
    check(parsed.scheme == "https" and parsed.hostname and parsed.hostname.endswith(".modal.run")
          and not parsed.username and not parsed.password and not parsed.query
          and not parsed.fragment and not parsed.path.strip("/"),
          "Use only the HTTPS Modal test endpoint without a path")
    return url


async def required(client: httpx.AsyncClient, method: str, path: str,
                   expected: int = 200, **kwargs):
    response = await client.request(method, path, **kwargs)
    check(response.status_code == expected,
          f"{method} {path.split('?')[0]}: expected {expected}, got {response.status_code}")
    return response


async def establish(client: httpx.AsyncClient):
    response = await required(client, "GET", "/")
    check("beta_session" in client.cookies, "Anonymous session cookie missing")
    check("httponly" in response.headers.get("set-cookie", "").lower(), "HttpOnly missing")
    check("secure" in response.headers.get("set-cookie", "").lower(), "Secure cookie missing")
    result = (await required(client, "GET", "/api/session")).json()
    check(result.get("anonymous") is True, "Endpoint is not the anonymous Studio app")
    check(isinstance(result.get("csrf"), str) and len(result["csrf"]) >= 32, "CSRF missing")
    return result["csrf"]


async def submit(client: httpx.AsyncClient, csrf: str, filename: str, data: bytes, registry: list):
    headers = {"X-CSRF": csrf}
    response = await required(client, "POST", "/api/jobs", json={
        "filename": filename, "size": len(data), "diarization": False, "speakers": 0,
    }, headers=headers)
    job = response.json()["id"]
    check(len(job) == 32, "Job ID malformed")
    registry.append((client, csrf, job))
    for offset in range(0, len(data), CHUNK):
        await required(client, "PUT", f"/api/jobs/{job}/chunks?offset={offset}",
                       content=data[offset:offset+CHUNK], headers=headers)
    done = await required(client, "POST", f"/api/jobs/{job}/finish", headers=headers)
    check(done.json()["status"] in ("queued", "running", "complete"), "Job not submitted")
    return job


async def completed(client: httpx.AsyncClient, job: str):
    until = time.monotonic() + MAX_SECONDS
    while time.monotonic() < until:
        response = await required(client, "GET", f"/api/jobs/{job}")
        current = response.json()
        if current["status"] == "complete":
            return current
        check(current["status"] != "failed",
              "GPU transcription failed. Inspect protected Modal logs, not raw speech")
        await asyncio.sleep(POLL_SECONDS)
    raise AssertionError("GPU job did not finish within 15 minutes")


async def edited_export(client: httpx.AsyncClient, csrf: str, job: str, marker: str, other_marker: str):
    route = "/api/jobs/" + job
    data = (await required(client, "GET", route + "/rows")).json()["rows"]
    check(len(data) > 0, "ASR produced no editable rows for permitted speech audio")
    data[0]["text"] = marker
    await required(client, "PUT", route + "/rows", headers={"X-CSRF": csrf},
                   json={"rows": data})
    download = await required(client, "GET", route + "/download")
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        check(archive.testzip() is None, "Damaged ZIP")
        check(set(archive.namelist()) >= {
            "文字起こし.txt", "文字起こし.csv", "文字起こし.srt", "文字起こし.json"
        }, "Missing export formats")
        for name in ("文字起こし.txt", "文字起こし.csv", "文字起こし.srt", "文字起こし.json"):
            exported = archive.read(name).decode("utf-8-sig")
            check(marker in exported, "Saved edit missing from an export format")
            check(other_marker not in exported, "Other session edit leaked into export")
    return len(data)


async def main():
    url = app_origin()
    source = Path(os.environ["KIROKU_TEST_AUDIO"])
    check(source.is_file() and source.suffix.lower() in (".ogg", ".wav", ".m4a", ".mp3"),
          "Missing authorized speech audio")
    started = time.monotonic()
    audio = source.read_bytes()
    check(1000 < len(audio) < 10 * 1024 * 1024, "Unexpected smoke audio size")
    results = {"test": "two_isolated_sessions_real_audio_and_gpu",
               "virtual_devices": 2, "physical_devices": 0,
               "audio_bytes": len(audio),
               "both_jobs_submitted": False, "owner_isolation": False,
               "gpu_completed": False, "edit_and_zip": False, "deleted": False}
    async with (httpx.AsyncClient(base_url=url, timeout=90, follow_redirects=False) as a,
                httpx.AsyncClient(base_url=url, timeout=90, follow_redirects=False) as b):
        csrf_a, csrf_b = await asyncio.gather(establish(a), establish(b))
        check(a.cookies.get("beta_session") != b.cookies.get("beta_session"),
              "Sessions unexpectedly share a cookie")
        jobs = []
        try:
            job_a, job_b = await asyncio.gather(
                submit(a, csrf_a, "anonymous-a" + source.suffix.lower(), audio, jobs),
                submit(b, csrf_b, "anonymous-b" + source.suffix.lower(), audio, jobs))
            results["both_jobs_submitted"] = True
            list_a, list_b = await asyncio.gather(
                required(a, "GET", "/api/jobs"), required(b, "GET", "/api/jobs"))
            check({j["id"] for j in list_a.json()["jobs"]} == {job_a},
                  "User A job listing leaked or missing")
            check({j["id"] for j in list_b.json()["jobs"]} == {job_b},
                  "User B job listing leaked or missing")
            check(job_a != job_b, "Job IDs unexpectedly identical")
            for owner, csrf, other in ((a, csrf_a, job_b), (b, csrf_b, job_a)):
                for suffix in ("", "/audio", "/rows", "/review", "/download"):
                    await required(owner, "GET", "/api/jobs/" + other + suffix, expected=404)
                await required(owner, "PUT", "/api/jobs/" + other + "/rows",
                               headers={"X-CSRF": csrf}, json={"rows": []}, expected=404)
            await required(a, "DELETE", "/api/jobs/" + job_b,
                           headers={"X-CSRF": csrf_a}, expected=404)
            await required(b, "DELETE", "/api/jobs/" + job_a,
                           headers={"X-CSRF": csrf_b}, expected=404)
            results["owner_isolation"] = True
            states = await asyncio.gather(completed(a, job_a), completed(b, job_b))
            results["gpu_completed"] = all(s["status"] == "complete" for s in states)
            results["elapsed_to_both_complete_seconds"] = round(time.monotonic() - started, 3)
            results["pipeline_seconds_per_job"] = [s.get("pipeline_seconds") for s in states]
            async with httpx.AsyncClient(base_url=url, timeout=90) as unauthenticated:
                await required(unauthenticated, "GET", "/api/jobs", expected=401)
                await required(unauthenticated, "GET", "/api/jobs/" + job_a + "/rows", expected=401)
            await required(a, "PUT", "/api/jobs/" + job_a + "/rows",
                           headers={"X-CSRF": "invalid"}, json={"rows": []}, expected=403)
            counts = await asyncio.gather(
                edited_export(a, csrf_a, job_a, "テストA・保存確認", "テストB・保存確認"),
                edited_export(b, csrf_b, job_b, "テストB・保存確認", "テストA・保存確認"))
            results["utterances_per_job"] = counts
            results["edit_and_zip"] = True
            # Ownership denial holds after both jobs complete and edits are saved.
            await required(a, "GET", "/api/jobs/" + job_b + "/download", expected=404)
            await required(b, "GET", "/api/jobs/" + job_a + "/download", expected=404)
        finally:
            removed = 0
            for client, csrf, job in jobs:
                try:
                    response = await client.delete("/api/jobs/" + job,
                        headers={"X-CSRF": csrf})
                    if response.status_code == 200:
                        for suffix in ("", "/audio", "/rows", "/download"):
                            await required(client, "GET", "/api/jobs/" + job + suffix, expected=404)
                        removed += 1
                except httpx.HTTPError:
                    pass
            results["deleted"] = len(jobs) == 2 and removed == 2
    check(all(results[k] for k in ("owner_isolation", "gpu_completed", "edit_and_zip", "deleted")),
          "Live test incomplete or test files not deleted")
    # Only non-sensitive numeric verification results.
    print("KIROKU_ANONYMOUS_TWO_CLIENT_LIVE_PASS " + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
