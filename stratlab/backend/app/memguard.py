"""Memory discipline for the one server process (MEM-001).

The server's cost is its memory. Three habits keep the peaks down without cutting a feature:

- the malloc library is told to give freed memory back (`tune_malloc`): with ~40 background threads every one gets its
  own arena, and big lists, pages and documents freed by a job stayed with the process (measured: 385 MB kept after
  eight threads built and dropped 100 MB each, 44 MB with these settings);
- the heavy background jobs take turns (`heavy`): at most one of them builds its big structures at a time, so two jobs'
  peaks never stack, and each hands its memory back when it is through (`release_memory`);
- the caches stay under one budget (`app.intel.net.shrink_caches`), with expired entries swept out, not kept until asked for.

- the small Python objects live in malloc's heap, not in Python's own 1 MB arenas (PYTHONMALLOC=malloc, set in the start
  command; MEM-3): an arena goes back to the system only when every object in it is gone, and a heap kept alive by a few
  long-lived entries between the temporary ones is what held ~300 MB after the day's peaks (measured on the replay of the
  day's jobs: freeing 250 MB of cache gave back 75 MB with Python's arenas, 220 MB with malloc; `python_heap` below tells which is in use).

Nothing here changes a result: a job that waits too long for its turn runs anyway, and a cache entry dropped is read again."""
import contextlib
import ctypes
import gc
import os
import re
import sys
import tempfile
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


def python_heap() -> dict | None:
    """What Python's own small-object allocator holds (MEM-3): `arenas_mb` taken from the system, `used_mb` of it in live
    objects, `wasted_mb` the rest (free, but kept: an arena goes back only when every block in it is free). None when it is
    not in use (PYTHONMALLOC=malloc: those objects are malloc's, and what malloc keeps shows in `rss_split`). The numbers
    are CPython's own report, written to stderr; it is caught for the moment through a temporary file."""
    if os.environ.get("PYTHONMALLOC", "").lower() in ("malloc", "malloc_debug") or not hasattr(sys, "_debugmallocstats"):
        return None
    try:
        fd = os.dup(2)
    except OSError:
        return None
    try:
        with tempfile.TemporaryFile() as t:
            sys.stderr.flush()
            os.dup2(t.fileno(), 2)
            try:
                sys._debugmallocstats()
            finally:
                os.dup2(fd, 2)
            t.seek(0)
            text = t.read().decode("ascii", "replace")
    except OSError:
        return None
    finally:
        os.close(fd)
    try:
        def n(pattern: str) -> int:
            return int(re.search(pattern + r"\s*=\s*([\d,]+)", text).group(1).replace(",", ""))
        arenas, used = n(r"\d+ arenas \* \d+ bytes/arena"), n("# bytes in allocated blocks")
    except (AttributeError, ValueError):
        return None
    return {"arenas_mb": round(arenas / 1048576, 1), "used_mb": round(used / 1048576, 1), "wasted_mb": round((arenas - used) / 1048576, 1)}


def rss_split() -> dict:
    """The resident memory as the kernel counts it: anonymous (the heap, Python's arenas, mappings made by malloc) and
    file-backed (the program, libraries, mapped files), in MB (Linux; {} elsewhere)."""
    out = {}
    try:
        with open("/proc/self/smaps_rollup") as f:
            for line in f:
                key, _, rest = line.partition(":")
                if key in ("Rss", "Anonymous"):
                    out["rss_mb" if key == "Rss" else "anon_mb"] = round(int(rest.split()[0]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        return {}
    if len(out) == 2:
        out["file_mb"] = round(out["rss_mb"] - out["anon_mb"], 1)
    return out


def allocators() -> dict:
    """Which allocators this process runs on, to be read from Admin (MEM-3): the C library's malloc (glibc, or jemalloc when
    preloaded) and whether Python's own small-object allocator is in use (`pymalloc`), with the settings that apply."""
    malloc = "glibc"
    try:
        with open("/proc/self/maps") as f:
            if "jemalloc" in f.read():
                malloc = "jemalloc"
    except OSError:
        malloc = "unknown"
    return {"malloc": malloc, "pymalloc": os.environ.get("PYTHONMALLOC", "").lower() not in ("malloc", "malloc_debug"),
            "arena_max": os.environ.get("MALLOC_ARENA_MAX") or ("2 (mallopt)" if os.environ.get("MALLOC_TUNE") != "0" else "default"),
            "malloc_conf": os.environ.get("MALLOC_CONF") or None}


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
            "cache_mb": round(net.cache_bytes() / 1048576, 1), "cache_budget_mb": round(CACHE_BUDGET / 1048576),
            "allocators": allocators()}


def named_caches(top: int = 15) -> list[dict]:
    """The caches by name, largest first: where each is held (a module's variable, or a field of an object it holds, such
    as a data source's), its items and its bytes as the budget counts them (MEM-3: the cache total is most of what grows
    through a day, and a total with no names says nothing about which cache it is). Walks the app's modules once."""
    from .intel import net
    kinds = (net.TTLCache, net.SizedDict)
    found: dict[int, tuple] = {}
    seen: set[int] = set()

    def look(path: str, obj, depth: int):
        if id(obj) in seen or depth > 5:
            return
        seen.add(id(obj))
        if isinstance(obj, kinds):
            found.setdefault(id(obj), (path, obj))
        elif depth < 5 and isinstance(obj, dict) and len(obj) <= 200:       # a registry of sources, by market or name
            for k, v in list(obj.items()):
                if isinstance(v, kinds) or hasattr(v, "__dict__"):
                    look(f"{path}[{str(k)[:20]}]", v, depth + 1)
        elif depth < 5 and not isinstance(obj, (type, str, bytes, int, float, list, tuple, set)) and hasattr(obj, "__dict__"):
            for k, v in list(vars(obj).items()):
                if isinstance(v, kinds) or (not k.startswith("__") and (hasattr(v, "__dict__") or isinstance(v, dict))):
                    look(f"{path}.{k}", v, depth + 1)
    for name, mod in list(sys.modules.items()):
        if name.startswith("app") and mod is not None:
            for attr, v in list(vars(mod).items()):
                if isinstance(v, kinds) or (not attr.startswith("__") and hasattr(v, "__dict__") and not isinstance(v, type)
                                            and type(v).__name__ != "module"):
                    look(f"{name}.{attr}", v, 1)
    for c in net.caches():       # any not reached above (held in a list or a dict), listed by type
        found.setdefault(id(c), (f"({type(c).__name__})", c))
    rows = [{"name": path, "items": len(c._d), "mb": round(c.bytes / 1048576, 1)} for path, c in found.values() if c._d or c.bytes]
    rows.sort(key=lambda r: -r["mb"])
    return rows[:top]


def census(top: int = 25) -> dict:
    """What the Python heap holds, by type: the object count and the shallow bytes of the `top` types by bytes, and the
    largest module-level dicts, lists and sets by length (MEM-002: after a restart the process grew ~20 MB an hour with the
    caches at a steady size; two of these an hour apart show which kind of object it is). Admin only, on demand: one pass
    over the tracked objects (about a second), nothing kept."""
    counts: dict[str, list[int]] = {}
    for o in gc.get_objects():
        t = type(o).__name__
        c = counts.get(t)
        size = sys.getsizeof(o, 0)
        if c is None:
            counts[t] = [1, size]
        else:
            c[0] += 1
            c[1] += size
    types = sorted(((t, n, b) for t, (n, b) in counts.items()), key=lambda x: -x[2])[:top]
    held = []
    for name, mod in list(sys.modules.items()):
        if not name.startswith("app"):
            continue
        for attr, v in list(vars(mod).items()):
            if isinstance(v, (dict, list, set, deque)) and len(v) >= 100:
                held.append((f"{name}.{attr}", type(v).__name__, len(v)))
    held.sort(key=lambda x: -x[2])
    tracked = sum(b for _, b in counts.values())
    # `types` and `held` see only what the garbage collector tracks: containers, with their own slots. The strings, numbers
    # and bytes inside them are not counted (a page's JSON, parsed, measured 10 MB here for 66 MB held: MEM-3), so the true
    # size of the Python heap is `python_heap` (or, with PYTHONMALLOC=malloc, `rss_split` less the libraries) and the
    # caches' own size is `caches`.
    return {"objects": sum(n for n, _ in counts.values()), "types": [{"type": t, "count": n, "mb": round(b / 1048576, 1)} for t, n, b in types],
            "held": [{"name": n, "kind": k, "len": ln} for n, k, ln in held[:top]], "rss_mb": rss_mb(),
            "tracked_mb": round(tracked / 1048576, 1), "python_heap": python_heap(), "rss_split": rss_split(), "caches": named_caches(top)}


def janitor(every: float = 300.0, sleep=time.sleep):
    """Every few minutes: expired cache entries out, the caches under budget, and the heap trimmed (the jobs do it after
    their own work; this catches what pages and imports left)."""
    while True:
        sleep(every)
        try:
            release_memory(force=True, full=False)
        except Exception as e:
            print("memguard: janitor failed:", str(e)[:120])
