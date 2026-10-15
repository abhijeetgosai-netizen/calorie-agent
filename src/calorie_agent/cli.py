"""Entry point: `calorie-agent bot` (Telegram) or `calorie-agent chat` (local terminal)."""

import argparse
import asyncio
import html
import logging
import re

from calorie_agent.app import build_agent
from calorie_agent.config import get_settings


def _plain(text: str) -> str:
    return html.unescape(re.sub(r"</?(b|i|pre|code)>", "", text))


async def _chat() -> None:
    agent = build_agent(get_settings())
    uid = agent.user_id_for(0)  # local user
    print("Calorie Agent — local chat. Type what you ate, /help, or 'quit'.\n")
    while True:
        try:
            text = await asyncio.to_thread(input, "you › ")
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip().lower() in {"quit", "exit"}:
            break
        if text.startswith("/"):
            name, *args = text.split()
            out = await agent.command(uid, name, args)
        else:
            out = await agent.handle_text(uid, text)
        print(f"\nbot › {_plain(out)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(prog="calorie-agent")
    parser.add_argument("mode", choices=["bot", "chat"], nargs="?", default="bot")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.mode == "chat":
        asyncio.run(_chat())
    else:
        from calorie_agent.adapters.telegram import run_bot

        settings = get_settings()
        run_bot(settings, build_agent(settings))


if __name__ == "__main__":
    main()
