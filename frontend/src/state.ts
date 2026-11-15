// Shared app state: the current search, its URL and the polling for the result.
import { useCallback, useEffect, useRef, useState } from "react";
import { fullUrl, getStatus, startSky, type Search, type SkyResponse } from "./api";
import type { ViewerStatus } from "./viewer";

const POLL_MS = 2000;
const MAX_POLL_FAILS = 5;

export const DEFAULT_FOV = 3;

export function searchFromUrl(): Search | null {
  const q = new URLSearchParams(location.search);
  const fov = Number(q.get("fov")) || DEFAULT_FOV;
  if (q.get("target")) return { target: q.get("target")!, fov };
  if (q.get("ra") && q.get("dec")) return { ra: q.get("ra")!, dec: q.get("dec")!, fov };
  return null;
}

function writeUrl(s: Search) {
  const q = new URLSearchParams(
    s.target ? { target: s.target, fov: String(s.fov) } : { ra: s.ra!, dec: s.dec!, fov: String(s.fov) },
  );
  history.replaceState(null, "", `?${q}`);
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("aborted", "AbortError"));
    });
  });

// Backend remarks about the result: fallback to precomputed data, or a plain note.
export interface SkyInfo {
  fallback: boolean;
  note: string | null;
}

const NO_INFO: SkyInfo = { fallback: false, note: null };

// setTarget starts a search; a new one cancels the previous polling. retry runs the last one again.
export function useSky() {
  const [status, setStatus] = useState<ViewerStatus>({ kind: "empty" });
  const [info, setInfo] = useState<SkyInfo>(NO_INFO);
  const abort = useRef<AbortController | null>(null);
  const last = useRef<Search | null>(null);

  const setTarget = useCallback(async (search: Search) => {
    abort.current?.abort();
    const ctl = (abort.current = new AbortController());
    last.current = search;
    writeUrl(search);
    setStatus({ kind: "loading", stage: "queued", done: 0, total: 0 });
    setInfo(NO_INFO);
    // Polls can omit the note, so keep the last one seen.
    const remember = (r: SkyResponse) =>
      setInfo((i) => ({ fallback: r.fallback ?? i.fallback, note: r.note ?? i.note }));
    try {
      let res = await startSky(search, ctl.signal);
      remember(res);
      while (res.status !== "done") {
        if (res.status === "error") throw new Error(res.error ?? "Unknown error");
        const p = res.preview;
        setStatus({
          kind: "loading",
          stage: res.stage ?? "queued",
          done: res.done ?? 0,
          total: res.total ?? 0,
          preview: p ? { meta: p.meta, baseUrl: fullUrl(p.base_url) } : undefined,
        });
        // The server can go quiet for a minute while the job keeps running, so one failed poll is not fatal.
        for (let tries = 1; ; tries++) {
          await sleep(POLL_MS, ctl.signal);
          try {
            res = await getStatus(res.job, ctl.signal);
            remember(res);
            break;
          } catch (e) {
            if ((e as Error).name === "AbortError" || tries >= MAX_POLL_FAILS) throw e;
          }
        }
      }
      setStatus({ kind: "done", meta: res.meta!, baseUrl: fullUrl(res.base_url!) });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setStatus({ kind: "error", message: (e as Error).message });
    }
  }, []);

  const retry = useCallback(() => {
    if (last.current) setTarget(last.current);
  }, [setTarget]);

  useEffect(() => () => abort.current?.abort(), []);

  return { status, setTarget, retry, info };
}
