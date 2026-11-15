import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { Viewer } from "../viewer";
import { DEFAULT_FOV, searchFromUrl, useSky } from "../state";
import { getTargets, type Target } from "../api";
import { SearchForm } from "./SearchForm";
import { Starfield } from "./beyond/Starfield";
import { BootSequence } from "./beyond/BootSequence";
import { Radar } from "./beyond/Radar";
import { Telemetry } from "./beyond/Telemetry";
import { ShipAudio } from "./beyond/shipAudio";
import "./app.css";
import "./beyond/beyond.css";
import "./beyond/ship.css";

const initial = searchFromUrl();

// The download attribute is ignored for other origins (the GIF is on the API),
// so fetch it and save a local copy. If that fails the link opens the GIF as before.
async function saveGif(e: MouseEvent<HTMLAnchorElement>) {
  e.preventDefault();
  const link = e.currentTarget;
  try {
    const res = await fetch(link.href);
    if (!res.ok) throw new Error(String(res.status));
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = link.href.split("/").pop() || "spherex.gif";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch {
    window.open(link.href, "_blank", "noopener");
  }
}

// demo/beyond: the boot screen plays once per browser session.
function shouldBoot(): boolean {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
  try {
    return sessionStorage.getItem("starx-booted") !== "1";
  } catch {
    return true;
  }
}

export function App() {
  const { status, setTarget, retry, info } = useSky();
  const [open, setOpen] = useState(false);

  // A link with coordinates in the URL runs the search straight away.
  useEffect(() => {
    if (initial) setTarget(initial);
  }, [setTarget]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // The image shown right now: the full result or the quick preview.
  const result = status.kind === "done" ? status : status.kind === "loading" ? status.preview : undefined;
  const gif = result?.meta.outputs.ALL?.gif;
  const fov = result ? Math.round((result.meta.shape[1] * result.meta.pixel_scale_arcsec) / 60) : 3;

  // ---------- demo/beyond: the ship ----------
  const [fx, setFx] = useState(true);
  const [booting, setBooting] = useState(() => shouldBoot());
  const endBoot = useCallback(() => {
    setBooting(false);
    try {
      sessionStorage.setItem("starx-booted", "1");
    } catch {
      /* private mode: boot again next time, that's fine */
    }
  }, []);

  const warp = fx && status.kind === "loading" && !status.preview;

  // Destinations for the radar.
  const [targets, setTargets] = useState<Target[]>([]);
  const [course, setCourse] = useState<string | null>(initial?.target ?? null);
  useEffect(() => {
    getTargets()
      .then(setTargets)
      .catch(() => {});
  }, []);
  const setCourseTo = (t: Target) => {
    setCourse(t.key);
    setTarget({ target: t.key, fov: DEFAULT_FOV });
  };

  // Arrival: spark burst, banner and chime when a full result lands.
  const doneKey = status.kind === "done" ? status.baseUrl : null;
  const [burst, setBurst] = useState(0);
  const [arrived, setArrived] = useState<string | null>(null);
  const audio = useRef(new ShipAudio());
  const [sound, setSound] = useState(false);
  useEffect(() => {
    if (!doneKey || status.kind !== "done") return;
    setBurst((b) => b + 1);
    setArrived(status.meta.target);
    if (sound) audio.current.chime();
    const t = setTimeout(() => setArrived(null), 2800);
    return () => clearTimeout(t);
    // Only when a new result arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doneKey]);

  useEffect(() => {
    if (sound) audio.current.setWarp(warp);
  }, [warp, sound]);

  function toggleSound() {
    if (sound) audio.current.stop();
    else {
      audio.current.start();
      audio.current.setWarp(warp);
    }
    setSound(!sound);
  }
  useEffect(() => {
    const a = audio.current;
    return () => a.stop();
  }, []);

  const link =
    status.kind === "empty" ? "standby"
    : status.kind === "loading" ? "acquiring"
    : status.kind === "error" ? "lost"
    : info.fallback ? "backup"
    : "linked";

  return (
    <div className={"ship" + (fx ? " fx-ship" : "") + (warp ? " is-warp" : "")}>
      {fx && <Starfield warp={warp} burst={burst} />}
      {fx && booting && <BootSequence onDone={endBoot} />}

      {fx && (
        <div className="ship__hull" aria-hidden="true">
          <span className="ship__strut ship__strut--tl" />
          <span className="ship__strut ship__strut--tr" />
          <span className="ship__strut ship__strut--bl" />
          <span className="ship__strut ship__strut--br" />
          <span className="ship__rail ship__rail--l" />
          <span className="ship__rail ship__rail--r" />
        </div>
      )}
      {fx && warp && (
        <div className="ship__warp" aria-hidden="true">
          <span>Warp engaged</span>
        </div>
      )}
      {fx && arrived && (
        <div className="ship__arrived" role="status">
          <span className="ship__arrived-label">Arrived</span>
          <span className="ship__arrived-name">{arrived}</span>
        </div>
      )}

      <main className={"app" + (fx ? " fx" : "")}>
        <header className="app__header">
          <h1>
            <span className="app__mark" aria-hidden="true" />
            STARx Viewer
          </h1>
          {fx && (
            <button type="button" className="fx-toggle" aria-pressed={sound} onClick={toggleSound}>
              Sound {sound ? "on" : "off"}
            </button>
          )}
          <button type="button" className="fx-toggle" aria-pressed={fx} onClick={() => setFx(!fx)}>
            FX {fx ? "on" : "off"}
          </button>
          {result && gif && (
            <a className="app__download" href={result.baseUrl + gif} download onClick={saveGif}>
              Download GIF
            </a>
          )}
        </header>

        {fx && (
          <Telemetry
            link={link}
            target={result?.meta.target ?? null}
            ra={result?.meta.ra_deg ?? null}
            dec={result?.meta.dec_deg ?? null}
            fov={result ? fov : null}
            epochs={result?.meta.epochs.length ?? null}
            warp={warp}
          />
        )}

        <div className={fx ? "ship__console" : undefined}>
          <SearchForm initial={initial} onSearch={(s) => { setCourse(s.target ?? null); setTarget(s); }} />
          {fx && targets.length > 0 && (
            <Radar
              targets={targets}
              activeKey={course}
              here={result ? { ra: result.meta.ra_deg, dec: result.meta.dec_deg } : null}
              onSelect={setCourseTo}
            />
          )}
        </div>

        {info.fallback ? (
          <div className="banner banner--warn" role="status">
            <div>
              <p className="banner__title">Live data unavailable – showing precomputed {fov}′ view</p>
              {info.note && <p>{info.note}</p>}
            </div>
            <button type="button" onClick={retry}>
              Try again
            </button>
          </div>
        ) : (
          info.note && <p className="banner note">{info.note}</p>
        )}
        <section className={"result card" + (open ? " is-open" : "")}>
          <Viewer status={status} onRetry={retry} />
        </section>
        {result && (
          <>
            {open && <button className="drawer-backdrop" aria-label="Close controls" onClick={() => setOpen(false)} />}
            <button className="drawer-toggle primary" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? "Close" : "Controls"}
            </button>
          </>
        )}
      </main>
    </div>
  );
}
