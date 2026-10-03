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
    "admin-token": ("u-admin", "owner@example.com", "pro"),
}


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
        self._order, self._limit = None, None

    # building
    def select(self, cols="*", count=None):
        self.op, self.cols, self.count = "select", cols, count
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload):
        self.op, self.payload = "upsert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def _f(self, fn):
        self.filters.append(fn)
        return self

    def eq(self, c, v): return self._f(lambda r: r.get(c) == v)
    def neq(self, c, v): return self._f(lambda r: r.get(c) != v)
    def gte(self, c, v): return self._f(lambda r: r.get(c) is not None and r.get(c) >= v)
    def gt(self, c, v): return self._f(lambda r: r.get(c) is not None and r.get(c) > v)
    def lte(self, c, v): return self._f(lambda r: r.get(c) is not None and r.get(c) <= v)
    def lt(self, c, v): return self._f(lambda r: r.get(c) is not None and r.get(c) < v)
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
                new = [self._fill(p) for p in (self.payload if isinstance(self.payload, list) else [self.payload])]
                rows += new
                return SimpleNamespace(data=copy.deepcopy(new), count=None)
            if self.op == "upsert":
                key = "key" if self.table == "app_settings" else "id"
                out = []
                for p in self.payload if isinstance(self.payload, list) else [self.payload]:
                    old = next((r for r in rows if r.get(key) == p.get(key)), None)
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
                return SimpleNamespace(data=copy.deepcopy(match), count=None)
            if self.op == "delete":
                self.db.tables[self.table] = [r for r in rows if r not in match]
                return SimpleNamespace(data=copy.deepcopy(match), count=None)
            if self._order:
                c, desc = self._order
                match.sort(key=lambda r: (r.get(c) is None, str(r.get(c))), reverse=desc)
            n = len(match)
            if self._limit is not None:
                match = match[: self._limit]
            return SimpleNamespace(data=[_project(r, self.cols) for r in match], count=n if self.count else None)

    def _fill(self, p):
        """Column defaults, as in supabase/schema.sql."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        r = copy.deepcopy(p)
        if self.table != "app_settings":
            r.setdefault("id", str(uuid.uuid4()))
        r.setdefault("created_at", now)
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


class FakeAuth:
    def __init__(self, db):
        self.db = db

    def get_user(self, token):
        from supabase_auth.errors import AuthApiError, AuthRetryableError
        if self.db.fail:
            raise AuthRetryableError("Connection refused", 0)
        u = USERS.get(token)
        if not u:
            raise AuthApiError("invalid JWT: unable to parse or verify signature", 401, "bad_jwt")
        return SimpleNamespace(user=SimpleNamespace(id=u[0], email=u[1], email_confirmed_at="2026-01-01T00:00:00Z"))


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.fail = None                     # an exception every query raises: the database is down
        self.lock = threading.RLock()
        self.auth = FakeAuth(self)
        self.tables["profiles"] = [{"id": uid, "email": email, "plan": plan, "created_at": "2026-09-01T00:00:00+00:00",
                                    "plan_status": "active" if plan != "free" else None,
                                    "current_period_end": "2099-01-01T00:00:00+00:00" if plan != "free" else None}
                                   for uid, email, plan in USERS.values()]

    def table(self, name):
        return Query(self, name)


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
