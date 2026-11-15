import { useEffect, useState } from "react";
import { readFits, valueAt, type FitsImage } from "../lib/fits";
import { joinUrl } from "../lib/frames";
import type { Band, Meta, Pixel } from "../types";

// Values of one pixel. Missing fields = not available for this result.
export interface PixelValues {
  sb?: number; // surface brightness, zodi subtracted (MJy/sr)
  zodi?: number; // zodiacal light (MJy/sr)
  snr?: number; // signal-to-noise
  wave?: number; // central wavelength (µm)
  bw?: number; // bandwidth (µm)
  detX?: number; // pixel on the original detector
  detY?: number;
  flags?: number; // SPHEREx flag bits (see lib/flags.ts)
}

// Layer names (EXTNAME) in the per-pixel file from science.
const LAYERS: Record<string, keyof PixelValues> = {
  SB: "sb",
  ZODI: "zodi",
  SNR: "snr",
  WAVE: "wave",
  BW: "bw",
  DETX: "detX",
  DETY: "detY",
  FLAGS: "flags",
};

// Layers where the same value everywhere is real data (e.g. no flags anywhere).
const ALWAYS_KEEP = new Set(["SB", "FLAGS"]);

// A layer with the same value in every pixel is a filler, not data
// (science writes defaults when the raw images were not available).
// Real wavelength, detector and zodi maps always vary across the image.
function isFiller(img: FitsImage): boolean {
  let first: number | undefined;
  for (const v of img.data) {
    if (!Number.isFinite(v)) continue;
    if (first === undefined) first = v;
    else if (v !== first) return false;
  }
  return true;
}

// Science's fallback detector grid when the raw image is missing: DETX = offset + x
// (DETY = offset + row), i.e. exactly one detector pixel per image pixel, no rotation.
// A real SPHEREx image is rotated against the sky, so real maps never look like this.
function isFallbackDetector(img: FitsImage): boolean {
  if (img.name !== "DETX" && img.name !== "DETY") return false;
  let offset: number | undefined;
  for (let i = 0; i < img.data.length; i++) {
    const pos = img.name === "DETX" ? i % img.width : Math.floor(i / img.width);
    const d = img.data[i] - pos;
    if (!Number.isFinite(d)) continue;
    if (offset === undefined) offset = d;
    else if (Math.abs(d - offset) > 1e-3) return false;
  }
  return true;
}

// One download per file, shared by every viewer on the page.
const cache = new Map<string, Promise<FitsImage[]>>();

function loadFits(url: string): Promise<FitsImage[]> {
  let promise = cache.get(url);
  if (!promise) {
    promise = fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.arrayBuffer();
      })
      .then((buffer) =>
        readFits(buffer).filter((img) => ALWAYS_KEEP.has(img.name) || (!isFiller(img) && !isFallbackDetector(img))),
      );
    promise.catch(() => cache.delete(url)); // allow a retry later
    cache.set(url, promise);
  }
  return promise;
}

// File of one epoch: "epoch3_D2.fits" or "pixels/D2/epoch3.fits" -> 3.
function pathForEpoch(paths: string[] | undefined, epoch: number): string | undefined {
  return paths?.find((p) => Number(/epoch(\d+)/.exec(p)?.[1]) === epoch);
}

// Pixel values under the cursor. Downloads only while the cursor is on the image.
// Uses the full per-pixel file when science provides it (outputs[band].pixels),
// otherwise the epoch stack (outputs[band].fits) for surface brightness only.
export function usePixelValues(
  meta: Meta,
  baseUrl: string,
  band: Band,
  epoch: number | null, // null in diff mode
  pixel: Pixel | null,
): { values: PixelValues | null; loading: boolean } {
  const out = meta.outputs[band];
  const pixelsPath = epoch === null ? undefined : pathForEpoch(out?.pixels, epoch);
  // The ALL stack is normalised across detectors, so it has no physical unit.
  const stackPath = epoch === null || band === "ALL" ? undefined : pathForEpoch(out?.fits, epoch);
  const path = pixelsPath ?? stackPath;
  const url = path ? joinUrl(baseUrl, path) : null;

  const [loaded, setLoaded] = useState<{ url: string; images: FitsImage[] } | null>(null);
  const wanted = pixel !== null && url !== null;

  useEffect(() => {
    if (!wanted || !url) return;
    let alive = true;
    loadFits(url)
      .then((images) => alive && setLoaded({ url, images }))
      .catch(() => alive && setLoaded({ url, images: [] }));
    return () => {
      alive = false;
    };
  }, [wanted, url]);

  if (!pixel || !url) return { values: null, loading: false };
  if (!loaded || loaded.url !== url) return { values: null, loading: true };

  const values: PixelValues = {};
  if (pixelsPath) {
    for (const img of loaded.images) {
      const key = LAYERS[img.name];
      if (key) values[key] = valueAt(img, pixel.x, pixel.y);
    }
  } else if (loaded.images[0]) {
    values.sb = valueAt(loaded.images[0], pixel.x, pixel.y);
  }
  return { values, loading: false };
}
