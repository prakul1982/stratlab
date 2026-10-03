"""Which newsletters each person gets, and how often: stored in app_settings as newsletters:<uid>."""
import json

from . import db

KEY = "newsletters:"
CHOICES = ("market_in", "market_us", "my_stocks")
VALUES = ("daily", "weekly", "off")
DEFAULTS = {k: "off" for k in CHOICES}


def get(uid: str) -> dict:
    """{"market_in", "market_us", "my_stocks"}: each "daily", "weekly" or "off" (the default)."""
    try:
        raw = json.loads(db.get_setting(KEY + uid) or "{}")
    except (ValueError, TypeError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    return {k: raw.get(k) if raw.get(k) in VALUES else DEFAULTS[k] for k in CHOICES}


def set(uid: str, **choices) -> dict:
    """Change some choices; unknown keys and values are ignored. Returns the saved choices."""
    prefs = {**get(uid), **{k: v for k, v in choices.items() if k in CHOICES and v in VALUES}}
    db.set_setting(KEY + uid, json.dumps({"uid": uid, **prefs}))
    return prefs
