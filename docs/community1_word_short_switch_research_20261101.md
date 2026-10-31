# Community-1 / Whisper weights frozen — short speaker-switch ablation (2026-11-01)

## Why
A real meeting transcript excerpt exhibited mid-phrase A–B–A labels, including '助詞だけ別話者' patterns. Without source audio, it cannot prove which speaker is correct. Improve the quality **without replacing Whisper large-v3, pyannote Community-1, or the GPU pipeline** by testing the separate post-inference attribution rule.

## Pre-existing evidence and hazards
- Existing `collapse_short_islands` operates on the raw exclusive diarization intervals at 0–300 ms and is experimental, not production-approved. This proposal is different: it operates on **speaker-labelled Whisper words after alignment**, so it can specifically target output fragmentation.
- In PR #10's three previously seen acted 2-speaker J-CRe3 development recordings, a different conservative attribution rule actually worsened micro cpCER from **45.209% to 53.194%**; no blanket suppression policy is justified.
- PR #11's timing shift improved pooled micro cpCER only 0.492 percentage points at retrospectively chosen lags; changes were inconsistent, and no shift was adopted.
- No ground-truth audio or verified per-word speaker assignment accompanies the current user-provided transcript; **zero validated actual-audio improvement is claimed**.

## Proposed diagnostic arm
Compare matched, frozen words and pyannote intervals; run the unchanged baseline first, then `quality_experiment=True, word_stability_ms=450`. The optional research algorithm in `transcriber/speaker_stability.py` finds tiny A–B–A 'islands' only when:
- B's contiguous utterance is at most 450 ms (research sensitivity arms 150/300/450/600 ms), no more than two token units.
- Both neighbouring A runs have at least 650 ms of contiguous evidence, with no more than 200 ms discontinuity at either island boundary.
- Labels and word time boundaries are valid and ordered; 'unknown' and absent speakers are never silently filled.
- Known short acknowledgements (e.g. `はい`, `うん`, `そうですね`) are protected; **lexical protection is only a defensive rule and not acoustic proof**.
- Reassignment changes only the **speaker label** of the flagged word. No text, start/end timestamps, word count, or original source JSON is modified.

The experimental arm is entirely disabled in default `Config()`, and its use requires `quality_experiment=True`. Public anonymous Studio, GPU deployment and Model weights are unchanged.

## What is NOT proved
A flag count is not accuracy. Fewer speaker switches can be worse diarization if authentic short backchannels are merged. A-B-A can be true conversation. The current sample has no vetted human word/turn reference, so visual plausibility and synthetic tests **cannot** establish an improved DER, JER or cpCER.

## Required evaluation
1. Fix model / ASR input/word times and keep the same Community-1 Exclusive timeline, regular overlap marks and speaker count. Use exact same words for baseline and each candidate; no whole-recording ASR repeats needed.
2. Obtain cloud-permitted, non-confidential real meetings with human-labelled speaker turns, **at least 2–4 actual speakers including brief interjections and overlapping speech**. Development threshold tuning and independent final evaluation must use separate recordings.
3. Record paired meeting-level `DER`, `JER`, `cpCER` and *micro-turn false-merge count*, separately for overlap, backchannels and non-speech. A valid improvement must not achieve lower false splits by wiping real speaker boundaries.
4. Compare the original output + our default merged same-speaker presentation in an editor, measure how often the user corrects speaker IDs and the real time spent on those corrections. Keep corrected transcript and raw references private; only aggregate metrics may enter CI artifacts.
5. Choose the narrowest threshold that improves both attribution and editing time without unacceptable false merges on independent recordings. Otherwise reject this arm and retain the original baseline.

## Repro
`python -m unittest tests.test_speaker_stability -v`
Run the full repo offline CI. Synthetic tests validate correctness and safety constraints, not effectiveness. No inference is needed to run these.

## Status
**Research candidate, not production-ready. Do not deploy by default.**
Related research: [PR #10](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/pull/10), [PR #11](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/pull/11).
