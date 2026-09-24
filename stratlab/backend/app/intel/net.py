"""Shared plumbing for the research sources: a small TTL cache and a polite HTTP client.

Every source is called from the server, so users never need their own keys and the
browser never hits a third-party site directly."""
import threading
import time
from collections import OrderedDict

import httpx

UA = "Mozilla/5.0 (compatible; StratLab/1.0; +https://stratlab.studio)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")


class SourceError(Exception):
    """A source couldn't answer. `source` names it for the connection check."""

    def __init__(self, source: str, message: str, busy: bool = False):
        super().__init__(message)
        self.source, self.busy = source, busy


class TTLCache:
    def __init__(self, max_items: int = 3000):
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.max = max_items

    def get(self, key):
        with self._lock:
            hit = self._d.get(key)
            if not hit:
                return None
            if hit[0] < time.time():
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return hit[1]

    def set(self, key, value, ttl: float):
        with self._lock:
            self._d[key] = (time.time() + ttl, value)
            self._d.move_to_end(key)
            while len(self._d) > self.max:
                self._d.popitem(last=False)

    def clear(self):
        with self._lock:
            self._d.clear()


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
        self.http = httpx.Client(base_url=base, timeout=timeout, transport=transport, follow_redirects=True,
                                 headers={"User-Agent": UA, **(headers or {})})
        self.limit = RateLimit(per_minute, burst)
        self.cache = TTLCache()

    def fetch(self, path: str, params: dict | None = None, ttl: float = 300, kind: str = "json"):
        key = (path, tuple(sorted((params or {}).items())), kind)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        if not self.limit.take():
            raise SourceError(self.name, f"{self.name} is busy (our rate limit). Try again in a minute.", busy=True)
        try:
            r = self.http.get(path, params=params)
        except httpx.HTTPError as e:
            raise SourceError(self.name, f"Couldn't reach {self.name} ({e.__class__.__name__}).", busy=True) from None
        self.check(r)
        if kind == "json":
            try:
                value = r.json()
            except ValueError:
                raise SourceError(self.name, f"{self.name} sent something that isn't data.") from None
        else:
            value = r.text
        self.cache.set(key, value, ttl)
        return value

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
