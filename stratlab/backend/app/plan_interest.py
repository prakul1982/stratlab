"""Who asked to be told when paid plans open ("Tell me when plans open").

While Basic and Pro can't be bought, a locked page or a plan limit has nothing to offer but the wait. This keeps one
small record per person, `plan_interest:<user id>`: when they asked and from where (a lock banner, the Plans page, a
plan limit). Asking twice changes nothing; they can take themselves off the list. Admin shows the count."""
import json
from datetime import datetime, timezone

from . import db

KEY = "plan_interest:"
SOURCES = {"lock", "plans", "limit", "inline"}


def get(uid: str) -> dict:
    """{"registered": bool, "at": ISO time or None} for one person."""
    row = db.json_value(db.get_setting(KEY + uid), {})
    if isinstance(row, dict) and row.get("at"):
        return {"registered": True, "at": row["at"]}
    return {"registered": False, "at": None}


def add(uid: str, source: str = "plans") -> dict:
    """Put the person on the list (their first time stays their time)."""
    have = get(uid)
    if have["registered"]:
        return have
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.set_setting(KEY + uid, json.dumps({"at": at, "source": source if source in SOURCES else "plans"}))
    return {"registered": True, "at": at}


def remove(uid: str) -> dict:
    db.delete_setting(KEY + uid)
    return {"registered": False, "at": None}


def count() -> int:
    """How many people are on the list."""
    return sum(1 for k, v in db.all_settings_with_prefix(KEY) if db.json_value(v, {}).get("at"))
