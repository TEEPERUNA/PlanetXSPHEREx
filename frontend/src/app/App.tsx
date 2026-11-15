import { useEffect, useState } from "react";
import { Viewer } from "../viewer";
import { searchFromUrl, useSky } from "../state";
import { SearchForm } from "./SearchForm";
import "./app.css";

const initial = searchFromUrl();

export function App() {
  const { status, setTarget } = useSky();
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

  return (
    <main className="app">
      <header className="app__header">
        <h1>
          <span className="app__mark" aria-hidden="true" />
          SPHEREx Sky
        </h1>
        <p className="note">See how a patch of sky changes over time.</p>
        {result && gif && (
          <a className="app__download" href={result.baseUrl + gif} download>
            Download GIF
          </a>
        )}
      </header>
      <SearchForm initial={initial} onSearch={setTarget} />
      <section className={"result card" + (open ? " is-open" : "")}>
        <Viewer status={status} />
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
