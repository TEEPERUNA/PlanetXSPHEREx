// Ship boot screen: system lines type in character by character, then the bridge
// powers on. Click skips it.
import { useEffect, useState } from "react";

const LINES = [
  "STARx DEEP-SPACE OBSERVATORY · BOOT SEQUENCE",
  "> Reactor core .................... ONLINE",
  "> Navigation computer ............. ONLINE",
  "> SPHEREx uplink (NASA/IPAC IRSA) . LINKED",
  "> Gaia DR3 star charts ............ LOADED",
  "> Spectrograph 0.75–5.0 µm, 102 ch  CALIBRATED",
  "ALL SYSTEMS NOMINAL. WELCOME ABOARD, COMMANDER.",
];

const CHARS_PER_TICK = 2;
const TICK_MS = 14;

export function BootSequence({ onDone }: { onDone: () => void }) {
  // Position of the typewriter: line and character within it.
  const [pos, setPos] = useState({ line: 0, char: 0 });

  useEffect(() => {
    if (pos.line >= LINES.length) {
      const t = setTimeout(onDone, 900);
      return () => clearTimeout(t);
    }
    const lineDone = pos.char >= LINES[pos.line].length;
    const t = setTimeout(
      () => setPos((p) => (lineDone ? { line: p.line + 1, char: 0 } : { ...p, char: p.char + CHARS_PER_TICK })),
      lineDone ? 120 : TICK_MS,
    );
    return () => clearTimeout(t);
  }, [pos, onDone]);

  return (
    <div className="boot" onClick={onDone} role="presentation">
      <div className="boot__screen" aria-live="polite">
        {LINES.map((line, i) => {
          if (i > pos.line) return null;
          const text = i < pos.line ? line : line.slice(0, pos.char);
          return (
            <p key={i} className={i === LINES.length - 1 ? "boot__final" : undefined}>
              {text}
              {i === pos.line && <span className="boot__cursor" aria-hidden="true" />}
            </p>
          );
        })}
      </div>
      <p className="boot__skip">Click to skip</p>
    </div>
  );
}
