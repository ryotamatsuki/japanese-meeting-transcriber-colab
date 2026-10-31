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

## Four real-LLM synthetic A10 runs (2026-10-31)

The Qwen3-4B-Instruct-2507 model was actually loaded and used on **Modal A10**.
All inputs were deliberately synthetic Japanese utterances; no real recordings
or human transcripts were transferred in these runs. Qwen3-ASR-1.7B weights
were untouched. The temporary one-shot CI GPU-trigger workflow was deleted
after these runs. All numbers are from the run's numeric-only logs.

| Protocol / evidence | Synthetic cases | Findings |
|---|---:|---|
| [Run 41178993676](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41178993676) | 8 | Initial conservative prompt missed both intended joins; safety restrictions prevented other joins |
| [Run 41179182216](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41179182216) | 12 | 3 intended joins found; 3 false joins (finished sentence, fast acknowledgement, ambiguous reply) |
| [Run 41179329077](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41179329077) | 18 | 5 intended joins found; 3 false joins on unpunctuated complete clauses and topic shifts |
| [Run 41179503156](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41179503156) | 22 | 7 intended joins found; 2 false joins on topic shifts following grammatically incomplete fragments |

Final run: 20/22 match manually designated synthetic boundary judgments,
7/7 intended joins, 2 false joins, 13 correct nonjoins. These figures are NOT
speech transcription accuracy or an independent test-set generalization rate.
The first 18 examples were used for iterative rule/prompt development; the
four later probe examples were also inspected here and cannot subsequently
count as an untouched holdout.

Final-run A10 GPU function duration 35.733 seconds, of which 31.232 seconds
was model loading. The original CI test suite plus research extensions ran
235 offline tests successfully, and React build / browser checks succeeded:
[latest post-inference CI](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41179503108).
GPU function time excludes image build, CI queues, storage, and billing overhead.

### Root cause and decision

An instruction LLM systematically over-merged when given permissive join
candidates, including independent topic changes. Hard guardrails blocked
finished sentences, rapid acknowledgements and clauses that do not show
obvious grammatical incompleteness. Still, two valid-looking incomplete
fragments were in fact conversational topic switches, and Qwen proposed to
merge them. In the absence of the source audio, no reliable speaker/turn
grounding exists for these cases.

**Research-only / review-only; do NOT automatically replace transcript rows
in public Studio.** This procedure must not be claimed to improve cpCER: all
word text and speaker assignments are fixed. Next evaluation needs
license-cleared Japanese meeting recordings with independent human turn
boundary annotations, and user edit-time measurement. A supervised text-only
boundary classifier or an audio-conditioned model should be compared against
Qwen and deterministic heuristics before a production decision.

## Status

Implemented and tested with synthetic scenarios on both CPU and real A10 Qwen.
Live Japanese meeting audio ground-truth tests, model-level unseen-source
validation, human editing studies, production integration, and commercial
acceptance are **not complete**. The code intentionally keeps every proposed
change out of the production pipeline.
