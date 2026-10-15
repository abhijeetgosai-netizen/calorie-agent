"""Graph routing and guardrails with a fake LLM — no network."""

from calorie_agent import reports


async def test_log_food_replies_with_item_and_day_total(agent, uid):
    out = await agent.handle_text(uid, "had 2 eggs")
    assert "Logged" in out and "155 kcal" in out and "Today:" in out
    out = await agent.handle_text(uid, "2 eggs again")
    assert "310 kcal" in out  # running daily total is summed in SQL


async def test_off_topic_is_refused_without_parsing(agent, uid, llm):
    out = await agent.handle_text(uid, "write me a poem about pizza")
    assert out == reports.REFUSAL
    assert llm.calls == ["classify"]


async def test_too_long_rejected_before_llm(agent, uid, llm):
    out = await agent.handle_text(uid, "egg " * 300)
    assert out == reports.TOO_LONG and llm.calls == []


async def test_clarification_round_trip(agent, uid):
    q = await agent.handle_text(uid, "had rice")
    assert "How much rice" in q
    out = await agent.handle_text(uid, "2 cups")
    assert "Logged" in out and "416 kcal" in out  # 320 g × 130 kcal/100 g
    # Next message starts a fresh run, not a resume.
    assert "Logged" in await agent.handle_text(uid, "2 eggs")


async def test_clarification_asked_only_once(agent, uid, llm):
    await agent.handle_text(uid, "had rice")
    await agent.handle_text(uid, "a normal amount")  # still no "cup"
    assert llm.calls.count("parse(clarify=False)") == 1


async def test_cancel_drops_pending_question(agent, uid):
    await agent.handle_text(uid, "had rice")
    assert await agent.command(uid, "/cancel", []) == reports.CANCELLED
    assert "Nothing logged" in agent.today(uid)
    assert "Logged" in await agent.handle_text(uid, "2 eggs")


async def test_unknown_food_uses_labelled_llm_estimate(agent, uid, llm):
    out = await agent.handle_text(uid, "1 zorbcake")
    assert "~200 kcal" in out and "AI estimate" in out
    assert "estimate(zorbcake)" in llm.calls


async def test_cache_avoids_repeat_lookups(agent, uid, source):
    await agent.handle_text(uid, "2 eggs")
    await agent.handle_text(uid, "2 eggs")
    assert source.calls == 1


async def test_no_food_found(agent, uid):
    assert await agent.handle_text(uid, "nothing really") == reports.NO_FOOD


async def test_commands_use_no_llm(agent, uid, llm):
    await agent.command(uid, "/today", [])
    await agent.command(uid, "/week", [])
    await agent.command(uid, "/undo", [])
    assert llm.calls == []


async def test_goal_validation(agent, uid):
    assert "Daily goal set" in await agent.command(uid, "/goal", ["2000", "120"])
    assert await agent.command(uid, "/goal", ["50"]) == reports.GOAL_USAGE
    assert await agent.command(uid, "/goal", ["abc"]) == reports.GOAL_USAGE


async def test_timezone_validation(agent, uid):
    assert "Asia/Kolkata" in await agent.command(uid, "/tz", ["Asia/Kolkata"])
    assert await agent.command(uid, "/tz", ["Mars/Base"]) == reports.TZ_USAGE


async def test_goal_via_natural_language(agent, uid):
    out = await agent.handle_text(uid, "set my goal to 2000 kcal and 120g protein")
    assert "2,000 kcal" in out and "120g protein" in out


async def test_undo_then_week(agent, uid):
    await agent.handle_text(uid, "2 eggs")
    assert "Removed" in await agent.command(uid, "/undo", [])
    assert "No meals" in agent.week(uid)
    await agent.handle_text(uid, "2 eggs")
    assert "Weekly report" in agent.week(uid) and "Days logged: 1/7" in agent.week(uid)


async def test_user_text_is_html_escaped(agent, uid, llm):
    from calorie_agent.nutrition.types import ResolvedItem

    line = reports.item_line(ResolvedItem("<b>egg</b>", 1, "pc", 50, 77, 6, 0, 5, "usda"))
    assert "<b>egg</b>" not in line and "&lt;b&gt;" in line


async def test_llm_estimates_expire_from_cache(agent, uid, llm, engine):
    from datetime import timedelta

    from sqlmodel import Session

    from calorie_agent.db.models import FoodCache, utcnow

    await agent.handle_text(uid, "1 zorbcake")
    with Session(engine) as s:
        row = s.get(FoodCache, "zorbcake")
        row.fetched_at = utcnow() - timedelta(days=2)
        s.add(row)
        s.commit()
    await agent.handle_text(uid, "1 zorbcake")
    assert llm.calls.count("estimate(zorbcake)") == 2
