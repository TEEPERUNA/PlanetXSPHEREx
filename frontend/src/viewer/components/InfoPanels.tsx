import { DR1_BAD_FLAGS, DR1_FLAG_BITS, FLAG_TEXT } from "../lib/flags";

// Flags that do not make the value unreliable: warnings and information.
const OTHER_FLAGS = Object.keys(DR1_FLAG_BITS).filter((name) => !DR1_BAD_FLAGS.includes(name));

function FlagList({ names, bad }: { names: string[]; bad: boolean }) {
  return (
    <dl>
      {names.map((name) => (
        <div key={name}>
          <dt className={bad ? "is-bad" : undefined}>{name}</dt>
          <dd>{FLAG_TEXT[name]}</dd>
        </div>
      ))}
    </dl>
  );
}

// What the flags mean, what each control does, and what the site is for. Static text, closed by default.
export function InfoPanels() {
  return (
    <>
      <details className="info">
        <summary>Flag info</summary>
        <p>
          SPHEREx marks every pixel of every image with flags for known problems. Point at the image to see the flags of
          that pixel. "% flagged" under the date is the share of unreliable pixels in that image.
        </p>
        <p className="info__group">Unreliable: the value should not be trusted</p>
        <FlagList names={DR1_BAD_FLAGS} bad />
        <p className="info__group">Warnings and information</p>
        <FlagList names={OTHER_FLAGS} bad={false} />
      </details>

      <details className="info">
        <summary>Controls info</summary>
        <dl>
          <dt>D1–D6 / ALL</dt>
          <dd>SPHEREx's six detector bands, each covering a range of infrared wavelengths. ALL stacks them into one image.</dd>
          <dt>◀ Play/Pause ▶</dt>
          <dd>Play loops the images in date order like a short video. The arrows step one image at a time and pause playback.</dd>
          <dt>Speed</dt>
          <dd>How many images per second the loop shows.</dd>
          <dt>Compare two dates</dt>
          <dd>Pick date A and date B. The loop then switches only between those two, the classic blink comparator: an object that moved jumps back and forth.</dd>
          <dt>Difference image</dt>
          <dd>The last epoch minus the first. White is brighter now, black is fainter now, so moving or changing objects stand out.</dd>
          <dt>Gaia position</dt>
          <dd>The green ring is where the Gaia catalogue predicts the target is on each date. The dots show its track.</dd>
          <dt>Brightness / Contrast</dt>
          <dd>Change only how the image looks on screen, not the data.</dd>
          <dt>Pointer on image</dt>
          <dd>Shows the sky coordinates and the measured values of that pixel: brightness, background, signal-to-noise and wavelength.</dd>
          <dt>Flags</dt>
          <dd>Amber flags mean the pixel value is unreliable; others are just information. Hover a flag for its meaning, or see Flag info above.</dd>
          <dt>Spectrum</dt>
          <dd>Brightness against wavelength for the target, one colour per epoch.</dd>
        </dl>
      </details>

      <details className="info">
        <summary>Website info</summary>
        <p>SPHEREx is a NASA space telescope that maps the whole sky in infrared, revisiting each patch every six months or so.</p>
        <p>
          This site, built for the NASA Space Apps Challenge, takes a position (RA/Dec or a preset target) and shows every
          SPHEREx image of that patch as a short animation. Anything that moves or changes brightness between visits, such
          as a nearby star or a brown dwarf, blinks or shifts, so you can see it without astronomy software.
        </p>
      </details>
    </>
  );
}
