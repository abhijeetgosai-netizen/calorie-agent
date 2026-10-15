"""Composition root: builds the agent from settings."""

import httpx

from calorie_agent.agent.core import CalorieAgent
from calorie_agent.agent.graph import Deps
from calorie_agent.agent.llm import LangChainLLM, LLMService
from calorie_agent.config import Settings
from calorie_agent.db.repo import Repository
from calorie_agent.db.session import make_engine, migrate
from calorie_agent.nutrition.off import OpenFoodFactsClient
from calorie_agent.nutrition.service import FoodSource, NutritionService
from calorie_agent.nutrition.usda import USDAClient


def build_agent(settings: Settings, llm: LLMService | None = None) -> CalorieAgent:
    migrate(settings.database_url)
    engine = make_engine(settings.database_url)
    llm = llm or LangChainLLM(settings.llm_model, settings.llm_temperature)
    http = httpx.AsyncClient()
    sources: list[FoodSource] = [USDAClient(settings.usda_api_key, http, settings.match_threshold)]
    if settings.use_open_food_facts:
        sources.append(OpenFoodFactsClient(http, settings.match_threshold))
    nutrition = NutritionService(engine, sources, llm.estimate)
    return CalorieAgent(
        Deps(repo=Repository(engine), llm=llm, nutrition=nutrition),
        default_tz=settings.default_timezone,
        max_chars=settings.max_message_chars,
    )
