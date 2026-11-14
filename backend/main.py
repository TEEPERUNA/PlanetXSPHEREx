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

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "science"))
import fetch_spherex as fs  # noqa: E402

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PER_GROUP = int(os.environ.get("PER_GROUP", "3"))      # images per epoch+detector (speed vs quality)
PREVIEW_PER_GROUP = int(os.environ.get("PREVIEW_PER_GROUP", "1"))  # quick first result (0 = off)
DOWNLOAD_WORKERS = int(os.environ.get("DOWNLOAD_WORKERS", "6"))
MAX_FOV_ARCMIN = float(os.environ.get("MAX_FOV_ARCMIN", "10"))
WARMUP = os.environ.get("WARMUP", "1") == "1"

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


def find_cached(slug: str):
    """Returns (meta, base_url) for a finished result, or None.
    Looks in OUTPUT_DIR first, then the precomputed examples/ folder in the repo."""
    for folder, prefix in ((OUTPUT_DIR, "/api/files"), (EXAMPLES_DIR, "/api/examples")):
        p = folder / slug / "meta.json"
        if p.exists():
            try:
                return json.loads(p.read_text()), f"{prefix}/{slug}/"
            except Exception:  # noqa: BLE001  half-written file
                return None
    return None


def cached_meta(slug: str):
    hit = find_cached(slug)
    return hit[0] if hit else None


def done_response(slug: str) -> dict:
    meta, base = find_cached(slug)
    return {"status": "done", "job": slug, "base_url": base, "meta": meta}


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
        except LookupError as e:
            jobs[slug].update(status="error", error=str(e))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            jobs[slug].update(status="error", error=f"{type(e).__name__}: {e}")

    executor.submit(runner)
    return {"status": "queued", "job": slug}


def target_job(key: str, fov: float):
    slug = key if fov == 3.0 else f"{key}_fov{fov:g}"

    def work(progress, out_slug, per_group):
        c, label, info = fs.target_coord(key)
        fs.run(c, label, out_slug, make_args(fov, per_group), info, progress=progress)
    return slug, work


# --------------------------------------------------------------------------- endpoints

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
        slug, work = target_job(target, fov)
    elif ra is not None and dec is not None:
        try:
            c = fs.parse_coord(ra, dec)
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "could not parse ra/dec")
        slug = slug_for(c.ra.deg, c.dec.deg, fov)

        def work(progress, out_slug, per_group, c=c):
            fs.run(c, f"RA {c.ra.deg:.4f} Dec {c.dec.deg:+.4f}", out_slug,
                    make_args(fov, per_group), {}, progress=progress)
    else:
        raise HTTPException(400, "give either target or ra+dec")

    if find_cached(slug):
        return done_response(slug)
    j = jobs.get(slug)
    if j and j["status"] == "error":
        jobs.pop(slug)  # allow retry
    return start_job(slug, work)


@app.get("/api/status/{job}")
def status(job: str):
    if find_cached(job):
        return done_response(job)
    j = jobs.get(job)
    if not j:
        raise HTTPException(404, "unknown job")
    return {"job": job, **j}


@app.on_event("startup")
def warmup():
    if not WARMUP:
        return
    for key in fs.TARGETS:
        if cached_meta(key) is None:
            slug, work = target_job(key, 3.0)
            start_job(slug, work, preview=False)
