import { useEffect, useMemo, useState } from "react";
import { api, type Band, type QueueItem } from "../api/client";
import { todayUTC } from "../lib/format";
import { useApi } from "../lib/hooks";
import {
  addSkip,
  completeReview,
  dueReviews,
  excludedKeys,
  loadMarks,
  markEditorial,
  nextReviewAt,
  problemKey,
  saveMarks,
  type EditorialMark,
  type Marks,
} from "../lib/marks";
import { rankColor } from "../lib/ranks";
import { useDark } from "../lib/theme";
import { ErrorNote, NotEnough, Section, Skeleton } from "./common";

const SOURCE_LABEL: Record<QueueItem["source"], string> = {
  A: "Unfinished",
  B: "From your contest",
  C: "Weak tag",
};

export function QueueSection({ handle, version, band }: { handle: string; version: number; band: Band | null }) {
  const date = todayUTC();
  const [n, setN] = useState(5);
  const [marks, setMarks] = useState<Marks>(() => loadMarks(handle));
  useEffect(() => setMarks(loadMarks(handle)), [handle]);
  const update = (m: Marks) => (setMarks(m), saveMarks(handle, m));

  const exclude = useMemo(() => excludedKeys(marks, date), [marks, date]);
  const q = useApi(() => api.queue(handle, date, n, exclude, band), [handle, date, n, exclude.join(","), band?.lo, band?.hi, version]);
  const reviews = dueReviews(marks, Date.now());
  const done = q.data?.items.filter((i) => i.solved).length ?? 0;

  return (
    <Section
      title="Today's upsolve queue"
      subtitle={
        q.data
          ? `${date} · ordered easy → hard · ${done}/${q.data.items.length} solved · same list all day`
          : date
      }
      right={
        <label className="flex items-center gap-1 text-sm muted">
          Size
          <select value={n} onChange={(e) => setN(Number(e.target.value))} className="rounded-md border border-slate-300 bg-transparent px-1 py-0.5 dark:border-slate-700">
            {[3, 5, 8, 10].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
      }
    >
      {reviews.length > 0 && <ReviewList reviews={reviews} onDone={(k) => update(completeReview(marks, k))} />}
      <ErrorNote error={q.error} />
      {q.loading && !q.data ? (
        <Skeleton h={260} />
      ) : q.data && !q.data.enough_data ? (
        <NotEnough message={q.data.message} />
      ) : (
        <ol className="space-y-2">
          {q.data?.items.map((item) => (
            <QueueRow
              key={problemKey(item.contest_id, item.index)}
              item={item}
              onSkip={() => update(addSkip(marks, date, problemKey(item.contest_id, item.index)))}
              onEditorial={() =>
                update(
                  markEditorial(
                    marks,
                    { key: problemKey(item.contest_id, item.index), name: item.name, rating: item.rating, tags: item.tags, url: item.url },
                    Date.now(),
                  ),
                )
              }
            />
          ))}
        </ol>
      )}
      <p className="mt-3 text-xs muted">
        Solved problems get a ✓ after your next sync. Skips and "needed editorial" marks are saved in this browser only;
        editorial problems come back for review after 7 and 21 days.
      </p>
    </Section>
  );
}

function QueueRow({ item, onSkip, onEditorial }: { item: QueueItem; onSkip: () => void; onEditorial: () => void }) {
  const dark = useDark();
  return (
    <li
      className={`flex flex-col gap-2 rounded-xl border p-3 sm:flex-row sm:items-center ${
        item.solved
          ? "border-green-300 bg-green-50 dark:border-green-900 dark:bg-green-950/30"
          : "border-slate-200 dark:border-slate-800"
      }`}
    >
      <div className="flex shrink-0 items-center gap-2 sm:w-20 sm:flex-col sm:items-start sm:gap-0">
        <span className="text-lg font-bold tabular-nums" style={{ color: rankColor(item.rating, dark) }}>
          {item.rating ?? "?"}
        </span>
        <span className="chip">{SOURCE_LABEL[item.source]}</span>
      </div>
      <div className="min-w-0 flex-1">
        <a href={item.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
          {item.solved && <span className="mr-1 text-green-600 dark:text-green-400" aria-label="solved">✓</span>}
          {item.contest_id}
          {item.index}. {item.name}
        </a>
        <p className="text-sm muted">{item.reason}</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {item.tags.map((t) => <span key={t} className="chip">{t}</span>)}
        </div>
      </div>
      {!item.solved && (
        <div className="flex shrink-0 gap-2">
          <button onClick={onSkip} className="btn-ghost text-xs">Skip</button>
          <button onClick={onEditorial} className="btn-ghost text-xs" title="Hide it now and bring it back after 7 and 21 days">
            Needed editorial
          </button>
        </div>
      )}
    </li>
  );
}

function ReviewList({ reviews, onDone }: { reviews: EditorialMark[]; onDone: (key: string) => void }) {
  return (
    <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30">
      <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">Review due: try these again without the editorial</p>
      <ul className="mt-2 space-y-1">
        {reviews.map((r) => (
          <li key={r.key} className="flex flex-wrap items-center gap-2 text-sm">
            <a href={r.url} target="_blank" rel="noreferrer" className="font-medium hover:underline">
              {r.key.replace("-", "")}. {r.name}
            </a>
            <span className="muted">{r.rating ?? "?"} · review {r.reviewsDone + 1} of 2</span>
            <button onClick={() => onDone(r.key)} className="btn-ghost ml-auto px-2 py-0.5 text-xs">
              Done{nextReviewAt({ ...r, reviewsDone: r.reviewsDone + 1 }) ? ", remind me later" : ""}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
