// A ship as inline SVG (header badge, hangar cards).
import type { ShipDesign } from "./ships";

export function ShipIcon({ ship, size = 40, locked = false }: { ship: ShipDesign; size?: number; locked?: boolean }) {
  const [cx, cy, rx, ry] = ship.cockpit;
  return (
    <svg
      className={"ship-icon" + (locked ? " is-locked" : "")}
      width={size}
      height={size}
      viewBox="-22 -22 44 48"
      aria-hidden="true"
      style={{ color: ship.accent }}
    >
      {ship.engines.map(([x, y], i) => (
        <path key={i} className="ship-icon__flame" d={`M${x - 2} ${y} L${x + 2} ${y} L${x} ${y + 8} Z`} fill="currentColor" />
      ))}
      <path d={ship.body} fill={locked ? "#334155" : ship.hull} stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill={locked ? "#1e293b" : "currentColor"} />
    </svg>
  );
}
