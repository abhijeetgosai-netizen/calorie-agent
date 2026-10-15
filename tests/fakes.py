"""Deterministic stand-ins for the LLM and food databases."""

from calorie_agent.agent.schemas import ParsedFood, ParsedMeal, RouterOutput
from calorie_agent.nutrition.types import FoodMatch, Per100g

EGG = Per100g(kcal=155, protein_g=12.6, carbs_g=1.1, fat_g=10.6)
RICE = Per100g(kcal=130, protein_g=2.7, carbs_g=28.0, fat_g=0.3)


class FakeLLM:
    """Keyword-based fake; records calls so tests can assert LLM usage."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def classify(self, text: str) -> RouterOutput:
        self.calls.append("classify")
        t = text.lower()
        if "goal" in t:
            return RouterOutput(intent="set_goal", kcal_goal=2000, protein_goal_g=120)
        if "today" in t:
            return RouterOutput(intent="query_today")
        if "week" in t:
            return RouterOutput(intent="weekly_report")
        if "undo" in t:
            return RouterOutput(intent="undo")
        if any(w in t for w in ("egg", "rice", "zorb", "nothing")):
            return RouterOutput(intent="log_food")
        return RouterOutput(intent="off_topic")

    async def parse_meal(self, text: str, allow_clarification: bool) -> ParsedMeal:
        self.calls.append(f"parse(clarify={allow_clarification})")
        t = text.lower()
        items: list[ParsedFood] = []
        unclear: list[str] = []
        if "egg" in t:
            items.append(
                ParsedFood(
                    name="egg", quantity=2, unit="piece", grams=100, search_term="egg whole boiled"
                )
            )
        if "rice" in t:
            grams = 320 if "2 cups" in t else 160
            items.append(
                ParsedFood(
                    name="rice",
                    quantity=1,
                    unit="serving",
                    grams=grams,
                    search_term="rice white cooked",
                )
            )
            if allow_clarification and "cup" not in t:
                unclear.append("rice")
        if "zorb" in t:
            items.append(
                ParsedFood(
                    name="zorbcake", quantity=1, unit="piece", grams=50, search_term="zorbcake"
                )
            )
        return ParsedMeal(items=items, unclear_items=unclear)

    async def estimate(self, food: str) -> Per100g:
        self.calls.append(f"estimate({food})")
        return Per100g(kcal=400, protein_g=5, carbs_g=50, fat_g=20)


class FakeSource:
    def __init__(self, table: dict[str, Per100g]) -> None:
        self.table, self.calls = table, 0

    async def search(self, query: str) -> FoodMatch | None:
        self.calls += 1
        for k, v in self.table.items():
            if k in query:
                return FoodMatch("usda", k, v)
        return None
