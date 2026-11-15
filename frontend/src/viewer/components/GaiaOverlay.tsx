import { gaiaPixelAt, mjdToYear, onImage } from "../lib/gaia";
import type { Source, StarPixel } from "../lib/gaiaField";
import type { Epoch, Meta } from "../types";

// Field stars drawn as rings, at most this many (brightest first); fainter ones as dots.
const MAX_RINGS = 25;
const MAX_DOTS = 60;

interface Props {
  meta: Meta;
  epochs: Epoch[]; // epochs of the current band, in blink order
  current: Epoch | null; // epoch on screen; null in diff mode
  field: StarPixel[]; // Gaia stars on the image at the date on screen, brightest first
  lonely: Source[]; // point sources with no Gaia star nearby
}

// Ring size from Gaia G magnitude: bright stars bigger (in SPHEREx pixels).
function ringRadius(g: number | null): number {
  if (g === null) return 0.6;
  return Math.max(0.55, Math.min(1.5, 1.5 - (g - 8) * 0.1));
}

// Drawn inside the SVG overlay (viewBox = SPHEREx pixels). SVG pixel i spans [i, i + 1],
// so a pixel centre is i + 0.5.
// - Target (green): predicted position on the current date, dots = track over all epochs.
//   In diff mode: dashed = first epoch, solid = last epoch.
// - Field (light rings/dots): every Gaia star at the date on screen.
// - No Gaia match (orange dashed squares): sources seen by SPHEREx that Gaia does not list.
export function GaiaOverlay({ meta, epochs, current, field, lonely }: Props) {
  const at = (e: Epoch) => {
    const p = gaiaPixelAt(meta, mjdToYear(e.mjd_mean));
    return p && onImage(p, meta) ? { x: p.x + 0.5, y: p.y + 0.5 } : null;
  };

  const track = epochs.map(at).filter((p): p is { x: number; y: number } => p !== null);
  const first = epochs.length ? at(epochs[0]) : null;
  const last = epochs.length ? at(epochs[epochs.length - 1]) : null;
  const now = current ? at(current) : last;

  // Leave out the field star that is the target itself, the green ring already marks it.
  const others = field.filter((s) => !now || Math.hypot(s.x + 0.5 - now.x, s.y + 0.5 - now.y) > 1);
  const rings = others.slice(0, MAX_RINGS);
  const dots = others.slice(MAX_RINGS, MAX_RINGS + MAX_DOTS);

  return (
    <g className={meta.inverted ? "gaia gaia--inverted" : "gaia"}>
      {dots.map((s) => (
        <circle key={s.star.id} className="gaia__field-dot" cx={s.x + 0.5} cy={s.y + 0.5} r={0.18} />
      ))}
      {rings.map((s) => (
        <circle key={s.star.id} className="gaia__field" cx={s.x + 0.5} cy={s.y + 0.5} r={ringRadius(s.star.g)} />
      ))}

      {lonely.map((s) => (
        <rect key={`${s.x},${s.y}`} className="gaia__nomatch" x={s.x - 1} y={s.y - 1} width={3} height={3} />
      ))}

      {track.map((p, i) => (
        <circle key={i} className="gaia__dot" cx={p.x} cy={p.y} r={0.25} />
      ))}
      {current
        ? now && <circle className="gaia__ring" cx={now.x} cy={now.y} r={1.6} />
        : track.length > 0 && (
            <>
              {first && <circle className="gaia__ring gaia__ring--first" cx={first.x} cy={first.y} r={1.6} />}
              {last && <circle className="gaia__ring" cx={last.x} cy={last.y} r={1.6} />}
            </>
          )}
    </g>
  );
}
