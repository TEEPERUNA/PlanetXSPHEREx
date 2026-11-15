import { gaiaPixelAt, gaiaSource, mjdToYear, offsetArcsec, onImage } from "../lib/gaia";
import type { Epoch, Meta } from "../types";

interface Props {
  meta: Meta;
  epoch: Epoch | null; // epoch on screen; null in diff mode
  showDiff: boolean;
}

interface FieldProps {
  status: "loading" | "ok" | "error";
  onImage: number; // Gaia stars on the image at the date on screen
  truncated: boolean; // the backend returned only the brightest stars
  lonely: number; // bright sources without a Gaia star
  date: string | null;
}

// One line about the Gaia field stars and the sources Gaia does not list.
export function GaiaFieldInfo({ status, onImage: count, truncated, lonely, date }: FieldProps) {
  if (status === "loading") return <p className="viewer__gaia">Loading Gaia stars for this field…</p>;
  if (status === "error") return <p className="viewer__gaia">Gaia field stars are not available right now.</p>;
  if (count === 0) return <p className="viewer__gaia">No Gaia DR3 stars in this field.</p>;
  return (
    <p className="viewer__gaia">
      <span className="viewer__gaia-key viewer__gaia-key--field" aria-hidden="true" />
      <span>
        {count} Gaia DR3 stars on the image{date ? ` on ${date}` : ""}
        {truncated ? " (the brightest in this area)" : ""}.{" "}
        {lonely > 0 ? (
          <>
            <span className="viewer__nomatch-key" aria-hidden="true" />
            {lonely} bright {lonely === 1 ? "source has" : "sources have"} no Gaia star: seen in infrared, not by Gaia.
          </>
        ) : (
          "Every bright source has a Gaia star."
        )}
      </span>
    </p>
  );
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
