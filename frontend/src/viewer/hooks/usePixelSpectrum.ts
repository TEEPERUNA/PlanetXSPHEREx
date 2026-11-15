import { useEffect, useState } from "react";
import { joinUrl } from "../lib/frames";
import { valueAt } from "../lib/fits";
import type { SpectrumRow } from "../lib/parseSpectrum";
import type { Detector, Meta, Pixel } from "../types";
import { loadFits } from "./usePixelValues";

const DETECTORS: Detector[] = ["D1", "D2", "D3", "D4", "D5", "D6"];

export interface PixelSpectrum {
  rows: SpectrumRow[] | null; // null while loading
  loading: boolean;
  approx: boolean; // some wavelengths are the detector centre (no WAVE layer)
  available: boolean; // this result has per-pixel files
}

// Spectrum of one pixel, built from the per-pixel files (pixels/D*/epoch*.fits):
// one point per detector and epoch. SB = surface brightness, error = SB / SNR, wavelength from
// the WAVE layer, or the middle of the detector range when that layer is missing or filler.
export function usePixelSpectrum(meta: Meta, baseUrl: string, pixel: Pixel | null): PixelSpectrum {
  const files = DETECTORS.flatMap((band) => (meta.outputs[band]?.pixels ?? []).map((path) => ({ band, path })));
  const key = pixel ? `${baseUrl}|${pixel.x},${pixel.y}` : null;
  const [state, setState] = useState<{ key: string; rows: SpectrumRow[]; approx: boolean } | null>(null);

  useEffect(() => {
    if (!pixel || !key || files.length === 0) return;
    let alive = true;
    Promise.all(
      files.map(async ({ band, path }) => {
        const epochIndex = Number(/epoch(\d+)/.exec(path)?.[1]);
        const epoch = meta.epochs.find((e) => e.index === epochIndex);
        const images = await loadFits(joinUrl(baseUrl, path)).catch(() => []);
        const layer = (name: string) => images.find((i) => i.name === name);
        const sb = layer("SB") ?? images[0];
        if (!sb || !epoch) return null;
        const flux = valueAt(sb, pixel.x, pixel.y);
        const snrImg = layer("SNR");
        const snr = snrImg ? valueAt(snrImg, pixel.x, pixel.y) : NaN;
        const waveImg = layer("WAVE");
        const wave = waveImg ? valueAt(waveImg, pixel.x, pixel.y) : NaN;
        const range = meta.detector_ranges_um?.[band];
        const centre = range ? (range[0] + range[1]) / 2 : NaN;
        const approx = !Number.isFinite(wave);
        const row: SpectrumRow & { approx: boolean } = {
          mjd: epoch.mjd_mean,
          epoch: epoch.index,
          detector: band,
          wavelength_um: approx ? centre : wave,
          flux_mjy_sr: flux,
          err_mjy_sr: Number.isFinite(snr) && snr > 0 ? Math.abs(flux) / snr : NaN,
          approx,
        };
        return row;
      }),
    ).then((all) => {
      if (!alive) return;
      const rows = all.filter(
        (r): r is SpectrumRow & { approx: boolean } =>
          r !== null && Number.isFinite(r.flux_mjy_sr) && Number.isFinite(r.wavelength_um),
      );
      setState({ key, rows, approx: rows.some((r) => r.approx) });
    });
    return () => {
      alive = false;
    };
    // files is derived from meta; key covers the pixel and the result
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, meta]);

  const ready = state !== null && state.key === key;
  return {
    rows: ready ? state.rows : null,
    loading: pixel !== null && files.length > 0 && !ready,
    approx: ready ? state.approx : false,
    available: files.length > 0,
  };
}
