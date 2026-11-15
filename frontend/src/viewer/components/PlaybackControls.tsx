import type { Band } from "../types";

interface Props {
  bands: Band[];
  band: Band;
  onBand: (band: Band) => void;

  playing: boolean;
  canPlay: boolean; // false when there is only one frame or the diff is shown
  onTogglePlay: () => void;
  onStep: (delta: number) => void;

  fps: number;
  onFps: (fps: number) => void;

  hasDiff: boolean;
  showDiff: boolean;
  onToggleDiff: () => void;

  hasGaia: boolean; // false when there is nothing from Gaia to draw on the image
  showGaia: boolean;
  onToggleGaia: () => void;

  // Compare two dates: the blink alternates between date A and date B only.
  dates: { mjd: number; date: string }[]; // dates of the current band, in order
  compareOn: boolean;
  canCompare: boolean; // false with fewer than two dates or in diff mode
  onToggleCompare: () => void;
  compareA: number; // mjd of date A
  compareB: number;
  onCompareA: (mjd: number) => void;
  onCompareB: (mjd: number) => void;

  brightness: number;
  onBrightness: (value: number) => void;
  contrast: number;
  onContrast: (value: number) => void;
}

// All viewer controls. Holds no state of its own.
export function PlaybackControls(p: Props) {
  return (
    <div className="controls">
      <div className="controls__row" role="group" aria-label="Detector band">
        {p.bands.map((band) => (
          <button
            key={band}
            type="button"
            className={band === p.band ? "controls__band is-active" : "controls__band"}
            aria-pressed={band === p.band}
            onClick={() => p.onBand(band)}
          >
            {band}
          </button>
        ))}
      </div>

      <div className="controls__row">
        <div className="controls__transport">
          <button type="button" onClick={() => p.onStep(-1)} disabled={!p.canPlay} aria-label="Previous frame">
            ◀
          </button>
          <button type="button" onClick={p.onTogglePlay} disabled={!p.canPlay}>
            {p.playing ? "Pause" : "Play"}
          </button>
          <button type="button" onClick={() => p.onStep(1)} disabled={!p.canPlay} aria-label="Next frame">
            ▶
          </button>
        </div>

        <label className="controls__slider">
          Speed {p.fps} fps
          <input
            id="viewer-fps"
            type="range"
            min={0.5}
            max={10}
            step={0.5}
            value={p.fps}
            onChange={(e) => p.onFps(Number(e.target.value))}
          />
        </label>

        <button
          type="button"
          onClick={p.onToggleDiff}
          disabled={!p.hasDiff}
          aria-pressed={p.showDiff}
          className={p.showDiff ? "is-active" : undefined}
        >
          Difference image
        </button>

        {p.hasGaia && (
          <button
            type="button"
            onClick={p.onToggleGaia}
            aria-pressed={p.showGaia}
            className={p.showGaia ? "is-active" : undefined}
          >
            Gaia stars
          </button>
        )}
      </div>

      <div className="controls__row controls__compare">
        <button
          type="button"
          onClick={p.onToggleCompare}
          disabled={!p.canCompare}
          aria-pressed={p.compareOn}
          className={p.compareOn ? "is-active" : undefined}
        >
          Compare two dates
        </button>
        {p.compareOn && (
          <>
            <label className="controls__select">
              A
              <select id="viewer-compare-a" value={p.compareA} onChange={(e) => p.onCompareA(Number(e.target.value))}>
                {p.dates.map((d) => (
                  <option key={d.mjd} value={d.mjd}>
                    {d.date}
                  </option>
                ))}
              </select>
            </label>
            <label className="controls__select">
              B
              <select id="viewer-compare-b" value={p.compareB} onChange={(e) => p.onCompareB(Number(e.target.value))}>
                {p.dates.map((d) => (
                  <option key={d.mjd} value={d.mjd}>
                    {d.date}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>

      <div className="controls__row">
        <label className="controls__slider">
          Brightness
          <input
            id="viewer-brightness"
            type="range"
            min={0.2}
            max={3}
            step={0.1}
            value={p.brightness}
            onChange={(e) => p.onBrightness(Number(e.target.value))}
          />
        </label>
        <label className="controls__slider">
          Contrast
          <input
            id="viewer-contrast"
            type="range"
            min={0.2}
            max={3}
            step={0.1}
            value={p.contrast}
            onChange={(e) => p.onContrast(Number(e.target.value))}
          />
        </label>
      </div>
    </div>
  );
}
