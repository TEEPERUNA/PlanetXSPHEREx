# Backend Plan – Erik

Owner: Erik · Folder: `backend/` · Branch: `backend`
Live API: https://planetx-api-38053485414.us-east4.run.app (docs: `/docs`)
See also: [`STRUCTURE.md`](STRUCTURE.md) · [`HANDOFF.md`](HANDOFF.md) · [`../CONTRACT.md`](../CONTRACT.md)

## Done ✅

### Core API
- FastAPI backend (`main.py`): `/api/targets`, `/api/sky`, `/api/status/{job}`, `/api/files/...`, `/api/examples/...`, `/api/health`
- Background jobs with progress (`stage`, `done`, `total`) and a **quick preview** (1 image per epoch+detector) before the full result
- Open CORS, so any website can use the API; coordinates and FOV work from the URL

### Data access
- **Fast S3 downloads** (`fetch.py`): IRSA SIA search → partial reads from the official SPHEREx copy on AWS S3 (`s3://nasa-irsa-spherex`), only the needed pixels, 32 in parallel, WCS shifted to the cutout
- Verified with `s3_test.py`: S3 data is identical to IRSA's (same VERSION, identical pixels); 48 images in 16 s with 0 errors vs. IRSA cutouts 54 images in 90–136 s with 30–60 % HTTP 503 errors
- Uses the newest release first (DR1, then QR3)
- **Retries**: IRSA SIA query retried 4× (2, 4, 8 s); automatic fallback to the IRSA cutout service if S3 fails
- Downloads shared between preview and full run (nothing fetched twice)
- Measured on Cloud Run: challenge targets 11–24 s total (download 7–16 s, processing 1–7 s); `TIMING` lines in the logs

### Reliability
- **Challenge targets bundled in the Docker image** (`examples/`, built by Emil's `rebuild_examples`): the 5 targets always open instantly, even when IRSA is down or after a restart
- **Fallbacks**: target coordinates (J2000 or today's position, any FOV) are searched as the target, so the moving star stays centred; if live data fails for a target, the precomputed 3′ result is returned with `fallback: true` and a `note`
- **Persistent cache**: Cloud Storage bucket `planetx-cache-erik` mounted at `/data` (fixed 15.11: the mount was missing, so the cache was lost on every deploy)
- **Jobs survive restarts**: `/api/status/<job>` rebuilds the job from its id if the server restarted
- **No double work**: a result being rebuilt in the background is not started a second time; half-written `meta.json` is retried
- **Clear errors**: user-friendly messages in `error` (no coverage / IRSA not responding / out of memory), technical details in `error_detail` and the logs; HTTP 500 responses include CORS headers and a generic message
- NaN/Infinity in results are converted to `null` (valid JSON)
- **Pinned dependency versions** (`constraints.txt`) so a new upstream release cannot break a deploy during judging

### Keeping data fresh
- Cached results are returned instantly; a light background check runs at most once a day (`CACHE_TTL_HOURS`)
- Free coordinates: rebuilt when IRSA has new images (fingerprint = release + number of images + newest date)
- Challenge targets: rebuilt into the cache only when IRSA has images > 30 days newer than the example's last epoch (a new survey pass)
- Results made with older science code are rebuilt automatically when Emil's code changes (`science_version` hash)
- New releases (e.g. DR2): add to `SPHEREX_COLLECTIONS`, no code change

### Deployment
- Google Cloud Run, `us-east4` (next to the S3 bucket in `us-east-1`), instance-based billing, min 1 / max 1 instance, 1 CPU, 2 GiB, second-generation runtime
- Continuous deploy from `main`; budget alert set; running on the free trial credit

### Docs and submission
- `STRUCTURE.md`, `HANDOFF.md`, `SUBMISSION_backend.md` (texts for the Space Apps project page)

## Next / if time allows 📋

1. Free coordinates: processing takes ~100 s because of the live Gaia query in the science module → waiting for Emil's timeout / `skip_gaia` flag, then skip Gaia in the quick preview (one line in `Pipeline.__call__`)
2. Progressive results: show each epoch as soon as it is ready
3. Backend tests (`job_from_slug`, `clean_json`, `friendly_error`, `/api/sky` routing) and a GitHub Actions check
4. Limit the in-memory job list (TTL) and add a simple rate limit
5. Replace `@app.on_event("startup")` with a lifespan handler

## After judging ⚠️

Delete the Cloud Run service `planetx-api` (or set minimum instances to 0) and the bucket if no longer needed – the credit is limited.

## AI use

Backend code and docs written with the help of Claude (Anthropic); noted in file headers.
