"""Bounded, read-only model-estimated overlap review candidates for beta users."""
from __future__ import annotations
import io
import json
import math
from zipfile import ZipFile, BadZipFile

CANDIDATE_FILE='pyannote_重複発話確認候補.json'
MAX_SHOW=1500
MAX_RAW=50000


def review_candidates_from_archive(raw_zip: bytes, duration: float):
    """Preserve original ASR text/attribution. No person identity is inferred."""
    if not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration<=0:
        raise ValueError('Invalid recording duration')
    with ZipFile(io.BytesIO(raw_zip)) as z:
        if CANDIDATE_FILE not in z.namelist():
            return {'available':False,'total_candidates':0,'windows':[],
                    'warning':'No model overlap estimates for this job'}
        meta=z.getinfo(CANDIDATE_FILE)
        if meta.file_size>8*1024*1024:
            raise ValueError('Overlap candidate file too large')
        payload=json.loads(z.read(CANDIDATE_FILE))
    raw=payload.get('segments')
    if not isinstance(raw,list) or len(raw)>MAX_RAW:
        raise ValueError('Too many or malformed overlap candidates')
    valid=[]
    for item in raw:
        if not isinstance(item,dict):
            raise ValueError('Malformed review window')
        try:
            a,b=float(item['start']),float(item['end'])
            n=len(item['speaker_ids'])
        except (KeyError,TypeError,ValueError):
            raise ValueError('Malformed review interval') from None
        if not (math.isfinite(a) and math.isfinite(b) and 0<=a<b<=duration+0.75 and 2<=n<=10):
            raise ValueError('Invalid overlap interval')
        if b-a<0.20:
            continue
        valid.append((round(a,3),round(b,3),n))
    valid.sort()
    windows=[{'id':f'ov-{i:05d}','start':a,'end':b,'speaker_count':n}
             for i,(a,b,n) in enumerate(valid[:MAX_SHOW])]
    return {'available':True,'total_candidates':len(valid),'windows':windows,
            'warning':'These are model-estimated overlap candidates, not confirmed speakers or words.'}
