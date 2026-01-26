# db.py
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SQLite (local file). On Render, you can swap to a persistent disk path if needed.
DATABASE_URL = "sqlite:///./data.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
