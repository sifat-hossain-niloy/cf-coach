import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  DAY_MS,
  addSkip,
  completeReview,
  dueReviews,
  emptyMarks,
  excludedKeys,
  loadMarks,
  markEditorial,
  nextReviewAt,
  saveMarks,
} from "./marks";

const info = { key: "1700-C", name: "X", rating: 1600, tags: ["dp"], url: "https://codeforces.com/contest/1700/problem/C" };

describe("skips", () => {
  it("excludes skipped problems only on that day", () => {
    const m = addSkip(emptyMarks(), "2026-10-23", "1700-C");
    expect(excludedKeys(m, "2026-10-23")).toEqual(["1700-C"]);
    expect(excludedKeys(m, "2026-10-24")).toEqual([]);
  });
  it("is idempotent and prunes old days", () => {
    let m = emptyMarks();
    for (let d = 1; d <= 20; d++) m = addSkip(m, `2026-10-${String(d).padStart(2, "0")}`, "1-A");
    m = addSkip(m, "2026-10-20", "1-A");
    expect(m.skips["2026-10-20"]).toEqual(["1-A"]);
    expect(Object.keys(m.skips).length).toBeLessThanOrEqual(14);
  });
});

describe("needed editorial", () => {
  const t0 = Date.UTC(2026, 9, 1);
  it("hides the problem and brings it back after 7 then 21 days", () => {
    let m = markEditorial(emptyMarks(), info, t0);
    expect(excludedKeys(m, "2026-10-01")).toContain("1700-C");
    expect(dueReviews(m, t0 + 6 * DAY_MS)).toEqual([]);
    expect(dueReviews(m, t0 + 7 * DAY_MS).map((r) => r.key)).toEqual(["1700-C"]);
    m = completeReview(m, "1700-C");
    expect(nextReviewAt(m.editorial["1700-C"])).toBe(t0 + 21 * DAY_MS);
    expect(dueReviews(m, t0 + 20 * DAY_MS)).toEqual([]);
    expect(dueReviews(m, t0 + 21 * DAY_MS)).toHaveLength(1);
    m = completeReview(m, "1700-C");
    expect(nextReviewAt(m.editorial["1700-C"])).toBeNull();
    expect(dueReviews(m, t0 + 400 * DAY_MS)).toEqual([]);
  });
});

describe("storage", () => {
  beforeEach(() => localStorage.clear());
  it("round-trips per handle, case-insensitively", () => {
    saveMarks("Tourist", addSkip(emptyMarks(), "2026-10-23", "1-A"));
    expect(loadMarks("tourist").skips["2026-10-23"]).toEqual(["1-A"]);
    expect(loadMarks("petr")).toEqual(emptyMarks());
  });
  it("survives broken or unavailable storage", () => {
    localStorage.setItem("cfcoach:marks:x_user", "{not json");
    expect(loadMarks("x_user")).toEqual(emptyMarks());
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceeded");
    });
    expect(() => saveMarks("x_user", emptyMarks())).not.toThrow();
    spy.mockRestore();
  });
});
