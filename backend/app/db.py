"""Database setup. SQLite by default; any SQLAlchemy URL works via DATABASE_URL."""
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'reclaim.db'}")
AI_MODE = os.getenv("AI_MODE", "demo")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}
    if DATABASE_URL in ("sqlite://", "sqlite:///:memory:"):
        _kwargs["poolclass"] = StaticPool
else:
    _kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(drop: bool = False):
    from . import models  # noqa: F401
    if DATABASE_URL.startswith("sqlite:///") and ":memory:" not in DATABASE_URL:
        Path(DATABASE_URL.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
