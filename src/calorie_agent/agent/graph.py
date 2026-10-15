"""LangGraph state machine: classify → route → (parse → clarify? → resolve & save) → reply."""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from calorie_agent import reports
from calorie_agent.agent.llm import LLMService
from calorie_agent.agent.schemas import ParsedFood, ParsedMeal
from calorie_agent.db.repo import Repository
from calorie_agent.nutrition.service import NutritionService

KCAL_RANGE = (800, 6000)
PROTEIN_RANGE = (20, 400)


class AgentState(TypedDict, total=False):
    user_id: int
    text: str
    local_date: str  # ISO date in the user's timezone
    intent: str
    router: dict
    parsed: dict
    clarified: bool
    reply: str


@dataclass
class Deps:
    repo: Repository
    llm: LLMService
    nutrition: NutritionService


def build_graph(deps: Deps, checkpointer: BaseCheckpointSaver | None = None):
    repo, llm, nutrition = deps.repo, deps.llm, deps.nutrition

    async def classify(state: AgentState) -> AgentState:
        out = await llm.classify(state["text"])
        return {"intent": out.intent, "router": out.model_dump()}

    def route(state: AgentState) -> str:
        return state["intent"]

    async def parse(state: AgentState) -> AgentState:
        meal = await llm.parse_meal(state["text"], allow_clarification=not state.get("clarified"))
        return {"parsed": meal.model_dump()}

    def after_parse(state: AgentState) -> str:
        meal = ParsedMeal.model_validate(state["parsed"])
        if meal.unclear_items and not state.get("clarified"):
            return "clarify"
        return "save"

    async def clarify(state: AgentState) -> AgentState:
        meal = ParsedMeal.model_validate(state["parsed"])
        answer = interrupt({"question": reports.clarify(meal.unclear_items)})
        return {"text": f"{state['text']}\n(amount: {answer})", "clarified": True}

    async def save(state: AgentState) -> AgentState:
        meal = ParsedMeal.model_validate(state["parsed"])
        if not meal.items:
            return {"reply": reports.NO_FOOD}
        items = await asyncio.gather(*(nutrition.resolve(i) for i in meal.items))
        day = date.fromisoformat(state["local_date"])
        repo.add_entry(state["user_id"], state["text"], list(items), day)
        user = repo.get_user(state["user_id"])
        return {"reply": reports.logged(items, repo.day_totals(user.id, day), user)}

    async def query_today(state: AgentState) -> AgentState:
        user = repo.get_user(state["user_id"])
        day = date.fromisoformat(state["local_date"])
        return {"reply": reports.today(repo.day_totals(user.id, day), user)}

    async def weekly_report(state: AgentState) -> AgentState:
        user = repo.get_user(state["user_id"])
        end = date.fromisoformat(state["local_date"])
        return {"reply": reports.weekly(repo.week_totals(user.id, end), user, end)}

    async def undo(state: AgentState) -> AgentState:
        return {"reply": undo_last(repo, state["user_id"], date.fromisoformat(state["local_date"]))}

    async def set_goal(state: AgentState) -> AgentState:
        r = state.get("router") or {}
        return {
            "reply": apply_settings(
                repo,
                state["user_id"],
                r.get("kcal_goal"),
                r.get("protein_goal_g"),
                r.get("timezone"),
            )
        }

    async def help_(state: AgentState) -> AgentState:
        return {"reply": reports.HELP}

    async def off_topic(state: AgentState) -> AgentState:
        return {"reply": reports.REFUSAL}

    g = StateGraph(AgentState)
    g.add_node("classify", classify)
    g.add_node("parse", parse)
    g.add_node("clarify", clarify)
    g.add_node("save", save)
    for name, fn in {
        "query_today": query_today,
        "weekly_report": weekly_report,
        "undo": undo,
        "set_goal": set_goal,
        "help": help_,
        "off_topic": off_topic,
    }.items():
        g.add_node(name, fn)
        g.add_edge(name, END)

    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        route,
        {
            "log_food": "parse",
            "query_today": "query_today",
            "weekly_report": "weekly_report",
            "undo": "undo",
            "set_goal": "set_goal",
            "help": "help",
            "off_topic": "off_topic",
        },
    )
    g.add_conditional_edges("parse", after_parse, {"clarify": "clarify", "save": "save"})
    g.add_edge("clarify", "parse")
    g.add_edge("save", END)
    return g.compile(checkpointer=checkpointer)


# ---- deterministic helpers shared with slash commands -----------------------
def undo_last(repo: Repository, user_id: int, day: date) -> str:
    removed = repo.undo_last(user_id, day)
    if removed is None:
        return reports.NOTHING_TO_UNDO
    entry, items = removed
    user = repo.get_user(user_id)
    return reports.undone(
        entry.raw_text, sum(i.kcal for i in items), repo.day_totals(user_id, day), user
    )


def apply_settings(
    repo: Repository,
    user_id: int,
    kcal: int | None,
    protein: int | None,
    tz: str | None,
) -> str:
    replies = []
    if kcal is not None and not KCAL_RANGE[0] <= kcal <= KCAL_RANGE[1]:
        return reports.GOAL_USAGE
    if protein is not None and not PROTEIN_RANGE[0] <= protein <= PROTEIN_RANGE[1]:
        return reports.GOAL_USAGE
    if kcal is not None or protein is not None:
        replies.append(reports.goal_set(repo.set_goal(user_id, kcal, protein)))
    if tz:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            return reports.TZ_USAGE
        replies.append(reports.tz_set(repo.set_timezone(user_id, tz)))
    return "\n".join(replies) or reports.GOAL_USAGE


__all__ = ["AgentState", "Deps", "ParsedFood", "build_graph", "undo_last", "apply_settings"]
