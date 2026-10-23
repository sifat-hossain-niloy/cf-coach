import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type Job } from "../api/client";
import { needsSync } from "./format";

/** Fetch with loading/error state; re-runs when `deps` change. `enabled=false` skips fetching. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[], enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(enabled);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    setLoading(true);
    fn()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled]);
  return { data, error, loading };
}

export type SyncPhase = "checking" | "syncing" | "idle" | "not_found" | "error";

export interface SyncState {
  phase: SyncPhase;
  job: Job | null;
  message: string | null;
  hasData: boolean; // a previous sync exists, so sections can render cached data
  version: number; // bumps whenever fresh data lands
  resync: () => void;
}

const POLL_MS = 1500;

/**
 * Dashboard data lifecycle: show cached data at once, trigger a sync when stale,
 * poll the job (queue position, stage) and bump `version` when it finishes.
 */
export function useHandleSync(handle: string): SyncState {
  const [phase, setPhase] = useState<SyncPhase>("checking");
  const [job, setJob] = useState<Job | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [hasData, setHasData] = useState(false);
  const [version, setVersion] = useState(0);
  const timer = useRef<number | null>(null);
  const alive = useRef(true);

  const stopPolling = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };

  const poll = useCallback((id: number) => {
    api
      .job(id)
      .then((j) => {
        if (!alive.current) return;
        setJob(j);
        if (j.status === "done") {
          setPhase("idle");
          setHasData(true);
          setVersion((v) => v + 1);
        } else if (j.status === "failed") {
          setPhase(j.error_code === "not_found" ? "not_found" : "error");
          setMessage(j.error ?? "Sync failed.");
        } else {
          timer.current = window.setTimeout(() => poll(id), POLL_MS);
        }
      })
      .catch(() => {
        if (alive.current) timer.current = window.setTimeout(() => poll(id), POLL_MS * 2);
      });
  }, []);

  const startSync = useCallback(() => {
    stopPolling();
    setMessage(null);
    api
      .sync(handle)
      .then((r) => {
        if (!alive.current) return;
        if (r.cached || !r.job) {
          setPhase("idle");
          setHasData(true);
          setVersion((v) => v + 1);
          return;
        }
        setJob(r.job);
        setPhase("syncing");
        poll(r.job.id);
      })
      .catch((e: unknown) => {
        if (!alive.current) return;
        if (e instanceof ApiError && e.code === "not_found") setPhase("not_found");
        else setPhase("error");
        setMessage(e instanceof Error ? e.message : "Sync failed.");
      });
  }, [handle, poll]);

  useEffect(() => {
    alive.current = true;
    setPhase("checking");
    setHasData(false);
    setJob(null);
    setMessage(null);
    api
      .summary(handle)
      .then((s) => {
        if (!alive.current) return;
        setHasData(true);
        setVersion((v) => v + 1);
        if (needsSync(s.last_synced_at)) startSync();
        else setPhase("idle");
      })
      .catch((e: unknown) => {
        if (!alive.current) return;
        if (e instanceof ApiError && e.code === "not_found") {
          setPhase("not_found");
          setMessage(e.message);
        } else if (e instanceof ApiError && e.status === 422) {
          setPhase("error");
          setMessage(e.message);
        } else startSync();
      });
    return () => {
      alive.current = false;
      stopPolling();
    };
  }, [handle, startSync]);

  return { phase, job, message, hasData, version, resync: startSync };
}

/** Dark mode: follows the system until the user picks, then remembers the choice. */
export function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => {
      let saved: string | null = null;
      try {
        saved = localStorage.getItem("cfcoach:theme");
      } catch {
        /* ignore */
      }
      if (!saved) {
        document.documentElement.classList.toggle("dark", e.matches);
        setDark(e.matches);
      }
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("cfcoach:theme", next ? "dark" : "light");
    } catch {
      /* ignore */
    }
    setDark(next);
  };
  return [dark, toggle];
}
