"""Database engine, session factory, and base model."""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/ai_recruiter"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# Lazy engine — only created when first accessed.
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        engine_kwargs = {
            "pool_pre_ping": True,
            "echo": os.getenv("SQL_ECHO", "").lower() in ("1", "true"),
        }
        if database_url.startswith(("postgresql://", "postgresql+")):
            engine_kwargs.update(
                {
                    "pool_size": int(os.getenv("PG_POOL_SIZE", "2")),
                    "max_overflow": int(os.getenv("PG_MAX_OVERFLOW", "2")),
                    "pool_timeout": int(os.getenv("PG_POOL_TIMEOUT_SECONDS", "5")),
                    "connect_args": {
                        "connect_timeout": int(
                            os.getenv("PG_CONNECT_TIMEOUT_SECONDS", "3")
                        )
                    },
                }
            )
        _engine = create_engine(database_url, **engine_kwargs)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


def SessionLocal() -> Session:
    """Create a new database session."""
    return get_session_factory()()
