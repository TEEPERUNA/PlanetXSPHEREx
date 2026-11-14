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
