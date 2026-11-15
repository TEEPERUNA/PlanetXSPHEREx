// Rank badge, XP bar, mission count, hunt-mode switch; plus the mission log and toasts.
import { MISSIONS, rankFor, type Progress } from "./game";
import type { Toast } from "./useGame";

interface HudProps {
  progress: Progress;
  hunting: boolean;
  canHunt: boolean; // a result with a catalogue position is on screen
  onHunt: () => void;
  onMissions: () => void;
}

export function GameHud({ progress, hunting, canHunt, onHunt, onMissions }: HudProps) {
  const rank = rankFor(progress.xp);
  const span = rank.next === null ? 1 : rank.next - rank.floor;
  const fill = rank.next === null ? 1 : (progress.xp - rank.floor) / span;
  return (
    <div className="game-hud">
      <div className="game-hud__rank" title={`Rank ${rank.index + 1} of 6`}>
        <span className="game-hud__chevrons" aria-hidden="true">
          {Array.from({ length: 6 }, (_, i) => (
            <span key={i} className={i <= rank.index ? "is-on" : undefined} />
          ))}
        </span>
        <span className="game-hud__name">{rank.name}</span>
      </div>
      <div className="game-hud__xp" aria-label={`${progress.xp} XP`}>
        <div className="game-hud__bar">
          <span style={{ width: `${Math.round(fill * 100)}%` }} />
        </div>
        <span className="game-hud__nums">
          {progress.xp} XP{rank.next !== null && <span className="game-hud__next"> / {rank.next}</span>}
        </span>
      </div>
      <button type="button" onClick={onMissions} title="Mission log (M)">
        Missions {progress.done.length}/{MISSIONS.length}
      </button>
      <button
        type="button"
        className={"game-hud__hunt" + (hunting ? " is-hunting" : "")}
        aria-pressed={hunting}
        disabled={!canHunt}
        onClick={onHunt}
        title={canHunt ? "Hunt mode (H): click the moving star" : "Needs a target with a catalogue position"}
      >
        {hunting ? "Hunting…" : "Hunt mode"}
      </button>
    </div>
  );
}

interface LogProps {
  progress: Progress;
  onClose: () => void;
  onReset: () => void;
}

export function MissionLog({ progress, onClose, onReset }: LogProps) {
  const rank = rankFor(progress.xp);
  return (
    <div className="mission-log" role="dialog" aria-modal="true" aria-label="Mission log" onClick={onClose}>
      <div className="mission-log__panel" onClick={(e) => e.stopPropagation()}>
        <header className="mission-log__head">
          <p className="mission-log__eyebrow">◆ Mission log</p>
          <h2>
            {rank.name} · {progress.xp} XP
          </h2>
          <button type="button" onClick={onClose} aria-label="Close mission log">
            Close
          </button>
        </header>
        <ol className="mission-log__list">
          {MISSIONS.map((m) => {
            const done = progress.done.includes(m.id);
            return (
              <li key={m.id} className={done ? "is-done" : undefined}>
                <span className="mission-log__check" aria-hidden="true">
                  {done ? "✓" : ""}
                </span>
                <span className="mission-log__text">
                  <strong>{m.title}</strong>
                  <span>{m.brief}</span>
                </span>
                <span className="mission-log__xp">+{m.xp}</span>
              </li>
            );
          })}
        </ol>
        <p className="mission-log__meta">
          Destinations visited {progress.visited.length}/5 · Targets locked {progress.locked.length}
        </p>
        <p className="mission-log__keys">
          Keys: <kbd>1</kbd>–<kbd>5</kbd> set course · <kbd>H</kbd> hunt mode · <kbd>M</kbd> missions
        </p>
        <button type="button" className="mission-log__reset" onClick={onReset}>
          Reset progress
        </button>
      </div>
    </div>
  );
}

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.kind}`}>
          <span className="toast__title">{t.title}</span>
          {t.detail && <span className="toast__detail">{t.detail}</span>}
        </div>
      ))}
    </div>
  );
}
