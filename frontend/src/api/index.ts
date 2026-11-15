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

// Community "report a candidate" reports (see backend/CANDIDATES.md).
export type CandidateKind = "moving" | "faint" | "spectrum" | "other";

export interface CandidateIn {
  ra: number;
  dec: number;
  job?: string;
  band?: string;
  epoch?: number;
  note?: string;
  name?: string;
  kind?: CandidateKind;
}

export interface Candidate extends CandidateIn {
  id: string;
  created_at: string; // UTC ISO
  near_challenge_target?: string | null; // e.g. "barnard": probably the known star
  reports_here?: number; // reports within 10" of this spot, this one included
}

export const getCandidates = (ra: number, dec: number, radiusArcmin: number, signal?: AbortSignal) =>
  getJson<{ count: number; candidates: Candidate[] }>(
    `/api/candidates?${new URLSearchParams({ ra: String(ra), dec: String(dec), radius_arcmin: String(radiusArcmin) })}`,
    signal,
  );

export async function reportCandidate(c: CandidateIn): Promise<Candidate> {
  const res = await fetch(API_BASE + "/api/candidates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(c),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    // 429 gives a plain message, 422 a list of field errors.
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail : detail?.[0]?.msg;
    throw new Error(msg ?? `Report failed (${res.status})`);
  }
  return body;
}
