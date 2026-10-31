"""Pure-Python validation, exports and credential primitives for private v0.1 beta."""
from __future__ import annotations
import csv
import hashlib
import hmac
import io
import json
import mimetypes
import re
import secrets
import time
import zipfile
from pathlib import Path

MAX_AUDIO_BYTES = 180 * 1024 * 1024
MAX_SECONDS = 3600
CHUNK_BYTES = 4 * 1024 * 1024
MAX_JOBS = 2
JOB_TTL_SECONDS = 24 * 3600
EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".mp4", ".webm"}
JOB_ID = re.compile(r"^[a-f0-9]{32}$")


def valid_job_id(value: str) -> bool:
    return bool(JOB_ID.fullmatch(value))


def validated_extension(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError("Unsupported audio container")
    return suffix


def make_session(secret: str, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    token = f"{now}.{secrets.token_hex(16)}"
    signature = hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
    return f"{token}.{signature}"


def verify_session(secret: str, token: str, now: int | None = None, max_age=12*3600) -> bool:
    try:
        stamp, nonce, signature = token.split(".")
        if not stamp.isdecimal() or not re.fullmatch(r"[a-f0-9]{32}", nonce):
            return False
        now = int(time.time()) if now is None else now
        if int(stamp) > now + 60 or now - int(stamp) > max_age:
            return False
        expected = hmac.new(secret.encode(), f"{stamp}.{nonce}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


def csrf_for(secret: str, session: str) -> str:
    return hmac.new(secret.encode(), ("csrf:" + session).encode(), hashlib.sha256).hexdigest()


def normalize_edits(raw, duration: float):
    if not isinstance(raw, list) or len(raw) > 5000:
        raise ValueError("Too many or invalid utterances")
    out = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Invalid utterance")
        try:
            s, e = float(item['start']), float(item['end'])
        except (ValueError, KeyError, TypeError):
            raise ValueError("Invalid timestamps") from None
        import math
        if not all(map(math.isfinite, (s, e))) or not 0 <= s < e <= duration + 0.5:
            raise ValueError("Timestamps out of range")
        text, who = item.get('text'), item.get('speaker')
        if not isinstance(text, str) or not isinstance(who, str) or len(text) > 6000 or len(who) > 80:
            raise ValueError("Invalid transcript fields")
        if not who.strip():
            who = '話者未設定'
        start_ms, end_ms = round(s, 3), round(e, 3)
        # Original s<e has been validated. Preserve a positive but sub-ms
        # interval that would otherwise become invalid after rounding.
        if start_ms == end_ms:
            end_ms = round(start_ms + 0.001, 3)
            if end_ms > duration + 0.5:
                raise ValueError("Timestamps out of range after rounding")
        out.append({'start': start_ms, 'end': end_ms,
                    'speaker': who.strip(), 'text': text})
    out.sort(key=lambda r: (r['start'], r['end']))
    # Do not require non-overlap: real speakers may talk simultaneously.
    return out


def srt_time(sec):
    millis = int(round(max(0, sec)*1000))
    return f'{millis//3600000:02d}:{millis//60000%60:02d}:{millis//1000%60:02d},{millis%1000:03d}'


def csv_safe(s):
    value = str(s)
    if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
        return "'" + value
    return value


def build_export(rows, *, source_name='meeting') -> bytes:
    """Exports user-verified edits. Text files are not labelled as verified unless edited."""
    rows = list(rows)
    transcript = ''.join(f"[{srt_time(r['start'])}–{srt_time(r['end'])}] {r['speaker']}: {r['text']}\n" for r in rows)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['start', 'end', 'speaker', 'utterance'])
    for r in rows:
        w.writerow([r['start'], r['end'], csv_safe(r['speaker']), csv_safe(r['text'])])
    subtitles = ''.join(f"{i}\n{srt_time(r['start'])} --> {srt_time(r['end'])}\n{r['speaker']}: {r['text']}\n\n" for i, r in enumerate(rows, 1))
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('文字起こし.txt', transcript)
        z.writestr('文字起こし.csv', '\ufeff' + out.getvalue())
        z.writestr('文字起こし.srt', subtitles)
        z.writestr('文字起こし.json', json.dumps({'source': source_name, 'utterances': rows,
            'disclaimer': 'Automatic transcript; verify against audio'}, ensure_ascii=False, indent=2))
    return payload.getvalue()


def parse_original_archive(data: bytes):
    """Read only normalized exported utterances; never extract untrusted paths."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if z.testzip() is not None:
            raise ValueError('Broken ZIP')
        names = z.namelist()
        report = json.loads(z.read('処理レポート.json'))
        import csv as csvlib
        csvname = next(x for x in names if x.endswith('_文字起こし.csv'))
        lines = csvlib.DictReader(io.StringIO(z.read(csvname).decode('utf-8-sig')))
        srtname = next((x for x in names if x.endswith('_文字起こし.srt')), None)
        def seconds(value):
            hh, mm, ss = map(int, value.split(':'))
            return hh*3600+mm*60+ss
        rows = [{'start':seconds(row['start']), 'end':seconds(row['end']),
                 'speaker':row['speaker'], 'text':row['utterance']} for row in lines]
        if srtname:
            parsed=[]
            src=z.read(srtname).decode('utf-8-sig')
            for block in re.split(r'\n\s*\n',src):
                block_lines=block.strip().splitlines()
                if len(block_lines)<3: continue
                timing=block_lines[1].split(' --> ')
                if len(timing)!=2: continue
                def from_ts(t):
                    h,m,tail=t.strip().split(':');sec,ms=tail.split(',')
                    return int(h)*3600+int(m)*60+int(sec)+int(ms)/1000
                text='\n'.join(block_lines[2:])
                if '：' in text:
                    who,text=text.split('：',1)
                elif ':' in text:
                    who,text=text.split(':',1)
                else:
                    who='話者未設定'
                parsed.append({'start':from_ts(timing[0]),'end':from_ts(timing[1]),
                               'speaker':who,'text':text})
            if len(parsed)==len(rows):
                # SRT timestamps have only millisecond resolution. Very short
                # model-generated spans can round to the same millisecond even
                # though the underlying timestamps were strictly increasing.
                # A zero-length row cannot be saved by normalize_edits.
                # Repair equality *only*; do not mask reversed or bad times.
                repaired=0
                for row in parsed:
                    if row['start']==row['end']:
                        row['end']=round(row['start']+0.001,3)
                        repaired+=1
                if repaired:
                    report['rounded_srt_zero_duration_repairs']=repaired
                rows=parsed
        return {'rows':rows, 'report':report}