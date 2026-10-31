# Public-license J-CRe3 actual-GPU attribution ablation — 2026-10-31

## Final outcome: do NOT adopt conservative assignment

[GitHub Actions one-shot A10 PASS #41190743599](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41190743599). The job completed the actual A10 Qwen3-ASR-1.7B + ForcedAligner-0.6B + Community-1 inference on three public J-CRe3 recordings, read human turn references, evaluated the same fixed recognized words under multiple speaker attribution policies, uploaded a **metrics-only** artifact #13038054505 (SHA256 `f4329d5517dc4bf2c59fc08c5b29cd04e4704f2d9c688f4aba954f5a18811bbd`), and successfully deleted `/eval.zip` from the dedicated test Modal volume. The app was stopped. No raw audio, human transcript or recognized text is published.

These recordings are *acted two-person household activity conversations*, NOT authentic meetings and NOT a new held-out corpus: the recordings were used in prior PR #6/#8 development. Audio previews were MP3 transcodes, not original WAVs. Three source audio SHA256s and three human reference SHA256s match the frozen source manifest. The reconstructed ZIP hash can change because ZIP metadata/compression differs; source identity is established by **the six individual hashes**, not ZIP container bytes.

## Raw numeric measurement

Values in percent; `delta_pp` = conservative Exclusive cpCER minus legacy baseline cpCER, positive is deterioration. Same frozen Qwen ASR text and aligned times for all attribution arms. Exact reference character counts and error counts are provided for reproducibility.

| Recording | Ref chars | Flattened CER | Legacy Exclusive cpCER | Conservative Exclusive cpCER | Conservative Regular cpCER | Human turn-region diagnostic cpCER | delta_pp |
|---|---:|---:|---:|---:|---:|---:|---:|
| 20220302-56130322-0 | 214 | 12.617 | 51.402 | 56.075 | 56.075 | 19.626 | +4.673 |
| 20220303-56130205-1 | 301 | 3.322 | 44.850 | 50.831 | 50.831 | 15.282 | +5.980 |
| 20220304-56132112-1 | 299 | 7.358 | 41.137 | 53.512 | 53.512 | 26.756 | +12.375 |
| **Micro (814 reference chars)** | **814** | **7.248** | **45.209** | **53.194** | **53.194** | **20.639** | **+7.985** |

Legacy cpCER edit counts 110/135/123 = 368. Conservative cpCER edit counts 120/153/160 = 433. Human-turn diagnostic edit counts 42/46/80 = 168. Flattened edit counts 27/10/22 = 59. Each micro score = sum edits / 814, not an unweighted recording average. The comparator's cpCER uses the same existing one-to-one global speaker-label matching. Neither CER vs cpCER subtraction nor change in the diagnostic human-turn arm is an estimate of *speaker error alone*.

The conservative approach abstains rather than guessing at gaps, short aligner tokens, or unclear attribution; the existing cpCER appropriately counts unassigned characters as errors rather than deleting them. In this evaluation, **cpCER worsened on each of the three recordings**. Regular vs Exclusive in the current conservative arm produces the same cpCER on all three. Do not use these numbers to claim that all regular diarization alternatives have equal accuracy. Text-only CER was unchanged because there was no new recognition.

A human turn-region reference is privileged diagnostic input—not deployable product predictions or verified human word onsets. Its apparently lower cpCER (~20.64%) suggests meaningful timing/speaker-segmentation investigation, but does not establish the cause or an attainable production score. This is developmental evidence (3 correlated recordings; no independent confidence interval for actual meetings).

## Human edit-time evidence

**Not measured.** An audio+reference corpus by itself cannot establish participant editing time, keyboard interaction count, or residual error after editing. No simulated runtime, GPU model runtime, or cpCER is presented as human editing-time savings.

## Adoption and next data source

- **Reject** this automatic conservative-attribution policy for deployment under the present loss function; preserve original Qwen ASR/Community-1 product baseline and PR#9 as research-only diagnostic tools.
- For independent 4-speaker spontaneous round-table *conversation* (not an administrative meeting), the [original CABank Sakura corpus](https://talkbank.org/ca/access/Sakura.html) contains 18 audio recordings, total 7h30, 4 participants in a conference room and linked human transcripts. [TalkBank/Hugging Face mirror](https://huggingface.co/datasets/talkbank/sakura) is a candidate for **license/processor transfer and reference-format validation first**. Its topic-card student conversations are not authentic local-government work meetings. Do not assume all mirror licenses are the same, or that user research rights imply permission to rehost.
- RWCP-SP01 is research use by application; Qlean is access-by-request. Neither was silently acquired or transferred to Modal. A valid authentic administrative meeting holdout needs explicit cloud authorization and independently validated speaker/time reference.
- Randomized/counterbalanced humans using Studio vs baseline/manual transcription must supply edit-time and post-edit critical-term correctness. Until then **v1 release No-Go**.

Code: `modal_qwen_open_audio_decomposition.py` on this branch; the one-shot GPU launch/harvest/inspection workflow files were removed after the successful run to prevent accidental repeated paid GPU invocation. Public default Studio and `main` unchanged.
