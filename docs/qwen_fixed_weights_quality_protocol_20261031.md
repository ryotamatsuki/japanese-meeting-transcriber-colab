# Kiroku Studio — Qwen3-ASR weights fixed quality study (pre-registered protocol)

Date: 2026-10-31 JST. Branch: research/qwen-fixed-weights-quality-20261031.
Frozen parent commit: 13ee84c06fa3da6339995e3f6929467ae78417e0 (PR #5).
PR #4 head at inspection: f53a1e430a5e745a27753b99b5c6337194acf8a1.
No AGENTS.md in repo root at inspected branch (GitHub 404).
**Research only; production anonymous app stays Whisper; no main merge.**

## Pre-existing data (not new results)
- Stage 17: Qwen3-ASR-1.7B/ForcedAligner-0.6B/Community-1 exclusive, human ELAN 10 2-speaker IngCrowd dialogues; cpCER median 36.60008%, Whisper 46.89493%. Qwen runs not strictly paired with Whisper, different special rescues for dialogue 02/07; no extrapolation.
- 2026-10-31 paired 1-record Whisper/Qwen: dialogue 01, exact source audio and EAF, 26.8123% vs 37.7100%; measured GPU function intervals 100.886s vs 69.550s. Tariff estimates $0.18808 vs $0.12966/audio-hour; **not bills**. [Run 41162850959](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41162850959).
- Whisper fixed-output Regular voting gave cpCER regression on two of three tests, so not promoted to Qwen without independent evidence. Community-1 Regular DER improvement does not mean cpCER improvement.
- ELAN annotation has substantial overlapping activity; true missing word counts and overlap-only CER cannot be inferred from gross text length or turn-wide overlap markers.
- Model weight names fixed: Qwen/Qwen3-ASR-1.7B, Qwen/Qwen3-ForcedAligner-0.6B; qwen-asr==0.0.6, torch etc pinned via requirements-modal.lock. **Resolved Hugging Face snapshot revision is not yet recorded and must be recorded before independent confirmatory experiment**; model name/version is insufficient to claim immutable snapshot.

## Licensed research data and private handling
IngCrowd Japanese Themed Casual Conversation Corpus, CC BY-NC 4.0, strictly noncommercial research. Human ELAN SHA256 for 01=c59daa71d0ffa34e50b4c532d33f5c0d2a51ceaa8aea4435a68a87d924f61b32; 05=e728b5e9cc74c91dfc2541dee1a404f98e3ff1b71b744512e4622d57a7; 08=36aaf89d33163770e0cbf8310245437a1d9da5f4d779416e2507917a1547392c. Same 16kHz 48kbps mono MP3 transcode from original public wav for all variants of a recording, no transcoding between variants. No audio/reference/decoded text in public logs/artifacts.

## Study A: independent screening (no production adoption)
A10 GPU, 2 CPU cores, 8 GiB memory; same forced aligner, same Community-1 **exclusive** with speakers=2. Diarization and model loaded once per recording. Each recording uses energy-boundary split from qwen-asr==0.0.6 with max 30s baseline and 15s and 45s candidates; 512 token ceiling held constant, fail-closed alignment/tail checks; no automatic replacement of erroneous transcripts. 45-second Qwen research function explicitly relaxes a safety input check from 38s to 50s while retaining all alignment validity checks. Record failure if generation truncates; do not call failed run improved.

Outputs for every recording and variant: normalized text-only flattened CER (time-ordered, overlapping reference ambiguity), cpCER, insertion/deletion/substitution count for flattened CER, predicted speaker count, alignment coverage, inferred tokens, bounded retry counts, review-flag counts, GPU inference and aggregate function time, audio SHA and EAF SHA. Human-derived exclusive speaker oracle is **only a diagnostic** and is ambiguous in simultaneous speech, never a strict error bound. Do not treat flags as confirmed transcription errors.

## Selection rule, fixed before GPU measurements
- Screening: 01 first, then 05/08 only if previous run works and workspace limit is safe; maximum 3 public research clips. One-off A10 only; no deployment/cron. Do not treat same-corpus recordings as independent holdout.
- On screening compare paired per-clip cpCER. Candidate must have >=3/3 improvements, at least 3.0pp median improvement, no failed conditions, no >2pp regression in either flattened CER or cpCER, tail coverage >=80% and estimated speakers still 2. Below 3 independent clips: insufficient evidence, no selection.
- Additional inference time and tariff estimate counted as harms; never use score-only improvements to claim product-ready.
- Bootstrap percentile CI at **recording** level if >=3 complete pairs; a CI crossing zero means insufficient evidence; it is exploratory due to model selection and shared corpus.
- No confirmatory adoption until separately sourced Japanese meetings (distinct rooms/participants) are held out and final acceptance gates including human editing are tested. A large gain on the 3 screening clips alone is not sufficient.

## Planned extensions and stop conditions
- Context: official API supports context. Implement only opt-in input handling and CPU tests. Domain-specific spoken and distractor terms lack lawful independent labeled Japanese administrative meeting audio; **context efficacy = NOT_TESTED**, not a fabricated score.
- Selective re-ASR: retain the original transcript by default; display alternatives as *review suggestions* only. Detection precision/recall needs word-level human reference, not available here.
- Regular diarization: no blind automatic reallocation. Evaluate with Qwen text held fixed if resources allow; do not conflate this with Whisper evidence.
- PCM-vs-MP3: only evaluate if original WAV is acquired and both hypotheses start from same source; converting compressed MP3 to WAV does not restore information.
- Human editing 50% reduction: NO human assessor measurements; leave NOT_RUN.

## Budget guard and limits
Previously observed on 2026-10-31 in private operator inspection: Modal Workspace Usage limit $30; credits then ~$25.48; alerts shown on. This is historical evidence, **not current account state**. Browser tab access from current session fails and no live budget dashboard was accessed. GitHub Actions workflow must fail closed unless MODAL_TOKEN_ID/SECRET are present and KIROKU_BUDGET_VERIFIED=yes, only run bounded 1-3 research clips, A10 one at a time, timeout 1800s, retries=0, max_containers=1, single_use_containers=True, scaledown_window=2. Worst-case in-function 1800s x official reference tariff $0.00034996/sec ~= $0.63 per clip (excludes container boot/idle/network), not a hard spend limit or actual invoice. Do not change spend limits, credits, alerts, existing deployed apps, model cache, user jobs or secrets. Modal GPU availability is confirmed only when inference starts.

Official docs: https://modal.com/pricing , https://modal.com/docs/guide/budgets
