"""Strict reader for J-CRe3's human ELAN tab exports (CC BY-SA 4.0).

Retain spoken fillers and responses; remove annotation syntax only. Never
use the reference to choose audio windows or recognition context.
"""
import hashlib
import math
import re


def load_reference(data: bytes):
    if not 0 < len(data) <= 1024*1024:
        raise ValueError('Invalid reference size')
    rows=[]
    for line in data.decode('utf-8-sig').splitlines():
        if not line.strip():
            continue
        fields=line.split('\t')
        if len(fields)!=12 or fields[0] not in ('主人','ロボット'):
            raise ValueError('Unexpected ELAN export schema')
        start,end=float(fields[3]),float(fields[6])
        if not (math.isfinite(start) and math.isfinite(end) and 0<=start<end<=900):
            raise ValueError('Invalid reference timing')
        if (abs(start*1000-float(fields[4]))>.01 or
            abs(end*1000-float(fields[7]))>.01 or
            abs(end-start-float(fields[9]))>.002):
            raise ValueError('Inconsistent ELAN time columns')
        text=fields[11].replace('<H>','').replace('(P)','')
        text=re.sub(r'\((?:F|R) ([^()]*)\)',r'\1',text).strip()
        if re.search(r'[<>()]',text):
            raise ValueError('Unknown transcription annotation')
        if text:
            rows.append({'start':start,'end':end,'speaker_id':fields[0],'text':text})
    if len(rows)<4 or {r['speaker_id'] for r in rows}!={'主人','ロボット'}:
        raise ValueError('Expected human two-speaker reference')
    return sorted(rows,key=lambda r:(r['start'],r['end'],r['speaker_id'])),hashlib.sha256(data).hexdigest()
