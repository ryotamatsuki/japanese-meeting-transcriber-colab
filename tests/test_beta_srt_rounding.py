"""Stage11 reproduction: SRT 1-ms rounding cannot break entire transcript save."""
import csv
import io
import json
import zipfile
import unittest
from beta.core import parse_original_archive, normalize_edits


def synthetic_archive_with_zero_duration(n=1200):
    stream=io.BytesIO()
    c=io.StringIO()
    writer=csv.writer(c)
    writer.writerow(['start','end','speaker','utterance'])
    lines=[]
    for i in range(n):
        second=i*2
        stamp=f"00:{second//60:02d}:{second%60:02d},000"
        stamp2=stamp if i%7==0 else f"00:{second//60:02d}:{second%60:02d},400"
        writer.writerow(['00:00:00','00:00:01','話者1','会議の発言'])
        lines.append(f"{i+1}\n{stamp} --> {stamp2}\n話者1：会議の発言\n")
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('処理レポート.json',json.dumps({'original':'reference'}))
        z.writestr('sample_文字起こし.csv','\ufeff'+c.getvalue())
        z.writestr('sample_文字起こし.srt','\n'.join(lines))
    return stream.getvalue()


class SrtTimePrecisionTests(unittest.TestCase):
    def test_all_model_generated_rows_can_be_saved_and_edited(self):
        parsed=parse_original_archive(synthetic_archive_with_zero_duration())
        rows=parsed['rows']
        self.assertEqual(len(rows),1200)
        self.assertGreater(parsed['report']['rounded_srt_zero_duration_repairs'],0)
        clean=normalize_edits(rows,2400)
        self.assertEqual(len(clean),1200)
        self.assertTrue(all(row['end']>row['start'] for row in clean))

    def test_no_repair_for_valid_duration(self):
        parsed=parse_original_archive(synthetic_archive_with_zero_duration(6))
        self.assertGreater(parsed['rows'][1]['end'],parsed['rows'][1]['start'])
        self.assertEqual(parsed['rows'][0]['end']-parsed['rows'][0]['start'],.001)

    def test_real_invalid_user_time_is_still_rejected(self):
        with self.assertRaises(ValueError):
            normalize_edits([{'start':1,'end':1,'speaker':'話者1','text':'はい'}],10)

if __name__=='__main__':
    unittest.main()
