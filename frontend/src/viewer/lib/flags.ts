// SPHEREx pixel flags: bit value -> names the user can read.
// Names and bits come from meta.json "flag_bits" (read by science from the FLAGS header);
// the table below is the SPHEREx DR1 layout, used when meta.json has no "flag_bits".

export const DR1_FLAG_BITS: Record<string, number> = {
  TRANSIENT: 0,
  OVERFLOW: 1,
  SUR_ERROR: 2,
  NONFUNC: 6,
  DICHROIC: 7,
  MISSING_DATA: 9,
  HOT: 10,
  COLD: 11,
  FULLSAMPLE: 12,
  PHANMISS: 14,
  NONLINEAR: 15,
  PERSIST: 17,
  OUTLIER: 19,
  CROSSTALK: 20,
  SOURCE: 21,
  GHOST: 22,
  GHOST_FPA: 23,
  GHOST_EXT: 24,
  STREAK: 25,
  BLOOM: 26,
  SNOWBALL: 27,
  HALO: 28,
};

// Flags that make the pixel value unreliable (same list as science's BAD_FLAGS).
export const DR1_BAD_FLAGS = [
  "TRANSIENT", "OVERFLOW", "SUR_ERROR", "NONFUNC", "DICHROIC", "MISSING_DATA",
  "HOT", "COLD", "NONLINEAR", "PERSIST", "OUTLIER", "BLOOM", "SNOWBALL",
];

// Plain-language meaning, after the MSKD descriptions in the SPHEREx FLAGS header.
export const FLAG_TEXT: Record<string, string> = {
  TRANSIENT: "Cosmic-ray hit or other short event during the exposure",
  OVERFLOW: "Saturated: the source was too bright for the pixel",
  SUR_ERROR: "Error in onboard processing",
  NONFUNC: "Permanently unusable pixel",
  DICHROIC: "Low efficiency due to the dichroic beam splitter",
  MISSING_DATA: "Onboard data lost",
  HOT: "Hot pixel",
  COLD: "Anomalously low signal",
  FULLSAMPLE: "Full sample history is available (informational)",
  PHANMISS: "Phantom correction was not applied",
  NONLINEAR: "Nonlinearity correction cannot be applied reliably",
  PERSIST: "Afterglow from a bright source in an earlier exposure",
  OUTLIER: "Flagged as an outlier",
  CROSSTALK: "Echo of a bright source elsewhere on the detector",
  SOURCE: "A known source is at this pixel (informational)",
  GHOST: "Reflection of a bright source in this exposure",
  GHOST_FPA: "Reflection of a bright source on another detector",
  GHOST_EXT: "Reflection of a bright source outside the field of view",
  STREAK: "Affected by a streak",
  BLOOM: "Charge spilled over from a saturated pixel",
  SNOWBALL: "Part of a large cosmic-ray 'snowball' event",
  HALO: "Part of a glow around a bright transient",
};

export interface FlagInfo {
  name: string;
  bad: boolean; // makes the value unreliable
  text: string;
}

// Names of the bits set in `value`, bad ones first.
export function decodeFlags(
  value: number,
  bits: Record<string, number> = DR1_FLAG_BITS,
  bad: string[] = DR1_BAD_FLAGS,
): FlagInfo[] {
  if (!Number.isFinite(value) || value <= 0) return [];
  const v = Math.round(value);
  return Object.entries(bits)
    .filter(([, bit]) => Math.floor(v / 2 ** bit) % 2 === 1) // works past 31 bits too
    .map(([name]) => ({ name, bad: bad.includes(name), text: FLAG_TEXT[name] ?? name }))
    .sort((a, b) => Number(b.bad) - Number(a.bad));
}
