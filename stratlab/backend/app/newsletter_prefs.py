"""Which newsletters each person gets, and how often: stored in app_settings as newsletters:<uid>."""
import json

from . import db

KEYS = ("market_in", "market_us", "my_stocks")
VALUES = ("daily", "weekly", "off")
PREFIX = KEY = "newsletters:"


def get(uid: str) -> dict:
    """Every newsletter's setting; anything not chosen yet is off."""
    try:
        saved = json.loads(db.get_setting(PREFIX + uid) or "{}")
    except (ValueError, TypeError):
        saved = {}
    saved = saved if isinstance(saved, dict) else {}
    return {k: saved[k] if saved.get(k) in VALUES else "off" for k in KEYS}


def set(uid: str, changes: dict | None = None, **choices) -> dict:
    """Change some settings and return all of them. An unknown newsletter or value raises ValueError. The stored row
    carries the uid, so the sender can list subscribers by prefix."""
    changes = {**(changes or {}), **choices}
    for k, v in changes.items():
        if k not in KEYS:
            raise ValueError(f"Unknown newsletter: {k}")
        if v not in VALUES:
            raise ValueError(f"Choose daily, weekly or off for {k}.")
    prefs = {**get(uid), **changes}
    db.set_setting(PREFIX + uid, json.dumps({"uid": uid, **prefs}))
    return prefs
