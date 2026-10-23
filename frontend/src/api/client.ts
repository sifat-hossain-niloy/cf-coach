// Typed API calls. Types come from the backend's OpenAPI schema (npm run gen:types).
import type { components } from "./schema";

type S = components["schemas"];
export type Summary = S["SummaryOut"];
export type Tags = S["TagsOut"];
export type Bands = S["BandsOut"];
export type Weak = S["WeakOut"];
export type Progress = S["ProgressOut"];
export type Queue = S["QueueOut"];
export type QueueItem = S["QueueItem"];
export type Job = S["JobOut"];
export type SyncResult = S["SyncOut"];
export type WeakTag = S["WeakTag"];
export type RankOut = S["RankOut"];

/** An HTTP error with the backend's machine-readable code when it sent one. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let code: string | null = null;
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
      else if (detail && typeof detail === "object" && "message" in detail) {
        message = String(detail.message);
        code = detail.code ? String(detail.code) : null;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message);
  }
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

const h = (handle: string) => `/api/handles/${encodeURIComponent(handle)}`;

export const api = {
  sync: (handle: string) => request<SyncResult>(`${h(handle)}/sync`, { method: "POST" }),
  job: (id: number) => request<Job>(`/api/jobs/${id}`),
  summary: (handle: string, target?: number | null) => request<Summary>(`${h(handle)}/summary${qs({ target })}`),
  tags: (handle: string) => request<Tags>(`${h(handle)}/tags`),
  bands: (handle: string) => request<Bands>(`${h(handle)}/bands`),
  weak: (handle: string, band?: Band | null) =>
    request<Weak>(`${h(handle)}/weak${qs({ band_lo: band?.lo, band_hi: band?.hi })}`),
  progress: (handle: string, target?: number | null) => request<Progress>(`${h(handle)}/progress${qs({ target })}`),
  queue: (handle: string, date: string, n: number, exclude: string[], band?: Band | null) =>
    request<Queue>(
      `${h(handle)}/queue${qs({ date, n, exclude: exclude.join(","), band_lo: band?.lo, band_hi: band?.hi })}`,
    ),
};

export interface Band {
  lo: number;
  hi: number;
}
