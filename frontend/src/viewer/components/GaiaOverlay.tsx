import { gaiaPixelAt, mjdToYear, onImage } from "../lib/gaia";
import type { Epoch, Meta } from "../types";

interface Props {
  meta: Meta;
  epochs: Epoch[]; // epochs of the current band, in blink order
  current: Epoch | null; // epoch on screen; null in diff mode
}

// Drawn inside the SVG overlay (viewBox = SPHEREx pixels).
// Small dots = predicted track over all epochs, circle = position on the current date.
// In diff mode: dashed circle = first epoch, solid circle = last epoch.
export function GaiaOverlay({ meta, epochs, current }: Props) {
  // SVG pixel i spans [i, i + 1], so its centre is i + 0.5.
  const at = (e: Epoch) => {
    const p = gaiaPixelAt(meta, mjdToYear(e.mjd_mean));
    return p && onImage(p, meta) ? { x: p.x + 0.5, y: p.y + 0.5 } : null;
  };

  const track = epochs.map(at).filter((p): p is { x: number; y: number } => p !== null);
  if (track.length === 0) return null;

  const first = epochs.length ? at(epochs[0]) : null;
  const last = epochs.length ? at(epochs[epochs.length - 1]) : null;
  const now = current ? at(current) : null;

  return (
    <g className="gaia">
      {track.map((p, i) => (
        <circle key={i} className="gaia__dot" cx={p.x} cy={p.y} r={0.25} />
      ))}
      {current
        ? now && <circle className="gaia__ring" cx={now.x} cy={now.y} r={1.6} />
        : (
          <>
            {first && <circle className="gaia__ring gaia__ring--first" cx={first.x} cy={first.y} r={1.6} />}
            {last && <circle className="gaia__ring" cx={last.x} cy={last.y} r={1.6} />}
          </>
        )}
    </g>
  );
}
