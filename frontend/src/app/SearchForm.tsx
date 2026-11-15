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
  const [active, setActive] = useState(initial?.target ?? null);

  // Presets are optional: if the backend is down the form still works.
  useEffect(() => {
    getTargets()
      .then(setTargets)
      .catch(() => {});
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    // A picked target stays the search until RA/Dec are edited.
    if (active) return onSearch({ target: active, fov });
    if (!ra.trim() || !dec.trim()) return;
    onSearch({ ra: ra.trim(), dec: dec.trim(), fov });
  }

  function pick(t: Target) {
    setRa(String(t.ra));
    setDec(String(t.dec));
    setActive(t.key);
    onSearch({ target: t.key, fov });
  }

  return (
    <form className="search card" onSubmit={submit}>
      {/* demo/beyond: console heading, shown only with FX on */}
      <p className="ship-label">Nav computer · set course</p>
      <div className="search__coords">
        <label>
          Right Ascension
          <input
            value={ra}
            onChange={(e) => {
              setRa(e.target.value);
              setActive(null);
            }}
            placeholder="133.795 or 08h55m10.8s"
            required={!active}
          />
        </label>
        <label>
          Declination
          <input
            value={dec}
            onChange={(e) => {
              setDec(e.target.value);
              setActive(null);
            }}
            placeholder="-7.245 or -7d14m42s"
            required={!active}
          />
        </label>
      </div>
      <div className="search__row">
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
        <button type="submit" className="primary">
          <span className="label-normal">Show sky</span>
          <span className="label-ship">Engage</span>
        </button>
      </div>
      {targets.length > 0 && (
        <div className="search__targets">
          <span className="note">
            <span className="label-normal">Try a target</span>
            <span className="label-ship">Destinations</span>
          </span>
          <div className="pills">
            {targets.map((t) => (
              <button key={t.key} type="button" aria-pressed={t.key === active} onClick={() => pick(t)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </form>
  );
}
