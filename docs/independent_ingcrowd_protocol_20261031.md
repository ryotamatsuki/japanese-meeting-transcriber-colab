# Independent Japanese spontaneous-dialogue benchmark protocol (locked before result inspection)

## Why another test?

Prior [PR #12](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/pull/12) was 3 recordings of acted, previously-used two-speaker J-CRe3 dialogues (community cpCER micro 45.209%; Sortformer 8.845%; Nemotron 8.477%). The largest epistemic risk is dataset-specific response and research-data reuse, NOT the lack of another diarizer.

This cohort is **IngCrowd/Japanese Themed Casual Conversation Corpus**, published August 2026, 10 real Zoom conversations with natural speech (not scripted), human-created utterance-level ELAN annotations, mixed 16kHz mono WAV. Research source: <https://huggingface.co/datasets/IngCrowd/japanese-themed-dialogue>. Dataset license **CC BY-NC 4.0**: restrict all operations here to **noncommercial R&D**; no transfer of rights to Kiroku Studio, no training, no data redistribution, no commercial exploitation. The corpus is *NOT workplace meetings*. Research conducted to evaluate, not incorporate source data.

## Frozen cohort and falsifiable prediction

Before looking at Qwen / model outputs, choose exactly:
- `japanese-themed-dialogue01`: ~11:15, mixed genders, entertainment theme.
- `japanese-themed-dialogue04`: ~12:39, mixed genders, manners theme.
- `japanese-themed-dialogue07`: ~11:35, two women, internet theme.

Whole recordings, no excerpt chosen by looking at reference or model quality. All 3 originals 16kHz mono WAV, each original human ELAN EAF only, dataset Git revision and individual six SHA256 recorded in private manifest. Do not use speaker-isolated tracks as input. Human transcript is for metrics only, never model prompt, context or bias correction.

**Prediction:** on the three independent recordings, Sortformer v2.1 and/or Nemotron 3 should improve **per-record cpCER** versus the same frozen Qwen words plus Community-1. Also examine paired DER and JER with zero-second collar and inclusion of overlap. A candidate only advances to further 4-person external research if it improves overall micro and at least 2/3 recordings and has no catastrophic regression. If results are mixed, explicit no promotion. With n=3 no claim of population significance, no hyperparameter selection using observed scores. None passes v1.0 without authentic workplace meetings and human editing time.

The three scores are:
- **CER:** normalized NFKC + casefold, remove Unicode punctuation/symbols and whitespace; flattened human turns and Qwen words in their respective original orders. Overlap and transcription annotation styles may invalidate direct CER interpretation.
- **cpCER:** global one-to-one speaker-label permutation with same Qwen words/times, same safe maximum-overlap+1.2s nearest fallback attribution across three diarizers, unknown text scored rather than omitted.
- **DER/JER:** human ELAN utterance regions, zero collar, do not suppress overlap; no invented human token timestamps. Report missed, false alarm, confusion separately.
- Record-aggregated scores use **sum of edit distances divided by sum of normalized reference characters**, not unweighted mean.
- Time per model is GPU function internal inference only; *not* uploader-to-editor E2E, editing minutes, or predicted annotation cost.

## Source validation & privacy

Use `scripts/ingcrowd_fetch_private.py` with pinned HF commit SHA and content SHA for six source files; reject any license/card change; `scripts/ingcrowd_eaf_reference.py` parses speaker_1 and speaker_2 human tiers only, time limits, bounded XML and strict two-speaker schema; no text or WAV in Git history, log or artifact. Only temporary isolated Modal Volume, deleted at workflow final step for success/failure. Ephemeral A10 jobs are invoked **only once** in manual source-code controlled GH Action, no retries; delete action YAML after use to avoid repeated billing.

## Next licensing/real-meeting gap

For **4–5 speaker planning meetings**, [NII RWCP-SP01](https://www.nii.ac.jp/dsc/idr/speech/submit/RWCP-SP01.html) offers seven simulated planning meetings, 4–5 participants, audio per speaker + whole room mic, no fee but required signed application and authorization. Its undertaking explicitly limits use to research, specified researchers and no transfer to third parties. Therefore **do not upload it to Modal without prior permission covering remote compute**. 3–4-person _genuine_ workplace meetings with consent, verbatim utterance reference and cloud processor authorization remain a necessary holdout.

For **human editing time**, instrument an editor and recruit humans for a pre-registered counterbalanced crossover: randomize clip to baseline vs candidate, measure active correction minutes and pauses, after-correction cpCER and critical-term accuracy. Automated cpCER does not yield actual editing minutes. No user participation or time estimate is fabricated.

**Release No-Go.** Published/production Kiroku Studio and main remain untouched.
