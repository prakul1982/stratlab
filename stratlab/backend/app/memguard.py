"""Memory discipline for the one server process (MEM-001).

The server's cost is its memory. Three habits keep the peaks down without cutting a feature:

- the malloc library is told to give freed memory back (`tune_malloc`): with ~40 background threads every one gets its
  own arena, and big lists, pages and documents freed by a job stayed with the process (measured: 385 MB kept after
  eight threads built and dropped 100 MB each, 44 MB with these settings);
- the heavy background jobs take turns (`heavy`): at most one of them builds its big structures at a time, so two jobs'
  peaks never stack, and each hands its memory back when it is through (`release_memory`);
- the caches stay under one budget (`app.intel.net.shrink_caches`), with expired entries swept out, not kept until asked for.

Nothing here changes a result: a job that waits too long for its turn runs anyway, and a cache entry dropped is read again."""
import contextlib
import ctypes
import gc
import os
import sys
import threading
import time
from collections import deque

CACHE_BUDGET = int(float(os.environ.get("CACHE_BUDGET_MB", "256")) * 1024 * 1024)   # all caches together (approximate bytes)
WAIT = float(os.environ.get("HEAVY_JOB_WAIT", str(45 * 60)))       # seconds a job waits for its turn before running anyway
TRIM_EVERY = 120.0           # seconds between two non-forced collections (a job that runs a small step every few seconds)

_libc = None


def _glibc():
    global _libc
    if _libc is None:
        try:
            _libc = ctypes.CDLL("libc.so.6") if sys.platform.startswith("linux") else False
        except OSError:
            _libc = False
    return _libc or None


def tune_malloc() -> bool:
    """Tell glibc malloc to keep two arenas, not one per thread, and to serve blocks of 1 MB and more from their own
    mappings, so freeing a big list, a PDF or a page hands the memory straight back. Call it before the threads start;
    MALLOC_TUNE=0 turns it off, and an explicit MALLOC_ARENA_MAX in the environment is left as it is."""
    if os.environ.get("MALLOC_TUNE") == "0":
        return False
    libc = _glibc()
    if libc is None:
        return False
    try:
        if "MALLOC_ARENA_MAX" not in os.environ:
            libc.mallopt(-8, 2)              # M_ARENA_MAX
        if "MALLOC_MMAP_THRESHOLD_" not in os.environ:
            libc.mallopt(-3, 1 << 20)        # M_MMAP_THRESHOLD (a fixed one also stops it growing to 32 MB with use)
        return True
    except Exception:
        return False


def malloc_trim() -> bool:
    libc = _glibc()
    if libc is None:
        return False
    try:
        libc.malloc_trim(0)
        return True
    except Exception:
        return False


def rss_mb() -> float | None:
    """This process's resident memory, in MB (Linux; None elsewhere)."""
    try:
        with open("/proc/self/statm") as f:
            return round(int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024), 1)
    except (OSError, ValueError, IndexError):
        return None


_last_release = 0.0
_release_lock = threading.Lock()


def release_memory(force: bool = False, full: bool = True) -> dict:
    """Give memory back after heavy work: expired cache entries out, the caches under their budget, a garbage collection
    and a trim of the malloc heap. Without `force` it runs at most every TRIM_EVERY seconds. `full`: collect every
    generation (a pass over everything the process holds, a second or so on a big heap), else only the young ones.
    Returns what it measured."""
    global _last_release
    now = time.monotonic()
    if not force and now - _last_release < TRIM_EVERY:
        return {}
    if not _release_lock.acquire(blocking=False):      # one at a time
        return {}
    try:
        _last_release = now
        before = rss_mb()
        freed = 0
        try:
            from .intel import net
            freed = net.sweep_caches() + net.shrink_caches(CACHE_BUDGET)
        except Exception as e:
            print("memguard: cache sweep failed:", str(e)[:120])
        gc.collect() if full else gc.collect(1)
        malloc_trim()
        return {"rss_before_mb": before, "rss_after_mb": rss_mb(), "cache_freed_mb": round(freed / 1048576, 1)}
    finally:
        _release_lock.release()


class _Turns:
    """A fair lock the heavy jobs queue on: first come, first served (a job that runs again at once goes to the back),
    held by one thread at a time but re-entrant for it. A wait that runs out returns False and the job runs anyway, so
    a stuck job can never stop the others for good."""

    def __init__(self):
        self._cond = threading.Condition()
        self._queue: deque = deque()
        self._owner = None
        self._depth = 0
        self.name: str | None = None
        self.since: float | None = None

    def acquire(self, name: str, timeout: float) -> bool:
        me = threading.get_ident()
        with self._cond:
            if self._owner == me:
                self._depth += 1
                return True
            ticket = object()
            self._queue.append(ticket)
            deadline = time.monotonic() + timeout
            try:
                while not (self._owner is None and self._queue[0] is ticket):
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return False
                    self._cond.wait(left)
                self._owner, self._depth, self.name, self.since = me, 1, name, time.time()
                return True
            finally:
                self._queue.remove(ticket)
                self._cond.notify_all()

    def release(self) -> bool:
        """One level out; True when this was the outermost (the lock is free again after it)."""
        with self._cond:
            self._depth -= 1
            if self._depth > 0:
                return False
            self._owner = self.name = self.since = None
            self._cond.notify_all()
            return True

    def waiting(self) -> int:
        with self._cond:
            return len(self._queue)

    def holds(self) -> bool:
        return self._owner == threading.get_ident()


TURNS = _Turns()
_local = threading.local()


REQUEST_WAIT = 20.0          # a person's request waits for the turn no longer than this, then runs (the page is not held for a job)


def _wait() -> float:
    try:
        from . import db
        return REQUEST_WAIT if db.in_request() else WAIT
    except Exception:
        return WAIT


@contextlib.contextmanager
def heavy(name: str, force_release: bool = False):
    """Run a heavy piece of background work (a whole-market read, an index build, a document read) with the lock held,
    so no other heavy job builds its big structures meanwhile; the memory is handed back afterwards. Put the lock around
    the work itself, not around the pauses between steps, so the others get their turn. `force_release`: always
    collect afterwards (a long job), else at most every couple of minutes (a short step run every few seconds)."""
    began, holder = time.monotonic(), TURNS.name
    got = TURNS.acquire(name, _wait())
    if time.monotonic() - began > 5:
        print(f"memguard: {name} waited {time.monotonic() - began:.0f}s for {holder}" + ("" if got else " and ran without its turn"))
    try:
        yield got
    finally:
        outer = TURNS.release() if got else True
        if outer:
            try:
                release_memory(force=force_release)
            except Exception as e:
                print("memguard: release failed:", str(e)[:120])


def status() -> dict:
    """Which heavy job has the turn, how many wait, the process's memory and the caches' size (Admin)."""
    from .intel import net
    return {"running": TURNS.name, "since": TURNS.since, "waiting": TURNS.waiting(), "rss_mb": rss_mb(),
            "cache_mb": round(net.cache_bytes() / 1048576, 1), "cache_budget_mb": round(CACHE_BUDGET / 1048576)}


def janitor(every: float = 300.0, sleep=time.sleep):
    """Every few minutes: expired cache entries out, the caches under budget, and the heap trimmed (the jobs do it after
    their own work; this catches what pages and imports left)."""
    while True:
        sleep(every)
        try:
            release_memory(force=True, full=False)
        except Exception as e:
            print("memguard: janitor failed:", str(e)[:120])
