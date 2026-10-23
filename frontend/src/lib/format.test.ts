import { describe, expect, it } from "vitest";
import { HANDLE_RE, bandForTarget, needsSync, todayUTC } from "./format";
import { rankBands, rankFor } from "./ranks";

describe("needsSync", () => {
  const now = Date.parse("2026-10-23T12:00:00Z");
  it("syncs when never synced or older than 10 minutes", () => {
    expect(needsSync(null, now)).toBe(true);
    expect(needsSync("2026-10-23T11:49:59Z", now)).toBe(true);
    expect(needsSync("2026-10-23T11:55:00Z", now)).toBe(false);
  });
});

describe("handle validation", () => {
  it("matches the backend rule", () => {
    expect(HANDLE_RE.test("tourist")).toBe(true);
    expect(HANDLE_RE.test("a.b-c_d")).toBe(true);
    expect(HANDLE_RE.test("ab")).toBe(false);
    expect(HANDLE_RE.test("x".repeat(25))).toBe(false);
    expect(HANDLE_RE.test("no spaces")).toBe(false);
  });
});

describe("ranks", () => {
  it("uses Codeforces thresholds", () => {
    expect(rankFor(1199)?.name).toBe("Newbie");
    expect(rankFor(1900)?.name).toBe("Candidate Master");
    expect(rankFor(null)).toBeNull();
  });
  it("splits a rating range into rank bands", () => {
    const b = rankBands(1100, 1700);
    expect(b.map((x) => [x.from, x.to])).toEqual([[1100, 1200], [1200, 1400], [1400, 1600], [1600, 1700]]);
  });
});

describe("bandForTarget", () => {
  it("only widens the band for ambitious targets", () => {
    expect(bandForTarget(1500, null)).toBeNull();
    expect(bandForTarget(1500, 1600)).toBeNull();
    expect(bandForTarget(1500, 2100)).toEqual({ lo: 1600, hi: 2100 });
  });
});

it("todayUTC formats as YYYY-MM-DD", () => {
  expect(todayUTC(new Date("2026-10-23T23:59:00Z"))).toBe("2026-10-23");
});
