"""Current level, target selection, and the rough contests-needed estimate (pure)."""

from __future__ import annotations

import math
from collections.abc import Sequence

from app import config
from app.ranks import default_target
from app.schemas import Level, RatingPoint


def determine_level(
    rating: int | None, rated_contests: int, practice: int | None, rated_solves: int
) -> Level:
    """Contest rating if the user has contests, else practice rating, else a default."""
    if rated_contests > 0 and rating is not None:
        return Level(value=rating, source="contest", note=None)
    if practice is not None and rated_solves >= config.MIN_RATED_SOLVES_FOR_LEVEL:
        return Level(
            value=practice,
            source="practice",
            note="No rated contests yet, so your level comes from your practice rating.",
        )
    return Level(
        value=config.DEFAULT_LEVEL,
        source="default",
        note=(
            f"Fewer than {config.MIN_RATED_SOLVES_FOR_LEVEL} rated problems solved and no rated "
            f"contests, so your level defaults to {config.DEFAULT_LEVEL}."
        ),
    )


def choose_target(current: int, override: int | None = None) -> int | None:
    """Override if given, else the next rank threshold above `current` (None at the top)."""
    return override if override is not None else default_target(current)


def recent_average_delta(history: Sequence[RatingPoint], n: int = config.PROGRESS_RECENT_CONTESTS) -> float | None:
    recent = history[-n:]
    if not recent:
        return None
    return sum(p.delta for p in recent) / len(recent)


def contests_needed(gap: int | None, avg_delta: float | None) -> tuple[int | None, str]:
    """Rough estimate of contests to close `gap` at the recent pace, plus an explanation."""
    if gap is None:
        return None, "You are at the top rank. There is no next threshold."
    if gap <= 0:
        return 0, "You have already reached this target."
    if avg_delta is None:
        return None, "No rated contests yet, so there is no pace to project from."
    if avg_delta <= 0:
        return None, (
            f"Your average change over recent contests is {avg_delta:+.1f}, so at this pace "
            "the gap is not closing yet."
        )
    n = math.ceil(gap / avg_delta)
    unit = "contest" if n == 1 else "contests"
    return n, f"Rough estimate: about {n} {unit} at your recent average of {avg_delta:+.1f} per contest."
