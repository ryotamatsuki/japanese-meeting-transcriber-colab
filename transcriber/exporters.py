"""Notebook cell 18 output schema, names, encodings and ZIP members."""
from zipfile import ZipFile, ZIP_DEFLATED
import csv
import json

def hhmmss(sec):
    sec = max(0, int(round(sec)))
    return f'{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}'

def srt_ts(sec):
    ms = max(0, int(round(sec * 1000)))
    return f'{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}'

def export(job, root, config, asr_settings, diar_settings):
    ROOT = root
    ENABLE_DIARIZATION = config.enable_diarization
    ASR_SETTINGS, DIAR_SETTINGS = asr_settings, diar_settings
    outdir, prefix = (job['outdir'], job['prefix'])
    rows, speakers = (job['utterances'], job['speaker_map'])
    txt = outdir / f'{prefix}_文字起こし.txt'
    csv_path = outdir / f'{prefix}_文字起こし.csv'
    srt = outdir / f'{prefix}_文字起こし.srt'
    mapping = outdir / '話者IDの対応表.csv'
    with txt.open('w', encoding='utf-8') as f:
        f.write(f"音声: {job['path'].name} / 機械文字起こし（要確認）\n")
        f.write('話者番号・時刻は自動推定です。役職・氏名は未特定。\n\n')
        for row in rows:
            f.write(f"[{hhmmss(row['start'])} - {hhmmss(row['end'])}] {row['speaker']}：{row['text']}\n")
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['start', 'end', 'speaker', 'utterance'])
        for row in rows:
            writer.writerow([hhmmss(row['start']), hhmmss(row['end']), row['speaker'], row['text']])
    with srt.open('w', encoding='utf-8') as f:
        for i, row in enumerate(rows, 1):
            f.write(f"{i}\n{srt_ts(row['start'])} --> {srt_ts(row['end'])}\n{row['speaker']}：{row['text']}\n\n")
    with mapping.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['モデル話者ID', '文字起こしの表示', '役職や氏名（手動記入）'])
        for raw_id, label in speakers.items():
            writer.writerow([raw_id, label, ''])
    report = {'source_filename': job['path'].name, 'source_sha256': job['sha256'], 'asr_settings': ASR_SETTINGS, 'diarization_enabled': ENABLE_DIARIZATION, 'diarization_settings': DIAR_SETTINGS if ENABLE_DIARIZATION else None, 'asr_segments': len(job['asr_segments']), 'word_intervals': job['word_count'], 'diarization_intervals': len(job['diar_segments']), 'estimated_speakers': len(speakers), 'utterances': len(rows), 'note': '機械処理結果。発言者の同一性、事業名、発言内容は必ず原音声と照合してください。'}
    report_path = outdir / '処理レポート.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    outputs = [txt, csv_path, srt, mapping, outdir / 'whisper_asr.json', report_path]
    if ENABLE_DIARIZATION:
        outputs.extend([outdir / 'pyannote_話者区間.csv', outdir / 'pyannote_話者区間.json'])
        # Experimental diagnostic files: never present in baseline output ZIPs.
        if config.quality_experiment:
            for name in ('pyannote_通常話者区間.json', 'pyannote_補正前話者区間.json', 'pyannote_重複発話確認候補.json'):
                p = outdir / name
                if p.exists():
                    outputs.append(p)
    zip_path = ROOT / f'{prefix}_文字起こし結果.zip'
    with ZipFile(zip_path, 'w', ZIP_DEFLATED, compresslevel=6) as z:
        for p in outputs:
            z.write(p, arcname=p.name)
    job['zip_path'] = zip_path
    return zip_path
