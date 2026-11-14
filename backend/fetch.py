"""
Fast SPHEREx data access for the backend (Erik).
AI-assisted: written with Claude (Anthropic).

1. find_images(): IRSA SIA search -> which images cover a position (+ their S3 paths)
2. fetch_cutouts(): partial reads from AWS S3 (s3://nasa-irsa-spherex, public, no credentials)
   -> small FITS cutouts with corrected WCS -> science.parse_cutout_hdul() -> Cutout objects
   that go straight into science.run(..., cutouts=...)

Why: IRSA's cutout service was slow (54 images in 90-136 s) and returned HTTP 503 for
30-60 % of requests in our tests. S3 partial reads: 48 images in 16 s from Finland, 0 errors,
pixels identical to IRSA (same VERSION). See backend/s3_test.py.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import math
import os
import time
from dataclasses import dataclass

import numpy as np
from astropy import log as _astropy_log
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

import fetch_spherex as fs  # science/ (on sys.path via backend/main.py)

_astropy_log.setLevel("WARNING")

# Newest release first. The first collection that has images for a position is used.
COLLECTIONS = [c.strip() for c in os.environ.get(
    "SPHEREX_COLLECTIONS", "spherex_dr1,spherex_qr3").split(",") if c.strip()]
S3_WORKERS = int(os.environ.get("S3_WORKERS", "32"))
S3_FS_KWARGS = {"anon": True, "default_block_size": 256 * 1024, "default_cache_type": "blockcache"}
DETECTOR_SIZE = 2040
EXTS = ("IMAGE", "FLAGS", "VARIANCE", "ZODI")


@dataclass
class ImageList:
    collection: str
    table: Table           # columns: mjd, band, url, s3
    fingerprint: str       # changes when new data appears -> cache invalidation


def _s3_path(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == "--":
        return None
    try:
        aws = json.loads(s)["aws"]
        return f"s3://{aws['bucket_name']}/{aws['key']}"
    except (ValueError, KeyError, TypeError):
        return None


def find_images(coord: SkyCoord, bands: list[str] | None = None) -> ImageList:
    """IRSA SIA search: all SPHEREx images whose footprint contains the position."""
    from astroquery.ipac.irsa import Irsa
    bands = bands or list(fs.DETECTORS)
    for coll in COLLECTIONS:
        res = Irsa.query_sia(pos=(coord, 1 * u.arcsec), collection=coll)
        tab = res.to_table() if hasattr(res, "to_table") else res
        if len(tab) == 0:
            continue
        rows, seen = [], set()
        for r in tab:
            url = str(r["access_url"])
            band = str(r["energy_bandpassname"]).replace("SPHEREx-", "")
            if url in seen or not url.endswith(".fits") or band not in bands:
                continue
            seen.add(url)
            rows.append((float(r["t_min"]), band, url, _s3_path(r["cloud_access"]) or ""))
        if not rows:
            continue
        rows.sort()
        t = Table(rows=rows, names=("mjd", "band", "url", "s3"))
        fp = f"{coll}:{len(t)}:{t['mjd'].max():.4f}"
        return ImageList(coll, t, fp)
    raise LookupError("No SPHEREx images cover this position")


def select(images: ImageList, per_group: int) -> Table:
    """Up to per_group images per (epoch, detector), spread over time. 0 = all."""
    return fs.select_per_group(images.table, per_group)


def _shift_header(hdr: fits.Header, x0: int, y0: int) -> fits.Header:
    """Cutout header: move reference pixels so WCS (incl. SIP and spectral 'W') stays valid."""
    h = hdr.copy()
    for key, off in (("CRPIX1", x0), ("CRPIX2", y0), ("CRPIX1W", x0), ("CRPIX2W", y0)):
        if key in h:
            h[key] = h[key] - off
    return h


def read_cutout(row, coord: SkyCoord, half_px: int) -> fits.HDUList:
    """Read only the needed pixels of one SPHEREx file from S3 and build a small HDUList
    with the same layout as an IRSA cutout (PRIMARY, IMAGE, FLAGS, VARIANCE, ZODI, WCS-WAVE)."""
    with fits.open(str(row["s3"]), use_fsspec=True, fsspec_kwargs=S3_FS_KWARGS) as h:
        hdr = h["IMAGE"].header
        x, y = WCS(hdr).world_to_pixel(coord)
        xc, yc = int(round(float(x))), int(round(float(y)))
        x0, x1 = max(0, xc - half_px), min(DETECTOR_SIZE, xc + half_px + 1)
        y0, y1 = max(0, yc - half_px), min(DETECTOR_SIZE, yc + half_px + 1)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("position outside detector")
        out = [fits.PrimaryHDU(header=h[0].header.copy())]
        for ext in EXTS:
            if ext not in h:
                continue
            data = np.asarray(h[ext].section[y0:y1, x0:x1])
            out.append(fits.ImageHDU(data=data, header=_shift_header(h[ext].header, x0, y0), name=ext))
        if "WCS-WAVE" in h:
            ww = h["WCS-WAVE"]
            out.append(fits.BinTableHDU(data=ww.data.copy(), header=ww.header.copy(), name="WCS-WAVE"))
    return fits.HDUList(out)


def _fetch_one(row, coord, half_px, pm_info, attempts=3):
    for a in range(1, attempts + 1):
        try:
            hdul = read_cutout(row, coord, half_px)
            return fs.parse_cutout_hdul(hdul, row["mjd"], row["band"], coord,
                                        pm_info=pm_info, url=str(row["url"]))
        except ValueError:
            return None
        except Exception as e:  # noqa: BLE001  network hiccup -> retry
            if a == attempts:
                print(f"  S3 skipped ({type(e).__name__}: {str(e)[:120]})")
                return None
            time.sleep(1.5 * a)


def fetch_cutouts(rows: Table, coord: SkyCoord, fov_arcmin: float, pm_info: dict | None = None,
                  progress=None, memo: dict | None = None) -> list:
    """Download cutouts from S3 in parallel. memo (url -> Cutout) lets a later full run
    reuse what the quick preview already downloaded."""
    memo = {} if memo is None else memo
    half_px = int(math.ceil(fov_arcmin * 60 / fs.PIXEL_SCALE_ARCSEC / 2)) + 4
    todo = [r for r in rows if r["s3"] and str(r["url"]) not in memo]
    total, done = len(rows), len(rows) - len(todo)
    if progress:
        progress(done, total, "downloading")
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=S3_WORKERS) as ex:
        futs = {ex.submit(_fetch_one, r, coord, half_px, pm_info): str(r["url"]) for r in todo}
        for f in cf.as_completed(futs):
            c = f.result()
            if c is not None:
                memo[futs[f]] = c
            done += 1
            if progress:
                progress(done, total, "downloading")
    cutouts = [memo[str(r["url"])] for r in rows if str(r["url"]) in memo]
    print(f"  S3: {len(cutouts)}/{total} cutouts ({time.time() - t0:.1f} s)")
    return cutouts
