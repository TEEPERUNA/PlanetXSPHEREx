import { useEffect, useState } from "react";
import { Viewer } from "../viewer";
import { searchFromUrl, useSky } from "../state";
import { GifView } from "./GifView";
import { SearchForm } from "./SearchForm";
import "./app.css";

const initial = searchFromUrl();

export function App() {
  const { status, isPreview, setTarget } = useSky();
  const [frames, setFrames] = useState(false);

  // A link with coordinates in the URL runs the search straight away.
  useEffect(() => {
    if (initial) setTarget(initial);
  }, [setTarget]);

  return (
    <main className="app">
      <header className="app__header">
        <h1>SPHEREx Sky</h1>
        <p className="note">See how a patch of sky changes over time.</p>
      </header>
      <SearchForm initial={initial} onSearch={setTarget} />
      {status.kind === "done" ? (
        <section className="result card">
          {isPreview && <p className="banner">Quick preview, full result is still loading…</p>}
          <h2>{status.meta.target}</h2>
          <GifView key={status.baseUrl} meta={status.meta} baseUrl={status.baseUrl} />
          <button className="toggle" aria-expanded={frames} onClick={() => setFrames(!frames)}>
            {frames ? "Hide" : "Show"} frame-by-frame
          </button>
          {frames && <Viewer status={status} />}
          <p className="note">{status.meta.credit}</p>
        </section>
      ) : (
        <section className="result card">
          <Viewer status={status} />
        </section>
      )}
    </main>
  );
}
