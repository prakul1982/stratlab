"""A probe for the 15 Oct hang: the real database client (supabase -> httpx, real connection pools) against a fake
PostgREST and sign-in service on 127.0.0.1, whose reads can be made to hang. Background "job" threads (no request
around them, like the after-close jobs) hold slow reads while signed-in routes that need nothing slow are timed.

Used by tests/test_db_hang.py, and runnable on its own to print the numbers:
    python -m tests.db_hang_probe [hang seconds] [job threads]
Nothing leaves the machine: any request to a host other than 127.0.0.1 fails."""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

GOOD = "good-token"
USER = {"id": "u-probe", "aud": "authenticated", "role": "authenticated", "email": "probe@example.com",
        "app_metadata": {"provider": "email", "providers": ["email"]}, "user_metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00"}
PROFILE = {"id": "u-probe", "email": "probe@example.com", "plan": "free", "created_at": "2026-01-01T00:00:00+00:00"}


class Server:
    """A fake Supabase. `job_hang`: seconds a read of the jobs' big table takes; `all_hang`: seconds every database read
    takes (the egress-throttled case); sign-in answers at once (it is its own service at Supabase)."""

    def __init__(self):
        self.job_hang = 0.0
        self.all_hang = 0.0
        self.release = threading.Event()        # set: every hanging read answers now
        probe = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except OSError:
                    pass

            def _wait(self, seconds):
                if seconds:
                    probe.release.wait(seconds)

            def do_GET(self):
                if self.path.startswith("/auth/v1/user"):
                    ok = self.headers.get("Authorization") == f"Bearer {GOOD}"
                    return self._reply(200, USER) if ok else self._reply(401, {"code": 401, "msg": "invalid JWT"})
                self._wait(probe.job_hang if "/rest/v1/job_rows" in self.path else probe.all_hang)
                if "/rest/v1/profiles" in self.path:
                    return self._reply(200, [PROFILE])
                return self._reply(200, [])

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self._wait(probe.all_hang)
                self._reply(201, [])

            do_PATCH = do_POST

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.release.set()
        self.httpd.shutdown()
        self.httpd.server_close()


_real_handle = httpx.HTTPTransport.handle_request


def _local_only(self, request):
    if request.url.host != "127.0.0.1":
        raise httpx.ConnectError("network disabled in the probe", request=request)
    return _real_handle(self, request)


def setup(patch):
    """Point the app's database client at a fresh fake server. `patch(obj, name, value)` sets an attribute for the run
    (pytest's monkeypatch.setattr, or a plain setattr in the script). Returns (server, TestClient)."""
    from fastapi.testclient import TestClient
    from app import auth, db, main
    from app.config import settings
    server = Server()
    patch(httpx.HTTPTransport, "handle_request", _local_only)
    patch(settings, "SUPABASE_URL", server.url)
    patch(settings, "SUPABASE_SERVICE_KEY", "service-key")
    patch(db, "_client", None)
    db._profiles.clear()
    auth._cache.clear()
    auth._rejected.clear()
    return server, TestClient(main.app)


def job_read():
    """What an after-close job does: a read with no request around it."""
    from app import db
    try:
        db.sb().table("job_rows").select("*").execute()
    except Exception:
        pass


def timed(client, path, token=GOOD) -> tuple[float, int]:
    t = time.monotonic()
    r = client.get(path, headers={"Authorization": f"Bearer {token}"})
    return time.monotonic() - t, r.status_code


ROUTES = ("/notebooks", "/me/first-steps")


def burst(client, n: int = 12, token=GOOD) -> tuple[float, list[int]]:
    """A page opening: n signed-in calls at once (half each route). (slowest seconds, status codes)."""
    with ThreadPoolExecutor(n) as ex:
        out = list(ex.map(lambda i: timed(client, ROUTES[i % 2], token), range(n)))
    return max(s for s, _ in out), sorted({c for _, c in out})


def run(patch, hang: float = 6.0, jobs: int = 40, all_slow: bool = False) -> dict:
    """The numbers: a page's calls while jobs hold slow reads (or while every read hangs), an invalid token, /health,
    and the same page once reads are fast again."""
    server, client = setup(patch)
    out = {}
    try:
        burst(client, 2)                                    # warm: the token checked, connections open
        from app import db
        db._profiles.clear()                                # so the page below reads the profile again
        if all_slow:
            server.all_hang = hang
        else:
            server.job_hang = hang
        workers = [threading.Thread(target=job_read, daemon=True) for _ in range(jobs)]
        for t in workers:
            t.start()
        time.sleep(0.3)                                     # the jobs hold their connections
        t0 = time.monotonic()
        with ThreadPoolExecutor(3) as ex:
            page = ex.submit(burst, client)
            bad = ex.submit(timed, client, "/me/first-steps", "made-up-token")
            health = ex.submit(lambda: (time.sleep(0.1), timed(client, "/health", ""))[1])
            out["page_s"], out["page_codes"] = page.result()
            out["invalid_token_s"], out["invalid_token_code"] = bad.result()
            out["health_s"], _ = health.result()
        out["while_slow_wall_s"] = time.monotonic() - t0
        server.job_hang = server.all_hang = 0.0
        server.release.set()                                # reads are fast again
        for t in workers:
            t.join(timeout=hang + 35)
        server.release.clear()
        db._profiles.clear()
        out["after_s"], out["after_codes"] = burst(client)
    finally:
        server.close()
    return {k: round(v, 2) if isinstance(v, float) else v for k, v in out.items()}


if __name__ == "__main__":
    hang = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    print("jobs hold slow reads:", run(setattr, hang, jobs))
    print("every read slow:     ", run(setattr, hang, jobs, all_slow=True))
