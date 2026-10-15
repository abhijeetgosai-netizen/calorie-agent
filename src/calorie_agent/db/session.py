"""Engine creation and schema migration."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import create_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _ensure_sqlite_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)


def make_engine(database_url: str) -> Engine:
    _ensure_sqlite_dir(database_url)
    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce ON DELETE CASCADE in SQLite
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def migrate(database_url: str) -> None:
    """Apply all pending migrations (idempotent)."""
    _ensure_sqlite_dir(database_url)
    command.upgrade(alembic_config(database_url), "head")
