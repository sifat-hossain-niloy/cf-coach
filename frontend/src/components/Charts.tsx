import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Bands, Progress, Weak } from "../api/client";
import { axisDate, pct, shortDate, signed } from "../lib/format";
import { rankBands } from "../lib/ranks";
import { useDark } from "../lib/theme";
import { NotEnough, Section } from "./common";

function useChartColors() {
  const dark = useDark();
  return {
    grid: dark ? "#1e293b" : "#e2e8f0",
    axis: dark ? "#94a3b8" : "#64748b",
    tooltipBg: dark ? "#0f172a" : "#ffffff",
    tooltipBorder: dark ? "#334155" : "#e2e8f0",
    primary: dark ? "#60a5fa" : "#2563eb",
    secondary: dark ? "#475569" : "#cbd5e1",
    accent: dark ? "#f472b6" : "#db2777",
    good: dark ? "#4ade80" : "#16a34a",
    dark,
  };
}

const tooltipStyle = (c: ReturnType<typeof useChartColors>) => ({
  contentStyle: { background: c.tooltipBg, border: `1px solid ${c.tooltipBorder}`, borderRadius: 8, fontSize: 12 },
  labelStyle: { color: c.axis },
});

// --- weak tags --------------------------------------------------------------------------------------

export function WeakTagsSection({ weak }: { weak: Weak }) {
  const c = useChartColors();
  const data = weak.tags.map((t) => ({ ...t, score: +(t.weakness * 100).toFixed(2) }));
  return (
    <Section
      title="Weak tags"
      subtitle={`Target band ${weak.band_lo}–${weak.band_hi}: the tags most likely to cost you points there`}
    >
      <div id="weak" />
      {!weak.enough_data ? (
        <NotEnough message={weak.message} />
      ) : (
        <>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid horizontal={false} stroke={c.grid} />
                <XAxis type="number" stroke={c.axis} fontSize={12} />
                <YAxis type="category" dataKey="tag" width={120} stroke={c.axis} fontSize={12} />
                <Tooltip {...tooltipStyle(c)} formatter={(v: number) => [v, "weakness × 100"]} />
                <Bar dataKey="score" fill={c.accent} radius={[0, 4, 4, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[460px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide muted">
                <tr>
                  <th className="py-1 pr-2">Tag</th>
                  <th className="py-1 pr-2" title="Share of problemset problems in the band with this tag">Importance</th>
                  <th className="py-1 pr-2" title="Smoothed solve rate in the band">Success</th>
                  <th className="py-1 pr-2" title="min(1, solved in band / 10)">Coverage</th>
                  <th className="py-1 pr-2">In band</th>
                  <th className="py-1">Score</th>
                </tr>
              </thead>
              <tbody>
                {weak.tags.map((t) => (
                  <tr key={t.tag} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 pr-2 font-medium">{t.tag}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{pct(t.importance)}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{pct(t.success)}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{pct(t.coverage)}</td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      {t.solved_in_band} / {t.attempted_in_band}
                    </td>
                    <td className="py-1.5 tabular-nums">{(t.weakness * 100).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details className="mt-3 text-sm muted">
            <summary className="cursor-pointer">How is this scored?</summary>
            <p className="mt-2">
              weakness = importance × (1 − success) × (1 − {weak.coverage_weight} × coverage). <b>Importance</b> is how
              often the tag appears among all Codeforces problems rated {weak.band_lo}–{weak.band_hi}. <b>Success</b> is
              your solve rate on those problems, smoothed toward your overall band rate ({pct(weak.prior)}) with{" "}
              {weak.smoothing_a} pseudo-attempts so a single miss doesn't dominate. <b>Coverage</b> is solved problems in
              the band divided by {weak.coverage_full}, capped at 1: tags you've already practised a lot are discounted.
            </p>
          </details>
        </>
      )}
    </Section>
  );
}

// --- rating bands --------------------------------------------------------------------------------------

type BandMode = "all" | "contest" | "practice";

export function BandsSection({ bands }: { bands: Bands }) {
  const c = useChartColors();
  const [mode, setMode] = useState<BandMode>("all");
  const data = bands.bands.map((b) => {
    const [att, sol] =
      mode === "contest"
        ? [b.contest_attempted, b.contest_solved]
        : mode === "practice"
          ? [b.practice_attempted, b.practice_solved]
          : [b.attempted, b.solved];
    return { bucket: b.bucket, solved: sol, unsolved: att - sol, rate: att ? sol / att : null };
  });
  return (
    <Section
      title="Rating bands"
      subtitle="Problems tried per 100-point band (unrated problems excluded)"
      right={
        <div className="flex rounded-lg border border-slate-200 p-0.5 text-xs dark:border-slate-700" role="tablist">
          {(["all", "contest", "practice"] as BandMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              role="tab"
              aria-selected={mode === m}
              className={`rounded-md px-2 py-1 capitalize ${mode === m ? "bg-slate-200 dark:bg-slate-700" : ""}`}
            >
              {m === "contest" ? "In contest" : m}
            </button>
          ))}
        </div>
      }
    >
      {!bands.enough_data ? (
        <NotEnough message={bands.message} />
      ) : (
        <div className="h-64">
          <ResponsiveContainer>
            <BarChart data={data} margin={{ left: -16, right: 8 }}>
              <CartesianGrid vertical={false} stroke={c.grid} />
              <XAxis dataKey="bucket" stroke={c.axis} fontSize={12} />
              <YAxis stroke={c.axis} fontSize={12} allowDecimals={false} />
              <Tooltip
                {...tooltipStyle(c)}
                formatter={(v: number, name: string) => [v, name]}
                labelFormatter={(b: number) => {
                  const row = data.find((d) => d.bucket === b);
                  return `${b}–${b + 99} · solve rate ${pct(row?.rate ?? null)}`;
                }}
              />
              <ReferenceLine x={Math.floor(bands.level.value / 100) * 100} stroke={c.primary} strokeDasharray="4 4" label={{ value: "you", fill: c.axis, fontSize: 11, position: "top" }} />
              <Bar dataKey="solved" stackId="a" fill={c.good} name="solved" isAnimationActive={false} />
              <Bar dataKey="unsolved" stackId="a" fill={c.secondary} name="not solved" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Section>
  );
}

// --- rating history -----------------------------------------------------------------------------------------

export function RatingSection({ progress }: { progress: Progress }) {
  const c = useChartColors();
  const data = progress.history.map((h) => ({ time: h.time, rating: h.new_rating, delta: h.delta, name: h.contest_name }));
  const fmt = axisDate(data.map((d) => d.time));
  const ratings = data.map((d) => d.rating).concat(progress.target ?? []);
  const lo = Math.max(0, Math.floor((Math.min(...ratings) - 100) / 100) * 100);
  const hi = Math.ceil((Math.max(...ratings) + 100) / 100) * 100;
  return (
    <Section
      title="Rating history"
      subtitle={
        progress.enough_data ? (
          <>
            {progress.avg_delta_recent !== null &&
              `Average change over the last ${progress.recent_contests} contests: ${signed(+progress.avg_delta_recent.toFixed(1))}. `}
            {progress.estimate_note}
          </>
        ) : undefined
      }
    >
      {!progress.enough_data ? (
        <NotEnough message={progress.message} />
      ) : (
        <div className="h-72">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ left: -8, right: 8, top: 8 }}>
              {rankBands(lo, hi).map((b) => (
                <ReferenceArea key={b.rank.name} y1={b.from} y2={b.to} fill={c.dark ? b.rank.dark : b.rank.color} fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
              ))}
              <CartesianGrid stroke={c.grid} strokeOpacity={0.6} />
              <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} tickFormatter={fmt} stroke={c.axis} fontSize={12} minTickGap={40} />
              <YAxis domain={[lo, hi]} stroke={c.axis} fontSize={12} />
              <Tooltip
                {...tooltipStyle(c)}
                labelFormatter={(t: number) => {
                  const row = data.find((d) => d.time === t);
                  return row ? `${row.name} · ${shortDate(t)}` : shortDate(t);
                }}
                formatter={(v: number, _n, p) => [`${v} (${signed(p.payload.delta)})`, "rating"]}
              />
              {progress.target !== null && (
                <ReferenceLine y={progress.target} stroke={c.accent} strokeDasharray="6 4" label={{ value: `target ${progress.target}`, fill: c.accent, fontSize: 11, position: "insideTopLeft" }} />
              )}
              <Line type="linear" dataKey="rating" stroke={c.primary} strokeWidth={2} dot={data.length < 60 ? { r: 2 } : false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {progress.contests_needed !== null && progress.contests_needed > 0 && (
        <p className="mt-2 text-sm">
          <span className="font-semibold">≈ {progress.contests_needed} contest{progress.contests_needed === 1 ? "" : "s"}</span>{" "}
          <span className="muted">to reach {progress.target} at your recent pace. This is a rough estimate.</span>
        </p>
      )}
    </Section>
  );
}

// --- practice rating ---------------------------------------------------------------------------------------------

export function PracticeSection({ progress }: { progress: Progress }) {
  const c = useChartColors();
  const data = progress.practice_history;
  const fmt = axisDate(data.map((d) => d.time));
  return (
    <Section
      title="Practice rating"
      subtitle="75th percentile rating of your last 30 distinct solved problems, over time"
      right={progress.practice_rating !== null ? <span className="text-2xl font-bold tabular-nums">{progress.practice_rating}</span> : undefined}
    >
      {progress.practice_message && <p className="mb-2 text-sm muted">{progress.practice_message}</p>}
      {data.length < 2 ? (
        <NotEnough message="Solve a few rated problems to see your practice rating over time." />
      ) : (
        <div className="h-56">
          <ResponsiveContainer>
            <LineChart data={data} margin={{ left: -8, right: 8, top: 8 }}>
              <CartesianGrid stroke={c.grid} />
              <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} tickFormatter={fmt} stroke={c.axis} fontSize={12} minTickGap={40} />
              <YAxis domain={[(m: number) => Math.floor((m - 100) / 100) * 100, (m: number) => Math.ceil((m + 100) / 100) * 100]} stroke={c.axis} fontSize={12} allowDecimals={false} />
              <Tooltip {...tooltipStyle(c)} labelFormatter={(t: number) => shortDate(t)} formatter={(v: number) => [v, "practice rating"]} />
              {progress.target !== null && <ReferenceLine y={progress.target} stroke={c.accent} strokeDasharray="6 4" />}
              <Line type="stepAfter" dataKey="rating" stroke={c.good} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Section>
  );
}
