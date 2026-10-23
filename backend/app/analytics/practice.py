"""Practice rating: the 75th percentile rating of the last 30 distinct solved problems."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from app import config
from app.analytics.types import ProblemAgg
from app.schemas import PracticePoint


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (same as numpy's default)."""
    if not values:
        raise ValueError("percentile of empty sequence")
    xs = sorted(values)
    pos = (len(xs) - 1) * p / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def solved_rated_in_order(aggs: Iterable[ProblemAgg]) -> list[ProblemAgg]:
    """Distinct solved problems with a rating, ordered by first AC time."""
    solved = [a for a in aggs if a.solved and a.rating is not None and a.first_ok_time is not None]
    return sorted(solved, key=lambda a: (a.first_ok_time, a.key))


def practice_rating(aggs: Iterable[ProblemAgg]) -> int | None:
    """Current practice rating, or None with no rated solves."""
    solved = solved_rated_in_order(aggs)
    window = [a.rating for a in solved[-config.PRACTICE_WINDOW :]]
    return round(percentile(window, config.PRACTICE_PERCENTILE)) if window else None


def practice_timeline(aggs: Iterable[ProblemAgg]) -> list[PracticePoint]:
    """Practice rating after each solve, keeping the last value per UTC day."""
    solved = solved_rated_in_order(aggs)
    per_day: dict[str, PracticePoint] = {}
    for i, agg in enumerate(solved):
        window = [a.rating for a in solved[max(0, i + 1 - config.PRACTICE_WINDOW) : i + 1]]
        day = datetime.fromtimestamp(agg.first_ok_time, timezone.utc).strftime("%Y-%m-%d")
        per_day[day] = PracticePoint(
            time=agg.first_ok_time,
            rating=round(percentile(window, config.PRACTICE_PERCENTILE)),
            window=len(window),
        )
    return list(per_day.values())
