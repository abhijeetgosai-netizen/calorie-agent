# Contributing

Thanks for helping! The project values **simplicity over cleverness**. Please read
[`docs/hld`](docs/hld/calorie-agent.md) before proposing large changes.

## Setup
```bash
uv sync --all-extras
uv run pytest                 # must pass, no API key needed
uv run ruff check . && uv run ruff format .
uv run calorie-agent chat     # manual testing without Telegram
```

## Ground rules
1. **The LLM never does math and never writes user-facing text.** Arithmetic goes in
   `db/repo.py` / `nutrition/types.py`; replies go in `reports.py`.
2. **Every LLM call lives in `agent/llm.py`** behind the `LLMService` protocol, so tests can use `tests/fakes.py`.
3. **Behaviour changes need an eval row.** If you fix a misparse or misclassification, add the example
   to `evals/datasets/*.jsonl`. Paste your `uv run pytest evals -m eval` results in the PR.
4. **Schema changes need an Alembic migration** (`uv run alembic revision --autogenerate -m "…"`)
   and an update to `docs/lld`.
5. **Features beyond the roadmap phase in progress:** open an issue first.

## Adding a chat platform
Create `src/calorie_agent/adapters/<platform>.py`. An adapter only needs to: map the platform
user → `agent.user_id_for(id)`, route commands → `agent.command(...)` and text →
`agent.handle_text(...)`, then send the returned (Telegram-HTML) string. See `adapters/telegram.py`.

## Adding a nutrition source
Implement `async def search(query) -> FoodMatch | None` (see `nutrition/usda.py`), use
`best_match` for match quality, and register it in `app.py`. Add mocked-HTTP tests like
`tests/test_sources.py`.
