import { skyToPixel } from "./skyCoords";
import type { GaiaValidation, Meta } from "../types";

// MJD -> decimal year. Close enough (under a day) for proper motion.
export function mjdToYear(mjd: number): number {
  return 2000 + (mjd - 51544.5) / 365.25;
}

// Catalogue the prediction comes from. Gaia cannot see the coldest brown dwarfs.
export function gaiaSource(g: GaiaValidation): string {
  return g.status === "VALIDATED_NON_GAIA" ? "CatWISE" : "Gaia DR3";
}

// Predicted sky position on a given date, moved from target_epoch with the proper motion.
export function gaiaSkyAt(g: GaiaValidation | null | undefined, year: number): { ra: number; dec: number } | null {
  if (!g || g.predicted_ra == null || g.predicted_dec == null || g.target_epoch == null) return null;
  const dt = year - g.target_epoch;
  const dec = g.predicted_dec + ((g.pmdec_masyr ?? 0) * dt) / 3.6e6;
  const ra = g.predicted_ra + ((g.pmra_masyr ?? 0) * dt) / 3.6e6 / Math.cos((g.predicted_dec * Math.PI) / 180);
  return { ra, dec };
}

// Predicted pixel position on a given date, or null if there is no prediction.
export function gaiaPixelAt(meta: Meta, year: number): { x: number; y: number } | null {
  const sky = gaiaSkyAt(meta.gaia_validation, year);
  return sky ? skyToPixel(sky.ra, sky.dec, meta) : null;
}

// True if the pixel is on the image.
export function onImage(p: { x: number; y: number }, meta: Meta): boolean {
  const [height, width] = meta.shape;
  return p.x >= -0.5 && p.x <= width - 0.5 && p.y >= -0.5 && p.y <= height - 0.5;
}

// Distance from the image centre in arcseconds.
export function offsetArcsec(p: { x: number; y: number }, meta: Meta): number {
  const [height, width] = meta.shape;
  return Math.hypot(p.x - (width - 1) / 2, p.y - (height - 1) / 2) * meta.pixel_scale_arcsec;
}
