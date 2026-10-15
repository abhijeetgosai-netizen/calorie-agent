from datetime import date

from calorie_agent.db.repo import local_today
from calorie_agent.nutrition.types import ResolvedItem


def item(kcal, p=10.0):
    return ResolvedItem("x", 1, "piece", 100, kcal, p, 5.0, 2.0, "usda")


def test_day_totals_are_exact_sums(repo):
    u = repo.get_or_create_user(1)
    d = date(2026, 10, 12)
    repo.add_entry(u.id, "a", [item(100.5), item(200.25)], d)
    repo.add_entry(u.id, "b", [item(50)], d)
    repo.add_entry(u.id, "other day", [item(999)], date(2026, 10, 11))
    t = repo.day_totals(u.id, d)
    assert t.kcal == 350.75
    assert t.protein_g == 30.0
    assert t.entries == 2


def test_users_are_isolated(repo):
    a, b = repo.get_or_create_user(1), repo.get_or_create_user(2)
    d = date(2026, 10, 12)
    repo.add_entry(a.id, "a", [item(100)], d)
    assert repo.day_totals(b.id, d).kcal == 0


def test_week_has_seven_days_with_gaps(repo):
    u = repo.get_or_create_user(1)
    repo.add_entry(u.id, "a", [item(300)], date(2026, 10, 9))
    week = repo.week_totals(u.id, date(2026, 10, 15))
    assert [d.day.day for d in week] == [9, 10, 11, 12, 13, 14, 15]
    assert week[0].totals.kcal == 300 and week[1].totals.entries == 0


def test_undo_removes_only_last_entry_and_items(repo):
    u = repo.get_or_create_user(1)
    d = date(2026, 10, 12)
    repo.add_entry(u.id, "first", [item(100)], d)
    repo.add_entry(u.id, "second", [item(200), item(1)], d)
    entry, items = repo.undo_last(u.id, d)
    assert entry.raw_text == "second" and len(items) == 2
    assert repo.day_totals(u.id, d).kcal == 100


def test_local_date_respects_timezone():
    from datetime import datetime

    utc = datetime(2026, 10, 15, 20, 0)  # 20:00 UTC
    assert local_today("UTC", utc) == date(2026, 10, 15)
    assert local_today("Asia/Kolkata", utc) == date(2026, 10, 16)  # 01:30 next day
