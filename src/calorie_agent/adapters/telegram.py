"""Telegram adapter: auth allow-list, commands, free text, scheduled weekly report."""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import BotCommand, Update
from telegram.constants import ChatAction, ChatType, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from calorie_agent import reports
from calorie_agent.agent.core import CalorieAgent
from calorie_agent.config import Settings

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand("today", "Today's totals"),
    BotCommand("week", "Last 7 days report"),
    BotCommand("undo", "Remove last log today"),
    BotCommand("goal", "Set goal: /goal 2000 120"),
    BotCommand("tz", "Set timezone: /tz Asia/Kolkata"),
    BotCommand("cancel", "Cancel pending question"),
    BotCommand("help", "How to use"),
]


def run_bot(settings: Settings, agent: CalorieAgent) -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. See README → Quick start.")
    if not settings.allowed_user_ids:
        log.warning(
            "ALLOWED_USER_IDS is empty: ANYONE who finds this bot can spend your LLM credits."
        )

    def authorized(update: Update) -> bool:
        u = update.effective_user
        return u is not None and (
            not settings.allowed_user_ids or u.id in settings.allowed_user_ids
        )

    async def reply(update: Update, text: str) -> None:
        assert update.effective_message is not None
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )

    async def gate(update: Update) -> int | None:
        """Returns internal user id, or None (and replies) if not allowed."""
        chat = update.effective_chat
        if chat is None or chat.type != ChatType.PRIVATE:
            return None  # private DMs only; logs are personal
        if not authorized(update):
            uid = update.effective_user.id if update.effective_user else "?"
            await reply(
                update,
                f"🔒 This is a private bot. Your Telegram ID is <code>{uid}</code>.\n"
                "If this is your bot, add it to ALLOWED_USER_IDS and restart.",
            )
            return None
        return agent.user_id_for(update.effective_user.id)  # type: ignore[union-attr]

    async def on_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if (uid := await gate(update)) is None or update.effective_message is None:
            return
        cmd = (update.effective_message.text or "/help").split()[0].split("@")[0]
        await reply(update, await agent.command(uid, cmd, list(ctx.args or [])))

    async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if (uid := await gate(update)) is None or update.effective_message is None:
            return
        await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)  # type: ignore[union-attr]
        await reply(update, await agent.handle_text(uid, update.effective_message.text or ""))

    async def on_non_text(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if await gate(update) is not None:
            await reply(update, "📝 Please describe your meal in text for now.")

    async def weekly_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Runs hourly; sends the report when it's the configured day+hour in each user's tz."""
        now = datetime.now(UTC)
        for user in agent.repo.all_users():
            if settings.allowed_user_ids and user.telegram_id not in settings.allowed_user_ids:
                continue
            local = now.astimezone(ZoneInfo(user.timezone))
            if (
                local.weekday() == settings.weekly_report_weekday
                and local.hour == settings.weekly_report_hour
                and user.last_weekly_report != local.date()
            ):
                try:
                    await ctx.bot.send_message(
                        user.telegram_id,
                        agent.week(user.id),
                        parse_mode=ParseMode.HTML,  # type: ignore[arg-type]
                    )
                    agent.repo.mark_weekly_report_sent(user.id, local.date())  # type: ignore[arg-type]
                except Exception:
                    log.exception("weekly report failed for user %s", user.id)

    async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Unhandled error", exc_info=ctx.error)
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(reports.ERROR)

    async def post_init(app: Application) -> None:
        await app.bot.set_my_commands(COMMANDS)

    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(
        CommandHandler(
            ["start", "help", "today", "week", "undo", "goal", "tz", "cancel"], on_command
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, on_non_text))
    app.add_error_handler(on_error)

    now = datetime.now(UTC)
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
    assert app.job_queue is not None
    app.job_queue.run_repeating(weekly_job, interval=3600, first=next_hour)

    log.info("Bot started (model=%s)", settings.llm_model)
    app.run_polling(allowed_updates=Update.ALL_TYPES)
