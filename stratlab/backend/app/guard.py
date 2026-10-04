"""Request guard: a size cap on request bodies, a per-caller request rate limit, and standard security headers.

Plain ASGI, so it sees every request before FastAPI reads the body. Limits are per signed-in user (their
token) or, for anonymous calls, per address; they're generous enough that normal use, including several
tabs polling paper sessions, never reaches them."""
import hashlib
import json
import re
import threading
import time

from .holdings_file import TAX_MAX_REQUEST

MAX_BODY = 8 * 1024 * 1024          # uploaded candles (50,000 bars) and share images fit well inside this
# routes allowed a bigger body: a tradebook or tax P&L ZIP for the tax report (10 MB a file, sent as the body itself,
# or as base64 in JSON, a third larger), within the 25 MB a request the tax import allows
BIG_BODY = {("POST", "/tax/import"): TAX_MAX_REQUEST}
PER_MINUTE_USER = 600
PER_MINUTE_ANON = 240
PER_MINUTE_ADDRESS = 1200           # every request from one address, signed in or not: made-up tokens can't dodge the limit
EXEMPT = ("/health",)               # the host's health check

HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"x-frame-options", b"DENY"),
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
]
# the API's own HTML pages (public company pages, share previews, unsubscribe) need no script at all: none may run
HTML_CSP = (b"content-security-policy", b"default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data: https:; "
                                         b"form-action 'self'; base-uri 'none'; frame-ancestors 'none'")


def max_body(scope) -> int:
    """The biggest request body this route takes."""
    return BIG_BODY.get((scope.get("method"), scope.get("path", "").rstrip("/") or "/"), MAX_BODY)


class Window:
    """Requests per caller in the current minute, a fixed window per caller."""

    def __init__(self):
        self._d: dict[str, list] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, now: float | None = None) -> bool:
        """Count one request; False once the caller is over the limit for this minute."""
        now = time.time() if now is None else now
        minute = int(now // 60)
        with self._lock:
            if len(self._d) > 50000:
                self._d = {k: v for k, v in self._d.items() if v[0] == minute}
            cur = self._d.get(key)
            if not cur or cur[0] != minute:
                cur = self._d[key] = [minute, 0]
            cur[1] += 1
            return cur[1] <= limit


def address(scope) -> str:
    headers = dict(scope.get("headers") or [])
    ip = (headers.get(b"x-real-ip") or headers.get(b"x-forwarded-for", b"").split(b",")[0]).strip().decode("latin-1")
    if not ip and scope.get("client"):
        ip = scope["client"][0]
    return ip or "?"


def caller(scope) -> tuple[str, int]:
    auth = dict(scope.get("headers") or []).get(b"authorization", b"")
    if auth[:7].lower() == b"bearer ":
        return "u:" + hashlib.sha256(auth[7:].strip()).hexdigest()[:32], PER_MINUTE_USER
    return "a:" + address(scope), PER_MINUTE_ANON


async def _reply(send, status: int, code: str, message: str, extra: list | None = None):
    body = json.dumps({"detail": {"code": code, "message": message}}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
                + HEADERS + (extra or [])})
    await send({"type": "http.response.body", "body": body})


class Guard:
    def __init__(self, app, window: Window | None = None):
        self.app = app
        self.window = window or Window()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if scope.get("method") != "OPTIONS" and path not in EXEMPT:
            key, limit = caller(scope)
            ok_caller = self.window.hit(key, limit)
            ok_address = key.startswith("a:") or self.window.hit("ip:" + address(scope), PER_MINUTE_ADDRESS)
            if not (ok_caller and ok_address):
                return await _reply(send, 429, "rate_limited", "Too many requests. Wait a minute and try again.",
                                    [(b"retry-after", b"60")])
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None:
            cap = max_body(scope)
            try:
                too_big = int(length) > cap
            except ValueError:
                too_big = True
            if too_big:
                return await _reply(send, 413, "too_large", f"That upload is too large ({cap // (1024 * 1024)} MB at most).")
        elif b"chunked" in headers.get(b"transfer-encoding", b"").lower():
            # browsers and webhooks always say how big the body is; the server (h11) then holds them to it
            return await _reply(send, 411, "length_required", "Send the request with a Content-Length.")

        async def send_with_headers(msg):
            if msg["type"] == "http.response.start":
                got = {k.lower(): v for k, v in msg.get("headers") or []}
                extra = HEADERS + ([HTML_CSP] if got.get(b"content-type", b"").startswith(b"text/html") else [])
                msg = {**msg, "headers": list(msg.get("headers") or []) + [h for h in extra if h[0] not in got]}
            await send(msg)

        await self.app(scope, receive, send_with_headers)


HEAVY = [  # (method, path pattern): work that holds the CPU for a second or more
    ("POST", re.compile(r"^/notebooks/[^/]+/experiments(/[^/]+/(basket|walkforward))?$")),
    ("POST", re.compile(r"^/research/scan$")),
    ("GET", re.compile(r"^/research/rotation$")),
    ("GET", re.compile(r"^/research/investor$")),             # up to 20 companies' numbers at once
    ("GET", re.compile(r"^/research/deep/[^/]+/deck$")),
    ("POST", re.compile(r"^/research/deep/[^/]+/(read|card)$")),
    ("POST", re.compile(r"^/live/(sessions|groups)$")),
    ("POST", re.compile(r"^/options/sessions$")),
    ("POST", re.compile(r"^/admin/platform/check$")),
    ("POST", re.compile(r"^/money/mutual-funds/import$")),   # reading a statement PDF
]


class HeavyGate:
    """At most `slots` heavy requests (backtests, scans, the sector chart, document reads) run at once; the rest
    wait their turn without holding a worker thread, so ordinary pages stay quick while the server is busy. A heavy
    request that waits longer than `max_wait` seconds is told the server is busy instead of hanging."""

    def __init__(self, app, slots: int | None = None, max_wait: float = 90.0):
        import asyncio
        import os
        self.app = app
        self.slots = slots or int(os.environ.get("HEAVY_SLOTS", "2"))
        self.max_wait = max_wait
        self._sem: asyncio.Semaphore | None = None
        self._loop = None
        self.waiting = 0

    def _heavy(self, scope) -> bool:
        m, p = scope.get("method"), scope.get("path", "")
        return any(m == hm and rx.match(p) for hm, rx in HEAVY)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self._heavy(scope):
            return await self.app(scope, receive, send)
        import asyncio
        loop = asyncio.get_running_loop()
        if self._sem is None or self._loop is not loop:     # one server loop in production; tests start new ones
            self._sem, self._loop = asyncio.Semaphore(self.slots), loop
        self.waiting += 1
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self.max_wait)
        except asyncio.TimeoutError:
            return await _reply(send, 503, "busy", "StratLab is very busy right now. Try again in a minute.",
                                [(b"retry-after", b"30")])
        finally:
            self.waiting -= 1
        try:
            return await self.app(scope, receive, send)
        finally:
            self._sem.release()
