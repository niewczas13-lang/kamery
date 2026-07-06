from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import ensure_runtime_dirs, load_settings


class Base(DeclarativeBase):
    pass


# Columns added after the first production deploy; create_all() does not alter
# existing tables, so they are backfilled with ALTER TABLE on SQLite.
_CAMERA_SOURCE_COLUMNS = {
    "rtsp_source_host": "VARCHAR(260)",
    "rtsp_source_username": "VARCHAR(160)",
    "rtsp_source_password_secret_ref": "VARCHAR(160)",
    "rtsp_source_main_path": "VARCHAR(260)",
    "rtsp_source_sub_path": "VARCHAR(260)",
    "rtsp_source_secondary_main_path": "VARCHAR(260)",
    "rtsp_source_secondary_sub_path": "VARCHAR(260)",
}


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or load_settings().database_url
    if url.startswith("sqlite:///"):
        ensure_runtime_dirs()
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(database_engine: Engine | None = None) -> None:
    from . import models  # noqa: F401

    bind = database_engine or engine
    Base.metadata.create_all(bind=bind)
    _apply_sqlite_column_migrations(bind)


def _apply_sqlite_column_migrations(bind: Engine) -> None:
    if bind.dialect.name != "sqlite":
        return
    with bind.begin() as connection:
        existing = {row[1] for row in connection.execute(text("PRAGMA table_info(cameras)"))}
        if not existing:
            return
        for column, ddl_type in _CAMERA_SOURCE_COLUMNS.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE cameras ADD COLUMN {column} {ddl_type}"))


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
