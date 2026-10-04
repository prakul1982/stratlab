"""Supabase access with the service-role key (bypasses RLS, server only)."""
import json
import threading
import time
from datetime import datetime, timezone
from supabase import create_client, Client
from .config import settings
from . import market_store

_client: Client | None = None


def sb() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- profiles ----------
def get_profile(user_id: str, email: str | None = None) -> dict:
    r = sb().table("profiles").select("*").eq("id", user_id).limit(1).execute()
    if r.data:
        return r.data[0]
    return sb().table("profiles").upsert({"id": user_id, "email": email, "plan": "free"}).execute().data[0]


# Signed-in requests read the profile on every call (a paper page polls every 3 s), so keep it for a few
# seconds. Every change goes through update_profile, which drops the copy, and the server runs one process.
PROFILE_TTL = 10.0
_profiles: dict[str, tuple[float, dict]] = {}
_profiles_lock = threading.Lock()


def cached_profile(user_id: str, email: str | None = None) -> dict:
    now = time.monotonic()
    with _profiles_lock:
        hit = _profiles.get(user_id)
    if hit and hit[0] > now:
        return dict(hit[1])
    row = get_profile(user_id, email)
    with _profiles_lock:
        if len(_profiles) > 5000:
            _profiles.clear()
        _profiles[user_id] = (now + PROFILE_TTL, dict(row))
    return dict(row)


def forget_profile(user_id: str) -> None:
    with _profiles_lock:
        _profiles.pop(user_id, None)


def update_profile(user_id: str, **fields) -> dict:
    fields["updated_at"] = now_iso()
    forget_profile(user_id)
    try:
        rows = sb().table("profiles").update(fields).eq("id", user_id).execute().data
        return rows[0] if rows else None      # no such user
    finally:
        forget_profile(user_id)   # also drop a copy a request re-read while the update ran


def all_profiles(page: int = 1000) -> list[dict]:
    """Every profile, read a page at a time by id (the server caps one read)."""
    out, after = [], ""
    while True:
        q = sb().table("profiles").select("*")
        if after:
            q = q.gt("id", after)
        rows = q.order("id").limit(page).execute().data
        out += rows
        if len(rows) < page:
            return out
        after = rows[-1]["id"]


def profile_by_subscription(sub_id: str) -> dict | None:
    r = sb().table("profiles").select("*").eq("razorpay_subscription_id", sub_id).limit(1).execute()
    return r.data[0] if r.data else None


# ---------- usage ----------
def count_usage(user_id: str, kind: str, since_iso: str) -> int:
    r = (sb().table("usage_events").select("id", count="exact")
         .eq("user_id", user_id).eq("kind", kind).gte("created_at", since_iso).execute())
    return r.count or 0


def usage_times(user_id: str, kind: str, since_iso: str, until_iso: str, limit: int = 500) -> list[str]:
    """When each of a user's events of one kind happened, between two times."""
    r = (sb().table("usage_events").select("created_at").eq("user_id", user_id).eq("kind", kind)
         .gte("created_at", since_iso).lt("created_at", until_iso).limit(limit).execute())
    return [x["created_at"] for x in r.data if x.get("created_at")]


def add_usage(user_id: str, kind: str) -> None:
    sb().table("usage_events").insert({"user_id": user_id, "kind": kind}).execute()


# ---------- strategies ----------
def get_strategy(user_id: str, sid: str) -> dict | None:
    r = sb().table("strategies").select("*").eq("user_id", user_id).eq("id", sid).limit(1).execute()
    return r.data[0] if r.data else None


def save_strategy(user_id: str, name: str, body: dict, token: int | None, sid: str | None = None) -> dict | None:
    row = {"user_id": user_id, "name": name, "body": body, "instrument_token": token, "updated_at": now_iso()}
    if sid:
        r = sb().table("strategies").update(row).eq("user_id", user_id).eq("id", sid).execute()
        return r.data[0] if r.data else None
    return sb().table("strategies").insert(row).execute().data[0]


def list_notebook_rows(user_id: str) -> list[dict]:
    """Notebook list without the (large) experiment history."""
    return (sb().table("strategies")
            .select("id,name,instrument_token,updated_at,kind:body->>kind,question:body->>question,"
                    "instrument:body->instrument,summary:body->summary,tf:body->>tf,pinned:body->>pinned,group:body->group")
            .eq("user_id", user_id).order("updated_at", desc=True).execute().data)


def delete_strategy(user_id: str, sid: str) -> None:
    sb().table("strategies").delete().eq("user_id", user_id).eq("id", sid).execute()


# ---------- live sessions ----------
def create_session(row: dict) -> dict:
    return sb().table("live_sessions").insert(row).execute().data[0]


def update_session(sid: str, **fields) -> None:
    sb().table("live_sessions").update(fields).eq("id", sid).execute()


def running_sessions() -> list[dict]:
    return sb().table("live_sessions").select("*").eq("status", "running").execute().data


def user_sessions(user_id: str, limit: int = 20) -> list[dict]:
    return (sb().table("live_sessions")
            .select("id,name,instrument,status,started_at,stopped_at,stop_reason")
            .eq("user_id", user_id).order("started_at", desc=True).limit(limit).execute().data)


def get_session_row(user_id: str, sid: str) -> dict | None:
    r = sb().table("live_sessions").select("*").eq("user_id", user_id).eq("id", sid).limit(1).execute()
    return r.data[0] if r.data else None


def delete_session(user_id: str, sid: str) -> None:
    """Remove one of the user's sessions; its orders go with it (on delete cascade)."""
    sb().table("live_sessions").delete().eq("user_id", user_id).eq("id", sid).neq("status", "running").execute()


def delete_stopped_sessions(user_id: str) -> int:
    r = sb().table("live_sessions").delete().eq("user_id", user_id).neq("status", "running").execute()
    return len(r.data or [])


def add_order(row: dict) -> None:
    sb().table("live_orders").insert(row).execute()


# ---------- app settings (Kite token) ----------
def json_value(raw, default):
    """A stored JSON value, or `default` when it's missing, damaged or not the same kind (a dict, a list…)."""
    try:
        v = json.loads(raw or "null")
    except (ValueError, TypeError):
        return default
    return v if isinstance(v, type(default)) else default


# Market-wide data (market_store.MARKET_PREFIXES and the option chains) goes to the second database once
# MARKET_DATABASE_URL is set; until it's all been moved, whatever isn't there yet is still read from this one.
def _market(key: str):
    ms = market_store.store()
    return ms if ms is not None and market_store.is_market_key(key) else None


def get_setting(key: str) -> str | None:
    ms = _market(key)
    if ms is not None:
        v = ms.get(key)
        if v is not None:
            return v
    r = sb().table("app_settings").select("value").eq("key", key).limit(1).execute()
    return r.data[0]["value"] if r.data else None


def set_setting(key: str, value: str) -> None:
    ms = _market(key)
    if ms is not None:
        ms.set(key, value)
        return
    sb().table("app_settings").upsert({"key": key, "value": value, "updated_at": now_iso()}).execute()


def delete_setting(key: str) -> None:
    ms = _market(key)
    if ms is not None:
        ms.delete(key)
    sb().table("app_settings").delete().eq("key", key).execute()


# ---------- recorded option chains ----------
def add_option_snapshot(row: dict) -> None:
    ms = market_store.store()
    if ms is not None:
        ms.add_snapshot(row)
        return
    sb().table("option_snapshots").insert(row).execute()


def delete_option_snapshots_before(iso: str) -> None:
    ms = market_store.store()
    if ms is not None:
        ms.delete_snapshots_before(iso)
    sb().table("option_snapshots").delete().lt("taken_at", iso).execute()


def option_snapshots(name: str, since: str, until: str, limit: int = 12) -> list[dict]:
    """An underlying's recorded chains taken from `since` to before `until` (ISO times), newest first, at most `limit`."""
    ms = market_store.store()
    got = ms.snapshots(name, since, until, limit) if ms is not None else []
    if len(got) >= limit:
        return got
    r = (sb().table("option_snapshots").select("taken_at,expiry,spot,chain").eq("name", name)
         .gte("taken_at", since).lt("taken_at", until).order("taken_at", desc=True).limit(limit).execute())
    if not got:
        return r.data or []
    seen = {_instant(x["taken_at"]) for x in got}
    rows = got + [x for x in (r.data or []) if _instant(x["taken_at"]) not in seen]
    return sorted(rows, key=lambda x: _instant(x["taken_at"]), reverse=True)[:limit]


def _instant(iso: str) -> datetime:
    t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def settings_with_prefix(prefix: str, limit: int = 1000) -> list[str]:
    ms = market_store.store()
    if ms is not None and market_store.touches_prefix(prefix):
        r = (sb().table("app_settings").select("key,value,updated_at").like("key", prefix + "%")
             .order("updated_at", desc=True).limit(limit).execute())
        rows = {k: (t, v) for k, v, t in ms.with_prefix(prefix, limit)}
        for x in r.data:
            rows.setdefault(x["key"], (_instant(x["updated_at"]).isoformat(), x["value"]))
        return [v for _, v in sorted(rows.values(), key=lambda tv: _instant(tv[0]), reverse=True)[:limit]]
    r = (sb().table("app_settings").select("value").like("key", prefix + "%")
         .order("updated_at", desc=True).limit(limit).execute())
    return [x["value"] for x in r.data]


def all_settings_with_prefix(prefix: str, page: int = 1000) -> list[tuple[str, str]]:
    """(key, value) for every setting under a prefix, read a page at a time by key (the server caps one read)."""
    out, after = [], ""
    while True:
        q = sb().table("app_settings").select("key,value").like("key", prefix + "%")
        if after:
            q = q.gt("key", after)
        rows = q.order("key").limit(page).execute().data
        out += [(r["key"], r["value"]) for r in rows]
        if len(rows) < page:
            break
        after = rows[-1]["key"]
    ms = market_store.store()
    if ms is not None and market_store.touches_prefix(prefix):
        merged = dict(out)
        merged.update(ms.all_with_prefix(prefix))      # the second database's copy is the newer one
        out = sorted(merged.items())
    return out


# ---------- size ----------
def usage() -> dict | None:
    """The main database's size, its biggest tables and the biggest groups of settings, from the stratlab_db_usage
    function in supabase/schema.sql; None while that function hasn't been created."""
    try:
        r = sb().rpc("stratlab_db_usage").execute()
    except Exception as e:
        if "stratlab_db_usage" in str(e) or "PGRST202" in str(e) or "42883" in str(e):
            return None
        raise
    return r.data if isinstance(r.data, dict) else None
