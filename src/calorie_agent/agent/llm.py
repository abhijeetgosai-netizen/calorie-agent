"""The only module that talks to an LLM. Swap or mock it freely (see tests/fakes.py)."""

from typing import Protocol

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from calorie_agent.agent import prompts
from calorie_agent.agent.schemas import ParsedMeal, RouterOutput, validate_meal
from calorie_agent.nutrition.types import Per100g


class LLMService(Protocol):
    async def classify(self, text: str) -> RouterOutput: ...
    async def parse_meal(self, text: str, allow_clarification: bool) -> ParsedMeal: ...
    async def estimate(self, food: str) -> Per100g: ...


# Newer Claude models removed the sampling parameters; sending temperature returns a 400.
# Older Claude models (4.6 and earlier) and every other provider still accept it.
_NO_SAMPLING = (
    "claude-fable-5",
    "claude-mythos-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-sonnet-5",
)


class LangChainLLM:
    """BYOK: any provider supported by LangChain's init_chat_model ("provider:model")."""

    def __init__(self, model: str, temperature: float = 0.0) -> None:
        kwargs = {} if any(m in model for m in _NO_SAMPLING) else {"temperature": temperature}
        llm = init_chat_model(model, **kwargs)
        self._router = llm.with_structured_output(RouterOutput)
        self._parser = llm.with_structured_output(ParsedMeal)
        self._estimator = llm.with_structured_output(Per100g)

    async def classify(self, text: str) -> RouterOutput:
        return await self._router.ainvoke([SystemMessage(prompts.CLASSIFY), HumanMessage(text)])  # type: ignore[return-value]

    async def parse_meal(self, text: str, allow_clarification: bool) -> ParsedMeal:
        rule = prompts.CLARIFY_ALLOWED if allow_clarification else prompts.CLARIFY_FORBIDDEN
        meal: ParsedMeal = await self._parser.ainvoke(
            [SystemMessage(prompts.PARSE.format(clarify_rule=rule)), HumanMessage(text)]
        )  # type: ignore[assignment]
        meal = validate_meal(meal)
        if not allow_clarification:
            meal.unclear_items = []
        return meal

    async def estimate(self, food: str) -> Per100g:
        return await self._estimator.ainvoke([SystemMessage(prompts.ESTIMATE), HumanMessage(food)])  # type: ignore[return-value]
