# Kiroku Studio v1: reproducible error decomposition (research only)

Date: 2026-10-31. Branch: research/qwen-error-decomposition-v1-20261031. Base: PR #8 (not main).

## Current evidence and explicit limitations

Historical Qwen-on-J-CRe3 pilot (three acted domestic two-person recordings, all development data): flattened micro CER 7.248%, micro cpCER 45.209%, per-recording cpCER 51.402%, 44.850%, 41.137%. **Do not subtract CER from cpCER to infer speaker errors.** Different speaker/text order, edit alignment, omissions and overlap all influence the measures. Neither a new unseen administrative meeting nor a human editing-time study is available in this PR. No v1 acceptance claim is made.

PR #7 text-only boundary Qwen accepted all nine eligible pairs and did not beat the rule baseline. PR #8's acoustic plus text split arm had false splits. These are not added to the released editor. Prior regular-vs-exclusive speaker voting was mixed and is not automatically adopted.

## What is implemented

- `scripts/qwen_error_decomposition.py`: **fixed lexical Qwen output**, the existing Exclusive legacy grouping, conservative Exclusive group assignment, conservative Regular group assignment, and (when available) human **turn-region** activity as a diagnostic-only upper-information scenario. Same source characters and timestamps are held fixed, checked against every output by normalized equality and SHA256. cpCER uses the existing global one-to-one speaker-label permutation. Additional flattened CER uses one ordered ELAN text stream and is explicitly flagged as order-dependent.
- `IntervalIndex`: interval starts with prefix-maximum ends, rather than bisection over an unsorted end array. Handles overlapping or nested Regular diarization. Duplicate intervals for one speaker are unioned to avoid double counting.
- Conservative arm never assigns from the closest interval across silence. Short (<0.05s), estimated/end-placeholder, low coverage (<0.55), ambiguous vote (<0.70), and no-overlap words are **abstentions**; their characters remain and are charged in cpCER. Thresholds are research defaults pending validation, not probability calibration.
- Timestamp provenance: `aligned_unverified`, `realigned` (same-length lexical boundary redistribution), `estimated` (end-of-file inferred placeholder), and `invalid` (reject/abstain only). **Direct ForcedAligner output is not confirmed by human listening.** Order repairs in the legacy export are not interpreted as acoustically verified timestamps.
- Optional timing-only arm accepts another timed Qwen output only if **the same ordered lexical token units** are present. The comparison reports downstream cpCER, not timing accuracy, because human word start/end times do not currently exist.
- Strict rejection of content changes or evaluation-order mismatch prevents invalid apparent improvements. Results/logs contain hashes, counters and metrics only. Private EAF, audio, word text, and full hypotheses remain off GitHub.
- No modification to production Studio, Qwen weights, default Whisper, public Modal endpoint, or automatic postprocessing.

## Reproduce on a permission-cleared private evaluation workstation

Use **the same source recording**, frozen Qwen chunk output and existing Community-1 speaker segments. The speaker tiers must represent independently annotated human speakers, not ASR-generated labels. Standard and Exclusive must be from the same run. Python dependencies are those already required by existing ELAN/cpCER evaluators.

```sh
python -m unittest tests.test_qwen_error_decomposition -v
python -m scripts.qwen_error_decomposition \
  --eaf /private/reference.eaf \
  --qwen /private/qwen_timed.json \
  --exclusive /private/community_exclusive.json \
  --regular /private/community_regular.json \
  --output /private/metric_only.json
```

The Qwen JSON must contain `duration_seconds` and `chunks` as accepted by `scripts/qwen_timing_bridge.py`. The audio and human references must not be passed to Qwen as context. `--timing-alternative` may be supplied for a **pre-frozen** timing-only hypothesis. A strict 2-4-speaker ELAN reference loader is now included (`scripts/v1_meeting_reference.py`). Automatic tier discovery accepts `speaker_1`...`speaker_4`; use `--speaker-tiers` with explicit human tier IDs for other annotation conventions. This is syntactic ingestion, NOT human validation of the reference or permission to run it on Modal.

## Experiment sequence (frozen before held-out use)

1. Use development recordings to establish data integrity, compare metrics, inspect why review flags co-occur with human errors. Preserve original raw audio in approved private storage and include a manifest with hashes, sample rate, channel, acquisition/consent/license, speaker labels, recording conditions, ASR version/commit, Qwen context, Community-1 version, processing configuration, and permission-to-cloud flag.
2. Fix the actual ASR output and timing, compare Legacy vs conservative Exclusive/Regular and reference turn-region arm. Count unassigned characters, reference ordering, overlap incidence, same-word/cpCER integrity. Report per-recording paired differences **including degradation**, and time-order rejections.
3. Freeze ASR and diarization, apply an independent local timing candidate to **the same tokens**, with invalid intervals rejected. Until human word-level annotations are available, do not report a word-timing error reduction.
4. Only after diagnostics prioritize VAD-ASR mismatch, silence hallucinations, deletions, and local selective re-ASR. Keep original and replacement texts separately and evaluate whether re-recognition harms or helps on held-out references.
5. Reserve a separate set of permission-cleared **real Japanese meetings** (two-, three-, four-person; quiet/far-field/overlap) for a one-time final evaluation. The past three J-CRe3 and ten IngCrowd recordings are **development**, not held-out meetings. Never use the held-out set to choose thresholds. Use meeting-level paired bootstrap intervals, not token-level pseudo-replication.

## Proposed v1 release gates — provisional, not achieved

- **Data**: target at least 20 independent, permission-cleared real meetings, with distinct development and sealed final test sets; include at least two different real recording settings and 2/3/4-speaker conditions. This is an operational minimum, **not** guaranteed statistical power. Pre-register the minimum detectable effects and confidence interval policy before evaluation.
- **Accuracy**: for a human-checked **verbatim** transcription use case, proposed initial target median normalized CER <= 15% and median cpCER <= 25% on held-out real meetings, while also publishing full distributions, uncertainty intervals and tail cases. These are **proposed product targets**, not currently observed values; adjust only through a documented scope decision made before seeing final test data. Speaker-number error, overlap deletion, numeric and named-entity errors must be reported separately. Do not certify by CER alone.
- **Candidate acceptance**: no model/threshold change based only on pooled characters or oracle labels; prefer recording-level paired non-inferiority of key metrics and convincing improvements in user correction effort. Any variant with uncontrolled false speaker certainty or increased critical-value errors is rejected.
- **Human benefit**: randomized/counterbalanced real-editor tests against manual transcription/old pipeline; measure time to a checked export and residual errors. Proposed target: at least 50% median time reduction versus manual baseline without worse residual critical errors, with a pre-registered paired interval. No synthetic click timing accepted.
- **Operations and privacy**: real iPhone/Safari, 60-minute edit/save/download E2E, simultaneous owners, failure recovery, enforced processing limits, spend/credit cap, retention and actual object deletion, cross-tenant isolation, consent/legal review and secure logs. Repeat failure-injection tests. Track wall time, GPU time, all-in spend and failure rate without pretending GPU-seconds equal invoice amount.
- **Stop rule**: after independent ablations cease yielding repeatable end-user benefits that exceed their GPU/runtime/maintenance costs, stop precision research and ship a clearly scoped, reviewed v1. A tiny cpCER gain on already tuned recordings does not qualify.

**Release disposition (2026-10-31): NO-GO.** Research branch only; new real meetings, independent human word/boundary reference and actual editor time trial remain external requirements.
