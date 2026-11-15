// demo/beyond: missions, XP and ranks. Every mission rewards a real use of the tool.

export type MissionId =
  | "first-jump"
  | "lock-on"
  | "difference"
  | "blink"
  | "spectro"
  | "deep-cold"
  | "explorer"
  | "grand-tour"
  | "sharpshooter"
  | "engineer"
  | "hail"
  | "defender"
  | "ace";

export interface Mission {
  id: MissionId;
  title: string;
  brief: string;
  xp: number;
}

export const MISSIONS: Mission[] = [
  { id: "first-jump", title: "First jump", brief: "Warp to any position in the sky.", xp: 50 },
  { id: "lock-on", title: "Lock on", brief: "Hunt mode: click the moving star on the viewscreen.", xp: 150 },
  { id: "difference", title: "Spot the change", brief: "Open the difference image: last visit minus first.", xp: 75 },
  { id: "blink", title: "Blink comparator", brief: "Compare two dates and watch the star jump.", xp: 75 },
  { id: "spectro", title: "Spectroscopist", brief: "Switch the spectrum to all measurements.", xp: 75 },
  { id: "deep-cold", title: "Deep cold", brief: "Visit WISE 0855, the coldest brown dwarf known.", xp: 100 },
  { id: "explorer", title: "Explorer", brief: "Set course to coordinates of your own.", xp: 100 },
  { id: "grand-tour", title: "Grand tour", brief: "Visit all five destinations.", xp: 200 },
  { id: "sharpshooter", title: "Sharpshooter", brief: "Lock on to three different targets.", xp: 250 },
  { id: "engineer", title: "Engineer", brief: "Power up the ship's sound system.", xp: 25 },
  { id: "hail", title: "First contact", brief: "Click a passing ship to scan it.", xp: 50 },
  { id: "defender", title: "Defender", brief: "Fly the simulator while the ship is in warp.", xp: 75 },
  { id: "ace", title: "Ace pilot", brief: "Score 1000 points in the flight simulator.", xp: 150 },
];

export const SCAN_XP = 20; // each new ship scanned
export const MAX_FLIGHT_XP = 200; // per simulator run

export const LOCK_XP = 50; // each new target locked
export const DESTINATIONS = 5;

const RANKS: [number, string][] = [
  [0, "Cadet"],
  [100, "Ensign"],
  [300, "Lieutenant"],
  [650, "Commander"],
  [1100, "Captain"],
  [1700, "Admiral"],
];
export const RANK_NAMES = RANKS.map(([, name]) => name);

export interface Rank {
  index: number;
  name: string;
  floor: number; // XP where this rank starts
  next: number | null; // XP for the next rank
}

export function rankFor(xp: number): Rank {
  let i = 0;
  while (i + 1 < RANKS.length && xp >= RANKS[i + 1][0]) i++;
  return { index: i, name: RANKS[i][1], floor: RANKS[i][0], next: RANKS[i + 1]?.[0] ?? null };
}

export interface Progress {
  xp: number;
  done: MissionId[];
  visited: string[]; // destination keys
  locked: string[]; // targets locked in hunt mode
  scanned: string[]; // passing ships scanned
  ship: string; // flown ship id
  best: number; // best simulator score
}

export const EMPTY: Progress = { xp: 0, done: [], visited: [], locked: [], scanned: [], ship: "kestrel", best: 0 };
const KEY = "starx-game-v1";

// Progress lives in this browser only. Storage can be blocked, so fail quietly.
export function loadProgress(): Progress {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<Progress>) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function saveProgress(p: Progress): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* private mode: progress lasts for this visit only */
  }
}
