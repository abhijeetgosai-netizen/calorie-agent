"""All database reads/writes. Pure, deterministic arithmetic lives here."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from calorie_agent.db.models import FoodItem, MealEntry, User, utcnow
from calorie_agent.nutrition.types import ResolvedItem


@dataclass(frozen=True)
class Totals:
    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    entries: int = 0


@dataclass(frozen=True)
class DayTotals:
    day: date
    totals: Totals


def local_today(tz: str, now_utc: datetime | None = None) -> date:
    now = now_utc or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(ZoneInfo(tz)).date()


class Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # ---- users -------------------------------------------------------------
    def get_or_create_user(self, telegram_id: int, default_tz: str = "UTC") -> User:
        with Session(self.engine) as s:
            user = s.exec(select(User).where(User.telegram_id == telegram_id)).first()
            if user is None:
                user = User(telegram_id=telegram_id, timezone=default_tz)
                s.add(user)
                s.commit()
                s.refresh(user)
            return user

    def get_user(self, user_id: int) -> User:
        with Session(self.engine) as s:
            user = s.get(User, user_id)
            if user is None:
                raise LookupError(f"user {user_id} not found")
            return user

    def set_goal(self, user_id: int, kcal: int | None, protein_g: int | None) -> User:
        with Session(self.engine) as s:
            user = s.get(User, user_id)
            assert user is not None
            if kcal is not None:
                user.kcal_goal = kcal
            if protein_g is not None:
                user.protein_goal_g = protein_g
            s.add(user)
            s.commit()
            s.refresh(user)
            return user

    def set_timezone(self, user_id: int, tz: str) -> User:
        ZoneInfo(tz)  # raises if invalid
        with Session(self.engine) as s:
            user = s.get(User, user_id)
            assert user is not None
            user.timezone = tz
            s.add(user)
            s.commit()
            s.refresh(user)
            return user

    # ---- entries -----------------------------------------------------------
    def add_entry(
        self,
        user_id: int,
        raw_text: str,
        items: list[ResolvedItem],
        local_date: date,
        now_utc: datetime | None = None,
    ) -> MealEntry:
        with Session(self.engine) as s:
            entry = MealEntry(
                user_id=user_id,
                raw_text=raw_text,
                logged_at=now_utc or utcnow(),
                local_date=local_date,
            )
            s.add(entry)
            s.flush()
            for it in items:
                s.add(
                    FoodItem(
                        entry_id=entry.id,
                        name=it.name,
                        quantity=it.quantity,
                        unit=it.unit,
                        grams=it.grams,
                        kcal=it.kcal,
                        protein_g=it.protein_g,
                        carbs_g=it.carbs_g,
                        fat_g=it.fat_g,
                        source=it.source,
                        match_name=it.match_name,
                    )
                )
            s.commit()
            s.refresh(entry)
            return entry

    def undo_last(self, user_id: int, local_date: date) -> tuple[MealEntry, list[FoodItem]] | None:
        with Session(self.engine) as s:
            entry = s.exec(
                select(MealEntry)
                .where(MealEntry.user_id == user_id, MealEntry.local_date == local_date)
                .order_by(col(MealEntry.id).desc())
            ).first()
            if entry is None:
                return None
            items = list(s.exec(select(FoodItem).where(FoodItem.entry_id == entry.id)))
            for it in items:
                s.delete(it)
            s.delete(entry)
            s.commit()
            return entry, items

    # ---- aggregates (deterministic) ----------------------------------------
    def _totals_by_day(self, user_id: int, start: date, end: date) -> dict[date, Totals]:
        with Session(self.engine) as s:
            rows = s.exec(
                select(
                    MealEntry.local_date,
                    func.coalesce(func.sum(FoodItem.kcal), 0),
                    func.coalesce(func.sum(FoodItem.protein_g), 0),
                    func.coalesce(func.sum(FoodItem.carbs_g), 0),
                    func.coalesce(func.sum(FoodItem.fat_g), 0),
                    func.count(func.distinct(MealEntry.id)),
                )
                .join(FoodItem, col(FoodItem.entry_id) == col(MealEntry.id))
                .where(
                    MealEntry.user_id == user_id,
                    MealEntry.local_date >= start,
                    MealEntry.local_date <= end,
                )
                .group_by(MealEntry.local_date)
            ).all()
        return {
            r[0]: Totals(float(r[1]), float(r[2]), float(r[3]), float(r[4]), int(r[5]))
            for r in rows
        }

    def day_totals(self, user_id: int, day: date) -> Totals:
        return self._totals_by_day(user_id, day, day).get(day, Totals())

    def week_totals(self, user_id: int, end: date) -> list[DayTotals]:
        start = end - timedelta(days=6)
        by_day = self._totals_by_day(user_id, start, end)
        return [
            DayTotals(start + timedelta(days=i), by_day.get(start + timedelta(days=i), Totals()))
            for i in range(7)
        ]

    # ---- scheduling --------------------------------------------------------
    def all_users(self) -> list[User]:
        with Session(self.engine) as s:
            return list(s.exec(select(User)))

    def mark_weekly_report_sent(self, user_id: int, day: date) -> None:
        with Session(self.engine) as s:
            user = s.get(User, user_id)
            assert user is not None
            user.last_weekly_report = day
            s.add(user)
            s.commit()
