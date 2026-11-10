"""SQLite campaign store: one campaign per chat, WAL, versioned migrations, 0600 files.

Readers (the Desktop route) can run ``SELECT chat, state FROM campaigns`` on a read-only
connection: ``campaigns`` is a view that assembles the full JSON snapshot of each chat.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

KEEP_ROLLS = 50
KEEP_LOG = 50
KEEP_HISTORY = 500

MIGRATIONS = [
    """
    CREATE TABLE chats(
      chat TEXT PRIMARY KEY, gm TEXT NOT NULL DEFAULT '', round INTEGER NOT NULL DEFAULT 0,
      active TEXT NOT NULL DEFAULT '', in_combat INTEGER NOT NULL DEFAULT 0,
      scene TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL);
    CREATE TABLE creatures(
      chat TEXT NOT NULL REFERENCES chats(chat) ON DELETE CASCADE, id TEXT NOT NULL,
      ord INTEGER NOT NULL, data TEXT NOT NULL CHECK(json_valid(data)), PRIMARY KEY(chat, id));
    CREATE TABLE initiative(
      chat TEXT NOT NULL REFERENCES chats(chat) ON DELETE CASCADE, pos INTEGER NOT NULL,
      creature_id TEXT NOT NULL, PRIMARY KEY(chat, pos));
    CREATE TABLE rolls(
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      chat TEXT NOT NULL REFERENCES chats(chat) ON DELETE CASCADE, ts REAL NOT NULL,
      data TEXT NOT NULL CHECK(json_valid(data)));
    CREATE TABLE log(
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      chat TEXT NOT NULL REFERENCES chats(chat) ON DELETE CASCADE, ts REAL NOT NULL,
      kind TEXT NOT NULL, text TEXT NOT NULL);
    CREATE INDEX rolls_chat ON rolls(chat, seq);
    CREATE INDEX log_chat ON log(chat, seq);
    CREATE VIEW campaigns AS SELECT c.chat AS chat, json_object(
      'chat', c.chat, 'gm', c.gm, 'round', c.round, 'active', c.active, 'in_combat', c.in_combat,
      'scene', c.scene, 'updated', c.updated,
      'creatures', json((SELECT json_group_array(json(data)) FROM
                    (SELECT data FROM creatures WHERE chat = c.chat ORDER BY ord))),
      'initiative', json((SELECT json_group_array(creature_id) FROM
                     (SELECT creature_id FROM initiative WHERE chat = c.chat ORDER BY pos))),
      'rolls', json((SELECT json_group_array(json(d)) FROM (SELECT d FROM
                (SELECT seq, json_patch(data, json_object('seq', seq, 'ts', ts)) AS d
                   FROM rolls WHERE chat = c.chat ORDER BY seq DESC LIMIT %d) ORDER BY seq))),
      'log', json((SELECT json_group_array(json(d)) FROM (SELECT d FROM
              (SELECT seq, json_object('seq', seq, 'ts', ts, 'kind', kind, 'text', text) AS d
                 FROM log WHERE chat = c.chat ORDER BY seq DESC LIMIT %d) ORDER BY seq)))
    ) AS state FROM chats c;
    """ % (KEEP_ROLLS, KEEP_LOG),
]


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (creating at mode 0600), enable WAL, and migrate to the current schema."""
    path = Path(path)
    if str(path) != ":memory:" and not path.exists():
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    db = sqlite3.connect(path, check_same_thread=False, timeout=5)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > len(MIGRATIONS):
        db.close()
        raise RuntimeError(f"campaign database is schema v{version}; this Tablekeeper reads up to v{len(MIGRATIONS)}")
    for target in range(version, len(MIGRATIONS)):
        db.executescript(f"BEGIN;{MIGRATIONS[target]};PRAGMA user_version={target + 1};COMMIT;")
    if str(path) != ":memory:":
        os.chmod(path, 0o600)
    return db


def chats(db: sqlite3.Connection) -> list[str]:
    return [r[0] for r in db.execute("SELECT chat FROM chats ORDER BY updated DESC")]


def load(db: sqlite3.Connection, chat: str) -> dict | None:
    """The chat's snapshot (creatures list, initiative ids, recent rolls and log), or None."""
    row = db.execute("SELECT state FROM campaigns WHERE chat=?", (chat,)).fetchone()
    if not row:
        return None
    state = json.loads(row[0])
    state["in_combat"] = bool(state["in_combat"])
    return state


def create(db: sqlite3.Connection, chat: str, gm: str) -> dict:
    """Start an empty campaign for the chat, replacing any previous one."""
    now = time.time()
    with db:
        db.execute("DELETE FROM chats WHERE chat=?", (chat,))
        db.execute("INSERT INTO chats(chat, gm, created, updated) VALUES(?,?,?,?)", (chat, gm, now, now))
    return load(db, chat)


def save(db: sqlite3.Connection, state: dict, *, rolls=(), log=()) -> None:
    """Write the mutable snapshot and append new rolls and log entries in one transaction."""
    chat, now = state["chat"], time.time()
    with db:
        cur = db.execute(
            "UPDATE chats SET gm=?, round=?, active=?, in_combat=?, scene=?, updated=? WHERE chat=?",
            (state["gm"], state["round"], state["active"], int(state["in_combat"]), state["scene"], now, chat))
        if cur.rowcount != 1:
            raise KeyError(f"no campaign for chat {chat!r}")
        db.execute("DELETE FROM creatures WHERE chat=?", (chat,))
        db.executemany("INSERT INTO creatures(chat, id, ord, data) VALUES(?,?,?,?)",
                       [(chat, c["id"], i, json.dumps(c, separators=(",", ":")))
                        for i, c in enumerate(state["creatures"])])
        db.execute("DELETE FROM initiative WHERE chat=?", (chat,))
        db.executemany("INSERT INTO initiative(chat, pos, creature_id) VALUES(?,?,?)",
                       [(chat, i, cid) for i, cid in enumerate(state["initiative"])])
        db.executemany("INSERT INTO rolls(chat, ts, data) VALUES(?,?,?)",
                       [(chat, now, json.dumps(r, separators=(",", ":"))) for r in rolls])
        db.executemany("INSERT INTO log(chat, ts, kind, text) VALUES(?,?,?,?)",
                       [(chat, now, kind, text) for kind, text in log])
        for table in ("rolls", "log"):
            db.execute(f"DELETE FROM {table} WHERE chat=? AND seq NOT IN "
                       f"(SELECT seq FROM {table} WHERE chat=? ORDER BY seq DESC LIMIT {KEEP_HISTORY})", (chat, chat))


def log_entries(db: sqlite3.Connection, chat: str, limit: int = 500) -> list[dict]:
    rows = db.execute("SELECT seq, ts, kind, text FROM log WHERE chat=? ORDER BY seq DESC LIMIT ?", (chat, limit))
    return [dict(seq=s, ts=t, kind=k, text=x) for s, t, k, x in reversed(rows.fetchall())]
