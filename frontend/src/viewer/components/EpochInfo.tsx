import { imageCount } from "../lib/frames";
import type { Band, Frame } from "../types";

interface Props {
  frames: Frame[];
  frameIdx: number;
  band: Band;
  showDiff: boolean;
}

// Date and image count of the visible frame.
export function EpochInfo({ frames, frameIdx, band, showDiff }: Props) {
  if (frames.length === 0) return null;

  if (showDiff) {
    const first = frames[0].epoch.date;
    const last = frames[frames.length - 1].epoch.date;
    return (
      <p className="viewer__info">
        Difference {last} minus {first} · white = brighter now, black = fainter now
      </p>
    );
  }

  const frame = frames[frameIdx];
  if (!frame) return null;
  const count = imageCount(frame.epoch, band);

  return (
    <p className="viewer__info">
      Epoch {frameIdx + 1}/{frames.length} · {frame.epoch.date} · {count}{" "}
      {count === 1 ? "image" : "images"}
    </p>
  );
}
