from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import ensure_runtime_dirs, load_settings


class Base(DeclarativeBase):
    pass


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

    Base.metadata.create_all(bind=database_engine or engine)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
