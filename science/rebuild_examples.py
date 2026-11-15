#!/usr/bin/env python3
"""
rebuild_examples.py - Rebuild pre-computed examples from existing epoch stacks.
AI-assisted: written with Claude / Antigravity (Google DeepMind).

Use when IRSA TAP/SIA is down:
1. Donut repair: eliminates saturated black cores and non-NaN craters from all PNGs, GIFs, and diffs.
2. Accurate Gaia DR3 astrometry: updates J2016-to-epoch propagation, source_id, and pixel_coords.
3. Inverted contrast: sets "inverted": true in meta.json and renders inverted stretch for WISE 0855.
4. Multi-layer pixel cubes: creates pixels/{band}/epoch{e}.fits (SB, ZODI, SNR, WAVE, BW, DETX, DETY).
5. R Dra notice: notes that R Dra's cutouts must be re-fetched when IRSA is back online.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

ROOT = Path(__file__).resolve().parent.parent
SCIENCE_DIR = ROOT / "science"
if str(SCIENCE_DIR) not in sys.path:
    sys.path.insert(0, str(SCIENCE_DIR))

import fetch_spherex as fs
from gaia_validation import validate_gaia


def rebuild_target(target_dir: Path):
    meta_file = target_dir / "meta.json"
    if not meta_file.exists():
        print(f"Skipping {target_dir}: no meta.json found")
        return

    meta = json.loads(meta_file.read_text())
    slug = target_dir.name
    label = meta.get("target", slug)
    print(f"\n== Rebuilding {label} ({slug}) in {target_dir}")

    coord = SkyCoord(meta["ra_deg"] * u.deg, meta["dec_deg"] * u.deg, frame="icrs")
    shape = tuple(meta.get("shape", [31, 31]))
    scale = max(1, 400 // shape[0])

    is_wise0855 = (slug == "wise0855")
    is_epsindib = (slug == "epsindib")
    is_rdra = (slug == "rdra")
    use_invert = is_wise0855
    meta["inverted"] = bool(use_invert)

    # 1. Discover target WCS from existing stacks
    w = None
    stack_files = list(target_dir.glob("epoch*.fits"))
    for f in stack_files:
        try:
            with fits.open(f) as h:
                w = WCS(h[0].header)
                break
        except Exception:
            continue
    if w is None:
        w, _ = fs.target_wcs(coord, meta.get("fov_arcmin", 3.0) / 60.0)

    # 2. Load existing stacks
    epochs_meta = meta.get("epochs", [])
    bands = meta.get("bands", list(fs.DETECTORS))
    n_ep = len(epochs_meta)
    stacks: dict[tuple[int, str], np.ndarray] = {}

    for e in range(n_ep):
        for b in bands:
            f_path = target_dir / f"epoch{e}_{b}.fits"
            if f_path.exists():
                try:
                    with fits.open(f_path) as h:
                        st = h[0].data.astype(np.float32)
                        stacks[(e, b)] = st
                except Exception as ex:
                    print(f"  Warning: could not read {f_path}: {ex}")

        # Combined ALL stack if present
        all_path = target_dir / f"epoch{e}_ALL.fits"
        if all_path.exists():
            try:
                with fits.open(all_path) as h:
                    stacks[(e, "ALL")] = h[0].data.astype(np.float32)
            except Exception:
                pass
        elif any((e, b) in stacks for b in bands):
            # Compute ALL stack if missing
            per = [fs.robust_norm(stacks[(e, b)]) for b in bands if (e, b) in stacks]
            if per:
                per_arr = np.array(per)
                valid_mask = ~np.isnan(per_arr)
                n_valid = np.sum(valid_mask, axis=0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    all_band = np.nansum(per_arr, axis=0) / np.sqrt(np.maximum(n_valid, 1))
                    all_band[n_valid == 0] = np.nan
                stacks[(e, "ALL")] = all_band
                fits.PrimaryHDU(all_band.astype(np.float32), header=w.to_header()).writeto(
                    target_dir / f"epoch{e}_ALL.fits", overwrite=True
                )

    # 3. Update Gaia DR3 validation and pixel coordinates
    gaia_meta = None
    gaia_pix = None
    if epochs_meta:
        target_year = float(Time(epochs_meta[-1]["mjd_mean"], format="mjd").decimalyear)
        try:
            gaia_meta = validate_gaia(coord, target_key=slug, target_epoch=target_year, timeout=10.0)
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
            meta["gaia_validation"] = gaia_meta
            print(f"  ✓ Gaia DR3 updated: status={gaia_meta.get('status')} residual={gaia_meta.get('residual_offset_arcsec')}\"")
        except Exception as ex:
            print(f"  Gaia validation skipped: {ex}")

    # 4. Re-render PNG frames, GIFs and diff images with Donut Repair
    outputs = meta.get("outputs", {})
    all_bands_to_process = [b for b in bands if any((e, b) in stacks for e in range(n_ep))]
    if any((e, "ALL") in stacks for e in range(n_ep)):
        all_bands_to_process.append("ALL")

    n_pixels_created = 0
    for b in all_bands_to_process:
        ims = [(e, stacks[(e, b)]) for e in range(n_ep) if (e, b) in stacks]
        if not ims:
            continue

        allpix = np.concatenate([i.ravel() for _, i in ims])
        lo, hi = np.nanpercentile(allpix, 1.0), np.nanpercentile(allpix, 99.7)
        (target_dir / "frames" / b).mkdir(parents=True, exist_ok=True)
        pil = []
        for e, img in ims:
            p = target_dir / "frames" / b / f"epoch{e}.png"
            date_str = epochs_meta[e]["date"] if e < len(epochs_meta) else ""
            pil.append(fs.to_png(fs.stretch(img, lo, hi, invert=use_invert), p, scale,
                                 f"{label} {b}  {date_str}", gaia_pix=None))

        files = {
            "frames": [f"frames/{b}/epoch{e}.png" for e, _ in ims],
            "fits": [f"epoch{e}_{b}.fits" for e in range(n_ep) if (e, b) in stacks]
        }

        # Multi-layer pixel cubes for detector bands D1-D6
        if b in bands:
            pixel_files = []
            for e in range(n_ep):
                if (e, b) not in stacks:
                    continue
                p_file = target_dir / "pixels" / b / f"epoch{e}.fits"
                mjd = epochs_meta[e]["mjd_mean"] if e < len(epochs_meta) else 60000.0
                c = fs.Cutout(
                    mjd=mjd, band=b, image=stacks[(e, b)], wcs=w,
                    x0=1005.0, y0=1005.0, wavelength_um=float(np.mean(fs.DETECTORS[b]))
                )
                fs.build_pixel_cube(p_file, stacks[(e, b)], [c], w, shape, b)
                pixel_files.append(f"pixels/{b}/epoch{e}.fits")
                n_pixels_created += 1
            files["pixels"] = pixel_files

        if len(pil) > 1:
            pil[0].save(target_dir / f"blink_{b}.gif", save_all=True, append_images=pil[1:],
                        duration=600, loop=0)
            date_first = epochs_meta[ims[0][0]]["date"] if ims[0][0] < len(epochs_meta) else "E0"
            date_last = epochs_meta[ims[-1][0]]["date"] if ims[-1][0] < len(epochs_meta) else "E1"
            fs.diff_png(ims[0][1], ims[-1][1], target_dir / f"diff_{b}.png", scale,
                        f"{b}: {date_last} - {date_first}")
            files["gif"] = f"blink_{b}.gif"
            files["diff"] = f"diff_{b}.png"

        outputs[b] = files

    meta["outputs"] = outputs
    clean_meta = fs.sanitize_for_json(meta)
    meta_file.write_text(json.dumps(clean_meta, indent=2))
    print(f"  ✓ Rebuilt {len(all_bands_to_process)} bands, {n_pixels_created} pixel cubes, updated meta.json")

    if is_rdra:
        print("  ⚠️  HUOM (R Dra): Kuvat ja pikselit päivitetty olemassa olevista pinoista,")
        print("      mutta vanhat leikkaukset oli rajattu pre-J2000 koordinaateilla.")
        print("      Kun IRSA palaa, aja täysi haku:")
        print("      python science/fetch_spherex.py --target rdra --out examples")


def main():
    parser = argparse.ArgumentParser(description="Rebuild examples from existing epoch stacks")
    parser.add_argument("--dir", default="examples", help="Directory containing target folders (default: examples)")
    parser.add_argument("--targets", nargs="*", help="Specific target slugs to rebuild (default: all in dir)")
    args = parser.parse_args()

    base_dir = Path(args.dir)
    if not base_dir.exists():
        sys.exit(f"Directory {base_dir} does not exist")

    target_dirs = []
    if args.targets:
        for t in args.targets:
            td = base_dir / t
            if td.is_dir():
                target_dirs.append(td)
            else:
                print(f"Target folder {td} not found")
    else:
        for p in sorted(base_dir.iterdir()):
            if p.is_dir() and (p / "meta.json").exists():
                target_dirs.append(p)

    print(f"Rebuilding {len(target_dirs)} target folders in {base_dir}...")
    for td in target_dirs:
        rebuild_target(td)
    print("\n✓ All target examples successfully rebuilt!")


if __name__ == "__main__":
    main()
