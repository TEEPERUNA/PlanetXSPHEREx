import { flaggedFraction, imageCount } from "../lib/frames";
import type { Band, Frame } from "../types";

interface Props {
  frames: Frame[];
  frameIdx: number;
  band: Band;
  showDiff: boolean;
  // flagged_frac is only reliable from results that list "flag_bits" (older ones counted every flag)
  showFlagged: boolean;
}

// Date, image count and share of flagged pixels of the visible frame.
export function EpochInfo({ frames, frameIdx, band, showDiff, showFlagged }: Props) {
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
  const flagged = showFlagged ? flaggedFraction(frame.epoch, band) : null;

  return (
    <p className="viewer__info">
      Epoch {frameIdx + 1}/{frames.length} · {frame.epoch.date} · {count}{" "}
      {count === 1 ? "image" : "images"}
      {flagged !== null && (
        <span title="Share of pixels with a flag that makes the value unreliable (saturation, cosmic ray, dead pixel…)">
          {" "}· {(flagged * 100).toFixed(flagged < 0.1 ? 1 : 0)} % flagged
        </span>
      )}
    </p>
  );
}
