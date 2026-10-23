import pytest

from app.analytics.dedup import aggregate, build_canonical_map
from app.analytics.importance import TOTAL, bucket_tag_counts, importance_in_band
from app.analytics.practice import percentile, practice_rating, practice_timeline
from app.analytics.progress import choose_target, contests_needed, determine_level, recent_average_delta
from app.analytics.stats import band_stats, tag_stats
from app.analytics.types import Sub
from app.analytics.weakness import band_prior, weakness_scores
from app.ranks import default_target, next_rank, rank_for
from app.schemas import RatingPoint
from app.sync import parse_problemset
from tests.conftest import load_fixture

_ids = iter(range(1, 1_000_000))


def S(cid, idx, verdict="OK", rating=1500, tags=("dp",), t=None, ptype="PRACTICE", name=None):
    i = next(_ids)
    return Sub(i, cid, idx, name or f"{cid}{idx}", rating, tuple(tags), verdict, ptype, t if t is not None else i)


# --- parallel-round dedup -------------------------------------------------------------------------


def test_parallel_rounds_merge_when_ids_adjacent():
    canon = build_canonical_map([((1700, "C"), "Same Thing", 1600), ((1701, "A"), "Same Thing", 1600)])
    assert canon[(1701, "A")] == (1700, "C") and canon[(1700, "C")] == (1700, "C")


def test_same_contest_easy_hard_versions_stay_separate():
    canon = build_canonical_map([((1531, "E1"), "Tree", None), ((1531, "E2"), "Tree", None)])
    assert canon[(1531, "E1")] != canon[(1531, "E2")]


def test_far_apart_contests_with_same_name_stay_separate():
    canon = build_canonical_map([((100, "A"), "Game", 800), ((900, "A"), "Game", 800)])
    assert canon[(100, "A")] != canon[(900, "A")]


def test_adjacent_but_very_different_ratings_stay_separate():
    # Real case from the problemset: 505A and 506E share a title but are different problems.
    rows = parse_problemset(load_fixture("problemset_sample.json")["result"])
    refs = [((r["contest_id"], r["index"]), r["name"], r["rating"]) for r in rows]
    canon = build_canonical_map(refs)
    assert canon[(506, "E")] != canon[(505, "A")]
    assert canon[(421, "D")] == canon[(420, "C")]  # genuine parallel copy, both rated 1900


def test_solving_either_copy_counts_once():
    subs = [S(1700, "C", "WRONG_ANSWER", name="X"), S(1701, "A", "OK", name="X")]
    canon = build_canonical_map([(s.key, s.name, s.rating) for s in subs])
    aggs = aggregate(subs, canon)
    assert len(aggs) == 1
    agg = next(iter(aggs.values()))
    assert agg.solved and agg.attempts == 2 and agg.wrong_before_ac == 1


# --- aggregation & tag stats ------------------------------------------------------------------------


def test_aggregate_ignores_special_gym_and_compile_errors():
    subs = [
        S(1, "A", tags=("*special", "dp")),
        S(100001, "A"),
        S(2, "A", "COMPILATION_ERROR"),
        S(2, "A", "OK"),
    ]
    aggs = aggregate(subs, {})
    assert list(aggs) == [(2, "A")]
    assert aggs[(2, "A")].first_try_ok and aggs[(2, "A")].attempts == 1


def test_tag_stats_numbers():
    subs = [
        # dp: problem 1 solved first try (1500), problem 2 WA, TLE then OK (1700), problem 3 never solved
        S(1, "A", "OK", 1500, ("dp", "greedy")),
        S(2, "A", "WRONG_ANSWER", 1700, ("dp",)),
        S(2, "A", "TIME_LIMIT_EXCEEDED", 1700, ("dp",)),
        S(2, "A", "OK", 1700, ("dp",)),
        S(3, "A", "RUNTIME_ERROR", 1900, ("dp",)),
        S(3, "A", "MEMORY_LIMIT_EXCEEDED", 1900, ("dp",)),
        S(4, "A", "OK", None, ("greedy",)),  # unrated still counts for tags
    ]
    stats = {t.tag: t for t in tag_stats(aggregate(subs, {}).values())}
    dp = stats["dp"]
    assert (dp.attempted, dp.solved) == (3, 2)
    assert dp.solve_rate == pytest.approx(2 / 3)
    assert dp.first_try_rate == pytest.approx(1 / 3)
    assert dp.avg_wrong_before_ac == pytest.approx(1.0)  # (0 + 2) / 2
    assert dp.median_rating_solved == 1600 and dp.max_rating_solved == 1700
    assert (dp.verdicts.wa, dp.verdicts.tle, dp.verdicts.mle, dp.verdicts.re) == (1, 1, 1, 1)
    assert stats["greedy"].attempted == 2 and stats["greedy"].max_rating_solved == 1500


def test_band_stats_split_contest_and_practice():
    subs = [
        S(1, "A", "OK", 1500, ptype="CONTESTANT"),
        S(2, "A", "WRONG_ANSWER", 1550, ptype="CONTESTANT"),
        S(2, "A", "OK", 1550, ptype="PRACTICE"),  # upsolved
        S(3, "A", "OK", None),  # unrated: excluded
    ]
    bands = band_stats(aggregate(subs, {}).values())
    assert len(bands) == 1
    b = bands[0]
    assert (b.bucket, b.attempted, b.solved) == (1500, 2, 2)
    assert (b.contest_attempted, b.contest_solved) == (2, 1)
    assert (b.practice_attempted, b.practice_solved) == (1, 1)


# --- practice rating ----------------------------------------------------------------------------------


def test_percentile_matches_numpy_linear():
    assert percentile([1, 2, 3, 4], 75) == pytest.approx(3.25)
    assert percentile([800], 75) == 800


def test_practice_rating_uses_last_30_distinct_solves():
    old = [S(i, "A", "OK", 3000, t=i) for i in range(1, 11)]          # 10 old hard solves
    recent = [S(100 + i, "A", "OK", 1000 + 10 * i, t=1000 + i) for i in range(30)]
    dupes = [S(100, "A", "OK", 1000, t=5000)]                           # re-solve doesn't count twice
    aggs = aggregate(old + recent + dupes, {}).values()
    expected = percentile([1000 + 10 * i for i in range(30)], 75)
    assert practice_rating(aggs) == round(expected)


def test_practice_rating_none_without_rated_solves():
    assert practice_rating(aggregate([S(1, "A", "OK", None)], {}).values()) is None


def test_practice_timeline_one_point_per_day():
    day = 86_400
    subs = [S(i, "A", "OK", 1000 + 100 * i, t=day * 10 + i) for i in range(3)] + [S(9, "A", "OK", 2000, t=day * 11)]
    tl = practice_timeline(aggregate(subs, {}).values())
    assert len(tl) == 2 and tl[-1].window == 4


# --- ranks, level, target, progress -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "rating,name,target",
    [(None, "Newbie", 1200), (0, "Newbie", 1200), (1199, "Newbie", 1200), (1200, "Pupil", 1400),
     (1599, "Specialist", 1600), (1600, "Expert", 1900), (2099, "Candidate Master", 2100),
     (2299, "Master", 2300), (2399, "International Master", 2400), (2599, "Grandmaster", 2600),
     (2999, "International Grandmaster", 3000), (3500, "Legendary Grandmaster", None)],
)
def test_rank_and_default_target(rating, name, target):
    assert rank_for(rating).name == name
    assert default_target(rating) == target


def test_override_target_wins():
    assert choose_target(1500, 2100) == 2100 and choose_target(1500) == 1600
    assert next_rank(3000) is None


def test_level_sources():
    assert determine_level(1650, 5, 1400, 50).source == "contest"
    lvl = determine_level(None, 0, 1300, 12)
    assert (lvl.value, lvl.source) == (1300, "practice")
    lvl = determine_level(None, 0, 1300, 9)
    assert (lvl.value, lvl.source) == (1000, "default") and "1000" in lvl.note


def _hist(deltas):
    out, r = [], 1500
    for i, d in enumerate(deltas):
        out.append(RatingPoint(contest_id=i, contest_name=f"R{i}", time=i, old_rating=r,
                               new_rating=r + d, delta=d, rank=1))
        r += d
    return out


def test_contests_needed_estimate():
    hist = _hist([100] * 5 + [10] * 10)
    assert recent_average_delta(hist) == 10
    assert contests_needed(95, 10.0)[0] == 10
    n, note = contests_needed(95, -3.0)
    assert n is None and "not closing" in note
    assert contests_needed(95, 0.0)[0] is None
    assert contests_needed(0, 5.0)[0] == 0
    assert contests_needed(None, 5.0)[0] is None
    assert contests_needed(50, None)[0] is None


# --- weakness ------------------------------------------------------------------------------------------------


def test_importance_shares():
    counts = bucket_tag_counts([(1600, ["dp"]), (1700, ["dp", "math"]), (1700, ["math"]),
                                (2500, ["dp"]), (None, ["dp"]), (1600, ["*special", "dp"])])
    assert counts[(1700, TOTAL)] == 2
    imp = importance_in_band(counts, 1600, 1900)
    assert imp == {"dp": pytest.approx(2 / 3), "math": pytest.approx(2 / 3)}
    assert importance_in_band(counts, 3000, 3100) == {}


def test_weakness_formula_components():
    counts = {(1600, TOTAL): 10, (1600, "dp"): 5, (1600, "math"): 2}
    subs = [
        # dp in band: 1 solved, 3 attempted ; math in band: 1 attempted, 1 solved
        S(1, "A", "OK", 1600, ("dp",)),
        S(2, "A", "WRONG_ANSWER", 1600, ("dp",)),
        S(3, "A", "WRONG_ANSWER", 1600, ("dp",)),
        S(4, "A", "OK", 1600, ("math",)),
        S(5, "A", "OK", 800, ("dp",)),  # outside band: ignored for success/coverage
    ]
    aggs = list(aggregate(subs, {}).values())
    prior = band_prior(aggs, 1600, 1900)
    assert prior == pytest.approx(0.5)  # 2 of 4 band problems solved
    weak, used_prior = weakness_scores(aggs, counts, 1600, 1900)
    assert used_prior == prior
    by = {w.tag: w for w in weak}
    dp = by["dp"]
    success = (1 + 3 * 0.5) / (3 + 3)
    assert dp.importance == pytest.approx(0.5)
    assert dp.success == pytest.approx(success)
    assert dp.coverage == pytest.approx(0.1)
    assert dp.weakness == pytest.approx(0.5 * (1 - success) * (1 - 0.05))
    assert weak[0].tag == "dp"  # more important and less successful than math


def test_weakness_never_attempted_tag_uses_prior():
    counts = {(1600, TOTAL): 4, (1600, "graphs"): 4}
    aggs = list(aggregate([S(1, "A", "OK", 1600, ("dp",)), S(2, "A", "WRONG_ANSWER", 1600, ("dp",))], {}).values())
    weak, prior = weakness_scores(aggs, counts, 1600, 1900)
    g = weak[0]
    assert g.tag == "graphs" and g.success == pytest.approx(prior) and g.coverage == 0
    assert g.weakness == pytest.approx(1.0 * (1 - 0.5))


def test_weakness_top_n_limit():
    counts = {(1600, TOTAL): 20, **{(1600, f"t{i}"): 1 for i in range(12)}}
    weak, _ = weakness_scores([], counts, 1600, 1900)
    assert len(weak) == 8
