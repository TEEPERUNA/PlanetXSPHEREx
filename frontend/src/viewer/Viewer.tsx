import { useMemo, useState } from "react";
import { BlinkImage } from "./components/BlinkImage";
import { CursorInfo } from "./components/CursorInfo";
import { EpochInfo } from "./components/EpochInfo";
import { PlaybackControls } from "./components/PlaybackControls";
import { SpectrumChart } from "./components/SpectrumChart";
import { StatusView } from "./components/StatusView";
import { useBlink } from "./hooks/useBlink";
import { availableBands, framesFor, joinUrl } from "./lib/frames";
import type { Band, Meta, Pixel, ViewerStatus } from "./types";
import "./viewer.css";

interface ViewerProps {
  status: ViewerStatus;
}

// Public component. The app passes the status, the viewer shows it.
export function Viewer({ status }: ViewerProps) {
  if (status.kind !== "done") {
    return (
      <div className="viewer">
        <StatusView status={status} />
      </div>
    );
  }
  // key = new target -> all viewer state starts fresh.
  return <LoadedViewer key={status.baseUrl} meta={status.meta} baseUrl={status.baseUrl} />;
}

interface LoadedProps {
  meta: Meta;
  baseUrl: string;
}

// Viewer with data. Owns band, frame, playback and filter state.
function LoadedViewer({ meta, baseUrl }: LoadedProps) {
  const bands = useMemo(() => availableBands(meta), [meta]);

  const [band, setBand] = useState<Band>(bands[0] ?? "ALL");
  const [frameIdx, setFrameIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [fps, setFps] = useState(2);
  const [showDiff, setShowDiff] = useState(false);
  const [brightness, setBrightness] = useState(1);
  const [contrast, setContrast] = useState(1);
  const [hoverPx, setHoverPx] = useState<Pixel | null>(null);

  const frames = useMemo(() => framesFor(meta, band, baseUrl), [meta, band, baseUrl]);
  const diffPath = meta.outputs[band]?.diff;
  const diffSrc = diffPath ? joinUrl(baseUrl, diffPath) : null;
  const canPlay = frames.length > 1 && !showDiff;

  // Move forward or back, wrapping around.
  function step(delta: number) {
    setFrameIdx((i) => (frames.length ? (i + delta + frames.length) % frames.length : 0));
  }

  function changeBand(next: Band) {
    setBand(next);
    setFrameIdx(0);
    if (!meta.outputs[next]?.diff) setShowDiff(false);
  }

  useBlink(playing && canPlay, fps, () => step(1));

  if (frames.length === 0) {
    return (
      <div className="viewer">
        <StatusView status={{ kind: "error", message: "No SPHEREx images for this position." }} />
      </div>
    );
  }

  return (
    <div className="viewer">
      <h2 className="viewer__title">{meta.target}</h2>

      <BlinkImage
        srcs={frames.map((f) => f.src)}
        activeIdx={frameIdx}
        diffSrc={showDiff ? diffSrc : null}
        shape={meta.shape}
        filter={`brightness(${brightness}) contrast(${contrast})`}
        alt={`${meta.target}, ${band}, ${frames[frameIdx]?.epoch.date ?? ""}`}
        onHover={setHoverPx}
      />

      <EpochInfo frames={frames} frameIdx={frameIdx} band={band} showDiff={showDiff} />
      <CursorInfo pixel={hoverPx} meta={meta} />

      <PlaybackControls
        bands={bands}
        band={band}
        onBand={changeBand}
        playing={playing}
        canPlay={canPlay}
        onTogglePlay={() => setPlaying((p) => !p)}
        onStep={(delta) => {
          setPlaying(false); // stepping means the user wants to look closely
          step(delta);
        }}
        fps={fps}
        onFps={setFps}
        hasDiff={diffSrc !== null}
        showDiff={showDiff}
        onToggleDiff={() => setShowDiff((d) => !d)}
        brightness={brightness}
        onBrightness={setBrightness}
        contrast={contrast}
        onContrast={setContrast}
      />

      {meta.spectrum && <SpectrumChart url={joinUrl(baseUrl, meta.spectrum)} />}

      {meta.credit && <p className="viewer__credit">Data: {meta.credit}</p>}
    </div>
  );
}
