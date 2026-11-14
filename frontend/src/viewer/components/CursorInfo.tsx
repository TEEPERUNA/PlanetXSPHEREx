import { pixelToSky } from "../lib/skyCoords";
import type { Meta, Pixel } from "../types";

interface Props {
  pixel: Pixel | null;
  meta: Meta;
}

// Pixel and sky coordinates under the cursor (or the last tap).
export function CursorInfo({ pixel, meta }: Props) {
  if (!pixel) {
    return <p className="viewer__cursor">Point at the image to see coordinates</p>;
  }

  const { ra, dec } = pixelToSky(pixel.x, pixel.y, meta);
  return (
    <p className="viewer__cursor">
      Pixel ({pixel.x}, {pixel.y}) · RA {ra.toFixed(4)}° · Dec {dec.toFixed(4)}°
    </p>
  );
}
