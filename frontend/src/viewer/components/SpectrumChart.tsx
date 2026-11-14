import { useEffect, useState } from "react";
import { parseSpectrum, type SpectrumRow } from "../lib/parseSpectrum";

interface Props {
  url: string; // full URL of spectrum.csv
}

// Spectrum: x = wavelength_um, y = flux_mjy_sr, error bars, colour by epoch.
// TODO: draw the chart once the library is chosen (Chart.js or uPlot).
export function SpectrumChart({ url }: Props) {
  const [rows, setRows] = useState<SpectrumRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load the CSV. Cancel if the target changes before it arrives.
  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError(null);

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

  return (
    <section className="spectrum">
      <h3>Spectrum</h3>
      {error && <p className="spectrum__note">Could not load the spectrum ({error}).</p>}
      {!error && !rows && <p className="spectrum__note">Loading spectrum…</p>}
      {rows && <p className="spectrum__note">{rows.length} measurements. Chart coming soon.</p>}
    </section>
  );
}
