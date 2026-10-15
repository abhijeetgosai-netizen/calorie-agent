"""Nutrition taken from the user's own previously logged foods.

Checked after the shared cache but before the public databases: if you logged "poha"
last week, the numbers that resolved then are reused. Two reasons this beats going back
out to USDA:

* **Consistency.** Foods that no database carries (most regional dishes) are otherwise
  re-estimated by the LLM every time, so the same breakfast scores differently week to
  week and trends become meaningless.
* **Cost.** A repeat meal resolves with no network call and no tokens.

Results are per-user and are deliberately never written to the shared `food_cache`.
"""

import logging

from calorie_agent.db.repo import Repository
from calorie_agent.nutrition.matching import best_match
from calorie_agent.nutrition.types import FoodMatch

log = logging.getLogger(__name__)


def _base_source(source: str) -> str:
    """Strip any provenance prefix so history-of-history never nests.

    "usda" -> "usda", "cache:usda" -> "usda", "history:llm_estimate" -> "llm_estimate"
    """
    return source.rsplit(":", 1)[-1]


class HistorySource:
    """Looks a food up in what this user has already logged."""

    def __init__(self, repo: Repository, threshold: float) -> None:
        self.repo = repo
        self.threshold = threshold

    async def search(self, name: str, term: str, user_id: int) -> FoodMatch | None:
        foods = self.repo.recent_foods(user_id)
        if not foods:
            return None
        candidates = [f.name for f in foods]
        # Match on what the user called it first: history stores colloquial names
        # ("poha"), while `term` is a generic database phrase ("rice flakes dry").
        for query in (name, term):
            if not query:
                continue
            idx = best_match(query, candidates, self.threshold)
            if idx is None:
                continue
            f = foods[idx]
            source = f"history:{_base_source(f.source)}"
            log.info("History hit for %r -> %r (%s)", query, f.name, source)
            return FoodMatch(source, f.match_name or f.name, f.per100g)
        return None
