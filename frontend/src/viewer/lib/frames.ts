import { BANDS, type Band, type Epoch, type Frame, type Meta } from "../types";

// Join the base URL and a relative path with exactly one slash.
export function joinUrl(baseUrl: string, path: string): string {
  return baseUrl.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, "");
}

// Epoch number from a filename: "frames/D2/epoch4.png" -> 4.
export function epochIndexFromPath(path: string): number | null {
  const match = /epoch(\d+)\.png$/.exec(path);
  return match ? Number(match[1]) : null;
}

// Frames of one band, in the order meta.json lists them.
// The epoch comes from the filename, never from the list position.
export function framesFor(meta: Meta, band: Band, baseUrl: string): Frame[] {
  const paths = meta.outputs[band]?.frames ?? [];
  const frames: Frame[] = [];
  for (const path of paths) {
    const index = epochIndexFromPath(path);
    const epoch = meta.epochs.find((e) => e.index === index);
    if (epoch) frames.push({ src: joinUrl(baseUrl, path), epoch });
  }
  return frames;
}

// Frame closest in time to `mjd`, or the first frame when nothing is picked yet.
// Remembering a date (not a list position) keeps the same epoch on screen when
// the band changes or the full result replaces the preview.
export function nearestFrame(frames: Frame[], mjd: number | null): number {
  if (mjd === null || frames.length === 0) return 0;
  let best = 0;
  for (let i = 1; i < frames.length; i++) {
    if (Math.abs(frames[i].epoch.mjd_mean - mjd) < Math.abs(frames[best].epoch.mjd_mean - mjd)) best = i;
  }
  return best;
}

// Bands that have at least one frame.
export function availableBands(meta: Meta): Band[] {
  return BANDS.filter((band) => (meta.outputs[band]?.frames.length ?? 0) > 0);
}

// Share of unreliable pixels (bad flags) for one frame, 0–1, or null when unknown.
// "ALL" averages the detectors that have images in this epoch.
export function flaggedFraction(epoch: Epoch, band: Band): number | null {
  const values = (band === "ALL" ? Object.values(epoch.detectors) : [epoch.detectors[band]])
    .map((d) => d?.flagged_frac)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

// Number of SPHEREx images behind one frame.
export function imageCount(epoch: Epoch, band: Band): number {
  if (band === "ALL") return epoch.n_images;
  return epoch.detectors[band]?.n_images ?? 0;
}
