// Types for meta.json (see CONTRACT.md) and the viewer status.
// Only the keys the viewer uses are listed. Other keys are ignored.

export type Detector = "D1" | "D2" | "D3" | "D4" | "D5" | "D6";
export type Band = "ALL" | Detector;

// Fixed display order for the band buttons.
export const BANDS: Band[] = ["ALL", "D1", "D2", "D3", "D4", "D5", "D6"];

export interface Epoch {
  index: number;
  date: string; // "2025-08-25"
  mjd_mean: number;
  n_images: number; // all detectors together
  detectors: Partial<Record<Detector, { n_images: number; flagged_frac?: number | null }>>;
}

export interface BandOutput {
  frames: string[]; // "frames/D2/epoch4.png", relative to baseUrl
  gif?: string;
  diff?: string;
  fits?: string[]; // "epoch3_D2.fits": epoch stack, surface brightness (MJy/sr)
  pixels?: string[]; // per-pixel layers SB, ZODI, SNR, WAVE, BW, DETX, DETY (planned, see plan.md)
  combined?: string; // "combined_D2.png": coadded image of all epochs
  combined_fits?: string; // "combined_D2.fits": coadded FITS stack of all epochs
}

// Science's position check against Gaia DR3 (or CatWISE for objects Gaia cannot see).
// Only for the challenge targets. Every field can be missing or null.
export interface GaiaValidation {
  status?: string; // "CONFIRMED_MATCH", "VALIDATED_NON_GAIA", "QUERY_ERROR", ...
  message?: string;
  predicted_ra?: number | null; // degrees, at target_epoch
  predicted_dec?: number | null;
  pmra_masyr?: number | null; // proper motion, RA already includes cos(dec)
  pmdec_masyr?: number | null;
  target_epoch?: number | null; // decimal year
  residual_offset_arcsec?: number | null;
}

export interface Meta {
  target: string;
  ra_deg: number; // image centre
  dec_deg: number;
  pixel_scale_arcsec: number;
  shape: [number, number]; // [height, width] in SPHEREx pixels
  detector_ranges_um?: Partial<Record<Detector, [number, number]>>;
  epochs: Epoch[];
  outputs: Partial<Record<Band, BandOutput>>;
  spectrum?: string;
  credit?: string;
  gaia_validation?: GaiaValidation | null;
  inverted?: boolean; // images drawn as a negative (dark sources on a light sky)
  flag_bits?: Record<string, number>; // SPHEREx flag planes, name -> bit
  flag_bad?: string[]; // flags counted in flagged_frac
}

// A finished result: meta.json + absolute base URL for its files.
export interface Result {
  meta: Meta;
  baseUrl: string;
}

// What the app tells the viewer to show.
// `preview` is optional: the quick result the backend sends while the full run continues.
export type ViewerStatus =
  | { kind: "empty" }
  | { kind: "loading"; stage: string; done: number; total: number; preview?: Result }
  | ({ kind: "done" } & Result)
  | { kind: "error"; message: string };

// One image in the blink, with the epoch it belongs to.
export interface Frame {
  src: string;
  epoch: Epoch;
}

// A SPHEREx pixel, (0, 0) = top left.
export interface Pixel {
  x: number;
  y: number;
}
