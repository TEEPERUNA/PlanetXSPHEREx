// Light curve from meta.json "light_curve": brightness of the target per epoch.
// Two formats exist:
// - per band (current science): {is_variable, variable_bands, bands: {D1: {..., epochs: [...]}}, points}
// - one series (older results):  {is_variable, mean_flux, ..., epochs: [{epoch, mjd, flux, err}]}

export interface LcPoint {
  epoch: number;
  mjd: number;
  flux: number; // MJy/sr
  err: number;
}

export interface LcSeries {
  band: string; // "D1"…"D6", or "All" for the older single series
  variable: boolean;
  mean: number;
  points: LcPoint[]; // in time order
}

export interface LightCurve {
  series: LcSeries[];
  variableBands: string[];
  isVariable: boolean;
}

type Raw = Record<string, unknown>;

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : NaN);

function toPoints(list: unknown): LcPoint[] {
  if (!Array.isArray(list)) return [];
  return list
    .map((p: Raw) => ({ epoch: num(p.epoch), mjd: num(p.mjd), flux: num(p.flux), err: num(p.err) }))
    .filter((p) => Number.isFinite(p.mjd) && Number.isFinite(p.flux))
    .sort((a, b) => a.mjd - b.mjd);
}

function mean(points: LcPoint[]): number {
  return points.length ? points.reduce((s, p) => s + p.flux, 0) / points.length : NaN;
}

// Null when meta.json has no usable light curve.
export function parseLightCurve(raw: unknown): LightCurve | null {
  if (!raw || typeof raw !== "object") return null;
  const lc = raw as Raw;
  const series: LcSeries[] = [];

  if (lc.bands && typeof lc.bands === "object") {
    for (const [band, info] of Object.entries(lc.bands as Record<string, Raw>)) {
      const points = toPoints(info?.epochs);
      if (points.length === 0) continue;
      const m = num(info.mean_flux);
      series.push({ band, variable: info.is_variable === true, mean: Number.isFinite(m) ? m : mean(points), points });
    }
    series.sort((a, b) => a.band.localeCompare(b.band));
  } else if (Array.isArray(lc.epochs)) {
    const points = toPoints(lc.epochs);
    const m = num(lc.mean_flux);
    if (points.length) series.push({ band: "All", variable: lc.is_variable === true, mean: Number.isFinite(m) ? m : mean(points), points });
  }

  if (series.length === 0) return null;
  const variableBands = Array.isArray(lc.variable_bands)
    ? (lc.variable_bands as unknown[]).map(String)
    : series.filter((s) => s.variable).map((s) => s.band);
  return { series, variableBands, isVariable: lc.is_variable === true || variableBands.length > 0 };
}
