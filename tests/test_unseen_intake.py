import hashlib
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from scripts.unseen_intake import create_intake


class Volume:
    def __init__(self):self.commits=0
    def commit(self):self.commits+=1


class FixedCorpusIntakeTests(unittest.TestCase):
    def test_only_exact_input_is_written_and_nothing_is_readable(self):
        data=b'synthetic fixture only'
        with tempfile.TemporaryDirectory() as root:
            volume=Volume()
            client=TestClient(create_intake(volume,root,hashlib.sha256(data).hexdigest(),len(data)))
            self.assertEqual(client.put('/ingest',content=b'x'*len(data)).status_code,422)
            self.assertEqual(client.put('/ingest',content=data+b'x').status_code,413)
            self.assertEqual(volume.commits,0)
            self.assertFalse((Path(root)/'eval.zip').exists())
            self.assertEqual(client.put('/ingest',content=data).status_code,200)
            self.assertEqual((Path(root)/'eval.zip').read_bytes(),data)
            for path in ('/ingest','/eval.zip','/docs','/openapi.json','/evaluate'):
                self.assertIn(client.get(path).status_code,(404,405))
