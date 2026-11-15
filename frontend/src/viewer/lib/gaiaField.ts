// Gaia field stars and point sources without a Gaia match.
// Pure functions: no React, no network.
import type { GaiaStar } from "../../api";
import { valueAt, type FitsImage } from "./fits";
import { skyToPixel } from "./skyCoords";
import type { Meta } from "../types";

const GAIA_EPOCH = 2016.0;

// Search radius for the image: half the diagonal plus a margin for stars that move in.
export function fieldRadiusArcsec(meta: Meta): number {
  const [h, w] = meta.shape;
  const halfDiag = (Math.hypot(h, w) / 2) * meta.pixel_scale_arcsec;
  return Math.min(900, Math.ceil(halfDiag + 30));
}

export interface StarPixel {
  x: number; // SPHEREx pixel, whole numbers are pixel centres
  y: number;
  star: GaiaStar;
}

// One star moved from J2016.0 to `year` with its proper motion, as an image pixel.
export function starPixelAt(star: GaiaStar, meta: Meta, year: number): { x: number; y: number } {
  const dt = year - GAIA_EPOCH;
  const dec = star.dec + ((star.pmdec ?? 0) * dt) / 3.6e6;
  const ra = star.ra + ((star.pmra ?? 0) * dt) / 3.6e6 / Math.cos((star.dec * Math.PI) / 180);
  return skyToPixel(ra, dec, meta);
}

// All stars on the image at `year` (with a half-pixel margin), in the order given (brightest first).
export function starsOnImage(stars: GaiaStar[], meta: Meta, year: number): StarPixel[] {
  const [h, w] = meta.shape;
  const out: StarPixel[] = [];
  for (const star of stars) {
    const p = starPixelAt(star, meta, year);
    if (p.x >= -0.5 && p.x <= w - 0.5 && p.y >= -0.5 && p.y <= h - 0.5) out.push({ ...p, star });
  }
  return out;
}

// Gaia star nearest to a pixel, within `maxPx`.
export function nearestStar(stars: StarPixel[], x: number, y: number, maxPx = 1.2): StarPixel | null {
  let best: StarPixel | null = null;
  let bestD = maxPx;
  for (const s of stars) {
    const d = Math.hypot(s.x - x, s.y - y);
    if (d <= bestD) {
      best = s;
      bestD = d;
    }
  }
  return best;
}

// Short text for the star under the cursor: "Gaia DR3 star · G 12.3 · moves 0.045″/yr".
export function describeStar(s: GaiaStar): string {
  const g = s.g === null ? "" : ` · G ${s.g.toFixed(1)}`;
  const pm =
    s.pmra === null || s.pmdec === null
      ? " · no proper motion in Gaia"
      : ` · moves ${(Math.hypot(s.pmra, s.pmdec) / 1000).toFixed(3)}″/yr`;
  return `Gaia DR3 star${g}${pm}`;
}

export interface Source {
  x: number; // screen pixel (row 0 = top), like the rest of the viewer
  y: number;
  snr: number; // peak height above the background, in noise units
}

// Point sources in one image: local maxima in a 5×5 box that rise `nSigma` above the
// background (median, noise from the median absolute deviation). Missing pixels are skipped,
// and so is a 2-pixel border, where edge effects of the cutout give false peaks.
export function detectSources(img: FitsImage, nSigma = 8): Source[] {
  const { width: w, height: h } = img;
  const values: number[] = [];
  for (const v of img.data) if (Number.isFinite(v)) values.push(v);
  if (values.length < 25) return [];
  values.sort((a, b) => a - b);
  const median = values[Math.floor(values.length / 2)];
  const dev = values.map((v) => Math.abs(v - median)).sort((a, b) => a - b);
  const sigma = 1.4826 * dev[Math.floor(dev.length / 2)] || 1e-9;
  const limit = median + nSigma * sigma;

  const at = (x: number, y: number) => valueAt(img, x, y);
  const found: Source[] = [];
  for (let y = 2; y < h - 2; y++) {
    for (let x = 2; x < w - 2; x++) {
      const v = at(x, y);
      if (!Number.isFinite(v) || v < limit) continue;
      let peak = true;
      for (let dy = -2; dy <= 2 && peak; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          if ((dx || dy) && at(x + dx, y + dy) > v) {
            peak = false;
            break;
          }
        }
      }
      if (peak) found.push({ x, y, snr: (v - median) / sigma });
    }
  }
  return found.sort((a, b) => b.snr - a.snr);
}

// Sources with no Gaia star within `tolPx` pixels (SPHEREx pixels are 6.15″).
export function withoutGaia(sources: Source[], stars: StarPixel[], tolPx = 2.5): Source[] {
  return sources.filter((s) => !stars.some((p) => Math.hypot(p.x - s.x, p.y - s.y) <= tolPx));
}
