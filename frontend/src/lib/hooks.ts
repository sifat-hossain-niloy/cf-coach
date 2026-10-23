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
  // Each mount/handle change starts a new generation; callbacks from older ones are ignored.
  const gen = useRef(0);

  const stopPolling = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };

  const poll = useCallback((id: number, g: number) => {
    api
      .job(id)
      .then((j) => {
        if (gen.current !== g) return;
        setJob(j);
        if (j.status === "done") {
          setPhase("idle");
          setHasData(true);
          setVersion((v) => v + 1);
        } else if (j.status === "failed") {
          setPhase(j.error_code === "not_found" ? "not_found" : "error");
          setMessage(j.error ?? "Sync failed.");
        } else {
          timer.current = window.setTimeout(() => poll(id, g), POLL_MS);
        }
      })
      .catch(() => {
        if (gen.current === g) timer.current = window.setTimeout(() => poll(id, g), POLL_MS * 2);
      });
  }, []);

  const startSync = useCallback(
    (g: number) => {
      stopPolling();
      setMessage(null);
      api
        .sync(handle)
        .then((r) => {
          if (gen.current !== g) return;
          if (r.cached || !r.job) {
            setPhase("idle");
            setHasData(true);
            setVersion((v) => v + 1);
            return;
          }
          setJob(r.job);
          setPhase("syncing");
          poll(r.job.id, g);
        })
        .catch((e: unknown) => {
          if (gen.current !== g) return;
          setPhase(e instanceof ApiError && e.code === "not_found" ? "not_found" : "error");
          setMessage(e instanceof Error ? e.message : "Sync failed.");
        });
    },
    [handle, poll],
  );

  useEffect(() => {
    const g = ++gen.current;
    setPhase("checking");
    setHasData(false);
    setJob(null);
    setMessage(null);
    api
      .summary(handle)
      .then((s) => {
        if (gen.current !== g) return;
        setHasData(true);
        setVersion((v) => v + 1);
        if (needsSync(s.last_synced_at)) startSync(g);
        else setPhase("idle");
      })
      .catch((e: unknown) => {
        if (gen.current !== g) return;
        if (e instanceof ApiError && (e.code === "not_found" || e.status === 422)) {
          setPhase(e.code === "not_found" ? "not_found" : "error");
          setMessage(e.message);
        } else startSync(g);
      });
    return () => {
      gen.current++;
      stopPolling();
    };
  }, [handle, startSync]);

  const resync = useCallback(() => startSync(gen.current), [startSync]);
  return { phase, job, message, hasData, version, resync };
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
