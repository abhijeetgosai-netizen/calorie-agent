"""Open Food Facts search client — good for packaged/branded foods."""

import logging

import httpx

from calorie_agent.nutrition.matching import best_match
from calorie_agent.nutrition.types import FoodMatch, Per100g

log = logging.getLogger(__name__)

URL = "https://world.openfoodfacts.org/cgi/search.pl"
HEADERS = {"User-Agent": "calorie-agent/0.1 (open-source; github.com/abhijeetgosai-netizen/calorie-agent)"}


def _per100(product: dict) -> Per100g | None:
    n = product.get("nutriments", {})
    kcal = n.get("energy-kcal_100g")
    if kcal is None:
        return None
    try:
        return Per100g(
            kcal=float(kcal),
            protein_g=float(n.get("proteins_100g", 0) or 0),
            carbs_g=float(n.get("carbohydrates_100g", 0) or 0),
            fat_g=float(n.get("fat_100g", 0) or 0),
        )
    except (TypeError, ValueError):
        return None


class OpenFoodFactsClient:
    def __init__(self, client: httpx.AsyncClient, threshold: float) -> None:
        self.client, self.threshold = client, threshold

    async def search(self, query: str) -> FoodMatch | None:
        try:
            r = await self.client.get(
                URL,
                params={"search_terms": query, "json": 1, "page_size": 10, "search_simple": 1},
                headers=HEADERS,
                timeout=10,
            )
            r.raise_for_status()
            products = r.json().get("products", [])
        except (httpx.HTTPError, ValueError) as e:
            log.warning("OFF lookup failed for %r: %s", query, e)
            return None
        candidates = [(p, _per100(p)) for p in products]
        candidates = [(p, n) for p, n in candidates if n is not None]
        names = [p.get("product_name", "") for p, _ in candidates]
        idx = best_match(query, names, self.threshold)
        if idx is None:
            return None
        product, per100 = candidates[idx]
        assert per100 is not None
        return FoodMatch("off", names[idx] or query, per100)
