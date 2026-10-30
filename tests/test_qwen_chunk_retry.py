"""CPU fixtures for bounded model failover, no Qwen weights or raw audio."""
import unittest
from types import SimpleNamespace
from scripts.qwen_chunk_retry import infer_chunk
from scripts.evaluate_asr_cer import normalized_ja


class Fake:
    def __init__(self,max_seconds):
        self.max_seconds=max_seconds
        self.calls=0

    def transcribe(self,*,audio,language,return_time_stamps):
        samples,sr=audio
        self.calls+=1
        text='はい'
        spoken='はい' if len(samples)/sr<=self.max_seconds else 'は'
        return [SimpleNamespace(text=text,time_stamps=SimpleNamespace(
            items=[SimpleNamespace(text=spoken,start_time=0.,
                                   end_time=len(samples)/sr-0.05)]))]


class QwenChunkRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.audio=bytearray(30*16000)

    def test_success_has_no_retries(self):
        model=Fake(30)
        rows,meta=infer_chunk(model,self.audio,0)
        self.assertEqual(len(rows),1)
        self.assertEqual(model.calls,1)
        self.assertEqual(meta['retries'],0)

    def test_failed_thirty_recovers_at_fifteen(self):
        model=Fake(16)
        rows,meta=infer_chunk(model,self.audio,100)
        self.assertEqual(len(rows),2)
        self.assertEqual(meta['retries'],1)
        self.assertEqual(rows[0]['offset_sec'],100)
        self.assertEqual(rows[1]['offset_sec'],115)
        self.assertEqual(model.calls,3)
        self.assertTrue(all(normalized_ja(r['text'])==
                            normalized_ja(''.join(w['text'] for w in r['items']))
                            for r in rows))

    def test_bounded_two_level_fallback(self):
        model=Fake(10)
        rows,meta=infer_chunk(model,self.audio,0)
        self.assertEqual(len(rows),4)
        self.assertEqual(meta['retries'],3)
        self.assertEqual(model.calls,7)

    def test_irrecoverable_alignment_fails_closed(self):
        model=Fake(1)
        with self.assertRaisesRegex(ValueError,'bounded retries'):
            infer_chunk(model,self.audio,0)
        self.assertEqual(model.calls,3)

    def test_rejects_invalid_bounds(self):
        with self.assertRaises(ValueError):
            infer_chunk(Fake(30),self.audio,-1)
        with self.assertRaises(ValueError):
            infer_chunk(Fake(30),self.audio,0,max_retries=5)


if __name__=='__main__':unittest.main()
