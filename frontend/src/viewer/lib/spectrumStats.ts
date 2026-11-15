import type { SpectrumRow } from "./parseSpectrum";

// A point in the chart: one measurement, or the average of several.
export interface SpectrumPoint extends SpectrumRow {
  count: number; // measurements behind this point
}

// One point per date and detector: mean wavelength and flux, error of the mean.
// Turns 30–50 scattered dots into 6 points per date that show the shape.
export function averageByDetector(rows: SpectrumRow[]): SpectrumPoint[] {
  const groups = new Map<string, SpectrumRow[]>();
  for (const r of rows) {
    const key = `${r.epoch}|${r.detector}`;
    const group = groups.get(key);
    if (group) group.push(r);
    else groups.set(key, [r]);
  }

  const points: SpectrumPoint[] = [];
  for (const g of groups.values()) {
    const n = g.length;
    const mean = (pick: (r: SpectrumRow) => number) => g.reduce((sum, r) => sum + pick(r), 0) / n;
    const errs = g.map((r) => r.err_mjy_sr).filter(Number.isFinite);
    const err = errs.length ? Math.sqrt(errs.reduce((sum, e) => sum + e * e, 0)) / errs.length : NaN;
    points.push({
      ...g[0],
      mjd: mean((r) => r.mjd),
      wavelength_um: mean((r) => r.wavelength_um),
      flux_mjy_sr: mean((r) => r.flux_mjy_sr),
      err_mjy_sr: err,
      count: n,
    });
  }
  return points.sort((a, b) => a.epoch - b.epoch || a.wavelength_um - b.wavelength_um);
}

// Every measurement as its own point.
export function asPoints(rows: SpectrumRow[]): SpectrumPoint[] {
  return rows.map((r) => ({ ...r, count: 1 }));
}

// Share of measurements that are within 2 sigma of zero (0–1).
export function noiseShare(rows: SpectrumRow[]): number {
  const usable = rows.filter((r) => Number.isFinite(r.err_mjy_sr) && r.err_mjy_sr > 0);
  if (usable.length === 0) return 0;
  return usable.filter((r) => Math.abs(r.flux_mjy_sr) < 2 * r.err_mjy_sr).length / usable.length;
}

// True when most of the spectrum cannot be told apart from zero.
export function isMostlyNoise(rows: SpectrumRow[]): boolean {
  return rows.length >= 3 && noiseShare(rows) >= 0.6;
}
