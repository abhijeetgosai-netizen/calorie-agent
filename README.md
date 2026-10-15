# 🍽 Calorie Agent

[![CI](https://github.com/abhijeetgosai-netizen/calorie-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/abhijeetgosai-netizen/calorie-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

**Log your food by just texting it.** A self-hosted Telegram bot that turns "2 eggs and a slice of toast" into calories, protein, carbs and fat, keeps a daily running total, and sends you a weekly report.

- 🔑 **Bring your own key:** OpenAI, Anthropic, Gemini, Groq, or fully local and free with Ollama.
- 🎯 **Real nutrition data:** values come from USDA FoodData Central and Open Food Facts. The LLM only *reads* your message; your code does the math. If a food isn't in either database, the AI estimates it and the reply marks it with `~`.
- 🔒 **Private:** your log stays in a SQLite file on your machine. Data leaves it only for the LLM provider you chose and the food-database lookups.
- 🧪 **Measured:** threshold-enforced evals for intent accuracy, guardrails, parsing, and calorie error.

```
you  › had 2 boiled eggs and a slice of toast
bot  › ✅ Logged
       • egg (2 piece, 100g): 155 kcal · P 12.6g · C 1.1g · F 10.6g
       • toast (1 slice, 30g): 87 kcal · P 2.7g · C 16.2g · F 1.1g
       Meal total: 242 kcal

       📊 Today: 1,240 / 2,000 kcal (760 left)
       Protein 68g / 120g · Carbs 140g · Fat 41g
```

## Quick start (5 minutes)

1. **Create a bot:** in Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token.
2. **Configure:**
   ```bash
   git clone https://github.com/abhijeetgosai-netizen/calorie-agent && cd calorie-agent
   cp .env.example .env     # paste TELEGRAM_BOT_TOKEN and your LLM key
   ```
3. **Run:** pick one.
   ```bash
   docker compose up -d                                  # Docker
   uv sync --extra openai && uv run calorie-agent bot    # or with uv (Python 3.12+)
   ```
4. **Lock it to you:** message your bot. It replies with your Telegram ID. Put that ID in `ALLOWED_USER_IDS` in `.env` and restart. Until you do this, anyone who finds the bot can spend your API credits.
5. Send `/tz Asia/Kolkata` (your timezone) and `/goal 2000 120`, and start logging.

**Try it without Telegram:** `uv run calorie-agent chat` opens a local terminal chat.

## Commands

| | |
|---|---|
| *any text* | Log what you ate ("dal chawal and a lassi", "200g chicken breast") |
| `/today` | Today's totals vs. goal |
| `/week` | 7-day report (also sent automatically on Sunday at 20:00 local time; configurable) |
| `/undo` | Remove your last log today |
| `/goal 2000 120` | Daily kcal and optional protein (g) goal |
| `/tz Europe/Berlin` | Your timezone (decides when a day starts) |
| `/cancel` | Cancel a pending "how much?" question |

You can also ask these in plain words: "how am I doing today?", "set my goal to 1800". Anything outside food logging gets a polite refusal.

## How it works

```
Telegram ─► adapter ─► LangGraph:  classify ─┬─ log_food → parse (LLM) → clarify? → resolve → save
                                             ├─ today / week / undo / set_goal / help
                                             └─ off_topic → refusal
resolve:  cache → USDA FoodData Central → Open Food Facts → LLM estimate (marked ~)
```

**The LLM never writes what you see.** It does three narrow jobs, each with structured (Pydantic) output:
1. Classify the intent.
2. Extract foods, quantities, and estimated grams.
3. Estimate per-100 g nutrition, only when no database has the food.

All arithmetic is done in Python and SQL, and every reply is rendered from a template. This is the main guardrail: a prompt injection can at worst be misclassified, and it can never make the bot say something else.

Design docs: [`docs/hld`](docs/hld/calorie-agent.md) · [`docs/lld`](docs/lld/calorie-agent.md)

## Configuration

Everything is set in `.env` (see [`.env.example`](.env.example)).

| Variable | Default | Notes |
|---|---|---|
| `LLM_MODEL` | `openai:gpt-4o-mini` | `provider:model` for LangChain [`init_chat_model`](https://python.langchain.com/docs/how_to/chat_models_universal_init/) |
| `USDA_API_KEY` | `DEMO_KEY` | [Free key](https://fdc.nal.usda.gov/api-key-signup). `DEMO_KEY` is heavily rate-limited |
| `DATABASE_URL` | SQLite in `./data` | Postgres: `postgresql+psycopg://…` (install the `postgres` extra) |
| `ALLOWED_USER_IDS` | *(empty)* | Comma-separated Telegram IDs |
| `WEEKLY_REPORT_WEEKDAY` / `_HOUR` | `6` / `20` | Sunday 20:00 in each user's local time |

Install only the provider you need: `uv sync --extra anthropic` (choices: `openai`, `anthropic`, `google`, `groq`, `ollama`, `postgres`, `all`).

## Evals

```bash
uv run pytest                    # unit tests: no network, no API key, < 2 s
uv run pytest evals -m eval -v   # real-model evals (uses LLM_MODEL from .env, costs ~cents)
```

| Eval | Dataset | Gate |
|---|---|---|
| Intent accuracy | `evals/datasets/intents.jsonl` | ≥ 95% |
| Guardrails (injections, off-topic) | `guardrails.jsonl` | 100% refused |
| Parsing (item F1, grams error) | `parsing.jsonl` | F1 ≥ 0.90, grams MAPE ≤ 35% |
| Calorie accuracy, end to end | `calories.jsonl` | MAPE ≤ 15% |

Each run writes `evals/results/<eval>-<timestamp>.json` with the model, metrics, and every failure. You can override thresholds with env vars (`EVAL_MIN_INTENT_ACC`, …). CI runs unit tests on every PR and evals nightly ([`.github/workflows`](.github/workflows)).

**Found a wrong answer?** Add it to a dataset in your PR. Every bug report becomes a permanent regression test.

## Database migrations

Migrations are applied automatically on startup. After changing `db/models.py`:
```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic downgrade -1      # rollback
```
Back up your data by copying `data/calorie_agent.db`.

## Roadmap

- **Phase 2:** 📸 photo logging (vision models), saved meals ("my usual breakfast"), weekly chart images, `/export` CSV, regional food datasets (e.g. Indian IFCT).
- **Phase 3:** Discord / WhatsApp adapters, web dashboard, step/wearable integration.

## Disclaimer
Numbers are estimates for personal tracking, not medical or dietary advice.

## License
[MIT](LICENSE). Contributions welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).
