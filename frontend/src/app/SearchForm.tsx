import { useEffect, useState, type FormEvent } from "react";
import { getTargets, type Search, type Target } from "../api";
import { DEFAULT_FOV } from "../state";

interface Props {
  initial: Search | null;
  onSearch: (s: Search) => void;
}

// Coordinates (degrees or 08h55m10.8s), preset targets and field of view.
export function SearchForm({ initial, onSearch }: Props) {
  const [targets, setTargets] = useState<Target[]>([]);
  const [ra, setRa] = useState(initial?.ra ?? "");
  const [dec, setDec] = useState(initial?.dec ?? "");
  const [fov, setFov] = useState(initial?.fov ?? DEFAULT_FOV);

  // Presets are optional: if the backend is down the form still works.
  useEffect(() => {
    getTargets().then(setTargets).catch(() => {});
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (ra.trim() && dec.trim()) onSearch({ ra: ra.trim(), dec: dec.trim(), fov });
  }

  return (
    <form className="search" onSubmit={submit}>
      <label>
        RA
        <input value={ra} onChange={(e) => setRa(e.target.value)} placeholder="133.795 or 08h55m10.8s" required />
      </label>
      <label>
        Dec
        <input value={dec} onChange={(e) => setDec(e.target.value)} placeholder="-7.245 or -7d14m42s" required />
      </label>
      <label>
        Field of view
        <select value={fov} onChange={(e) => setFov(Number(e.target.value))}>
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n} arcmin
            </option>
          ))}
        </select>
      </label>
      <button type="submit">Show</button>
      {targets.length > 0 && (
        <div className="targets">
          {targets.map((t) => (
            <button key={t.key} type="button" onClick={() => onSearch({ target: t.key, fov })}>
              {t.label}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}
