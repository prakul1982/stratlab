"""One leader among overlapping containers: the one that runs the background jobs and the live paper sessions.

A deploy starts the new container while the old one still runs until the new one passes its health check. Both serve
requests, but only the holder of the `app_leader` lease (one row in the market database) runs what must happen once:
every job, the live sessions, the daily report, the Kite auto-login. The lease lasts LEASE seconds and is renewed every
RENEW seconds; the old container releases it on shutdown, so the new one takes over within RETRY seconds of that.

No market database (local dev, tests) or LEADER_LEASE=off: this process always leads.
"""
import logging
import os
import secrets
import socket
import threading
import time

from . import market_store

log = logging.getLogger("stratlab")

NAME = "main"
LEASE, RENEW, RETRY = 60.0, 15.0, 5.0

CLAIM = ("insert into app_leader (name, owner, until) values (%s, %s, now() + make_interval(secs => %s)) "
         "on conflict (name) do update set owner = excluded.owner, until = excluded.until "
         "where app_leader.owner = excluded.owner or app_leader.until <= now() returning owner")


class PgLease:
    """The lease row in the market database: one atomic statement claims or renews it."""

    def __init__(self, store):
        self.store = store

    def claim(self, name: str, owner: str, secs: float) -> bool:
        return bool(self.store._run(CLAIM, (name, owner, secs), fetch=True))

    def release(self, name: str, owner: str) -> None:
        self.store._run("update app_leader set until = now() where name = %s and owner = %s", (name, owner))

    def read(self, name: str) -> dict | None:
        rows = self.store._run("select owner, until from app_leader where name = %s", (name,), fetch=True)
        return {"owner": rows[0][0], "until": rows[0][1].isoformat()} if rows else None


def _backend():
    if os.getenv("LEADER_LEASE", "").strip().lower() == "off":
        return None
    s = market_store.store()
    return PgLease(s) if s is not None else None


class Leader:
    def __init__(self, backend=_backend, clock=time.monotonic, lease: float = LEASE, renew: float = RENEW,
                 retry: float = RETRY, name: str = NAME):
        self.backend, self.clock, self.name = backend, clock, name
        self.lease, self.renew_every, self.retry = lease, renew, retry
        self.me = f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}"
        self.held = False
        self.held_until = 0.0         # by our own clock: never lead past it without a renewal
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def leading(self) -> bool:
        if self.backend() is None:     # the kill switch, or no database to hold a lease in
            return True
        return self.held and self.clock() < self.held_until

    def renew(self) -> bool:
        """Claim or renew the lease; whether this process leads now."""
        b = self.backend()
        if b is None:
            return True
        t = self.clock()
        try:
            got = b.claim(self.name, self.me, self.lease)
        except Exception as e:         # keep what we hold until it would have run out by our own clock
            print("leader: could not renew the lease:", str(e)[:160])
            return self.leading()
        if got:
            self.held, self.held_until = True, t + self.lease
        elif self.held:
            print(f"leader: LOST the lease to another container; {self.me} stops its jobs and live sessions")
            self.held = False
        return self.held

    @staticmethod
    def _call(fn, what: str) -> None:
        """A callback that raises never ends the lease loop (the container would then lead, or not, for good)."""
        try:
            fn()
        except Exception:
            log.exception("leader: %s failed", what)

    def run(self, on_gain, on_lose) -> None:
        """Wait for the lease (try now, then every RETRY s), then keep renewing it; on_gain/on_lose on each change."""
        was = False
        while not self._stop.is_set():
            now = self.renew()
            if now and not was:
                print(f"leader: {self.me} leads")
                self._call(on_gain, "on_gain")
            elif was and not now:
                print(f"leader: {self.me} STEPPED DOWN; jobs and live sessions stop here")
                self._call(on_lose, "on_lose")
            was = now
            wait = self.renew_every if now else self.retry
            if now and self.backend() is not None:      # wake in time to step down at the lease's end
                wait = min(wait, max(0.05, self.held_until - self.clock()))
            self._stop.wait(wait)

    def start(self, on_gain, on_lose) -> None:
        if not self._thread:
            self._thread = threading.Thread(target=self.run, args=(on_gain, on_lose), daemon=True, name="leader")
            self._thread.start()

    def release(self) -> None:
        """Shutdown: stop renewing and let the next container take over now rather than at the lease's end."""
        self._stop.set()
        was, self.held = self.held, False
        b = self.backend()
        if b is not None and was:
            try:
                b.release(self.name, self.me)
            except Exception as e:
                print("leader: could not release the lease:", str(e)[:160])

    def status(self) -> dict:
        """For Admin: who leads and until when (the database's row), and whether it's this container."""
        out = {"me": self.me, "leading": self.leading(), "lease": "off" if self.backend() is None else "on"}
        b = self.backend()
        if b is not None:
            try:
                out.update(b.read(self.name) or {"owner": None, "until": None})
            except Exception as e:
                out["error"] = str(e)[:160]
        return out


current = Leader()


def leading() -> bool:
    """Whether this process runs the jobs and live sessions now: jobs check it before each run."""
    return current.leading()
