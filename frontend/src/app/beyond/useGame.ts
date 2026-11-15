// Game state: XP, missions, visited destinations, locked targets, and toasts.
import { useCallback, useEffect, useRef, useState } from "react";
import { DESTINATIONS, LOCK_XP, MISSIONS, EMPTY, loadProgress, rankFor, saveProgress, type MissionId, type Progress } from "./game";

export interface Toast {
  id: number;
  kind: "mission" | "rank" | "lock" | "info";
  title: string;
  detail?: string;
}

export interface GameEvents {
  onMission?: () => void; // sound hooks
  onRank?: () => void;
}

export function useGame(events: GameEvents = {}) {
  const [progress, setProgress] = useState<Progress>(loadProgress);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const ref = useRef(progress); // latest progress, for chained updates in one event
  const nextId = useRef(1);
  const eventsRef = useRef(events);
  eventsRef.current = events;

  useEffect(() => saveProgress(progress), [progress]);

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = nextId.current++;
    setToasts((list) => [...list.slice(-3), { ...t, id }]);
    setTimeout(() => setToasts((list) => list.filter((x) => x.id !== id)), 4200);
  }, []);

  // Apply a change, then announce any rank-up.
  const update = useCallback(
    (change: (p: Progress) => Progress) => {
      const before = ref.current;
      const after = change(before);
      if (after === before) return;
      ref.current = after;
      setProgress(after);
      const r0 = rankFor(before.xp);
      const r1 = rankFor(after.xp);
      if (r1.index > r0.index) {
        toast({ kind: "rank", title: `Promoted to ${r1.name}`, detail: `${after.xp} XP` });
        eventsRef.current.onRank?.();
      }
    },
    [toast],
  );

  const complete = useCallback(
    (id: MissionId) => {
      const m = MISSIONS.find((x) => x.id === id);
      if (!m || ref.current.done.includes(id)) return;
      update((p) => ({ ...p, xp: p.xp + m.xp, done: [...p.done, id] }));
      toast({ kind: "mission", title: `Mission complete · ${m.title}`, detail: `+${m.xp} XP` });
      eventsRef.current.onMission?.();
    },
    [toast, update],
  );

  const visit = useCallback(
    (key: string) => {
      if (!ref.current.visited.includes(key)) update((p) => ({ ...p, visited: [...p.visited, key] }));
      if (ref.current.visited.length >= DESTINATIONS) complete("grand-tour");
    },
    [complete, update],
  );

  // Returns true the first time this target is locked.
  const lock = useCallback(
    (key: string, label: string) => {
      const first = !ref.current.locked.includes(key);
      if (first) {
        update((p) => ({ ...p, xp: p.xp + LOCK_XP, locked: [...p.locked, key] }));
        toast({ kind: "lock", title: `Target locked · ${label}`, detail: `+${LOCK_XP} XP` });
      }
      complete("lock-on");
      if (ref.current.locked.length >= 3) complete("sharpshooter");
      return first;
    },
    [complete, toast, update],
  );

  const reset = useCallback(() => {
    ref.current = EMPTY;
    setProgress(EMPTY);
    toast({ kind: "info", title: "Progress reset", detail: "Back to Cadet" });
  }, [toast]);

  return { progress, toasts, toast, complete, visit, lock, reset };
}
