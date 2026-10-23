import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Bands, type Progress, type Summary, type Tags } from "../api/client";
import { HandleName, NotEnough, RatingText, Section, Skeleton } from "../components/common";
import { SyncPill } from "../components/SummaryHeader";
import { axisDate, pct, shortDate } from "../lib/format";
import { useApi, useHandleSync, type SyncState } from "../lib/hooks";
import { useDark } from "../lib/theme";

const COLORS = { light: ["#2563eb", "#db2777"], dark: ["#60a5fa", "#f472b6"] };

interface Side {
  handle: string;
  sync: SyncState;
  summary: Summary | null;
  tags: Tags | null;
  bands: Bands | null;
  progress: Progress | null;
}

function useSide(handle: string): Side {
  const sync = useHandleSync(handle);
  const on = sync.hasData;
  const v = sync.version;
  return {
    handle,
    sync,
    summary: useApi(() => api.summary(handle), [handle, v], on).data,
    tags: useApi(() => api.tags(handle), [handle, v], on).data,
    bands: useApi(() => api.bands(handle), [handle, v], on).data,
    progress: useApi(() => api.progress(handle), [handle, v], on).data,
  };
}

export default function Compare() {
  const { a = "", b = "" } = useParams();
  const left = useSide(a);
  const right = useSide(b);
  const dark = useDark();
  const colors = dark ? COLORS.dark : COLORS.light;
  const sides = [left, right];

  const missing = sides.find((s) => s.sync.phase === "not_found");
  if (missing) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h1 className="text-2xl font-bold">Handle not found</h1>
        <p className="mt-2 muted">Codeforces has no user called <b>{missing.handle}</b>.</p>
        <Link to="/" className="btn-primary mt-6">Back</Link>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {sides.map((s, i) => (
          <SideCard key={s.handle} side={s} color={colors[i]} />
        ))}
      </div>
      <RatingOverlay sides={sides} colors={colors} />
      <BandOverlay sides={sides} colors={colors} />
      <TagComparison sides={sides} colors={colors} />
    </div>
  );
}

function SideCard({ side, color }: { side: Side; color: string }) {
  const s = side.summary;
  return (
    <section className="card min-w-0" style={{ borderTop: `4px solid ${color}` }}>
      {!s ? (
        <div className="space-y-3">
          <p className="font-semibold">{side.handle}</p>
          <SyncPill sync={side.sync} />
          <Skeleton h={80} />
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2">
            <Link to={`/u/${s.handle}`} className="truncate text-2xl hover:underline">
              <HandleName handle={s.handle} rating={s.rating} />
            </Link>
            <SyncPill sync={side.sync} />
          </div>
          <p className="text-sm muted">{s.rank?.name ?? "Unrated"}</p>
          <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
            <div><dt className="muted">Rating</dt><dd className="text-lg"><RatingText rating={s.rating} /></dd></div>
            <div><dt className="muted">Max</dt><dd className="text-lg"><RatingText rating={s.max_rating} /></dd></div>
            <div><dt className="muted">Practice</dt><dd className="text-lg"><RatingText rating={s.practice_rating} /></dd></div>
            <div><dt className="muted">Solved</dt><dd className="text-lg tabular-nums">{s.counts.solved}</dd></div>
            <div><dt className="muted">Contests</dt><dd className="text-lg tabular-nums">{s.counts.rated_contests}</dd></div>
            <div><dt className="muted">Weakest</dt><dd className="truncate">{s.top_weak[0]?.tag ?? "–"}</dd></div>
          </dl>
        </>
      )}
    </section>
  );
}

function RatingOverlay({ sides, colors }: { sides: Side[]; colors: string[] }) {
  const ready = sides.every((s) => s.progress);
  const data = useMemo(() => {
    if (!ready) return [];
    const rows: Record<string, number>[] = [];
    sides.forEach((s, i) => s.progress!.history.forEach((h) => rows.push({ time: h.time, [`r${i}`]: h.new_rating })));
    return rows.sort((x, y) => x.time - y.time);
  }, [ready, sides]);
  const fmt = axisDate(data.map((d) => d.time));
  return (
    <Section title="Rating history">
      {!ready ? (
        <Skeleton h={260} />
      ) : data.length < 2 ? (
        <NotEnough message="Neither handle has rated contests yet." />
      ) : (
        <div className="h-72">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ left: -8, right: 8, top: 8 }}>
              <CartesianGrid strokeOpacity={0.15} />
              <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} tickFormatter={fmt} fontSize={12} minTickGap={40} />
              <YAxis domain={[(m: number) => Math.floor((m - 100) / 100) * 100, (m: number) => Math.ceil((m + 100) / 100) * 100]} fontSize={12} />
              <Tooltip labelFormatter={(t: number) => shortDate(t)} />
              <Legend />
              {sides.map((s, i) => (
                <Line key={s.handle} dataKey={`r${i}`} name={s.summary?.handle ?? s.handle} stroke={colors[i]} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Section>
  );
}

function BandOverlay({ sides, colors }: { sides: Side[]; colors: string[] }) {
  const ready = sides.every((s) => s.bands);
  const data = useMemo(() => {
    if (!ready) return [];
    const by = new Map<number, Record<string, number | null>>();
    sides.forEach((s, i) =>
      s.bands!.bands.forEach((b) => {
        const row = by.get(b.bucket) ?? { bucket: b.bucket };
        row[`s${i}`] = b.solve_rate != null ? Math.round(b.solve_rate * 100) : null;
        by.set(b.bucket, row);
      }),
    );
    return [...by.values()].sort((x, y) => (x.bucket as number) - (y.bucket as number));
  }, [ready, sides]);
  return (
    <Section title="Solve rate by rating band" subtitle="Share of attempted problems that were solved, per 100-point band">
      {!ready ? (
        <Skeleton h={240} />
      ) : (
        <div className="h-64">
          <ResponsiveContainer>
            <BarChart data={data} margin={{ left: -16, right: 8 }}>
              <CartesianGrid vertical={false} strokeOpacity={0.15} />
              <XAxis dataKey="bucket" fontSize={12} />
              <YAxis unit="%" domain={[0, 100]} fontSize={12} />
              <Tooltip formatter={(v: number) => `${v}%`} />
              <Legend />
              {sides.map((s, i) => (
                <Bar key={s.handle} dataKey={`s${i}`} name={s.summary?.handle ?? s.handle} fill={colors[i]} isAnimationActive={false} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Section>
  );
}

function TagComparison({ sides, colors }: { sides: Side[]; colors: string[] }) {
  const ready = sides.every((s) => s.tags);
  const rows = useMemo(() => {
    if (!ready) return [];
    const maps = sides.map((s) => new Map(s.tags!.tags.map((t) => [t.tag, t])));
    const names = new Set(sides.flatMap((s) => s.tags!.tags.slice(0, 15).map((t) => t.tag)));
    return [...names]
      .map((tag) => ({ tag, stats: maps.map((m) => m.get(tag) ?? null) }))
      .sort((x, y) => (y.stats[0]?.attempted ?? 0) + (y.stats[1]?.attempted ?? 0) - (x.stats[0]?.attempted ?? 0) - (x.stats[1]?.attempted ?? 0));
  }, [ready, sides]);
  return (
    <Section title="Tags side by side" subtitle="Solved / attempted and solve rate for each handle's most-attempted tags">
      {!ready ? (
        <Skeleton h={300} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[460px] text-sm">
            <thead className="text-left text-xs uppercase tracking-wide muted">
              <tr>
                <th className="py-1 pr-2">Tag</th>
                {sides.map((s, i) => (
                  <th key={s.handle} className="py-1 pr-2" style={{ color: colors[i] }}>{s.summary?.handle ?? s.handle}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.tag} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-2 font-medium">{r.tag}</td>
                  {r.stats.map((t, i) => (
                    <td key={i} className="py-1.5 pr-2 tabular-nums">
                      {t ? `${t.solved}/${t.attempted} · ${pct(t.solve_rate)}` : <span className="muted">–</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
