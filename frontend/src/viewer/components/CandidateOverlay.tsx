import type { Candidate } from "../../api";
import { onImage } from "../lib/gaia";
import { skyToPixel } from "../lib/skyCoords";
import type { Meta, Pixel } from "../types";

interface Props {
  meta: Meta;
  candidates: Candidate[];
  picked: Pixel | null; // pixel chosen for a new report
}

// Drawn inside the SVG overlay (viewBox = SPHEREx pixels).
// Square = a community report, crosshair = the pixel picked for a new report.
export function CandidateOverlay({ meta, candidates, picked }: Props) {
  return (
    <g className="cand">
      {candidates.map((c) => {
        const p = skyToPixel(c.ra, c.dec, meta);
        if (!onImage(p, meta)) return null;
        return <rect key={c.id} className="cand__mark" x={p.x - 0.5} y={p.y - 0.5} width={2} height={2} />;
      })}
      {picked && (
        <rect className="cand__pick" x={picked.x - 0.5} y={picked.y - 0.5} width={2} height={2} />
      )}
    </g>
  );
}
