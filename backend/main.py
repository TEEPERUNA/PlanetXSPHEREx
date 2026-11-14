"""
SPHEREx Sky API (FastAPI)
Project architecture: TypeScript Frontend + FastAPI Backend + Science Engine
Follows CONTRACT.md specifications.

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
MAX_FOV_ARCMIN = float(os.environ.get("MAX_FOV_ARCMIN", "10"))
WARMUP = os.environ.get("WARMUP", "1") == "1"

app = FastAPI(title="SPHEREx Sky API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/api/files", StaticFiles(directory=OUTPUT_DIR), name="files")

executor = ThreadPoolExecutor(max_workers=int(os.environ.get("JOB_WORKERS", "2")))
jobs: dict[str, dict] = {}
lock = threading.Lock()


def make_args(fov: float) -> SimpleNamespace:
    return SimpleNamespace(size=fov, bands=list(fs.DETECTORS), max=0, per_group=PER_GROUP,
                           workers=10, mask_flags=False, lo=1.0, hi=99.7, frame_ms=600,
                           out=str(OUTPUT_DIR))


def slug_for(ra: float, dec: float, fov: float) -> str:
    return f"ra{ra:.4f}_dec{dec:+.4f}_fov{fov:g}"


def cached_meta(slug: str):
    p = OUTPUT_DIR / slug / "meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    # Check if precomputed in examples/
    ex_p = ROOT / "examples" / slug / "meta.json"
    if ex_p.exists():
        try:
            return json.loads(ex_p.read_text())
        except Exception:
            return None
    return None


def done_response(slug: str, meta: dict) -> dict:
    return {"status": "done", "job": slug, "base_url": f"/api/files/{slug}/", "meta": meta}


def start_job(slug: str, work) -> dict:
    with lock:
        j = jobs.get(slug)
        if j and j["status"] in ("queued", "processing"):
            return {"status": j["status"], "job": slug}
        jobs[slug] = {"status": "queued", "done": 0, "total": 0, "stage": "queued", "error": None}

    def progress(done, total, stage):
        jobs[slug].update(status="processing", done=done, total=total, stage=stage)

    def runner():
        try:
            jobs[slug]["status"] = "processing"
            work(progress)
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

    def work(progress):
        c, label, info = fs.target_coord(key)
        fs.run(c, label, slug, make_args(fov), info, progress=progress)
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

        def work(progress, c=c, slug=slug):
            fs.run(c, f"RA {c.ra.deg:.4f} Dec {c.dec.deg:+.4f}", slug, make_args(fov), {}, progress=progress)
    else:
        raise HTTPException(400, "give either target or ra+dec")

    meta = cached_meta(slug)
    if meta:
        return done_response(slug, meta)
    j = jobs.get(slug)
    if j and j["status"] == "error":
        jobs.pop(slug)  # allow retry
    return start_job(slug, work)


@app.get("/api/status/{job}")
def status(job: str):
    meta = cached_meta(job)
    if meta:
        return done_response(job, meta)
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
            start_job(slug, work)
