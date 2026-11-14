// One row of spectrum.csv = one SPHEREx image.
export interface SpectrumRow {
  mjd: number;
  epoch: number;
  detector: string;
  wavelength_um: number;
  flux_mjy_sr: number;
  err_mjy_sr: number;
}

// Parse spectrum.csv. Columns are found by name, so extra columns are fine.
// flagged_frac is skipped on purpose (it is always 1.0 for now).
export function parseSpectrum(text: string): SpectrumRow[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];

  const header = lines[0].split(",").map((name) => name.trim());
  const col = (name: string) => header.indexOf(name);
  const c = {
    mjd: col("mjd"),
    epoch: col("epoch"),
    detector: col("detector"),
    wavelength: col("wavelength_um"),
    flux: col("flux_mjy_sr"),
    err: col("err_mjy_sr"),
  };

  const rows: SpectrumRow[] = [];
  for (const line of lines.slice(1)) {
    const cells = line.split(",");
    const row: SpectrumRow = {
      mjd: Number(cells[c.mjd]),
      epoch: Number(cells[c.epoch]),
      detector: (cells[c.detector] ?? "").trim(),
      wavelength_um: Number(cells[c.wavelength]),
      flux_mjy_sr: Number(cells[c.flux]),
      err_mjy_sr: Number(cells[c.err]),
    };
    // Skip broken rows instead of drawing NaN.
    if (Number.isFinite(row.wavelength_um) && Number.isFinite(row.flux_mjy_sr)) rows.push(row);
  }
  return rows;
}
