// Small helpers for drawing charts by hand in SVG.

// Maps a data value to a pixel position.
export function linearScale(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v) => r0 + (v - d0) * k;
}

// A round step (1, 2 or 5 × 10^n) that splits the span into about `count` parts.
function niceStep(span: number, count: number): number {
  const raw = span / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const nice = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
  return nice * mag;
}

// Range widened to round numbers, plus the tick values inside it.
export function niceAxis(min: number, max: number, count = 5): { lo: number; hi: number; ticks: number[] } {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { lo: 0, hi: 1, ticks: [0, 1] };
  if (min === max) {
    const pad = Math.abs(min) || 1;
    min -= pad;
    max += pad;
  }
  const step = niceStep(max - min, count);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { lo, hi, ticks };
}

// Short tick label: 1200 -> "1200", 0.5 -> "0.5", 1e-7 -> "0".
export function formatTick(v: number): string {
  if (Math.abs(v) < 1e-9) return "0";
  return Number(v.toPrecision(4)).toString();
}
