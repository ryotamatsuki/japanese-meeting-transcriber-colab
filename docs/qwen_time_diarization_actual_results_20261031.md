# J-CRe3 Qwen speaker regions vs relative timestamp error — actual A10 results (2026-10-31)

## Exact experimental scope

**Research-only / NO-GO**. [One-shot actual Modal A10 run #41193187489](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41193187489) passed all **three** 2022 J-CRe3 acted **two-person household dialogue** recordings, not real meetings. These were previously used as development records and are not independent held-out test cases. Same pinned six source audio/reference SHA256s, verified; source is official Box **preview MP3** not original WAV. Qwen3-ASR-1.7B, ForcedAligner-0.6B, Community-1, 2 fixed speakers, 30-second chunking, context disabled, same recognized text and token onset/end within each matched arm. Human text and speech never entered prompts/context. No human editing-time study.

**Method:** existing Legacy Exclusive + a separate *overlap-safe* nearest-fallback implementation that matches legacy on unshifted automatic Exclusive intervals in all three files; use the same safe method with **human turn-region** activity and exclusive/regular. Source speaker regions and token text remain fixed except the predeclared relative-region shift for sensitivity only. The human regions provide information unavailable in production. Time shifts are not learned, not deployable, and do **not** demonstrate human word timestamp precision. Strictly no threshold selection from these development/gold metrics.

## Actual measured table

Percent, lower is better. DER/JER reference uses human turn-region labels, zero-second collar and overlapping speech included. cpCER global one-to-one speaker permutation; the human-turn region arm uses the SAME safe assignment policy as the automatic safe arm. CER remains the previously measured 7.248% micro for frozen ASR.

| Human-source ID | Ref chars | Legacy Exclusive cpCER | Automatic safe cpCER | Human-turn-region safe diagnostic cpCER | DER (zero collar) | JER |
|---|---:|---:|---:|---:|---:|---:|
| 20220302-56130322-0 | 214 | 51.402 | 51.402 | 13.084 | 33.454 | 43.814 |
| 20220303-56130205-1 | 301 | 44.850 | 44.850 | 3.987 | 34.265 | 49.852 |
| 20220304-56132112-1 | 299 | 41.137 | 41.137 | 9.699 | 27.574 | 39.491 |
| **Micro, 814 reference chars** | **814** | **45.209** | **45.209** | **8.477** | — | — |

Underlying edit counts: legacy=110+135+123=368; human-region safe=28+12+29=69; reference=214+301+299=814 characters. Difference 36.732 percentage points is an **oracle-input gap**, not a measured achievable automatic improvement. The previously reported human **conservative** attribution score was 20.639% micro, versus 8.477% for human **safe-nearest** attribution, demonstrating that mixing attribution rules confounds the diagnosis. With exactly matched attribution policy the effect of replacing Community-1 regions is much larger than a global clock shift.

DER and JER were equal for Community-1 Regular and Exclusive in these three files (at zero-second collar); this does not guarantee equivalence on overlapping 3–4 speaker meetings. DER speaker confusion contribution was 7.0494, 9.4530, 9.7298 seconds per recording; the remainder includes missed speech and false alarm. Human turn timestamps are only turn-level activity annotations, not word timestamp gold.

## Predeclared shift sensitivity (diagnostic, no production use)

Reference-scored sweep of uniformly shifting *speaker intervals relative to fixed Qwen word times* by -0.6, -0.3, -0.15, 0, +0.15, +0.3, +0.6 seconds. Each arm preserved the frozen lexical text. Micro cpCER:

| Shift (seconds) | Automatic safe cpCER (micro) |
|---:|---:|
| -0.60 | 47.052% |
| -0.30 | 44.717% |
| -0.15 | 44.963% |
| 0 (unmodified) | **45.209%** |
| +0.15 | 44.717% |
| +0.30 | 45.946% |
| +0.60 | 48.894% |

The best retrospectively selected -0.30 / +0.15 shift is 44.717%, just 0.492 percentage points below baseline **in this development corpus**, with *inconsistent per-record changes*. This is not evidence of a useful fixed lag correction; any offset selected by inspecting human references would leak the test set. The unmodified (0-second) baseline remains the only pre-specified deployable configuration in this experiment.

## Operational evidence

- [Run #41193187489](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41193187489): real A10, same model weights, 3/3 successful, fixed source hash checks successful, artifact only numeric JSON.
- Artifact **13039802249** `jcre3-qwen-timing-sensitivity-metrics-only`, SHA256 `c47b7ddb41180b7da3429d6eda3f22326386ee186bdc469b58dd0074656f636c`; raw audio, original human transcription and Qwen text are absent.
- Dedicated research app was stopped; `/eval.zip` was confirmed deleted from the dedicated Modal Volume. Existing shared model cache and production app were not touched.
- All confidence / time-shift values are diagnostics only; no calibrated speaker posterior, no live editorial timing benefit, and **no real Japanese work-meeting quality claim**.

## Decision and next research investment

1. Do **not** apply global timestamp offset; effect is weak and inconsistent across the three development recordings.
2. Do **not** adopt the conservative unknown-speaker policy from PR #10; all three cpCER comparisons degraded.
3. Focus on **actual automatic diarization quality**, especially diarization speaker-confusion and missed-speech regions. Paired comparisons of Community-1 vs a second model (Sortformer, subject to architecture and license verification) should retain Qwen words/timestamps unchanged, and compare DER, JER and cpCER *together*. A better DER alone is not an adoption gate.
4. Add permission-cleared **independent authentic Japanese meetings** with human turn attribution, including 3–4 speakers and overlap, before final model choice. TalkBank Sakura has research-only/noncommercial and web-processing/non-retention restrictions in [TalkBank rules](https://talkbank.org/0share/rules.html); the dataset was **not** sent to Modal. RWCP-SP01 needs an application and Qlean data need a provision/license grant.
5. Human editing time and corrected residual errors cannot be measured by public references alone. Real randomized and counterbalanced user studies remain required for v1.

**Release: No-Go.** Draft research PR only. The one-shot GPU workflow must be removed following the experiment to avoid unintended repeat billing.
