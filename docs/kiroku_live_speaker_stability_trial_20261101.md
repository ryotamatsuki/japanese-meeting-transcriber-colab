# 2026-11-01 JST — Real public anonymous Studio opt-in speaker-stability trial deployment

## Verified result

**Success**: [GitHub Actions #41255336971](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41255336971).
Deployed existing `kiroku-anonymous-studio-beta` by `modal deploy beta_modal_anonymous.py` with the existing Volume, Dict, A10, Community-1, Whisper large-v3 and signature secret.
Public endpoint: <https://ryota-matsuki--kiroku-anonymous-studio-beta-anonymous-web.us-east.modal.run/>

- `TRIAL_UI_BUNDLE=PASS`
- `TRIAL_MODAL_DEPLOY=PASS`
- `LIVE_TRIAL_UI_ASSETS=PASS`
- `LIVE_OWNER_SCOPED_SESSION_AND_JOBS=PASS`
- Deploy job and workflow **success**, rollback **skipped**.

## Usage

On the new transcription form, check `話者分離の改善を試す` before upload to enable word-level short A–B–A stabilization. The checkbox defaults to **OFF**. New and prior jobs run unaltered baseline when not explicitly opted in; trial jobs are marked `話者補正の試験モード` in the file list. Server accepts only strict boolean settings and retains owner isolation, same rate limits and retention policy.

This trial deliberately does not incorporate the separate, not-yet-deployed progress UI of PR #15.

## What is not verified

No GPU transcription was launched during live smoke verification; user is expected to test permitted non-confidential audio. The existing pyannote Community-1 weights and Whisper large-v3 are unchanged. The experimental 450 ms rule does **not** have demonstrated human-referenced DER or cpCER improvement. If testing against the same audio, avoid post-hoc threshold tuning on the held-out file. Do not interpret visual tidiness as speaker accuracy; listen to potential true short acknowledgements. All raw audio remains private.

The experimental code is on Draft PR #17, extending Draft PR #16. Nothing merged to `main`.
