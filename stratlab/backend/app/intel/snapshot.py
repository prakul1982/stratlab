"""A value read behind the page and served from memory: a request never waits on a slow source once a first copy exists.

R24-001: at India's open the Market pulse request read the index levels (the broker's quotes, behind the throttle every
job shares, and the 52-week ranges from the other source) and the headlines itself, one after the other. Near the
quarter-hour breadth round and the option-chain reads that took 12 to 40 s, and an iPhone gave up. Now the page gets the
last copy at once and a fresh one is read in the background; only the very first request waits, and only up to `wait`
seconds. A read that hangs is given up on after `give_up` seconds, so the next request starts a new one."""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

# its own threads: the research pool can be full of a company page's sources, and a refresh must never queue behind them
_bg = ThreadPoolExecutor(max_workers=4, thread_name_prefix="snapshot")


class Snapshot:
    """{key: the last value read} with the time it was read. `get` answers from memory and starts a background read when the
    copy is older than `fresh_for` seconds (one read per key at a time)."""

    def __init__(self, fresh_for: float, give_up: float = 30.0, clock=time.time, pool: ThreadPoolExecutor | None = None):
        self.fresh_for, self.give_up, self.clock = fresh_for, give_up, clock
        self.pool = pool or _bg
        self._lock = threading.Lock()
        self._kept: dict = {}                      # key -> (read at, value)
        self._running: dict = {}                   # key -> (started at, future)
        self.errors: dict = {}                     # key -> the last read's error, for the logs

    def kept(self, key):
        """(read at, value) of the last good read, or None."""
        with self._lock:
            return self._kept.get(key)

    def put(self, key, value, at: float | None = None):
        with self._lock:
            self._kept[key] = (self.clock() if at is None else at, value)

    def _start(self, key, read) -> Future:
        """The read running for `key`, started now unless one is already going (and not given up on)."""
        with self._lock:
            going = self._running.get(key)
            if going and not going[1].done() and self.clock() - going[0] < self.give_up:
                return going[1]

            def work():
                try:
                    value = read()
                except Exception as e:              # the last good copy stays; the next request tries again
                    self.errors[key] = f"{e.__class__.__name__}: {str(e)[:160]}"
                    raise
                self.errors.pop(key, None)
                self.put(key, value)
                return value
            f = self.pool.submit(work)
            self._running[key] = (self.clock(), f)
            return f

    def get(self, key, read, wait: float) -> tuple[object, float | None]:
        """(value, the time it was read). The kept value at once, a background read started when it is older than
        `fresh_for`. With nothing kept, waits up to `wait` seconds for the first read: (None, None) when it isn't back in
        time, and the read's own error raised when it failed."""
        hit = self.kept(key)
        if hit and self.clock() - hit[0] < self.fresh_for:
            return hit[1], hit[0]
        f = self._start(key, read)
        if hit:
            return hit[1], hit[0]
        try:
            value = f.result(timeout=max(0.0, wait))
        except FutureTimeout:
            return None, None
        got = self.kept(key)
        return value, (got[0] if got else self.clock())
