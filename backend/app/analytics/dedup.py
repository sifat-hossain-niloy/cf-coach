"""Parallel-round deduplication and per-problem aggregation of a user's submissions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from app import config
from app.analytics.types import ProblemAgg, ProblemKey, Sub

ProblemRef = tuple[ProblemKey, str, int | None]  # (key, name, rating)


def _normalise(name: str) -> str:
    return " ".join(name.split()).casefold()


def _ratings_compatible(a: int | None, b: int | None) -> bool:
    return a is None or b is None or abs(a - b) <= config.DEDUP_MAX_RATING_DIFF


def build_canonical_map(refs: Iterable[ProblemRef]) -> dict[ProblemKey, ProblemKey]:
    """Map each problem key to a canonical key, merging Div1/Div2 parallel copies.

    Two problems merge when they share a name, their contestIds differ by exactly 1
    (same-contest duplicates such as E1/E2 easy/hard versions stay separate), and their
    ratings are within DEDUP_MAX_RATING_DIFF (or one is unrated). The canonical key is the
    one with the lower contestId.
    """
    by_name: dict[str, dict[ProblemKey, int | None]] = defaultdict(dict)
    for key, name, rating in refs:
        group = by_name[_normalise(name)]
        if group.get(key) is None:
            group[key] = rating

    canon: dict[ProblemKey, ProblemKey] = {}
    for group in by_name.values():
        items = sorted(group.items())
        for key, rating in items:
            canon[key] = key
            for other, other_rating in items:
                if other[0] == key[0] - 1 and _ratings_compatible(rating, other_rating):
                    canon[key] = canon[other]
                    break
    return canon


def aggregate(subs: Iterable[Sub], canon: dict[ProblemKey, ProblemKey]) -> dict[ProblemKey, ProblemAgg]:
    """Fold submissions into one ProblemAgg per canonical problem ("*special" problems dropped)."""
    out: dict[ProblemKey, ProblemAgg] = {}
    for s in sorted(subs, key=lambda s: (s.time, s.id)):
        if config.SPECIAL_TAG in s.tags or s.contest_id >= config.GYM_CONTEST_MIN_ID:
            continue
        key = canon.get(s.key, s.key)
        agg = out.get(key)
        if agg is None:
            agg = out[key] = ProblemAgg(key=key, name=s.name, rating=s.rating, tags=s.tags)
        agg.member_keys.add(s.key)
        if agg.rating is None and s.rating is not None:
            agg.rating = s.rating
        if s.tags and not set(s.tags) <= set(agg.tags):
            agg.tags = tuple(sorted(set(agg.tags) | set(s.tags)))
        _add_submission(agg, s)
    return out


def _add_submission(agg: ProblemAgg, s: Sub) -> None:
    if s.verdict in config.IGNORED_VERDICTS_FOR_ATTEMPTS:
        return
    in_contest = s.participant_type in config.IN_CONTEST_TYPES
    ok = s.verdict == "OK"
    if agg.attempts == 0:
        agg.first_attempt_time = s.time
        agg.first_try_ok = ok
    agg.attempts += 1
    agg.verdicts[s.verdict or "UNKNOWN"] += 1
    if in_contest:
        agg.contest_attempted = True
        agg.contest_solved |= ok
    else:
        agg.practice_attempted = True
        agg.practice_solved |= ok
    if ok:
        if not agg.solved:
            agg.solved = True
            agg.first_ok_time = s.time
    elif not agg.solved:
        agg.wrong_before_ac += 1
