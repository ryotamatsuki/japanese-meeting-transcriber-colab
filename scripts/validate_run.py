"""Validate real-run artifacts structurally; never certifies transcription/DER accuracy."""
import argparse
import json
from pathlib import Path
import re
from zipfile import ZipFile


def validate(path, stage, off=False):
    with ZipFile(path) as archive:
        assert archive.testzip() is None, 'ZIP CRC failure'
        names = archive.namelist()
        assert not any(n.lower().endswith(('.wav','.mp3','.m4a','.bin')) for n in names)
        if stage != 'diarization':
            record = json.loads(archive.read('whisper_asr.json'))
            assert record['settings']['model'] == 'large-v3'
            segments = record['segments']
            assert segments and any(re.search('[ぁ-んァ-ヶ一-龯]', s['text']) for s in segments), 'No Japanese speech recognized'
            words = [w for s in segments for w in s['words']]
            assert words, 'No word timestamps'
            assert all(0 <= w['start'] <= w['end'] for w in words)
            assert [w['start'] for w in words] == sorted(w['start'] for w in words)
        if stage != 'asr' and not off:
            record = json.loads(archive.read('pyannote_話者区間.json'))
            intervals = record['segments']
            assert record['settings']['model'] == 'pyannote/speaker-diarization-community-1'
            assert intervals, 'No speaker intervals'
            assert all(0 <= r['start'] < r['end'] for r in intervals)
            assert all(a['end'] <= b['start']+1e-6 for a,b in zip(intervals,intervals[1:])), 'Exclusive intervals overlap'
        if stage == 'full':
            for suffix in ('txt','csv','srt'):
                assert any(n.endswith('_文字起こし.'+suffix) for n in names)
            report = json.loads(archive.read('処理レポート.json'))
            assert report['utterances'] > 0
            assert report['diarization_enabled'] == (not off)
            if off:
                assert not any('pyannote' in n for n in names)
            else:
                assert report['estimated_speakers'] > 0
                srt = archive.read(next(n for n in names if n.endswith('.srt'))).decode()
                assert re.search('話者[0-9]+', srt), 'No assigned speaker labels'
    return 'PASS: structural checks only; listening/reference comparison is still required'


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('zip',type=Path);p.add_argument('--stage',choices=['asr','diarization','full'],default='full')
    p.add_argument('--off',action='store_true');args=p.parse_args()
    print(validate(args.zip,args.stage,args.off))
