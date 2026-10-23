"""Daily upsolve queue (pure).

Sources:
  A  attempted but never solved, rated level-200 .. level+400
  B  unsolved problems from contests the user took part in, rated up to level+500
  C  never-attempted problems carrying the user's top weak tags, in the target band

Determinism: every source's candidate pool is sorted, then shuffled with an RNG seeded from
(handle, date, source). Picks walk that shuffled order, so excluding one item (a skip) only
replaces that item and never reshuffles the rest. Candidates come from a snapshot of the
user's history *before* the queue's date, so solving an item today marks it solved instead
of swapping it out.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app import config
from app.analytics.importance import bucket_of
from app.analytics.types import ProblemAgg, ProblemKey, Prob
from app.schemas import QueueItem

Source = str  # "A" | "B" | "C"


@dataclass(frozen=True)
class Candidate:
    key: ProblemKey
    name: str
    rating: int | None
    tags: tuple[str, ...]
    source: Source
    reason: str


@dataclass(frozen=True)
class QueueInputs:
    handle_key: str
    date: str                              # YYYY-MM-DD
    level: int
    band: tuple[int, int]
    snapshot: dict[ProblemKey, ProblemAgg]  # user's problems before `date`
    current: dict[ProblemKey, ProblemAgg]   # user's problems now (for solved status)
    canon: dict[ProblemKey, ProblemKey]
    problems: Sequence[Prob]
    contests_taken: frozenset[int]
    weak_tags: Sequence[str]
    exclude: frozenset[ProblemKey] = frozenset()


def seed_for(handle_key: str, date: str, source: str = "") -> int:
    digest = hashlib.sha256(f"{handle_key.lower()}|{date}|{source}".encode()).hexdigest()
    return int(digest[:16], 16)


def split_quota(n: int, mix: Sequence[tuple[Source, int]] = config.QUEUE_MIX) -> dict[Source, int]:
    """Scale the default mix (1 A, 2 B, 2 C per 5) to `n` items (largest remainder)."""
    total = sum(w for _, w in mix)
    raw = {s: n * w / total for s, w in mix}
    quota = {s: math.floor(v) for s, v in raw.items()}
    leftover = n - sum(quota.values())
    for s, _ in sorted(mix, key=lambda sw: (-(raw[sw[0]] - quota[sw[0]]), -sw[1])):
        if leftover <= 0:
            break
        quota[s] += 1
        leftover -= 1
    return quota


def problem_url(key: ProblemKey) -> str:
    return f"https://codeforces.com/contest/{key[0]}/problem/{key[1]}"


# --- candidate pools -----------------------------------------------------------------------------


def _usable(p: Prob) -> bool:
    return config.SPECIAL_TAG not in p.tags and p.contest_id < config.GYM_CONTEST_MIN_ID


def source_a(inp: QueueInputs) -> list[Candidate]:
    lo, hi = inp.level + config.QUEUE_A_RANGE[0], inp.level + config.QUEUE_A_RANGE[1]
    out = [
        Candidate(a.key, a.name, a.rating, a.tags, "A",
                  f"attempted {a.attempts}× without AC, rated {a.rating}")
        for a in inp.snapshot.values()
        if a.attempted and not a.solved and a.rating is not None and lo <= a.rating <= hi
        and config.SPECIAL_TAG not in a.tags
    ]
    return sorted(out, key=lambda c: (abs(c.rating - inp.level), c.key))


def source_b(inp: QueueInputs) -> list[Candidate]:
    cap = inp.level + config.QUEUE_B_MAX_OFFSET
    stretch = inp.level + 200
    out = []
    for p in inp.problems:
        if p.contest_id not in inp.contests_taken or p.rating is None or p.rating > cap or not _usable(p):
            continue
        agg = inp.snapshot.get(inp.canon.get(p.key, p.key))
        if agg is not None and agg.solved:
            continue
        out.append(Candidate(p.key, p.name, p.rating, p.tags, "B",
                             f"unsolved from contest {p.contest_id}, which you took part in"))
    return sorted(out, key=lambda c: (abs(c.rating - stretch), -c.key[0], c.key))


def source_c(inp: QueueInputs) -> list[Candidate]:
    """Never-attempted band problems for the top weak tags.

    Each tag's pool is ranked (popular and recent first), its best POOL_SIZE are shuffled
    deterministically, and the tags are interleaved round-robin so several weak tags appear.
    """
    lo, hi = inp.band
    tags = list(inp.weak_tags[: config.QUEUE_C_TOP_TAGS])
    in_band = [
        p for p in inp.problems
        if p.rating is not None and lo <= p.rating <= hi and _usable(p)
        and inp.canon.get(p.key, p.key) not in inp.snapshot
    ]
    if not in_band or not tags:
        return []
    max_solved = max(p.solved_count for p in in_band) or 1
    max_cid = max(p.contest_id for p in in_band)

    def score(p: Prob) -> float:
        return 0.5 * math.log1p(p.solved_count) / math.log1p(max_solved) + 0.5 * p.contest_id / max_cid

    per_tag: list[list[Candidate]] = []
    for tag in tags:
        ranked = sorted((p for p in in_band if tag in p.tags), key=lambda p: (-score(p), p.key))
        pool = [
            Candidate(p.key, p.name, p.rating, p.tags, "C", f"weak tag: {tag}, band {bucket_of(p.rating)}")
            for p in ranked
        ]
        per_tag.append(_shuffled(pool, inp, f"C:{tag}"))
    out: list[Candidate] = []
    for i in range(max((len(x) for x in per_tag), default=0)):
        out.extend(pool[i] for pool in per_tag if i < len(pool))
    return out


def _shuffled(pool: list[Candidate], inp: QueueInputs, salt: str) -> list[Candidate]:
    """Deterministic order: shuffle the best POOL_SIZE candidates, then the rest in rank order."""
    head = pool[: config.QUEUE_POOL_SIZE]
    rng = random.Random(seed_for(inp.handle_key, inp.date, salt))
    rng.shuffle(head)
    return head + pool[config.QUEUE_POOL_SIZE :]


# --- assembly --------------------------------------------------------------------------------------


def build_queue(inp: QueueInputs, n: int = config.QUEUE_DEFAULT_N) -> list[QueueItem]:
    """Pick `n` problems by the source mix, fall back to other sources, order easy → hard."""
    pools = {
        "A": _shuffled(source_a(inp), inp, "A"),
        "B": _shuffled(source_b(inp), inp, "B"),
        "C": source_c(inp),  # shuffled per tag inside
    }
    cursors = {s: iter(p) for s, p in pools.items()}
    used: set[ProblemKey] = set()
    picked: list[Candidate] = []

    def take(source: Source) -> bool:
        for cand in cursors[source]:
            canon = inp.canon.get(cand.key, cand.key)
            if canon in used or cand.key in inp.exclude or canon in inp.exclude:
                continue
            used.add(canon)
            picked.append(cand)
            return True
        return False

    for source, k in split_quota(n).items():
        for _ in range(k):
            take(source)
    for source in ("C", "B", "A"):  # fallback order when a source ran dry
        while len(picked) < n and take(source):
            pass

    picked.sort(key=lambda c: (c.rating if c.rating is not None else 10_000, c.key))
    return [_to_item(c, inp) for c in picked]


def _to_item(c: Candidate, inp: QueueInputs) -> QueueItem:
    agg = inp.current.get(inp.canon.get(c.key, c.key))
    return QueueItem(
        contest_id=c.key[0],
        index=c.key[1],
        name=c.name,
        rating=c.rating,
        tags=list(c.tags),
        source=c.source,  # type: ignore[arg-type]
        reason=c.reason,
        url=problem_url(c.key),
        solved=bool(agg and agg.solved),
    )


def contests_taken(rated_contest_ids: Iterable[int], in_contest_sub_contest_ids: Iterable[int]) -> frozenset[int]:
    """Contests the user took part in: rated contests plus any with in-contest submissions."""
    return frozenset(rated_contest_ids) | frozenset(in_contest_sub_contest_ids)
