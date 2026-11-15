// Bridge telemetry bar. Every reading is real: link state from the search status,
// target and position from meta.json, and a live UTC clock with Modified Julian Date.
import { useEffect, useState } from "react";

interface Props {
  link: "standby" | "acquiring" | "linked" | "backup" | "lost";
  target: string | null;
  ra: number | null;
  dec: number | null;
  fov: number | null; // arcmin
  epochs: number | null;
  warp: boolean;
}

const LINK_TEXT: Record<Props["link"], string> = {
  standby: "STANDBY",
  acquiring: "ACQUIRING",
  linked: "LINKED",
  backup: "BACKUP DATA",
  lost: "LOST",
};

function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function Telemetry({ link, target, ra, dec, fov, epochs, warp }: Props) {
  const now = useNow();
  const mjd = now.getTime() / 86400000 + 40587; // Unix epoch is MJD 40587
  const utc = now.toISOString().slice(11, 19);

  const cells: [string, string, string?][] = [
    ["Link", LINK_TEXT[link], `is-${link}`],
    ["Target", target ?? "—"],
    ["RA", ra === null ? "—" : `${ra.toFixed(4)}°`],
    ["Dec", dec === null ? "—" : `${dec >= 0 ? "+" : ""}${dec.toFixed(4)}°`],
    ["FOV", fov === null ? "—" : `${fov}′`],
    ["Epochs", epochs === null ? "—" : String(epochs)],
    ["Drive", warp ? "WARP" : "IMPULSE", warp ? "is-warp" : undefined],
    ["UTC", utc],
    ["MJD", mjd.toFixed(5)],
  ];

  return (
    <div className="telemetry" role="status" aria-label="Ship telemetry">
      {cells.map(([label, value, cls]) => (
        <div key={label} className={"telemetry__cell" + (cls ? ` ${cls}` : "")}>
          <span className="telemetry__label">{label}</span>
          <span className="telemetry__value">{value}</span>
        </div>
      ))}
    </div>
  );
}
