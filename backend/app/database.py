"""Database engine/session setup. SQLite by default, PostgreSQL via DATABASE_URL."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

SERVERLESS = bool(os.getenv("VERCEL"))
# On Vercel only /tmp is writable, and it is wiped between instances: fine for a demo, but set
# DATABASE_URL to a hosted Postgres (e.g. Neon) to keep accounts, trips and city guides.
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ("sqlite:////tmp/travelsphere.db" if SERVERLESS else "sqlite:///./travelsphere.db")
if DATABASE_URL.startswith("postgres://"):  # Heroku-style URLs
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# Serverless instances freeze between requests, so don't hold pooled connections open.
_pool_args = {"poolclass": NullPool} if SERVERLESS else {"pool_pre_ping": True}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_pool_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    Base.metadata.create_all(bind=engine)
