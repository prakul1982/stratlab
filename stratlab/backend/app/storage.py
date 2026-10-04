"""How full the databases are, for Admin's storage panel and the daily check, and the job that moves the bulky
market data to the second database (market_store)."""
import json
import threading

from . import db, market_store
from .config import settings

WARN_AT = 0.8         # the share of the limit at which Admin and the daily check warn
FAIL_AT = 0.95
# The SQL that creates the size function, for Admin to show with a copy button: the same as in supabase/schema.sql
# between the usage-function markers (a test keeps the two equal), kept here as the server is deployed without that folder.
USAGE_SQL = """-- The database's size, its biggest tables and the biggest groups of settings, for Admin's storage panel and the
-- daily check. Server only (the service role); nobody signed in can call it.
create or replace function public.stratlab_db_usage() returns jsonb
language sql stable security definer set search_path = public, pg_catalog as $$
  select jsonb_build_object(
    'total', pg_database_size(current_database()),
    'tables', (select coalesce(jsonb_agg(jsonb_build_object('name', t.name, 'bytes', t.bytes) order by t.bytes desc), '[]'::jsonb)
               from (select n.nspname || '.' || c.relname as name, pg_total_relation_size(c.oid) as bytes
                     from pg_class c join pg_namespace n on n.oid = c.relnamespace
                     where c.relkind = 'r' and n.nspname in ('public', 'auth', 'storage')
                     order by 2 desc limit 12) t),
    'settings', (select coalesce(jsonb_agg(jsonb_build_object('prefix', s.prefix, 'bytes', s.bytes, 'rows', s.n) order by s.bytes desc), '[]'::jsonb)
                 from (select split_part(key, ':', 1) as prefix, sum(pg_column_size(value))::bigint as bytes, count(*) as n
                       from public.app_settings group by 1 order by 2 desc limit 15) s)
  )
$$;
revoke all on function public.stratlab_db_usage() from public, anon, authenticated;
grant execute on function public.stratlab_db_usage() to service_role;"""


def usage_sql() -> str:
    return USAGE_SQL


def report() -> dict:
    limit = settings.DB_LIMIT_MB * 1024 * 1024
    out: dict = {"limit": limit, "warn_at": WARN_AT, "market": {"enabled": market_store.store() is not None},
                 "move": {**db.json_value(db.get_setting(market_store.STATUS_KEY), {}), "running": _moving.locked()}}
    try:
        u = db.usage()
    except Exception as e:
        u, out["error"] = None, str(e)[:200]
    if u is None:
        out["missing"] = "error" not in out
        out["sql"] = usage_sql()
    else:
        out.update(total=int(u.get("total") or 0), tables=u.get("tables") or [], settings=u.get("settings") or [])
        out["share"] = round(out["total"] / limit, 3) if limit else None
    ms = market_store.store()
    if ms is not None:
        try:
            out["market"].update(ms.usage())
        except Exception as e:
            out["market"]["error"] = str(e)[:200]
    return out


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:,.0f} MB"


def check() -> dict:
    """The daily check's line: warns at 80% of the limit, fails at 95%, and says what to do."""
    r = report()
    if r.get("error"):
        raise RuntimeError("Couldn't read the database's size: " + r["error"])
    if r.get("missing"):
        return {"name": "Database space", "area": "Server", "state": "warn", "seconds": None,
                "detail": "The size check isn't set up: copy the SQL from Admin → Data checks → Storage into Supabase's SQL editor once."}
    share, state = r["share"], "pass"
    detail = f"{_mb(r['total'])} of {_mb(r['limit'])} used ({share:.0%})."
    if share >= WARN_AT:
        state = "fail" if share >= FAIL_AT else "warn"
        detail += (" Move the market data to the second database: Admin → Data checks → Storage." if r["market"]["enabled"]
                   else " Add a Postgres on Railway and set MARKET_DATABASE_URL, then move the market data (Admin → Data checks → Storage).")
    if r["market"].get("error"):
        state, detail = "fail", detail + " The second database can't be reached: " + r["market"]["error"]
    return {"name": "Database space", "area": "Server", "state": state, "detail": detail, "seconds": None}


# ---------- moving the market data ----------
_moving = threading.Lock()


def start_move() -> bool:
    """Start the move in the background; False if one is already running or there's no second database."""
    ms = market_store.store()
    if ms is None or not _moving.acquire(blocking=False):
        return False
    _status(running=True, started_at=_now(), error=None)

    def work():
        try:
            moved = market_store.move(db, ms)
            _status(running=False, finished_at=_now(), moved=moved)
        except Exception as e:
            print("market data move failed:", str(e)[:200])
            _status(running=False, finished_at=_now(), error=str(e)[:200])
        finally:
            _moving.release()
    threading.Thread(target=work, daemon=True, name="market-move").start()
    return True


def _status(**fields) -> None:
    s = db.json_value(db.get_setting(market_store.STATUS_KEY), {})
    s.update(fields)
    db.set_setting(market_store.STATUS_KEY, json.dumps(s))


def _now() -> str:
    return market_store._now()
