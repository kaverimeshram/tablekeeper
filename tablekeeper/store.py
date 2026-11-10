"""SQLite campaign state, scoped to Hermes plugin data."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS campaigns(chat TEXT PRIMARY KEY, state TEXT NOT NULL);
    """)
    return db


def load(db: sqlite3.Connection, chat: str) -> dict:
    row = db.execute("SELECT state FROM campaigns WHERE chat=?", (chat,)).fetchone()
    if row:
        return json.loads(row["state"])
    state = {"characters": {}, "monsters": [], "initiative": [], "round": 0, "turn": 0, "rolls": [], "log": []}
    save(db, chat, state)
    return state


def save(db: sqlite3.Connection, chat: str, state: dict) -> None:
    db.execute("INSERT INTO campaigns(chat,state) VALUES(?,?) ON CONFLICT(chat) DO UPDATE SET state=excluded.state",
               (chat, json.dumps(state, separators=(",", ":"))))
    db.commit()
