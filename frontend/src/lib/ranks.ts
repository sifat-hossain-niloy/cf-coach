// Rank thresholds and colors (mirrors backend app/ranks.py), plus readable dark-mode variants.

export interface Rank {
  name: string;
  min: number;
  color: string; // Codeforces color, used on light backgrounds
  dark: string; // same hue, lifted so it stays readable on dark backgrounds
}

export const RANKS: Rank[] = [
  { name: "Newbie", min: -Infinity, color: "#808080", dark: "#a3a3a3" },
  { name: "Pupil", min: 1200, color: "#008000", dark: "#4ade80" },
  { name: "Specialist", min: 1400, color: "#03a89e", dark: "#2dd4bf" },
  { name: "Expert", min: 1600, color: "#0000ff", dark: "#7c8cff" },
  { name: "Candidate Master", min: 1900, color: "#aa00aa", dark: "#e879f9" },
  { name: "Master", min: 2100, color: "#ff8c00", dark: "#ffa94d" },
  { name: "International Master", min: 2300, color: "#ff8c00", dark: "#ffa94d" },
  { name: "Grandmaster", min: 2400, color: "#ff0000", dark: "#ff5c5c" },
  { name: "International Grandmaster", min: 2600, color: "#ff0000", dark: "#ff5c5c" },
  { name: "Legendary Grandmaster", min: 3000, color: "#ff0000", dark: "#ff5c5c" },
];

export function rankFor(rating: number | null | undefined): Rank | null {
  if (rating === null || rating === undefined) return null;
  let r = RANKS[0];
  for (const rank of RANKS) if (rating >= rank.min) r = rank;
  return r;
}

export function rankColor(rating: number | null | undefined, dark: boolean): string {
  const r = rankFor(rating);
  if (!r) return dark ? "#cbd5e1" : "#334155";
  return dark ? r.dark : r.color;
}

/** Horizontal bands for the rating chart background. */
export function rankBands(lo: number, hi: number): { from: number; to: number; rank: Rank }[] {
  const out: { from: number; to: number; rank: Rank }[] = [];
  RANKS.forEach((rank, i) => {
    const from = Math.max(lo, rank.min === -Infinity ? lo : rank.min);
    const to = Math.min(hi, i + 1 < RANKS.length ? RANKS[i + 1].min : hi);
    if (to > from) out.push({ from, to, rank });
  });
  return out;
}
