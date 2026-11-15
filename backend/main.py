"""
SPHEREx Sky API (FastAPI)
Project architecture: TypeScript Frontend + FastAPI Backend + Science Engine
Follows CONTRACT.md specifications.
AI-assisted: written with Claude (Anthropic).

Run locally (from repo root):
    pip install -r backend/requirements.txt
    uvicorn backend.main:app --reload --port 8000

Endpoints: see CONTRACT.md
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import math
import re
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "science"))
import fetch_spherex as fs  # noqa: E402
sys.path.insert(0, str(ROOT / "backend"))
import fetch  # noqa: E402  fast S3 data access (backend/fetch.py)
import time  # noqa: E402

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PER_GROUP = int(os.environ.get("PER_GROUP", "3"))      # images per epoch+detector (speed vs quality)
PREVIEW_PER_GROUP = int(os.environ.get("PREVIEW_PER_GROUP", "1"))  # quick first result (0 = off)
DOWNLOAD_WORKERS = int(os.environ.get("DOWNLOAD_WORKERS", "6"))
MAX_FOV_ARCMIN = float(os.environ.get("MAX_FOV_ARCMIN", "10"))
WARMUP = os.environ.get("WARMUP", "1") == "1"
FETCH_MODE = os.environ.get("FETCH_MODE", "s3")             # "s3" (fast) or "irsa" (cutout service)
CACHE_TTL_HOURS = float(os.environ.get("CACHE_TTL_HOURS", "24"))  # how often to check for new data

app = FastAPI(title="SPHEREx Sky API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/api/files", StaticFiles(directory=OUTPUT_DIR), name="files")
if (ROOT / "examples").is_dir():
    app.mount("/api/examples", StaticFiles(directory=ROOT / "examples"), name="examples")

executor = ThreadPoolExecutor(max_workers=int(os.environ.get("JOB_WORKERS", "2")))
jobs: dict[str, dict] = {}
lock = threading.Lock()


def make_args(fov: float, per_group: int = PER_GROUP) -> SimpleNamespace:
    return SimpleNamespace(size=fov, bands=list(fs.DETECTORS), max=0, per_group=per_group,
                           workers=DOWNLOAD_WORKERS, mask_flags=False, lo=1.0, hi=99.7, frame_ms=600,
                           out=str(OUTPUT_DIR))


def slug_for(ra: float, dec: float, fov: float) -> str:
    return f"ra{ra:.4f}_dec{dec:+.4f}_fov{fov:g}"


EXAMPLES_DIR = ROOT / "examples"


def clean_json(o):
    """NaN/Infinity are not valid JSON -> FastAPI would crash with HTTP 500. Replace them with null."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    return o


def find_cached(slug: str):
    """Returns (meta, base_url) for a finished result, or None.
    Looks in OUTPUT_DIR first, then the precomputed examples/ folder in the repo."""
    for folder, prefix in ((OUTPUT_DIR, "/api/files"), (EXAMPLES_DIR, "/api/examples")):
        p = folder / slug / "meta.json"
        if p.exists():
            try:
                return clean_json(json.loads(p.read_text())), f"{prefix}/{slug}/"
            except Exception:  # noqa: BLE001  half-written file
                return None
    return None


def cached_meta(slug: str):
    hit = find_cached(slug)
    return hit[0] if hit else None


def done_response(slug: str) -> dict:
    meta, base = find_cached(slug)
    info = read_cache_info(slug) or {}
    return {"status": "done", "job": slug, "base_url": base, "meta": meta,
            "data_release": info.get("collection"), "timing": info.get("timing")}


def friendly_error(e: Exception) -> str:
    """Turn internal exceptions into short messages a user understands."""
    name, text = type(e).__name__, str(e).lower()
    if isinstance(e, LookupError):
        return "No SPHEREx images cover this position yet. Try another position or a target."
    if isinstance(e, MemoryError):
        return "The server ran out of memory for this request. Try a smaller field of view."
    if (isinstance(e, (TimeoutError, ConnectionError, OSError)) or "timeout" in text
            or "timed out" in text or "503" in text or "502" in text
            or name in ("DALServiceError", "DALQueryError", "ReadTimeout", "ConnectTimeout",
                        "HTTPError", "URLError", "ClientError")):
        return ("The SPHEREx data archive (NASA/IPAC IRSA) did not respond. "
                "Please try again in a minute.")
    return "Processing failed for this position. Please try again or choose another position."


def job_from_slug(job: str):
    """Rebuild a job from its id, e.g. after a server restart lost the in-memory job list.
    'barnard', 'barnard_fov4', 'ra133.7950_dec-7.2450_fov3' (and '__preview' suffix)."""
    base = job.removesuffix("__preview")
    m = re.fullmatch(r"ra([0-9.]+)_dec([+-][0-9.]+)_fov([0-9.]+)", base)
    if m:
        ra, dec, fov = float(m[1]), float(m[2]), float(m[3])
        if fov > MAX_FOV_ARCMIN:
            return None
        c = fs.parse_coord(str(ra), str(dec))
        return coord_job(c, fov)
    m = re.fullmatch(r"([a-z0-9]+?)(?:_fov([0-9.]+))?", base)
    if m and m[1] in fs.TARGETS:
        return target_job(m[1], float(m[2]) if m[2] else 3.0)
    return None


def start_job(slug: str, work, preview: bool = True) -> dict:
    """work(progress, out_slug, per_group) does one pipeline run.
    With preview: a quick 1-image-per-group run first (slug__preview), then the full run."""
    with lock:
        j = jobs.get(slug)
        if j and j["status"] in ("queued", "processing"):
            return {"status": j["status"], "job": slug}
        jobs[slug] = {"status": "queued", "done": 0, "total": 0, "stage": "queued",
                      "error": None, "preview": None}

    def progress_for(stage_prefix):
        def progress(done, total, stage):
            jobs[slug].update(status="processing", done=done, total=total,
                              stage=f"{stage_prefix}{stage}")
        return progress

    def runner():
        try:
            jobs[slug]["status"] = "processing"
            if preview and PREVIEW_PER_GROUP and PREVIEW_PER_GROUP < PER_GROUP:
                pslug = f"{slug}__preview"
                try:
                    work(progress_for("preview_"), pslug, PREVIEW_PER_GROUP)
                    hit = find_cached(pslug)
                    if hit:
                        jobs[slug]["preview"] = {"base_url": hit[1], "meta": hit[0]}
                except LookupError:
                    raise
                except Exception:  # noqa: BLE001  preview failure is not fatal
                    traceback.print_exc()
            work(progress_for(""), slug, PER_GROUP)
            jobs[slug].update(status="done", stage="done")
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, LookupError):
                traceback.print_exc()
            jobs[slug].update(status="error", error=friendly_error(e),
                              error_detail=f"{type(e).__name__}: {e}")

    executor.submit(runner)
    return {"status": "queued", "job": slug}


class Pipeline:
    """One pipeline for one position + FOV. Keeps the image list and downloaded cutouts
    between the quick preview run and the full run, so nothing is fetched twice."""

    def __init__(self, resolve, fov: float):
        self.resolve = resolve          # () -> (coord, label, info)
        self.fov = fov
        self._target = None
        self._images = None
        self.memo: dict = {}

    def target(self):
        if self._target is None:
            self._target = self.resolve()
        return self._target

    def images(self):
        if self._images is None:
            c, _, _ = self.target()
            self._images = fetch.find_images(c)
        return self._images

    def __call__(self, progress, out_slug: str, per_group: int):
        t0 = time.time()
        c, label, info = self.target()
        args = make_args(self.fov, per_group)
        fingerprint = None
        if FETCH_MODE == "s3":
            try:
                imgs = self.images()                      # LookupError = no coverage
                t1 = time.time()
                fingerprint = imgs.fingerprint
                rows = fetch.select(imgs, per_group)
                cutouts = fetch.fetch_cutouts(rows, c, self.fov, info, progress, self.memo)
                t2 = time.time()
                if cutouts:
                    fs.run(c, label, out_slug, args, info, progress=progress, cutouts=cutouts)
                    t3 = time.time()
                    timing = {"search_s": round(t1 - t0, 1), "download_s": round(t2 - t1, 1),
                              "processing_s": round(t3 - t2, 1), "total_s": round(t3 - t0, 1),
                              "images": len(cutouts)}
                    print(f"  TIMING {out_slug}: search {timing['search_s']} s | "
                          f"download {timing['download_s']} s ({len(cutouts)} images) | "
                          f"processing {timing['processing_s']} s | total {timing['total_s']} s")
                    write_cache_info(out_slug, fingerprint, imgs.collection, "s3", timing)
                    return
                print("  S3 returned no cutouts -> falling back to IRSA cutout service")
            except LookupError:
                raise
            except Exception:  # noqa: BLE001  any S3/SIA problem -> IRSA fallback
                traceback.print_exc()
                print("  S3 route failed -> falling back to IRSA cutout service")
        fs.run(c, label, out_slug, args, info, progress=progress)
        print(f"  TIMING {out_slug}: IRSA route total {round(time.time() - t0, 1)} s")
        write_cache_info(out_slug, fingerprint, None, "irsa",
                         {"total_s": round(time.time() - t0, 1)})


def cache_info_path(slug: str) -> Path:
    return OUTPUT_DIR / slug / "cache.json"


def write_cache_info(slug: str, fingerprint, collection, source: str, timing: dict | None = None):
    p = cache_info_path(slug)
    if p.parent.exists():
        old = read_cache_info(slug) or {}
        p.write_text(json.dumps({"fingerprint": fingerprint, "collection": collection,
                                 "source": source, "checked_at": time.time(),
                                 "timing": timing or old.get("timing")}))


def read_cache_info(slug: str):
    try:
        return json.loads(cache_info_path(slug).read_text())
    except Exception:  # noqa: BLE001
        return None


def maybe_refresh(slug: str, make_pipeline) -> bool:
    """Stale-while-revalidate: the cached result is returned right away; if it is older than
    CACHE_TTL_HOURS we check IRSA for new SPHEREx data in the background and rebuild if needed.
    Returns True if a refresh is running."""
    rkey = f"{slug}__refresh"
    if jobs.get(rkey, {}).get("status") == "processing":
        return True
    if jobs.get(slug, {}).get("status") in ("queued", "processing"):
        return False
    info = read_cache_info(slug)
    if info and time.time() - info.get("checked_at", 0) < CACHE_TTL_HOURS * 3600:
        return False
    jobs[rkey] = {"status": "processing"}

    def runner():
        try:
            pipe = make_pipeline()
            new_fp = pipe.images().fingerprint
            if info and info.get("fingerprint") == new_fp:
                write_cache_info(slug, new_fp, info.get("collection"), info.get("source", "s3"))
            else:
                print(f"  New SPHEREx data for {slug} ({new_fp}) -> rebuilding")
                pipe(lambda *a: None, slug, PER_GROUP)
            jobs[rkey] = {"status": "done"}
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            jobs[rkey] = {"status": "error", "error": str(e)}

    executor.submit(runner)
    return True


def matching_target(c) -> str | None:
    """Challenge target whose position is within 2 arcmin of c (J2000 catalogue position or the
    proper-motion-corrected centre of its cached result), else None."""
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    for key, t in fs.TARGETS.items():
        points = [t["fallback"][:2]]
        hit = find_cached(key)
        if hit and hit[0].get("ra_deg") is not None:
            points.append((hit[0]["ra_deg"], hit[0]["dec_deg"]))
        for ra, dec in points:
            if c.separation(SkyCoord(ra * u.deg, dec * u.deg)).arcmin < 2.0:
                return key
    return None


def fallback_response(slug: str, key: str, reason: str) -> dict:
    """Precomputed challenge-target result used when live data is not available."""
    resp = done_response(key)
    resp["requested_job"] = slug
    resp["note"] = reason
    return resp


def target_job(key: str, fov: float):
    slug = key if fov == 3.0 else f"{key}_fov{fov:g}"

    def make_pipeline():
        return Pipeline(lambda: fs.target_coord(key), fov)
    return slug, make_pipeline


def coord_job(c, fov: float):
    slug = slug_for(c.ra.deg, c.dec.deg, fov)

    def make_pipeline():
        return Pipeline(lambda: (c, f"RA {c.ra.deg:.4f} Dec {c.dec.deg:+.4f}", {}), fov)
    return slug, make_pipeline


# --------------------------------------------------------------------------- endpoints

@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Return the real error as JSON *with* CORS headers, so the browser shows the message
    instead of a bare 'Failed to fetch'."""
    traceback.print_exception(exc)
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"},
                        headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/targets")
def targets():
    return [{"key": k, "label": v["label"], "ra": v["fallback"][0], "dec": v["fallback"][1],
             "cached": cached_meta(k) is not None} for k, v in fs.TARGETS.items()]


@app.get("/api/sky")
def sky(ra: str | None = None, dec: str | None = None,
        target: str | None = Query(None, description="one of /api/targets keys"),
        fov: float = Query(3.0, gt=0, description="field of view, arcmin")):
    if fov > MAX_FOV_ARCMIN:
        raise HTTPException(400, f"fov must be <= {MAX_FOV_ARCMIN} arcmin")

    if target:
        if target not in fs.TARGETS:
            raise HTTPException(404, f"unknown target '{target}'")
        slug, make_pipeline = target_job(target, fov)
    elif ra is not None and dec is not None:
        try:
            c = fs.parse_coord(ra, dec)
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "could not parse ra/dec")
        slug, make_pipeline = coord_job(c, fov)
        # Coordinates of a challenge target at the default FOV -> use its precomputed result.
        key = matching_target(c)
        if key and fov == 3.0 and not find_cached(slug) and find_cached(key):
            return fallback_response(slug, key, f"Matched challenge target '{key}'.")
    else:
        raise HTTPException(400, "give either target or ra+dec")

    if find_cached(slug):
        resp = done_response(slug)
        resp["refreshing"] = maybe_refresh(slug, make_pipeline)
        return resp
    j = jobs.get(slug)
    if j and j["status"] == "error":
        jobs.pop(slug)  # allow retry
    resp = start_job(slug, make_pipeline())
    # Remember a precomputed result to fall back on if live data (IRSA) fails.
    fb = target if target else (matching_target(c) if ra is not None else None)
    if fb and find_cached(fb) and slug in jobs:
        jobs[slug]["fallback"] = fb
    return resp


@app.get("/api/status/{job}")
def status(job: str):
    if find_cached(job):
        return done_response(job)
    j = jobs.get(job)
    if not j:
        # The server may have restarted (deploy, crash) and lost its in-memory job list.
        # Job ids encode the request, so start it again instead of failing.
        rebuilt = job_from_slug(job)
        if rebuilt is None:
            raise HTTPException(404, "Unknown job id. Start a new search with /api/sky.")
        slug, make_pipeline = rebuilt
        if find_cached(slug):
            return done_response(slug)
        resp = start_job(slug, make_pipeline())
        resp["note"] = "The server restarted, so this search was started again."
        return resp
    fb = j.get("fallback")
    if j.get("status") == "error" and fb and find_cached(fb):
        return fallback_response(job, fb, "Live SPHEREx data is not available right now "
                                 f"({j.get('error')}). Showing the precomputed result for this "
                                 "target with the default 3 arcmin field of view.")
    return clean_json({"job": job, **j})


@app.on_event("startup")
def warmup():
    if not WARMUP:
        return
    for key in fs.TARGETS:
        if cached_meta(key) is None:
            slug, make_pipeline = target_job(key, 3.0)
            start_job(slug, make_pipeline(), preview=False)
