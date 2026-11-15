# Backend Handoff

Owner: Erik · Folder: `backend/` · Structure and flow: [`STRUCTURE.md`](STRUCTURE.md) · API format: [`../CONTRACT.md`](../CONTRACT.md)
AI-assisted: written with Claude (Anthropic).

## Live service

| | |
|---|---|
| API | https://planetx-api-38053485414.us-east4.run.app |
| Docs (try every endpoint) | https://planetx-api-38053485414.us-east4.run.app/docs |
| Platform | Google Cloud Run, service `planetx-api`, region `us-east4` |
| Settings | Instance-based billing, **min 1 / max 1** instance, 1 CPU, 2 GiB, second-generation runtime |
| Cache | Cloud Storage bucket `planetx-cache-erik` mounted at `/data` (volume `cache`) |
| Deploys | Automatic from `main` (Cloud Build trigger, root `Dockerfile`), 5–10 min |
| Data | SPHEREx DR1/QR3 via IRSA SIA + AWS S3 `s3://nasa-irsa-spherex` (public, no credentials) |

Keep max instances at **1**: job state lives in memory, and more instances also start cold (20–30 s).
Every merge to `main` redeploys – avoid many merges right before or during judging.

## For the frontend

1. `GET /api/sky?target=<key>&fov=..` for challenge targets (keep using `target` when the user changes the FOV), or `?ra=..&dec=..&fov=..`.
2. If `status` is `done`: show `meta` right away.
3. Otherwise poll `GET /api/status/<job>` every ~2 s. Show `preview` as soon as it is not `null`; show `done / total` and `stage` as progress. Retry a failed poll; on 502/503/504 say "server busy, retrying".
4. Image URL = `API + base_url + path from meta.json`. `base_url` can start with `/api/files/` **or** `/api/examples/` – never hard-code it.
5. If `fallback` is `true`, show a banner with `note` (e.g. live data unavailable, showing the precomputed 3′ view). `precomputed: true` means a bundled challenge-target result.
6. Errors: `status: "error"` has a user-friendly `error`; HTTP 400/404/500 have `{"detail": "..."}`. Show them with a "Try again" button.
7. HTTP `429` (too many new searches / reports from one IP) and `503` (server busy) also have a `detail` text – show it.
8. Masked images: add `mask_flags=true` to `/api/sky`; the job id ends in `_mask`.
9. Candidate reports: `POST` / `GET /api/candidates`, see [`CANDIDATES.md`](CANDIDATES.md).
10. Gaia field stars: `GET /api/gaia?ra=&dec=&radius=<arcsec, max 900>` → J2016.0 positions + proper motions, brightest first; `503` = catalogue unreachable, show only the target star.
11. `VITE_API_BASE_URL` defaults to the Cloud Run URL; set it to `http://localhost:8000` only to test a local backend.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate                 # Mac/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt -c backend/constraints.txt
uvicorn backend.main:app --reload --port 8000
```
Open http://localhost:8000/docs. Results go to `output/` (gitignored).
Useful: `WARMUP=0` (don't compute targets on start), `FETCH_MODE=irsa` (test the fallback route).

## Deploy and settings

- Merge to `main` → new revision. Check Cloud Run → `planetx-api` → Revision History: newest revision green with 100 % traffic. A failed build keeps the previous revision running.
- Change settings (CPU, memory, env vars, volumes, scaling) in the service's tabs, then press **Redeploy** (top right).
- Volume check: Containers tab → volume `cache` = bucket `planetx-cache-erik`, mount path `/data`; the compute service account needs `roles/storage.objectUser` on the bucket.

## Updating data and processing

- **Emil changes the processing:** he reruns `rebuild_examples` and merges code + `examples/` together → after the deploy the targets use the new images. Cached free-coordinate results made with older code are rebuilt automatically in the background on their next request.
- **New SPHEREx observations:** found automatically (daily background check), no action needed.
- **New data release (e.g. DR2):** set `SPHEREX_COLLECTIONS=spherex_dr2,spherex_dr1,spherex_qr3` in the Cloud Run variables and redeploy.
- **Clear the cache:** delete the `output/` folder in the bucket; everything is recomputed on request (the 5 targets keep working from `examples/`). Keep `output/_candidates/` (the community reports); `output/_gaia/` can be deleted freely.
- **Delete a spam report:** set `CANDIDATES_ADMIN_TOKEN` in the Cloud Run variables, then `DELETE /api/candidates/<id>` with header `X-Admin-Token: <token>` (or delete the file in `output/_candidates/`).
- **Upgrade libraries:** change `constraints.txt` deliberately, build and test locally, then merge.

## Test checklist

| Test | Expected |
|---|---|
| `/api/health` | `{"ok": true}` |
| `/api/targets` | 5 targets, all `cached: true`, Barnard `dec` ≈ 4.7707 (today's position) |
| `/api/sky?target=barnard` | `done` instantly, `precomputed: true`; `diff_ALL.png` shows the star moving north |
| `/api/sky?ra=269.452083&dec=4.693364` | matched to `barnard` (note), star centred |
| `/api/sky?ra=83.82&dec=-5.39` | `queued` → `preview` → `done` (needs IRSA) |
| `/api/sky?ra=abc&dec=1` / `fov=50` / `target=nope` | 400 / 400 / 404 |
| `/api/status/ra1.2.3_dec+1_fov3` | 404 |
| `/api/sky?target=barnard&mask_flags=true` | job `barnard_mask`, then `done` |
| `/api/gaia?ra=269.4461&dec=4.7707&radius=130` | ~330 stars, first = Barnard (`g` 8.19, `pmdec` ≈ 10362) |
| `/api/gaia?ra=1&dec=1&radius=1000` | 400 |
| `POST /api/candidates` `{"ra":269.45,"dec":4.69}` | 201, `near_challenge_target: "barnard"` |
| `GET /api/candidates` | `{count, candidates}` |

## Logs and debugging

Cloud Run → `planetx-api` → Observability → Logs. Useful filters:
- `TIMING` – `search | download | processing | total` seconds per run
- `S3:` – cutouts from S3 and time · `falling back` – IRSA cutout route used
- `IRSA SIA failed` – IRSA retries · `Refresh check` / `Rebuilding` – background freshness work
- `Traceback` – errors
- `Gaia: all VizieR mirrors failed` – `/api/gaia` could not reach any VizieR mirror

**`DALServiceError: 502 Server Error: Proxy Error … irsa.ipac.caltech.edu`** = NASA's IRSA is down/overloaded, not our bug. Cached results and the 5 targets keep working; new positions return "The SPHEREx data archive (NASA/IPAC IRSA) did not respond".

## Known issues

- Free coordinates: processing ~100 s because the science module queries the ESA Gaia archive live; waiting for Emil's timeout / `skip_gaia` flag.
- SIMBAD is sometimes down → long warnings in logs; built-in coordinates are used, results are fine.
- `RuntimeWarning: All-NaN slice` is harmless (empty cutout edges).

## Costs and shutdown

- Runs on the Google Cloud free trial credit (~257 €); one always-on instance ≈ 50–60 €/month. Budget alert: 5 € of real cost.
- **After judging:** Cloud Run → `planetx-api` → Delete (or minimum instances 0); delete the bucket if no longer needed.
