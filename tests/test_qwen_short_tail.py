import unittest
from scripts.qwen_short_tail import coalesce_short_tail


class ShortTailTests(unittest.TestCase):
    def test_padded_subsecond_tail_merges_without_losing_or_inventing_samples(self):
        audio=bytearray(60*16000+1100)
        chunks=[(audio[:30*16000],0),(audio[30*16000:60*16000],30),(bytearray(8000),60)]
        result=coalesce_short_tail(audio,chunks)
        self.assertEqual([o for _,o in result],[0,30])
        self.assertEqual(b''.join(c for c,_ in result),audio)
        self.assertEqual(len(result[-1][0]),30*16000+1100)

    def test_maximum_is_preserved_by_moving_last_boundary(self):
        audio=bytearray(38*16000+1100)
        result=coalesce_short_tail(audio,[(audio[:38*16000],0),(bytearray(8000),38)])
        self.assertEqual(len(result),2)
        self.assertEqual(len(result[-1][0]),16000)
        self.assertEqual(b''.join(c for c,_ in result),audio)

    def test_normal_chunks_are_unchanged(self):
        audio=bytearray(60*16000)
        result=coalesce_short_tail(audio,[(audio[:30*16000],0),(audio[30*16000:],30)])
        self.assertEqual([len(c) for c,_ in result],[30*16000,30*16000])

    def test_unsupported_internal_tiny_chunk_is_rejected(self):
        with self.assertRaises(ValueError):
            coalesce_short_tail(bytearray(5*16000),[(b'',0),(b'',.5)])
