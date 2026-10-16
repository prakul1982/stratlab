"""Where users' own data (the main database) lives: Supabase, or Railway's Postgres once it has been moved there.

Supabase's free plan counts every byte the server reads from it, and the server reads users' data all day (profiles,
paper sessions, notebooks, settings): October went past the plan's monthly egress more than twice. On Railway the
database sits next to the server on its private network, so none of that leaves it. Supabase keeps the sign-ins.

The move, once: Admin → Storage → "Move users' data to Railway" marks it wanted (STATE_KEY in the market database)
and restarts the server. Before the new process answers anything, start() copies every table from Supabase into the
`app` schema in one transaction, checks each table's count, and marks the move done in the same transaction; from
then on every start reads and writes there. Nothing is written in between: the old process is gone and the new one
isn't serving yet. If the copy fails, nothing is kept on Railway, the error shows in Admin, and the server carries on
with Supabase; pressing the button again tries again.

MAIN_DATABASE=supabase on the backend forces Supabase (an emergency way back: what was written on Railway since the
move isn't in Supabase)."""
import json
import logging
import os
import time
from datetime import datetime, timezone

from . import db, market_store, pgdb
from .config import settings

log = logging.getLogger("stratlab")

STATE_KEY = "maindb:state"        # {"state": "pending" | "done" | "failed", "asked_at", "done_at", "copied", "error"}
# each table, its key to page by, and rows a read (the big JSON rows in small pages; never over Supabase's 1000-row cap
# on one read); parents before children
COPY = (("profiles", "id", 500), ("strategies", "id", 50), ("usage_events", "id", 1000), ("live_sessions", "id", 25),
        ("live_orders", "id", 1000), ("app_settings", "key", 500), ("option_snapshots", "id", 20))
SEQUENCES = ("usage_events", "live_orders", "option_snapshots")
READ_TRIES, READ_PAUSE = 5, 4.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def forced_supabase() -> bool:
    return os.getenv("MAIN_DATABASE", "").strip().lower() == "supabase"


def state(ms=None) -> dict:
    ms = ms or market_store.store()
    if ms is None:
        return {}
    return db.json_value(ms.get(STATE_KEY), {})


def _set_state(ms, **fields) -> dict:
    s = state(ms)
    s.update(fields)
    ms.set(STATE_KEY, json.dumps(s))
    return s


def request(ms) -> dict:
    """Ask for the move at the next start (the caller restarts the server)."""
    return _set_state(ms, state="pending", asked_at=_now(), error=None)


def status() -> dict:
    """For Admin: where users' data is read from now, and how the move went."""
    out = {"on": "railway" if db.on_railway() else "supabase", "forced": forced_supabase()}
    try:
        out.update({k: v for k, v in state().items() if k != "on"})
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def _read_state(ms) -> dict | None:
    """The move's state, tried a few times (the database may be starting too); None when it can't be read."""
    for i in range(READ_TRIES):
        try:
            return state(ms)
        except Exception as e:
            log.warning("main database: can't read the move's state yet: %s", str(e)[:160])
            if i < READ_TRIES - 1:
                time.sleep(READ_PAUSE)
    return None


def _moved_per_supabase() -> bool:
    try:
        r = db.supabase().table("app_settings").select("value").eq("key", STATE_KEY).limit(1).execute().data
        return bool(r) and db.json_value(r[0]["value"], {}).get("state") == "done"
    except Exception:
        return False


def start() -> str:
    """At startup, before anything reads the database: choose where users' data is, moving it first when asked.
    Returns where it is ("supabase" or "railway")."""
    ms = market_store.store()
    if ms is None or forced_supabase():
        return "supabase"
    st = _read_state(ms)
    if st is None:
        if _moved_per_supabase():       # the data is on Railway, which can't be reached: don't serve Supabase's old copy
            raise RuntimeError("Users' data is on Railway's Postgres, which can't be reached. Starting again shortly.")
        return "supabase"
    if st.get("state") == "done":
        db.use_railway(settings.MARKET_DATABASE_URL)
        return "railway"
    if st.get("state") != "pending":
        return "supabase"
    pg = pgdb.PgClient(settings.MARKET_DATABASE_URL, auth_source=db.supabase)
    began = time.monotonic()
    try:
        copied = move(db.supabase(), pg)
    except Exception as e:
        log.error("main database: the move to Railway failed; staying on Supabase: %s", e)
        try:
            _set_state(ms, state="failed", failed_at=_now(), error=str(e)[:300])
        except Exception:
            pass
        pg.close()
        return "supabase"
    log.warning("main database: moved to Railway in %.0f s: %s", time.monotonic() - began, copied)
    db.use_railway(settings.MARKET_DATABASE_URL, client=pg)
    try:                                 # the same mark in Supabase: a start that can't reach Railway then knows
        db.supabase().table("app_settings").upsert({"key": STATE_KEY, "value": json.dumps({"state": "done", "done_at": _now()}),
                                                    "updated_at": db.now_iso()}).execute()
    except Exception as e:
        log.warning("main database: couldn't leave the moved mark in Supabase: %s", str(e)[:160])
    return "railway"


def _type(v) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "bigint"
    if isinstance(v, float):
        return "double precision"
    if isinstance(v, (dict, list)):
        return "jsonb"
    return "text"


def _columns(c, table: str) -> dict[str, str]:
    rows = c.execute("select column_name, data_type from information_schema.columns where table_schema = %s and table_name = %s",
                     (pgdb.SCHEMA_NAME, table)).fetchall()
    return {n: t for n, t in rows}


def _value(kind: str, v):
    from psycopg.types.json import Jsonb
    if v is None:
        return None
    if kind == "jsonb" or isinstance(v, (dict, list)):
        return Jsonb(v)
    return v


def move(src, pg: "pgdb.PgClient") -> dict:
    """Copy every table from `src` (the Supabase client) into Railway's `app` schema in one transaction, replacing
    whatever a failed try left there, and mark the move done in the same transaction. Raises (and keeps nothing)
    when a read fails or a table's count doesn't match."""
    copied: dict[str, int] = {}
    with pg.connection("job") as c, c.transaction():
        c.execute("set local statement_timeout = 0")
        c.execute("truncate " + ", ".join(f"app.{t}" for t, _, _ in reversed(COPY)))
        for table, key, page in COPY:
            cols = _columns(c, table)
            n, after = 0, None
            while True:
                q = src.table(table).select("*")
                if after is not None:
                    q = q.gt(key, after)
                rows = q.order(key).limit(page).execute().data or []
                for r in rows:                      # a column Supabase has that this schema doesn't: added, by its value
                    for k, v in r.items():
                        if k not in cols:
                            pgdb._ident(k)
                            c.execute(f'alter table app.{table} add column if not exists "{k}" {_type(v)}')
                            cols[k] = _type(v)
                groups: dict[tuple, list] = {}
                for r in rows:
                    groups.setdefault(tuple(r), []).append(r)
                for names, part in groups.items():
                    sql = (f"insert into app.{table} ({', '.join(pgdb._ident(k) for k in names)}) "
                           f"values ({', '.join(['%s'] * len(names))})")
                    with c.cursor() as cur:
                        cur.executemany(sql, [[_value(cols.get(k, ""), r[k]) for k in names] for r in part])
                n += len(rows)
                if not rows:                        # a short page isn't the end: the server may cap what one read returns
                    break
                after = rows[-1][key]
            want = src.table(table).select(key, count="exact").limit(1).execute().count
            if want is not None and want != n:
                raise RuntimeError(f"{table}: Supabase has {want} rows but {n} were read")
            copied[table] = n
        for table in SEQUENCES:
            c.execute(f"select setval(pg_get_serial_sequence('app.{table}', 'id'), coalesce((select max(id) from app.{table}), 0) + 1, false)")
        for table, _, _ in COPY:
            have = c.execute(f"select count(*) from app.{table}").fetchone()[0]
            if have != copied[table]:
                raise RuntimeError(f"{table}: {copied[table]} rows read from Supabase but {have} written")
        done = json.dumps({"state": "done", "done_at": _now(), "copied": copied})
        c.execute("insert into public.app_settings (key, value, updated_at) values (%s, %s, now()) "
                  "on conflict (key) do update set value = excluded.value, updated_at = excluded.updated_at", (STATE_KEY, done))
    return copied
