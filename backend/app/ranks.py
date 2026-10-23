"""Codeforces rank thresholds, colors, and target selection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rank:
    name: str
    min_rating: int
    color: str


# Ascending. Colors match the ones Codeforces shows for each rank.
RANKS: tuple[Rank, ...] = (
    Rank("Newbie", -10_000, "#808080"),
    Rank("Pupil", 1200, "#008000"),
    Rank("Specialist", 1400, "#03a89e"),
    Rank("Expert", 1600, "#0000ff"),
    Rank("Candidate Master", 1900, "#aa00aa"),
    Rank("Master", 2100, "#ff8c00"),
    Rank("International Master", 2300, "#ff8c00"),
    Rank("Grandmaster", 2400, "#ff0000"),
    Rank("International Grandmaster", 2600, "#ff0000"),
    Rank("Legendary Grandmaster", 3000, "#ff0000"),
)


def rank_for(rating: int | None) -> Rank:
    """Rank for a rating; None (unrated) maps to Newbie."""
    if rating is None:
        return RANKS[0]
    current = RANKS[0]
    for rank in RANKS:
        if rating >= rank.min_rating:
            current = rank
    return current


def next_rank(rating: int | None) -> Rank | None:
    """The first rank whose threshold is strictly above `rating`; None at the top."""
    value = rating if rating is not None else 0
    for rank in RANKS[1:]:
        if rank.min_rating > value:
            return rank
    return None


def default_target(rating: int | None) -> int | None:
    """Target = the next rank threshold above the current rating."""
    nxt = next_rank(rating)
    return nxt.min_rating if nxt else None
