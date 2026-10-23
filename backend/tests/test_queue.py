from app.analytics.dedup import aggregate
from app.analytics.types import Prob, Sub
from app.queue import QueueInputs, build_queue, seed_for, split_quota

_ids = iter(range(1, 10**7))


def S(cid, idx, verdict="OK", rating=1500, tags=("dp",), t=100):
    return Sub(next(_ids), cid, idx, f"{cid}{idx}", rating, tuple(tags), verdict, "CONTESTANT", t)


def world(level=1500, subs=(), problems=None, taken=(), weak=("dp", "graphs"), date="2026-10-23",
          handle="someone", exclude=(), current_subs=None):
    problems = problems if problems is not None else default_problems()
    snap = aggregate(subs, {})
    cur = aggregate(current_subs if current_subs is not None else subs, {})
    return QueueInputs(
        handle_key=handle, date=date, level=level, band=(level + 100, level + 400),
        snapshot=snap, current=cur, canon={}, problems=problems,
        contests_taken=frozenset(taken), weak_tags=list(weak), exclude=frozenset(exclude),
    )


def default_problems():
    out = []
    for cid in range(1000, 1100):
        for j, idx in enumerate("ABCDEF"):
            rating = 800 + 300 * j
            tags = ("dp",) if cid % 2 else ("graphs",)
            out.append(Prob(cid, idx, f"P{cid}{idx}", rating, tags, solved_count=cid * 10 - j))
    return out


def sources(items):
    return sorted(i.source for i in items)


def test_split_quota_default_and_scaled():
    assert split_quota(5) == {"A": 1, "B": 2, "C": 2}
    assert sum(split_quota(7).values()) == 7
    assert split_quota(1) in ({"A": 0, "B": 1, "C": 0}, {"A": 0, "B": 0, "C": 1})


def test_default_mix_when_all_sources_available():
    attempted = [S(1001, "C", "WRONG_ANSWER", rating=1400), S(1003, "C", "WRONG_ANSWER", rating=1700)]
    items = build_queue(world(subs=attempted, taken=range(1050, 1060)), 5)
    assert sources(items) == ["A", "B", "B", "C", "C"]


def test_fallback_when_a_and_b_run_dry():
    items = build_queue(world(), 5)
    assert sources(items) == ["C"] * 5


def test_fallback_to_b_when_no_weak_tags():
    items = build_queue(world(taken=range(1000, 1100), weak=()), 5)
    assert sources(items) == ["B"] * 5


def test_queue_shorter_than_n_when_nothing_left():
    items = build_queue(world(problems=[], weak=()), 5)
    assert items == []


def test_deterministic_per_handle_and_date():
    a = build_queue(world(taken=range(1000, 1100)), 5)
    b = build_queue(world(taken=range(1000, 1100)), 5)
    assert [(i.contest_id, i.index) for i in a] == [(i.contest_id, i.index) for i in b]
    other_day = build_queue(world(taken=range(1000, 1100), date="2026-10-24"), 5)
    other_user = build_queue(world(taken=range(1000, 1100), handle="someone_else"), 5)
    keys = {(i.contest_id, i.index) for i in a}
    assert keys != {(i.contest_id, i.index) for i in other_day}
    assert keys != {(i.contest_id, i.index) for i in other_user}
    assert seed_for("Someone", "2026-10-23") == seed_for("someone", "2026-10-23")


def test_ladder_easy_to_hard_and_links():
    items = build_queue(world(taken=range(1000, 1100)), 5)
    ratings = [i.rating for i in items]
    assert ratings == sorted(ratings)
    assert all(i.url == f"https://codeforces.com/contest/{i.contest_id}/problem/{i.index}" for i in items)


def test_ranges_respected():
    items = build_queue(world(taken=range(1000, 1100)), 10)
    for i in items:
        if i.source == "B":
            assert i.rating <= 1500 + 500
        if i.source == "C":
            assert 1600 <= i.rating <= 1900 and i.reason.startswith("weak tag: ")


def test_skip_replaces_only_that_item():
    base = build_queue(world(taken=range(1000, 1100)), 5)
    skipped = (base[0].contest_id, base[0].index)
    again = build_queue(world(taken=range(1000, 1100), exclude=[skipped]), 5)
    before = {(i.contest_id, i.index) for i in base}
    after = {(i.contest_id, i.index) for i in again}
    assert skipped not in after and len(after) == 5
    assert len(before & after) == 4


def test_solved_today_stays_in_queue_marked_solved():
    base = build_queue(world(taken=range(1000, 1100)), 5)
    first = base[0]
    solved_now = [S(first.contest_id, first.index, "OK", first.rating, tuple(first.tags), t=10**10)]
    again = build_queue(world(taken=range(1000, 1100), current_subs=solved_now), 5)
    assert [(i.contest_id, i.index) for i in again] == [(i.contest_id, i.index) for i in base]
    assert again[0].solved and not any(i.solved for i in again[1:])


def test_already_solved_and_special_never_suggested():
    problems = [Prob(1000, "A", "x", 1700, ("dp",), 5), Prob(1001, "A", "y", 1700, ("dp", "*special"), 5)]
    subs = [S(1000, "A", "OK", 1700)]
    assert build_queue(world(subs=subs, problems=problems, taken=[1000, 1001]), 5) == []
