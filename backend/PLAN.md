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

## In progress 🔄

- **Deploy to Google Cloud Run** (Space Apps Global Offer, $300 free credit)
  - Region: `us-east4` (close to the SPHEREx S3 bucket in `us-east-1`)
  - Instance-based billing (CPU always allocated, needed for background jobs)
  - Min instances 1, max instances 1 (job state is in memory)
  - Memory 2 GiB, CPU 1
  - Env: `WARMUP=1`, `PER_GROUP=3`, `OUTPUT_DIR=/data/output`
  - Cloud Storage bucket mounted at `/data` for a persistent cache
  - Continuous deploy from `main`
- Share the public API URL with Eliz and Juho (`API_BASE_URL`)

## Next 📋

1. **Measure where time goes**: log timings for TAP query vs. downloads vs. processing
2. **Faster downloads via AWS S3** (`s3://nasa-irsa-spherex`, public, no credentials)
   - Test first: compare one file from S3 vs. IRSA (same `VERSION`, identical pixels)
   - If it works: read only the needed pixels with `fits.open(..., use_fsspec=True)` + `.section[...]`, 30+ parallel reads, no IRSA 503 errors
   - Agree with Emil: move TAP query + downloads to `backend/fetch.py`; `science/` keeps the image processing
3. **Progressive results**: return each epoch's frames as soon as they are ready, instead of waiting for the whole run
4. **Cache TAP query results** per position
5. **Free-coordinate checks**: clear error if no SPHEREx coverage; limit FOV
6. Decide whether `examples/` should be included in the Docker image (now excluded in `.dockerignore`)

## Notes for the team

- Always use the `base_url` returned by the API; files can come from `/api/files/` or `/api/examples/`
- Show `preview` from `/api/status` immediately, then swap to the full result when `status` is `done`
- Suggestions for Emil (his decision, in `science/`):
  - Retries with backoff for IRSA 503 errors (~5–20% of cutouts fail now) and fewer parallel downloads (10 → 6)
  - Silence astropy SIP INFO logs: `from astropy import log; log.setLevel("WARNING")`
  - Restore the AI-use note at the top of `fetch_spherex.py` (required by Space Apps rules)
  - Light curve: compute per detector band (epochs have different bands)
  - `slug == "epsindib"` / `"wise0855"` checks don't match API slugs with other FOVs

## AI use

Backend code written with the help of Claude (Anthropic); noted in file headers.
