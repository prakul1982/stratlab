"""An in-memory stand-in for the Supabase client: the query-builder calls app/db.py and app/admin.py make, plus
auth.get_user for sign-in tokens. Lets the whole app run, signed in, with no database."""
import copy
import fnmatch
import threading
import uuid
from types import SimpleNamespace

USERS = {
    **{f"load-{i}": (f"u-load-{i}", f"load{i}@example.com", ("free", "basic", "pro")[i % 3]) for i in range(300)},
    "free-token": ("u-free", "free@example.com", "free"),
    "basic-token": ("u-basic", "basic@example.com", "basic"),
    "pro-token": ("u-pro", "pro@example.com", "pro"),
    "email-signup-admin-token": ("u-imposter", "owner@example.com", "free"),   # the admin's address, but by email sign-up
    "admin-token": ("u-admin", "owner@example.com", "pro"),
}


def _instants(a, b):
    """Two timestamps compared as the database does: as moments, not as text. 19:00 UTC on 31 March is after the start of
    1 April in India (00:00+05:30), though as text it sorts before it. Anything that isn't a pair of timestamps compares as is."""
    from datetime import datetime, timezone
    try:
        x, y = datetime.fromisoformat(a), datetime.fromisoformat(b)
    except (TypeError, ValueError):
        return a, b
    if (x.tzinfo is None) != (y.tzinfo is None):
        return a, b
    return (x, y) if x.tzinfo else (x.replace(tzinfo=timezone.utc), y.replace(tzinfo=timezone.utc))


def _get(row: dict, path: str):
    """'body->>kind' or 'body->instrument' or a plain column."""
    if "->" not in path:
        return row.get(path)
    col, _, rest = path.partition("->")
    rest = rest.lstrip(">")
    v = row.get(col)
    return v.get(rest) if isinstance(v, dict) else None


def _project(row: dict, cols: str) -> dict:
    if cols.strip() in ("*", ""):
        return copy.deepcopy(row)
    out = {}
    for part in cols.split(","):
        part = part.strip()
        alias, _, path = part.partition(":") if ":" in part else (part, "", part)
        out[alias] = copy.deepcopy(_get(row, path))
    return out


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, []
        self.op, self.cols, self.count, self.payload = "select", "*", None, None
        self._order, self._limit, self.returning = None, None, None

    # building
    def select(self, cols="*", count=None):
        self.op, self.cols, self.count = "select", cols, count
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload, ignore_duplicates=False, on_conflict=None):
        self.op, self.payload, self.ignore, self.on_conflict = "upsert", payload, ignore_duplicates, on_conflict
        return self

    def update(self, payload, count=None, returning=None):
        self.op, self.payload, self.count, self.returning = "update", payload, count, returning
        return self

    def delete(self, count=None, returning=None):
        """returning="minimal": no rows come back; count="exact": how many were removed, as .count."""
        self.op, self.count, self.returning = "delete", count, returning
        return self

    def _f(self, fn):
        self.filters.append(fn)
        return self

    def eq(self, c, v): return self._f(lambda r: r.get(c) == v)
    def neq(self, c, v): return self._f(lambda r: r.get(c) != v)
    def gte(self, c, v): return self._f(lambda r: r.get(c) is not None and (lambda p: p[0] >= p[1])(_instants(r.get(c), v)))
    def gt(self, c, v): return self._f(lambda r: r.get(c) is not None and (lambda p: p[0] > p[1])(_instants(r.get(c), v)))
    def lte(self, c, v): return self._f(lambda r: r.get(c) is not None and (lambda p: p[0] <= p[1])(_instants(r.get(c), v)))
    def lt(self, c, v): return self._f(lambda r: r.get(c) is not None and (lambda p: p[0] < p[1])(_instants(r.get(c), v)))
    def in_(self, c, vs): return self._f(lambda r, vs=set(vs): r.get(c) in vs)
    def like(self, c, p): return self._f(lambda r: fnmatch.fnmatchcase(str(r.get(c) or ""), p.replace("%", "*")))
    def ilike(self, c, p): return self._f(lambda r: fnmatch.fnmatch(str(r.get(c) or "").lower(), p.lower().replace("%", "*")))

    def order(self, c, desc=False):
        self._order = (c, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    # running
    def execute(self):
        if self.db.fail:
            raise self.db.fail
        with self.db.lock:
            rows = self.db.tables.setdefault(self.table, [])
            match = [r for r in rows if all(f(r) for f in self.filters)]
            if self.op == "insert":
                if self.table == "app_settings":      # key is the primary key
                    from postgrest.exceptions import APIError
                    for p in (self.payload if isinstance(self.payload, list) else [self.payload]):
                        if any(r.get("key") == p.get("key") for r in rows):
                            raise APIError({"message": 'duplicate key value violates unique constraint "app_settings_pkey"',
                                            "code": "23505"})
                new = [self._fill(p) for p in (self.payload if isinstance(self.payload, list) else [self.payload])]
                rows += new
                return SimpleNamespace(data=copy.deepcopy(new), count=None)
            if self.op == "upsert":
                key = getattr(self, "on_conflict", None) or ("key" if self.table == "app_settings" else "id")
                out = []
                for p in self.payload if isinstance(self.payload, list) else [self.payload]:
                    old = next((r for r in rows if r.get(key) == p.get(key)), None)
                    if old and getattr(self, "ignore", False):     # ON CONFLICT DO NOTHING: no row comes back
                        continue
                    if old:
                        old.update(copy.deepcopy(p))
                        out.append(old)
                    else:
                        r = self._fill(p)
                        rows.append(r)
                        out.append(r)
                return SimpleNamespace(data=copy.deepcopy(out), count=None)
            if self.op == "update":
                for r in match:
                    r.update(copy.deepcopy(self.payload))
                return self._answer(match)
            if self.op == "delete":
                self.db.tables[self.table] = [r for r in rows if r not in match]
                return self._answer(match)
            if self._order:
                c, desc = self._order
                match.sort(key=lambda r: (r.get(c) is None, str(r.get(c))), reverse=desc)
            n = len(match)
            if self._limit is not None:
                match = match[: self._limit]
            return SimpleNamespace(data=[_project(r, self.cols) for r in match], count=n if self.count else None)

    def _answer(self, match):
        """What a write answers: the rows, or with returning="minimal" none of them; the count when asked for."""
        return SimpleNamespace(data=[] if self.returning == "minimal" else copy.deepcopy(match),
                               count=len(match) if self.count else None)

    def _fill(self, p):
        """Column defaults, as in supabase/schema.sql."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        r = copy.deepcopy(p)
        if self.table not in ("app_settings", "blog_posts"):       # these two are keyed by "key" and "slug"
            r.setdefault("id", str(uuid.uuid4()))
        if self.table != "blog_posts":
            r.setdefault("created_at", now)
        else:
            r.setdefault("indexable", True)
            r.setdefault("published", True)
        if self.table in ("profiles", "strategies", "app_settings"):
            r.setdefault("updated_at", now)
        if self.table == "profiles":
            r.setdefault("plan", "free")
            r.setdefault("cancel_at_period_end", False)
            r.setdefault("alerts_enabled", False)
        if self.table == "live_sessions":
            r.setdefault("status", "running")
            r.setdefault("started_at", now)
        if self.table == "live_orders":
            r.setdefault("ts", now)
        return r


class FakeAuthAdmin:
    """auth.admin: deleting a user removes the sign-in record and what hangs from it (on delete cascade in schema.sql)."""
    def __init__(self, db):
        self.db = db
        self.deleted: list[str] = []
        self.fail = None

    def delete_user(self, uid, should_soft_delete=False):
        if self.fail:
            raise self.fail
        with self.db.lock:
            self.deleted.append(uid)
            for name in ("profiles", "usage_events", "strategies", "live_sessions", "live_orders"):
                key = "id" if name == "profiles" else "user_id"
                self.db.tables[name] = [r for r in self.db.tables.get(name, []) if r.get(key) != uid]


class FakeAuth:
    def __init__(self, db):
        self.db = db
        self.admin = FakeAuthAdmin(db)

    def get_user(self, token):
        from supabase_auth.errors import AuthApiError, AuthRetryableError
        if self.db.fail:
            raise AuthRetryableError("Connection refused", 0)
        u = USERS.get(token)
        if u and u[0] in self.admin.deleted:
            u = None                          # the sign-in record is gone: the token no longer checks out
        if not u:
            raise AuthApiError("invalid JWT: unable to parse or verify signature", 401, "bad_jwt")
        provider = "email" if token == "email-signup-admin-token" else "google"
        return SimpleNamespace(user=SimpleNamespace(id=u[0], email=u[1], email_confirmed_at="2026-01-01T00:00:00Z",
                                                    app_metadata={"provider": provider, "providers": [provider]}))


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.fail = None                     # an exception every query raises: the database is down
        self.lock = threading.RLock()
        self.auth = FakeAuth(self)
        self.tables["profiles"] = [{"id": uid, "email": email, "plan": plan, "created_at": "2026-09-01T00:00:00+00:00",
                                    "plan_status": "active" if plan != "free" else None,
                                    "current_period_end": None}          # paid plans given by hand, with no end date
                                   for uid, email, plan in USERS.values()]

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, params=None):
        """stratlab_db_usage: the sizes in self.usage, or the error PostgREST gives while the function isn't created."""
        db = self

        class Call:
            def execute(self):
                if name == "stratlab_db_usage" and getattr(db, "usage", None) is not None:
                    return SimpleNamespace(data=copy.deepcopy(db.usage))
                raise RuntimeError(f"{{'code': 'PGRST202', 'message': 'Could not find the function public.{name} in the schema cache'}}")
        return Call()


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
