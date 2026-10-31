"""Public preview must never expose private jobs, recordings or GPU actions."""
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from modal_public_preview import create_preview_app, SAMPLE_ID


class PasswordlessPublicPreviewTests(unittest.TestCase):
    def test_public_preview_is_read_only_and_sample_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"assets").mkdir()
            (root/"index.html").write_text(
                '<!doctype html><script src="/ui/assets/demo.js"></script>',
                encoding="utf-8")
            (root/"assets"/"demo.js").write_text("console.log('public preview')",encoding="utf-8")
            (root/"nope.js").write_text("never serve",encoding="utf-8")
            with TestClient(create_preview_app(root), base_url="https://example.org") as client:
                self.assertEqual(client.get("/").status_code,200)
                self.assertEqual(client.get("/ui/assets/demo.js").status_code,200)
                self.assertEqual(client.get("/ui/assets/../nope.js").status_code,404)
                self.assertEqual(client.get("/api/session").json()["limits"]["gpu_jobs_24h"],0)
                records=client.get("/api/jobs").json()["jobs"]
                self.assertEqual(len(records),1)
                self.assertEqual(records[0]["id"],SAMPLE_ID)
                self.assertIn("架空",records[0]["filename"])
                self.assertEqual(client.get("/api/jobs/"+SAMPLE_ID+"/rows").status_code,200)
                self.assertEqual(client.get("/api/jobs/"+SAMPLE_ID+"/review").status_code,200)
                self.assertEqual(client.get("/api/jobs/"+"a"*32).status_code,404)
                self.assertEqual(client.get("/api/jobs/"+SAMPLE_ID+"/audio").status_code,404)
                self.assertEqual(client.get("/api/jobs/"+SAMPLE_ID+"/download").status_code,404)
                self.assertEqual(client.post("/api/jobs",json={"filename":"test.wav","size":100}).status_code,403)
                self.assertEqual(client.put("/api/jobs/"+SAMPLE_ID+"/rows",json={"rows":[]}).status_code,403)
                self.assertEqual(client.delete("/api/jobs/"+SAMPLE_ID).status_code,403)
                self.assertIn("script-src 'self'",client.get("/").headers["content-security-policy"])
                self.assertTrue(client.get("/healthz").json()["preview_only"])


if __name__=="__main__":
    unittest.main()
