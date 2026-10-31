import io
import json
import unittest
import zipfile
from beta.core import (make_session,verify_session,csrf_for,normalize_edits,build_export,
                       validated_extension,MAX_SECONDS,MAX_AUDIO_BYTES,csv_safe)

class BetaCoreTests(unittest.TestCase):
    def test_cookies(self):
        tok=make_session('long-secret',now=1000)
        self.assertTrue(verify_session('long-secret',tok,now=1010))
        self.assertFalse(verify_session('bad-secret',tok,now=1010))
        self.assertFalse(verify_session('long-secret',tok,now=1000+12*3600+1))
        self.assertFalse(verify_session('long-secret',tok+'x',now=1010))
        self.assertEqual(len(csrf_for('long-secret',tok)),64)
    def test_edits(self):
        rows=normalize_edits([{'start':.1,'end':.5,'text':'確認','speaker':'A'},
                              {'start':.3,'end':.9,'text':'はい','speaker':'B'}],1)
        self.assertEqual(len(rows),2)  # allow actual simultaneous conversation
        for data in [[{'start':-1,'end':1,'text':'a','speaker':'A'}],
                     [{'start':.9,'end':.8,'text':'a','speaker':'A'}],
                     [{'start':0,'end':float('nan'),'text':'a','speaker':'A'}]]:
            with self.assertRaises(ValueError): normalize_edits(data,1)
    def test_csv_injection(self):
        self.assertEqual(csv_safe('=HYPERLINK(...)'),"'=HYPERLINK(...)")
        data=build_export([{'start':0,'end':1,'speaker':'=1+1','text':'@evil'}])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn("'=1+1",z.read('文字起こし.csv').decode('utf-8-sig'))
            self.assertIn('文字起こし.srt',z.namelist())
    def test_extensions(self):
        self.assertEqual(validated_extension('a.M4A'),'.m4a')
        with self.assertRaises(ValueError): validated_extension('malware.exe')

if __name__=='__main__': unittest.main()