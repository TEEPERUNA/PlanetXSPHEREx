import { useEffect, useRef } from "react";

// Calls onTick `fps` times per second while `playing` is true.
export function useBlink(playing: boolean, fps: number, onTick: () => void): void {
  // Keep the latest callback without restarting the timer.
  const tickRef = useRef(onTick);
  useEffect(() => {
    tickRef.current = onTick;
  });

  useEffect(() => {
    if (!playing || fps <= 0) return;
    const id = window.setInterval(() => tickRef.current(), 1000 / fps);
    return () => window.clearInterval(id);
  }, [playing, fps]);
}
