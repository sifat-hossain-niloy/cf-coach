import { useState, type FormEvent, type ReactNode } from "react";
import type { Summary } from "../api/client";
import { timeAgo } from "../lib/format";
import { rankFor } from "../lib/ranks";
import type { SyncState } from "../lib/hooks";
import { HandleName, RatingText } from "./common";

interface Props {
  summary: Summary;
  sync: SyncState;
  target: number | null;
  onTarget: (t: number | null) => void;
}

export function SummaryHeader({ summary: s, sync, target, onTarget }: Props) {
  const [draft, setDraft] = useState(target?.toString() ?? "");
  const [editing, setEditing] = useState(false);
  const current = s.rating ?? s.level.value;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const v = parseInt(draft, 10);
    onTarget(Number.isFinite(v) && v > 0 && v <= 5000 ? v : null);
    setEditing(false);
  };

  return (
    <section className="card">
      <div className="flex flex-wrap items-center gap-4">
        {s.avatar && (
          <img
            src={s.avatar}
            alt=""
            className="h-16 w-16 rounded-xl object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
        )}
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl sm:text-3xl">
            <a href={`https://codeforces.com/profile/${s.handle}`} target="_blank" rel="noreferrer">
              <HandleName handle={s.handle} rating={s.rating} />
            </a>
          </h1>
          <p className="mt-1 text-sm muted">
            {s.rank ? s.rank.name : "Unrated"} · last synced {timeAgo(s.last_synced_at)}
          </p>
        </div>
        <SyncPill sync={sync} />
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Rating">
          <RatingText rating={s.rating} />
          {s.max_rating !== null && <span className="ml-1 text-xs muted">max {s.max_rating}</span>}
        </Stat>
        <Stat label={s.level.source === "contest" ? "Level" : `Level (${s.level.source})`}>
          <span className="tabular-nums">{s.level.value}</span>
        </Stat>
        <Stat label="Target">
          {editing ? (
            <form onSubmit={submit} className="flex gap-1">
              <input
                autoFocus
                inputMode="numeric"
                value={draft}
                onChange={(e) => setDraft(e.target.value.replace(/\D/g, ""))}
                placeholder="auto"
                className="w-20 rounded-md border border-slate-300 bg-transparent px-2 py-0.5 text-sm dark:border-slate-700"
              />
              <button className="btn-ghost px-2 py-0.5 text-xs">Set</button>
            </form>
          ) : (
            <button
              onClick={() => (setDraft(target?.toString() ?? ""), setEditing(true))}
              className="group text-left"
              title="Change target"
            >
              {s.target !== null ? <RatingText rating={s.target} /> : <span className="muted">top rank</span>}
              <span className="ml-1 text-xs muted group-hover:underline">{target !== null ? "custom · edit" : "edit"}</span>
            </button>
          )}
          {s.target_rank && <span className="block text-xs muted">{rankFor(s.target)?.name}</span>}
        </Stat>
        <Stat label="Gap">
          <span className="tabular-nums">{s.gap === null ? "–" : s.gap <= 0 ? "reached" : `+${s.gap}`}</span>
          <span className="block text-xs muted">from {current}</span>
        </Stat>
      </dl>
      {target !== null && (
        <button onClick={() => onTarget(null)} className="mt-2 text-xs underline muted">
          Reset target to next rank
        </button>
      )}
      {s.level.note && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">{s.level.note}</p>}
      {s.top_weak.length > 0 && (
        <p className="mt-3 text-sm">
          <span className="muted">Focus on: </span>
          {s.top_weak.map((w, i) => (
            <span key={w.tag}>
              <a href="#weak" className="font-medium underline decoration-dotted">{w.tag}</a>
              {i < s.top_weak.length - 1 ? ", " : ""}
            </span>
          ))}
        </p>
      )}
      <p className="mt-2 text-xs muted">
        {s.counts.solved} solved of {s.counts.attempted} attempted · {s.counts.submissions} submissions ·{" "}
        {s.counts.rated_contests} rated contests
      </p>
    </section>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
      <dt className="text-xs uppercase tracking-wide muted">{label}</dt>
      <dd className="mt-0.5 text-lg">{children}</dd>
    </div>
  );
}

export function SyncPill({ sync }: { sync: SyncState }) {
  const { phase, job } = sync;
  if (phase === "syncing" && job) {
    const text =
      job.status === "queued" && job.position
        ? `You are #${job.position} in line`
        : job.stage ?? "Syncing…";
    return (
      <span className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1 text-sm text-blue-800 dark:bg-blue-950/50 dark:text-blue-200" aria-live="polite">
        <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
        {text}
      </span>
    );
  }
  if (phase === "checking") return <span className="text-sm muted">Checking…</span>;
  if (phase === "error")
    return (
      <span className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
        {sync.message}
        <button onClick={sync.resync} className="btn-ghost px-2 py-0.5 text-xs">Retry</button>
      </span>
    );
  return (
    <button onClick={sync.resync} className="btn-ghost text-xs" title="Refreshes at most every 10 minutes">
      ↻ Refresh
    </button>
  );
}
