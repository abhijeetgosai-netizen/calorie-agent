"""Numbers the user states themselves win over every lookup."""

from datetime import date

import pytest

from calorie_agent.agent.schemas import MAX_STATED_KCAL, ParsedFood, ParsedMeal, validate_meal
from calorie_agent.db.models import User
from calorie_agent.db.repo import Repository, Totals
from calorie_agent.nutrition.history import HistorySource
from calorie_agent.nutrition.service import NutritionService
from calorie_agent.reports import item_line, logged
from tests.fakes import EGG, FakeLLM, FakeSource

DAY = date(2026, 1, 15)


def _food(**kw) -> ParsedFood:
    base = dict(name="egg", quantity=2, unit="piece", grams=100, search_term="egg whole boiled")
    return ParsedFood(**{**base, **kw})


class ExplodingSource:
    """Any call means the stated-value short-circuit failed."""

    async def search(self, query: str):
        raise AssertionError(f"database was queried for {query!r}")


async def _boom(term: str):
    raise AssertionError(f"LLM estimate was called for {term!r}")


def _svc(engine, **kw) -> NutritionService:
    return NutritionService(engine, [ExplodingSource()], _boom, **kw)


# ---- the short-circuit ------------------------------------------------------
async def test_stated_values_skip_every_source(engine):
    got = await _svc(engine).resolve(_food(kcal=200, protein_g=20, carbs_g=15, fat_g=7, fiber_g=3))
    assert (got.kcal, got.protein_g, got.carbs_g, got.fat_g, got.fiber_g) == (
        200.0,
        20.0,
        15.0,
        7.0,
        3.0,
    )
    assert got.source == "user"


async def test_stated_values_are_totals_and_are_never_scaled_by_grams(engine):
    """ "a 250 g bowl, 400 calories" means 400 kcal, not 400 per 100 g."""
    got = await _svc(engine).resolve(_food(name="pasta", grams=250, kcal=400))
    assert got.kcal == 400.0, "stated figures are the total for the portion"


async def test_partial_statement_leaves_the_rest_at_zero(engine):
    """Calories only: macros stay 0 rather than being mixed in from a database."""
    got = await _svc(engine).resolve(_food(name="bar", kcal=200))
    assert got.kcal == 200.0
    assert (got.protein_g, got.carbs_g, got.fat_g, got.fiber_g) == (0.0, 0.0, 0.0, 0.0)


async def test_a_single_stated_macro_is_enough_to_short_circuit(engine):
    got = await _svc(engine).resolve(_food(protein_g=12))
    assert got.source == "user" and got.protein_g == 12.0 and got.kcal == 0.0


async def test_nothing_stated_falls_through_to_the_databases(engine):
    svc = NutritionService(engine, [FakeSource({"egg": EGG})], FakeLLM().estimate)
    got = await svc.resolve(_food())
    assert got.source == "usda" and got.kcal == 155.0


async def test_stated_values_beat_the_users_own_history(repo: Repository, engine):
    """History is good, but an explicit number in this message is better."""
    uid = repo.get_or_create_user(9001).id
    assert uid is not None
    from calorie_agent.nutrition.types import ResolvedItem

    repo.add_entry(
        uid,
        "bar",
        [ResolvedItem("bar", 1, "piece", 100.0, 500.0, 5.0, 60.0, 25.0, "usda")],
        DAY,
    )
    svc = _svc(engine, history=HistorySource(repo, 0.5))
    got = await svc.resolve(_food(name="bar", search_term="bar", kcal=200), user_id=uid)
    assert got.kcal == 200.0, "the stated figure must win over the history hit"


async def test_stated_values_never_enter_the_shared_cache(engine):
    """One user's "my bar is 200 kcal" must not become everyone's answer for "bar"."""
    svc = NutritionService(engine, [FakeSource({"egg": EGG})], FakeLLM().estimate)
    await svc.resolve(_food(name="egg", kcal=999))
    # a later lookup for the same term must hit the database, not the stated figure
    got = await svc.resolve(_food(name="egg"))
    assert got.kcal == 155.0 and got.source == "usda"


# ---- validation -------------------------------------------------------------
@pytest.mark.parametrize("bad", [-1, MAX_STATED_KCAL + 1])
def test_impossible_stated_calories_are_discarded(bad):
    meal = validate_meal(ParsedMeal(items=[_food(kcal=bad)]))
    assert meal.items[0].kcal is None, "out-of-range values fall back to a normal lookup"


def test_sane_stated_calories_survive_validation():
    meal = validate_meal(ParsedMeal(items=[_food(kcal=200, protein_g=20)]))
    assert (meal.items[0].kcal, meal.items[0].protein_g) == (200.0, 20.0)


def test_has_stated_nutrition_flag():
    assert not _food().has_stated_nutrition
    assert _food(fiber_g=3).has_stated_nutrition


# ---- display ----------------------------------------------------------------
async def test_stated_items_are_marked_and_footnoted(engine):
    got = await _svc(engine).resolve(_food(name="bar", kcal=200))
    assert "*200 kcal" in item_line(got)
    out = logged([got], Totals(kcal=200, entries=1), User(telegram_id=1))
    assert "your own figures" in out


async def test_stated_items_are_not_labelled_as_estimates(engine):
    got = await _svc(engine).resolve(_food(kcal=200))
    assert not got.is_estimate and got.is_stated
