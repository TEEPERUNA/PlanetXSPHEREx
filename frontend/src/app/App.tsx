import { useEffect, useState, type MouseEvent } from "react";
import { Viewer } from "../viewer";
import { searchFromUrl, useSky } from "../state";
import { SearchForm } from "./SearchForm";
import "./app.css";

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

  return (
    <main className="app">
      <header className="app__header">
        <h1>
          <span className="app__mark" aria-hidden="true" />
          STARx Viewer
        </h1>
        {result && gif && (
          <a className="app__download" href={result.baseUrl + gif} download onClick={saveGif}>
            Download GIF
          </a>
        )}
      </header>
      <SearchForm initial={initial} onSearch={setTarget} />
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
  );
}
