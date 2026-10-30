"""Single-file orchestration with no Colab or Modal dependency."""
from dataclasses import dataclass
from pathlib import Path
import json
import time

from .files import safe_name, sha256_file
from .alignment import assign_and_group
from .exporters import export


@dataclass(frozen=True)
class Config:
    enable_diarization: bool = True
    language: str = 'ja'
    glossary: str = ''
    expected_speakers: int = 0
    min_speakers: int = 0
    max_speakers: int = 0
    quality_experiment: bool = False
    speaker_cleanup_ms: int = 0

    def __post_init__(self):
        counts = (self.expected_speakers, self.min_speakers, self.max_speakers)
        if any(type(n) is not int or n < 0 for n in counts):
            raise ValueError('話者数は0以上の整数で指定してください。')
        if self.min_speakers and self.max_speakers and self.min_speakers > self.max_speakers:
            raise ValueError('MIN_SPEAKERSはMAX_SPEAKERS以下にしてください。')
        if type(self.quality_experiment) is not bool:
            raise ValueError('quality_experiment must be boolean')
        if type(self.speaker_cleanup_ms) is not int or not 0 <= self.speaker_cleanup_ms <= 300:
            raise ValueError('speaker_cleanup_ms must be between 0 and 300')
        if self.speaker_cleanup_ms and not self.quality_experiment:
            raise ValueError('Experimental cleanup requires quality_experiment=True')
        if self.speaker_cleanup_ms and not self.enable_diarization:
            raise ValueError('Cannot clean speaker labels with diarization OFF')
        if self.language not in ('ja', 'auto', 'en'):
            raise ValueError('language must be ja, auto or en')


def process(path, output_root, model_cache, config=None, token=None, stage='full'):
    from .asr import transcribe
    from .diarization import diarize
    config = config or Config()
    if stage not in ('asr', 'diarization', 'full'):
        raise ValueError('Invalid stage')
    if config.enable_diarization and stage != 'asr' and not token:
        raise RuntimeError('HF_TOKEN is required: configure Modal Secret transcriber-hf and accept Community-1 conditions.')
    path, output_root = Path(path), Path(output_root)
    if not path.is_file():
        raise FileNotFoundError('Input audio does not exist')
    output_root.mkdir(parents=True, exist_ok=True)
    digest = sha256_file(path)
    prefix = f'{safe_name(path.stem)}_{digest[:10]}'
    outdir = output_root / prefix
    outdir.mkdir(parents=True, exist_ok=True)
    job = dict(path=path, sha256=digest, prefix=prefix, outdir=outdir)
    metrics = {'stage': stage}
    started = time.perf_counter()
    if stage != 'diarization':
        asr_settings = transcribe(job, config, Path(model_cache), metrics)
    if stage != 'asr':
        diar_settings = diarize(job, config, token, metrics)
    if stage == 'full':
        merge_started = time.perf_counter()
        job['utterances'], job['speaker_map'], job['word_count'] = assign_and_group(
            job['asr_segments'], job['diar_segments'], config.enable_diarization)
        if config.quality_experiment and config.enable_diarization:
            from .attribution_review import audit_word_speaker_assignments
            standard_path = outdir / "pyannote_通常話者区間.json"
            standard = (json.loads(standard_path.read_text(encoding="utf-8"))["segments"]
                        if standard_path.exists() else [])
            audit = audit_word_speaker_assignments(job["asr_segments"], job["diar_segments"],
                                                   standard)
            (outdir / "話者割当て要確認.json").write_text(
                json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
            metrics["word_attribution_review_words"] = audit["review_words"]
            metrics["word_attribution_total_words"] = audit["word_count"]
        zip_path = export(job, output_root, config, asr_settings, diar_settings)
        metrics['alignment_export_seconds'] = time.perf_counter() - merge_started
        metrics['estimated_speakers'] = len(job['speaker_map'])
    else:
        from zipfile import ZipFile, ZIP_DEFLATED
        zip_path = output_root / (prefix + '_' + stage + '.zip')
        with ZipFile(zip_path, 'w', ZIP_DEFLATED) as archive:
            for item in outdir.iterdir():
                archive.write(item, item.name)
        if stage == 'diarization':
            metrics['estimated_speakers'] = len({s['speaker_id'] for s in job['diar_segments']})
    metrics['pipeline_seconds'] = time.perf_counter() - started
    metrics_path = output_root / (prefix + '_metrics.json')
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    return zip_path, metrics
