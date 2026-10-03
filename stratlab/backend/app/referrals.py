"""Invite links: every user has a personal link (/?ref=CODE), and a new account that arrived through one remembers
who sent it.

Only tracked for now, with no reward: the owner hasn't decided on one. When they do, it goes in on_referral_joined,
the one place a counted referral lands.

Kept in app_settings, so no new database columns:
  ref:code:{CODE}   -> the id of the user the code belongs to
  ref:user:{uid}    -> that user's code
  ref:by:{uid}      -> who invited this account, and when (written once, never changed)
  ref:joined:{uid}  -> the accounts this user invited, [{id, at}]

Abuse: codes are 12 random characters (about 72 bits), so they can't be guessed; nobody can use their own code (or
one belonging to the same email address); and an account counts once, only in its first day."""
import json
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone

from . import db
from .config import settings

CODE = re.compile(r"^[A-Za-z0-9_-]{12}\Z")          # \Z, not $: "$" would let a trailing newline through
NEW_FOR = timedelta(hours=24)        # an account older than this is not new: it can't be counted as invited
_lock = threading.Lock()             # one server process: two requests from the same newcomer can't both count


def _load(key: str, default):
    try:
        raw = db.get_setting(key)
        return json.loads(raw) if raw else default
    except (ValueError, TypeError):  # a damaged value: as if nothing were stored
        return default


def code_for(uid: str) -> str:
    """The user's invite code, made the first time it's asked for."""
    have = db.get_setting(f"ref:user:{uid}")
    if have and CODE.match(have):
        return have
    with _lock:
        have = db.get_setting(f"ref:user:{uid}")
        if have and CODE.match(have):
            return have
        while True:
            code = secrets.token_urlsafe(9)          # 12 characters
            if not db.get_setting(f"ref:code:{code}"):
                break
        db.set_setting(f"ref:code:{code}", uid)
        db.set_setting(f"ref:user:{uid}", code)
        return code


def owner(code: str | None) -> str | None:
    """Whose code this is; None for anything that isn't a code someone was given."""
    if not isinstance(code, str) or not CODE.match(code):
        return None
    return db.get_setting(f"ref:code:{code}") or None


def link(code: str) -> str:
    return f"{settings.PUBLIC_SITE_URL}/?ref={code}"


def joined(uid: str) -> list[dict]:
    rows = _load(f"ref:joined:{uid}", [])
    return rows if isinstance(rows, list) else []


def counts() -> dict[str, int]:
    """{user id: how many accounts they invited}, for everyone who invited anyone (the admin's Users tab)."""
    out = {}
    for key, raw in db.all_settings_with_prefix("ref:joined:"):
        try:
            rows = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(rows, list) and rows:
            out[key.split(":", 2)[2]] = len(rows)
    return out


def referred_by(uid: str) -> str | None:
    return (_load(f"ref:by:{uid}", {}) or {}).get("by")


def _age(profile: dict, now: datetime) -> timedelta | None:
    try:
        made = datetime.fromisoformat(str(profile["created_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None
    return now - (made if made.tzinfo else made.replace(tzinfo=timezone.utc))


def _mailbox(email: str | None) -> str:
    """An address as the mailbox it reaches: lower case, no +tag, and no dots for Gmail."""
    local, _, domain = (email or "").strip().lower().partition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}" if local and domain else ""


def _profile(uid: str) -> dict | None:
    """A profile by id without making one (db.get_profile would create a missing one)."""
    rows = db.sb().table("profiles").select("*").eq("id", uid).limit(1).execute().data
    return rows[0] if rows else None


def record(newcomer: dict, code: str | None, now: datetime | None = None) -> str:
    """Remember that a new account came through an invite link. Returns what happened: "recorded", or why not
    ("bad_code", "self", "not_new", "already")."""
    now = now or datetime.now(timezone.utc)
    uid = newcomer.get("id")
    ref = owner(code)
    if not uid or not ref:
        return "bad_code"
    if ref == uid:
        return "self"
    referrer = _profile(ref)
    if not referrer:
        return "bad_code"                            # the code's owner deleted their account
    mine = _mailbox(newcomer.get("email"))
    if mine and mine == _mailbox(referrer.get("email")):
        return "self"
    age = _age(newcomer, now)
    if age is None or age > NEW_FOR:
        return "not_new"
    with _lock:
        if db.get_setting(f"ref:by:{uid}"):
            return "already"
        at = now.isoformat(timespec="seconds")
        db.set_setting(f"ref:by:{uid}", json.dumps({"by": ref, "at": at}))
        rows = [r for r in joined(ref) if isinstance(r, dict) and r.get("id") != uid]
        db.set_setting(f"ref:joined:{ref}", json.dumps(rows + [{"id": uid, "at": at}]))
    try:
        on_referral_joined(referrer, newcomer)
    except Exception as e:                           # a reward going wrong must not undo the record
        print("referral reward failed:", str(e)[:160])
    return "recorded"


def on_referral_joined(referrer: dict, newcomer: dict) -> None:
    """Called once when a new account that came through `referrer`'s invite link is counted. Does nothing for now:
    no reward or free plan time is given until the owner decides on one. A reward goes here."""
    return None
