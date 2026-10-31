import unittest
from beta.progress import progress_snapshot

class ProgressTests(unittest.TestCase):
    def test_measured_audio_and_monotone_stage(self):
        a=progress_snapshot(None,'preparing',now=100)
        self.assertNotIn('audio_done',a)
        b=progress_snapshot(a,'asr',done=10,total=60,now=110)
        self.assertEqual((b['audio_done'],b['audio_total'],b['phase_started_at']),(10,60,110))
        c=progress_snapshot(b,'asr',done=8,total=60,now=115)
        self.assertEqual(c['audio_done'],10)
        d=progress_snapshot(c,'asr',done=80,total=60,now=120)
        self.assertEqual(d['audio_done'],60)
        e=progress_snapshot(d,'diarization',now=150)
        self.assertNotIn('audio_done',e)
        self.assertEqual(progress_snapshot(e,'asr',now=160),e)
        self.assertEqual(progress_snapshot(e,'formatting',now=170)['phase'],'formatting')
        self.assertEqual(progress_snapshot(e,'saving',now=180)['phase'],'saving')
    def test_unknown_stage_and_unbounded_estimates_are_not_advertised(self):
        with self.assertRaises(ValueError):
            progress_snapshot(None,'fake',done=50,total=100,now=1)
        for total in (0,-1,float('inf'),float('nan')):
            p=progress_snapshot(None,'asr',done=10,total=total,now=1)
            self.assertNotIn('audio_done',p)
        p=progress_snapshot(None,'asr',done=0,total=60,now=10)
        self.assertEqual(p['audio_done'],0)
    def test_never_serialize_content(self):
        event=progress_snapshot({},'asr',done=3.0,total=12.0,now=100)
        self.assertEqual(set(event),{'phase','phase_started_at','updated_at','audio_done','audio_total'})
if __name__=='__main__':
    unittest.main()
