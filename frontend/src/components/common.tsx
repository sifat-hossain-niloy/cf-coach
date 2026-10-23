import type { ReactNode } from "react";
import { rankColor, rankFor } from "../lib/ranks";
import { useDark } from "../lib/theme";

/** Handle in its rank color; Legendary Grandmasters get the first letter in black (white in dark mode). */
export function HandleName({ handle, rating, className = "" }: { handle: string; rating: number | null; className?: string }) {
  const dark = useDark();
  const color = rankColor(rating, dark);
  const legendary = rankFor(rating)?.name === "Legendary Grandmaster";
  return (
    <span className={`font-bold ${className}`} style={{ color }}>
      {legendary ? (
        <>
          <span className="text-black dark:text-white">{handle[0]}</span>
          {handle.slice(1)}
        </>
      ) : (
        handle
      )}
    </span>
  );
}

export function RatingText({ rating }: { rating: number | null }) {
  const dark = useDark();
  if (rating === null) return <span className="muted">unrated</span>;
  return (
    <span className="font-semibold tabular-nums" style={{ color: rankColor(rating, dark) }}>
      {rating}
    </span>
  );
}

export function Section({ title, subtitle, children, right }: { title: string; subtitle?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card min-w-0">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm muted">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

export function NotEnough({ message }: { message?: string | null }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm muted dark:border-slate-700">
      {message ?? "Not enough data yet. Solve a few more problems and sync again."}
    </div>
  );
}

export function Skeleton({ h = 200 }: { h?: number }) {
  return <div className="animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" style={{ height: h }} />;
}

export function ErrorNote({ error }: { error: Error | null }) {
  if (!error) return null;
  return <p className="text-sm text-red-600 dark:text-red-400">{error.message}</p>;
}
