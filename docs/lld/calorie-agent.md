# LLD — Calorie Agent (MVP)

## 1. Interfaces (no REST API in MVP)
The "API" is the chat surface.

| Input | Handler | LLM calls |
|---|---|---|
| `/start`, `/help` | static help + registration | 0 |
| `/today` | daily summary | 0 |
| `/week` | 7-day report | 0 |
| `/undo` | delete last entry of today | 0 |
| `/goal <kcal> [protein_g]` | update goals | 0 |
| `/tz <IANA zone>` | update timezone | 0 |
| `/cancel` | drop a pending clarification | 0 |
| free text | LangGraph agent | 1 (classify) + 1 (parse, if food) + 0..n (estimates) |

## 2. Database
```
user
  id PK · telegram_id BIGINT UNIQUE · timezone TEXT · kcal_goal INT NULL
  protein_goal_g INT NULL · last_weekly_report DATE NULL · created_at TIMESTAMP
meal_entry
  id PK · user_id FK→user.id · raw_text TEXT · logged_at TIMESTAMP (UTC) · local_date DATE
  INDEX ix_meal_entry_user_date (user_id, local_date)
food_item
  id PK · entry_id FK→meal_entry.id (ON DELETE CASCADE) · name · quantity REAL · unit
  grams REAL · kcal · protein_g · carbs_g · fat_g REAL
  source TEXT ('usda'|'off'|'llm_estimate'|'cache:*') · match_name TEXT NULL
food_cache
  query_key TEXT PK · source · match_name · kcal_100g · protein_100g · carbs_100g · fat_100g · fetched_at
```
Migrations are managed with Alembic (`src/calorie_agent/migrations`) and applied automatically on startup (`upgrade head`).

## 3. Service Layer
```python
LLMService                       # the only class that talks to an LLM
  classify(text) -> RouterOutput     # intent + optional kcal_goal/protein_goal/timezone
  parse_meal(text) -> ParsedMeal     # items[name, quantity, unit, grams, search_term], unclear_items
  estimate(name) -> Per100g          # fallback nutrition per 100 g

NutritionService
  resolve(item) -> ResolvedItem      # cache → USDA → OFF → LLM; macros = per100g * grams / 100

Repository
  get_or_create_user, set_goal, set_timezone
  add_entry(user, raw_text, items, now_utc) -> MealEntry
  day_totals(user_id, date) -> Totals
  week_totals(user_id, end_date) -> list[DayTotals]
  undo_last(user_id, date) -> MealEntry | None
  users_due_weekly_report(now_utc) -> list[User]
```

## 4. Agent Graph (LangGraph)
State: `user_id, text, local_date, intent, router, parsed, clarified, reply`
```
START → classify ─┬─ log_food → parse ─┬─(unclear & !clarified)→ clarify[interrupt] → parse
                  │                    └─→ resolve_and_save → END
                  ├─ query_today → END      ├─ weekly_report → END
                  ├─ undo → END             ├─ set_goal → END
                  ├─ help → END             └─ off_topic → END
```
- Checkpointer: `InMemorySaver`, thread_id = `user-{id}`.
- When a message arrives and the thread has a pending interrupt, it is sent as `Command(resume=text)`.
- Clarification is asked **at most once**; after that, the parser must assume standard portions.

## 5. Validation Rules
- Message length ≤ 500 chars, otherwise rejected before any LLM call.
- `kcal_goal` must be within 800–6000 and `protein_goal_g` within 20–400.
- Timezone must be a valid `zoneinfo` key.
- Parsed `grams` must be > 0 and ≤ 3000 per item, and at most 15 items per message.
- A DB match is accepted only if its token-overlap score ≥ 0.5; otherwise the next source is tried.
- Sources must return non-negative macros and kcal ≤ 900 per 100 g.

## 6. Sequence — "2 eggs and toast"
```
User → Telegram → Adapter: authorize(telegram_id) → repo.get_or_create_user
Adapter → Graph.ainvoke(text)
Graph.classify → LLM → {intent: log_food}
Graph.parse → LLM → [{egg,2,piece,100g,"egg whole boiled"}, {toast,1,slice,30g,"bread white toasted"}]
Graph.resolve → cache miss → USDA search → match → cache write → compute macros
Graph.save → repo.add_entry → repo.day_totals
Graph → template reply → Adapter → Telegram
```

## 7. Testing Strategy
- **Unit (`tests/`, no network, no LLM):** repository math, report formatting, matching score, graph routing with a fake LLM, validation.
- **Evals (`evals/`, real LLM, marked `eval`):** intent accuracy, guardrail refusal, parse F1/gram error, calorie MAPE. Thresholds are enforced, and results are written to `evals/results/`.
- **CI:** lint + unit tests on every PR; evals on manual dispatch or a nightly run with a repo secret.

## 8. Rollback Strategy
- Code: tagged releases; roll back by redeploying the previous image tag.
- DB: `alembic downgrade -1`. Migrations are additive only in MVP.
- Data: SQLite is a single file in a mounted volume. Back it up by copying `data/calorie_agent.db`.
