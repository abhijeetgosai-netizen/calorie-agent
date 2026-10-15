"""USDA FoodData Central search client (free; DEMO_KEY works for light use)."""

import logging

import httpx

from calorie_agent.nutrition.matching import best_match
from calorie_agent.nutrition.types import FoodMatch, Per100g

log = logging.getLogger(__name__)

URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
# Foundation & SR Legacy report nutrients per 100 g, which is what we want.
DATA_TYPES = "Foundation,SR Legacy,Survey (FNDDS)"
ENERGY_IDS = (1008, 2047, 2048)  # kcal, Atwater general, Atwater specific
PROTEIN, FAT, CARBS = 1003, 1004, 1005


def _nutrients(food: dict) -> Per100g | None:
    # Keyed by (nutrient id, unit) so a kJ energy row can never shadow the kcal row.
    vals: dict[tuple[int, str], float] = {}
    for n in food.get("foodNutrients", []):
        nid, val = n.get("nutrientId"), n.get("value")
        if nid is not None and val is not None:
            vals.setdefault((int(nid), str(n.get("unitName", "")).upper()), float(val))
    kcal = next((vals[(i, "KCAL")] for i in ENERGY_IDS if (i, "KCAL") in vals), None)
    if kcal is None:
        return None
    try:
        return Per100g(
            kcal=kcal,
            protein_g=vals.get((PROTEIN, "G"), 0.0),
            carbs_g=vals.get((CARBS, "G"), 0.0),
            fat_g=vals.get((FAT, "G"), 0.0),
        )
    except ValueError:
        return None


class USDAClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient, threshold: float) -> None:
        self.api_key, self.client, self.threshold = api_key, client, threshold

    async def search(self, query: str) -> FoodMatch | None:
        try:
            r = await self.client.get(
                URL,
                params={
                    "query": query,
                    "dataType": DATA_TYPES,
                    "pageSize": 10,
                    "api_key": self.api_key,
                },
                timeout=10,
            )
            r.raise_for_status()
            foods = r.json().get("foods", [])
        except (httpx.HTTPError, ValueError) as e:
            log.warning("USDA lookup failed for %r: %s", query, e)
            return None
        candidates = [(f, _nutrients(f)) for f in foods]
        candidates = [(f, n) for f, n in candidates if n is not None]
        idx = best_match(query, [f.get("description", "") for f, _ in candidates], self.threshold)
        if idx is None:
            return None
        food, per100 = candidates[idx]
        assert per100 is not None
        return FoodMatch("usda", food.get("description", query), per100)
