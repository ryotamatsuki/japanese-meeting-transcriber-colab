# Passwordless public preview (no GPU)

This is **not the production transcription application**. It is a public, read-only preview of the selected Studio design. The website displays only fabricated meeting entries; there are no real uploads, GPU inference, downloadable transcripts or persistent server-side edits.

To make the preview:
```bash
cd frontend
npm install
VITE_PREVIEW_ONLY=true npm run build
cd ..
modal deploy --name kiroku-public-studio-preview modal_public_preview.py
```

The production app must instead build without `VITE_PREVIEW_ONLY` and use its own authenticated `beta_modal_qwen_research.py` deployment.

Safety principles:

* Dedicated Modal CPU app; no `transcriber-beta-auth`, `transcriber-hf`, Volume, Dict, or GPU worker wired to this preview.
* Reject every non-GET method server-side (HTTP 403), including upload, save, review updates, and DELETE; disallow audio and ZIP GETs.
* CSP restricts assets to same origin. All sample text is fictitious.
* Not a staging instance for confidential or personal meeting recordings.
* Public URL means anyone can view the design and may trigger tiny CPU serving charges. Free credits are not a hard monetary cap.

Before opening real uploads without a password, implement anonymous per-visitor job isolation, non-bypassable cost budgets, resource quotas, retention and abuse prevention; then rerun real Modal end-to-end checks.
