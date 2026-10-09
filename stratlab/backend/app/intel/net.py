"""Shared plumbing for the research sources: a small TTL cache and a polite HTTP client.

Every source is called from the server, so users never need their own keys and the
browser never hits a third-party site directly."""
import threading
import time
from collections import OrderedDict

import httpx

from ..http_retry import real_transport

UA = "Mozilla/5.0 (compatible; StratLab/1.0; +https://stratlab.studio)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")


class SourceError(Exception):
    """A source couldn't answer. `source` names it for the connection check."""

    def __init__(self, source: str, message: str, busy: bool = False):
        super().__init__(message)
        self.source, self.busy = source, busy


class NotFound(SourceError):
    """The sources answered, and there is no such company or ticker: a wrong name, not a fault (answered as a 404)."""


def approx_size(value, _budget: list | None = None) -> int:
    """A rough byte count of a cached value (strings, bytes, dicts, lists, numbers), cheap enough to run on every
    set: it walks at most 20,000 nodes and scales up from there. Counted generously, since parsed JSON takes several
    times its text size in memory."""
    budget = _budget if _budget is not None else [20000]
    seen, size, stack = 0, 0, [value]
    while stack:
        v = stack.pop()
        if budget[0] <= 0:
            return int(size * (1 + len(stack) / max(seen, 1))) + 64 * len(stack)
        budget[0] -= 1
        seen += 1
        if isinstance(v, (str, bytes, bytearray)):
            size += 50 + len(v)
        elif isinstance(v, dict):
            size += 100 + 50 * len(v)
            stack.extend(v.keys())
            stack.extend(v.values())
        elif isinstance(v, (list, tuple, set, frozenset)):
            size += 60 + 8 * len(v)
            stack.extend(v)
        else:
            size += 32
    return size


class TTLCache:
    """Least-recently-used with a time to live, bounded by both an item count and an approximate memory size, so a
    long walk over every company (the whole-market audit) can't fill memory with large responses."""

    def __init__(self, max_items: int = 3000, max_bytes: int = 48 * 1024 * 1024):
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.max = max_items
        self.max_bytes = max_bytes
        self.bytes = 0

    def get(self, key, max_age: float | None = None):
        """The value, unless it has expired; with `max_age`, also None when it was stored longer ago than that (a copy
        another caller kept for longer than this one may use: R7V-005, a chart read in the minutes after the close,
        before the day's close was final, kept for a day and handed to the page that asked for one read after it)."""
        with self._lock:
            hit = self._d.get(key)
            if not hit:
                return None
            now = time.time()
            if hit[0] < now:
                self._drop(key)
                return None
            if max_age is not None and len(hit) > 3 and now - hit[3] > max_age:
                return None
            self._d.move_to_end(key)
            return hit[1]

    def _drop(self, key):
        old = self._d.pop(key, None)
        if old:
            self.bytes -= old[2]

    def set(self, key, value, ttl: float, size: int | None = None):
        n = approx_size(value) if size is None else int(size)
        if n > self.max_bytes // 4:          # one value bigger than a quarter of the cache: don't keep it
            with self._lock:
                self._drop(key)
            return
        with self._lock:
            self._drop(key)
            self._d[key] = (time.time() + ttl, value, n, time.time())
            self.bytes += n
            while self._d and (len(self._d) > self.max or self.bytes > self.max_bytes):
                _, old = self._d.popitem(last=False)
                self.bytes -= old[2]

    def stored_at(self, key) -> float | None:
        """When an entry was stored (None when there is none)."""
        with self._lock:
            hit = self._d.get(key)
            return hit[3] if hit and len(hit) > 3 else None

    def pop(self, key):
        """Forget one entry (no error when it isn't there)."""
        with self._lock:
            self._drop(key)

    def clear(self):
        with self._lock:
            self._d.clear()
            self.bytes = 0


class SizedDict:
    """A plain dict-like store (get, [key] = value, pop, len, iter) that drops its oldest entries past a memory size
    or item count. For caches written as dicts of (time, value)."""

    def __init__(self, max_items: int = 300, max_bytes: int = 64 * 1024 * 1024):
        self._d: OrderedDict = OrderedDict()
        self._sizes: dict = {}
        self._lock = threading.Lock()
        self.max, self.max_bytes, self.bytes = max_items, max_bytes, 0

    def get(self, key, default=None):
        with self._lock:
            return self._d.get(key, default)

    def __setitem__(self, key, value):
        n = approx_size(value)
        with self._lock:
            self.pop(key, None, _locked=True)
            self._d[key] = value
            self._sizes[key] = n
            self.bytes += n
            while self._d and (len(self._d) > self.max or self.bytes > self.max_bytes):
                k, _ = self._d.popitem(last=False)
                self.bytes -= self._sizes.pop(k, 0)

    def pop(self, key, default=None, _locked: bool = False):
        if not _locked:
            with self._lock:
                return self.pop(key, default, _locked=True)
        if key in self._d:
            self.bytes -= self._sizes.pop(key, 0)
            return self._d.pop(key)
        return default

    def clear(self):
        with self._lock:
            self._d.clear()
            self._sizes.clear()
            self.bytes = 0

    def __len__(self):
        return len(self._d)

    def __iter__(self):
        return iter(list(self._d))

    def __contains__(self, key):
        return key in self._d


class RateLimit:
    """Token bucket: `per_minute` calls a minute, with short bursts up to `burst`."""

    def __init__(self, per_minute: float, burst: int):
        self.rate, self.cap = per_minute / 60.0, float(burst)
        self.tokens, self.at = float(burst), time.time()
        self._lock = threading.Lock()

    def take(self, max_wait: float = 8.0) -> bool:
        deadline = time.time() + max_wait
        while True:
            with self._lock:
                now = time.time()
                self.tokens = min(self.cap, self.tokens + (now - self.at) * self.rate)
                self.at = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                wait = (1 - self.tokens) / self.rate
            if time.time() + wait > deadline:
                return False
            time.sleep(min(wait, 0.5))


class Source:
    """An HTTP source with its own cache, rate limit and friendly errors."""
    name = "source"

    def __init__(self, base: str, per_minute: float = 120, burst: int = 20, headers: dict | None = None,
                 transport: httpx.BaseTransport | None = None, timeout: float = 15):
        self.http = httpx.Client(base_url=base, timeout=timeout, transport=transport or real_transport(), follow_redirects=True,
                                 headers={"User-Agent": UA, **(headers or {})})
        self.limit = RateLimit(per_minute, burst)
        self.cache = TTLCache()
        self._fails, self._down_until = 0, 0.0
        self._lock = threading.Lock()

    BREAK_AFTER, BREAK_FOR = 3, 60.0     # failures in a row, then seconds treated as down

    def fetch(self, path: str, params: dict | None = None, ttl: float = 300, kind: str = "json", with_time: bool = False):
        """The answer, from the cache when a copy is no older than `ttl` seconds (whoever stored it); `with_time`: also
        when the source sent it, (value, time)."""
        key = (path, tuple(sorted((params or {}).items())), kind)
        hit = self.cache.get(key, max_age=ttl)
        if hit is not None:
            return (hit, self.cache.stored_at(key) or time.time()) if with_time else hit
        if time.time() < self._down_until:   # down a moment ago: answer now instead of queueing behind the outage
            raise SourceError(self.name, f"{self.name} isn't answering right now. Try again in a minute.", busy=True)
        if not self.limit.take():
            raise SourceError(self.name, f"{self.name} is busy (our rate limit). Try again in a minute.", busy=True)
        try:
            try:
                r = self.http.get(path, params=params)
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"Couldn't reach {self.name} ({e.__class__.__name__}).", busy=True) from None
            self.check(r)
            if kind == "json":
                try:
                    value = r.json()
                except ValueError:
                    raise SourceError(self.name, f"{self.name} sent something that isn't data.", busy=True) from None
            else:
                value = r.text
        except SourceError as e:
            self._failed(e.busy)
            raise
        self._failed(False, ok=True)
        # parsed JSON takes several times its text size in memory
        self.cache.set(key, value, ttl, size=len(r.content) * (4 if kind == "json" else 1) + 200)
        return (value, time.time()) if with_time else value

    def _failed(self, outage: bool, ok: bool = False):
        """Count outages (unreachable, 5xx, 429, a page instead of data); a normal answer, even a 404, resets it."""
        with self._lock:
            if ok or not outage:
                self._fails = 0
                return
            self._fails += 1
            if self._fails >= self.BREAK_AFTER:
                self._down_until, self._fails = time.time() + self.BREAK_FOR, 0

    def check(self, r: httpx.Response):
        if r.status_code == 429:
            raise SourceError(self.name, f"{self.name} is rate limiting us right now. Try again in a minute.", busy=True)
        if r.status_code >= 500:
            raise SourceError(self.name, f"{self.name} is having trouble ({r.status_code}).", busy=True)
        if r.status_code == 404:
            raise SourceError(self.name, f"{self.name} has nothing for that.")
        if r.status_code >= 400:
            raise SourceError(self.name, f"{self.name} returned an error ({r.status_code}).")


def num(v) -> float | None:
    """A float from anything numeric-looking: 1,23,456.7 · "12.5 %" · None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v else None   # NaN check
    s = str(v).replace(",", "").replace("₹", "").replace("%", "").strip()
    if s in ("", "-", "—", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        import re
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group()) if m else None
