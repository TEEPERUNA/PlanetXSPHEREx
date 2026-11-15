# Backend Handoff

Owner: Erik · Folder: `backend/` · Structure and flow: [`STRUCTURE.md`](STRUCTURE.md) · API format: [`../CONTRACT.md`](../CONTRACT.md)
AI-assisted: written with Claude (Anthropic).

## Live service

| | |
|---|---|
| API | https://planetx-api-38053485414.us-east4.run.app |
| Docs (try every endpoint) | https://planetx-api-38053485414.us-east4.run.app/docs |
| Platform | Google Cloud Run, service `planetx-api`, region `us-east4` |
| Settings | Instance-based billing, min 1 / max 1 instance, 1 CPU, 2 GiB, second-generation runtime |
| Cache | Cloud Storage bucket `planetx-cache-erik` mounted at `/data` |
| Deploys | Automatic from `main` (Cloud Build trigger, root `Dockerfile`) |
| Data | SPHEREx DR1/QR3 via IRSA SIA + AWS S3 `s3://nasa-irsa-spherex` (public, no credentials) |

Keep max instances at **1**: job state lives in memory.

## For the frontend

1. `GET /api/sky?ra=..&dec=..&fov=..` (or `?target=barnard`).
2. If `status` is `done`: use `meta` and `base_url` right away.
3. Otherwise poll `GET /api/status/<job>` every ~2 s. Show `preview` as soon as it is not `null`, and show `done / total` and `stage` as progress.
4. Image URL = `API + base_url + path from meta.json`. `base_url` is relative and can start with `/api/files/` **or** `/api/examples/`, so never hard-code it.
5. On HTTP 400/404/500 the body is `{"detail": "..."}`; show it to the user. 500 responses include CORS headers, so the browser shows the real message.
6. Set `VITE_API_BASE_URL=https://planetx-api-38053485414.us-east4.run.app` (in `frontend/.env` locally, UTF-8, and in Vercel's Environment Variables). Without it the frontend falls back to `localhost:8000`.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate                 # Mac/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```
Open http://localhost:8000/docs. Results go to `output/` (gitignored).
Useful while developing: `WARMUP=0` (skip fetching the 5 targets on start), `FETCH_MODE=irsa` (test the fallback).

## Deploy

Merge to `main` → Cloud Build builds the `Dockerfile` → new Cloud Run revision (5–10 min).
Check: Cloud Run → `planetx-api` → Revisions (green tick, 100 % traffic) → `/api/health`.

Change settings without code (CPU, memory, env vars): Cloud Run → `planetx-api` → **Edit & deploy new revision**.

## Test checklist

| Test | Expected |
|---|---|
| `/api/health` | `{"ok": true}` |
| `/api/targets` | 5 targets, `cached: true` after warm-up |
| `/api/sky?target=barnard` | `done` instantly; `diff_ALL.png` shows the star moving north |
| `/api/sky?ra=83.82&dec=-5.39` | `queued` → `preview` → `done` |
| `/api/sky?ra=abc&dec=1` | 400 |
| `/api/sky?ra=10&dec=20&fov=50` | 400 |
| `/api/sky?target=nope` | 404 |

## Logs and debugging

Cloud Run → `planetx-api` → **Observability → Logs**. Useful filters:
- `TIMING` – per run: `search | download | processing | total` seconds
- `S3:` – how many cutouts came from S3 and how long it took
- `falling back` – S3 failed, IRSA cutout service was used
- `Traceback` – errors

Measured on Cloud Run (S3 route): challenge targets 11–24 s total (download 7–16 s, processing 1–7 s).

## Known issues

- **Free coordinates are slow in processing (~100 s)** because the science module queries the ESA Gaia archive live (`validate_gaia`). Asked Emil for a timeout and a `skip_gaia` flag; once it exists, the quick preview should skip Gaia (one line in `Pipeline.__call__`).
- **SIMBAD is sometimes down** → long warnings in the logs; the science module falls back to built-in coordinates, results are fine.
- `RuntimeWarning: All-NaN slice` in logs is harmless (empty edges of a cutout).
- Results in `examples/` have no `cache.json`, so the first request triggers a background refresh into the cache. This is expected.

## Costs and shutdown

- Runs on the Google Cloud free trial credit (~257 €); one always-on instance is roughly 50–60 €/month.
- Budget alert is set to 5 € of real (non-credit) cost.
- **After judging:** Cloud Run → `planetx-api` → Delete (or set minimum instances to 0), and delete the bucket if no longer needed.
