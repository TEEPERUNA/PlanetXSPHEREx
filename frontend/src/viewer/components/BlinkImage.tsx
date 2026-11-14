import type { PointerEvent } from "react";
import type { Pixel } from "../types";

interface Props {
  srcs: string[]; // all frames of the band
  activeIdx: number; // frame to show
  diffSrc: string | null; // shown instead of the frames when set
  shape: [number, number]; // [height, width] in SPHEREx pixels
  filter: string; // CSS filter for brightness and contrast
  alt: string;
  onHover: (pixel: Pixel | null) => void;
}

// Image stack + SVG overlay.
// All frames stay in the DOM and only one is visible, so the blink never waits for loading.
export function BlinkImage({ srcs, activeIdx, diffSrc, shape, filter, alt, onHover }: Props) {
  const [height, width] = shape;

  // Screen position -> SPHEREx pixel.
  function handlePointer(e: PointerEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * width);
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * height);
    const inside = x >= 0 && x < width && y >= 0 && y < height;
    onHover(inside ? { x, y } : null);
  }

  // Keep the last tap visible on touch screens.
  function handleLeave(e: PointerEvent<HTMLDivElement>) {
    if (e.pointerType === "mouse") onHover(null);
  }

  return (
    <div
      className="blink"
      onPointerMove={handlePointer}
      onPointerDown={handlePointer}
      onPointerLeave={handleLeave}
    >
      {srcs.map((src, i) => {
        const visible = !diffSrc && i === activeIdx;
        return (
          <img
            key={src}
            src={src}
            alt={visible ? alt : ""}
            aria-hidden={!visible}
            className={visible ? "blink__img is-visible" : "blink__img"}
            style={{ filter }}
            draggable={false}
          />
        );
      })}

      {diffSrc && (
        <img
          src={diffSrc}
          alt="Difference image, last epoch minus first"
          className="blink__img is-visible"
          style={{ filter }}
          draggable={false}
        />
      )}

      {/* Coordinates are SPHEREx pixels. Gaia circles go here later. */}
      <svg className="blink__overlay" viewBox={`0 0 ${width} ${height}`} aria-hidden="true" />
    </div>
  );
}
