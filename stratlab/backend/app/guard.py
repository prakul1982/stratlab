"""Request guard: a size cap on request bodies, a per-caller request rate limit, and standard security headers.

Plain ASGI, so it sees every request before FastAPI reads the body. Limits are per signed-in user (their
token) or, for anonymous calls, per address; they're generous enough that normal use, including several
tabs polling paper sessions, never reaches them."""
import hashlib
import json
import threading
import time

MAX_BODY = 8 * 1024 * 1024          # uploaded candles (50,000 bars) and share images fit well inside this
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
            try:
                too_big = int(length) > MAX_BODY
            except ValueError:
                too_big = True
            if too_big:
                return await _reply(send, 413, "too_large", "That upload is too large (8 MB at most).")
        elif b"chunked" in headers.get(b"transfer-encoding", b"").lower():
            # browsers and webhooks always say how big the body is; the server (h11) then holds them to it
            return await _reply(send, 411, "length_required", "Send the request with a Content-Length.")

        async def send_with_headers(msg):
            if msg["type"] == "http.response.start":
                have = {k.lower() for k, _ in msg.get("headers") or []}
                msg = {**msg, "headers": list(msg.get("headers") or []) + [h for h in HEADERS if h[0] not in have]}
            await send(msg)

        await self.app(scope, receive, send_with_headers)
