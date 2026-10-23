"""Plain data types the pure analytics functions operate on (no DB, no I/O)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

ProblemKey = tuple[int, str]  # (contestId, index)


@dataclass(frozen=True)
class Sub:
    """One submission, already filtered of gym entries."""

    id: int
    contest_id: int
    index: str
    name: str
    rating: int | None
    tags: tuple[str, ...]
    verdict: str | None
    participant_type: str | None
    time: int

    @property
    def key(self) -> ProblemKey:
        return (self.contest_id, self.index)


@dataclass(frozen=True)
class Prob:
    """One problemset problem."""

    contest_id: int
    index: str
    name: str
    rating: int | None
    tags: tuple[str, ...]
    solved_count: int = 0

    @property
    def key(self) -> ProblemKey:
        return (self.contest_id, self.index)


@dataclass
class ProblemAgg:
    """Everything the user did on one (deduplicated) problem."""

    key: ProblemKey
    name: str
    rating: int | None
    tags: tuple[str, ...]
    attempts: int = 0                 # judged submissions (CE / skipped / testing excluded)
    solved: bool = False
    first_ok_time: int | None = None
    first_attempt_time: int | None = None
    first_try_ok: bool = False        # the first judged submission was OK
    wrong_before_ac: int = 0          # judged non-OK submissions before the first OK
    contest_attempted: bool = False
    contest_solved: bool = False
    practice_attempted: bool = False
    practice_solved: bool = False
    verdicts: Counter[str] = field(default_factory=Counter)
    member_keys: set[ProblemKey] = field(default_factory=set)

    @property
    def attempted(self) -> bool:
        return self.attempts > 0 or self.solved
