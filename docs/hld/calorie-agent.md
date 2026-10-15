# HLD — Calorie Agent (MVP)

Status: **Approved** · Version 0.1

## Problem Statement
Logging food in calorie apps involves searching databases, picking portions, and tapping through forms, so most people give up within a week. People already describe what they ate in plain sentences in chat apps. The agent turns those messages into accurate, persistent calorie and macro logs.

## Business Value
- **Retention:** logging a meal takes one sentence, which removes the friction that causes churn.
- **Trust:** numbers come from nutrition databases, not LLM guesses, and every estimate is labelled as one.
- **Zero hosting cost for us:** it is self-hosted with bring-your-own-key, so each user pays only their own LLM usage.

## User Flow
1. The user deploys the bot (Docker or `uv run`), sets a Telegram token and LLM key, and opens a DM with the bot.
2. `/start` registers the user and shows help; `/goal` and `/tz` set the targets and timezone.
3. The user types "2 eggs and a slice of toast". The agent replies with each item's kcal and macros plus the running total for the day.
4. If the quantity is unclear ("had rice"), the bot asks once how much, then logs.
5. `/today` returns today's totals; `/week` returns a 7-day report. The weekly report is also pushed automatically on the configured day.
6. Anything off-topic gets a polite refusal.

## Architecture
```
Telegram DM ─► TelegramAdapter (python-telegram-bot)
                 │  commands (/today /week /undo /goal /tz) ─► deterministic handlers ─┐
                 │  free text                                                            │
                 ▼                                                                       │
             LangGraph agent                                                             │
               classify ─► log_food ─► parse (LLM) ─► [clarify via interrupt]            │
                         │              resolve: cache → USDA → OpenFoodFacts → LLM est. │
                         │              save ─► template reply                           │
                         ├► today / week / undo / set_goal / help / off_topic ───────────┤
                         ▼                                                               ▼
                    SQL (SQLite default / Postgres) ◄─────────── Reports (templates)
             JobQueue (hourly) ─► weekly report push per user's local time
```

## Components
| Component | Responsibility |
|---|---|
| `adapters/telegram.py` | Auth allow-list, command routing, message → agent → reply |
| `agent/graph.py` | LangGraph state machine (routing + clarification interrupt) |
| `agent/llm.py` | **Only** place the LLM is called: classify, parse, estimate |
| `nutrition/*` | Cache, USDA FoodData Central, Open Food Facts, LLM fallback |
| `db/*` | SQLModel models, repository, Alembic migrations |
| `reports.py` | Deterministic text formatting of all replies |
| `cli.py` | `bot` (Telegram) and `chat` (local terminal REPL for testing) |

## Guardrails
1. Every reply is rendered from a template, so the LLM never writes user-facing text.
2. Only a fixed set of intents is allowed; anything else becomes `off_topic` and gets a fixed refusal.
3. Inputs are capped in length, and each LLM call uses structured (Pydantic) output.
4. The bot answers only users on the allow-list (`ALLOWED_USER_IDS`), which protects the owner's API key.
5. All arithmetic (per-item totals, daily and weekly sums) is done in Python and SQL.

## Risks
| Risk | Mitigation |
|---|---|
| Wrong database match ("roti" → "rotisserie chicken") | Token-overlap match score; falls back to LLM estimate below a threshold |
| LLM portion→grams error | Eval-tracked; user can `/undo` and re-log with grams |
| USDA rate limits (`DEMO_KEY`) | Local cache table; a free personal key is documented |
| Regional dishes missing from USDA | OFF + labelled LLM estimate; regional datasets planned for Phase 2 |
| Restart loses pending clarification | Acceptable for MVP (in-memory checkpointer) |

## MVP Scope
Telegram DMs, self-host BYOK (OpenAI, Anthropic, Gemini, Groq, Ollama), 7 intents, USDA/OFF/LLM resolution, today and weekly reports (on demand and scheduled), undo, goals, timezone, SQLite/Postgres, evals in CI, Docker.

## Explicitly NOT in MVP
Hosted multi-tenant bot / `/setkey`, photo logging, charts, saved meals, other chat platforms, web dashboard, Redis or queues.
