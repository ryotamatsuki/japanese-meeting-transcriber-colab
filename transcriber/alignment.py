"""Extracted from notebook cell 16; algorithm unchanged."""
from bisect import bisect_right

def assign_and_group(asr_segments, diar_segments, enable_diarization=True):
    ordered = sorted(diar_segments, key=lambda r: (r['start'], r['end']))
    ends = [r['end'] for r in ordered]
    raw_to_label = {}
    for r in ordered:
        if r['speaker_id'] not in raw_to_label:
            raw_to_label[r['speaker_id']] = f'話者{len(raw_to_label) + 1}'

    def speaker_for(start, end):
        if not ordered:
            return '話者未設定' if not enable_diarization else '話者不明'
        start, end = (float(start), max(float(start), float(end)))
        idx = bisect_right(ends, start)
        scores = {}
        j = idx
        while j < len(ordered) and ordered[j]['start'] < max(start + 0.01, end):
            r = ordered[j]
            overlap = max(0.0, min(end, r['end']) - max(start, r['start']))
            if overlap > 0:
                scores[r['speaker_id']] = scores.get(r['speaker_id'], 0.0) + overlap
            j += 1
        if scores:
            return raw_to_label[max(scores, key=scores.get)]
        center = (start + end) / 2.0
        near = ordered[max(idx - 1, 0):min(idx + 2, len(ordered))]
        if not near:
            return '話者不明'
        chosen = min(near, key=lambda r: max(r['start'] - center, 0, center - r['end']))
        distance = max(chosen['start'] - center, 0, center - chosen['end'])
        return raw_to_label[chosen['speaker_id']] if distance <= 1.2 else '話者不明'
    words = []
    for seg in asr_segments:
        for w in seg.get('words') or []:
            if str(w.get('text', '')).strip():
                words.append({'start': float(w['start']), 'end': float(w['end']), 'text': str(w['text']), 'speaker': speaker_for(w['start'], w['end'])})
        if not seg.get('words') and str(seg.get('text', '')).strip():
            words.append({'start': float(seg['start']), 'end': float(seg['end']), 'text': str(seg['text']), 'speaker': speaker_for(seg['start'], seg['end'])})
    words.sort(key=lambda r: (r['start'], r['end']))
    MAX_CHARS, MAX_SECONDS, MAX_PAUSE = (110, 22, 1.5)
    utterances, current = ([], None)
    for w in words:
        if current is None:
            current = {'start': w['start'], 'end': w['end'], 'speaker': w['speaker'], 'parts': [w['text']]}
            continue
        pause = w['start'] - current['end']
        too_long = w['end'] - current['start'] > MAX_SECONDS or sum(map(len, current['parts'])) + len(w['text']) > MAX_CHARS
        if w['speaker'] != current['speaker'] or pause > MAX_PAUSE or too_long:
            content = ''.join(current['parts']).strip()
            if content:
                utterances.append({'start': current['start'], 'end': current['end'], 'speaker': current['speaker'], 'text': content})
            current = {'start': w['start'], 'end': w['end'], 'speaker': w['speaker'], 'parts': [w['text']]}
        else:
            current['end'] = max(current['end'], w['end'])
            current['parts'].append(w['text'])
    if current:
        content = ''.join(current['parts']).strip()
        if content:
            utterances.append({'start': current['start'], 'end': current['end'], 'speaker': current['speaker'], 'text': content})
    return (utterances, raw_to_label, len(words))
