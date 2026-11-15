#!/usr/bin/env python3
"""
fetch_spherex.py - Fetches SPHEREx cutouts for a given sky position and generates
time-series epochs, blink GIFs, difference images, spectra, band-specific light curves,
and Gaia DR3 astrometric validation.

Examples:
    python fetch_spherex.py --target wise0855
    python fetch_spherex.py --all-targets
    python fetch_spherex.py --ra 133.795 --dec -7.245 --size 3
    python fetch_spherex.py --ra "08h55m10.831s" --dec "-7d14m42.53s" --bands D1 D2
    python fetch_spherex.py --name "RW Aur"

Data: NASA/IPAC IRSA, SPHEREx (TAP tables spherex.artifact + spherex.plane, cutout service).
Developed for the NASA Space Apps Challenge 2026 (Planet X and SPHEREx).
Scientific image processing & validation: Emil.
Based on IRSA SPHEREx tutorials (BSD-3-Clause, Caltech-IPAC).
AI usage: Written and developed with the assistance of an AI assistant (Claude / Antigravity).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import http.client
import json
import os
import sys
import time
import urllib.error
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.utils.data import conf as data_conf
from astropy.wcs import WCS, FITSFixedWarning
from astropy import log

# Silence SIP and WCS info logs
log.setLevel("WARNING")

# Import Gaia validation and target identification
try:
    from gaia_validation import validate_gaia, identify_benchmark_target, sanitize_for_json
except ImportError:
    try:
        from science.gaia_validation import validate_gaia, identify_benchmark_target, sanitize_for_json
    except ImportError:
        validate_gaia = None
        identify_benchmark_target = None
        sanitize_for_json = None

if sanitize_for_json is None:
    def sanitize_for_json(obj):
        """
        Recursively replaces NaN, Infinity, -Infinity with None so that json.dumps
        writes valid standard JSON with 'null' instead of non-standard 'NaN'.
        Also converts numpy types (float32, int64, ndarray) into native Python types.
        """
        if obj is None:
            return None
        if isinstance(obj, (float, np.floating)):
            return None if not np.isfinite(obj) else float(obj)
        if isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        if isinstance(obj, (int, np.integer)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return [sanitize_for_json(x) for x in obj.tolist()]
        if isinstance(obj, dict):
            return {str(k): sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [sanitize_for_json(x) for x in obj]
        return obj

warnings.filterwarnings("ignore", category=FITSFixedWarning)
data_conf.remote_timeout = 90

PIXEL_SCALE_ARCSEC = 6.15  # SPHEREx pixel scale (arcsec)

# Detectors and their wavelength coverage (µm)
DETECTORS = {
    "D1": (0.75, 1.09),
    "D2": (1.10, 1.62),
    "D3": (1.63, 2.41),
    "D4": (2.42, 3.82),
    "D5": (3.83, 4.41),
    "D6": (4.42, 5.00),
}

BAND_COLORS = {
    "D1": "#38bdf8",  # Light blue (0.75-1.09 µm)
    "D2": "#6366f1",  # Indigo (1.10-1.62 µm)
    "D3": "#10b981",  # Green (1.63-2.41 µm)
    "D4": "#f59e0b",  # Yellow (2.42-3.82 µm)
    "D5": "#f97316",  # Orange (3.83-4.41 µm)
    "D6": "#ef4444",  # Red (4.42-5.00 µm)
}

# SPHEREx Level 2 bad-pixel flag bitmask (Table 16, SPHEREx Explanatory Supplement).
# Excludes benign informational bits: Bit 12 (FULLSAMPLE, 4096) and Bit 22 (SOURCE, 4194304).
BAD_PIXEL_MASK = (
    (1 << 0)    # TRANSIENT (cosmic ray)
    | (1 << 1)  # OVERFLOW (saturation)
    | (1 << 2)  # SUR_ERROR
    | (1 << 6)  # NONFUNC (dead pixel)
    | (1 << 7)  # DICHROIC
    | (1 << 9)  # MISSING_DATA
    | (1 << 10) # HOT pixel
    | (1 << 11) # COLD pixel
    | (1 << 15) # NONLINEAR
    | (1 << 17) # PERSIST
    | (1 << 20) # OUTLIER
    | (1 << 27) # BLOOM
    | (1 << 28) # SNOWBALL
)

# Challenge benchmark targets. Simbad name is queried for coordinates and proper motion (J2000),
# with fallback coordinates used if Simbad query fails.
TARGETS = {
    "barnard":  {"simbad": "GJ 699", "label": "Barnard's Star",
                 "fallback": (269.452083, 4.693364, -801.551, 10362.394)},
    "epsindib": {"simbad": "eps Ind B", "label": "Epsilon Indi B",
                 "fallback": (331.0438, -56.7827, 3966.7, -2536.2)},
    "wise0855": {"simbad": "WISE J085510.83-071442.5", "label": "WISE 0855-0714",
                 # Challenge target coordinates, proper motion approx -8.1"/yr, +0.7"/yr
                 "fallback": (133.795129, -7.245147, -8118.0, 673.0), "fallback_epoch": 2014.4},
    "rwaur":    {"simbad": "RW Aur", "label": "RW Aurigae",
                 "fallback": (76.956250, 30.401111, 0.0, 0.0)},
    "rdra":     {"simbad": "R Dra", "label": "R Draconis",
                 "fallback": (248.167625, 66.754972, 9.12, 12.44)},
}

EPOCH_GAP_DAYS = 30  # Gap in observations exceeding this triggers a new epoch


# --------------------------------------------------------------------------- coordinates

def parse_coord(ra: str, dec: str) -> SkyCoord:
    try:
        return SkyCoord(float(ra) * u.deg, float(dec) * u.deg, frame="icrs")
    except ValueError:
        return SkyCoord(ra, dec, frame="icrs")


def propagate(ra, dec, pmra_masyr, pmdec_masyr, epoch_from: float, epoch_to: float) -> SkyCoord:
    """Linear proper motion propagation (sufficient for small arcminute cutouts)."""
    dt = epoch_to - epoch_from
    dec2 = dec + pmdec_masyr * dt / 3.6e6
    ra2 = ra + pmra_masyr * dt / 3.6e6 / np.cos(np.radians(dec))
    return SkyCoord(ra2 * u.deg, dec2 * u.deg, frame="icrs")


def resolve_name(name: str):
    """Returns (ra, dec, pmra, pmdec) at J2000 from Simbad. None if lookup fails."""
    try:
        from astroquery.simbad import Simbad
        s = Simbad()
        s.add_votable_fields("pmra", "pmdec")
        r = s.query_object(name)
        if r is None or len(r) == 0:
            return None
        cols = {c.lower(): c for c in r.colnames}
        ra_v, dec_v = r[cols["ra"]][0], r[cols["dec"]][0]
        if isinstance(ra_v, str):  # legacy astroquery: sexagesimal string
            c = SkyCoord(ra_v, dec_v, unit=(u.hourangle, u.deg))
            ra_v, dec_v = c.ra.deg, c.dec.deg
        pmra_raw = r[cols["pmra"]][0] if "pmra" in cols and not np.ma.is_masked(r[cols["pmra"]][0]) else 0.0
        pmdec_raw = r[cols["pmdec"]][0] if "pmdec" in cols and not np.ma.is_masked(r[cols["pmdec"]][0]) else 0.0
        pmra = float(pmra_raw) if (pmra_raw is not None and np.isfinite(pmra_raw)) else 0.0
        pmdec = float(pmdec_raw) if (pmdec_raw is not None and np.isfinite(pmdec_raw)) else 0.0
        return float(ra_v), float(dec_v), pmra, pmdec
    except Exception as e:  # noqa: BLE001
        print(f"  Simbad lookup failed ({name}): {e}")
        return None


def target_coord(key_or_name: str) -> tuple[SkyCoord, str, dict]:
    now = Time.now().decimalyear
    if key_or_name in TARGETS:
        t = TARGETS[key_or_name]
        res = resolve_name(t["simbad"])
        if res:
            ra, dec, pmra, pmdec = res
            epoch0 = 2000.0
        else:
            ra, dec, pmra, pmdec = t["fallback"]
            epoch0 = t.get("fallback_epoch", 2000.0)
        label = t["label"]
    else:
        res = resolve_name(key_or_name)
        if not res:
            sys.exit(f"Target not found: {key_or_name}")
        ra, dec, pmra, pmdec = res
        epoch0, label = 2000.0, key_or_name
    c = propagate(ra, dec, pmra, pmdec, epoch0, now)
    info = {
        "pmra_masyr": round(float(pmra), 3) if (pmra is not None and np.isfinite(pmra)) else None,
        "pmdec_masyr": round(float(pmdec), 3) if (pmdec is not None and np.isfinite(pmdec)) else None,
        "propagated_to": round(now, 3)
    }
    return c, label, info


def get_target_key(coord: SkyCoord, slug_or_name: str = "") -> str | None:
    """Identifies benchmark test target based on name/slug or coordinate proximity."""
    if identify_benchmark_target:
        return identify_benchmark_target(coord, slug_or_name)
    s = slug_or_name.lower().replace("-", "").replace("_", "").replace(" ", "").replace("'", "")
    for k in TARGETS:
        if k in s or s.startswith(k):
            return k
    for k, t in TARGETS.items():
        fb_ra, fb_dec = t["fallback"][:2]
        c_ref = SkyCoord(fb_ra * u.deg, fb_dec * u.deg, frame="icrs")
        if coord.separation(c_ref).arcmin < 3.0:
            return k
    return None


# --------------------------------------------------------------------------- TAP query

def query_images(coord: SkyCoord, size_deg: float, bands: list[str]):
    from astroquery.ipac.irsa import Irsa
    band_sql = ",".join(f"'SPHEREx-{b}'" for b in bands)
    query = f"""
    SELECT
        'https://irsa.ipac.caltech.edu/' || a.uri ||
            '?center={coord.ra.deg},{coord.dec.deg}d&size={size_deg}' AS uri,
        p.time_bounds_lower AS mjd,
        p.energy_bandpassname AS band
    FROM spherex.artifact a
    JOIN spherex.plane p ON a.planeid = p.planeid
    WHERE 1 = CONTAINS(POINT('ICRS', {coord.ra.deg}, {coord.dec.deg}), p.poly)
      AND p.energy_bandpassname IN ({band_sql})
    ORDER BY p.time_bounds_lower
    """
    t0 = time.time()
    tab = Irsa.query_tap(query).to_table()
    print(f"  TAP: {len(tab)} images ({time.time() - t0:.1f} s)")
    return tab


@dataclass
class Cutout:
    mjd: float
    band: str
    url: str
    image: np.ndarray = None
    flags: np.ndarray = None
    variance: np.ndarray = None
    wcs: WCS = None
    wavelength_um: float = np.nan
    center_flux: float = np.nan
    center_err: float = np.nan
    flagged_frac: float = np.nan
    version: str = ""


def parse_cutout_hdul(h, mjd: float, band: str, coord: SkyCoord,
                      pm_info: dict | None = None, url: str = "") -> Cutout:
    """Parses an opened FITS HDUList into a Cutout object and computes photometry and wavelength."""
    c = Cutout(mjd=float(mjd), band=str(band).replace("SPHEREx-", ""), url=url)
    img = h["IMAGE"].data.astype(np.float32)
    zodi = h["ZODI"].data.astype(np.float32) if "ZODI" in h else 0.0
    c.image = img - zodi
    c.flags = h["FLAGS"].data
    c.variance = h["VARIANCE"].data.astype(np.float32)
    hdr = h["IMAGE"].header
    c.wcs = WCS(hdr)
    c.version = str(h[0].header.get("VERSION", ""))

    # Proper motion compensation in photometry and spectroscopy:
    # If the target has significant proper motion (e.g. Barnard's Star, WISE 0855),
    # shift the 3x3 measurement aperture dynamically to the target's true position
    # at the observation epoch of this specific cutout (c.mjd).
    target_pos = coord
    if pm_info and (pm_info.get("pmra_masyr") or pm_info.get("pmdec_masyr")):
        pmra = float(pm_info.get("pmra_masyr", 0.0))
        pmdec = float(pm_info.get("pmdec_masyr", 0.0))
        prop_from = float(pm_info.get("propagated_to", Time.now().decimalyear))
        cutout_yr = float(Time(c.mjd, format="mjd").decimalyear)
        target_pos = propagate(coord.ra.deg, coord.dec.deg, pmra, pmdec, prop_from, cutout_yr)

    x, y = c.wcs.world_to_pixel(target_pos)
    try:
        swcs = WCS(hdr, fobj=h, key="W")
        swcs.sip = None
        wl, _bw = swcs.pixel_to_world(x, y)
        c.wavelength_um = float(u.Quantity(wl).to(u.um).value)
    except Exception:
        c.wavelength_um = np.nan

    # 3x3 aperture centered on target -> spectral point
    xi, yi = int(round(float(x))), int(round(float(y)))
    ny, nx = c.image.shape
    if 1 <= xi < nx - 1 and 1 <= yi < ny - 1:
        ap = c.image[yi - 1:yi + 2, xi - 1:xi + 2]
        var = c.variance[yi - 1:yi + 2, xi - 1:xi + 2]
        c.center_flux = float(np.nanmean(ap))
        c.center_err = float(np.sqrt(np.nansum(var)) / 9)
    bad_pixels = (c.flags & BAD_PIXEL_MASK) != 0 if c.flags is not None else False
    c.flagged_frac = float(np.mean(bad_pixels))
    return c


def fetch_cutout(row, coord: SkyCoord, pm_info: dict | None = None) -> Cutout | None:
    mjd = float(row["mjd"])
    band = str(row["band"]).replace("SPHEREx-", "")
    url = str(row["uri"])
    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            with fits.open(url, cache=False, memmap=False) as h:
                return parse_cutout_hdul(h, mjd, band, coord, pm_info, url)
        except (TimeoutError, urllib.error.URLError, http.client.IncompleteRead,
                http.client.RemoteDisconnected, OSError) as e:
            if attempt == max_attempts - 1:
                print(f"  skipped ({band}): {e}")
                return None
            # Exponential backoff (~1.5s, 3s, 5.5s, 10s, 18s) with random jitter
            sleep_sec = min(30.0, (1.8 ** attempt) + np.random.uniform(0.5, 1.5))
            time.sleep(sleep_sec)
    return None


# --------------------------------------------------------------------------- image processing

def group_epochs(mjds: np.ndarray) -> np.ndarray:
    order = np.argsort(mjds)
    labels = np.zeros(len(mjds), dtype=int)
    ep = 0
    for i in range(1, len(order)):
        if mjds[order[i]] - mjds[order[i - 1]] > EPOCH_GAP_DAYS:
            ep += 1
        labels[order[i]] = ep
    return labels


def target_wcs(coord: SkyCoord, size_deg: float) -> tuple[WCS, tuple[int, int]]:
    n = int(np.ceil(size_deg * 3600 / PIXEL_SCALE_ARCSEC)) | 1  # odd -> centered pixel
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [coord.ra.deg, coord.dec.deg]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    w.wcs.cdelt = [-PIXEL_SCALE_ARCSEC / 3600, PIXEL_SCALE_ARCSEC / 3600]
    return w, (n, n)


def reproject_one(c: Cutout, w: WCS, shape, mask_flags: bool) -> np.ndarray:
    from reproject import reproject_interp
    data = c.image.copy()
    if mask_flags and c.flags is not None:
        data[(c.flags & BAD_PIXEL_MASK) != 0] = np.nan
    out, _ = reproject_interp((data, c.wcs), w, shape_out=shape, order="bilinear")
    return out


def suppress_stellar_glare(img: np.ndarray, sigma: float = 3.5) -> np.ndarray:
    """
    Spatial high-pass filter / unsharp masking to remove stellar diffraction halo.
    Essential for isolating the faint brown dwarf companion Epsilon Indi B from the bright primary star halo.
    """
    from scipy.ndimage import gaussian_filter
    clean = np.nan_to_num(img, nan=float(np.nanmedian(img)))
    smoothed = gaussian_filter(clean, sigma=sigma)
    return img - smoothed


def robust_norm(img: np.ndarray) -> np.ndarray:
    """Background subtraction + noise normalization (MAD) so detector bands can be combined."""
    med = np.nanmedian(img)
    mad = np.nanmedian(np.abs(img - med)) * 1.4826
    return (img - med) / (mad if mad > 0 else 1.0)


def repair_star_donuts(img: np.ndarray) -> np.ndarray:
    """
    Repairs stellar core saturation holes ('donuts'), NaN artifacts, and non-NaN flux dips.

    1. Saturated core reconstruction: identifies connected NaN components. Border/sky NaNs outside
       the field of view are filled with the median sky background, while enclosed saturated star
       cores are filled with the peak boundary flux (preventing dark center holes).
    2. Multi-threshold morphological hole filling: ensures any central crater, saturation
       wrap-around, or zeroed core enclosed within bright stellar contours is elevated to its
       enclosing contour level.
    """
    if img is None or img.size == 0:
        return img
    out = np.copy(img).astype(np.float64)

    # 1. Fill NaNs
    nan_mask = np.isnan(out)
    if np.any(nan_mask):
        valid = out[~nan_mask]
        if len(valid) == 0:
            return np.zeros_like(out)
        med_sky = float(np.median(valid))
        mad_sky = float(np.median(np.abs(valid - med_sky))) * 1.4826
        star_thresh = med_sky + 3.0 * (mad_sky if mad_sky > 0 else 1.0)
        img_max = float(np.max(valid))

        try:
            from scipy.ndimage import label, binary_dilation
            labeled_nans, num_nans = label(nan_mask, structure=np.ones((3, 3)))
            for i in range(1, num_nans + 1):
                comp = (labeled_nans == i)
                touches_edge = bool(comp[0, :].any() or comp[-1, :].any() or comp[:, 0].any() or comp[:, -1].any())
                dilated = binary_dilation(comp, structure=np.ones((3, 3)))
                boundary = dilated & (~nan_mask)
                bvals = out[boundary]
                if len(bvals) == 0:
                    out[comp] = med_sky
                    continue
                max_b = float(np.max(bvals))
                # Saturated stellar core: interior cutout region with elevated boundary,
                # or edge-touching source with high flux (> 50% of image peak)
                is_saturated_core = (not touches_edge and max_b > star_thresh) or (
                    touches_edge and max_b > 0.5 * img_max and max_b > star_thresh
                )
                if is_saturated_core:
                    out[comp] = max_b
                elif touches_edge:
                    out[comp] = med_sky
                else:
                    out[comp] = float(np.median(bvals))
        except Exception:
            # Fallback if scipy labeling fails
            out = np.nan_to_num(out, nan=med_sky)

    # 2. Multi-threshold morphological hole filling (fixes non-NaN craters / wrap-around / zeros)
    try:
        from scipy.ndimage import binary_fill_holes
        med = float(np.median(out))
        mad = float(np.median(np.abs(out - med))) * 1.4826
        vmax = float(np.max(out))
        low_t = med + 3.0 * (mad if mad > 0 else 1.0)
        if vmax > low_t:
            for t in np.linspace(low_t, vmax, 40):
                mask = out >= t
                if not np.any(mask):
                    continue
                holes = binary_fill_holes(mask) & (~mask)
                if np.any(holes):
                    out[holes] = t
    except Exception:
        pass

    return out


# Backward-compatible alias
inpaint_nans = repair_star_donuts


def stretch(img: np.ndarray, lo: float, hi: float, invert: bool = False, use_zscale: bool = False) -> np.ndarray:
    """
    Astronomical contrast stretch (asinh / ZScale) with optional negative-contrast mode.
    Applies repair_star_donuts so saturated pixels and craters do not render as dark/black center holes.
    """
    clean = repair_star_donuts(img)
    if use_zscale:
        try:
            from astropy.visualization import ZScaleInterval
            lo, hi = ZScaleInterval().get_limits(clean)
        except Exception:
            pass
    x = np.clip((clean - lo) / (hi - lo + 1e-12), 0, 1)
    x = np.arcsinh(10 * x) / np.arcsinh(10)
    x = np.nan_to_num(x, nan=0.0)
    arr = (x * 255).astype(np.uint8)
    if invert:
        arr = 255 - arr
    return arr


def to_png(arr8: np.ndarray, path: Path, scale: int, text: str | None = None,
           gaia_pix: tuple[float, float] | None = None):
    """Saves 8-bit array as PNG with center reticle crosshair and optional Gaia marker."""
    from PIL import Image, ImageDraw
    im = Image.fromarray(np.flipud(arr8), mode="L")  # North up
    im = im.resize((arr8.shape[1] * scale, arr8.shape[0] * scale), Image.NEAREST).convert("RGB")
    d = ImageDraw.Draw(im)
    if text:
        d.rectangle([0, 0, im.width, 16], fill=(0, 0, 0))
        d.text((4, 2), text, fill=(255, 255, 255))
    
    # Center reticle crosshair (red)
    cx, cy, g = im.width // 2, im.height // 2, 6 * scale
    for a, b in (((cx - 2 * g, cy), (cx - g, cy)), ((cx + g, cy), (cx + 2 * g, cy)),
                 ((cx, cy - 2 * g), (cx, cy - g)), ((cx, cy + g), (cx, cy + 2 * g))):
        d.line([a, b], fill=(255, 60, 60), width=1)
    
    # Gaia DR3 predicted position (green circle / reticle)
    if gaia_pix:
        gx, gy = gaia_pix
        gx_img = int(gx * scale)
        gy_img = int(im.height - gy * scale)
        r = 6
        d.ellipse([gx_img - r, gy_img - r, gx_img + r, gy_img + r], outline=(50, 230, 50), width=1)

    im.save(path)
    return im


def diff_png(a: np.ndarray, b: np.ndarray, path: Path, scale: int, text: str):
    """Computes and saves difference image (Delta I = b - a) with donut artifact protection."""
    clean_a = repair_star_donuts(a)
    clean_b = repair_star_donuts(b)
    d = clean_b - clean_a
    lim = np.nanpercentile(np.abs(d), 99.5) or 1.0
    arr = np.nan_to_num(np.clip((d / lim + 1) / 2, 0, 1) * 255, nan=127).astype(np.uint8)
    to_png(arr, path, scale, text)


# --------------------------------------------------------------------------- main pipeline

def select_per_group(tab, n: int):
    """Selects max n images per (epoch, detector) uniformly sampled across time -> fast preview."""
    if not n:
        return tab
    mjds = np.array(tab["mjd"], dtype=float)
    eps = group_epochs(mjds)
    bands = np.array([str(b) for b in tab["band"]])
    keep = []
    for e in np.unique(eps):
        for b in np.unique(bands):
            idx = np.where((eps == e) & (bands == b))[0]
            if len(idx):
                keep.extend(idx[np.linspace(0, len(idx) - 1, min(n, len(idx))).astype(int)])
    return tab[sorted(set(int(i) for i in keep))]


def run(coord: SkyCoord, label: str, slug: str, args, extra: dict,
        progress=None, cutouts: list[Cutout] | None = None):
    """
    Main processing pipeline.
    progress(done, total, stage) is called during downloading (used by backend).
    If cutouts=None, images are queried and downloaded from IRSA TAP.
    If cutouts=[...], bypasses query_images + fetch_cutout and processes directly (e.g. AWS S3 downloads).
    """
    print(f"\n== {label}  RA={coord.ra.deg:.6f}  Dec={coord.dec.deg:.6f}")
    out = Path(args.out) / slug
    (out / "frames").mkdir(parents=True, exist_ok=True)
    size_deg = args.size / 60.0

    # Robustly identify benchmark target (by name, slug, or coordinates)
    matched_target = get_target_key(coord, slug)
    is_epsindib = (matched_target == "epsindib") or getattr(args, "glare_suppress", False)
    is_wise0855 = (matched_target == "wise0855")

    # Ensure proper motion info is present for aperture tracking
    pm_info = dict(extra) if extra else {}
    if ("pmra_masyr" not in pm_info or not pm_info.get("pmra_masyr")) and matched_target in TARGETS:
        t = TARGETS[matched_target]
        fb_pmra = t["fallback"][2]
        fb_pmdec = t["fallback"][3]
        if fb_pmra or fb_pmdec:
            pm_info["pmra_masyr"] = fb_pmra
            pm_info["pmdec_masyr"] = fb_pmdec
            pm_info["propagated_to"] = round(Time.now().decimalyear, 3)
    extra = {**pm_info, **extra}

    if cutouts is None:
        tab = query_images(coord, size_deg, args.bands)
        if len(tab) == 0:
            print("  No SPHEREx images cover this position.")
            raise LookupError("No SPHEREx images cover this position")
        tab = select_per_group(tab, getattr(args, "per_group", 0))
        if args.max and len(tab) > args.max:
            idx = np.linspace(0, len(tab) - 1, args.max).astype(int)
            tab = tab[idx]
            print(f"  Limited to {args.max} images (--max)")

        t0 = time.time()
        total = len(tab)
        if progress:
            progress(0, total, "downloading")
        cutouts = []
        n_workers = min(int(getattr(args, "workers", 6) or 6), 6)
        with cf.ThreadPoolExecutor(max_workers=n_workers) as ex:
            futs = [ex.submit(fetch_cutout, r, coord, pm_info) for r in tab]
            for i, f in enumerate(cf.as_completed(futs), 1):
                c = f.result()
                if c is not None:
                    cutouts.append(c)
                if progress:
                    progress(i, total, "downloading")
        print(f"  Downloaded {len(cutouts)}/{len(tab)} cutouts ({time.time() - t0:.0f} s)")
    else:
        print(f"  Using {len(cutouts)} preloaded cutouts directly (e.g. S3 fetch)")

    if not cutouts:
        raise RuntimeError("No cutouts provided or all cutout downloads failed")
    if progress:
        progress(len(cutouts), len(cutouts), "processing")

    mjds = np.array([c.mjd for c in cutouts])
    ep_labels = group_epochs(mjds)
    n_ep = ep_labels.max() + 1
    w, shape = target_wcs(coord, size_deg)

    # Stacking: epoch x detector -> median
    stacks: dict[tuple[int, str], np.ndarray] = {}
    epochs_meta = []
    for e in range(n_ep):
        sel = [c for c, l in zip(cutouts, ep_labels) if l == e]
        em = {"index": e, "mjd_mean": float(np.mean([c.mjd for c in sel])),
              "n_images": len(sel), "detectors": {}}
        em["date"] = Time(em["mjd_mean"], format="mjd").iso[:10]
        for b in args.bands:
            imgs = [reproject_one(c, w, shape, args.mask_flags) for c in sel if c.band == b]
            if not imgs:
                continue
            
            # Epsilon Indi B special processing: suppress primary star halo
            if is_epsindib:
                imgs = [suppress_stellar_glare(im) for im in imgs]

            st = np.nanmedian(np.stack(imgs), axis=0)
            stacks[(e, b)] = st
            em["detectors"][b] = {"n_images": len(imgs),
                                  "flagged_frac": float(np.mean([c.flagged_frac for c in sel if c.band == b]))}
            fits.PrimaryHDU(st.astype(np.float32), header=w.to_header()).writeto(
                out / f"epoch{e}_{b}.fits", overwrite=True)
        
        # Combine all detectors (S/N-weighted, preserving NaNs where no detector has valid data)
        per = [robust_norm(stacks[(e, b)]) for b in args.bands if (e, b) in stacks]
        if per:
            per_arr = np.array(per)
            valid_mask = ~np.isnan(per_arr)
            n_valid = np.sum(valid_mask, axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                all_band = np.nansum(per_arr, axis=0) / np.sqrt(np.maximum(n_valid, 1))
                all_band[n_valid == 0] = np.nan
            stacks[(e, "ALL")] = all_band
            fits.PrimaryHDU(stacks[(e, "ALL")].astype(np.float32), header=w.to_header()).writeto(
                out / f"epoch{e}_ALL.fits", overwrite=True)
        epochs_meta.append(em)

    # Validate Gaia DR3 position and compute pixel coordinates
    gaia_meta = None
    gaia_pix = None
    target_year = float(Time(epochs_meta[-1]["mjd_mean"], format="mjd").decimalyear)
    skip_gaia = bool(getattr(args, "skip_gaia", False))
    gaia_timeout = float(getattr(args, "gaia_timeout", 10.0) or 10.0)

    if skip_gaia:
        gaia_meta = {
            "status": "SKIPPED",
            "message": "Gaia DR3 validation skipped.",
            "is_match": False
        }
    elif validate_gaia:
        try:
            gaia_meta = validate_gaia(coord, target_key=matched_target, target_epoch=target_year, timeout=gaia_timeout)
            pred_ra = gaia_meta.get("predicted_ra") if gaia_meta else None
            pred_dec = gaia_meta.get("predicted_dec") if gaia_meta else None
            if (pred_ra is not None and pred_dec is not None and
                    np.isfinite(pred_ra) and np.isfinite(pred_dec)):
                c_gaia_pred = SkyCoord(pred_ra * u.deg, pred_dec * u.deg, frame="icrs")
                gx, gy = w.world_to_pixel(c_gaia_pred)
                if np.isfinite(gx) and np.isfinite(gy) and 0 <= gx < shape[1] and 0 <= gy < shape[0]:
                    gaia_pix = (float(gx), float(gy))
                    gaia_meta["pixel_coords"] = {
                        "canvas_x": round(float(gx), 2),
                        "canvas_y": round(float(shape[0] - 1 - gy), 2),
                        "wcs_x": round(float(gx), 2),
                        "wcs_y": round(float(gy), 2)
                    }
        except Exception as e:
            print(f"  Gaia validation skipped: {e}")

    # PNG frames, GIF and difference image per detector, common stretch across all epochs
    scale = max(1, 400 // shape[0])
    outputs = {}
    use_invert = getattr(args, "invert", False) or is_wise0855

    for b in list(args.bands) + ["ALL"]:
        ims = [(e, stacks[(e, b)]) for e in range(n_ep) if (e, b) in stacks]
        if not ims:
            continue
        allpix = np.concatenate([i.ravel() for _, i in ims])
        lo, hi = np.nanpercentile(allpix, args.lo), np.nanpercentile(allpix, args.hi)
        (out / "frames" / b).mkdir(exist_ok=True)
        pil = []
        for e, img in ims:
            p = out / "frames" / b / f"epoch{e}.png"
            # Render Gaia marker only if explicitly requested as baked-in (default: clean image, viewer renders dynamic overlay)
            cur_gaia_pix = gaia_pix if (e == ims[-1][0] and getattr(args, "show_gaia", False)) else None
            pil.append(to_png(stretch(img, lo, hi, invert=use_invert), p, scale,
                              f"{label} {b}  {epochs_meta[e]['date']}", gaia_pix=cur_gaia_pix))
        files = {
            "frames": [f"frames/{b}/epoch{e}.png" for e, _ in ims],
            "fits": [f"epoch{e}_{b}.fits" for e in range(n_ep) if (e, b) in stacks]
        }
        if len(pil) > 1:
            pil[0].save(out / f"blink_{b}.gif", save_all=True, append_images=pil[1:],
                        duration=args.frame_ms, loop=0)
            diff_png(ims[0][1], ims[-1][1], out / f"diff_{b}.png", scale,
                     f"{b}: {epochs_meta[ims[-1][0]]['date']} - {epochs_meta[ims[0][0]]['date']}")
            files["gif"] = f"blink_{b}.gif"
            files["diff"] = f"diff_{b}.png"
        outputs[b] = files

    # Spectrum at target position
    with open(out / "spectrum.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["mjd", "epoch", "detector", "wavelength_um", "flux_mjy_sr", "err_mjy_sr", "flagged_frac"])
        for c, l in sorted(zip(cutouts, ep_labels), key=lambda t: (t[1], t[0].wavelength_um)):
            wr.writerow([f"{c.mjd:.5f}", l, c.band, f"{c.wavelength_um:.4f}",
                         f"{c.center_flux:.5g}", f"{c.center_err:.3g}", f"{c.flagged_frac:.3f}"])
    plot_spectrum(cutouts, ep_labels, epochs_meta, out / "spectrum.png", label)

    # Band-specific light curve and variability analysis at target position
    lightcurve_info = plot_lightcurve(cutouts, ep_labels, epochs_meta, out / "lightcurve.png", label)
    with open(out / "lightcurve.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["epoch", "date", "mjd", "band", "flux_mjy_sr", "err_mjy_sr"])
        for pt in lightcurve_info.get("points", []):
            wr.writerow([pt["epoch"], pt["date"], pt["mjd"], pt["band"], pt["flux"], pt["err"]])

    meta = {
        "target": label, "ra_deg": coord.ra.deg, "dec_deg": coord.dec.deg,
        "fov_arcmin": args.size, "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
        "shape": list(shape), "bands": args.bands, "detector_ranges_um": DETECTORS,
        "inverted": bool(use_invert),
        "epochs": epochs_meta, "outputs": outputs, "spectrum": "spectrum.csv",
        "lightcurve": "lightcurve.csv",
        "lightcurve_png": "lightcurve.png",
        "light_curve": lightcurve_info,
        "gaia_validation": gaia_meta,
        "versions": sorted({c.version for c in cutouts if c.version}),
        "generated": Time.now().iso, **extra,
        "credit": "NASA/IPAC Infrared Science Archive (IRSA), SPHEREx Team",
    }
    clean_meta = sanitize_for_json(meta)
    (out / "meta.json").write_text(json.dumps(clean_meta, indent=2))
    print(f"  {n_ep} epochs -> {out}/")
    return out


def plot_spectrum(cutouts, ep_labels, epochs_meta, path: Path, label: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for e, em in enumerate(epochs_meta):
        pts = sorted((c.wavelength_um, c.center_flux, c.center_err)
                     for c, l in zip(cutouts, ep_labels) if l == e and np.isfinite(c.center_flux))
        if pts:
            wl, fl, er = map(np.array, zip(*pts))
            ax.errorbar(wl, fl, yerr=er, fmt=".", ms=4, alpha=.8, label=em["date"])
    ax.set_xlabel("Wavelength (µm)")
    ax.set_ylabel("Surface Brightness (MJy/sr, zodi subtracted)")
    ax.set_title(f"{label} – SPHEREx Spectrum per Epoch")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_lightcurve(cutouts, ep_labels, epochs_meta, path: Path, label: str) -> dict:
    """
    Computes light curves separately for each detector band (D1–D6).
    Prevents false flux variability caused by mixing detector bands
    across epochs with different band coverage.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bands_data: dict[str, list[dict]] = {}
    for b in DETECTORS:
        band_pts = []
        for e, em in enumerate(epochs_meta):
            sel = [c for c, l in zip(cutouts, ep_labels) if l == e and c.band == b and np.isfinite(c.center_flux)]
            if sel:
                mjd_b = float(np.mean([c.mjd for c in sel]))
                flux_b = float(np.mean([c.center_flux for c in sel]))
                err_b = float(np.sqrt(np.sum([c.center_err**2 for c in sel])) / len(sel))
                band_pts.append({
                    "epoch": e,
                    "date": em["date"],
                    "mjd": round(mjd_b, 2),
                    "flux": round(flux_b, 4),
                    "err": round(err_b, 4)
                })
        if band_pts:
            bands_data[b] = band_pts

    if not bands_data:
        return {"is_variable": False, "variable_bands": [], "bands": {}, "points": []}

    # Variability analysis per detector band
    bands_summary = {}
    variable_bands = []
    for b, pts in bands_data.items():
        fluxes = np.array([p["flux"] for p in pts])
        errs = np.array([p["err"] for p in pts])
        mean_f = float(np.mean(fluxes))
        std_f = float(np.std(fluxes)) if len(fluxes) > 1 else 0.0
        amplitude = float(np.max(fluxes) - np.min(fluxes)) if len(fluxes) > 1 else 0.0
        
        # Genuine variability within the same detector band
        is_var = bool(len(fluxes) >= 2 and (std_f / max(1e-4, abs(mean_f)) > 0.15) and (amplitude > 2.5 * np.mean(errs)))
        if is_var:
            variable_bands.append(b)

        bands_summary[b] = {
            "is_variable": is_var,
            "mean_flux": round(mean_f, 3),
            "std_flux": round(std_f, 3),
            "amplitude_flux": round(amplitude, 3),
            "wavelength_range_um": DETECTORS[b],
            "epochs": pts
        }

    is_target_variable = len(variable_bands) > 0

    # Multiband light curve plot
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    for b, pts in bands_data.items():
        mjds = [p["mjd"] for p in pts]
        fluxes = [p["flux"] for p in pts]
        errs = [p["err"] for p in pts]
        color = BAND_COLORS.get(b, "#888888")
        rng = DETECTORS[b]
        var_tag = " [Variable]" if b in variable_bands else ""
        lbl = f"{b} ({rng[0]}–{rng[1]} µm){var_tag}"
        ax.errorbar(mjds, fluxes, yerr=errs, fmt="o-", color=color, ecolor=color,
                    capsize=3, lw=1.5, ms=5, label=lbl, alpha=0.9)

    ax.set_xlabel("MJD (Modified Julian Date)")
    ax.set_ylabel("Flux Density (MJy/sr)")
    status_str = f"VARIABLE ({', '.join(variable_bands)})" if is_target_variable else "STABLE"
    ax.set_title(f"{label} – Light Curve per Band [{status_str}]")
    ax.legend(fontsize=7.5, loc="best", ncol=2)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)

    all_points = []
    for b, pts in bands_data.items():
        for p in pts:
            all_points.append({
                "epoch": p["epoch"],
                "date": p["date"],
                "mjd": p["mjd"],
                "band": b,
                "flux": p["flux"],
                "err": p["err"]
            })
    all_points.sort(key=lambda x: (x["epoch"], x["band"]))

    return {
        "is_variable": is_target_variable,
        "variable_bands": variable_bands,
        "bands": bands_summary,
        "points": all_points
    }


def main():
    p = argparse.ArgumentParser(description="SPHEREx time-series pipeline for a given sky position")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", choices=TARGETS.keys(), help="Challenge benchmark target")
    g.add_argument("--all-targets", action="store_true", help="Process all 5 benchmark targets")
    g.add_argument("--name", help="Any Simbad-resolvable target name")
    g.add_argument("--ra", help="Right Ascension in degrees or sexagesimal (e.g. 08h55m10.8s)")
    p.add_argument("--dec", help="Declination in degrees or sexagesimal (e.g. -7d14m42s)")
    p.add_argument("--size", type=float, default=3.0, help="Field of view in arcmin (default: 3)")
    p.add_argument("--bands", nargs="+", default=list(DETECTORS), choices=list(DETECTORS))
    p.add_argument("--max", type=int, default=0, help="Max images to download (0 = all)")
    p.add_argument("--per-group", type=int, default=0,
                   help="Max images per epoch+band (e.g. 3 = fast preview, 0 = all)")
    p.add_argument("--workers", type=int, default=6, help="Concurrent download threads (default: 6)")
    p.add_argument("--mask-flags", action="store_true", help="Mask flagged bad pixels")
    p.add_argument("--lo", type=float, default=1.0, help="Lower percentile for stretch (default: 1.0)")
    p.add_argument("--hi", type=float, default=99.7, help="Upper percentile for stretch (default: 99.7)")
    p.add_argument("--frame-ms", type=int, default=600, help="Frame duration in ms for blink GIF (default: 600)")
    p.add_argument("--invert", action="store_true", help="Invert colors (negative contrast)")
    p.add_argument("--show-gaia", action="store_true", default=False,
                   help="Bake Gaia DR3 position marker into PNG frames (default: False, viewer renders dynamic overlay)")
    p.add_argument("--skip-gaia", action="store_true", default=False,
                   help="Skip Gaia DR3 astrometric validation (e.g. for quick preview)")
    p.add_argument("--gaia-timeout", type=float, default=10.0,
                   help="Timeout in seconds for Gaia DR3 query (default: 10.0)")
    p.add_argument("--out", default="output")
    args = p.parse_args()

    if args.ra is not None:
        if args.dec is None:
            p.error("--ra requires --dec")
        c = parse_coord(args.ra, args.dec)
        run(c, f"RA{c.ra.deg:.4f} Dec{c.dec.deg:+.4f}",
            f"ra{c.ra.deg:.4f}_dec{c.dec.deg:+.4f}", args, {})
    elif args.name:
        c, label, info = target_coord(args.name)
        run(c, label, args.name.lower().replace(" ", "_"), args, info)
    else:
        keys = list(TARGETS) if args.all_targets else [args.target]
        for k in keys:
            c, label, info = target_coord(k)
            run(c, label, k, args, info)


if __name__ == "__main__":
    main()
