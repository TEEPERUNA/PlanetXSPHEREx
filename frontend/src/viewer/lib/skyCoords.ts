import type { Meta } from "../types";

// SPHEREx pixel -> sky coordinates in degrees.
// North is up and east is left, so RA grows to the left.
// A flat-sky approximation, fine for a cutout of a few arcminutes.
export function pixelToSky(x: number, y: number, meta: Meta): { ra: number; dec: number } {
  const [height, width] = meta.shape;
  const centreX = (width - 1) / 2; // 15 for a 31 px image
  const centreY = (height - 1) / 2;
  const scaleDeg = meta.pixel_scale_arcsec / 3600;

  const dec = meta.dec_deg - (y - centreY) * scaleDeg;
  const ra = meta.ra_deg - ((x - centreX) * scaleDeg) / Math.cos((meta.dec_deg * Math.PI) / 180);

  return { ra: (ra + 360) % 360, dec };
}

// Sky coordinates -> SPHEREx pixel (the opposite of pixelToSky).
// Whole numbers are pixel centres, so (15, 15) is the image centre.
export function skyToPixel(ra: number, dec: number, meta: Meta): { x: number; y: number } {
  const [height, width] = meta.shape;
  const scaleDeg = meta.pixel_scale_arcsec / 3600;
  const dRa = ((ra - meta.ra_deg + 540) % 360) - 180; // handles RA wrapping past 0°/360°

  const x = (width - 1) / 2 - (dRa * Math.cos((meta.dec_deg * Math.PI) / 180)) / scaleDeg;
  const y = (height - 1) / 2 - (dec - meta.dec_deg) / scaleDeg;
  return { x, y };
}
