"""Resolve a parsed food item to nutrition numbers.

Order: local cache → USDA → Open Food Facts → LLM estimate (labelled).
Macros are always computed in code from per-100 g values × grams.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, timedelta
from typing import Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session

from calorie_agent.db.models import FoodCache, utcnow
from calorie_agent.nutrition.types import FoodMatch, Per100g, ResolvedItem, scale

log = logging.getLogger(__name__)


class FoodSource(Protocol):
    async def search(self, query: str) -> FoodMatch | None: ...


class ParsedItemLike(Protocol):
    name: str
    quantity: float
    unit: str
    grams: float
    search_term: str


Estimator = Callable[[str], Awaitable[Per100g]]

# DB hits are stable; LLM estimates expire so a transient API outage doesn't pin them forever.
ESTIMATE_TTL = timedelta(days=1)


def cache_key(term: str) -> str:
    return " ".join(term.lower().split())


class NutritionService:
    def __init__(self, engine: Engine, sources: list[FoodSource], estimator: Estimator) -> None:
        self.engine = engine
        self.sources = sources
        self.estimator = estimator

    def _cache_get(self, key: str) -> FoodMatch | None:
        with Session(self.engine) as s:
            row = s.get(FoodCache, key)
            if row is None:
                return None
            fetched = (
                row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=UTC)
            )
            if row.source == "llm_estimate" and utcnow() - fetched > ESTIMATE_TTL:
                return None
            per = Per100g(
                kcal=row.kcal_100g,
                protein_g=row.protein_100g,
                carbs_g=row.carbs_100g,
                fat_g=row.fat_100g,
            )
            return FoodMatch(f"cache:{row.source}", row.match_name, per)

    def _cache_put(self, key: str, m: FoodMatch) -> None:
        with Session(self.engine) as s:
            s.merge(
                FoodCache(
                    query_key=key,
                    source=m.source,
                    match_name=m.match_name,
                    kcal_100g=m.per100g.kcal,
                    protein_100g=m.per100g.protein_g,
                    carbs_100g=m.per100g.carbs_g,
                    fat_100g=m.per100g.fat_g,
                    fetched_at=utcnow(),
                )
            )
            s.commit()

    async def lookup(self, term: str) -> FoodMatch:
        key = cache_key(term)
        if (hit := self._cache_get(key)) is not None:
            return hit
        match: FoodMatch | None = None
        for src in self.sources:
            match = await src.search(term)
            if match is not None:
                break
        if match is None:
            log.info("No DB match for %r, using LLM estimate", term)
            match = FoodMatch("llm_estimate", term, await self.estimator(term))
        self._cache_put(key, match)
        return match

    async def resolve(self, item: ParsedItemLike) -> ResolvedItem:
        m = await self.lookup(item.search_term or item.name)
        kcal, p, c, f = scale(m.per100g, item.grams)
        return ResolvedItem(
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            grams=item.grams,
            kcal=kcal,
            protein_g=p,
            carbs_g=c,
            fat_g=f,
            source=m.source,
            match_name=m.match_name,
        )
