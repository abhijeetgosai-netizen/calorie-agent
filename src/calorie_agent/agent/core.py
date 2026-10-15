"""Platform-agnostic agent facade. Adapters (Telegram, CLI, …) only call this."""

import logging

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from calorie_agent import reports
from calorie_agent.agent.graph import Deps, apply_settings, build_graph, undo_last
from calorie_agent.db.repo import local_today

log = logging.getLogger(__name__)


class CalorieAgent:
    def __init__(self, deps: Deps, default_tz: str = "UTC", max_chars: int = 500) -> None:
        self.deps = deps
        self.repo = deps.repo
        self.default_tz = default_tz
        self.max_chars = max_chars
        self.graph = build_graph(deps, checkpointer=InMemorySaver())

    # ---- identity ---------------------------------------------------------
    def user_id_for(self, platform_user_id: int) -> int:
        user = self.repo.get_or_create_user(platform_user_id, self.default_tz)
        assert user.id is not None
        return user.id

    def _today(self, user_id: int):
        return local_today(self.repo.get_user(user_id).timezone)

    @staticmethod
    def _config(user_id: int) -> dict:
        return {"configurable": {"thread_id": f"user-{user_id}"}}

    async def _pending(self, user_id: int) -> bool:
        snap = await self.graph.aget_state(self._config(user_id))
        return bool(snap.next)

    # ---- free text --------------------------------------------------------
    async def handle_text(self, user_id: int, text: str) -> str:
        text = text.strip()
        if not text:
            return reports.HELP
        if len(text) > self.max_chars:
            return reports.TOO_LONG
        cfg = self._config(user_id)
        try:
            if await self._pending(user_id):
                result = await self.graph.ainvoke(Command(resume=text), cfg)
            else:
                result = await self.graph.ainvoke(
                    {
                        "user_id": user_id,
                        "text": text,
                        "local_date": self._today(user_id).isoformat(),
                        "intent": "",
                        "router": {},
                        "parsed": {},
                        "clarified": False,
                        "reply": "",
                    },
                    cfg,
                )
        except Exception:
            log.exception("agent failure for user %s", user_id)
            await self.cancel(user_id)
            return reports.ERROR
        if interrupts := result.get("__interrupt__"):
            return interrupts[0].value["question"]
        return result.get("reply") or reports.ERROR

    async def cancel(self, user_id: int) -> str:
        if await self._pending(user_id):
            # Jump the paused run to END so the next message starts fresh.
            await self.graph.aupdate_state(
                self._config(user_id), {"reply": reports.CANCELLED}, as_node="save"
            )
        return reports.CANCELLED

    # ---- deterministic commands (no LLM) ------------------------------------
    def today(self, user_id: int) -> str:
        user = self.repo.get_user(user_id)
        return reports.today(self.repo.day_totals(user_id, self._today(user_id)), user)

    def week(self, user_id: int) -> str:
        user = self.repo.get_user(user_id)
        end = self._today(user_id)
        return reports.weekly(self.repo.week_totals(user_id, end), user, end)

    def undo(self, user_id: int) -> str:
        return undo_last(self.repo, user_id, self._today(user_id))

    def goal(self, user_id: int, args: list[str]) -> str:
        try:
            nums = [int(float(a)) for a in args[:2]]
        except ValueError:
            return reports.GOAL_USAGE
        if not nums:
            return reports.GOAL_USAGE
        return apply_settings(self.repo, user_id, nums[0], nums[1] if len(nums) > 1 else None, None)

    def timezone(self, user_id: int, args: list[str]) -> str:
        if not args:
            return reports.TZ_USAGE
        return apply_settings(self.repo, user_id, None, None, args[0])

    async def command(self, user_id: int, name: str, args: list[str]) -> str:
        name = name.lower().lstrip("/")
        match name:
            case "start" | "help":
                return reports.HELP
            case "today":
                return self.today(user_id)
            case "week":
                return self.week(user_id)
            case "undo":
                return self.undo(user_id)
            case "goal":
                return self.goal(user_id, args)
            case "tz" | "timezone":
                return self.timezone(user_id, args)
            case "cancel":
                return await self.cancel(user_id)
            case _:
                return reports.HELP
