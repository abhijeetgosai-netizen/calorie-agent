"""Database tables. Keep in sync with Alembic migrations (see docs/lld)."""

from datetime import UTC, date, datetime

from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    telegram_id: int = Field(sa_column=Column(BigInteger, unique=True, nullable=False))
    timezone: str = "UTC"
    kcal_goal: int | None = None
    protein_goal_g: int | None = None
    last_weekly_report: date | None = None
    created_at: datetime = Field(default_factory=utcnow)


class MealEntry(SQLModel, table=True):
    __tablename__ = "meal_entry"
    __table_args__ = (Index("ix_meal_entry_user_date", "user_id", "local_date"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    raw_text: str
    logged_at: datetime = Field(default_factory=utcnow)  # timezone-aware UTC
    local_date: date


class FoodItem(SQLModel, table=True):
    __tablename__ = "food_item"

    id: int | None = Field(default=None, primary_key=True)
    entry_id: int = Field(
        sa_column=Column(Integer, ForeignKey("meal_entry.id", ondelete="CASCADE"), nullable=False)
    )
    name: str
    quantity: float
    unit: str
    grams: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    source: str
    match_name: str | None = None


class FoodCache(SQLModel, table=True):
    __tablename__ = "food_cache"

    query_key: str = Field(primary_key=True)
    source: str
    match_name: str
    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float
    fetched_at: datetime = Field(default_factory=utcnow)
