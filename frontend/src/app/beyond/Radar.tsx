// Navigation radar: the whole sky as a disc (north celestial pole in the centre,
// south pole on the rim, RA around the circle). Blips are the challenge targets;
// clicking one sets course. The ring marks the position on screen right now.
import type { Target } from "../../api";

interface Props {
  targets: Target[];
  activeKey: string | null;
  here: { ra: number; dec: number } | null; // current image centre
  onSelect: (t: Target) => void;
}

const C = 100; // centre of the 200×200 viewBox
const R = 88; // radius of the sky disc

// RA/Dec (degrees) -> point on the disc. RA 0h at the top, increasing clockwise.
function toDisc(ra: number, dec: number) {
  const r = ((90 - dec) / 180) * R;
  const a = (ra * Math.PI) / 180;
  return { x: C + r * Math.sin(a), y: C - r * Math.cos(a) };
}

export function Radar({ targets, activeKey, here, onSelect }: Props) {
  const pos = here ? toDisc(here.ra, here.dec) : null;
  return (
    <div className="radar">
      <p className="radar__title">Nav radar</p>
      <svg viewBox="0 0 200 200" role="group" aria-label="Sky map of the destinations. North pole in the centre.">
        <defs>
          <radialGradient id="radar-bg">
            <stop offset="0%" stopColor="rgb(34 211 238 / 0.18)" />
            <stop offset="100%" stopColor="rgb(34 211 238 / 0.02)" />
          </radialGradient>
          <linearGradient id="radar-sweep" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="rgb(34 211 238 / 0)" />
            <stop offset="100%" stopColor="rgb(34 211 238 / 0.55)" />
          </linearGradient>
        </defs>
        <circle cx={C} cy={C} r={R} fill="url(#radar-bg)" className="radar__rim" />
        {/* Declination rings at +60, +30, 0 (equator), -30, -60 */}
        {[60, 30, 0, -30, -60].map((d) => (
          <circle key={d} cx={C} cy={C} r={((90 - d) / 180) * R} className={d === 0 ? "radar__equator" : "radar__ring"} />
        ))}
        <line x1={C} y1={C - R} x2={C} y2={C + R} className="radar__ring" />
        <line x1={C - R} y1={C} x2={C + R} y2={C} className="radar__ring" />
        <text x={C} y={C - R - 3} className="radar__label" textAnchor="middle">0h</text>
        <text x={C + R + 3} y={C + 3} className="radar__label">6h</text>

        {/* Rotating sweep */}
        <g className="radar__sweep">
          <path d={`M ${C} ${C} L ${C + R} ${C} A ${R} ${R} 0 0 0 ${C + R * Math.cos(-0.6)} ${C + R * Math.sin(-0.6)} Z`} fill="url(#radar-sweep)" />
        </g>

        {targets.map((t) => {
          const p = toDisc(t.ra, t.dec);
          const active = t.key === activeKey;
          // Labels point away from the centre so neighbours in the same direction don't collide;
          // blips close to the pole get their label underneath.
          const nearPole = Math.hypot(p.x - C, p.y - C) < 25;
          const label = nearPole
            ? { x: p.x, y: p.y + 11, anchor: "middle" as const }
            : p.x < C
              ? { x: p.x - 5, y: p.y - 4, anchor: "end" as const }
              : { x: p.x + 5, y: p.y - 4, anchor: "start" as const };
          return (
            <g
              key={t.key}
              className={active ? "radar__blip is-active" : "radar__blip"}
              role="button"
              tabIndex={0}
              aria-label={`Set course to ${t.label}`}
              onClick={() => onSelect(t)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(t)}
            >
              <circle cx={p.x} cy={p.y} r={9} className="radar__hit" />
              <circle cx={p.x} cy={p.y} r={active ? 3.6 : 2.6} className="radar__dot" />
              <text x={label.x} y={label.y} textAnchor={label.anchor} className="radar__name">
                {t.label}
              </text>
            </g>
          );
        })}

        {pos && <circle cx={pos.x} cy={pos.y} r={6} className="radar__here" />}
      </svg>
      <p className="radar__hint">North pole in the centre · click a blip to set course</p>
    </div>
  );
}
