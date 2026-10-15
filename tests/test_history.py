"""Personal food history as a nutrition source. No network, no LLM."""

from datetime import date

import pytest

from calorie_agent.agent.schemas import ParsedFood
from calorie_agent.db.repo import Repository
from calorie_agent.nutrition.history import HistorySource, _base_source
from calorie_agent.nutrition.service import NutritionService
from calorie_agent.nutrition.types import ResolvedItem
from tests.fakes import EGG, FakeLLM, FakeSource

DAY = date(2026, 1, 15)


def _item(name="poha", grams=180.0, kcal=234.0, source="llm_estimate", **kw) -> ResolvedItem:
    return ResolvedItem(
        name=name,
        quantity=kw.get("quantity", 1),
        unit=kw.get("unit", "bowl"),
        grams=grams,
        kcal=kcal,
        protein_g=kw.get("protein_g", 7.2),
        carbs_g=kw.get("carbs_g", 45.0),
        fat_g=kw.get("fat_g", 3.6),
        source=source,
        match_name=kw.get("match_name"),
    )


@pytest.fixture
def user(repo):
    u = repo.get_or_create_user(1001)
    assert u.id is not None
    return u.id


# ---- recovering per-100 g from a stored row --------------------------------
def test_recent_foods_recovers_per_100g(repo: Repository, user):
    repo.add_entry(user, "poha", [_item(grams=180.0, kcal=234.0)], DAY)
    (food,) = repo.recent_foods(user)
    assert food.name == "poha"
    assert food.per100g.kcal == pytest.approx(130.0)  # 234 / 180 * 100
    assert food.per100g.protein_g == pytest.approx(4.0)


def test_most_recent_wins_and_duplicates_collapse(repo: Repository, user):
    repo.add_entry(user, "poha", [_item(grams=100.0, kcal=100.0)], DAY)
    repo.add_entry(user, "poha again", [_item(grams=100.0, kcal=160.0)], DAY)
    foods = repo.recent_foods(user)
    assert len(foods) == 1, "the same food must appear once"
    assert foods[0].per100g.kcal == pytest.approx(160.0), "newest entry wins"


def test_impossible_rows_are_skipped(repo: Repository, user):
    # 50 g row claiming 900 kcal recovers to 1800 kcal/100 g, which Per100g rejects.
    repo.add_entry(user, "bad", [_item(name="bad", grams=50.0, kcal=900.0)], DAY)
    assert repo.recent_foods(user) == []


def test_zero_gram_rows_are_excluded(repo: Repository, user):
    repo.add_entry(user, "ghost", [_item(name="ghost", grams=0.0, kcal=0.0)], DAY)
    assert repo.recent_foods(user) == []


# ---- matching ---------------------------------------------------------------
async def test_matches_on_colloquial_name_not_just_search_term(repo: Repository, user):
    repo.add_entry(user, "poha", [_item()], DAY)
    hist = HistorySource(repo, threshold=0.5)
    # The generic term would never match; the name the user used must.
    m = await hist.search(name="poha", term="rice flakes dry", user_id=user)
    assert m is not None and m.per100g.kcal == pytest.approx(130.0)


async def test_unknown_food_returns_none(repo: Repository, user):
    repo.add_entry(user, "poha", [_item()], DAY)
    hist = HistorySource(repo, threshold=0.5)
    assert await hist.search(name="sushi", term="sushi salmon", user_id=user) is None


async def test_empty_history_returns_none(repo: Repository, user):
    assert await HistorySource(repo, 0.5).search("poha", "poha", user) is None


# ---- provenance -------------------------------------------------------------
@pytest.mark.parametrize(
    ("stored", "expected"),
    [("usda", "usda"), ("cache:usda", "usda"), ("history:llm_estimate", "llm_estimate")],
)
def test_source_prefixes_never_nest(stored, expected):
    assert _base_source(stored) == expected


async def test_estimate_provenance_survives_so_the_tilde_still_shows(repo: Repository, user):
    repo.add_entry(user, "poha", [_item(source="llm_estimate")], DAY)
    hist = HistorySource(repo, 0.5)
    m = await hist.search("poha", "poha", user)
    assert m is not None
    assert m.source == "history:llm_estimate"
    # the `~` marker in the reply keys off is_estimate, which must survive the prefix
    assert _item(source=m.source).is_estimate


# ---- integration with the resolution chain ----------------------------------
async def test_history_is_preferred_over_the_databases(repo: Repository, engine, user):
    repo.add_entry(user, "egg", [_item(name="egg", grams=100.0, kcal=99.0)], DAY)
    source = FakeSource({"egg": EGG})
    svc = NutritionService(engine, [source], FakeLLM().estimate, history=HistorySource(repo, 0.5))

    got = await svc.resolve(
        ParsedFood(name="egg", quantity=1, unit="piece", grams=100, search_term="egg whole boiled"),
        user_id=user,
    )
    assert got.kcal == pytest.approx(99.0), "should reuse the logged value, not USDA's 155"
    assert source.calls == 0, "history hit must short-circuit the network sources"


async def test_history_never_leaks_between_users(repo: Repository, engine, user):
    """A history hit must not be written to the shared food_cache."""
    other = repo.get_or_create_user(2002).id
    assert other is not None
    repo.add_entry(user, "poha", [_item()], DAY)
    svc = NutritionService(engine, [], FakeLLM().estimate, history=HistorySource(repo, 0.5))
    parsed = ParsedFood(name="poha", quantity=1, unit="bowl", grams=180, search_term="poha")

    mine = await svc.resolve(parsed, user_id=user)
    theirs = await svc.resolve(parsed, user_id=other)

    assert mine.source == "history:llm_estimate"
    assert theirs.source == "llm_estimate", "user B must not inherit user A's history"


async def test_no_user_id_behaves_exactly_as_before(repo: Repository, engine, user):
    repo.add_entry(user, "egg", [_item(name="egg", grams=100.0, kcal=99.0)], DAY)
    source = FakeSource({"egg": EGG})
    svc = NutritionService(engine, [source], FakeLLM().estimate, history=HistorySource(repo, 0.5))
    got = await svc.resolve(
        ParsedFood(name="egg", quantity=1, unit="piece", grams=100, search_term="egg whole boiled"),
        # no user_id: callers that don't pass one must skip history entirely
    )
    assert got.kcal == pytest.approx(155.0)
    assert source.calls == 1
