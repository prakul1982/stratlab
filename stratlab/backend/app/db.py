"""Supabase access with the service-role key (bypasses RLS, server only)."""
import contextvars
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
import httpx
from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions
from .config import settings
from . import http_retry, market_store
from .flight import Flights

log = logging.getLogger(__name__)

_client: Client | None = None
_client_lock = threading.Lock()

# The database client's own HTTP connection. The library's default is one HTTP/2 connection shared by every thread:
# when the server closes it (an idle timeout, a restart) every request in flight fails with "Server disconnected",
# and two threads using one HTTP/2 stream table at once fail with a bare KeyError (the stream number). HTTP/1.1 keeps a
# pool of connections instead (one request each, safe across threads), and a dropped connection is simply left out.
READ_METHODS = http_retry.READ_METHODS
RETRY_PAUSE = http_retry.RETRY_PAUSE   # seconds before the one retry, so a server that is restarting has a moment


class RetryReads(http_retry.RetryReads):
    """A read that fails because the connection broke is sent once more, on a new connection (app/http_retry.py). A
    write is sent again only when it never left, so nothing is ever saved twice."""

    def _pause(self) -> float:
        return RETRY_PAUSE


def _http() -> httpx.Client:
    # the connection limits belong to the transport: a client given a transport ignores its own `limits`, which is why the
    # 30 s keep-alive once written here never applied (R9R-009); a short one keeps a pooled connection inside the idle timeout
    # of the server at the other end
    return httpx.Client(http2=False, follow_redirects=True, timeout=httpx.Timeout(30.0, connect=10.0),
                        transport=RetryReads(httpx.HTTPTransport(http2=False, limits=httpx.Limits(
                            max_connections=40, max_keepalive_connections=20, keepalive_expiry=http_retry.KEEPALIVE_EXPIRY))))


def sb() -> Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY,
                                        options=SyncClientOptions(httpx_client=_http()))
    return _client


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- profiles ----------
def get_profile(user_id: str, email: str | None = None) -> dict:
    r = sb().table("profiles").select("*").eq("id", user_id).limit(1).execute()
    if r.data:
        return r.data[0]
    # insert only when absent: a row another request made meanwhile (a payment, a plan change) is never overwritten
    sb().table("profiles").upsert({"id": user_id, "email": email, "plan": "free"}, ignore_duplicates=True).execute()
    return sb().table("profiles").select("*").eq("id", user_id).limit(1).execute().data[0]


def find_profile(user_id: str) -> dict | None:
    """A profile by id, or None: unlike get_profile, a missing one (a deleted account) is never made."""
    rows = sb().table("profiles").select("*").eq("id", user_id).limit(1).execute().data
    return rows[0] if rows else None


# Signed-in requests read the profile on every call (a paper page polls every 3 s), so keep it for a few
# seconds. Every change goes through update_profile, which drops the copy, and the server runs one process.
PROFILE_TTL = 10.0
_profiles: dict[str, tuple[float, dict]] = {}
_profiles_lock = threading.Lock()
_profile_flights = Flights()
_profile_versions: dict[str, int] = {}       # bumped by forget_profile: a read begun before a change isn't kept


def cached_profile(user_id: str, email: str | None = None) -> dict:
    now = time.monotonic()
    with _profiles_lock:
        hit = _profiles.get(user_id)
    if hit and hit[0] > now:
        return dict(hit[1])
    # a page's dozen calls at once each need the profile: the first reads it, the others wait and find it kept (R9R-010)
    with _profile_flights.hold(user_id):
        with _profiles_lock:
            hit = _profiles.get(user_id)
        if hit and hit[0] > time.monotonic():
            return dict(hit[1])
        with _profiles_lock:
            seen = _profile_versions.get(user_id, 0)
        row = get_profile(user_id, email)
        with _profiles_lock:
            if len(_profiles) > 5000:
                _profiles.clear()
            if _profile_versions.get(user_id, 0) == seen:       # no update_profile since the read began
                _profiles[user_id] = (time.monotonic() + PROFILE_TTL, dict(row))
    return dict(row)


def forget_profile(user_id: str) -> None:
    with _profiles_lock:
        _profiles.pop(user_id, None)
        if len(_profile_versions) > 5000:
            _profile_versions.clear()
        _profile_versions[user_id] = _profile_versions.get(user_id, 0) + 1


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
    return paged(lambda: sb().table("profiles").select("*"), page)


def pages(query, page: int = 1000):
    """A query's rows one page at a time by id (the server caps one read), each page a list, so a caller that only
    totals or forwards them never holds them all; `query()` gives a fresh one selecting at least id."""
    after = ""
    while True:
        q = query()
        if after:
            q = q.gt("id", after)
        rows = q.order("id").limit(page).execute().data
        if rows:
            yield rows
        if len(rows) < page:
            return
        after = rows[-1]["id"]


def paged(query, page: int = 1000) -> list[dict]:
    """Every row of a query, read a page at a time by id (the server caps one read); `query()` gives a fresh one
    selecting at least id."""
    return [r for rows in pages(query, page) for r in rows]


def profile_by_subscription(sub_id: str) -> dict | None:
    r = sb().table("profiles").select("*").eq("razorpay_subscription_id", sub_id).limit(1).execute()
    return r.data[0] if r.data else None


# ---------- usage ----------
def count_usage(user_id: str, kind: str, since_iso: str) -> int:
    r = (sb().table("usage_events").select("id", count="exact")       # the count only: one row, not every one
         .eq("user_id", user_id).eq("kind", kind).gte("created_at", since_iso).limit(1).execute())
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


def has_strategy(user_id: str) -> bool:
    """Whether the user has any notebook or saved strategy (one row is enough to know)."""
    return bool(sb().table("strategies").select("id").eq("user_id", user_id).limit(1).execute().data)


def delete_strategy(user_id: str, sid: str) -> None:
    sb().table("strategies").delete().eq("user_id", user_id).eq("id", sid).execute()


# ---------- live sessions ----------
def create_session(row: dict) -> dict:
    return sb().table("live_sessions").insert(row).execute().data[0]


def update_session(sid: str, **fields) -> None:
    sb().table("live_sessions").update(fields).eq("id", sid).execute()


def stop_running_session(sid: str, reason: str) -> bool:
    """Mark a running session's row stopped (the leader, which runs it, follows the database); False when it isn't running."""
    rows = (sb().table("live_sessions").update({"status": "stopped", "stopped_at": now_iso(), "stop_reason": reason})
            .eq("id", sid).eq("status", "running").execute().data)
    return bool(rows)


def stop_user_sessions(user_id: str, reason: str) -> None:
    """Mark every running session of a user's stopped, wherever it runs."""
    (sb().table("live_sessions").update({"status": "stopped", "stopped_at": now_iso(), "stop_reason": reason}, returning="minimal")
     .eq("user_id", user_id).eq("status", "running").execute())


def running_sessions() -> list[dict]:
    return sb().table("live_sessions").select("*").eq("status", "running").execute().data


def running_index() -> list[dict]:
    """Every running session's id, owner and status: the light read a reconcile makes every half minute."""
    return sb().table("live_sessions").select("id,user_id,status").eq("status", "running").execute().data


def sessions_by_ids(ids: list[str]) -> list[dict]:
    """The full rows (state and all) of these sessions, those still running."""
    ids = [i for i in ids if isinstance(i, str)]
    if not ids:
        return []
    return sb().table("live_sessions").select("*").eq("status", "running").in_("id", ids).execute().data or []


def count_running(user_id: str) -> int:
    """How many sessions the user has running (one light read, for the plan limit)."""
    return len(sb().table("live_sessions").select("id").eq("user_id", user_id).eq("status", "running").execute().data or [])


def stopped_among(ids: list[str]) -> set[str]:
    """Which of these sessions are stored as anything but running (one light read, for Admin's count)."""
    ids = [i for i in ids if isinstance(i, str)]
    if not ids:
        return set()
    rows = sb().table("live_sessions").select("id,status").in_("id", ids[:500]).execute().data or []
    return {r["id"] for r in rows if r.get("status") != "running"}


def user_sessions(user_id: str, limit: int = 20, running: bool = True) -> list[dict]:
    """The user's newest `limit` sessions, newest first. With `running`, every running one too, however old: a page
    that lists only the newest would hide a session that is still trading (and counting against the plan's limit)."""
    cols = "id,name,instrument,status,started_at,stopped_at,stop_reason"
    rows = sb().table("live_sessions").select(cols).eq("user_id", user_id).order("started_at", desc=True).limit(limit).execute().data
    if running:
        have = {r["id"] for r in rows}
        older = (sb().table("live_sessions").select(cols).eq("user_id", user_id).eq("status", "running")
                 .order("started_at", desc=True).execute().data)
        extra = [r for r in older if r["id"] not in have]
        if extra:
            rows = sorted(rows + extra, key=lambda r: str(r.get("started_at") or ""), reverse=True)
    return rows


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


# One request reads the same setting several times (a user's preferences four times in /me, each holding's corporate
# actions twice in the tax report), and every read is a round trip to the database. Within a request each key is read
# once: SettingsMemo gives each request its own copy. Any write in this process, from any thread, drops the key from
# every request's copy, and a read that overlapped a write isn't kept, so a request never sees an older value than
# it would have read from the database.
_memo: contextvars.ContextVar[dict | None] = contextvars.ContextVar("settings_memo", default=None)
_memos: dict[int, dict] = {}            # every running request's copy, so a write can reach them all
_memo_lock = threading.Lock()
_writes = [0]                           # how many writes so far: a read that saw this change isn't kept


def _forget_setting(key: str) -> None:
    with _memo_lock:
        _writes[0] += 1
        for m in _memos.values():
            m.pop(key, None)


def _remember(memo: dict, key: str, value, mark: int) -> None:
    with _memo_lock:
        if _writes[0] == mark:
            memo[key] = value


class SettingsMemo:
    """ASGI middleware: one database read per setting key per request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        memo: dict = {}
        with _memo_lock:
            _memos[id(memo)] = memo
        token = _memo.set(memo)
        try:
            await self.app(scope, receive, send)
        finally:
            _memo.reset(token)
            with _memo_lock:
                _memos.pop(id(memo), None)


def _read_setting(key: str) -> str | None:
    if _mirrored(key):
        rows = _mirror_rows(_mirrored(key), wait=False)
        if rows is not None:
            return rows.get(key)
        # no copy yet (warm_caches reads it at startup): this one key from the database, not the whole prefix
    ms = _market(key)
    if ms is not None:
        v = ms.get(key)
        if v is not None:
            return v
    r = sb().table("app_settings").select("value").eq("key", key).limit(1).execute()
    return r.data[0]["value"] if r.data else None


def get_setting(key: str) -> str | None:
    memo = _memo.get()
    if memo is None:
        return _read_setting(key)
    if key in memo:
        return memo[key]
    mark = _writes[0]
    v = _read_setting(key)
    _remember(memo, key, v, mark)
    return v


def prefetch_settings(keys) -> None:
    """Read several settings in one database call, for the rest of this request (outside a request it does nothing).
    For a page that reads one key per holding: one round trip instead of one per holding. Keys kept in the market
    data store are left to get_setting."""
    memo = _memo.get()
    if memo is None:
        return
    want = sorted({k for k in keys if k not in memo and _market(k) is None and not _mirrored(k)})
    for i in range(0, len(want), 100):                  # keeps the address of one read short
        part, mark = want[i:i + 100], _writes[0]
        try:
            rows = sb().table("app_settings").select("key,value").in_("key", part).execute().data or []
        except Exception:               # only a head start: each read then goes (and fails) as it would have
            return
        got = {r["key"]: r["value"] for r in rows}
        for k in part:
            _remember(memo, k, got.get(k), mark)


def set_setting(key: str, value: str) -> None:
    try:
        ms = _market(key)
        if ms is not None:
            ms.set(key, value)
        else:
            sb().table("app_settings").upsert({"key": key, "value": value, "updated_at": now_iso()}).execute()
        _mirror_put(key, value)
    finally:
        _forget_setting(key)


REMOVE = object()                       # what an update_setting function returns to delete the row


class SettingConflict(RuntimeError):
    """A setting kept changing under update_setting for every try."""


def _is_duplicate(e: Exception) -> bool:
    return getattr(e, "code", None) == "23505" or "duplicate key" in str(e)


def _swap(key: str, new, stamp: str | None) -> bool:
    """Write `new` (REMOVE: delete) only if the row is still the one read: absent when `stamp` is None, else with that
    updated_at. False when another writer got in first."""
    t = now_iso()
    if t == stamp:                      # the clock didn't move between two writes: the stamp must still change
        t = (_instant(t) + timedelta(microseconds=1)).isoformat()
    tbl = sb().table("app_settings")
    if stamp is None:
        if new is REMOVE:
            return True
        try:
            tbl.insert({"key": key, "value": new, "updated_at": t}).execute()
        except Exception as e:
            if _is_duplicate(e):
                return False
            raise
        return True
    q = tbl.delete() if new is REMOVE else tbl.update({"value": new, "updated_at": t})
    return bool(q.eq("key", key).eq("updated_at", stamp).execute().data)


def update_setting(key: str, fn, tries: int = 10) -> str | None:
    """Change a setting atomically: fn(current text or None) returns the new text, None to leave it, or REMOVE.
    Returns what the setting holds afterwards. The main database is reached over REST, with no transaction to hold
    a lock in, so this is a compare-and-set on the row's updated_at: if another writer changed the row since it was
    read, fn runs again on the new value (so keep it free of side effects). Keys in the second database use a
    transaction with the row locked instead."""
    try:
        ms = _market(key)
        if ms is not None:
            def locked(cur):            # a value not moved over yet is still read from the main database
                return fn(cur if cur is not None else _read_setting_main(key))
            new = ms.update(key, locked)
            _mirror_put(key, new)
            return new
        for _ in range(tries):
            r = sb().table("app_settings").select("value,updated_at").eq("key", key).limit(1).execute().data
            old, stamp = (r[0]["value"], r[0]["updated_at"]) if r else (None, None)
            new = fn(old)
            if new is None:
                return old
            if _swap(key, new, stamp):
                new = None if new is REMOVE else new
                _mirror_put(key, new)
                return new
        raise SettingConflict(key)
    finally:
        _forget_setting(key)


def _read_setting_main(key: str) -> str | None:
    r = sb().table("app_settings").select("value").eq("key", key).limit(1).execute()
    return r.data[0]["value"] if r.data else None


def delete_setting(key: str) -> None:
    try:
        ms = _market(key)
        if ms is not None:
            ms.delete(key)
            _mirror_put(key, None)          # gone from the second database even if the main one's delete fails next
        sb().table("app_settings").delete().eq("key", key).execute()
        _mirror_put(key, None)
    finally:
        _forget_setting(key)


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
    if _mirrored(prefix):
        rows = _mirror_rows(_mirrored(prefix))
        with _mirror_lock:                  # a write from another thread would change the dict mid-way through
            items = [(k, v) for k, v in rows.items() if k.startswith(prefix)]
        return sorted(items)
    return _all_from_db(prefix, page)


def _all_from_db(prefix: str, page: int = 1000) -> list[tuple[str, str]]:
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


# ---------- settings kept in memory ----------
# The stored company pages ("stocks:", some 15,000 rows and 25 MB) are read whole by the screens index (twice a region
# every half hour), by the price refresh after each close (once a minute while it has a backlog) and by the sitemaps,
# and one at a time by every page view, crawlers' included. Read from the database each time, that was gigabytes a
# day out of it, over the free plan's monthly egress. One process writes them all (railway.json: one replica, one
# worker), so they're read once, kept here, and changed here as this process writes them. A full read again every few
# hours picks up anything written elsewhere (another instance during a deploy's overlap).
MIRRORED = ("stocks:",)
MIRROR_FOR = 6 * 3600
MIRROR_RETRY = 60                       # seconds after a failed background read before the next one is tried
_mirror: dict = {}                      # prefix -> {"at": monotonic time read, "client": id of the client, "rows": {key: value}}
_mirror_lock = threading.Lock()         # guards _mirror, _mirror_log, _mirror_reloading and _mirror_retry_at
_mirror_loading = threading.Lock()      # one full read at a time
_mirror_log: dict | None = None         # while a full read runs: the writes made meanwhile, laid over it when it lands
_mirror_reloading: set = set()          # prefixes with a background read under way
_mirror_retry_at: dict = {}             # prefix -> monotonic time before which a failed background read isn't tried again


def _mirrored(key_or_prefix: str) -> str | None:
    return next((p for p in MIRRORED if key_or_prefix.startswith(p)), None)


def _mirror_usable(m: dict | None) -> bool:
    return bool(m) and m["client"] == id(sb())


def _mirror_fresh(m: dict | None) -> bool:
    return _mirror_usable(m) and time.monotonic() - m["at"] < MIRROR_FOR


def _mirror_rows(prefix: str, wait: bool = True) -> dict | None:
    """Every setting under a mirrored prefix, read from the database at most once every MIRROR_FOR seconds. A copy past
    that age is still served while one background thread reads the prefix again (a read that fails keeps the copy and
    is logged), so no request waits on the full read. With no copy at all: wait=True reads it now (one read at a
    time, the others wait for it); wait=False returns None, for a caller that needs one key and reads it itself."""
    with _mirror_lock:
        m = _mirror.get(prefix)
        if _mirror_usable(m):
            if time.monotonic() - m["at"] >= MIRROR_FOR:
                _start_reload(prefix)
            return m["rows"]
    if not wait:
        return None
    return _load_mirror(prefix)


def _load_mirror(prefix: str, since: float | None = None) -> dict:
    """Read the prefix whole into the copy, unless a copy read at or after `since` (None: any copy) is there by the time
    this read's turn comes. Raises when the read fails, leaving the copy there was."""
    global _mirror_log
    with _mirror_loading:
        with _mirror_lock:
            m = _mirror.get(prefix)
            if _mirror_usable(m) and (since is None or m["at"] >= since):
                return m["rows"]
            _mirror_log = {}
        client = id(sb())
        try:
            rows = dict(_all_from_db(prefix))
        except Exception:
            with _mirror_lock:
                _mirror_log = None
            raise
        with _mirror_lock:
            for k, v in (_mirror_log or {}).items():          # written while the read was on its way: the write is newer
                if k.startswith(prefix):
                    if v is None:
                        rows.pop(k, None)
                    else:
                        rows[k] = v
            _mirror_log = None
            _mirror[prefix] = {"at": time.monotonic(), "client": client, "rows": rows}
        return rows


def _start_reload(prefix: str, force: bool = False) -> None:
    """One background read of the prefix at a time (call with _mirror_lock held)."""
    if prefix in _mirror_reloading or (not force and time.monotonic() < _mirror_retry_at.get(prefix, 0)):
        return
    _mirror_reloading.add(prefix)
    threading.Thread(target=_reload, args=(prefix, time.monotonic()), daemon=True, name="settings-mirror").start()


def _reload(prefix: str, since: float) -> None:
    try:
        _load_mirror(prefix, since)
        with _mirror_lock:
            _mirror_retry_at.pop(prefix, None)
    except Exception as e:
        log.error("settings mirror: could not read %s again; still serving the copy there was: %s", prefix, e)
        with _mirror_lock:
            _mirror_retry_at[prefix] = time.monotonic() + MIRROR_RETRY
    finally:
        with _mirror_lock:
            _mirror_reloading.discard(prefix)


def warm_mirror() -> None:
    """Read every mirrored prefix now (at startup, so no request pays for it)."""
    for p in MIRRORED:
        _mirror_rows(p)


def reload_mirror() -> None:
    """Read every mirrored prefix again in the background, serving the copy there is meanwhile (on taking the lease: to
    pick up what the old container wrote since this one booted)."""
    with _mirror_lock:
        for p in MIRRORED:
            _start_reload(p, force=True)


def _mirror_put(key: str, value: str | None) -> None:
    """A write this process made to a mirrored key (None: deleted), into the copy and into any full read under way."""
    p = _mirrored(key)
    if not p:
        return
    with _mirror_lock:
        if _mirror_log is not None:
            _mirror_log[key] = value
        m = _mirror.get(p)
        if m is not None:
            if value is None:
                m["rows"].pop(key, None)
            else:
                m["rows"][key] = value


def forget_mirror() -> None:
    """Drop the in-memory copies (the next read goes to the database)."""
    with _mirror_lock:
        _mirror.clear()
        _mirror_retry_at.clear()


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
