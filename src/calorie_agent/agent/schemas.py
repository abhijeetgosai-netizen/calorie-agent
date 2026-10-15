"""Structured outputs the LLM must return. Kept constraint-free so every provider's
structured-output mode accepts them; validation happens in code (see `validate_meal`)."""

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal[
    "log_food", "query_today", "weekly_report", "undo", "set_goal", "help", "off_topic"
]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]


class RouterOutput(BaseModel):
    """Classify a message sent to a calorie-tracking bot."""

    intent: Intent = Field(description="The single best intent for the message.")
    kcal_goal: int | None = Field(
        default=None, description="Daily calorie goal if the user states one, else null."
    )
    protein_goal_g: int | None = Field(
        default=None, description="Daily protein goal in grams if stated, else null."
    )
    timezone: str | None = Field(
        default=None,
        description="IANA timezone (e.g. 'Asia/Kolkata') if the user states where they live "
        "or their timezone, else null.",
    )


class ParsedFood(BaseModel):
    name: str = Field(description="Short human-readable food name as the user said it.")
    quantity: float = Field(description="Number of units eaten, e.g. 2 for '2 eggs'.")
    unit: str = Field(description="Unit as stated: piece, slice, bowl, cup, g, ml, tbsp, serving…")
    grams: float = Field(description="Your best estimate of the total edible weight in grams.")
    search_term: str = Field(
        description="Generic English nutrition-database search term, most specific first, "
        "e.g. 'egg whole boiled', 'rice white cooked', 'chapati roti'. No brand unless given."
    )


class ParsedMeal(BaseModel):
    """Foods extracted from one message."""

    items: list[ParsedFood] = Field(default_factory=list)
    unclear_items: list[str] = Field(
        default_factory=list,
        description="Names of foods whose amount is missing AND varies so much that a "
        "default portion would be misleading. Leave empty if clarification is not allowed.",
    )


MAX_ITEMS = 15
MAX_GRAMS = 3000.0


def validate_meal(meal: ParsedMeal) -> ParsedMeal:
    """Drop impossible items and cap list length. Deterministic guard on LLM output."""
    items = [
        it for it in meal.items if it.name.strip() and 0 < it.grams <= MAX_GRAMS and it.quantity > 0
    ][:MAX_ITEMS]
    names = {it.name for it in items}
    unclear = [u for u in meal.unclear_items if u in names]
    return ParsedMeal(items=items, unclear_items=unclear)
