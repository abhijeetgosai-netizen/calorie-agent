"""Resolve a parsed food item to nutrition numbers.

Order: values the user stated → local cache → the user's own history → USDA →
Open Food Facts → LLM estimate.
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


class HistoryLookup(Protocol):
    """Per-user source; takes the colloquial name as well as the database term."""

    async def search(self, name: str, term: str, user_id: int) -> FoodMatch | None: ...


class ParsedItemLike(Protocol):
    name: str
    quantity: float
    unit: str
    grams: float
    search_term: str
    # Set only when the user stated the number themselves; see `_stated`.
    kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None


Estimator = Callable[[str], Awaitable[Per100g]]

# DB hits are stable; LLM estimates expire so a transient API outage doesn't pin them forever.
ESTIMATE_TTL = timedelta(days=1)


def cache_key(term: str) -> str:
    return " ".join(term.lower().split())


class NutritionService:
    def __init__(
        self,
        engine: Engine,
        sources: list[FoodSource],
        estimator: Estimator,
        history: HistoryLookup | None = None,
    ) -> None:
        self.engine = engine
        self.sources = sources
        self.estimator = estimator
        self.history = history

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
                fiber_g=row.fiber_100g,
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
                    fiber_100g=m.per100g.fiber_g,
                    fetched_at=utcnow(),
                )
            )
            s.commit()

    async def lookup(
        self, term: str, user_id: int | None = None, name: str | None = None
    ) -> FoodMatch:
        key = cache_key(term)
        if (hit := self._cache_get(key)) is not None:
            return hit
        if self.history is not None and user_id is not None:
            hist = await self.history.search(name or term, term, user_id)
            if hist is not None:
                # Never cached: `food_cache` is shared by all users, and these values
                # carry one user's portion history. Writing them would leak across users.
                return hist
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

    @staticmethod
    def _stated(item: ParsedItemLike) -> ResolvedItem | None:
        """Use the user's own numbers verbatim, skipping every lookup.

        Stated values are totals for the portion eaten, so they are NOT scaled by grams,
        and they are never written to the shared cache — one person saying their bar is
        200 kcal must not become everyone's answer for "bar". Nutrients the user did not
        mention stay 0 rather than being filled in from a database, because mixing a
        stated calorie count with looked-up macros would silently describe a different food.
        """
        if not any(
            getattr(item, f, None) is not None
            for f in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")
        ):
            return None
        return ResolvedItem(
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            grams=item.grams,
            kcal=getattr(item, "kcal", None) or 0.0,
            protein_g=getattr(item, "protein_g", None) or 0.0,
            carbs_g=getattr(item, "carbs_g", None) or 0.0,
            fat_g=getattr(item, "fat_g", None) or 0.0,
            fiber_g=getattr(item, "fiber_g", None) or 0.0,
            source="user",
            match_name=None,
        )

    async def resolve(self, item: ParsedItemLike, user_id: int | None = None) -> ResolvedItem:
        if (stated := self._stated(item)) is not None:
            log.info("Using stated nutrition for %r (%s kcal)", item.name, stated.kcal)
            return stated
        m = await self.lookup(item.search_term or item.name, user_id=user_id, name=item.name)
        kcal, p, c, f, fib = scale(m.per100g, item.grams)
        return ResolvedItem(
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            grams=item.grams,
            kcal=kcal,
            protein_g=p,
            carbs_g=c,
            fat_g=f,
            fiber_g=fib,
            source=m.source,
            match_name=m.match_name,
        )
