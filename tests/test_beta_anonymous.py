"""Anonymous sessions: IDOR prevention across every file and edit endpoint."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from beta.backend import FileBackend, StoreError
from beta.server import create_app

SECRET = "anonymous-session-key-longer-than-thirty-two-characters"


class AnonymousIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = {}
        self.backend = FileBackend(self.tmp.name, self.state, probe=lambda _: 12,
                                   launch=lambda *args: None, require_owner=True)
        self.app = create_app(self.backend, session_secret=SECRET, anonymous=True)
        self.a = TestClient(self.app, base_url="https://kiroku.example")
        self.b = TestClient(self.app, base_url="https://kiroku.example")
        for client in (self.a, self.b):
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Secure", response.headers["set-cookie"])
            self.assertIn("HttpOnly", response.headers["set-cookie"])
            self.assertIn("SameSite=strict", response.headers["set-cookie"])
        self.ca = self.a.get("/api/session").json()["csrf"]
        self.cb = self.b.get("/api/session").json()["csrf"]

    def tearDown(self):
        self.a.close()
        self.b.close()
        self.tmp.cleanup()

    def _create(self, client, csrf, filename):
        response = client.post("/api/jobs", headers={"X-CSRF": csrf},
                               json={"filename": filename, "size": 6, "diarization": True,
                                     "speakers": 2})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("owner", response.json())
        return response.json()["id"]

    def test_session_issued_without_login_and_owner_not_in_metadata(self):
        self.assertTrue(self.a.get("/api/session").json()["anonymous"])
        self.assertNotEqual(self.a.cookies["beta_session"], self.b.cookies["beta_session"])
        self.assertEqual(self.a.get("/login", follow_redirects=False).status_code, 303)
        self.assertEqual(self.a.post("/login", data={"password": "anything"}).status_code, 404)
        original = self.a.cookies["beta_session"]
        self.a.get("/")
        self.assertEqual(self.a.cookies["beta_session"], original)
        job_id = self._create(self.a, self.ca, "one.wav")
        self.assertEqual(self.b.get("/api/jobs").json(), {"jobs": []})
        self.assertEqual(len(self.a.get("/api/jobs").json()["jobs"]), 1)
        self.assertNotIn("owner", self.a.get("/api/jobs/" + job_id).json())
        self.assertIn("owner", self.state["job:" + job_id])
        with self.assertRaises(StoreError):
            self.backend.info(job_id)  # Missing backend owner must fail closed.
        with self.assertRaises(StoreError):
            self.backend.list_jobs()
        self.assertNotIn(original, repr(self.state))

    def test_cross_session_all_job_apis_deny_including_audio_edits_and_zip(self):
        job_id = self._create(self.a, self.ca, "owner-a.wav")
        path = "/api/jobs/" + job_id
        h_a = {"X-CSRF": self.ca}
        h_b = {"X-CSRF": self.cb}
        self.assertEqual(self.a.put(path + "/chunks?offset=0", headers=h_a,
                                    content=b"abcdef").status_code, 200)
        self.assertEqual(self.a.post(path + "/finish", headers=h_a).status_code, 200)
        rec = self.state["job:" + job_id]
        rec["status"] = "complete"
        self.state["job:" + job_id] = rec
        folder = Path(self.tmp.name) / job_id
        rows = [{"start": 0, "end": 2, "speaker": "話者1", "text": "owner A only"}]
        (folder / "results.json").write_text(json.dumps(rows), encoding="utf-8")
        (folder / "review_candidates.json").write_text(json.dumps({
            "available": True, "total_candidates": 1,
            "windows": [{"id": "w1", "start": 0, "end": 1}],
        }), encoding="utf-8")

        # Valid API usage is preserved for the owner, including editing.
        self.assertEqual(self.a.get(path + "/audio").content, b"abcdef")
        self.assertEqual(self.a.get(path + "/rows").json()["rows"], rows)
        edited = [{"start": 0, "end": 2, "speaker": "話者A", "text": "edited"}]
        self.assertEqual(self.a.put(path + "/rows", headers=h_a,
                                   json={"rows": edited}).status_code, 200)
        self.assertEqual(self.a.put(path + "/review/w1", headers=h_a,
                                   json={"reviewed": True}).status_code, 200)
        self.assertTrue(self.a.get(path + "/download").content.startswith(b"PK"))

        for route in ("", "/audio", "/rows", "/review", "/download"):
            self.assertEqual(self.b.get(path + route).status_code, 404, route)
        self.assertEqual(self.b.put(path + "/chunks?offset=0", headers=h_b,
                                    content=b"x").status_code, 404)
        self.assertEqual(self.b.post(path + "/finish", headers=h_b).status_code, 404)
        self.assertEqual(self.b.put(path + "/rows", headers=h_b,
                                    json={"rows": edited}).status_code, 404)
        self.assertEqual(self.b.put(path + "/review/w1", headers=h_b,
                                    json={"reviewed": False}).status_code, 404)
        self.assertEqual(self.b.delete(path, headers=h_b).status_code, 404)
        self.assertEqual(self.b.get("/api/jobs").json()["jobs"], [])
        self.assertEqual(self.a.get(path + "/rows").json()["rows"], edited)
        self.assertTrue(folder.exists())
        self.assertEqual(self.a.delete(path, headers=h_a).status_code, 200)
        self.assertFalse(folder.exists())

    def test_missing_expired_or_replaced_cookie_cannot_access_previous_files(self):
        id_a = self._create(self.a, self.ca, "original.wav")
        cookie = self.a.cookies["beta_session"]
        self.a.cookies.delete("beta_session")
        self.assertEqual(self.a.get("/api/jobs").status_code, 401)
        self.assertEqual(self.a.get("/api/jobs/" + id_a).status_code, 401)
        self.a.get("/")  # New browser identity, never inherits old jobs.
        self.assertNotEqual(self.a.cookies["beta_session"], cookie)
        self.assertEqual(self.a.get("/api/jobs").json()["jobs"], [])
        self.assertEqual(self.a.get("/api/jobs/" + id_a).status_code, 404)
        self.assertEqual(self.a.post("/api/jobs", json={"filename": "x.wav", "size": 1}).status_code, 403)

    def test_global_anonymous_upload_limit_cannot_be_bypassed_by_new_cookies(self):
        for i in range(8):
            with TestClient(self.app, base_url="https://kiroku.example") as client:
                client.get("/")
                csrf = client.get("/api/session").json()["csrf"]
                self._create(client, csrf, f"session-{i}.wav")
        with TestClient(self.app, base_url="https://kiroku.example") as ninth:
            ninth.get("/")
            csrf = ninth.get("/api/session").json()["csrf"]
            response = ninth.post("/api/jobs", headers={"X-CSRF": csrf},
                                  json={"filename": "ninth.wav", "size": 6})
            self.assertEqual(response.status_code, 429)
        self.assertEqual(len(self.state["job_index"]), 8)

    def test_csrf_and_origin_remain_required(self):
        self.assertEqual(self.b.post("/api/jobs", json={"filename": "b.wav", "size": 6}).status_code, 403)
        self.assertEqual(self.b.post("/api/jobs", headers={
            "X-CSRF": self.ca}, json={"filename": "b.wav", "size": 6}).status_code, 403)
        self.assertEqual(self.b.post("/api/jobs", headers={
            "X-CSRF": self.cb, "Origin": "https://attacker.example"},
            json={"filename": "b.wav", "size": 6}).status_code, 403)

    def test_parallel_sessions_use_separate_job_owners(self):
        async def exercise():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="https://kiroku.example") as a, \
                       httpx.AsyncClient(transport=transport, base_url="https://kiroku.example") as b:
                await asyncio.gather(a.get("/"), b.get("/"))
                sa, sb = await asyncio.gather(a.get("/api/session"), b.get("/api/session"))
                async def create(client, label, csrf):
                    return await client.post("/api/jobs", headers={"X-CSRF": csrf},
                        json={"filename": label + ".wav", "size": 6})
                ra, rb = await asyncio.gather(
                    create(a, "parallel-a", sa.json()["csrf"]),
                    create(b, "parallel-b", sb.json()["csrf"]))
                self.assertEqual((ra.status_code, rb.status_code), (200, 200))
                ja, jb = ra.json()["id"], rb.json()["id"]
                self.assertNotEqual(ja, jb)
                la, lb = await asyncio.gather(a.get("/api/jobs"), b.get("/api/jobs"))
                self.assertEqual({x["id"] for x in la.json()["jobs"]}, {ja})
                self.assertEqual({x["id"] for x in lb.json()["jobs"]}, {jb})
                self.assertEqual((await b.get("/api/jobs/" + ja)).status_code, 404)
                self.assertEqual((await a.get("/api/jobs/" + jb)).status_code, 404)
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
