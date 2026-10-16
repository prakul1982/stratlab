"""The main database on Railway's Postgres: the same query-builder calls the app makes on the Supabase client
(table(...).select/insert/upsert/update/delete, the filters, order, limit, execute), run as SQL through psycopg.

Users' own data lives in the `app` schema of the Postgres that also holds the market data (market_store, in `public`),
so nothing is read across the internet: the server and the database share Railway's private network. Supabase is
still used for sign-in only (auth.get_user and the admin magic link), through `auth`.

Rows come back as PostgREST gives them: timestamps as ISO text, numbers as numbers, JSON columns as Python objects.
A call made while answering an HTTP request that can't get a connection or an answer in time raises
db.DatabaseUnavailable (the API answers 503), as the Supabase client's request lane does."""
import re
import threading
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

SCHEMA_NAME = "app"

SCHEMA = """
create schema if not exists app;
create table if not exists app.profiles (
  id text primary key,
  email text,
  plan text not null default 'free',
  plan_status text,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  razorpay_subscription_id text,
  pending_subscription_id text,
  live_trial_started_at timestamptz,
  alerts_enabled boolean not null default false,
  telegram_chat_id text,
  alert_email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists profiles_sub_idx on app.profiles (razorpay_subscription_id);
create index if not exists profiles_email_idx on app.profiles (email);
create table if not exists app.usage_events (
  id bigserial primary key,
  user_id text not null,
  kind text not null,
  created_at timestamptz not null default now()
);
create index if not exists usage_user_kind_time on app.usage_events (user_id, kind, created_at);
create index if not exists usage_kind_time on app.usage_events (kind, created_at);
create table if not exists app.strategies (
  id text primary key default gen_random_uuid()::text,
  user_id text not null,
  name text not null,
  body jsonb not null,
  instrument_token bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists strategies_user on app.strategies (user_id, updated_at desc);
create table if not exists app.live_sessions (
  id text primary key default gen_random_uuid()::text,
  user_id text not null,
  name text not null,
  strategy jsonb not null,
  instrument jsonb not null,
  status text not null default 'running',
  state jsonb,
  stop_reason text,
  started_at timestamptz not null default now(),
  stopped_at timestamptz
);
create index if not exists live_user on app.live_sessions (user_id, started_at desc);
create index if not exists live_status on app.live_sessions (status);
create table if not exists app.live_orders (
  id bigserial primary key,
  session_id text not null references app.live_sessions(id) on delete cascade,
  user_id text not null,
  side text not null,
  qty integer not null,
  price numeric not null,
  reason text,
  pnl numeric,
  candle_time text,
  ts timestamptz not null default now()
);
create index if not exists orders_session on app.live_orders (session_id, ts desc);
create index if not exists orders_user on app.live_orders (user_id);
create table if not exists app.app_settings (
  key text primary key,
  value text,
  updated_at timestamptz not null default now()
);
create table if not exists app.option_snapshots (
  id bigserial primary key,
  taken_at timestamptz not null,
  exchange text not null,
  name text not null,
  expiry date not null,
  spot double precision,
  lot integer,
  chain jsonb not null
);
create index if not exists option_snapshots_lookup on app.option_snapshots (name, expiry, taken_at);
"""

TABLES = ("profiles", "usage_events", "strategies", "live_sessions", "live_orders", "app_settings", "option_snapshots")
KEY = {"app_settings": "key"}                       # each table's primary key (the rest: id)
JSON_COLS = {"strategies": {"body"}, "live_sessions": {"strategy", "instrument", "state"}, "option_snapshots": {"chain"}}

# The size readout (storage.report): the same shape as Supabase's stratlab_db_usage, for the app schema.
USAGE_SQL = """
select jsonb_build_object(
  'total', (select coalesce(sum(pg_total_relation_size(c.oid)), 0) from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where c.relkind = 'r' and n.nspname = 'app'),
  'tables', (select coalesce(jsonb_agg(jsonb_build_object('name', t.name, 'bytes', t.bytes) order by t.bytes desc), '[]'::jsonb)
             from (select n.nspname || '.' || c.relname as name, pg_total_relation_size(c.oid) as bytes
                   from pg_class c join pg_namespace n on n.oid = c.relnamespace
                   where c.relkind = 'r' and n.nspname = 'app' order by 2 desc limit 12) t),
  'settings', (select coalesce(jsonb_agg(jsonb_build_object('prefix', s.prefix, 'bytes', s.bytes, 'rows', s.n) order by s.bytes desc), '[]'::jsonb)
               from (select split_part(key, ':', 1) as prefix, sum(pg_column_size(value))::bigint as bytes, count(*) as n
                     from app.app_settings group by 1 order by 2 desc limit 15) s))
"""

REQUEST_POOL, REQUEST_WAIT, REQUEST_STATEMENT_MS = 16, 2.0, 8000
JOB_POOL, JOB_WAIT, JOB_STATEMENT_MS = 8, 30.0, 120000

_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def _ident(name: str) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError(f"not a column name: {name!r}")
    return f'"{name}"'


def _table(name: str) -> str:
    if name not in TABLES:
        raise ValueError(f"no such table: {name!r}")
    return f"{SCHEMA_NAME}.{_ident(name)}"


def _column(expr: str) -> tuple[str, str]:
    """One item of a select list as SQL and the name it comes back under: 'id', 'kind:body->>kind',
    'instrument:body->instrument'."""
    expr = expr.strip()
    alias, path = (expr.split(":", 1) if ":" in expr else (None, expr))
    if "->" in path:
        col, rest = path.split("->", 1)
        text = rest.startswith(">")
        key = rest[1:] if text else rest
        sql = f"{_ident(col.strip())}{'->>' if text else '->'}'{_ident(key.strip())[1:-1]}'"
        return sql, (alias or key).strip()
    return _ident(path), (alias or path).strip()


def _out(v):
    """A value as PostgREST would give it in JSON."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and abs(v) < 2 ** 53 else float(v)
    if isinstance(v, UUID):
        return str(v)
    return v


def _row(cur, values) -> dict:
    return {d.name: _out(v) for d, v in zip(cur.description, values)}


class Result(SimpleNamespace):
    """What execute() returns: .data (the rows) and .count (when asked for)."""


class Query:
    def __init__(self, client: "PgClient", table: str):
        self.client, self.table = client, table
        self.op, self.cols, self.count = "select", "*", None
        self.payload, self.ignore, self.returning = None, False, None
        self.where: list[tuple[str, tuple]] = []
        self.orders: list[str] = []
        self._limit: int | None = None
        self.on_conflict: str | None = None

    # ---- building
    def select(self, cols: str = "*", count: str | None = None):
        self.op, self.cols, self.count = "select", cols, count
        return self

    def insert(self, payload, count=None, returning=None):
        self.op, self.payload, self.count, self.returning = "insert", payload, count, returning
        return self

    def upsert(self, payload, ignore_duplicates: bool = False, on_conflict: str | None = None, count=None, returning=None):
        self.op, self.payload, self.ignore, self.on_conflict = "upsert", payload, ignore_duplicates, on_conflict
        self.count, self.returning = count, returning
        return self

    def update(self, payload: dict, count=None, returning=None):
        self.op, self.payload, self.count, self.returning = "update", payload, count, returning
        return self

    def delete(self, count=None, returning=None):
        self.op, self.count, self.returning = "delete", count, returning
        return self

    def _f(self, sql: str, *args):
        self.where.append((sql, args))
        return self

    def eq(self, c, v):
        return self._f(f"{_ident(c)} is null") if v is None else self._f(f"{_ident(c)} = %s", self._arg(c, v))

    def neq(self, c, v):
        return self._f(f"{_ident(c)} is not null") if v is None else self._f(f"{_ident(c)} <> %s", self._arg(c, v))   # as PostgREST: a null is neither

    def gt(self, c, v): return self._f(f"{_ident(c)} > %s", self._arg(c, v))
    def gte(self, c, v): return self._f(f"{_ident(c)} >= %s", self._arg(c, v))
    def lt(self, c, v): return self._f(f"{_ident(c)} < %s", self._arg(c, v))
    def lte(self, c, v): return self._f(f"{_ident(c)} <= %s", self._arg(c, v))
    def like(self, c, p): return self._f(f"{_ident(c)} like %s", p)
    def ilike(self, c, p): return self._f(f"{_ident(c)} ilike %s", p)

    def in_(self, c, values):
        values = list(values)
        if not values:
            return self._f("false")
        return self._f(f"{_ident(c)} = any(%s)", [self._arg(c, v) for v in values])

    def is_(self, c, v):
        if v is None or v == "null":
            return self._f(f"{_ident(c)} is null")
        return self._f(f"{_ident(c)} is {'true' if v in (True, 'true') else 'false'}")

    def order(self, c, desc: bool = False, nullsfirst: bool | None = None):
        sql = f"{_ident(c)} {'desc' if desc else 'asc'}"
        if nullsfirst is not None:
            sql += " nulls first" if nullsfirst else " nulls last"
        self.orders.append(sql)
        return self

    def limit(self, n: int):
        self._limit = int(n)
        return self

    def _arg(self, col: str, v):
        """A filter value: kept as text for Postgres to read in the column's own type (a timestamp, a number)."""
        if isinstance(v, bool) or v is None:
            return v
        if isinstance(v, (int, float, Decimal)):
            return v
        return str(v)

    # ---- SQL
    def _where_sql(self) -> tuple[str, list]:
        if not self.where:
            return "", []
        parts, args = [], []
        for sql, a in self.where:
            parts.append(sql)
            args += list(a)
        return " where " + " and ".join(parts), args

    def _value(self, col: str, v):
        from psycopg.types.json import Jsonb
        if v is None:
            return None             # SQL null, as PostgREST stores a JSON null sent for a column
        if col in JSON_COLS.get(self.table, ()) or isinstance(v, (dict, list)):
            return Jsonb(v)
        return v

    def _returning(self) -> str:
        return "" if self.returning == "minimal" else " returning *"

    def execute(self) -> Result:
        return self.client.run(self)

    def run(self, conn) -> Result:
        t = _table(self.table)
        where, wargs = self._where_sql()
        if self.op == "select":
            cols = self.cols.strip() if self.cols else "*"
            items = ["*"] if cols == "*" else [_column(c) for c in cols.split(",") if c.strip()]
            select = "*" if items == ["*"] else ", ".join(f'{sql} as {_ident(name)}' for sql, name in items)
            sql = f"select {select} from {t}{where}"
            if self.orders:
                sql += " order by " + ", ".join(self.orders)
            if self._limit is not None:
                sql += f" limit {int(self._limit)}"
            cur = conn.execute(sql, wargs)
            data = [_row(cur, r) for r in cur.fetchall()]
            n = None
            if self.count:
                n = conn.execute(f"select count(*) from {t}{where}", wargs).fetchone()[0]
            return Result(data=data, count=n)
        if self.op in ("insert", "upsert"):
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            key = self.on_conflict or KEY.get(self.table, "id")
            with conn.transaction():
                for p in rows:
                    cols = list(p)
                    sql = (f"insert into {t} ({', '.join(_ident(c) for c in cols)}) "
                           f"values ({', '.join(['%s'] * len(cols))})")
                    if self.op == "upsert":
                        rest = [c for c in cols if c != key]
                        if self.ignore or not rest:
                            sql += f" on conflict ({_ident(key)}) do nothing"
                        else:
                            sql += (f" on conflict ({_ident(key)}) do update set "
                                    + ", ".join(f"{_ident(c)} = excluded.{_ident(c)}" for c in rest))
                    sql += self._returning()
                    cur = conn.execute(sql, [self._value(c, p[c]) for c in cols])
                    if self.returning != "minimal":
                        out += [_row(cur, r) for r in cur.fetchall()]
            return Result(data=out, count=len(rows) if self.count else None)
        if self.op == "update":
            cols = list(self.payload)
            if not cols:
                return Result(data=[], count=0 if self.count else None)
            sql = f"update {t} set " + ", ".join(f"{_ident(c)} = %s" for c in cols) + where + self._returning()
            cur = conn.execute(sql, [self._value(c, self.payload[c]) for c in cols] + wargs)
            data = [_row(cur, r) for r in cur.fetchall()] if self.returning != "minimal" else []
            return Result(data=data, count=cur.rowcount if self.count else None)
        if self.op == "delete":
            cur = conn.execute(f"delete from {t}{where}{self._returning()}", wargs)
            data = [_row(cur, r) for r in cur.fetchall()] if self.returning != "minimal" else []
            return Result(data=data, count=cur.rowcount if self.count else None)
        raise ValueError(f"unknown operation {self.op}")


class Call:
    def __init__(self, client: "PgClient", name: str):
        self.client, self.name = client, name

    def execute(self) -> Result:
        if self.name != "stratlab_db_usage":
            raise RuntimeError(f"no such function: {self.name}")
        return self.client.run(self)

    def run(self, conn) -> Result:
        return Result(data=conn.execute(USAGE_SQL).fetchone()[0], count=None)


class PgClient:
    """The Supabase client's query calls over Railway's Postgres. `auth` gives sign-in calls to `auth_source()` (the
    Supabase client), which is only made when a sign-in is checked."""

    def __init__(self, url: str, auth_source=None):
        self.url, self._auth_source = url, auth_source
        self._pools: dict[str, object] = {}
        self._lock = threading.Lock()
        self._ready = False

    @property
    def auth(self):
        if self._auth_source is None:
            raise RuntimeError("no sign-in service")
        return self._auth_source().auth

    def table(self, name: str) -> Query:
        return Query(self, name)

    def rpc(self, name: str, params=None) -> Call:
        return Call(self, name)

    def _pool(self, lane: str):
        p = self._pools.get(lane)
        if p is not None:
            return p
        with self._lock:
            p = self._pools.get(lane)
            if p is None:
                from psycopg_pool import ConnectionPool
                size, wait, ms = ((REQUEST_POOL, REQUEST_WAIT, REQUEST_STATEMENT_MS) if lane == "request"
                                  else (JOB_POOL, JOB_WAIT, JOB_STATEMENT_MS))
                p = ConnectionPool(self.url, min_size=1, max_size=size, timeout=wait, open=True, name=f"main-{lane}",
                                   kwargs={"autocommit": True, "options": f"-c statement_timeout={ms} -c timezone=UTC"})
                if not self._ready:
                    with p.connection() as c:
                        c.execute(SCHEMA)
                    self._ready = True
                self._pools[lane] = p
        return p

    def connection(self, lane: str = "job"):
        """A connection from a lane's pool, as a context manager (for the move's transaction)."""
        return self._pool(lane).connection()

    def run(self, q) -> Result:
        from . import db
        import psycopg
        from psycopg_pool import PoolTimeout
        lane = "request" if db.in_request() else "job"
        reads = isinstance(q, Call) or q.op == "select"
        try:
            try:
                with self._pool(lane).connection() as c:
                    return q.run(c)
            except psycopg.OperationalError as e:
                # a read on a connection that broke (the server restarted, an idle connection was cut) is sent once
                # more on a new one; a write is never sent twice, nor a read that ran out of time
                if not reads or isinstance(e, psycopg.errors.QueryCanceled):
                    raise
                with self._pool(lane).connection() as c:
                    return q.run(c)
        except (PoolTimeout, psycopg.OperationalError) as e:
            if lane == "job":
                raise
            raise db.DatabaseUnavailable(f"Couldn't reach the database ({type(e).__name__})") from e

    def close(self) -> None:
        with self._lock:
            for p in self._pools.values():
                p.close()
            self._pools.clear()
