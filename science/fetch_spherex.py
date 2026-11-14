#!/usr/bin/env python3
"""
fetch_spherex.py - hakee SPHEREx-cutoutit annetulle taivaan kohdalle ja tekee niistä
aikasarjan (epookit), blink-GIFin, erotuskuvan ja spektrin.

Esimerkit:
    python fetch_spherex.py --target wise0855
    python fetch_spherex.py --all-targets
    python fetch_spherex.py --ra 133.795 --dec -7.245 --size 3
    python fetch_spherex.py --ra "08h55m10.831s" --dec "-7d14m42.53s" --bands D1 D2
    python fetch_spherex.py --name "RW Aur"

Data: NASA/IPAC IRSA, SPHEREx (TAP-taulut spherex.artifact + spherex.plane, cutout-palvelu).
AI-assisted: written with Claude (Anthropic).
Pohjana IRSA:n SPHEREx-tutoriaalit (BSD-3-Clause, Caltech-IPAC).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import http.client
import json
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

warnings.filterwarnings("ignore", category=FITSFixedWarning)
data_conf.remote_timeout = 90

PIXEL_SCALE_ARCSEC = 6.15  # SPHEREx-pikselikoko

# Ilmaisimet ja niiden aallonpituusalueet (µm)
DETECTORS = {
    "D1": (0.75, 1.09),
    "D2": (1.10, 1.62),
    "D3": (1.63, 2.41),
    "D4": (2.42, 3.82),
    "D5": (3.83, 4.41),
    "D6": (4.42, 5.00),
}

# Haasteen testikohteet. Simbad-nimellä haetaan sijainti + ominaisliike (J2000),
# fallback-koordinaatit käytetään jos Simbad ei vastaa.
TARGETS = {
    "barnard":  {"simbad": "GJ 699", "label": "Barnard's Star",
                 "fallback": (269.452083, 4.693364, -801.551, 10362.394)},
    "epsindib": {"simbad": "eps Ind B", "label": "Epsilon Indi B",
                 "fallback": (331.0438, -56.7827, 3966.7, -2536.2)},
    "wise0855": {"simbad": "WISE J085510.83-071442.5", "label": "WISE 0855-0714",
                 # Haasteen antamat koordinaatit, ominaisliike n. -8.1"/v, +0.7"/v
                 "fallback": (133.795129, -7.245147, -8118.0, 673.0), "fallback_epoch": 2014.4},
    "rwaur":    {"simbad": "RW Aur", "label": "RW Aurigae",
                 "fallback": (76.956250, 30.401111, 0.0, 0.0)},
    "rdra":     {"simbad": "R Dra", "label": "R Draconis",
                 "fallback": (246.661250, 66.752222, 0.0, 0.0)},
}

EPOCH_GAP_DAYS = 30  # yli tämän aukko havainnoissa = uusi epookki


# --------------------------------------------------------------------------- koordinaatit

def parse_coord(ra: str, dec: str) -> SkyCoord:
    try:
        return SkyCoord(float(ra) * u.deg, float(dec) * u.deg, frame="icrs")
    except ValueError:
        return SkyCoord(ra, dec, frame="icrs")


def propagate(ra, dec, pmra_masyr, pmdec_masyr, epoch_from: float, epoch_to: float) -> SkyCoord:
    """Lineaarinen ominaisliike (riittää muutaman arcminin cutouteille)."""
    dt = epoch_to - epoch_from
    dec2 = dec + pmdec_masyr * dt / 3.6e6
    ra2 = ra + pmra_masyr * dt / 3.6e6 / np.cos(np.radians(dec))
    return SkyCoord(ra2 * u.deg, dec2 * u.deg, frame="icrs")


def resolve_name(name: str):
    """Palauttaa (ra, dec, pmra, pmdec) J2000 Simbadista. None jos ei onnistu."""
    try:
        from astroquery.simbad import Simbad
        s = Simbad()
        s.add_votable_fields("pmra", "pmdec")
        r = s.query_object(name)
        if r is None or len(r) == 0:
            return None
        cols = {c.lower(): c for c in r.colnames}
        ra_v, dec_v = r[cols["ra"]][0], r[cols["dec"]][0]
        if isinstance(ra_v, str):  # vanha astroquery: sexagesimaali
            c = SkyCoord(ra_v, dec_v, unit=(u.hourangle, u.deg))
            ra_v, dec_v = c.ra.deg, c.dec.deg
        pmra = float(r[cols["pmra"]][0]) if "pmra" in cols and not np.ma.is_masked(r[cols["pmra"]][0]) else 0.0
        pmdec = float(r[cols["pmdec"]][0]) if "pmdec" in cols and not np.ma.is_masked(r[cols["pmdec"]][0]) else 0.0
        return float(ra_v), float(dec_v), pmra, pmdec
    except Exception as e:  # noqa: BLE001
        print(f"  Simbad-haku epäonnistui ({name}): {e}")
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
            sys.exit(f"Kohdetta ei löytynyt: {key_or_name}")
        ra, dec, pmra, pmdec = res
        epoch0, label = 2000.0, key_or_name
    c = propagate(ra, dec, pmra, pmdec, epoch0, now)
    info = {"pmra_masyr": pmra, "pmdec_masyr": pmdec, "propagated_to": round(now, 3)}
    return c, label, info


# --------------------------------------------------------------------------- haku

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
    print(f"  TAP: {len(tab)} kuvaa ({time.time() - t0:.1f} s)")
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


def fetch_cutout(row, coord: SkyCoord) -> Cutout | None:
    c = Cutout(mjd=float(row["mjd"]), band=str(row["band"]).replace("SPHEREx-", ""), url=str(row["uri"]))
    for attempt in range(3):
        try:
            with fits.open(c.url, cache=False, memmap=False) as h:
                img = h["IMAGE"].data.astype(np.float32)
                zodi = h["ZODI"].data.astype(np.float32) if "ZODI" in h else 0.0
                c.image = img - zodi
                c.flags = h["FLAGS"].data
                c.variance = h["VARIANCE"].data.astype(np.float32)
                hdr = h["IMAGE"].header
                c.wcs = WCS(hdr)
                c.version = str(h[0].header.get("VERSION", ""))
                x, y = c.wcs.world_to_pixel(coord)
                swcs = WCS(hdr, fobj=h, key="W")
                swcs.sip = None
                wl, _bw = swcs.pixel_to_world(x, y)
                c.wavelength_um = float(u.Quantity(wl).to(u.um).value)
            # 3x3 apertuuri kohteen kohdalla -> spektripiste
            xi, yi = int(round(float(x))), int(round(float(y)))
            ny, nx = c.image.shape
            if 1 <= xi < nx - 1 and 1 <= yi < ny - 1:
                ap = c.image[yi - 1:yi + 2, xi - 1:xi + 2]
                var = c.variance[yi - 1:yi + 2, xi - 1:xi + 2]
                c.center_flux = float(np.nanmean(ap))
                c.center_err = float(np.sqrt(np.nansum(var)) / 9)
            c.flagged_frac = float(np.mean(c.flags != 0))
            return c
        except (TimeoutError, urllib.error.URLError, http.client.IncompleteRead,
                http.client.RemoteDisconnected, OSError) as e:
            if attempt == 2:
                print(f"  ohitettu: {e}")
                return None
            time.sleep(2 * (attempt + 1))
    return None


# --------------------------------------------------------------------------- käsittely

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
    n = int(np.ceil(size_deg * 3600 / PIXEL_SCALE_ARCSEC)) | 1  # pariton -> keskipikseli
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [coord.ra.deg, coord.dec.deg]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    w.wcs.cdelt = [-PIXEL_SCALE_ARCSEC / 3600, PIXEL_SCALE_ARCSEC / 3600]
    return w, (n, n)


def reproject_one(c: Cutout, w: WCS, shape, mask_flags: bool) -> np.ndarray:
    from reproject import reproject_interp
    data = c.image.copy()
    if mask_flags:
        data[c.flags != 0] = np.nan
    out, _ = reproject_interp((data, c.wcs), w, shape_out=shape, order="bilinear")
    return out


def robust_norm(img: np.ndarray) -> np.ndarray:
    """Taustan poisto + jako kohinalla (MAD), jotta ilmaisimet voi summata."""
    med = np.nanmedian(img)
    mad = np.nanmedian(np.abs(img - med)) * 1.4826
    return (img - med) / (mad if mad > 0 else 1.0)


def stretch(img: np.ndarray, lo: float, hi: float) -> np.ndarray:
    x = np.clip((img - lo) / (hi - lo + 1e-12), 0, 1)
    x = np.arcsinh(10 * x) / np.arcsinh(10)
    x = np.nan_to_num(x, nan=0.0)
    return (x * 255).astype(np.uint8)


def to_png(arr8: np.ndarray, path: Path, scale: int, text: str | None = None):
    from PIL import Image, ImageDraw
    im = Image.fromarray(np.flipud(arr8), mode="L")  # pohjoinen ylös
    im = im.resize((arr8.shape[1] * scale, arr8.shape[0] * scale), Image.NEAREST).convert("RGB")
    if text:
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, im.width, 16], fill=(0, 0, 0))
        d.text((4, 2), text, fill=(255, 255, 255))
    # keskiristikko
    d = ImageDraw.Draw(im)
    cx, cy, g = im.width // 2, im.height // 2, 6 * scale
    for a, b in (((cx - 2 * g, cy), (cx - g, cy)), ((cx + g, cy), (cx + 2 * g, cy)),
                 ((cx, cy - 2 * g), (cx, cy - g)), ((cx, cy + g), (cx, cy + 2 * g))):
        d.line([a, b], fill=(255, 60, 60), width=1)
    im.save(path)
    return im


def diff_png(a: np.ndarray, b: np.ndarray, path: Path, scale: int, text: str):
    d = b - a
    lim = np.nanpercentile(np.abs(d), 99.5) or 1.0
    arr = np.nan_to_num(np.clip((d / lim + 1) / 2, 0, 1) * 255, nan=127).astype(np.uint8)
    to_png(arr, path, scale, text)


# --------------------------------------------------------------------------- pääohjelma

def select_per_group(tab, n: int):
    """Valitsee max n kuvaa per (epookki, ilmaisin) tasaisesti ajan yli -> nopea haku."""
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


def run(coord: SkyCoord, label: str, slug: str, args, extra: dict, progress=None):
    """progress(done, total, stage) kutsutaan latauksen aikana (backend käyttää tätä)."""
    print(f"\n== {label}  RA={coord.ra.deg:.6f}  Dec={coord.dec.deg:.6f}")
    out = Path(args.out) / slug
    (out / "frames").mkdir(parents=True, exist_ok=True)
    size_deg = args.size / 60.0

    tab = query_images(coord, size_deg, args.bands)
    if len(tab) == 0:
        print("  Ei SPHEREx-kuvia tälle kohdalle.")
        raise LookupError("No SPHEREx images cover this position")
    tab = select_per_group(tab, getattr(args, "per_group", 0))
    if args.max and len(tab) > args.max:
        idx = np.linspace(0, len(tab) - 1, args.max).astype(int)
        tab = tab[idx]
        print(f"  Rajattu {args.max} kuvaan (--max)")

    t0 = time.time()
    total = len(tab)
    if progress:
        progress(0, total, "downloading")
    cutouts = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_cutout, r, coord) for r in tab]
        for i, f in enumerate(cf.as_completed(futs), 1):
            c = f.result()
            if c is not None:
                cutouts.append(c)
            if progress:
                progress(i, total, "downloading")
    print(f"  Ladattu {len(cutouts)}/{len(tab)} cutoutia ({time.time() - t0:.0f} s)")
    if not cutouts:
        raise RuntimeError("All cutout downloads failed")
    if progress:
        progress(total, total, "processing")

    mjds = np.array([c.mjd for c in cutouts])
    ep_labels = group_epochs(mjds)
    n_ep = ep_labels.max() + 1
    w, shape = target_wcs(coord, size_deg)

    # Pinotaan: epookki x ilmaisin -> mediaani
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
            st = np.nanmedian(np.stack(imgs), axis=0)
            stacks[(e, b)] = st
            em["detectors"][b] = {"n_images": len(imgs),
                                  "flagged_frac": float(np.mean([c.flagged_frac for c in sel if c.band == b]))}
            fits.PrimaryHDU(st.astype(np.float32), header=w.to_header()).writeto(
                out / f"epoch{e}_{b}.fits", overwrite=True)
        # kaikki ilmaisimet yhteen (S/N-painotettu)
        per = [robust_norm(stacks[(e, b)]) for b in args.bands if (e, b) in stacks]
        if per:
            stacks[(e, "ALL")] = np.nansum(per, axis=0) / np.sqrt(len(per))
            fits.PrimaryHDU(stacks[(e, "ALL")].astype(np.float32), header=w.to_header()).writeto(
                out / f"epoch{e}_ALL.fits", overwrite=True)
        epochs_meta.append(em)

    # PNG-framet, GIF ja erotuskuva per ilmaisin, yhteinen venytys kaikille epookeille
    scale = max(1, 400 // shape[0])
    outputs = {}
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
            pil.append(to_png(stretch(img, lo, hi), p, scale,
                              f"{label} {b}  {epochs_meta[e]['date']}"))
        files = {"frames": [f"frames/{b}/epoch{e}.png" for e, _ in ims]}
        if len(pil) > 1:
            pil[0].save(out / f"blink_{b}.gif", save_all=True, append_images=pil[1:],
                        duration=args.frame_ms, loop=0)
            diff_png(ims[0][1], ims[-1][1], out / f"diff_{b}.png", scale,
                     f"{b}: {epochs_meta[ims[-1][0]]['date']} - {epochs_meta[ims[0][0]]['date']}")
            files["gif"] = f"blink_{b}.gif"
            files["diff"] = f"diff_{b}.png"
        outputs[b] = files

    # Spektri / valokäyrä kohteen kohdalta
    with open(out / "spectrum.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["mjd", "epoch", "detector", "wavelength_um", "flux_mjy_sr", "err_mjy_sr", "flagged_frac"])
        for c, l in sorted(zip(cutouts, ep_labels), key=lambda t: (t[1], t[0].wavelength_um)):
            wr.writerow([f"{c.mjd:.5f}", l, c.band, f"{c.wavelength_um:.4f}",
                         f"{c.center_flux:.5g}", f"{c.center_err:.3g}", f"{c.flagged_frac:.3f}"])
    plot_spectrum(cutouts, ep_labels, epochs_meta, out / "spectrum.png", label)

    meta = {
        "target": label, "ra_deg": coord.ra.deg, "dec_deg": coord.dec.deg,
        "fov_arcmin": args.size, "pixel_scale_arcsec": PIXEL_SCALE_ARCSEC,
        "shape": list(shape), "bands": args.bands, "detector_ranges_um": DETECTORS,
        "epochs": epochs_meta, "outputs": outputs, "spectrum": "spectrum.csv",
        "versions": sorted({c.version for c in cutouts if c.version}),
        "generated": Time.now().iso, **extra,
        "credit": "NASA/IPAC Infrared Science Archive (IRSA), SPHEREx Team",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"  {n_ep} epookkia -> {out}/")
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
    ax.set_xlabel("Aallonpituus (µm)")
    ax.set_ylabel("Pintakirkkaus (MJy/sr, zodi poistettu)")
    ax.set_title(f"{label} – SPHEREx-spektri per epookki")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description="SPHEREx-aikasarja annetulle taivaan kohdalle")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", choices=TARGETS.keys(), help="haasteen testikohde")
    g.add_argument("--all-targets", action="store_true", help="kaikki 5 testikohdetta")
    g.add_argument("--name", help="mikä tahansa Simbad-nimi")
    g.add_argument("--ra", help="RA asteina tai esim. 08h55m10.8s")
    p.add_argument("--dec", help="Dec asteina tai esim. -7d14m42s")
    p.add_argument("--size", type=float, default=3.0, help="näkökenttä arcmin (oletus 3)")
    p.add_argument("--bands", nargs="+", default=list(DETECTORS), choices=list(DETECTORS))
    p.add_argument("--max", type=int, default=0, help="max kuvia per kohde (0 = kaikki)")
    p.add_argument("--per-group", type=int, default=0,
                   help="max kuvia per epookki+ilmaisin (esim. 3 = nopea blink, 0 = kaikki)")
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--mask-flags", action="store_true", help="maskaa kaikki liputetut pikselit")
    p.add_argument("--lo", type=float, default=1.0, help="venytyksen alapersentiili")
    p.add_argument("--hi", type=float, default=99.7, help="venytyksen yläpersentiili")
    p.add_argument("--frame-ms", type=int, default=600, help="GIF-framen kesto")
    p.add_argument("--out", default="output")
    args = p.parse_args()

    if args.ra is not None:
        if args.dec is None:
            p.error("--ra vaatii --dec")
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
