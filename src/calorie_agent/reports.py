"""Every user-facing message is rendered here from templates (Telegram HTML subset).
The LLM never writes text the user sees — this is the core output guardrail."""

from collections.abc import Sequence
from datetime import date
from html import escape

from calorie_agent.db.models import User
from calorie_agent.db.repo import DayTotals, Totals
from calorie_agent.nutrition.types import ResolvedItem

HELP = (
    "🍽 <b>Calorie Agent</b>\n"
    "Just tell me what you ate, e.g. <i>2 eggs and a slice of toast</i>.\n"
    "I track calories, protein, carbs, fat and fiber.\n\n"
    "/today — today's totals\n"
    "/week — last 7 days report\n"
    "/undo — remove your last log today\n"
    "/goal 2000 120 — set kcal (and protein g) goal\n"
    "/tz Asia/Kolkata — set your timezone\n"
    "/cancel — cancel a pending question\n\n"
    "<i>Estimates are marked ~. Not medical advice.</i>"
)

REFUSAL = (
    "🙅 I can only log food and report your calorie & macro intake.\n"
    "Tell me what you ate, or try /today or /week."
)
TOO_LONG = "✂️ That message is too long. Please describe your meal in a shorter message."
NO_FOOD = "🤔 I couldn't find any food in that. Try e.g. <i>1 bowl of oatmeal with a banana</i>."
NOTHING_TO_UNDO = "Nothing logged today to undo."
CANCELLED = "👍 Cancelled."
ERROR = "⚠️ Something went wrong processing that. Please try again."


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _macros(t: Totals | ResolvedItem) -> str:
    return f"P {t.protein_g:.1f}g · C {t.carbs_g:.1f}g · F {t.fat_g:.1f}g · Fib {t.fiber_g:.1f}g"


def item_line(it: ResolvedItem) -> str:
    approx = "~" if it.is_estimate else ("*" if it.is_stated else "")
    qty = f"{it.quantity:g} {it.unit}".strip()
    return (
        f"• {escape(it.name)} ({escape(qty)}, {it.grams:.0f}g): "
        f"{approx}{_n(it.kcal)} kcal · {_macros(it)}"
    )


def day_summary(t: Totals, user: User, label: str = "Today") -> str:
    kcal = f"{_n(t.kcal)}"
    if user.kcal_goal:
        left = user.kcal_goal - t.kcal
        kcal += f" / {_n(user.kcal_goal)} kcal ({_n(abs(left))} {'left' if left >= 0 else 'over'})"
    else:
        kcal += " kcal"
    protein = f"{t.protein_g:.0f}g"
    if user.protein_goal_g:
        protein += f" / {user.protein_goal_g}g"
    return (
        f"📊 <b>{label}:</b> {kcal}\n"
        f"Protein {protein} · Carbs {t.carbs_g:.0f}g · Fat {t.fat_g:.0f}g "
        f"· Fiber {t.fiber_g:.0f}g"
    )


def logged(items: Sequence[ResolvedItem], day: Totals, user: User) -> str:
    meal_kcal = sum(i.kcal for i in items)
    lines = ["✅ <b>Logged</b>", *(item_line(i) for i in items)]
    if len(items) > 1:
        lines.append(f"Meal total: {_n(meal_kcal)} kcal")
    if any(i.is_estimate for i in items):
        lines.append("<i>~ = AI estimate (not found in food databases)</i>")
    if any(i.is_stated for i in items):
        lines.append("<i>* = your own figures, used as given</i>")
    return "\n".join(lines) + "\n\n" + day_summary(day, user)


def today(day: Totals, user: User) -> str:
    if day.entries == 0:
        return "Nothing logged today yet. Tell me what you ate!"
    return day_summary(day, user) + f"\nMeals logged: {day.entries}"


def undone(raw_text: str, items_kcal: float, day: Totals, user: User) -> str:
    return f"↩️ Removed: <i>{escape(raw_text[:80])}</i> ({_n(items_kcal)} kcal)\n\n" + day_summary(
        day, user
    )


def clarify(unclear: Sequence[str]) -> str:
    names = ", ".join(escape(u) for u in unclear)
    return (
        f"❓ How much {names} did you have? (e.g. <i>1 bowl</i>, <i>2 cups</i>, <i>200g</i>)\n"
        "Or /cancel."
    )


def goal_set(user: User) -> str:
    parts = []
    if user.kcal_goal:
        parts.append(f"{_n(user.kcal_goal)} kcal")
    if user.protein_goal_g:
        parts.append(f"{user.protein_goal_g}g protein")
    return "🎯 Daily goal set: " + " · ".join(parts)


def tz_set(user: User) -> str:
    return f"🕒 Timezone set to {escape(user.timezone)}."


GOAL_USAGE = "Usage: /goal 2000 120  (kcal 800–6000, optional protein g 20–400)"
TZ_USAGE = (
    "Usage: /tz Asia/Kolkata  (an IANA timezone name — see "
    "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)"
)


def _bar(value: float, scale_max: float, width: int = 10) -> str:
    if scale_max <= 0:
        return "░" * width
    filled = min(width, round(value / scale_max * width))
    return "▇" * filled + "░" * (width - filled)


def weekly(days: Sequence[DayTotals], user: User, end: date) -> str:
    logged_days = [d for d in days if d.totals.entries > 0]
    if not logged_days:
        return "📅 No meals logged in the last 7 days."
    scale_max = max(user.kcal_goal or 0, *(d.totals.kcal for d in days))
    rows = []
    for d in days:
        t = d.totals
        val = f"{_n(t.kcal):>6} kcal  P{t.protein_g:>4.0f}g" if t.entries else "     —"
        rows.append(f"{d.day:%a %d} {_bar(t.kcal, scale_max)} {val}")
    n = len(logged_days)
    avg_kcal = sum(d.totals.kcal for d in logged_days) / n
    avg_p = sum(d.totals.protein_g for d in logged_days) / n
    avg_c = sum(d.totals.carbs_g for d in logged_days) / n
    avg_f = sum(d.totals.fat_g for d in logged_days) / n
    avg_fib = sum(d.totals.fiber_g for d in logged_days) / n
    summary = [
        f"Days logged: {n}/7",
        f"Avg/day: {_n(avg_kcal)} kcal · P {avg_p:.0f}g · C {avg_c:.0f}g "
        f"· F {avg_f:.0f}g · Fib {avg_fib:.0f}g",
    ]
    if user.kcal_goal:
        on_target = sum(
            1 for d in logged_days if abs(d.totals.kcal - user.kcal_goal) <= 0.1 * user.kcal_goal
        )
        summary.append(f"Days within ±10% of goal: {on_target}/{n}")
    if user.protein_goal_g:
        hit = sum(1 for d in logged_days if d.totals.protein_g >= user.protein_goal_g)
        summary.append(f"Protein goal hit: {hit}/{n} days")
    start = days[0].day
    return (
        f"📅 <b>Weekly report</b> ({start:%d %b} – {end:%d %b})\n"
        f"<pre>{chr(10).join(rows)}</pre>\n" + "\n".join(summary)
    )
