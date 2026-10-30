# Stage 37 — React UI (private alpha)

- Frontend: React 19, TypeScript, Vite, lucide-react; no external CDN/fonts.
- Backend: existing FastAPI routes and signed HttpOnly cookie, CSRF/Origin checks, Modal A10 Qwen worker.
- Must be served from **the same origin** as FastAPI; do not expose a public GitHub Pages site against a protected API.
- The backend maintains the canonical transcript; audio/text are not saved in browser localStorage or external analytics.

## Local development

From repo root, run the existing authenticated FastAPI server with a **test-only** backend and permitted recordings. In another shell:

```sh
cd frontend
npm install
npm run typecheck
npm run build
npm run dev
```

The Vite proxy routes /api, /login and /logout to 127.0.0.1:8000. For authenticated local development, use the backend login and the actual matching origin; alternatively test the built UI via FastAPI at /.

## Modal deployment packaging

Run `npm install && npm run build` in `frontend/` **before deploying**. This writes a production bundle to `beta/react_dist/`. The existing Modal `web_image.add_local_dir('beta', remote_path='/root/beta')` includes this directory and FastAPI serves the compiled index and assets from the same origin. If the build is absent, the original HTML/JS alpha UI remains as an explicit fallback; no uncompiled JSX is sent to browsers.

Do not push generated dist or node_modules into the public repository. Never embed Modal tokens, API keys, or auth secrets in Vite `VITE_*` environment variables. Password login remains in the original protected /login form.

## Functional acceptance

- Login required for home and assets; no external scripts, preserving CSP.
- Chunk upload up to 180 MiB, duration 1–60 min enforced by backend.
- Queue/run/status, edit transcript, sync audio, speaker badges, overlap review, save, ZIP export, delete.
- Disallow ZIP download while local changes remain unsaved; warn before switching jobs or leaving page.
- Paginate long transcripts to keep 60-minute recordings responsive.
- Only nonconfidential, permission-cleared audio. Research model output must be checked against original audio.

No accuracy, user time savings, or public beta authorization is inferred from a UI build.
