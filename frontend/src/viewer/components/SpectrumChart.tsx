import { useEffect, useMemo, useState, type PointerEvent } from "react";
import { formatTick, linearScale, niceAxis } from "../lib/chartScale";
import { parseSpectrum, type SpectrumRow } from "../lib/parseSpectrum";
import type { Detector, Epoch } from "../types";

interface Props {
  url: string; // full URL of spectrum.csv
  epochs: Epoch[]; // for dates in the legend
  ranges?: Partial<Record<Detector, [number, number]>>; // detector bands in µm
  highlightEpoch?: number; // epoch shown in the blink right now
}

// One colour per epoch, readable on light and dark backgrounds.
const EPOCH_COLORS = ["#3b82f6", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6", "#06b6d4", "#ef4444"];
export const epochColor = (index: number) => EPOCH_COLORS[index % EPOCH_COLORS.length];

// Drawing area in SVG units. The SVG scales to the container width.
const W = 480;
const H = 280;
const M = { left: 52, right: 12, top: 22, bottom: 40 };

// Spectrum: x = wavelength, y = flux, error bars, colour by epoch.
export function SpectrumChart({ url, epochs, ranges, highlightEpoch }: Props) {
  const [rows, setRows] = useState<SpectrumRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<SpectrumRow | null>(null);

  // Load the CSV. Cancel if the target changes before it arrives.
  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError(null);
    setHover(null);

    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => setRows(parseSpectrum(text)))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
      });

    return () => controller.abort();
  }, [url]);

  // Axes from the data. x covers all detectors, y starts at 0 unless flux goes below it.
  const chart = useMemo(() => {
    if (!rows || rows.length === 0) return null;
    const bandEdges = Object.values(ranges ?? {}).flatMap((range) => range ?? []);
    const xs = [...rows.map((r) => r.wavelength_um), ...bandEdges];
    const lows = rows.map((r) => r.flux_mjy_sr - (Number.isFinite(r.err_mjy_sr) ? r.err_mjy_sr : 0));
    const highs = rows.map((r) => r.flux_mjy_sr + (Number.isFinite(r.err_mjy_sr) ? r.err_mjy_sr : 0));

    // x: tight to the data (0.75–5 µm), round ticks only inside it.
    const xMin = Math.min(...xs) - 0.05;
    const xMax = Math.max(...xs) + 0.05;
    const xTicks = niceAxis(xMin, xMax, 6).ticks.filter((t) => t >= xMin && t <= xMax);
    const xAxis = { lo: xMin, hi: xMax, ticks: xTicks };
    const yAxis = niceAxis(Math.min(0, ...lows), Math.max(...highs), 5);
    return {
      xAxis,
      yAxis,
      sx: linearScale(xAxis.lo, xAxis.hi, M.left, W - M.right),
      sy: linearScale(yAxis.lo, yAxis.hi, H - M.bottom, M.top),
    };
  }, [rows, ranges]);

  const dateOf = (index: number) => epochs.find((e) => e.index === index)?.date ?? `epoch ${index}`;
  const epochsInData = useMemo(() => [...new Set((rows ?? []).map((r) => r.epoch))].sort((a, b) => a - b), [rows]);

  // Nearest point to the pointer, within 24 SVG units.
  function handlePointer(e: PointerEvent<SVGSVGElement>) {
    if (!rows || !chart) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const py = ((e.clientY - rect.top) / rect.height) * H;
    let best: SpectrumRow | null = null;
    let bestDist = 24 * 24;
    for (const r of rows) {
      const dx = chart.sx(r.wavelength_um) - px;
      const dy = chart.sy(r.flux_mjy_sr) - py;
      const d = dx * dx + dy * dy;
      if (d < bestDist) {
        bestDist = d;
        best = r;
      }
    }
    setHover(best);
  }

  // Highlighted epoch is drawn last so it sits on top.
  const ordered = useMemo(() => {
    if (!rows) return [];
    if (highlightEpoch === undefined) return rows;
    return [...rows.filter((r) => r.epoch !== highlightEpoch), ...rows.filter((r) => r.epoch === highlightEpoch)];
  }, [rows, highlightEpoch]);

  return (
    <section className="spectrum">
      <h3>Spectrum</h3>
      {error && <p className="spectrum__note">Could not load the spectrum ({error}).</p>}
      {!error && !rows && <p className="spectrum__note">Loading spectrum…</p>}
      {rows && rows.length === 0 && <p className="spectrum__note">No spectrum measurements for this position.</p>}

      {chart && (
        <>
          <svg
            className="spectrum__chart"
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label={`Spectrum of the image centre: ${rows!.length} measurements from ${epochsInData.length} epochs`}
            onPointerMove={handlePointer}
            onPointerDown={handlePointer}
            onPointerLeave={(e) => e.pointerType === "mouse" && setHover(null)}
          >
            {/* Detector bands D1–D6 in the background */}
            {Object.entries(ranges ?? {}).map(([name, range], i) => {
              const [a, b] = range as [number, number];
              const x0 = chart.sx(a);
              const x1 = chart.sx(b);
              return (
                <g key={name}>
                  {i % 2 === 0 && (
                    <rect className="spectrum__band" x={x0} y={M.top} width={x1 - x0} height={H - M.top - M.bottom} />
                  )}
                  <text className="spectrum__bandlabel" x={(x0 + x1) / 2} y={M.top - 8} textAnchor="middle">
                    {name}
                  </text>
                </g>
              );
            })}

            {/* Horizontal grid + y labels */}
            {chart.yAxis.ticks.map((t) => (
              <g key={`y${t}`}>
                <line className="spectrum__grid" x1={M.left} x2={W - M.right} y1={chart.sy(t)} y2={chart.sy(t)} />
                <text className="spectrum__tick" x={M.left - 6} y={chart.sy(t) + 3.5} textAnchor="end">
                  {formatTick(t)}
                </text>
              </g>
            ))}

            {/* x labels */}
            {chart.xAxis.ticks.map((t) => (
              <text key={`x${t}`} className="spectrum__tick" x={chart.sx(t)} y={H - M.bottom + 16} textAnchor="middle">
                {formatTick(t)}
              </text>
            ))}

            {/* Axes */}
            <line className="spectrum__axis" x1={M.left} x2={W - M.right} y1={H - M.bottom} y2={H - M.bottom} />
            <line className="spectrum__axis" x1={M.left} x2={M.left} y1={M.top} y2={H - M.bottom} />
            <text className="spectrum__title" x={(M.left + W - M.right) / 2} y={H - 6} textAnchor="middle">
              Wavelength (µm)
            </text>
            <text
              className="spectrum__title"
              transform={`translate(13 ${(M.top + H - M.bottom) / 2}) rotate(-90)`}
              textAnchor="middle"
            >
              Flux (MJy/sr)
            </text>

            {/* Points with error bars */}
            {ordered.map((r, i) => {
              const x = chart.sx(r.wavelength_um);
              const y = chart.sy(r.flux_mjy_sr);
              const err = Number.isFinite(r.err_mjy_sr) ? r.err_mjy_sr : 0;
              const dim = highlightEpoch !== undefined && r.epoch !== highlightEpoch;
              return (
                <g key={i} className={dim ? "spectrum__point is-dim" : "spectrum__point"} style={{ color: epochColor(r.epoch) }}>
                  {err > 0 && (
                    <line x1={x} x2={x} y1={chart.sy(r.flux_mjy_sr - err)} y2={chart.sy(r.flux_mjy_sr + err)} stroke="currentColor" />
                  )}
                  <circle cx={x} cy={y} r={hover === r ? 4.5 : 3} fill="currentColor" />
                </g>
              );
            })}
          </svg>

          {/* Legend: one colour per epoch */}
          <ul className="spectrum__legend">
            {epochsInData.map((e) => (
              <li key={e} className={e === highlightEpoch ? "is-current" : undefined}>
                <span className="spectrum__swatch" style={{ background: epochColor(e) }} />
                {dateOf(e)}
              </li>
            ))}
          </ul>

          <p className="spectrum__readout">
            {hover
              ? `${hover.detector} · ${hover.wavelength_um.toFixed(3)} µm · ${formatTick(hover.flux_mjy_sr)} ± ${formatTick(hover.err_mjy_sr)} MJy/sr · ${dateOf(hover.epoch)}`
              : "Point at a dot to see its value. Measured at the image centre."}
          </p>
        </>
      )}
    </section>
  );
}
