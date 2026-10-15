"""Application settings, loaded from environment variables or a .env file."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str = ""
    # Comma-separated Telegram user IDs allowed to use the bot. Empty = anyone (not recommended).
    allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # LLM (BYOK). Format "<provider>:<model>", passed to LangChain's init_chat_model.
    # Provider keys are read by the provider packages: OPENAI_API_KEY, ANTHROPIC_API_KEY,
    # GOOGLE_API_KEY, GROQ_API_KEY. Ollama needs no key.
    llm_model: str = "openai:gpt-4o-mini"
    llm_temperature: float = 0.0

    # Nutrition data
    usda_api_key: str = "DEMO_KEY"  # free key: https://fdc.nal.usda.gov/api-key-signup
    use_open_food_facts: bool = True
    # Reuse nutrition from the user's own past logs before querying public databases.
    use_food_history: bool = True
    match_threshold: float = 0.5

    # Storage
    database_url: str = "sqlite:///data/calorie_agent.db"

    # Behaviour
    default_timezone: str = "UTC"
    max_message_chars: int = 500
    weekly_report_weekday: int = 6  # 0=Mon … 6=Sun, in the user's local time
    weekly_report_hour: int = 20

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _split_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        if isinstance(v, int):
            return [v]
        return v


def export_dotenv(path: str = ".env") -> None:
    """Copy .env into os.environ (without overriding real env vars).

    pydantic-settings reads .env for *our* fields, but LangChain provider packages read
    their API keys (OPENAI_API_KEY, …) straight from os.environ.
    """
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@lru_cache
def get_settings() -> Settings:
    export_dotenv()
    return Settings()
