"""Read-only campaign routes behind the Tablekeeper Desktop pane.

Hermes loads this file by path as ``hermes_dashboard_plugin_tablekeeper``, so the plugin's own
``store.py`` is loaded the same way instead of through a relative import. Every handler opens the
campaign database with ``mode=ro`` and ``query_only``; the router declares GET routes only.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

DB_NAME = "campaigns.sqlite3"
SUMMARY_LIMIT = 50

router = APIRouter()
_store = None


def _store_module():
    global _store
    if _store is None:
        path = Path(__file__).resolve().parent.parent / "store.py"
        spec = importlib.util.spec_from_file_location("tablekeeper_dashboard_store", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _store = module
    return _store


def _open_readonly():
    """A read-only connection to this profile's campaign database, or None before the first campaign."""
    from plugins.plugin_storage import plugin_data_dir

    path = plugin_data_dir("tablekeeper") / DB_NAME
    if not path.exists():
        return None
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=2)
    db.execute("PRAGMA query_only=ON")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    supported = len(_store_module().MIGRATIONS)
    if version > supported:
        db.close()
        raise HTTPException(503, f"campaign database is schema v{version}; this Tablekeeper reads up to v{supported}")
    if version == 0:
        db.close()
        return None
    return db


def _summary(state: dict) -> dict:
    return {
        "chat": state["chat"], "scene": state["scene"], "round": state["round"],
        "in_combat": state["in_combat"], "updated": state["updated"], "creatures": len(state["creatures"]),
    }


@router.get("/campaigns")
def campaigns():
    """One summary per chat, most recently played first."""
    db = _open_readonly()
    if db is None:
        return {"campaigns": []}
    store = _store_module()
    with closing(db):
        return {"campaigns": [_summary(store.load(db, chat)) for chat in store.chats(db)[:SUMMARY_LIMIT]]}


@router.get("/campaign")
def campaign(chat: str | None = Query(None, max_length=256)):
    """The full snapshot for ``chat``, or for the most recently played chat when omitted."""
    db = _open_readonly()
    if db is None:
        return {"campaign": None}
    store = _store_module()
    with closing(db):
        if chat is None:
            known = store.chats(db)
            state = store.load(db, known[0]) if known else None
        else:
            state = store.load(db, chat)
    if state is None:
        raise HTTPException(404, "No campaign for that chat")
    pending = state.get("pending_throw")
    state["pending_throw"] = ({"character": pending["character"], "owner": pending["owner_name"],
                               "kind": pending["kind"],
                               "seconds_left": max(0, int(pending["created_at"] + state.get("phone_timeout", 120)
                                                            - time.time()))} if pending else None)
    return {"campaign": state}
