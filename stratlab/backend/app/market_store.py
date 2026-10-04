"""A second database for the bulky market-wide data, so the main one (logins, users' own data) stays small.

Off until MARKET_DATABASE_URL is set (a Postgres on Railway: Railway → New → Database → PostgreSQL, then
MARKET_DATABASE_URL = ${{Postgres.DATABASE_URL}} on the backend). Then the settings under MARKET_PREFIXES and the
recorded option chains are written here, and read here first: anything not moved yet is still read from the main
database, so turning it on loses nothing. move() copies what's already in the main database across and deletes it there.

Only market data that every user shares lives here (whole-market checks, breadth history, stored company reads,
corporate actions, option chains). Users' own data and payments stay in the main database, which is backed up nightly.
"""
import json
import threading
from datetime import datetime, timezone

from .config import settings

# app_settings keys that hold market-wide data: big, shared by every user, and rebuilt by the server's own jobs
MARKET_PREFIXES = (
    "audit:", "deep:", "breadth:hist:", "breadth:sectors:", "breadth:members:", "corpact:cal:", "corpact:hist:",
    "deals:", "results:cal:", "surv:", "screens:index:", "screens:known:", "fmv2018:", "fxhist:", "mfnav:", "isin:",
    "pos:", "holidays-auto:", "mfter:",
)

SCHEMA = """
create table if not exists app_settings (
  key text primary key,
  value text,
  updated_at timestamptz not null default now()
);
create table if not exists option_snapshots (
  id bigserial primary key,
  taken_at timestamptz not null,
  exchange text not null,
  name text not null,
  expiry date not null,
  spot double precision,
  lot integer,
  chain jsonb not null
);
create index if not exists option_snapshots_lookup on option_snapshots (name, expiry, taken_at);
create index if not exists option_snapshots_taken on option_snapshots (taken_at);
"""

SNAP_COLS = ("taken_at", "exchange", "name", "expiry", "spot", "lot", "chain")


def is_market_key(key: str) -> bool:
    return key.startswith(MARKET_PREFIXES)


def covers_prefix(prefix: str) -> bool:
    """A prefix whose keys all live here (an exact market prefix or narrower)."""
    return prefix.startswith(MARKET_PREFIXES)


def touches_prefix(prefix: str) -> bool:
    """A prefix some of whose keys may live here (e.g. "breadth:" spans market history and users' alerts)."""
    return covers_prefix(prefix) or any(p.startswith(prefix) for p in MARKET_PREFIXES)


class Store:
    """Postgres through psycopg, one small pool. Every call opens nothing new once the pool is warm."""

    def __init__(self, url: str):
        self.url = url
        self._pool = None
        self._lock = threading.Lock()

    def pool(self):
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    from psycopg_pool import ConnectionPool
                    p = ConnectionPool(self.url, min_size=1, max_size=4, timeout=20, kwargs={"autocommit": True},
                                       open=True, name="market")
                    with p.connection() as c:
                        c.execute(SCHEMA)
                    self._pool = p
        return self._pool

    def _run(self, sql: str, args=(), fetch: bool = False):
        with self.pool().connection() as c:
            cur = c.execute(sql, args)
            return cur.fetchall() if fetch else None

    # ---- key/value
    def get(self, key: str) -> str | None:
        rows = self._run("select value from app_settings where key = %s", (key,), fetch=True)
        return rows[0][0] if rows else None

    def set(self, key: str, value: str) -> None:
        self._run("insert into app_settings (key, value, updated_at) values (%s, %s, now()) "
                  "on conflict (key) do update set value = excluded.value, updated_at = excluded.updated_at", (key, value))

    def set_many(self, rows: list[tuple[str, str]]) -> None:
        if not rows:
            return
        with self.pool().connection() as c, c.transaction(), c.cursor() as cur:
            cur.executemany("insert into app_settings (key, value, updated_at) values (%s, %s, now()) "
                            "on conflict (key) do update set value = excluded.value, updated_at = excluded.updated_at", rows)

    def delete(self, key: str) -> None:
        self._run("delete from app_settings where key = %s", (key,))

    def with_prefix(self, prefix: str, limit: int = 1000) -> list[tuple[str, str, str]]:
        """(key, value, updated_at ISO) under a prefix, newest first."""
        rows = self._run("select key, value, updated_at from app_settings where key like %s escape '\\' "
                         "order by updated_at desc limit %s", (_like(prefix), limit), fetch=True)
        return [(k, v, t.isoformat()) for k, v, t in rows]

    def all_with_prefix(self, prefix: str) -> list[tuple[str, str]]:
        return [(k, v) for k, v in self._run("select key, value from app_settings where key like %s escape '\\' order by key",
                                              (_like(prefix),), fetch=True)]

    # ---- option chains
    def add_snapshot(self, row: dict) -> None:
        self.add_snapshots([row])

    def add_snapshots(self, rows: list[dict]) -> None:
        if not rows:
            return
        vals = [tuple(json.dumps(r.get(k)) if k == "chain" else r.get(k) for k in SNAP_COLS) for r in rows]
        with self.pool().connection() as c, c.transaction(), c.cursor() as cur:     # all or none, so a retry never doubles
            cur.executemany(f"insert into option_snapshots ({', '.join(SNAP_COLS)}) values (%s, %s, %s, %s, %s, %s, %s::jsonb)", vals)

    def delete_snapshots_before(self, iso: str) -> None:
        self._run("delete from option_snapshots where taken_at < %s", (iso,))

    def snapshots(self, name: str, since: str, until: str, limit: int = 12) -> list[dict]:
        rows = self._run("select taken_at, expiry, spot, chain from option_snapshots where name = %s and taken_at >= %s "
                         "and taken_at < %s order by taken_at desc limit %s", (name, since, until, limit), fetch=True)
        return [{"taken_at": t.isoformat(), "expiry": e.isoformat(), "spot": s, "chain": ch} for t, e, s, ch in rows]

    # ---- size
    def usage(self) -> dict:
        total = self._run("select pg_database_size(current_database())", fetch=True)[0][0]
        tables = self._run("select c.relname, pg_total_relation_size(c.oid) from pg_class c join pg_namespace n on "
                           "n.oid = c.relnamespace where c.relkind = 'r' and n.nspname = 'public' order by 2 desc", fetch=True)
        return {"total": int(total), "tables": [{"name": n, "bytes": int(b)} for n, b in tables]}


def _like(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


_store: Store | None = None
_store_url = ""


def store() -> Store | None:
    """The second database, or None while MARKET_DATABASE_URL isn't set."""
    global _store, _store_url
    url = (settings.MARKET_DATABASE_URL or "").strip()
    if not url:
        return None
    if _store is None or _store_url != url:
        _store, _store_url = Store(url), url
    return _store


def use(s) -> None:
    """Swap in a store (tests)."""
    global _store, _store_url
    _store, _store_url = s, (settings.MARKET_DATABASE_URL or "").strip()


# ---------- moving what's already in the main database ----------
STATUS_KEY = "marketstore:move"          # in the main database: {"running", "started_at", "finished_at", "moved", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def move(main, target: Store, batch: int = 200) -> dict:
    """Copy every market setting and recorded option chain from the main database (db's Supabase client) into the
    second one, deleting each batch from the main one only once it's safely written there. Safe to run again: a
    copy that stops halfway resumes where it stopped."""
    moved = {"settings": 0, "snapshots": 0}
    sb = main.sb()
    for prefix in MARKET_PREFIXES:
        after = ""
        while True:
            q = sb.table("app_settings").select("key,value").like("key", prefix + "%")
            if after:
                q = q.gt("key", after)
            rows = q.order("key").limit(batch).execute().data or []
            if not rows:
                break
            have = {}
            for r in rows:     # a newer value already written here wins over the old copy
                have[r["key"]] = target.get(r["key"])
            target.set_many([(r["key"], r["value"]) for r in rows if have[r["key"]] is None])
            sb.table("app_settings").delete().in_("key", [r["key"] for r in rows]).execute()
            moved["settings"] += len(rows)
            after = rows[-1]["key"]
    while True:
        rows = (sb.table("option_snapshots").select("id," + ",".join(SNAP_COLS)).order("id").limit(batch).execute().data or [])
        if not rows:
            break
        target.add_snapshots(rows)
        sb.table("option_snapshots").delete().in_("id", [r["id"] for r in rows]).execute()     # exactly what was copied
        moved["snapshots"] += len(rows)
    return moved
