# Kiroku Studio: Second-pass Qwen text boundary experiment (B)

Research branch only; public Studio and default Whisper pipeline are unchanged.

## What is actually implemented

- A separate Qwen3-4B-Instruct-2507 text LLM adapter for an explicitly configured OpenAI-compatible local endpoint (vLLM or equivalent). **Qwen3-ASR-1.7B weights are unchanged.**
- Each request contains a bounded series of diarized lines and eligible join/split boundaries. The model returns index-only JSON, NEVER rewritten text.
- Independent validators prohibit cross-speaker merges, unknown labels, overlaps, long gaps, finished-sentence joins across pauses, backchannel joins, and exceeding duration/size constraints.
- Split only on explicitly provided word-aligned boundaries; the current original-ZIP importer usually only exposes utterance rows, so **the CLI currently tests merging, not splitting, on existing exported archives**.
- A chain of merges is checked *after* grouping; any violation, malformed output or timeout preserves **all original rows**. Source indices are kept. No auto-apply to Studio or main.
- Local-only HTTP endpoint by default, remote HTTPS requires an explicit command switch and authorization to send recording text.
- Offline tests use synthetic Japanese conversations; they measure guardrail behavior, not Qwen model reasoning accuracy or real cpCER.

## Example study (private input)

First serve `Qwen/Qwen3-4B-Instruct-2507` through a local OpenAI-compatible endpoint, for example via vLLM. Then run:

```bash
python scripts/qwen_text_boundary_cli.py \
  --archive /private/original.zip \
  --endpoint http://127.0.0.1:8000/v1/chat/completions \
  --output /private/qwen_boundary_proposal.json
python -m unittest tests.test_qwen_text_boundary_postprocess -v
```

No transcript text is printed, but private output JSON includes verbatim content. Never commit it. Running in a different cloud environment requires explicit permission and an isolated endpoint.

## Safety / evaluation protocol

A (baseline): original utterance rows.
B (text-only): same-speaker joins / word-timed splits, unchanged text, speaker identities unchanged.

Use identical untouched recording and human ELAN reference, and log numeric-only:
- source row count, proposed join/split counts, rejected requests;
- true positive / false positive against human turn boundaries;
- number of false joins, with emphasis on backchannels / simultaneous speech;
- retained exact transcript bytes (mandatory), speaker assignment (mandatory);
- cpCER / CER expected to remain identical for same-speaker join-only edits if the scorer concatenates per-speaker text without separators, hence not an appropriate sole B success metric;
- human review/edit time and residual mistakes for actual user-facing value.

Important: B alone **cannot** fix an incorrectly labelled speaker, since changing speaker labels is forbidden. That requires a separate, audio-grounded C study.

## Status

Implemented in a dedicated branch with synthetic multi-pattern regression tests. No real Qwen-LLM inference, live Modal test, licensed meeting comparison, or human edit-time trial has been performed as part of this branch yet. A production quality claim is prohibited.
