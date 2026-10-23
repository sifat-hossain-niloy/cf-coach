"""Weakness score per tag against a target rating band.

    importance(t) = share of problemset problems in the band carrying tag t
    success(t)    = (solved + a * prior) / (attempted + a)          (in the band)
    coverage(t)   = min(1, solved_in_band(t) / COVERAGE_FULL)
    weakness(t)   = importance(t) * (1 - success(t)) * (1 - W * coverage(t))
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from app import config
from app.analytics.importance import importance_in_band
from app.analytics.types import ProblemAgg
from app.schemas import WeakTag


def band_prior(aggs: list[ProblemAgg], lo: int, hi: int) -> float:
    """User's solve rate in the band, falling back to their overall rate, then to a constant."""
    in_band = [a for a in aggs if a.attempted and a.rating is not None and lo <= a.rating <= hi]
    if in_band:
        return sum(a.solved for a in in_band) / len(in_band)
    attempted = [a for a in aggs if a.attempted]
    if attempted:
        return sum(a.solved for a in attempted) / len(attempted)
    return config.WEAKNESS_FALLBACK_PRIOR


def weakness_scores(
    aggs: Iterable[ProblemAgg],
    bucket_counts: Mapping[tuple[int, str], int],
    lo: int,
    hi: int,
    top_n: int = config.WEAKNESS_TOP_N,
) -> tuple[list[WeakTag], float]:
    """Top `top_n` weak tags for band [lo, hi] (inclusive), plus the prior used."""
    aggs = list(aggs)
    prior = band_prior(aggs, lo, hi)
    importance = importance_in_band(bucket_counts, lo, hi)

    attempted: Counter[str] = Counter()
    solved: Counter[str] = Counter()
    for a in aggs:
        if a.attempted and a.rating is not None and lo <= a.rating <= hi:
            for tag in a.tags:
                attempted[tag] += 1
                solved[tag] += a.solved

    a_ = config.WEAKNESS_SMOOTHING_A
    scores: list[WeakTag] = []
    for tag, imp in importance.items():
        if tag == config.SPECIAL_TAG:
            continue
        success = (solved[tag] + a_ * prior) / (attempted[tag] + a_)
        coverage = min(1.0, solved[tag] / config.WEAKNESS_COVERAGE_FULL)
        weakness = imp * (1 - success) * (1 - config.WEAKNESS_COVERAGE_WEIGHT * coverage)
        scores.append(
            WeakTag(
                tag=tag,
                weakness=weakness,
                importance=imp,
                success=success,
                coverage=coverage,
                attempted_in_band=attempted[tag],
                solved_in_band=solved[tag],
            )
        )
    scores.sort(key=lambda w: (-w.weakness, w.tag))
    return scores[:top_n], prior
