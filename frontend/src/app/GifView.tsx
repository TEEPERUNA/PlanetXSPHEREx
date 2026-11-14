import { useState } from "react";
import type { Meta } from "../viewer";

const ORDER = ["ALL", "D1", "D2", "D3", "D4", "D5", "D6"];

interface Props {
  meta: Meta;
  baseUrl: string;
}

// The server-made GIF per band.
export function GifView({ meta, baseUrl }: Props) {
  const bands = ORDER.filter((b) => meta.outputs[b as keyof Meta["outputs"]]?.gif);
  const [band, setBand] = useState(bands[0]);
  const gif = band && meta.outputs[band as keyof Meta["outputs"]]?.gif;

  if (!gif) return <p className="note">No GIF available for this result.</p>;
  return (
    <div className="gif">
      <div className="bands">
        {bands.map((b) => (
          <button key={b} className={b === band ? "on" : ""} onClick={() => setBand(b)}>
            {b}
          </button>
        ))}
      </div>
      <img src={baseUrl + gif} alt={`${meta.target}, band ${band}, over time`} />
    </div>
  );
}
