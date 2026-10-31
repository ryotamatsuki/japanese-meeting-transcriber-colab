# Qwen second-pass utterance boundary study: frozen four-arm comparison

Date: 2026-10-31. Research-only; never modifies public Kiroku Studio or main.
Base: Draft PR #7. The first-stage Qwen3-ASR-1.7B, ForcedAligner-0.6B and
Community-1 remain fixed in the J-CRe3 real-audio trial.

## Research question and 4 matched arms

This does **not** attempt speaker relabeling, lexical text rewriting, or source
WAV replacement. Only the decision to merge adjacent display rows is evaluated.

- A **No formatting**: always keep the original boundary.
- B **Rules only**: deterministic grammar/punctuation-based rule from PR #7.
- C **Text + Qwen**: separate Qwen3-4B-Instruct-2507 sees the target boundary
  and up to two preceding and two following utterances plus ASR timestamps.
- D **Observed audio metadata + same Qwen**: exactly C's context and candidate
  universe, plus real waveform-derived dBFS RMS before/inside/after the
  boundary and measured gap. The current implementation does **not** measure
  pitch, emotion, a calibrated speaker identity confidence or voice timbre;
  such features are represented as null, not fabricated.

All arms see the same *frozen* adjacent-same-speaker candidate universe, with
non-overlap, max gap 3 seconds, max group duration 36 seconds, and max
combined text 220 characters. These safety guards exclude some true joins
and report **candidate coverage**. Never interpret accuracy within candidates
as an all-boundary quality score.

C and D must choose one of merge/keep/hold, with a strict index-only JSON
response. Invalid responses and model failures abstain (hold). Every result
is a separate review layer; underlying lexical bytes, speaker labels and
original timestamps remain canonical.

## J-CRe3 provenance

Data: [J-CRe3](https://github.com/riken-grp/J-CRe3), Ueda et al.,
LREC-COLING 2024; CC BY-SA 4.0.

Three existing pilot recordings from PR #6 (not new independent data).
Official preview MP3, **not original WAV**. Public J-CRe3 README's ordinary
password-protected Box sharing UI was used (no credential bypass) to fetch
exactly the same bytes. Source revision, audio SHA256, and ELAN transcription
SHA256 must match `docs/jcre3_unseen_manifest_20261031.json`.
The reacquisition run verified **3 audio + 3 human reference files**.

Audio/transcript text are not stored in the public GitHub tree, CI artifacts
or normal logs. They exist temporarily within a GitHub Actions worker and
a separately named Modal Volume, with removal after the job. A one-time GPU
job is used and the temporary auto-trigger is removed after validation.

## Boundary ground truth limitations

Human ELAN contains annotated utterance start/end and speaker, but does not
directly answer the UI editing question 'should these particular ASR rows be
merged?'. We therefore enforce the following distinction:

- **Provisional ELAN time-alignment proxy**: ASR rows must each overlap one
  ELAN human turn by at least 75% with no competing turn over 20%. Two rows
  both in one human turn -> proxy merge; a row change between different
  speakers -> proxy keep; same speaker but distinct turns, overlap ambiguity,
  and weak alignment -> **uncertain**, excluded from numeric rate denominators.
- **Human-verified final labels**: must come from private annotation sheets,
  independently judged with audio listening, with second annotator and an
  adjudication note for disagreements. The runner refuses to call proxy labels
  human-reviewed gold.

The J-CRe3 three recordings are now development data, regardless of model
training exposure. They are acted household conversations with two speakers,
not an administrative 3–4-person meeting. A recording-held-out meeting test
and annotator disagreement study remain required.

## Metrics and decision rule

Each arm reports for the same labeled candidates: true merges, false merges,
missed merges, hold, false merge rate (among keep-gold), miss rate (among
merge-gold), number of unscored uncertain boundaries, and candidate coverage.
No denominator is silently zero-filled. For independent recordings, bootstrap
differences using *recording* as the resampling unit, not boundaries.

The priority is minimizing false merges; an improvement in recall alone is
insufficient. Hold has a measurable user-review burden, not a free success.
A real-world user editing-time randomized/counterbalanced study is not part
of the present automated test and must not be claimed.

**Important:** For same-speaker merges with unchanged text, flattened CER and
speaker-permutation cpCER are normally unchanged. Evaluation of readability
or editing time is a separate causal/product question.

## Synthetic A10 test, not a speech benchmark

[One-shot Qwen synthetic four-arm A10 run](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41183833613):
16 human-designed miniature cases with artificial constant-amplitude tones and
programmed gaps; NOT real speech. Aggregates:

| Arm | Correct joins | False joins | Missed joins |
|---|---:|---:|---:|
| A unchanged | 0 | 0 | 6 |
| B rules | 6 | 8 | 0 |
| C text Qwen | 6 | 9 | 0 |
| D artificial acoustics Qwen | 5 | 8 | 1 |

**No gain from C or D** is supported by this diagnostic. The synthetic tones
cannot demonstrate the value of actual prosody. Future design should compare
measured VAD, pitch continuity and speaker embeddings only once calibrated.

## Separate split study (research extension)

The real-audio merge pilot obtained 13/15/15 ASR utterances versus
14/23/22 human ELAN turns; only 2/0/2 merge candidates survived, and only
1/0/1 boundaries had unambiguous ELAN-derived proxy labels. It cannot
support a positive uplift claim for C or D. This motivated a **separate**
within-utterance split study, without loosening safety across speaker changes.

`scripts/qwen_boundary_split_study.py` reconstructs the exact Qwen
ForcedAligner token sequence, rejects any lexical/timestamp discrepancy,
and selects up to 16 within-utterance candidate boundaries per recording.
It combines boundaries with punctuation or pauses and a deterministic
sample of ordinary control boundaries, all selected before seeing reference
labels. Four corresponding split decisions are
(A) keep, (B) punctuation/pause rule, (C) Qwen text, (D) real audio RMS/gap
metadata plus the same Qwen. Outputs are **split/keep/hold** and split-specific
false-split and missed-split counts. Split denominators are not combined
with join denominators. If forced-aligned text cannot be mapped exactly to
the editor row, that recording is marked unavailable for splits.

Any ELAN-derived split labels are still provisional. No real listening
adjudication has yet taken place.

## Research-only modules

- `scripts/qwen_boundary_fourarm.py`: candidate universe, RMS, strict actions,
  4 arms, scores and recording-level bootstrap.
- `scripts/jcre3_boundary_adjudication.py`: provisional ELAN alignment and
  strict two-rater human annotation gate.
- `scripts/run_qwen_fourarm_private.py`: offline real audio/ASR ZIP runner,
  source SHA pin option, local-only LLM endpoint by default.
- `scripts/jcre3_reacquire_private.py`: official re-acquisition with SHA pins.
- `modal_qwen_jcre3_fourarm.py`: one-shot A10 real J-CRe3 trial.
- Unit tests: `test_qwen_boundary_fourarm.py`,
  `test_jcre3_boundary_adjudication.py`,
  `test_qwen_fourarm_private_contract.py`.

## Release decision

Always **Draft / No-Go** until an *independently adjudicated* Japanese meeting
test shows C or D reduces false joins against rules at comparable useful recall
and without unacceptable GPU/latency overhead. No automatic merge into Studio.
