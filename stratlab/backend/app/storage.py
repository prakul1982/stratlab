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


MB = 1024 * 1024


def railway_link() -> str:
    """Where the owner sees the Railway Postgres volume's size and disk use: the project, when Railway says which."""
    pid = (settings.RAILWAY_PROJECT_ID or "").strip()
    return f"https://railway.com/project/{pid}" if pid else "https://railway.com/dashboard"


def supabase_link() -> str:
    """Supabase's own usage page for the project (its ref is the first part of SUPABASE_URL's host)."""
    import re
    m = re.match(r"https?://([a-z0-9]+)\.supabase\.co", (settings.SUPABASE_URL or "").strip())
    return f"https://supabase.com/dashboard/project/{m[1]}/settings/usage" if m else "https://supabase.com/dashboard"


def _meter(name: str, used: int | None, limit: int | None, link: str, **extra) -> dict:
    return {"name": name, "used": used, "limit": limit, "share": round(used / limit, 3) if used is not None and limit else None,
            "link": link, **extra}


def report() -> dict:
    """The sizes Admin shows (DJ-020): `databases`, one meter per real database against its own real limit: Railway's
    Postgres (users' data and market data once moved; its limit is the volume's, known only when RAILWAY_VOLUME_MB is
    set, else a link to Railway) and Supabase (sign-ins, and users' data until moved; DB_LIMIT_MB, the plan's limit),
    with what Supabase still holds from before the move. `total`, `tables` and `settings` are the main database's."""
    limit = settings.DB_LIMIT_MB * MB
    from . import maindb, pgdb
    moved = db.on_railway()
    out: dict = {"limit": limit, "warn_at": WARN_AT, "market": {"enabled": market_store.store() is not None},
                 "move": {**db.json_value(db.get_setting(market_store.STATUS_KEY), {}), "running": _moving.locked()},
                 "users": maindb.status(), "main": "railway" if moved else "supabase"}
    try:
        u = db.usage()
    except Exception as e:
        u, out["error"] = None, str(e)[:200]
    if u is None:
        out["missing"] = "error" not in out and not moved
        out["sql"] = usage_sql()
    else:
        out.update(total=int(u.get("total") or 0), tables=u.get("tables") or [], settings=u.get("settings") or [])
        out["share"] = round(out["total"] / limit, 3) if limit and not moved else None
    ms = market_store.store()
    if ms is not None:
        try:
            out["market"].update(ms.usage())
        except Exception as e:
            out["market"]["error"] = str(e)[:200]
    dbs = []
    if ms is not None:
        # the whole Railway database (users' data in `app`, market data in `public`), by Postgres's own count
        vol = settings.RAILWAY_VOLUME_MB * MB or None
        dbs.append(_meter("Railway Postgres", out["market"].get("total"), vol, railway_link(), error=out["market"].get("error"),
                          note=None if vol else "The volume's size and disk use are shown on Railway."))
    if moved:
        # users' data is on Railway: Supabase holds the sign-ins, plus the tables copied across, which stay until removed
        try:
            r = db.supabase().rpc("stratlab_db_usage").execute()
            su = r.data if isinstance(r.data, dict) else None
        except Exception as e:
            su, su_error = None, str(e)[:200]
        else:
            su_error = None if su else "Supabase's size function isn't set up."
        left = [t for t in (su or {}).get("tables") or [] if t.get("name") in {f"public.{x}" for x in pgdb.TABLES}]
        dbs.append(_meter("Supabase", int(su["total"]) if su and su.get("total") is not None else None, limit, supabase_link(),
                          error=su_error, reclaimable=sum(int(t.get("bytes") or 0) for t in left) or None,
                          reclaimable_tables=[t["name"] for t in left]))
    elif u is not None:
        dbs.append(_meter("Supabase", out["total"], limit, supabase_link()))
    out["databases"] = dbs
    return out


def _mb(n: int) -> str:
    """As Admin's storage panel writes it: one decimal under 10 MB (one figure on both pages, DJ-020)."""
    v = n / MB
    return f"{v:,.1f} MB" if v < 10 else f"{v:,.0f} MB"


def check() -> dict:
    """The daily check's line: the same figures as Admin's storage panel (DJ-020); warns at 80% of a database's limit,
    fails at 95%, and says what to do."""
    r = report()
    if r.get("error"):
        raise RuntimeError("Couldn't read the database's size: " + r["error"])
    if r.get("missing"):
        return {"name": "Database space", "area": "Server", "state": "warn", "seconds": None,
                "detail": "The size check isn't set up: copy the SQL from Admin → Data and jobs → Storage into Supabase's SQL editor once."}
    state, parts, high = "pass", [], None
    for d in r["databases"]:
        if d.get("used") is None:
            parts.append(f"{d['name']}: size not read{' (' + d['error'] + ')' if d.get('error') else ''}.")
            continue
        line = f"{d['name']}: {_mb(d['used'])}"
        line += f" of {_mb(d['limit'])} used ({d['share']:.0%})" if d.get("limit") else " used (the volume's size is on Railway)"
        if d.get("reclaimable"):
            line += f", {_mb(d['reclaimable'])} of it copies left from before the move"
        parts.append(line + ".")
        if d.get("share") is not None and d["share"] >= WARN_AT:
            state = "fail" if d["share"] >= FAIL_AT or state == "fail" else "warn"
            high = d["name"]
    detail = " ".join(parts)
    if high == "Supabase" and r["main"] == "supabase":
        detail += (" Move the market data to the second database: Admin → Data and jobs → Storage." if r["market"]["enabled"]
                   else " Add a Postgres on Railway and set MARKET_DATABASE_URL, then move the market data (Admin → Data and jobs → Storage).")
    elif high:
        detail += f" {high} is getting full: see its own dashboard."
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
