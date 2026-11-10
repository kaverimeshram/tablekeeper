"""Read-only campaign snapshot route for the Hermes Desktop pane."""
from pathlib import Path
import json
import sqlite3

from fastapi import APIRouter

router = APIRouter()


def _db_path():
    from plugins.plugin_storage import plugin_data_dir
    return plugin_data_dir("tablekeeper") / "campaigns.sqlite3"


@router.get("/campaigns")
def campaigns():
    path = _db_path()
    if not path.exists():
        return {"campaigns": []}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT chat, state FROM campaigns ORDER BY chat").fetchall()
    return {"campaigns": [{"chat": chat, **json.loads(state)} for chat, state in rows]}
