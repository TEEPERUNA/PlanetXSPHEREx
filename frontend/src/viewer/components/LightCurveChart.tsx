import { useMemo, useState, type PointerEvent } from "react";
import { formatTick, linearScale, niceAxis } from "../lib/chartScale";
import { parseLightCurve, type LcPoint } from "../lib/lightCurve";
import type { Epoch } from "../types";

interface Props {
  lightCurve: unknown; // meta.light_curve, any of the two formats
  epochs: Epoch[]; // for dates on the time axis
  highlightEpoch?: number; // epoch shown in the blink right now
}

type Scale = "relative" | "absolute";

// Same detector colours as the science plots (blue → red with wavelength).
const BAND_COLORS: Record<string, string> = {
  D1: "#8b5cf6",
  D2: "#3b82f6",
  D3: "#10b981",
  D4: "#f59e0b",
  D5: "#f97316",
  D6: "#ef4444",
  All: "#22d3ee",
};

const W = 480;
const H = 230;
const M = { left: 52, right: 12, top: 14, bottom: 40 };

interface Hover {
  band: string;
  p: LcPoint;
  rel: number;
}

// Brightness of the target over time, one line per detector band.
export function LightCurveChart({ lightCurve, epochs, highlightEpoch }: Props) {
  const lc = useMemo(() => parseLightCurve(lightCurve), [lightCurve]);
  const [scale, setScale] = useState<Scale>("relative");
  const [hover, setHover] = useState<Hover | null>(null);

  // y value of a point in the chosen scale
  const yOf = (p: LcPoint, mean: number) => (scale === "relative" ? p.flux / mean : p.flux);
  const eOf = (p: LcPoint, mean: number) => (scale === "relative" ? p.err / mean : p.err);

  const chart = useMemo(() => {
    if (!lc) return null;
    const all = lc.series.flatMap((s) => s.points.map((p) => ({ p, s })));
    const mjds = all.map(({ p }) => p.mjd);
    const span = Math.max(...mjds) - Math.min(...mjds) || 30;
    const x0 = Math.min(...mjds) - span * 0.06;
    const x1 = Math.max(...mjds) + span * 0.06;
    const err = (p: LcPoint) => (Number.isFinite(p.err) ? p.err : 0);
    const lows = all.map(({ p, s }) => (scale === "relative" ? (p.flux - err(p)) / s.mean : p.flux - err(p)));
    const highs = all.map(({ p, s }) => (scale === "relative" ? (p.flux + err(p)) / s.mean : p.flux + err(p)));
    const yAxis =
      scale === "relative"
        ? niceAxis(Math.min(1, ...lows), Math.max(1, ...highs), 5)
        : niceAxis(Math.min(0, ...lows), Math.max(...highs), 5);
    return {
      yAxis,
      sx: linearScale(x0, x1, M.left, W - M.right),
      sy: linearScale(yAxis.lo, yAxis.hi, H - M.bottom, M.top),
    };
  }, [lc, scale]);

  if (!lc || !chart) return null;
  const single = lc.series.length === 1 && lc.series[0].band === "All"; // older results: one series

  const dateOf = (mjd: number) => epochs.reduce((best, e) => (Math.abs(e.mjd_mean - mjd) < Math.abs(best.mjd_mean - mjd) ? e : best), epochs[0])?.date ?? "";
  const highlight = epochs.find((e) => e.index === highlightEpoch);
  // Time axis: one tick per epoch that has light-curve points
  const tickMjds = [...new Set(lc.series.flatMap((s) => s.points.map((p) => p.epoch)))]
    .map((i) => epochs.find((e) => e.index === i))
    .filter((e): e is Epoch => !!e);

  function handlePointer(e: PointerEvent<SVGSVGElement>) {
    if (!lc || !chart) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const py = ((e.clientY - rect.top) / rect.height) * H;
    let best: Hover | null = null;
    let bestD = 24 * 24;
    for (const s of lc.series) {
      for (const p of s.points) {
        const d = (chart.sx(p.mjd) - px) ** 2 + (chart.sy(yOf(p, s.mean)) - py) ** 2;
        if (d < bestD) {
          bestD = d;
          best = { band: s.band, p, rel: p.flux / s.mean };
        }
      }
    }
    setHover(best);
  }

  return (
    <section className="lightcurve">
      <div className="spectrum__head">
        <h3>Light curve</h3>
        <div className="spectrum__modes" role="group" aria-label="Light curve scale">
          <button type="button" aria-pressed={scale === "relative"} className={scale === "relative" ? "is-active" : undefined} onClick={() => setScale("relative")}>
            Relative
          </button>
          <button type="button" aria-pressed={scale === "absolute"} className={scale === "absolute" ? "is-active" : undefined} onClick={() => setScale("absolute")}>
            MJy/sr
          </button>
        </div>
      </div>

      <p className={lc.isVariable ? "lightcurve__verdict is-variable" : "lightcurve__verdict"}>
        {!lc.isVariable
          ? "No clear change in brightness between the dates."
          : single || lc.variableBands.length === 0
            ? "Brightness changes between the dates."
            : `Brightness changes in ${lc.variableBands.join(", ")}.`}
      </p>
      <p className="spectrum__intro">
        Brightness of the target on each date, {single ? "all detectors together" : "one line per detector"}.{" "}
        {scale === "relative" ? "1.0 = the band's average, so lines that rise or fall show change." : "In MJy/sr; bands differ a lot in brightness."}
      </p>

      <svg
        className="spectrum__chart"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Light curve: ${lc.series.length} bands over ${tickMjds.length} dates. ${lc.isVariable ? "Variable." : "No clear variability."}`}
        onPointerMove={handlePointer}
        onPointerDown={handlePointer}
        onPointerLeave={(e) => e.pointerType === "mouse" && setHover(null)}
      >
        {chart.yAxis.ticks.map((t) => (
          <g key={`y${t}`}>
            <line className="spectrum__grid" x1={M.left} x2={W - M.right} y1={chart.sy(t)} y2={chart.sy(t)} />
            <text className="spectrum__tick" x={M.left - 6} y={chart.sy(t) + 3.5} textAnchor="end">
              {formatTick(t)}
            </text>
          </g>
        ))}
        {scale === "relative" && (
          <line className="lightcurve__mean" x1={M.left} x2={W - M.right} y1={chart.sy(1)} y2={chart.sy(1)} />
        )}
        {tickMjds.map((e) => (
          <text key={e.index} className="spectrum__tick" x={chart.sx(e.mjd_mean)} y={H - M.bottom + 16} textAnchor="middle">
            {e.date.slice(0, 7)}
          </text>
        ))}
        {highlight && (
          <line className="lightcurve__now" x1={chart.sx(highlight.mjd_mean)} x2={chart.sx(highlight.mjd_mean)} y1={M.top} y2={H - M.bottom} />
        )}
        <line className="spectrum__axis" x1={M.left} x2={W - M.right} y1={H - M.bottom} y2={H - M.bottom} />
        <line className="spectrum__axis" x1={M.left} x2={M.left} y1={M.top} y2={H - M.bottom} />
        <text className="spectrum__title" x={(M.left + W - M.right) / 2} y={H - 6} textAnchor="middle">
          Date
        </text>
        <text className="spectrum__title" transform={`translate(13 ${(M.top + H - M.bottom) / 2}) rotate(-90)`} textAnchor="middle">
          {scale === "relative" ? "Brightness ÷ average" : "Brightness (MJy/sr)"}
        </text>

        {lc.series.map((s) => {
          const color = BAND_COLORS[s.band] ?? "#94a3b8";
          return (
            <g key={s.band} style={{ color }} className={s.variable ? "lightcurve__series is-variable" : "lightcurve__series"}>
              {s.points.length > 1 && (
                <polyline className="spectrum__line" points={s.points.map((p) => `${chart.sx(p.mjd)},${chart.sy(yOf(p, s.mean))}`).join(" ")} />
              )}
              {s.points.map((p) => {
                const x = chart.sx(p.mjd);
                const y = yOf(p, s.mean);
                const e = eOf(p, s.mean);
                const active = hover?.band === s.band && hover.p === p;
                return (
                  <g key={p.mjd}>
                    {Number.isFinite(e) && e > 0 && (
                      <line className="spectrum__err" x1={x} x2={x} y1={chart.sy(y - e)} y2={chart.sy(y + e)} />
                    )}
                    <circle cx={x} cy={chart.sy(y)} r={active ? 5 : 3.5} fill="currentColor" />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>

      <ul className="spectrum__legend">
        {lc.series.map((s) => (
          <li key={s.band} className={s.variable ? "is-current" : undefined}>
            <span className="spectrum__swatch" style={{ background: BAND_COLORS[s.band] ?? "#94a3b8" }} />
            {s.band === "All" ? "All detectors" : s.band}
            {s.variable && " · varies"}
          </li>
        ))}
      </ul>

      <p className="spectrum__readout">
        {hover
          ? `${hover.band} · ${dateOf(hover.p.mjd)} · ${formatTick(hover.p.flux)} ± ${formatTick(hover.p.err)} MJy/sr · ${hover.rel.toFixed(2)}× average`
          : "Point at a dot to see its value. Measured at the image centre."}
      </p>
    </section>
  );
}
