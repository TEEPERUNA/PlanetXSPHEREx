import { useMemo, useState, type ReactNode } from "react";
import { BlinkImage } from "./components/BlinkImage";
import { CursorInfo } from "./components/CursorInfo";
import { EpochInfo } from "./components/EpochInfo";
import { GaiaInfo } from "./components/GaiaInfo";
import { GaiaOverlay } from "./components/GaiaOverlay";
import { InfoPanels } from "./components/InfoPanels";
import { PlaybackControls } from "./components/PlaybackControls";
import { SpectrumChart } from "./components/SpectrumChart";
import { LoadingProgress, StatusView } from "./components/StatusView";
import { useBlink } from "./hooks/useBlink";
import { usePixelValues } from "./hooks/usePixelValues";
import { availableBands, framesFor, joinUrl } from "./lib/frames";
import { gaiaPixelAt, mjdToYear, onImage } from "./lib/gaia";
import type { Band, Meta, Pixel, ViewerStatus } from "./types";
import "./viewer.css";

interface ViewerProps {
  status: ViewerStatus;
}

// Same position = same key, so preview -> full result keeps band, frame and filters.
// A new position gets a new key and starts fresh.
function viewKey(meta: Meta): string {
  return `${meta.ra_deg}|${meta.dec_deg}|${meta.shape.join("x")}`;
}

// Public component. The app passes the status, the viewer shows it.
export function Viewer({ status }: ViewerProps) {
  if (status.kind === "done") {
    return <LoadedViewer key={viewKey(status.meta)} meta={status.meta} baseUrl={status.baseUrl} />;
  }

  // Quick preview while the full run continues.
  if (status.kind === "loading" && status.preview) {
    const { meta, baseUrl } = status.preview;
    return (
      <LoadedViewer
        key={viewKey(meta)}
        meta={meta}
        baseUrl={baseUrl}
        notice={
          <div className="viewer__notice">
            <p>Quick preview with fewer images. Full data is on its way.</p>
            <LoadingProgress stage={status.stage} done={status.done} total={status.total} />
          </div>
        }
      />
    );
  }

  return (
    <div className="viewer">
      <StatusView status={status} />
    </div>
  );
}

interface LoadedProps {
  meta: Meta;
  baseUrl: string;
  notice?: ReactNode; // shown above the image, e.g. preview progress
}

// Viewer with data. Owns band, frame, playback and filter state.
function LoadedViewer({ meta, baseUrl, notice }: LoadedProps) {
  const bands = useMemo(() => availableBands(meta), [meta]);

  const [band, setBand] = useState<Band>(bands[0] ?? "ALL");
  const [frameIdx, setFrameIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [fps, setFps] = useState(2);
  const [showDiff, setShowDiff] = useState(false);
  const [brightness, setBrightness] = useState(1);
  const [contrast, setContrast] = useState(1);
  const [hoverPx, setHoverPx] = useState<Pixel | null>(null);
  const [showGaia, setShowGaia] = useState(true);

  // The full result can have other bands and epochs than the preview.
  const activeBand: Band = bands.includes(band) ? band : (bands[0] ?? "ALL");
  const frames = useMemo(() => framesFor(meta, activeBand, baseUrl), [meta, activeBand, baseUrl]);
  const idx = frames.length ? frameIdx % frames.length : 0;

  const diffPath = meta.outputs[activeBand]?.diff;
  const diffSrc = diffPath ? joinUrl(baseUrl, diffPath) : null;
  const diffOn = showDiff && diffSrc !== null;
  const canPlay = frames.length > 1 && !diffOn;

  // Gaia button only when the predicted position lands on the image for some epoch.
  const bandEpochs = frames.map((f) => f.epoch);
  const hasGaia = bandEpochs.some((e) => {
    const p = gaiaPixelAt(meta, mjdToYear(e.mjd_mean));
    return p !== null && onImage(p, meta);
  });
  const currentEpoch = diffOn ? null : (frames[idx]?.epoch ?? null);

  // Values of the pixel under the cursor, for the epoch on screen.
  const pixelInfo = usePixelValues(meta, baseUrl, activeBand, currentEpoch?.index ?? null, hoverPx);

  // Move forward or back, wrapping around.
  function step(delta: number) {
    setFrameIdx((i) => (frames.length ? (i + delta + frames.length) % frames.length : 0));
  }

  function changeBand(next: Band) {
    setBand(next);
    setFrameIdx(0);
  }

  useBlink(playing && canPlay, fps, () => step(1));

  if (frames.length === 0) {
    return (
      <div className="viewer">
        {notice}
        <StatusView status={{ kind: "error", message: "No SPHEREx images for this position." }} />
      </div>
    );
  }

  return (
    <div className="viewer">
      <h2 className="viewer__title">{meta.target}</h2>
      {notice}

      <BlinkImage
        srcs={frames.map((f) => f.src)}
        activeIdx={idx}
        diffSrc={diffOn ? diffSrc : null}
        shape={meta.shape}
        filter={`brightness(${brightness}) contrast(${contrast})`}
        alt={`${meta.target}, ${activeBand}, ${frames[idx]?.epoch.date ?? ""}`}
        onHover={setHoverPx}
        overlay={
          hasGaia && showGaia ? <GaiaOverlay meta={meta} epochs={bandEpochs} current={currentEpoch} /> : null
        }
      />

      <div className="viewer__side">
        <EpochInfo frames={frames} frameIdx={idx} band={activeBand} showDiff={diffOn} />
        <CursorInfo
          pixel={hoverPx}
          meta={meta}
          band={activeBand}
          values={pixelInfo.values}
          loading={pixelInfo.loading}
        />
        {(showGaia || !hasGaia) && (
          <GaiaInfo meta={meta} epoch={diffOn ? (frames[frames.length - 1]?.epoch ?? null) : currentEpoch} showDiff={diffOn} />
        )}

        <PlaybackControls
          bands={bands}
          band={activeBand}
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
          showDiff={diffOn}
          onToggleDiff={() => setShowDiff((d) => !d)}
          hasGaia={hasGaia}
          showGaia={showGaia}
          onToggleGaia={() => setShowGaia((s) => !s)}
          brightness={brightness}
          onBrightness={setBrightness}
          contrast={contrast}
          onContrast={setContrast}
        />

        {meta.spectrum && (
          <SpectrumChart
            url={joinUrl(baseUrl, meta.spectrum)}
            epochs={meta.epochs}
            ranges={meta.detector_ranges_um}
            highlightEpoch={diffOn ? undefined : frames[idx]?.epoch.index}
          />
        )}

        {meta.credit && <p className="viewer__credit">Data: {meta.credit}</p>}

        <InfoPanels />
      </div>
    </div>
  );
}
