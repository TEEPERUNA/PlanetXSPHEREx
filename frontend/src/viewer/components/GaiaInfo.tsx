import { gaiaPixelAt, gaiaSource, mjdToYear, offsetArcsec, onImage } from "../lib/gaia";
import type { Epoch, Meta } from "../types";

interface Props {
  meta: Meta;
  epoch: Epoch | null; // epoch on screen; null in diff mode
  showDiff: boolean;
}

// One line under the image that explains the green circle.
export function GaiaInfo({ meta, epoch, showDiff }: Props) {
  const g = meta.gaia_validation;
  if (!g || g.predicted_ra == null || g.predicted_dec == null || !epoch) return null;

  const source = gaiaSource(g);
  const p = gaiaPixelAt(meta, mjdToYear(epoch.mjd_mean));
  if (!p) return null;

  if (!onImage(p, meta)) {
    return (
      <p className="viewer__gaia">
        {source} predicted position is outside the image ({Math.round(offsetArcsec(p, meta))}″ from the centre).
      </p>
    );
  }

  // The image is centred on the target, so a large offset means the prediction
  // may point at another source. More than 2 pixels is worth saying.
  const offset = offsetArcsec(p, meta);
  const farNote = offset > 2 * meta.pixel_scale_arcsec ? ` It is ${Math.round(offset)}″ from the image centre, so it may mark a different source.` : "";

  return (
    <p className="viewer__gaia">
      <span className="viewer__gaia-key" aria-hidden="true" />
      {showDiff
        ? `${source} predicted position: dashed = first epoch, solid = last epoch.${farNote}`
        : `${source} predicted position on ${epoch.date}. Dots show the track over all epochs.${farNote}`}
    </p>
  );
}
