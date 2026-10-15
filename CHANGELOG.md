# Changelog
Format: [Keep a Changelog](https://keepachangelog.com); versions follow [SemVer](https://semver.org).

## [0.1.0] — Unreleased
### Added
- Telegram DM bot with allow-list (self-host, bring-your-own-key).
- LangGraph agent: intent routing, food parsing, one-shot clarification via interrupt.
- Nutrition resolution: cache → USDA FoodData Central → Open Food Facts → labelled LLM estimate.
- `/today`, `/week`, `/undo`, `/goal`, `/tz`, `/cancel`; scheduled weekly report in each user's timezone.
- Templated replies (no free-form LLM output), input length cap, structured outputs.
- SQLite by default, Postgres via `DATABASE_URL`; Alembic migrations applied on startup.
- Unit tests (no network) and threshold-enforced LLM evals; CI + nightly eval workflow.
- `calorie-agent chat` local terminal mode; Docker image.
