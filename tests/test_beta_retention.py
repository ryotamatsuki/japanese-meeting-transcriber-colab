"""Stage11 physical deletion and crash/orphan safety regression."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from beta.core import JOB_TTL_SECONDS
from beta.retention import purge_expired


class RetentionTests(unittest.TestCase):
    def test_expired_complete_deleted_from_disk_and_index(self):
        with tempfile.TemporaryDirectory() as temp:
            job='a'*32
            folder=Path(temp)/job;folder.mkdir()
            (folder/'source.wav').write_bytes(b'nonpersonal test data')
            now=2000000000.
            state={'job_index':[job],'job:'+job:{'created':now-JOB_TTL_SECONDS-1,'status':'complete'}}
            counts=purge_expired(temp,state,now=now)
            self.assertFalse(folder.exists())
            self.assertEqual(counts['expired_removed'],1)
            self.assertEqual(state['job_index'],[])
            self.assertEqual(state['job:'+job]['status'],'deleted')

    def test_active_and_fresh_are_not_physically_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            now=2000000000.
            state={'job_index':[]}
            for marker,status,age in [('b','running',JOB_TTL_SECONDS+10),
                                      ('c','queued',JOB_TTL_SECONDS+10),
                                      ('d','complete',JOB_TTL_SECONDS-1)]:
                folder=Path(temp)/(marker*32);folder.mkdir()
                (folder/'audio.mp3').write_bytes(b'x')
                state['job_index'].append(marker*32)
                state['job:'+(marker*32)]={'created':now-age,'status':status}
            r=purge_expired(temp,state,now=now)
            self.assertEqual(r['active_expired_skipped'],2)
            self.assertEqual(r['expired_removed'],0)
            self.assertEqual(len(list(Path(temp).iterdir())),3)

    def test_orphan_older_than_safety_window_is_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            now=2000000000.
            orphan=Path(temp)/('e'*32);orphan.mkdir()
            (orphan/'raw.wav').write_bytes(b'x')
            old=now-JOB_TTL_SECONDS-3601
            os.utime(orphan,(old,old))
            r=purge_expired(temp,{'job_index':[]},now=now)
            self.assertEqual(r['orphan_removed'],1)
            self.assertFalse(orphan.exists())

    def test_stale_running_and_queued_are_reclaimed(self):
        with tempfile.TemporaryDirectory() as temp:
            now=2000000000.
            stale_running='7'*32
            stale_queued='8'*32
            active_running='9'*32
            state={'job_index':[stale_running,stale_queued,active_running]}
            for jid,status,age,started in [
                (stale_running,'running',JOB_TTL_SECONDS+8000,now-8000),
                (stale_queued,'queued',JOB_TTL_SECONDS+8000,None),
                (active_running,'running',JOB_TTL_SECONDS+8000,now-300),
            ]:
                folder=Path(temp)/jid;folder.mkdir()
                (folder/'source.mp3').write_bytes(b'x')
                row={'created':now-age,'status':status}
                if started is not None:
                    row['started_at']=started
                state['job:'+jid]=row
            outcome=purge_expired(temp,state,now=now)
            self.assertEqual(outcome['stale_active_reclaimed'],2)
            self.assertEqual(outcome['expired_removed'],2)
            self.assertTrue((Path(temp)/active_running).exists())
            self.assertFalse((Path(temp)/stale_running).exists())
            self.assertFalse((Path(temp)/stale_queued).exists())
            self.assertEqual(state['job:'+active_running]['status'],'running')

    def test_failed_disk_delete_does_not_claim_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            now=2000000000.
            job='f'*32
            folder=Path(temp)/job;folder.mkdir()
            state={'job_index':[job],'job:'+job:{'created':now-JOB_TTL_SECONDS-1,'status':'complete'}}
            with patch('beta.retention.shutil.rmtree',side_effect=OSError('simulated storage error')):
                with self.assertRaises(OSError):
                    purge_expired(temp,state,now=now)
            self.assertEqual(state['job:'+job]['status'],'complete')
            self.assertTrue(folder.exists())


if __name__=='__main__':
    unittest.main()
