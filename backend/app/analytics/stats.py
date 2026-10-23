"""Tag stats and rating-band stats (pure)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from statistics import median

from app.analytics.importance import bucket_of
from app.analytics.types import ProblemAgg
from app.schemas import BandStat, TagStat, VerdictCounts

VERDICT_FIELDS = {
    "WRONG_ANSWER": "wa",
    "TIME_LIMIT_EXCEEDED": "tle",
    "MEMORY_LIMIT_EXCEEDED": "mle",
    "RUNTIME_ERROR": "re",
}


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def tag_stats(aggs: Iterable[ProblemAgg]) -> list[TagStat]:
    """Per-tag stats over attempted problems, most-attempted first."""
    by_tag: dict[str, list[ProblemAgg]] = defaultdict(list)
    for agg in aggs:
        if agg.attempted:
            for tag in agg.tags:
                by_tag[tag].append(agg)

    out: list[TagStat] = []
    for tag, problems in by_tag.items():
        solved = [p for p in problems if p.solved]
        ratings = [p.rating for p in solved if p.rating is not None]
        verdicts = VerdictCounts()
        for p in problems:
            for verdict, n in p.verdicts.items():
                field = VERDICT_FIELDS.get(verdict)
                if field:
                    setattr(verdicts, field, getattr(verdicts, field) + n)
        judged = [p for p in problems if p.attempts > 0]
        out.append(
            TagStat(
                tag=tag,
                attempted=len(problems),
                solved=len(solved),
                solve_rate=_rate(len(solved), len(problems)),
                first_try_rate=_rate(sum(p.first_try_ok for p in judged), len(judged)),
                avg_wrong_before_ac=(
                    sum(p.wrong_before_ac for p in solved) / len(solved) if solved else None
                ),
                median_rating_solved=int(median(ratings)) if ratings else None,
                max_rating_solved=max(ratings) if ratings else None,
                verdicts=verdicts,
            )
        )
    out.sort(key=lambda t: (-t.attempted, t.tag))
    return out


def band_stats(aggs: Iterable[ProblemAgg]) -> list[BandStat]:
    """Per 100-point rating bucket; unrated problems are skipped."""
    buckets: dict[int, BandStat] = {}
    for agg in aggs:
        if agg.rating is None or not agg.attempted:
            continue
        b = bucket_of(agg.rating)
        stat = buckets.get(b) or BandStat(bucket=b)
        buckets[b] = stat
        stat.attempted += 1
        stat.solved += agg.solved
        stat.contest_attempted += agg.contest_attempted
        stat.contest_solved += agg.contest_solved
        stat.practice_attempted += agg.practice_attempted
        stat.practice_solved += agg.practice_solved
    for stat in buckets.values():
        stat.solve_rate = _rate(stat.solved, stat.attempted)
    return [buckets[b] for b in sorted(buckets)]
