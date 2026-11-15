// Talks to the backend (see CONTRACT.md). The only place that knows the API address.
import type { Meta } from "../viewer";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "https://planetx-api-38053485414.us-east4.run.app";

export interface Target {
  key: string;
  label: string;
  ra: number;
  dec: number;
  cached: boolean;
}

// One search: a preset target key, or coordinates (degrees or 08h55m10.8s).
export interface Search {
  target?: string;
  ra?: string;
  dec?: string;
  fov: number;
}

export interface SkyResponse {
  status: "done" | "queued" | "processing" | "error";
  job: string;
  base_url?: string;
  meta?: Meta;
  stage?: string;
  done?: number;
  total?: number;
  error?: string | null;
  preview?: { base_url: string; meta: Meta } | null;
  precomputed?: boolean; // bundled challenge-target result
  fallback?: boolean; // true = live data failed, this is the precomputed result instead
  note?: string | null;
}

// base_url from the API is relative ("/api/files/<job>/"), images need the full address.
export const fullUrl = (baseUrl: string) => API_BASE + baseUrl;

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(API_BASE + path, { signal });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const getTargets = () => getJson<Target[]>("/api/targets");

export function startSky(s: Search, signal?: AbortSignal) {
  const q = new URLSearchParams({ fov: String(s.fov) });
  if (s.target) q.set("target", s.target);
  else {
    q.set("ra", s.ra ?? "");
    q.set("dec", s.dec ?? "");
  }
  return getJson<SkyResponse>(`/api/sky?${q}`, signal);
}

export const getStatus = (job: string, signal?: AbortSignal) =>
  getJson<SkyResponse>(`/api/status/${encodeURIComponent(job)}`, signal);
