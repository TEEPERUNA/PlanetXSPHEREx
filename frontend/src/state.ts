// Shared app state: the current search, its URL and the polling for the result.
import { useCallback, useEffect, useRef, useState } from "react";
import { fullUrl, getStatus, startSky, type Search } from "./api";
import type { ViewerStatus } from "./viewer";

const POLL_MS = 2000;

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

// setTarget starts a search; a new one cancels the previous polling.
export function useSky() {
  const [status, setStatus] = useState<ViewerStatus>({ kind: "empty" });
  const [isPreview, setIsPreview] = useState(false);
  const abort = useRef<AbortController | null>(null);

  const setTarget = useCallback(async (search: Search) => {
    abort.current?.abort();
    const ctl = (abort.current = new AbortController());
    writeUrl(search);
    setIsPreview(false);
    setStatus({ kind: "loading", stage: "queued", done: 0, total: 0 });
    try {
      let res = await startSky(search, ctl.signal);
      while (res.status !== "done") {
        if (res.status === "error") throw new Error(res.error ?? "Unknown error");
        const p = res.preview;
        if (p) {
          setIsPreview(true);
          setStatus({ kind: "done", meta: p.meta, baseUrl: fullUrl(p.base_url) });
        } else {
          setStatus({ kind: "loading", stage: res.stage ?? "queued", done: res.done ?? 0, total: res.total ?? 0 });
        }
        await sleep(POLL_MS, ctl.signal);
        res = await getStatus(res.job, ctl.signal);
      }
      setIsPreview(false);
      setStatus({ kind: "done", meta: res.meta!, baseUrl: fullUrl(res.base_url!) });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setIsPreview(false);
      setStatus({ kind: "error", message: (e as Error).message });
    }
  }, []);

  useEffect(() => () => abort.current?.abort(), []);

  return { status, isPreview, setTarget };
}
