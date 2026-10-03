#!/usr/bin/env python3
"""Reset and re-seed the demo database: python scripts/seed_db.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.db import SessionLocal, init_db  # noqa: E402
from app.seed import reset_demo  # noqa: E402

init_db()
with SessionLocal() as db:
    print("Seeded:", reset_demo(db))
