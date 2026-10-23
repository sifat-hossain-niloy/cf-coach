export const HANDLE_RE = /^[A-Za-z0-9_.-]{3,24}$/;
export const SYNC_FRESH_MS = 10 * 60 * 1000;

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? "–" : `${(x * 100).toFixed(digits)}%`;

export const signed = (x: number) => (x > 0 ? `+${x}` : `${x}`);

export function todayUTC(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function shortDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

/** Tick formatter that shows days for short ranges and months for long ones. */
export function axisDate(times: number[]): (t: number) => string {
  const span = times.length ? Math.max(...times) - Math.min(...times) : 0;
  const opts: Intl.DateTimeFormatOptions =
    span < 120 * 86_400 ? { month: "short", day: "numeric" } : { year: "numeric", month: "short" };
  return (t: number) => new Date(t * 1000).toLocaleDateString(undefined, opts);
}

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

/** True when the dashboard should ask the server to re-sync (it may still answer "cached"). */
export function needsSync(lastSyncedAt: string | null | undefined, now: number = Date.now()): boolean {
  if (!lastSyncedAt) return true;
  return now - Date.parse(lastSyncedAt) >= SYNC_FRESH_MS;
}

/** Weak-tag band for a target override: never narrower than the default level+100..level+400. */
export function bandForTarget(level: number, target: number | null): { lo: number; hi: number } | null {
  if (target === null || target <= level + 400) return null;
  return { lo: level + 100, hi: target };
}
