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

// Bands that have at least one frame.
export function availableBands(meta: Meta): Band[] {
  return BANDS.filter((band) => (meta.outputs[band]?.frames.length ?? 0) > 0);
}

// Number of SPHEREx images behind one frame.
export function imageCount(epoch: Epoch, band: Band): number {
  if (band === "ALL") return epoch.n_images;
  return epoch.detectors[band]?.n_images ?? 0;
}
