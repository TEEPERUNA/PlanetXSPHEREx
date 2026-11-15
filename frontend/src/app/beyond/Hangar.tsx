// Hangar: pick the ship you fly. Ships unlock with rank; each one recolours the bridge.
import { RANK_NAMES, rankFor } from "./game";
import { SHIPS } from "./ships";
import { ShipIcon } from "./ShipIcon";

interface Props {
  xp: number;
  current: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}

const STAT_LABELS: [keyof (typeof SHIPS)[number]["stats"], string][] = [
  ["speed", "Speed"],
  ["fireRate", "Fire rate"],
  ["hull", "Hull"],
];

export function Hangar({ xp, current, onSelect, onClose }: Props) {
  const rank = rankFor(xp);
  return (
    <div className="mission-log hangar" role="dialog" aria-modal="true" aria-label="Hangar" onClick={onClose}>
      <div className="mission-log__panel hangar__panel" onClick={(e) => e.stopPropagation()}>
        <header className="mission-log__head">
          <p className="mission-log__eyebrow">◆ Hangar</p>
          <h2>Choose your ship</h2>
          <button type="button" onClick={onClose} aria-label="Close hangar">
            Close
          </button>
        </header>
        <div className="hangar__grid">
          {SHIPS.map((s) => {
            const locked = rank.index < s.unlockRank;
            const active = s.id === current;
            return (
              <button
                key={s.id}
                type="button"
                className={"hangar__ship" + (active ? " is-active" : "") + (locked ? " is-locked" : "")}
                style={{ ["--ship" as string]: s.accent }}
                disabled={locked}
                aria-pressed={active}
                onClick={() => onSelect(s.id)}
              >
                <span className="hangar__art">
                  <ShipIcon ship={s} size={92} locked={locked} />
                </span>
                <span className="hangar__name">{s.name}</span>
                <span className="hangar__role">{s.role}</span>
                <span className="hangar__stats">
                  {STAT_LABELS.map(([key, label]) => (
                    <span key={key} className="hangar__stat">
                      <span>{label}</span>
                      <span className="hangar__pips">
                        {Array.from({ length: 5 }, (_, i) => (
                          <i key={i} className={i < s.stats[key] ? "is-on" : undefined} />
                        ))}
                      </span>
                    </span>
                  ))}
                </span>
                <span className="hangar__status">
                  {locked ? `Unlocks at ${RANK_NAMES[s.unlockRank]}` : active ? "Flying" : "Select"}
                </span>
              </button>
            );
          })}
        </div>
        <p className="mission-log__keys">Each ship recolours the bridge and flies differently in the simulator.</p>
      </div>
    </div>
  );
}
