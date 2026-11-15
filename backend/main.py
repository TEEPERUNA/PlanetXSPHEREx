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
import math
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "science"))
import fetch_spherex as fs  # noqa: E402
sys.path.insert(0, str(ROOT / "backend"))
import fetch  # noqa: E402  fast S3 data access (backend/fetch.py)

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PER_GROUP = int(os.environ.get("PER_GROUP", "3"))      # images per epoch+detector (speed vs quality)
PREVIEW_PER_GROUP = int(os.environ.get("PREVIEW_PER_GROUP", "1"))  # quick first result (0 = off)
DOWNLOAD_WORKERS = int(os.environ.get("DOWNLOAD_WORKERS", "6"))
MAX_FOV_ARCMIN = float(os.environ.get("MAX_FOV_ARCMIN", "20"))
WARMUP = os.environ.get("WARMUP", "1") == "1"
FETCH_MODE = os.environ.get("FETCH_MODE", "s3")             # "s3" (fast) or "irsa" (cutout service)
CACHE_TTL_HOURS = float(os.environ.get("CACHE_TTL_HOURS", "24"))  # how often to check for new data
RATE_JOBS = int(os.environ.get("RATE_JOBS", "20"))        # new (uncached) searches per IP ...
RATE_WINDOW_S = int(os.environ.get("RATE_WINDOW_S", "600"))  # ... per this many seconds
MAX_ACTIVE_JOBS = int(os.environ.get("MAX_ACTIVE_JOBS", "20"))  # queued+processing, then "busy"
JOB_KEEP_S = int(os.environ.get("JOB_KEEP_S", "3600"))    # finished jobs kept in memory this long


@asynccontextmanager
async def lifespan(_app):
    warmup()
    yield


app = FastAPI(title="SPHEREx Sky API", version="0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/api/files", StaticFiles(directory=OUTPUT_DIR), name="files")
if (ROOT / "examples").is_dir():
    app.mount("/api/examples", StaticFiles(directory=ROOT / "examples"), name="examples")

executor = ThreadPoolExecutor(max_workers=int(os.environ.get("JOB_WORKERS", "2")))
jobs: dict[str, dict] = {}
lock = threading.Lock()
_hits: dict[str, list[float]] = {}   # rate limit: ip -> times of new searches


def write_text_atomic(p: Path, text: str):
    """Write to a temp file and rename it into place, so a reader never sees half a file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}_{threading.get_ident()}")
    tmp.write_text(text)
    os.replace(tmp, p)


def publish(tmp_slug: str, slug: str):
    """Move a finished rebuild from OUTPUT_DIR/tmp_slug into OUTPUT_DIR/slug file by file.
    Every file is replaced atomically and meta.json/cache.json go last, so a reader sees either
    the old complete result or the new one, never a half-written mix. (Directory renames are not
    atomic on the Cloud Storage mount, so files are swapped one at a time.)"""
    src, dst = OUTPUT_DIR / tmp_slug, OUTPUT_DIR / slug
    files = [p for p in src.rglob("*") if p.is_file()]
    files.sort(key=lambda p: p.name in ("meta.json", "cache.json"))
    for p in files:
        d = dst / p.relative_to(src)
        d.parent.mkdir(parents=True, exist_ok=True)
        tmp = d.with_name(d.name + ".tmp")
        shutil.copyfile(p, tmp)
        os.replace(tmp, d)
    shutil.rmtree(src, ignore_errors=True)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")   # Cloud Run puts the real client IP here
    return (fwd.split(",")[0] if fwd else (request.client.host if request.client else "?")).strip()


def check_capacity(request: Request):
    """Protect the single instance: limit new searches per IP and the total queue length.
    Cached results and challenge targets are never limited."""
    with lock:
        active = sum(1 for j in jobs.values() if j.get("status") in ("queued", "processing"))
        if active >= MAX_ACTIVE_JOBS:
            raise HTTPException(503, "The server is busy with other searches. Please try again in "
                                     "a minute, or pick one of the challenge targets.")
    rate_limit(request, "search", RATE_JOBS, "Too many new searches from your address. Please wait "
                                             "a few minutes, or pick one of the challenge targets.")


def rate_limit(request: Request, bucket: str, limit: int, message: str):
    """At most `limit` calls per RATE_WINDOW_S for one client IP in one bucket (memory only,
    IPs are never written to disk)."""
    now = time.time()
    key = f"{bucket}:{client_ip(request)}"
    with lock:
        hits = [t for t in _hits.get(key, []) if now - t < RATE_WINDOW_S]
        if len(hits) >= limit:
            raise HTTPException(429, message)
        hits.append(now)
        if len(_hits) > 5000:   # drop clients whose window has passed, keep the active ones
            for k in [k for k, ts in _hits.items() if now - ts[-1] >= RATE_WINDOW_S]:
                del _hits[k]
        _hits[key] = hits


def prune_jobs():
    """Forget finished jobs older than JOB_KEEP_S so the job list cannot grow forever.
    (Results stay on disk; a later request finds them from the cache.) Call with lock held."""
    if len(jobs) < 200:
        return
    now = time.time()
    for k in [k for k, j in jobs.items()
              if j.get("status") in ("done", "error") and now - j.get("t", 0) > JOB_KEEP_S]:
        jobs.pop(k, None)


def make_args(fov: float, per_group: int = PER_GROUP, mask_flags: bool = False) -> SimpleNamespace:
    return SimpleNamespace(size=fov, bands=list(fs.DETECTORS), max=0, per_group=per_group,
                           workers=DOWNLOAD_WORKERS, mask_flags=mask_flags, lo=1.0, hi=99.7, frame_ms=600,
                           out=str(OUTPUT_DIR))


MASK_SUFFIX = "_mask"   # job id suffix for results with flagged (bad) pixels masked out


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
        if not p.exists():
            continue
        for attempt in range(2):
            try:
                return clean_json(json.loads(p.read_text())), f"{prefix}/{slug}/"
            except Exception:  # noqa: BLE001  half-written (being rebuilt) or broken file
                if attempt == 0:
                    time.sleep(0.2)
        # broken file here -> try the next location (examples/)
    return None


def cached_meta(slug: str):
    hit = find_cached(slug)
    return hit[0] if hit else None


def done_response(slug: str) -> dict:
    meta, base = find_cached(slug)
    info = read_cache_info(slug) or {}
    return {"status": "done", "job": slug, "base_url": base, "meta": meta,
            "precomputed": base.startswith("/api/examples/"),   # bundled challenge-target result
            "fallback": False,                                   # True = not what was asked for
            "note": None,
            "data_release": info.get("collection"), "timing": info.get("timing"),
            "science_version": info.get("code_version")}


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
    'barnard', 'barnard_fov4', 'ra133.7950_dec-7.2450_fov3' (+ '_mask', + '__preview')."""
    num = r"\d+(?:\.\d+)?"
    base = job.removesuffix("__preview")
    mask = base.endswith(MASK_SUFFIX)
    base = base.removesuffix(MASK_SUFFIX)
    m = re.fullmatch(rf"ra({num})_dec([+-]{num})_fov({num})", base)
    if m:
        ra, dec, fov = float(m[1]), float(m[2]), float(m[3])
        if not (0 <= ra < 360 and -90 <= dec <= 90 and 0 < fov <= MAX_FOV_ARCMIN):
            return None
        c = fs.parse_coord(str(ra), str(dec))
        return coord_job(c, fov, mask)
    m = re.fullmatch(rf"([a-z0-9]+?)(?:_fov({num}))?", base)
    if m and m[1] in fs.TARGETS:
        fov = float(m[2]) if m[2] else 3.0
        if not 0 < fov <= MAX_FOV_ARCMIN:
            return None
        return target_job(m[1], fov, mask)
    return None


def start_job(slug: str, work, preview: bool = True, fallback: str | None = None) -> dict:
    """work(progress, out_slug, per_group) does one pipeline run.
    With preview: a quick 1-image-per-group run first (slug__preview), then the full run.
    fallback: precomputed result to show if this run fails (set before the worker starts)."""
    with lock:
        j = jobs.get(slug)
        if j and j["status"] in ("queued", "processing"):
            return {"status": j["status"], "job": slug}
        prune_jobs()
        jobs[slug] = {"status": "queued", "done": 0, "total": 0, "stage": "queued",
                      "error": None, "preview": None, "fallback": fallback, "t": time.time()}

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
            jobs[slug].update(status="done", stage="done", t=time.time())
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, LookupError):
                traceback.print_exc()
            jobs[slug].update(status="error", error=friendly_error(e),
                              error_detail=f"{type(e).__name__}: {e}", t=time.time())

    executor.submit(runner)
    return {"status": "queued", "job": slug}


class Pipeline:
    """One pipeline for one position + FOV. Keeps the image list and downloaded cutouts
    between the quick preview run and the full run, so nothing is fetched twice."""

    def __init__(self, resolve, fov: float, mask_flags: bool = False):
        self.resolve = resolve          # () -> (coord, label, info)
        self.fov = fov
        self.mask_flags = mask_flags    # True = flagged (bad) pixels left out of the stacks
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
        args = make_args(self.fov, per_group, self.mask_flags)
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


def _science_version() -> str:
    """Short hash of the science code. When Emil changes the processing, cached results made
    with older code are rebuilt in the background (examples/ excluded, Emil rebuilds those)."""
    import hashlib
    h = hashlib.sha1()
    for name in ("fetch_spherex.py", "gaia_validation.py"):
        p = ROOT / "science" / name
        if p.exists():
            h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:10]


SCIENCE_VERSION = _science_version()
NEW_EPOCH_DAYS = float(os.environ.get("NEW_EPOCH_DAYS", "30"))  # newer images than this = new data


def write_cache_info(slug: str, fingerprint, collection, source: str, timing: dict | None = None):
    p = cache_info_path(slug)
    if p.parent.exists():
        old = read_cache_info(slug) or {}
        write_text_atomic(p, json.dumps({"fingerprint": fingerprint, "collection": collection,
                                 "source": source, "checked_at": time.time(),
                                 "code_version": SCIENCE_VERSION,
                                 "timing": timing or old.get("timing")}))


def read_cache_info(slug: str):
    try:
        return json.loads(cache_info_path(slug).read_text())
    except Exception:  # noqa: BLE001
        return None


def _check_path(slug: str) -> Path:
    return OUTPUT_DIR / "_checks" / f"{slug}.json"


def read_example_check(slug: str):
    try:
        return json.loads(_check_path(slug).read_text())
    except Exception:  # noqa: BLE001
        return None


def write_example_check(slug: str, newest_mjd):
    write_text_atomic(_check_path(slug),
                      json.dumps({"checked_at": time.time(), "newest_irsa_mjd": newest_mjd}))


def refresh_running(slug: str) -> bool:
    return jobs.get(f"{slug}__refresh", {}).get("status") == "processing"


def maybe_refresh(slug: str, make_pipeline) -> bool:
    """Stale-while-revalidate: the cached result is always returned right away; a light
    background check then decides whether it must be rebuilt. Returns True if a check runs.

    - Results in the cache (OUTPUT_DIR): rebuilt if IRSA has new images (fingerprint changed)
      or if they were made with older science code. Checked at most every CACHE_TTL_HOURS.
    - Precomputed examples/ (challenge targets): only rebuilt if IRSA has images more than
      NEW_EPOCH_DAYS newer than the example's last epoch (= a new SPHEREx survey pass).
      The rebuilt result goes to the cache and then takes priority over the example.
    """
    rkey = f"{slug}__refresh"
    if jobs.get(rkey, {}).get("status") == "processing":
        return True
    if jobs.get(slug, {}).get("status") in ("queued", "processing"):
        return False
    hit = find_cached(slug)
    if not hit:
        return False
    meta, base = hit
    ttl = CACHE_TTL_HOURS * 3600
    from_examples = base.startswith("/api/examples/")
    if from_examples:
        chk = read_example_check(slug)
        if chk and time.time() - chk.get("checked_at", 0) < ttl:
            return False
        info, old_code = None, False
    else:
        info = read_cache_info(slug)
        old_code = bool(info) and info.get("code_version") not in (None, SCIENCE_VERSION)
        if info and not old_code and time.time() - info.get("checked_at", 0) < ttl:
            return False
    jobs[rkey] = {"status": "processing", "t": time.time()}

    def rebuild(pipe):
        """Build into a temp folder while the old result keeps being served, then swap it in."""
        tmp = f"{slug}__new"
        shutil.rmtree(OUTPUT_DIR / tmp, ignore_errors=True)
        pipe(lambda *a: None, tmp, PER_GROUP)
        publish(tmp, slug)

    def runner():
        try:
            pipe = make_pipeline()
            imgs = pipe.images()                     # one light IRSA query
            if from_examples:
                newest = float(imgs.table["mjd"].max())
                last = max((e.get("mjd_mean") or 0) for e in meta.get("epochs", [])) or 0
                if newest > last + NEW_EPOCH_DAYS:
                    print(f"  New SPHEREx survey pass for {slug} (newest MJD {newest:.1f} > "
                          f"example {last:.1f}) -> rebuilding into cache")
                    rebuild(pipe)
                write_example_check(slug, newest)
            elif info and info.get("fingerprint") == imgs.fingerprint and not old_code:
                write_cache_info(slug, imgs.fingerprint, info.get("collection"),
                                 info.get("source", "s3"))
            else:
                why = "science code changed" if old_code else f"new SPHEREx data ({imgs.fingerprint})"
                print(f"  Rebuilding {slug}: {why}")
                rebuild(pipe)
            jobs[rkey] = {"status": "done", "t": time.time()}
        except Exception as e:  # noqa: BLE001
            print(f"  Refresh check for {slug} failed: {type(e).__name__}: {str(e)[:120]}")
            jobs[rkey] = {"status": "error", "error": str(e), "t": time.time()}

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
    resp["fallback"] = True
    resp["note"] = reason
    return resp


def target_job(key: str, fov: float, mask: bool = False):
    slug = (key if fov == 3.0 else f"{key}_fov{fov:g}") + (MASK_SUFFIX if mask else "")

    def make_pipeline():
        return Pipeline(lambda: fs.target_coord(key), fov, mask)
    return slug, make_pipeline


def coord_job(c, fov: float, mask: bool = False):
    slug = slug_for(c.ra.deg, c.dec.deg, fov) + (MASK_SUFFIX if mask else "")

    def make_pipeline():
        return Pipeline(lambda: (c, f"RA {c.ra.deg:.4f} Dec {c.dec.deg:+.4f}", {}), fov, mask)
    return slug, make_pipeline


# --------------------------------------------------------------------------- endpoints

@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Return the real error as JSON *with* CORS headers, so the browser shows the message
    instead of a bare 'Failed to fetch'."""
    traceback.print_exception(exc)   # full details go to the Cloud Run logs only
    return JSONResponse(status_code=500,
                        content={"detail": "Internal server error. Please try again in a moment."},
                        headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/targets")
def targets():
    """Challenge targets. ra/dec = today's position (proper motion applied) when a result exists,
    otherwise the catalogue position. Search by "key" to always get the moving star centred."""
    out = []
    for k, v in fs.TARGETS.items():
        meta = cached_meta(k)
        ra, dec = v["fallback"][0], v["fallback"][1]
        if meta and meta.get("ra_deg") is not None and meta.get("dec_deg") is not None:
            ra, dec = meta["ra_deg"], meta["dec_deg"]
        out.append({"key": k, "label": v["label"], "ra": round(ra, 6), "dec": round(dec, 6),
                    "cached": meta is not None})
    return out


@app.get("/api/sky")
def sky(request: Request, ra: str | None = None, dec: str | None = None,
        target: str | None = Query(None, description="one of /api/targets keys"),
        fov: float = Query(3.0, gt=0, description="field of view, arcmin"),
        mask_flags: bool = Query(False, description="leave flagged (bad) pixels out of the images")):
    if fov > MAX_FOV_ARCMIN:
        raise HTTPException(400, f"fov must be <= {MAX_FOV_ARCMIN} arcmin")

    if target:
        if target not in fs.TARGETS:
            raise HTTPException(404, f"unknown target '{target}'")
        slug, make_pipeline = target_job(target, fov, mask_flags)
    elif ra is not None and dec is not None:
        try:
            c = fs.parse_coord(ra, dec)
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "could not parse ra/dec")
        # Coordinates of a challenge target (any FOV, J2000 or today's position) -> search it as
        # that target, so the moving star is centred at today's position, not 26 years ago.
        key = matching_target(c)
        if key:
            target = key
            slug, make_pipeline = target_job(key, fov, mask_flags)
        else:
            slug, make_pipeline = coord_job(c, fov, mask_flags)
    else:
        raise HTTPException(400, "give either target or ra+dec")

    if find_cached(slug):
        resp = done_response(slug)
        resp["refreshing"] = maybe_refresh(slug, make_pipeline)
        if ra is not None and target:
            resp["note"] = f"Coordinates matched challenge target '{target}'."
        return resp
    if refresh_running(slug):
        # A background rebuild is writing this result right now; don't start a second one.
        return {"status": "processing", "job": slug, "stage": "processing", "done": 0, "total": 0,
                "preview": None}
    j = jobs.get(slug)
    if j and j["status"] in ("queued", "processing"):
        return {"status": j["status"], "job": slug}
    if j and j["status"] == "error":
        jobs.pop(slug)  # allow retry
    if not target:
        check_capacity(request)   # challenge targets are never rate limited
    # A precomputed result to fall back on if live data (IRSA) fails.
    fallback = target if target and find_cached(target) else None
    return start_job(slug, make_pipeline(), fallback=fallback)


@app.get("/api/status/{job}")
def status(job: str):
    if find_cached(job):
        return done_response(job)
    j = jobs.get(job)
    if not j and refresh_running(job):
        return {"job": job, "status": "processing", "stage": "processing", "done": 0, "total": 0,
                "preview": None}
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


# --------------------------------------------------------------------------- candidates
# Community "report a candidate" database. One small JSON file per report in
# OUTPUT_DIR/_candidates/ (the Cloud Storage bucket), so reports survive deploys and two
# reports at the same moment can never overwrite each other. Works even when IRSA is down.

CAND_DIR = OUTPUT_DIR / "_candidates"
CAND_RATE = int(os.environ.get("CANDIDATE_RATE", "10"))          # reports per IP per window
CAND_ADMIN_TOKEN = os.environ.get("CANDIDATES_ADMIN_TOKEN", "")   # set in Cloud Run to allow delete
SAME_OBJECT_ARCSEC = 10.0                                         # reports this close = same object
_cands: dict[str, dict] | None = None
cand_lock = threading.Lock()


class CandidateIn(BaseModel):
    ra: float = Field(..., ge=0, lt=360, description="RA of the moving object, degrees (ICRS)")
    dec: float = Field(..., ge=-90, le=90, description="Dec, degrees")
    job: str | None = Field(None, max_length=80, description="job id of the search it was seen in")
    band: str | None = Field(None, max_length=10, description="detector/band, e.g. 'D3'")
    epoch: int | None = Field(None, ge=0, le=1000, description="epoch index where it was clicked")
    note: str | None = Field(None, max_length=500, description="what the user saw")
    name: str | None = Field(None, max_length=40, description="optional nickname, shown publicly")
    kind: Literal["moving", "faint", "spectrum", "other"] | None = "moving"


def _load_candidates() -> dict[str, dict]:
    global _cands
    if _cands is None:
        out = {}
        CAND_DIR.mkdir(parents=True, exist_ok=True)
        for p in CAND_DIR.glob("*.json"):
            try:
                c = json.loads(p.read_text())
                out[c["id"]] = c
            except Exception:  # noqa: BLE001  half-written or broken file: skip it
                pass
        _cands = out
    return _cands


def _sep_arcsec(ra1, dec1, ra2, dec2) -> float:
    r = math.radians
    a = (math.sin(r(dec2 - dec1) / 2) ** 2
         + math.cos(r(dec1)) * math.cos(r(dec2)) * math.sin(r(ra2 - ra1) / 2) ** 2)
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(a)))) * 3600


def _with_counts(c: dict, all_c: dict[str, dict]) -> dict:
    """Add how many reports (including this one) point at the same spot on the sky."""
    same = sum(1 for o in all_c.values()
               if _sep_arcsec(c["ra"], c["dec"], o["ra"], o["dec"]) <= SAME_OBJECT_ARCSEC)
    return {**c, "reports_here": same}


@app.post("/api/candidates", status_code=201)
def report_candidate(body: CandidateIn, request: Request):
    """Report a possible new moving object. Returns the stored report."""
    rate_limit(request, "candidates", CAND_RATE,
               "Too many reports from your address. Please wait a few minutes.")
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    near = matching_target(SkyCoord(body.ra * u.deg, body.dec * u.deg))
    c = {"id": uuid.uuid4().hex[:12],
         "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         **body.model_dump(),
         "note": (body.note or "").strip() or None,
         "name": (body.name or "").strip() or None,
         "near_challenge_target": near}       # e.g. 'barnard' = probably the known star
    with cand_lock:
        cands = _load_candidates()
        write_text_atomic(CAND_DIR / f"{c['id']}.json", json.dumps(c))
        cands[c["id"]] = c
        return _with_counts(c, cands)


@app.get("/api/candidates")
def list_candidates(ra: float | None = Query(None, ge=0, lt=360),
                    dec: float | None = Query(None, ge=-90, le=90),
                    radius_arcmin: float = Query(10.0, gt=0, le=600),
                    limit: int = Query(200, ge=1, le=1000)):
    """All reports, newest first. With ra+dec: only reports within radius_arcmin of that point
    (e.g. the field the viewer is showing)."""
    with cand_lock:
        cands = dict(_load_candidates())
    items = list(cands.values())
    if ra is not None and dec is not None:
        items = [c for c in items
                 if _sep_arcsec(ra, dec, c["ra"], c["dec"]) <= radius_arcmin * 60]
    items.sort(key=lambda c: c["created_at"], reverse=True)
    return {"count": len(items), "candidates": [_with_counts(c, cands) for c in items[:limit]]}


@app.get("/api/candidates/{cid}")
def get_candidate(cid: str):
    with cand_lock:
        cands = _load_candidates()
        c = cands.get(cid)
        if not c:
            raise HTTPException(404, "Unknown candidate id.")
        return _with_counts(c, cands)


@app.delete("/api/candidates/{cid}")
def delete_candidate(cid: str, request: Request):
    """Moderation (spam). Needs header  X-Admin-Token: <CANDIDATES_ADMIN_TOKEN>."""
    if not CAND_ADMIN_TOKEN or request.headers.get("x-admin-token") != CAND_ADMIN_TOKEN:
        raise HTTPException(403, "Not allowed.")
    with cand_lock:
        cands = _load_candidates()
        if cands.pop(cid, None) is None:
            raise HTTPException(404, "Unknown candidate id.")
        (CAND_DIR / f"{cid}.json").unlink(missing_ok=True)
    return {"deleted": cid}


# --------------------------------------------------------------------------- Gaia field stars
# All Gaia DR3 stars around an image, for the viewer overlay. Fetched from VizieR mirrors
# (short timeout each), cached in memory and on disk (Gaia DR3 never changes).

GAIA_MIRRORS = [m.strip() for m in os.environ.get(
    "GAIA_MIRRORS",
    "https://vizier.cfa.harvard.edu,https://vizier.cds.unistra.fr,https://vizier.iucaa.in,"
    "https://vizier.nao.ac.jp").split(",") if m.strip()]
GAIA_TIMEOUT_S = float(os.environ.get("GAIA_TIMEOUT_S", "10"))
GAIA_MAX_STARS = 2000            # brightest first; enough that faint field stars are not missed
GAIA_MAX_RADIUS_ARCSEC = 900.0   # covers the corners of a 20 arcmin field (half diagonal ~850")
GAIA_DIR = OUTPUT_DIR / "_gaia"
_gaia_mem: dict[str, dict] = {}
_gaia_locks: dict[str, threading.Lock] = {}


def _num(v: str):
    """TSV cell -> float, or None for blank/NaN (JSON has no NaN)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def parse_vizier_tsv(text: str) -> list[dict]:
    """Rows of a VizieR asu-tsv answer with -out=Source,RA_ICRS,DE_ICRS,pmRA,pmDE,Gmag.
    Skips #comments, blank lines, the column-name, unit and dash lines."""
    stars, cols = [], None
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = [c.strip() for c in line.split("\t")]
        if cols is None:
            if "Source" in cells and "RA_ICRS" in cells:
                cols = {name: i for i, name in enumerate(cells)}
            continue
        row = dict(zip(cols, (cells + [""] * len(cols))[:len(cols)]))
        if not row.get("Source", "").isdigit():
            continue                      # unit line, dash line or junk
        ra, dec = _num(row.get("RA_ICRS")), _num(row.get("DE_ICRS"))
        if ra is None or dec is None:
            continue
        stars.append({"id": row["Source"], "ra": ra, "dec": dec,
                      "pmra": _num(row.get("pmRA")), "pmdec": _num(row.get("pmDE")),
                      "g": _num(row.get("Gmag"))})
    return stars


def fetch_gaia(ra: float, dec: float, radius_arcsec: float) -> list[dict]:
    """Ask each VizieR mirror in turn. Raises ConnectionError if none answers properly."""
    q = urllib.parse.urlencode({
        "-source": "I/355/gaiadr3", "-c": f"{ra:.6f} {dec:+.6f}", "-c.rs": f"{radius_arcsec:g}",
        "-out": "Source,RA_ICRS,DE_ICRS,pmRA,pmDE,Gmag", "-out.max": str(GAIA_MAX_STARS + 1),
        "-sort": "Gmag"})
    errors = []
    for mirror in GAIA_MIRRORS:
        url = f"{mirror}/viz-bin/asu-tsv?{q}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "StarXViewer/1.0"})
            with urllib.request.urlopen(req, timeout=GAIA_TIMEOUT_S) as r:
                text = r.read().decode("utf-8", "replace")
            if "RA_ICRS" not in text:      # error page, not a catalogue answer
                raise ValueError("no catalogue table in answer")
            return parse_vizier_tsv(text)
        except Exception as e:  # noqa: BLE001  try the next mirror
            errors.append(f"{mirror}: {type(e).__name__}: {str(e)[:80]}")
    print("  Gaia: all VizieR mirrors failed -> " + " | ".join(errors))
    raise ConnectionError("no VizieR mirror answered")


@app.get("/api/gaia")
def gaia(ra_f: float = Query(..., alias="ra", ge=0, lt=360, description="degrees"),
         dec_f: float = Query(..., alias="dec", ge=-90, le=90, description="degrees"),
         rad_f: float = Query(..., alias="radius", gt=0, le=GAIA_MAX_RADIUS_ARCSEC, description="arcsec")):
    """Gaia DR3 stars within `radius` arcsec of ra/dec (degrees). Positions at J2016.0,
    brightest first, at most 2000. The viewer moves them to each SPHEREx epoch itself."""
    key = f"ra{ra_f:.4f}_dec{dec_f:+.4f}_r{rad_f:.0f}"
    if key in _gaia_mem:
        return _gaia_mem[key]
    with lock:
        klock = _gaia_locks.setdefault(key, threading.Lock())
    with klock:                                    # same field asked twice at once -> one query
        if key in _gaia_mem:
            return _gaia_mem[key]
        p = GAIA_DIR / f"{key}.json"
        try:
            resp = json.loads(p.read_text())
        except Exception:  # noqa: BLE001  not cached on disk yet
            try:
                stars = fetch_gaia(ra_f, dec_f, rad_f)
            except ConnectionError:
                raise HTTPException(503, "Gaia catalogue not reachable right now")
            stars.sort(key=lambda s: (s["g"] is None, s["g"] if s["g"] is not None else 0))
            resp = {"epoch": 2016.0, "source": "Gaia DR3 (VizieR I/355/gaiadr3)",
                    "ra": ra_f, "dec": dec_f, "radius_arcsec": rad_f,
                    "count": min(len(stars), GAIA_MAX_STARS),
                    "truncated": len(stars) > GAIA_MAX_STARS,
                    "stars": stars[:GAIA_MAX_STARS]}
            try:
                write_text_atomic(p, json.dumps(resp))
            except Exception:  # noqa: BLE001  disk cache is optional
                traceback.print_exc()
        if len(_gaia_mem) > 2000:
            _gaia_mem.clear()
            with lock:
                _gaia_locks.clear()   # one lock per field, pruned together with the answers
        _gaia_mem[key] = resp
        return resp


def warmup():
    """Run once at startup (see lifespan): build any challenge target that has no result yet."""
    if not WARMUP:
        return
    for key in fs.TARGETS:
        if cached_meta(key) is None:
            slug, make_pipeline = target_job(key, 3.0)
            start_job(slug, make_pipeline(), preview=False)
