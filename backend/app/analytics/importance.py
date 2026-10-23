"""Global problemset tag importance per rating bucket (precomputed once per problemset refresh)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from app.config import SPECIAL_TAG

TOTAL = "__total__"


def bucket_of(rating: int) -> int:
    """100-point bucket for a rating (e.g. 1750 → 1700)."""
    return rating // 100 * 100


def bucket_tag_counts(problems: Iterable[tuple[int | None, list[str]]]) -> dict[tuple[int, str], int]:
    """Count rated problems per (bucket, tag), plus (bucket, TOTAL). Input: (rating, tags) pairs."""
    counts: Counter[tuple[int, str]] = Counter()
    for rating, tags in problems:
        if rating is None or SPECIAL_TAG in tags:
            continue
        b = bucket_of(rating)
        counts[(b, TOTAL)] += 1
        for tag in set(tags):
            counts[(b, tag)] += 1
    return dict(counts)


def importance_in_band(
    counts: Mapping[tuple[int, str], int], lo: int, hi: int
) -> dict[str, float]:
    """Share of problemset problems rated in [lo, hi] that carry each tag."""
    total = 0
    per_tag: Counter[str] = Counter()
    for (bucket, tag), n in counts.items():
        if not lo <= bucket <= hi:
            continue
        if tag == TOTAL:
            total += n
        else:
            per_tag[tag] += n
    if total == 0:
        return {}
    return {tag: n / total for tag, n in per_tag.items()}
