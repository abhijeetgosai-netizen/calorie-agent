"""Dietary fiber, end to end: parsing from both databases, storage, totals, display."""

from datetime import date

import httpx
import pytest

from calorie_agent.db.models import User
from calorie_agent.db.repo import Repository, Totals
from calorie_agent.nutrition.history import HistorySource
from calorie_agent.nutrition.off import OpenFoodFactsClient
from calorie_agent.nutrition.types import Per100g, ResolvedItem, scale
from calorie_agent.nutrition.usda import USDAClient
from calorie_agent.reports import day_summary, item_line

DAY = date(2026, 1, 15)

OATS = Per100g(kcal=389, protein_g=16.9, carbs_g=66.3, fat_g=6.9, fiber_g=10.6)


def _item(**kw) -> ResolvedItem:
    base = dict(
        name="oats",
        quantity=1,
        unit="bowl",
        grams=100.0,
        kcal=389.0,
        protein_g=16.9,
        carbs_g=66.3,
        fat_g=6.9,
        fiber_g=10.6,
        source="usda",
    )
    return ResolvedItem(**{**base, **kw})


# ---- the model --------------------------------------------------------------
def test_fiber_defaults_to_zero_so_old_callers_still_work():
    assert Per100g(kcal=100, protein_g=1, carbs_g=2, fat_g=3).fiber_g == 0.0


def test_fiber_is_range_validated_like_the_other_macros():
    with pytest.raises(ValueError):
        Per100g(kcal=100, protein_g=1, carbs_g=2, fat_g=3, fiber_g=101)
    with pytest.raises(ValueError):
        Per100g(kcal=100, protein_g=1, carbs_g=2, fat_g=3, fiber_g=-1)


def test_scale_computes_fiber_in_code():
    kcal, p, c, f, fib = scale(OATS, 40)
    assert (kcal, fib) == (155.6, 4.2)
    assert (p, c, f) == (6.8, 26.5, 2.8)


# ---- parsing from the real API shapes --------------------------------------
async def test_usda_reads_nutrient_1079():
    payload = {
        "foods": [
            {
                "description": "Oats, whole grain, rolled",
                "foodNutrients": [
                    {"nutrientId": 1008, "value": 389, "unitName": "KCAL"},
                    {"nutrientId": 1003, "value": 16.9, "unitName": "G"},
                    {"nutrientId": 1004, "value": 6.9, "unitName": "G"},
                    {"nutrientId": 1005, "value": 66.3, "unitName": "G"},
                    {"nutrientId": 1079, "value": 10.6, "unitName": "G"},
                ],
            }
        ]
    }
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as http:
        m = await USDAClient("k", http, 0.5).search("oats")
    assert m is not None and m.per100g.fiber_g == 10.6


async def test_usda_food_without_fiber_reports_zero_not_an_error():
    payload = {
        "foods": [
            {
                "description": "Egg, whole, cooked",
                "foodNutrients": [{"nutrientId": 1008, "value": 155, "unitName": "KCAL"}],
            }
        ]
    }
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as http:
        m = await USDAClient("k", http, 0.5).search("egg")
    assert m is not None and m.per100g.fiber_g == 0.0


async def test_off_reads_fiber_100g():
    payload = {
        "products": [
            {
                "product_name": "Wholemeal bread",
                "nutriments": {
                    "energy-kcal_100g": 247,
                    "proteins_100g": 13,
                    "carbohydrates_100g": 41,
                    "fat_100g": 3.4,
                    "fiber_100g": 7.0,
                },
            }
        ]
    }
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as http:
        m = await OpenFoodFactsClient(http, 0.5).search("wholemeal bread")
    assert m is not None and m.per100g.fiber_g == 7.0


# ---- storage and aggregation ------------------------------------------------
def test_fiber_is_stored_and_summed_into_day_totals(repo: Repository):
    uid = repo.get_or_create_user(7001).id
    assert uid is not None
    repo.add_entry(uid, "oats", [_item(), _item(name="apple", fiber_g=2.4)], DAY)
    assert repo.day_totals(uid, DAY).fiber_g == pytest.approx(13.0)


def test_fiber_survives_a_round_trip_through_history(repo: Repository):
    uid = repo.get_or_create_user(7002).id
    assert uid is not None
    # a 50 g portion: every value is half the per-100 g figure
    repo.add_entry(
        uid,
        "oats",
        [_item(grams=50.0, kcal=194.5, protein_g=8.45, carbs_g=33.15, fat_g=3.45, fiber_g=5.3)],
        DAY,
    )
    (food,) = repo.recent_foods(uid)
    assert food.per100g.fiber_g == pytest.approx(10.6)  # 5.3 / 50 * 100


async def test_history_hit_carries_fiber(repo: Repository):
    uid = repo.get_or_create_user(7003).id
    assert uid is not None
    repo.add_entry(uid, "oats", [_item()], DAY)
    m = await HistorySource(repo, 0.5).search("oats", "oats rolled", uid)
    assert m is not None and m.per100g.fiber_g == pytest.approx(10.6)


# ---- display ----------------------------------------------------------------
def test_item_line_shows_fiber_when_present():
    assert "Fib 10.6g" in item_line(_item())


def test_item_line_shows_fiber_even_when_zero():
    assert "Fib 0.0g" in item_line(_item(name="egg", fiber_g=0.0))


def test_day_summary_always_shows_fiber():
    totals = Totals(kcal=1800, protein_g=90, carbs_g=200, fat_g=60, fiber_g=24, entries=3)
    assert "Fiber 24g" in day_summary(totals, User(telegram_id=1))
