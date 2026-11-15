import { useState, type FormEvent } from "react";
import { reportCandidate, type Candidate, type CandidateKind } from "../../api";
import { pixelToSky } from "../lib/skyCoords";
import type { Band, Meta, Pixel } from "../types";

interface Props {
  pixel: Pixel | null; // picked by clicking the image
  meta: Meta;
  band: Band;
  epoch: number | null; // null in diff mode
  job?: string;
  count: number; // reports already in this field
  onReported: (c: Candidate) => void;
}

const KINDS: { value: CandidateKind; label: string }[] = [
  { value: "moving", label: "Moving object" },
  { value: "faint", label: "Faint source" },
  { value: "spectrum", label: "Odd spectrum" },
  { value: "other", label: "Other" },
];

// "Report a candidate" form for the picked pixel.
export function CandidateReport({ pixel, meta, band, epoch, job, count, onReported }: Props) {
  const [kind, setKind] = useState<CandidateKind>("moving");
  const [note, setNote] = useState("");
  const [name, setName] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const field = count === 1 ? "1 report in this field" : `${count} reports in this field`;

  if (!pixel) {
    return (
      <div className="cand-form">
        <p className="cand-form__hint">Spot something moving? Click the image to report it. ({field})</p>
        {result && <p className={result.ok ? "cand-form__ok" : "cand-form__err"}>{result.text}</p>}
      </div>
    );
  }

  const { ra, dec } = pixelToSky(pixel.x, pixel.y, meta);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setResult(null);
    try {
      const c = await reportCandidate({
        ra,
        dec,
        job,
        band,
        epoch: epoch ?? undefined,
        note: note.trim() || undefined,
        name: name.trim() || undefined,
        kind,
      });
      const here = c.reports_here && c.reports_here > 1 ? ` ${c.reports_here} reports at this spot.` : "";
      const known = c.near_challenge_target ? ` This is close to ${c.near_challenge_target}, probably the known star.` : "";
      setResult({ ok: true, text: `Reported, thank you!${here}${known}` });
      setNote("");
      onReported(c);
    } catch (err) {
      setResult({ ok: false, text: (err as Error).message });
    } finally {
      setSending(false);
    }
  }

  return (
    <form className="cand-form" onSubmit={submit}>
      <p className="cand-form__title">
        Report candidate at RA {ra.toFixed(4)}° · Dec {dec.toFixed(4)}° ({field})
      </p>
      <select value={kind} onChange={(e) => setKind(e.target.value as CandidateKind)} aria-label="Kind">
        {KINDS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </select>
      <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="Note (optional)" aria-label="Note" />
      <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="Nickname, shown publicly (optional)" aria-label="Nickname" />
      <button type="submit" disabled={sending}>
        {sending ? "Sending…" : "Report"}
      </button>
      {result && <p className={result.ok ? "cand-form__ok" : "cand-form__err"}>{result.text}</p>}
    </form>
  );
}
