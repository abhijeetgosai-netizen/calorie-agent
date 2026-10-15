"""Plain data types shared by the nutrition layer, the agent and the DB."""

from dataclasses import dataclass

from pydantic import BaseModel, Field


class Per100g(BaseModel):
    """Nutrition per 100 g of a food. Validation rejects impossible values."""

    kcal: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)
    # Defaults to 0 so a source that doesn't report fiber stays valid. Fiber is a
    # subset of carbohydrate, so it is never added into the calorie total.
    fiber_g: float = Field(default=0.0, ge=0, le=100)


@dataclass(frozen=True)
class FoodMatch:
    source: str  # "usda" | "off" | "llm_estimate"
    match_name: str
    per100g: Per100g


@dataclass(frozen=True)
class LoggedFood:
    """A food this user logged before, with per-100 g recovered from the stored row."""

    name: str
    match_name: str | None
    source: str
    per100g: Per100g


@dataclass(frozen=True)
class ResolvedItem:
    name: str
    quantity: float
    unit: str
    grams: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    source: str
    match_name: str | None = None
    # Trails the required fields for dataclass ordering; 0.0 means "not reported",
    # which is also what rows logged before fiber tracking existed will read.
    fiber_g: float = 0.0

    @property
    def is_estimate(self) -> bool:
        return self.source.endswith("llm_estimate")

    @property
    def is_stated(self) -> bool:
        """Numbers the user gave us, not looked up. Also true when replayed from history."""
        return self.source.endswith("user")


def scale(per100g: Per100g, grams: float) -> tuple[float, float, float, float, float]:
    """Deterministic macro calculation. The LLM never does this.

    Returns (kcal, protein_g, carbs_g, fat_g, fiber_g).
    """
    f = grams / 100.0
    return (
        round(per100g.kcal * f, 1),
        round(per100g.protein_g * f, 1),
        round(per100g.carbs_g * f, 1),
        round(per100g.fat_g * f, 1),
        round(per100g.fiber_g * f, 1),
    )
