"""Plain data types shared by the nutrition layer, the agent and the DB."""

from dataclasses import dataclass

from pydantic import BaseModel, Field


class Per100g(BaseModel):
    """Nutrition per 100 g of a food. Validation rejects impossible values."""

    kcal: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)


@dataclass(frozen=True)
class FoodMatch:
    source: str  # "usda" | "off" | "llm_estimate"
    match_name: str
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

    @property
    def is_estimate(self) -> bool:
        return self.source.endswith("llm_estimate")


def scale(per100g: Per100g, grams: float) -> tuple[float, float, float, float]:
    """Deterministic macro calculation. The LLM never does this."""
    f = grams / 100.0
    return (
        round(per100g.kcal * f, 1),
        round(per100g.protein_g * f, 1),
        round(per100g.carbs_g * f, 1),
        round(per100g.fat_g * f, 1),
    )
