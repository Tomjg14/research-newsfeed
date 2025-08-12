import os
from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DB_PATH = os.environ.get("NEWSFEED_DB", "data/newsfeed.db")

@dataclass
class User:
    id: int
    email: str

def get_engine() -> Engine:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return create_engine(f"sqlite:///{DB_PATH}", future=True)

def ensure_schema(engine: Engine) -> None:
    with engine.begin() as con:
        con.execute(text("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""))
        con.execute(text("""
        CREATE TABLE IF NOT EXISTS user_sources(
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            PRIMARY KEY(user_id, source),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );"""))
        con.execute(text("""
        CREATE TABLE IF NOT EXISTS user_settings(
            user_id INTEGER PRIMARY KEY,
            hours_default INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );"""))

def upsert_user(engine: Engine, email: str) -> User:
    with engine.begin() as con:
        con.execute(text("INSERT OR IGNORE INTO users(email) VALUES(:email)"), {"email": email})
        row = con.execute(text("SELECT id, email FROM users WHERE email=:email"), {"email": email}).first()
        return User(id=row[0], email=row[1])

def get_user(engine: Engine, email: str) -> Optional[User]:
    with engine.begin() as con:
        row = con.execute(text("SELECT id, email FROM users WHERE email=:email"), {"email": email}).first()
        return User(id=row[0], email=row[1]) if row else None

def set_user_sources(engine: Engine, user_id: int, sources: List[str]) -> None:
    sources = list(set(sources))
    with engine.begin() as con:
        con.execute(text("DELETE FROM user_sources WHERE user_id=:uid"), {"uid": user_id})
        for s in sources:
            con.execute(text("INSERT INTO user_sources(user_id, source) VALUES(:uid,:s)"), {"uid": user_id, "s": s})

def get_user_sources(engine: Engine, user_id: int) -> List[str]:
    with engine.begin() as con:
        rows = con.execute(text("SELECT source FROM user_sources WHERE user_id=:uid"), {"uid": user_id}).all()
        return [r[0] for r in rows]

def set_user_hours_default(engine: Engine, user_id: int, hours: int) -> None:
    with engine.begin() as con:
        con.execute(text("""
        INSERT INTO user_settings(user_id, hours_default)
        VALUES(:uid, :h)
        ON CONFLICT(user_id) DO UPDATE SET hours_default=excluded.hours_default
        """), {"uid": user_id, "h": hours})

def get_user_hours_default(engine: Engine, user_id: int) -> Optional[int]:
    with engine.begin() as con:
        row = con.execute(text("SELECT hours_default FROM user_settings WHERE user_id=:uid"), {"uid": user_id}).first()
        return int(row[0]) if row and row[0] is not None else None

def list_supported_sources(cfg) -> List[str]:
    return sorted(list(cfg.get("sources", {}).keys()))
