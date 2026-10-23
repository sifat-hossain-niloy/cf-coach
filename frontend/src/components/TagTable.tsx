import { useState } from "react";
import type { Tags } from "../api/client";
import { pct } from "../lib/format";
import { NotEnough, Section } from "./common";

export function TagTable({ tags }: { tags: Tags }) {
  const [all, setAll] = useState(false);
  const rows = all ? tags.tags : tags.tags.slice(0, 12);
  return (
    <Section title="Tag stats" subtitle="Every tag you've tried, most-attempted first">
      {!tags.enough_data ? (
        <NotEnough message={tags.message} />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs uppercase tracking-wide muted">
                <tr>
                  <th className="py-1 pr-2">Tag</th>
                  <th className="py-1 pr-2">Solved</th>
                  <th className="py-1 pr-2">Rate</th>
                  <th className="py-1 pr-2" title="First judged submission was accepted">1st try</th>
                  <th className="py-1 pr-2" title="Average wrong submissions before AC">WA→AC</th>
                  <th className="py-1 pr-2">Median / max</th>
                  <th className="py-1">WA · TLE · MLE · RE</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.tag} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 pr-2 font-medium">{t.tag}</td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      {t.solved}/{t.attempted}
                    </td>
                    <td className="py-1.5 pr-2 tabular-nums">{pct(t.solve_rate)}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{pct(t.first_try_rate)}</td>
                    <td className="py-1.5 pr-2 tabular-nums">{t.avg_wrong_before_ac?.toFixed(2) ?? "–"}</td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      {t.median_rating_solved ?? "–"} / {t.max_rating_solved ?? "–"}
                    </td>
                    <td className="py-1.5 tabular-nums muted">
                      {t.verdicts.wa} · {t.verdicts.tle} · {t.verdicts.mle} · {t.verdicts.re}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {tags.tags.length > 12 && (
            <button onClick={() => setAll(!all)} className="mt-2 text-sm underline muted">
              {all ? "Show fewer" : `Show all ${tags.tags.length} tags`}
            </button>
          )}
        </>
      )}
    </Section>
  );
}
