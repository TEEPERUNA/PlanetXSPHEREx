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
import { GameHud, MissionLog, Toasts } from "./beyond/GameHud";
import { HuntLayer, catalogPixels } from "./beyond/HuntLayer";
import { useGame } from "./beyond/useGame";
import "./app.css";
import "./beyond/beyond.css";
import "./beyond/ship.css";
import "./beyond/game.css";

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

  // Sound
  const audio = useRef(new ShipAudio());
  const [sound, setSound] = useState(false);
  const soundRef = useRef(sound);
  soundRef.current = sound;
  useEffect(() => {
    if (sound) audio.current.setWarp(warp);
  }, [warp, sound]);
  useEffect(() => {
    const a = audio.current;
    return () => a.stop();
  }, []);

  // ---------- demo/beyond: the game ----------
  const game = useGame({
    onMission: () => soundRef.current && audio.current.fanfare(),
    onRank: () => soundRef.current && audio.current.fanfare(),
  });
  const { complete, visit, lock, toast } = game;
  const [logOpen, setLogOpen] = useState(false);
  const [hunting, setHunting] = useState(false);
  const canHunt = fx && !!result && catalogPixels(result.meta).length > 0;
  useEffect(() => {
    if (!canHunt) setHunting(false);
  }, [canHunt]);

  function toggleSound() {
    if (sound) audio.current.stop();
    else {
      audio.current.start();
      audio.current.setWarp(warp);
      complete("engineer");
    }
    setSound(!sound);
  }

  // Destinations for the radar and the number keys.
  const [targets, setTargets] = useState<Target[]>([]);
  const [course, setCourse] = useState<string | null>(initial?.target ?? null);
  useEffect(() => {
    getTargets()
      .then(setTargets)
      .catch(() => {});
  }, []);
  const setCourseTo = useCallback(
    (t: Target) => {
      setCourse(t.key);
      setTarget({ target: t.key, fov: DEFAULT_FOV });
    },
    [setTarget],
  );

  // Arrival: spark burst, banner, chime and missions when a full result lands.
  const doneKey = status.kind === "done" ? status.baseUrl : null;
  const [burst, setBurst] = useState(0);
  const [arrived, setArrived] = useState<string | null>(null);
  useEffect(() => {
    if (!doneKey || status.kind !== "done") return;
    setBurst((b) => b + 1);
    setArrived(status.meta.target);
    if (soundRef.current) audio.current.chime();
    complete("first-jump");
    if (course) {
      visit(course);
      if (course === "wise0855") complete("deep-cold");
    } else {
      complete("explorer");
    }
    const t = setTimeout(() => setArrived(null), 2800);
    return () => clearTimeout(t);
    // Only when a new result arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doneKey]);

  // Missions that come from viewer controls: watch the clicks on its buttons.
  useEffect(() => {
    function onClick(e: globalThis.MouseEvent) {
      const button = (e.target as Element | null)?.closest?.("button");
      if (!button || button.getAttribute("aria-pressed") === "true") return; // only when turning on
      const text = button.textContent ?? "";
      if (text.includes("Difference image")) complete("difference");
      else if (text.includes("Compare two dates")) complete("blink");
      else if (text.includes("All measurements")) complete("spectro");
    }
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [complete]);

  // Hunt mode results.
  const onHit = useCallback(() => {
    if (!result) return;
    lock(course ?? result.meta.target, result.meta.target);
    if (soundRef.current) audio.current.lockOn();
  }, [course, lock, result]);
  const onMiss = useCallback(() => {
    if (soundRef.current) audio.current.miss();
  }, []);

  // Keys: 1–5 set course, H hunt mode, M mission log.
  useEffect(() => {
    if (!fx) return;
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      const n = Number(e.key);
      if (n >= 1 && n <= targets.length) setCourseTo(targets[n - 1]);
      else if (e.key === "h" || e.key === "H") {
        if (canHunt) setHunting((h) => !h);
        else toast({ kind: "info", title: "Hunt mode needs a target", detail: "Pick a destination first" });
      } else if (e.key === "m" || e.key === "M") setLogOpen((o) => !o);
      else if (e.key === "Escape") setLogOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fx, targets, setCourseTo, canHunt, toast]);

  const link =
    status.kind === "empty" ? "standby"
    : status.kind === "loading" ? "acquiring"
    : status.kind === "error" ? "lost"
    : info.fallback ? "backup"
    : "linked";

  return (
    <div className={"ship" + (fx ? " fx-ship" : "") + (warp ? " is-warp" : "") + (hunting ? " is-hunting" : "")}>
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
      {fx && hunting && (
        <div className="hunt-hint" role="status">
          <span>◎ Hunt mode</span> Click the star that moves between dates · <kbd>H</kbd> to stop
        </div>
      )}
      {fx && <HuntLayer active={hunting} meta={result?.meta ?? null} onHit={onHit} onMiss={onMiss} />}
      {fx && <Toasts toasts={game.toasts} />}
      {fx && logOpen && <MissionLog progress={game.progress} onClose={() => setLogOpen(false)} onReset={game.reset} />}

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
          <GameHud
            progress={game.progress}
            hunting={hunting}
            canHunt={canHunt}
            onHunt={() => setHunting((h) => !h)}
            onMissions={() => setLogOpen(true)}
          />
        )}

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
          <SearchForm
            initial={initial}
            onSearch={(s) => {
              setCourse(s.target ?? null);
              setTarget(s);
            }}
          />
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
