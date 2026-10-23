// Queue marks kept in the browser (users are anonymous): skips and "needed editorial".
// Editorial problems leave the queue, then come back for review 7 and 21 days after marking.
import { readJSON, writeJSON } from "./storage";

export const DAY_MS = 86_400_000;
export const REVIEW_DAYS = [7, 21] as const;

export interface ProblemInfo {
  key: string; // "1700-C"
  name: string;
  rating: number | null;
  tags: string[];
  url: string;
}

export interface EditorialMark extends ProblemInfo {
  markedAt: number;
  reviewsDone: number; // 0, 1 or 2 (2 = finished)
}

export interface Marks {
  skips: Record<string, string[]>; // date → problem keys skipped that day
  editorial: Record<string, EditorialMark>;
}

export const emptyMarks = (): Marks => ({ skips: {}, editorial: {} });

export const problemKey = (contestId: number, index: string) => `${contestId}-${index}`;

const storageKey = (handle: string) => `cfcoach:marks:${handle.toLowerCase()}`;

export function loadMarks(handle: string): Marks {
  const m = readJSON<Partial<Marks>>(storageKey(handle), {});
  return { skips: m.skips ?? {}, editorial: m.editorial ?? {} };
}

export function saveMarks(handle: string, marks: Marks): void {
  writeJSON(storageKey(handle), marks);
}

export function addSkip(marks: Marks, date: string, key: string): Marks {
  const day = marks.skips[date] ?? [];
  if (day.includes(key)) return marks;
  // Keep only the last two weeks of skip lists so storage stays small.
  const skips = Object.fromEntries(
    Object.entries(marks.skips)
      .sort(([a], [b]) => b.localeCompare(a))
      .slice(0, 13),
  );
  return { ...marks, skips: { ...skips, [date]: [...day, key] } };
}

export function markEditorial(marks: Marks, info: ProblemInfo, now: number): Marks {
  return { ...marks, editorial: { ...marks.editorial, [info.key]: { ...info, markedAt: now, reviewsDone: 0 } } };
}

/** When the next review is due, or null once both reviews are done. */
export function nextReviewAt(mark: EditorialMark): number | null {
  const days = REVIEW_DAYS[mark.reviewsDone];
  return days === undefined ? null : mark.markedAt + days * DAY_MS;
}

/** Editorial problems whose next review date has arrived, oldest first. */
export function dueReviews(marks: Marks, now: number): EditorialMark[] {
  return Object.values(marks.editorial)
    .filter((m) => {
      const due = nextReviewAt(m);
      return due !== null && due <= now;
    })
    .sort((a, b) => a.markedAt - b.markedAt);
}

export function completeReview(marks: Marks, key: string): Marks {
  const m = marks.editorial[key];
  if (!m) return marks;
  return { ...marks, editorial: { ...marks.editorial, [key]: { ...m, reviewsDone: m.reviewsDone + 1 } } };
}

/** Keys the server should leave out of today's queue: today's skips and every editorial mark. */
export function excludedKeys(marks: Marks, date: string): string[] {
  return Array.from(new Set([...(marks.skips[date] ?? []), ...Object.keys(marks.editorial)])).sort();
}
