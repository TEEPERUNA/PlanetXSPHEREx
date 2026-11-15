// Hunt mode: click the moving star on the viewscreen.
// A hit is a click within 2.5 SPHEREx pixels of the catalogue position (Gaia, or CatWISE
// for WISE 0855) on any of the epochs, since the star moves between them.
import { useEffect, useState } from "react";
import type { Meta } from "../../viewer";
import { gaiaPixelAt, mjdToYear, onImage } from "../../viewer/lib/gaia";

const HIT_PX = 2.5;

interface Props {
  active: boolean;
  meta: Meta | null;
  onHit: () => void;
  onMiss: () => void;
}

interface Mark {
  id: number;
  x: number; // screen position of the click
  y: number;
  hit: boolean;
}

// Catalogue positions (pixel centres) on the image, for every epoch.
// Empty when there is no catalogue position or it falls outside the image.
export function catalogPixels(meta: Meta | null): { x: number; y: number }[] {
  if (!meta) return [];
  return meta.epochs
    .map((e) => gaiaPixelAt(meta, mjdToYear(e.mjd_mean)))
    .filter((p): p is { x: number; y: number } => p !== null && onImage(p, meta));
}

export function HuntLayer({ active, meta, onHit, onMiss }: Props) {
  const [marks, setMarks] = useState<Mark[]>([]);

  useEffect(() => {
    if (!active || !meta) return;
    const targets = catalogPixels(meta);
    let id = 0;

    function onClick(e: MouseEvent) {
      const blink = (e.target as Element | null)?.closest?.(".blink");
      if (!blink || !meta) return;
      const rect = blink.getBoundingClientRect();
      const [h, w] = meta.shape;
      // Screen -> pixel coordinates where whole numbers are pixel centres.
      const px = ((e.clientX - rect.left) / rect.width) * w - 0.5;
      const py = ((e.clientY - rect.top) / rect.height) * h - 0.5;
      const hit = targets.some((t) => Math.hypot(t.x - px, t.y - py) <= HIT_PX);
      const mark = { id: ++id + Date.now(), x: e.clientX, y: e.clientY, hit };
      setMarks((m) => [...m, mark]);
      setTimeout(() => setMarks((m) => m.filter((x) => x.id !== mark.id)), 1400);
      if (hit) onHit();
      else onMiss();
    }

    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [active, meta, onHit, onMiss]);

  return (
    <>
      {marks.map((m) => (
        <div key={m.id} className={"lockfx" + (m.hit ? " is-hit" : " is-miss")} style={{ left: m.x, top: m.y }} aria-hidden="true">
          <span className="lockfx__ring" />
          <span className="lockfx__ring lockfx__ring--2" />
          <span className="lockfx__brackets" />
          <span className="lockfx__label">{m.hit ? "Target locked" : "Miss"}</span>
        </div>
      ))}
    </>
  );
}
