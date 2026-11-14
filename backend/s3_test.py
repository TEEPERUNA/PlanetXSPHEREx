"""
S3 vs IRSA test for SPHEREx (Erik / backend).
AI-assisted: written with Claude (Anthropic).

Checks:
  1. Does the SIA query return S3 paths (cloud_access)?
  2. Is the S3 file identical to the IRSA file (VERSION header + pixels)?
  3. Speed: N cutouts via IRSA cutout service vs. N partial reads from S3.

Run from repo root:
    pip install s3fs
    python backend/s3_test.py
"""
import concurrent.futures as cf
import io
import json
import time
import urllib.request

import numpy as np
import astropy.units as u
from astropy import log
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astroquery.ipac.irsa import Irsa

log.setLevel("WARNING")

COORD = SkyCoord(269.446080, 4.770706, unit="deg")  # Barnard's Star (2026)
COLLECTIONS = ["spherex_qr3", "spherex_dr1", "spherex_qr2"]
N = 12            # files in the speed test
HALF = 15         # cutout half-size in pixels (31x31 like the pipeline)
SIZE_DEG = 0.05   # IRSA cutout size, same as the pipeline
WORKERS = 12


def s3_path(row):
    raw = row["cloud_access"]
    if raw is None or str(raw).strip() in ("", "--"):
        return None
    aws = json.loads(str(raw))["aws"]
    return f"s3://{aws['bucket_name']}/{aws['key']}"


S3_DEFAULT = {"anon": True}
S3_TUNED = {"anon": True, "default_block_size": 256 * 1024, "default_cache_type": "blockcache"}


def read_s3(path, fs_kwargs=S3_DEFAULT):
    """Partial read from S3: headers + only the needed pixels."""
    with fits.open(path, use_fsspec=True, fsspec_kwargs=fs_kwargs) as h:
        hdr = h["IMAGE"].header
        x, y = WCS(hdr).world_to_pixel(COORD)
        xi, yi = int(round(float(x))), int(round(float(y)))
        sl = (slice(yi - HALF, yi + HALF + 1), slice(xi - HALF, xi + HALF + 1))
        img = h["IMAGE"].section[sl]
        flags = h["FLAGS"].section[sl]
        var = h["VARIANCE"].section[sl]
        zodi = h["ZODI"].section[sl]
        version = h[0].header.get("VERSION")
    return img, version, (img.nbytes + flags.nbytes + var.nbytes + zodi.nbytes)


def read_irsa_cutout(url):
    """Current method: IRSA cutout service."""
    cut = f"{url}?center={COORD.ra.deg},{COORD.dec.deg}d&size={SIZE_DEG}"
    with urllib.request.urlopen(cut, timeout=120) as r:
        data = r.read()
    with fits.open(io.BytesIO(data)) as h:
        return h["IMAGE"].data.copy(), h[0].header.get("VERSION"), len(data)


def timed(fn, items):
    return timed2(fn, items, WORKERS)


def timed2(fn, items, workers):
    t0, ok, fail = time.time(), 0, 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for f in cf.as_completed([ex.submit(fn, i) for i in items]):
            try:
                f.result()
                ok += 1
            except Exception as e:  # noqa: BLE001
                fail += 1
                print(f"    failed: {type(e).__name__}: {str(e)[:100]}")
    return time.time() - t0, ok, fail


def main():
    print("== 1. SIA query")
    res = None
    for coll in COLLECTIONS:
        t0 = time.time()
        r = Irsa.query_sia(pos=(COORD, 1 * u.arcsec), collection=coll)
        print(f"  {coll}: {len(r)} images ({time.time() - t0:.1f} s)")
        if len(r) and res is None:
            res, used = r, coll
    if res is None:
        print("No images found.")
        return
    print(f"  using {used}; has cloud_access column: {'cloud_access' in res.colnames}")
    tab = res.to_table() if hasattr(res, "to_table") else res
    rows = [(str(row["access_url"]), s3_path(row)) for row in tab]
    with_s3 = [(a, s) for a, s in rows if s]
    print(f"  rows with S3 path: {len(with_s3)}/{len(rows)}")
    if not with_s3:
        print("  -> No S3 paths for this release. S3 route not possible (yet).")
        return
    print(f"  example S3 path: {with_s3[0][1]}")

    if "--speed" in __import__("sys").argv:
        return speed(with_s3)
    print("\n== 2. Same data? (one file, both routes)")
    url, s3 = with_s3[0]
    a, va, _ = read_s3(s3)
    with fits.open(url, use_fsspec=True) as h:  # IRSA full file, partial read
        x, y = WCS(h["IMAGE"].header).world_to_pixel(COORD)
        xi, yi = int(round(float(x))), int(round(float(y)))
        b = h["IMAGE"].section[yi - HALF:yi + HALF + 1, xi - HALF:xi + HALF + 1]
        vb = h[0].header.get("VERSION")
    print(f"  VERSION  S3={va}  IRSA={vb}")
    print(f"  identical pixels: {np.array_equal(a, b, equal_nan=True)}")

    speed(with_s3, irsa=True)


def speed(with_s3, irsa=False):
    print(f"\n== 3. Speed, {N} files, {WORKERS} parallel")
    sample = with_s3[:N]
    if irsa:
        t, ok, fail = timed(lambda p: read_irsa_cutout(p[0]), sample)
        print(f"  IRSA cutout service: {t:.1f} s  (ok {ok}, failed {fail})")
    t, ok, fail = timed(lambda p: read_s3(p[1], S3_DEFAULT), sample)
    print(f"  S3 default (5 MB blocks): {t:.1f} s  (ok {ok}, failed {fail})")
    t, ok, fail = timed(lambda p: read_s3(p[1], S3_TUNED), sample)
    print(f"  S3 tuned (256 kB blocks): {t:.1f} s  (ok {ok}, failed {fail})")
    big = with_s3[:48]
    t, ok, fail = timed2(lambda p: read_s3(p[1], S3_TUNED), big, 32)
    print(f"  S3 tuned, {len(big)} files, 32 parallel: {t:.1f} s  (ok {ok}, failed {fail})")
    print("\nPaste this output to the chat.")


if __name__ == "__main__":
    main()
