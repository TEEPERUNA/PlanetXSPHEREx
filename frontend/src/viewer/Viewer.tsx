import { useEffect, useMemo, useState, type ReactNode } from "react";
import { getCandidates, type Candidate } from "../api";
import { BlinkImage } from "./components/BlinkImage";
import { CandidateOverlay } from "./components/CandidateOverlay";
import { CandidateReport } from "./components/CandidateReport";
import { CursorInfo } from "./components/CursorInfo";
import { EpochInfo } from "./components/EpochInfo";
import { GaiaFieldInfo, GaiaInfo } from "./components/GaiaInfo";
import { GaiaOverlay } from "./components/GaiaOverlay";
import { InfoPanels } from "./components/InfoPanels";
import { LightCurveChart } from "./components/LightCurveChart";
import { PlaybackControls } from "./components/PlaybackControls";
import { SpectrumChart } from "./components/SpectrumChart";
import { LoadingProgress, StatusView } from "./components/StatusView";
import { useBlink } from "./hooks/useBlink";
import { useGaiaField } from "./hooks/useGaiaField";
import { usePixelSpectrum } from "./hooks/usePixelSpectrum";
import { usePixelValues } from "./hooks/usePixelValues";
import { useSources } from "./hooks/useSources";
import { availableBands, framesFor, joinUrl, nearestFrame } from "./lib/frames";
import { gaiaPixelAt, mjdToYear, onImage } from "./lib/gaia";
import { describeStar, nearestStar, starsOnImage, withoutGaia } from "./lib/gaiaField";
import type { Band, Meta, Pixel, ViewerStatus } from "./types";
import "./viewer.css";

interface ViewerProps {
  status: ViewerStatus;
  onRetry?: () => void; // shows a Try again button on errors
}

// Same search = same key, so preview -> full result keeps band, date and filters.
// A new search gets a new key and starts fresh. The target name is unique per search
// ("Barnard's Star", "RA 10.6800 Dec +41.2700"), and shape changes with the field of view.
// Not the exact RA/Dec: a moving star's position can differ slightly between runs.
function viewKey(meta: Meta): string {
  return `${meta.target}|${meta.shape.join("x")}`;
}

// Public component. The app passes the status, the viewer shows it.
export function Viewer({ status, onRetry }: ViewerProps) {
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
      <StatusView status={status} onRetry={onRetry} />
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
  const [anchorMjd, setAnchorMjd] = useState<number | null>(null); // date of the frame on screen
  const [playing, setPlaying] = useState(true);
  const [fps, setFps] = useState(2);
  const [showDiff, setShowDiff] = useState(false);
  const [showDeep, setShowDeep] = useState(false);
  const [brightness, setBrightness] = useState(1);
  const [contrast, setContrast] = useState(1);
  const [hoverPx, setHoverPx] = useState<Pixel | null>(null);
  const [showGaia, setShowGaia] = useState(true);
  const [compareOn, setCompareOn] = useState(false);
  const [compareA, setCompareA] = useState<number | null>(null); // dates (mjd), like anchorMjd
  const [compareB, setCompareB] = useState<number | null>(null);
  const [reporting, setReporting] = useState(false); // candidate report form open
  const [pickPx, setPickPx] = useState<Pixel | null>(null); // pixel chosen for a candidate report
  const [spectrumPx, setSpectrumPx] = useState<Pixel | null>(null); // clicked pixel shown in the spectrum
  const [candidates, setCandidates] = useState<Candidate[]>([]);

  // Community reports in this field. Optional extra, so a failed request just shows none.
  const { ra_deg, dec_deg } = meta;
  const radius = ((Math.max(...meta.shape) * meta.pixel_scale_arcsec) / 60) * 0.75; // ≈ half the diagonal, arcmin
  useEffect(() => {
    const ctl = new AbortController();
    getCandidates(ra_deg, dec_deg, radius, ctl.signal)
      .then((r) => setCandidates(r.candidates))
      .catch(() => {});
    return () => ctl.abort();
  }, [ra_deg, dec_deg, radius]);
  const job = baseUrl.match(/\/files\/([^/]+)/)?.[1]; // ".../api/files/<job>/"

  // The full result can have other bands and epochs than the preview.
  const activeBand: Band = bands.includes(band) ? band : (bands[0] ?? "ALL");
  const frames = useMemo(() => framesFor(meta, activeBand, baseUrl), [meta, activeBand, baseUrl]);

  const diffPath = meta.outputs[activeBand]?.diff;
  const diffSrc = diffPath ? joinUrl(baseUrl, diffPath) : null;
  const diffOn = showDiff && diffSrc !== null;

  // Deep image: all epochs of the band added together (more signal, faint sources show up).
  const deepPath = meta.outputs[activeBand]?.combined;
  const deepSrc = deepPath ? joinUrl(baseUrl, deepPath) : null;
  const deepOn = showDeep && deepSrc !== null && !diffOn;
  const stillOn = diffOn || deepOn; // one fixed image instead of the epochs

  // Compare mode: blink only between date A (default first) and date B (default last).
  const ia = nearestFrame(frames, compareA ?? frames[0]?.epoch.mjd_mean ?? null);
  const ib = nearestFrame(frames, compareB ?? frames[frames.length - 1]?.epoch.mjd_mean ?? null);
  const canCompare = frames.length > 1 && !stillOn;
  const compareActive = compareOn && canCompare;
  const playFrames = compareActive ? [...new Set([ia, ib])].sort((x, y) => x - y).map((i) => frames[i]) : frames;

  // Position in the played list, and in the full list (for the image stack and info).
  const playIdx = nearestFrame(playFrames, anchorMjd);
  const idx = Math.max(0, frames.indexOf(playFrames[playIdx]));
  const canPlay = playFrames.length > 1 && !stillOn;

  // Gaia button only when the predicted position lands on the image for some epoch.
  const bandEpochs = frames.map((f) => f.epoch);
  const hasGaia = bandEpochs.some((e) => {
    const p = gaiaPixelAt(meta, mjdToYear(e.mjd_mean));
    return p !== null && onImage(p, meta);
  });
  const currentEpoch = stillOn ? null : (frames[idx]?.epoch ?? null);

  // All Gaia stars in the field, moved to the date on screen (last epoch in diff mode,
  // the middle epoch for the deep image), and the bright sources Gaia does not list.
  const gaiaField = useGaiaField(meta);
  const fieldEpoch =
    currentEpoch ?? (deepOn ? frames[Math.floor(frames.length / 2)]?.epoch : frames[frames.length - 1]?.epoch) ?? null;
  const fieldStars = useMemo(
    () => (fieldEpoch ? starsOnImage(gaiaField.stars, meta, mjdToYear(fieldEpoch.mjd_mean)) : []),
    [gaiaField.stars, meta, fieldEpoch],
  );
  // The deep image is searched in its own FITS stack: deeper, so fainter sources count.
  const sources = useSources(meta, baseUrl, activeBand, fieldEpoch?.index ?? null, deepOn ? meta.outputs[activeBand]?.combined_fits : undefined);
  // Only when the field came back with stars: an empty or failed query would flag everything.
  const lonely = gaiaField.status === "ok" && fieldStars.length > 0 ? withoutGaia(sources, fieldStars) : [];
  const hoverStar = hoverPx ? nearestStar(fieldStars, hoverPx.x, hoverPx.y) : null;
  const showGaiaButton = hasGaia || fieldStars.length > 0;

  // Spectrum of the clicked pixel from the per-pixel files (only when the result has them).
  const pixelSpectrum = usePixelSpectrum(meta, baseUrl, spectrumPx);

  // Values of the pixel under the cursor, for the epoch on screen.
  const pixelInfo = usePixelValues(meta, baseUrl, activeBand, currentEpoch?.index ?? null, hoverPx);

  // Move forward or back, wrapping around. Stores the date, not the position.
  function step(delta: number) {
    if (playFrames.length === 0) return;
    const next = (playIdx + delta + playFrames.length) % playFrames.length;
    setAnchorMjd(playFrames[next].epoch.mjd_mean);
  }

  // Turning compare on starts at date A.
  function toggleCompare() {
    if (!compareOn && frames[ia]) setAnchorMjd(frames[ia].epoch.mjd_mean);
    setCompareOn((c) => !c);
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
        diffSrc={diffOn ? diffSrc : deepOn ? deepSrc : null}
        stillAlt={
          deepOn
            ? `${meta.target}, ${activeBand}, deep image of all ${frames.length} epochs`
            : "Difference image, last epoch minus first"
        }
        shape={meta.shape}
        filter={`brightness(${brightness}) contrast(${contrast})`}
        alt={`${meta.target}, ${activeBand}, ${frames[idx]?.epoch.date ?? ""}`}
        onHover={setHoverPx}
        onPick={(p) => {
          if (reporting) setPickPx(p); // a report spot only while the report form is open
          if (pixelSpectrum.available) setSpectrumPx(p);
        }}
        overlay={
          <>
            {showGaiaButton && showGaia && (
              <GaiaOverlay meta={meta} epochs={bandEpochs} current={currentEpoch} field={fieldStars} lonely={lonely} />
            )}
            <CandidateOverlay meta={meta} candidates={candidates} picked={pickPx} />
          </>
        }
      />

      <div className="viewer__side">
        {deepOn ? (
          <p className="viewer__info">
            Deep image · all {frames.length} epochs added together ({frames[0]?.epoch.date} – {frames[frames.length - 1]?.epoch.date}).
            Faint sources show up; a moving star is smeared along its path.
          </p>
        ) : (
          <EpochInfo
            frames={frames}
            frameIdx={idx}
            band={activeBand}
            showDiff={diffOn}
            showFlagged={meta.flag_bits !== undefined}
          />
        )}
        {compareActive && (
          <p className="viewer__compare">
            Comparing{" "}
            <strong className={idx === ia ? "is-current" : undefined}>A {frames[ia].epoch.date}</strong> ↔{" "}
            <strong className={idx === ib ? "is-current" : undefined}>B {frames[ib].epoch.date}</strong>
            {ia === ib && " (pick two different dates)"}
          </p>
        )}
        <CursorInfo
          pixel={hoverPx}
          meta={meta}
          band={activeBand}
          values={pixelInfo.values}
          loading={pixelInfo.loading}
          gaiaNote={showGaia && hoverStar ? describeStar(hoverStar.star) : null}
        />
        <CandidateReport
          open={reporting}
          pixel={pickPx}
          meta={meta}
          band={activeBand}
          epoch={currentEpoch?.index ?? null}
          job={job}
          count={candidates.length}
          onReported={(c) => setCandidates((cs) => [c, ...cs])}
          onOpen={() => setReporting(true)}
          onClose={() => {
            setReporting(false);
            setPickPx(null);
          }}
        />
        {(showGaia || !hasGaia) && (
          <GaiaInfo meta={meta} epoch={stillOn ? fieldEpoch : currentEpoch} showDiff={stillOn} />
        )}
        {showGaia && (
          <GaiaFieldInfo
            status={gaiaField.status}
            onImage={fieldStars.length}
            truncated={gaiaField.truncated}
            lonely={lonely.length}
            date={fieldEpoch?.date ?? null}
          />
        )}

        <PlaybackControls
          bands={bands}
          band={activeBand}
          onBand={setBand}
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
          onToggleDiff={() => {
            setShowDiff((d) => !d);
            setShowDeep(false);
          }}
          hasDeep={deepSrc !== null}
          showDeep={deepOn}
          onToggleDeep={() => {
            setShowDeep((d) => !d);
            setShowDiff(false);
          }}
          hasGaia={showGaiaButton}
          showGaia={showGaia}
          onToggleGaia={() => setShowGaia((s) => !s)}
          dates={frames.map((f) => ({ mjd: f.epoch.mjd_mean, date: f.epoch.date }))}
          compareOn={compareActive}
          canCompare={canCompare}
          onToggleCompare={toggleCompare}
          compareA={frames[ia]?.epoch.mjd_mean ?? 0}
          compareB={frames[ib]?.epoch.mjd_mean ?? 0}
          onCompareA={(mjd) => {
            setCompareA(mjd);
            setAnchorMjd(mjd);
          }}
          onCompareB={(mjd) => {
            setCompareB(mjd);
            setAnchorMjd(mjd);
          }}
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
            highlightEpoch={stillOn ? undefined : frames[idx]?.epoch.index}
            pixel={
              spectrumPx
                ? {
                    label: `Pixel (${spectrumPx.x}, ${spectrumPx.y})`,
                    rows: pixelSpectrum.rows,
                    approx: pixelSpectrum.approx,
                    onBack: () => setSpectrumPx(null),
                  }
                : null
            }
          />
        )}

        {meta.light_curve != null && (
          <LightCurveChart
            lightCurve={meta.light_curve}
            epochs={meta.epochs}
            highlightEpoch={stillOn ? undefined : frames[idx]?.epoch.index}
          />
        )}

        {meta.credit && <p className="viewer__credit">Data: {meta.credit}</p>}

        <InfoPanels />
      </div>
    </div>
  );
}
