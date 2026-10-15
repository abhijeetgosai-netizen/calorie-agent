"""End-to-end calorie accuracy: real LLM parse → real USDA/OFF lookup → code math.

Uses explicit quantities so the score reflects lookup + arithmetic, not portion guessing.
Needs network access to api.nal.usda.gov (set USDA_API_KEY to avoid DEMO_KEY limits).
"""

import asyncio

import httpx
import pytest

from calorie_agent.config import get_settings
from calorie_agent.db.session import make_engine, migrate
from calorie_agent.nutrition.off import OpenFoodFactsClient
from calorie_agent.nutrition.service import NutritionService
from calorie_agent.nutrition.usda import USDAClient
from evals.conftest import CONCURRENCY, THRESHOLDS, load, save_result
from evals.metrics import ape, mape

pytestmark = pytest.mark.eval


async def test_calorie_accuracy(real_llm, tmp_path):
    s = get_settings()
    url = f"sqlite:///{tmp_path}/eval.db"
    migrate(url)
    async with httpx.AsyncClient() as http:
        nutrition = NutritionService(
            make_engine(url),
            [
                USDAClient(s.usda_api_key, http, s.match_threshold),
                OpenFoodFactsClient(http, s.match_threshold),
            ],
            real_llm.estimate,
        )
        sem = asyncio.Semaphore(CONCURRENCY)

        async def one(text: str):
            async with sem:
                meal = await real_llm.parse_meal(text, allow_clarification=False)
                return [await nutrition.resolve(i) for i in meal.items]

        rows = load("calories")
        results = await asyncio.gather(*(one(r["text"]) for r in rows))

    pairs, details, estimates = [], [], 0
    for row, items in zip(rows, results, strict=True):
        kcal = sum(i.kcal for i in items)
        estimates += sum(i.is_estimate for i in items)
        pairs.append((kcal, row["kcal"]))
        if ape(kcal, row["kcal"]) > THRESHOLDS["calorie_mape"]:
            details.append(
                {
                    "text": row["text"],
                    "expected": row["kcal"],
                    "got": kcal,
                    "items": [
                        {
                            "name": i.name,
                            "grams": i.grams,
                            "kcal": i.kcal,
                            "source": i.source,
                            "match": i.match_name,
                        }
                        for i in items
                    ],
                }
            )
    score = mape(pairs)
    path = save_result("calories", {"mape": score, "llm_estimates": estimates}, details)
    assert score <= THRESHOLDS["calorie_mape"], f"kcal MAPE {score:.1%}; see {path}"
