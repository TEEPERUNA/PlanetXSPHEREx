# Backend Structure

Owner: Erik · Folder: `backend/` · Live API: https://planetx-api-38053485414.us-east4.run.app (docs: `/docs`)
AI-assisted: written with Claude (Anthropic).

## Files

| File | What it does |
|---|---|
| `main.py` | FastAPI app: endpoints, job queue, quick preview, cache, cache refresh, warm-up, error handling |
| `fetch.py` | Fast data access: IRSA SIA search + partial reads from AWS S3 → `Cutout` objects for the science module |
| `requirements.txt` | Backend dependencies (includes `../science/requirements.txt`) |
| `s3_test.py` | Test script: S3 vs. IRSA (same data? which is faster?) |
| `PLAN.md` | What is done and what is next |
| `HANDOFF.md` | How to run, deploy, test and debug the backend |
| `SUBMISSION_backend.md` | Backend texts for the Space Apps project page |

Related files outside `backend/`:
- `../Dockerfile`, `../.dockerignore`: container image for Cloud Run
- `../science/fetch_spherex.py`: Emil's processing (`run()`, `parse_cutout_hdul()`, `select_per_group()`, `TARGETS`)
- `../CONTRACT.md`: API and `meta.json` format shared with the frontend
- `../examples/`: precomputed example results, served at `/api/examples/`

## Request flow

```
Frontend
   │  GET /api/sky?ra=..&dec=..&fov=..   (or ?target=barnard)
   ▼
main.py ── cached? ── yes ──► {"status":"done", base_url, meta, timing, data_release, refreshing}
   │                              └─ older than CACHE_TTL_HOURS → background check for new data
   no
   ▼
start_job() ──► {"status":"queued", job}     Frontend polls GET /api/status/<job>
   │
   ├─ 1. Quick preview  (PREVIEW_PER_GROUP=1 image per epoch+detector) → output/<job>__preview/
   │                     /api/status returns it as "preview"
   └─ 2. Full run       (PER_GROUP=3) → output/<job>/  → status "done"

Each run (class Pipeline in main.py):
   fetch.find_images()   IRSA SIA: which images cover the position (DR1, then QR3) + S3 paths
   fetch.select()        up to N images per (epoch, detector)
   fetch.fetch_cutouts() S3 partial reads, 32 parallel, WCS shifted to the cutout
                         (downloads shared between preview and full run)
   science run(..., cutouts=...)   zodi subtraction, epochs, stacking, PNG/GIF/diff/spectrum, meta.json
   write_cache_info()    output/<job>/cache.json: data fingerprint, release, timing
   If S3 fails → fallback: science run() with IRSA cutout service
```

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{"ok": true}` |
| `GET /api/targets` | The 5 challenge targets and whether they are cached |
| `GET /api/sky?target=` or `?ra=&dec=&fov=` | Cached result, or a new job id |
| `GET /api/status/{job}` | Progress (`stage`, `done`, `total`, `preview`) or the finished result |
| `GET /api/files/{job}/{path}` | Output files (PNG, GIF, CSV, FITS) from the cache |
| `GET /api/examples/{job}/{path}` | Precomputed results from the repo's `examples/` |
| `GET /docs` | Interactive API docs (Swagger) |

Full format: `../CONTRACT.md`.

## Job ids (cache keys)

- Challenge target, default FOV: `barnard`, `epsindib`, `wise0855`, `rwaur`, `rdra`
- Challenge target, other FOV: `barnard_fov4`
- Free coordinates: `ra133.7950_dec-7.2450_fov3`
- Quick preview: `<job>__preview`
- Background refresh status (internal): `<job>__refresh`

## Cache layout (`OUTPUT_DIR`, on Cloud Run = bucket `planetx-cache-erik` mounted at `/data`)

```
output/<job>/
  meta.json        written by science (frontend reads this)
  cache.json       written by backend: {"fingerprint", "collection", "source", "checked_at", "timing"}
  frames/<band>/epoch<i>.png, blink_<band>.gif, diff_<band>.png, epoch<i>_<band>.fits, spectrum.csv, ...
```

Fingerprint = `<collection>:<number of images>:<newest MJD>`. When it changes, the result is rebuilt.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `OUTPUT_DIR` | `<repo>/output` | Cache folder (`/data/output` on Cloud Run) |
| `PER_GROUP` | `3` | Images per epoch+detector in the full run (0 = all) |
| `PREVIEW_PER_GROUP` | `1` | Images per epoch+detector in the quick preview (0 = no preview) |
| `FETCH_MODE` | `s3` | `s3` (fast) or `irsa` (IRSA cutout service only) |
| `SPHEREX_COLLECTIONS` | `spherex_dr1,spherex_qr3` | Releases to search, newest first |
| `S3_WORKERS` | `32` | Parallel S3 reads |
| `DOWNLOAD_WORKERS` | `6` | Parallel downloads on the IRSA fallback route |
| `CACHE_TTL_HOURS` | `24` | How often a cached result is checked for new SPHEREx data |
| `MAX_FOV_ARCMIN` | `10` | Largest allowed field of view |
| `WARMUP` | `1` | Fetch the 5 challenge targets on startup |
| `JOB_WORKERS` | `2` | Jobs running at the same time |
