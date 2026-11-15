// demo/beyond: spaceships. One shape definition (SVG path, nose up, about 36×36 units
// around 0,0) is used both in React SVG (hangar, header) and on canvas (game, star field).

export interface ShipDesign {
  id: string;
  name: string;
  role: string;
  unlockRank: number; // rank index needed (0 = Cadet)
  accent: string; // UI colour when this ship is flown
  accentRgb: string; // same colour as "r g b" for rgb(... / alpha)
  hull: string; // body fill
  body: string; // SVG path of the hull
  cockpit: [number, number, number, number]; // ellipse cx, cy, rx, ry
  engines: [number, number][]; // engine exhausts (x, y)
  stats: { speed: number; fireRate: number; hull: number }; // 1–5
}

export const SHIPS: ShipDesign[] = [
  {
    id: "kestrel",
    name: "Kestrel",
    role: "Survey scout",
    unlockRank: 0,
    accent: "#22d3ee",
    accentRgb: "34 211 238",
    hull: "#cbd5e1",
    body: "M0 -18 L6 -4 L15 9 L15 12 L5 9 L3 14 L-3 14 L-5 9 L-15 12 L-15 9 L-6 -4 Z",
    cockpit: [0, -6, 2.6, 5],
    engines: [[-3, 14], [3, 14]],
    stats: { speed: 4, fireRate: 3, hull: 2 },
  },
  {
    id: "atlas",
    name: "Atlas",
    role: "Heavy cruiser",
    unlockRank: 2,
    accent: "#fbbf24",
    accentRgb: "251 191 36",
    hull: "#e2e8f0",
    body: "M0 -17 L5 -9 L5 3 L16 5 L17 13 L6 11 L5 16 L-5 16 L-6 11 L-17 13 L-16 5 L-5 3 L-5 -9 Z",
    cockpit: [0, -8, 2.4, 4],
    engines: [[-12, 13], [0, 16], [12, 13]],
    stats: { speed: 2, fireRate: 4, hull: 5 },
  },
  {
    id: "vega",
    name: "Vega",
    role: "Interceptor",
    unlockRank: 4,
    accent: "#f472b6",
    accentRgb: "244 114 182",
    hull: "#f1f5f9",
    body: "M0 -19 L4 -6 L16 -13 L11 4 L4 6 L3 14 L-3 14 L-4 6 L-11 4 L-16 -13 L-4 -6 Z",
    cockpit: [0, -7, 2.2, 5],
    engines: [[-3, 14], [3, 14]],
    stats: { speed: 5, fireRate: 5, hull: 1 },
  },
];

export const shipById = (id: string) => SHIPS.find((s) => s.id === id) ?? SHIPS[0];

// Other ships in the star field: named after real observatories.
export const TRAFFIC = [
  "Hubble",
  "Spitzer",
  "Kepler",
  "Herschel",
  "Euclid",
  "Roman",
  "Webb",
  "NEOWISE",
  "Planck",
  "Chandra",
];

// Messages they send: real facts about the sky this tool looks at.
export const HAILS = [
  "Barnard's Star moves 10.4″ a year, faster than any other star in our sky.",
  "WISE 0855 is about 250 K, roughly as cold as the North Pole in winter.",
  "SPHEREx maps the whole sky in 102 infrared colours, again every six months.",
  "Gaia DR3 measured the positions of 1.8 billion stars.",
  "Epsilon Indi B is a pair of brown dwarfs only 12 light-years from the Sun.",
  "R Draconis is a Mira variable: it brightens and fades over about 8 months.",
  "RW Aurigae's disk has dimmed the star again and again since 2010.",
  "Infrared light passes through dust that hides stars from visible-light telescopes.",
  "A brown dwarf is too light to fuse hydrogen: more than a planet, less than a star.",
  "Proper motion is how far a star drifts on the sky each year, in arcseconds.",
];

// Canvas: draw a ship at (x, y), nose rotated by `angle` (0 = up), with engine flames.
const pathCache = new Map<string, Path2D>();
export function drawShip(
  ctx: CanvasRenderingContext2D,
  ship: ShipDesign,
  x: number,
  y: number,
  scale: number,
  angle = 0,
  thrust = 1,
  t = 0,
): void {
  let path = pathCache.get(ship.id);
  if (!path) {
    path = new Path2D(ship.body);
    pathCache.set(ship.id, path);
  }
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.scale(scale, scale);

  // Engine flames (flicker with time)
  for (const [ex, ey] of ship.engines) {
    const len = (6 + thrust * 10) * (0.8 + 0.2 * Math.sin(t * 0.03 + ex));
    const g = ctx.createLinearGradient(ex, ey, ex, ey + len);
    g.addColorStop(0, "rgba(255,255,255,0.95)");
    g.addColorStop(0.3, ship.accent);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(ex - 2.2, ey);
    ctx.lineTo(ex + 2.2, ey);
    ctx.lineTo(ex, ey + len);
    ctx.closePath();
    ctx.fill();
  }

  ctx.shadowColor = ship.accent;
  ctx.shadowBlur = 10;
  ctx.fillStyle = ship.hull;
  ctx.fill(path);
  ctx.shadowBlur = 0;
  ctx.strokeStyle = ship.accent;
  ctx.lineWidth = 1.2;
  ctx.stroke(path);

  const [cx, cy, rx, ry] = ship.cockpit;
  ctx.fillStyle = ship.accent;
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}
