# Backend Structure

Owner: Erik · Folder: `backend/` · Live API: https://planetx-api-38053485414.us-east4.run.app (docs: `/docs`)
AI-assisted: written with Claude (Anthropic).

## Files

| File | What it does |
|---|---|
| `main.py` | FastAPI app: endpoints, job queue, quick preview, cache, fallbacks, background freshness checks, warm-up, error handling, rate limits, candidate reports, Gaia field stars |
| `fetch.py` | Fast data access: IRSA SIA search (with retries) + partial reads from AWS S3 → `Cutout` objects for the science module |
| `requirements.txt` | Backend + science runtime libraries (names only; add any new science library here too) |
| `constraints.txt` | Exact pinned versions used in the Docker image (the only place with versions) |
| `CANDIDATES.md` | Candidate reports API for the frontend |
| `s3_test.py` | Test script: S3 vs. IRSA (same data? which is faster?) |
| `PLAN.md` | What is done and what is next |
| `HANDOFF.md` | How to run, deploy, test and debug the backend |
| `SUBMISSION_backend.md` | Backend texts for the Space Apps project page |

Related files outside `backend/`:
- `../Dockerfile`, `../.dockerignore`: container image (copies `science/`, `backend/`, `examples/`)
- `../science/fetch_spherex.py`: Emil's processing (`run()`, `parse_cutout_hdul()`, `select_per_group()`, `TARGETS`)
- `../science/rebuild_examples.py`: Emil's script that regenerates `examples/`
- `../examples/`: precomputed challenge-target results, served at `/api/examples/`
- `../CONTRACT.md`: API and `meta.json` format shared with the frontend
- `../.github/workflows/docker-build.yml`: builds the Docker image on every push (catches dependency problems before deploy)

## Request flow

```
Frontend
   │  GET /api/sky?target=barnard&fov=3      or   ?ra=..&dec=..&fov=..
   ▼
main.py
   ├─ coordinates within 2′ of a challenge target? → treat as that target (today's position)
   ├─ result cached (OUTPUT_DIR, then examples/)?
   │     yes → {"status":"done", base_url, meta, precomputed, fallback:false, ...}
   │           + light background freshness check (max once per CACHE_TTL_HOURS)
   ├─ background rebuild already running? → {"status":"processing"} (no second run)
   └─ otherwise start_job() → {"status":"queued", job}
                                   Frontend polls GET /api/status/<job> every ~2 s
start_job():
   1. quick preview  (PREVIEW_PER_GROUP=1)  → output/<job>__preview/   ("preview" in status)
   2. full run       (PER_GROUP=3)          → output/<job>/            (status "done")
   on error: challenge target → precomputed 3′ result with fallback:true + note
             anything else    → status "error" with a friendly message

Pipeline (class in main.py), one run:
   fetch.find_images()    IRSA SIA (DR1, then QR3), 4 attempts → image list + S3 paths + fingerprint
   fetch.select()         up to N images per (epoch, detector)
   fetch.fetch_cutouts()  S3 partial reads, 32 parallel; shared between preview and full run
   science run(..., cutouts=...)   zodi subtraction, epochs, stacking, PNG/GIF/diff/spectrum, meta.json
   write_cache_info()     output/<job>/cache.json
   S3 problem → same run via the IRSA cutout service (FETCH_MODE=irsa forces this)
```

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{"ok": true}` |
| `GET /api/targets` | The 5 challenge targets with **today's** position (proper motion applied) and `cached` |
| `GET /api/sky?target=` or `?ra=&dec=&fov=` | Finished result, or a new job id |
| `GET /api/status/{job}` | Progress (`stage`, `done`, `total`, `preview`), error, or the finished result |
| `GET /api/files/{job}/{path}` | Files from the cache (bucket) |
| `GET /api/examples/{job}/{path}` | Files from the bundled precomputed results |
| `GET /api/gaia?ra=&dec=&radius=` | Gaia DR3 stars around a position (J2016.0, brightest first, max 500), cached forever |
| `POST /api/candidates` | Store a community candidate report |
| `GET /api/candidates[?ra=&dec=&radius_arcmin=]` | Reports, newest first, optionally only one field |
| `GET /api/candidates/{id}` · `DELETE …` | One report · delete (admin token) |
| `GET /docs` | Interactive API docs (Swagger) |

`/api/sky` also takes `mask_flags=true` (flagged pixels left out of the stacks).

Extra fields in a finished result (besides `meta`, `base_url`): `precomputed` (bundled example), `fallback` (not exactly what was asked), `note`, `refreshing`, `data_release`, `timing`, `science_version`. Full format: `../CONTRACT.md`.

## Job ids (= cache keys)

- Challenge target, default FOV: `barnard`, `epsindib`, `wise0855`, `rwaur`, `rdra`
- Challenge target, other FOV: `barnard_fov5`
- Free coordinates: `ra133.7950_dec-7.2450_fov3`
- Masked images: `+ _mask`, e.g. `barnard_mask`, `ra133.7950_dec-7.2450_fov3_mask`
- Quick preview: `<job>__preview` · background check (internal): `<job>__refresh`

## Where results come from (priority order)

1. `OUTPUT_DIR/<job>/` – cache in the bucket (live results, or a newer rebuild of a challenge target)
2. `examples/<job>/` – bundled in the Docker image, always available

```
output/<job>/
  meta.json      written by science (read by the frontend)
  cache.json     written by backend: fingerprint, collection, source, checked_at, code_version, timing
  frames/…, blink_*.gif, diff_*.png, *.fits, spectrum.csv, lightcurve.*
output/_checks/<target>.json   last freshness check for a bundled example
output/_candidates/<id>.json   one community candidate report each
output/_gaia/<key>.json        cached Gaia field-star answers
output/<job>__new/             temporary folder of a background rebuild (swapped in when done)
```

## Freshness rules (background, never delays the response)

| Result | Rebuilt when |
|---|---|
| Cached free coordinates | IRSA fingerprint changed (new images), or science code changed |
| Bundled challenge target | IRSA has images more than `NEW_EPOCH_DAYS` (30) newer than its last epoch → rebuilt into the cache, which then takes priority |
| Any | Checked at most once per `CACHE_TTL_HOURS` (24); if IRSA is down the old result simply stays |

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `OUTPUT_DIR` | `/data/output` in Docker | Cache folder (bucket mount) |
| `PER_GROUP` | `3` | Images per epoch+detector in the full run (0 = all) |
| `PREVIEW_PER_GROUP` | `1` | Images per epoch+detector in the preview (0 = no preview) |
| `FETCH_MODE` | `s3` | `s3` or `irsa` |
| `SPHEREX_COLLECTIONS` | `spherex_dr1,spherex_qr3` | Releases to search, newest first |
| `S3_WORKERS` | `32` | Parallel S3 reads |
| `SIA_ATTEMPTS` | `4` | Tries for the IRSA search |
| `DOWNLOAD_WORKERS` | `6` | Parallel downloads on the IRSA fallback route |
| `CACHE_TTL_HOURS` | `24` | How often results are checked for new data |
| `NEW_EPOCH_DAYS` | `30` | How much newer IRSA data must be to rebuild a bundled example |
| `MAX_FOV_ARCMIN` | `20` | Largest allowed field of view |
| `WARMUP` | `1` | Compute missing challenge targets on startup |
| `JOB_WORKERS` | `2` | Jobs running at the same time |
| `RATE_JOBS` / `RATE_WINDOW_S` | `20` / `600` | New searches per IP per window |
| `MAX_ACTIVE_JOBS` | `20` | Queued + running jobs before `503` busy |
| `CANDIDATE_RATE` | `10` | Candidate reports per IP per window |
| `CANDIDATES_ADMIN_TOKEN` | – | Enables `DELETE /api/candidates/{id}` |
| `GAIA_MIRRORS` | Harvard, CDS, IUCAA, NAOJ | VizieR mirrors for `/api/gaia`, tried in order |
| `GAIA_TIMEOUT_S` | `10` | Timeout per mirror |
