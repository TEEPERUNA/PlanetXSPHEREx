import type { PixelValues } from "../hooks/usePixelValues";
import { decodeFlags } from "../lib/flags";
import { pixelToSky } from "../lib/skyCoords";
import type { Band, Meta, Pixel } from "../types";

interface Props {
  pixel: Pixel | null;
  meta: Meta;
  band: Band;
  values: PixelValues | null;
  loading: boolean;
  gaiaNote?: string | null; // nearest Gaia star under the cursor, e.g. "Gaia DR3 star · G 12.3 · …"
}

// Number for display, or null when it is missing or NaN.
function num(v: number | undefined, digits: number): string | null {
  return v === undefined || !Number.isFinite(v) ? null : Number(v.toPrecision(digits)).toString();
}

// Pixel, sky coordinates and pixel values under the cursor (or the last tap).
export function CursorInfo({ pixel, meta, band, values, loading, gaiaNote }: Props) {
  if (!pixel) {
    return <p className="viewer__cursor">Point at the image to see coordinates and pixel values</p>;
  }

  const { ra, dec } = pixelToSky(pixel.x, pixel.y, meta);

  // Second line: brightness, zodi, S/N
  const sb = num(values?.sb, 4);
  const zodi = num(values?.zodi, 3);
  const snr = num(values?.snr, 3);
  const light = [
    sb && `SB ${sb} MJy/sr`,
    zodi && `zodi ${zodi} MJy/sr`,
    snr && `S/N ${snr}`,
  ].filter(Boolean);

  // Third line: wavelength and detector pixel
  const wave = values?.wave !== undefined && Number.isFinite(values.wave) ? values.wave.toFixed(3) : null;
  const bw = values?.bw !== undefined && Number.isFinite(values.bw) ? values.bw.toFixed(3) : null;
  const hasDet = Number.isFinite(values?.detX) && Number.isFinite(values?.detY);
  const instrument = [
    wave && (bw ? `λ ${wave} ± ${bw} µm` : `λ ${wave} µm`),
    hasDet && `detector (${Math.round(values!.detX!)}, ${Math.round(values!.detY!)})`,
  ].filter(Boolean);

  // Fourth line: SPHEREx flags on this pixel (from the representative image), bad ones first.
  const hasFlags = values?.flags !== undefined && Number.isFinite(values.flags);
  const flags = hasFlags ? decodeFlags(values!.flags!, meta.flag_bits, meta.flag_bad) : [];

  let note: string | null = null;
  if (loading) note = "Loading pixel values…";
  else if (band === "ALL" && light.length === 0) note = "Pick D1–D6 to see pixel values";

  return (
    <div className="viewer__cursor">
      <p>
        Pixel ({pixel.x}, {pixel.y}) · RA {ra.toFixed(4)}° · Dec {dec.toFixed(4)}°
      </p>
      {light.length > 0 && <p>{light.join(" · ")}</p>}
      {instrument.length > 0 && <p>{instrument.join(" · ")}</p>}
      {gaiaNote && <p className="viewer__cursor-gaia">{gaiaNote}</p>}
      {/* Always shown, so a missing FLAGS layer (older results, ALL band) is visible too. */}
      {!loading && (
        <p className="viewer__flags">
          Flags:{" "}
          {!hasFlags
            ? band === "ALL"
              ? "pick D1–D6 to see flags"
              : "not available for this result"
            : flags.length === 0
            ? "none"
            : flags.map((f, i) => (
                <span key={f.name}>
                  {i > 0 && ", "}
                  <abbr title={f.text} className={f.bad ? "viewer__flag is-bad" : "viewer__flag"}>
                    {f.name}
                  </abbr>
                </span>
              ))}
        </p>
      )}
      {note && <p className="viewer__cursor-note">{note}</p>}
    </div>
  );
}
