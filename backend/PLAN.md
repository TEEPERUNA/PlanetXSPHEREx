# Backend Plan – Erik

Owner: Erik · Folder: `backend/` · Branch: `backend`
API contract: [`../CONTRACT.md`](../CONTRACT.md)

## Done ✅

- **Project setup**: repo structure (`backend/`, `science/`, `frontend/`, `examples/`), `README.md`, `CONTRACT.md`, `.gitignore`, `Dockerfile`, `.dockerignore`
- **Example data**: Barnard's Star precomputed in `examples/barnard/` for frontend development (real SPHEREx QR3 data, 5 epochs Aug 2025 – Aug 2026; difference image shows the star's known northward proper motion)
- **FastAPI backend** (`backend/main.py`)
  - `GET /api/targets`: the 5 challenge targets
  - `GET /api/sky?target=` or `?ra=&dec=&fov=`: returns cached result instantly or starts a background job
  - `GET /api/status/{job}`: job progress (`done` / `total` / `stage`)
  - `GET /api/files/...` and `GET /api/examples/...`: static outputs (PNG frames, GIFs, diff images, spectrum CSV)
  - Disk cache keyed by target / `ra_dec_fov`: repeated requests are instant
  - Warm-up: fetches the 5 challenge targets on startup
  - Quick preview: fast 1-image-per-epoch run first, exposed as `preview` in `/api/status`, then the full run
  - Fixed: results from `examples/` are served from the correct URL (`base_url`)
- **Docker**: image builds and runs locally; warm-up fetches all targets

- **Deployed to Google Cloud Run** ✅ https://planetx-api-38053485414.us-east4.run.app
  - Region `us-east4` (close to the SPHEREx S3 bucket in `us-east-1`), instance-based billing, 1 instance, 2 GiB
  - Cache in Cloud Storage bucket `planetx-cache-erik` mounted at `/data`
  - Continuous deploy: every merge to `main` redeploys automatically
  - Budget alert set (5 €); runs on the free trial credit
- **S3 speed test** (`backend/s3_test.py`): S3 data is identical to IRSA (same VERSION, identical pixels);
  48 images in 16 s with 0 errors vs. IRSA cutouts 54 images in 90–136 s with 30–60 % HTTP 503 errors
- **Fast S3 downloads** (`backend/fetch.py`)
  - IRSA SIA search → list of images + S3 paths (newest release first: DR1, then QR3)
  - Partial reads from `s3://nasa-irsa-spherex` (256 kB blocks, 32 parallel), only the needed pixels
  - Builds IRSA-style cutouts with corrected WCS → Emil's `parse_cutout_hdul()` → `run(..., cutouts=...)`
  - Preview and full run share downloads (nothing is fetched twice)
  - Automatic fallback to the IRSA cutout service if S3 fails (`FETCH_MODE=irsa` forces it)
- **Cache refresh for new SPHEREx data**
  - Each result stores a data fingerprint (release + number of images + newest date) in `cache.json`
  - Cached results are returned instantly; if older than `CACHE_TTL_HOURS` (default 24 h) the backend
    checks IRSA in the background and rebuilds only if new data exists
  - `/api/sky` responses include `"refreshing": true/false`

## Next 📋

1. Merge to `main` → Cloud Run redeploys → measure S3 speed from `us-east4`
2. Measure where time goes (SIA query vs. downloads vs. processing)
3. Progressive results: return each epoch's frames as soon as they are ready
4. Free-coordinate checks: clearer errors, FOV limits
5. After judging: delete the Cloud Run service or set min instances to 0 (credit is limited)

## Notes for the team

- Always use the `base_url` returned by the API; files can come from `/api/files/` or `/api/examples/`
- Show `preview` from `/api/status` immediately, then swap to the full result when `status` is `done`
- API URL: https://planetx-api-38053485414.us-east4.run.app (docs at `/docs`)
- `/api/sky` may return `"refreshing": true` → a newer result may appear later; frontend can ignore it
- Suggestion for Emil (his decision): FLAGS masking is off by default, consider which flag bits to mask

## AI use

Backend code written with the help of Claude (Anthropic); noted in file headers.
