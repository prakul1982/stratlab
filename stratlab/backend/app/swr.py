"""Answer at once from the last read, and read again behind it ("stale while revalidate").

A company page's exchange lists (deals, business updates) took 3 to 9 seconds whenever their hour-long cache had run
out (R46-004: company pages and /research slow on a first visit). Here an answer up to `keep` seconds old is returned
straight away; one older than `fresh` also starts a read in the background for the next visit. Only a page with no
answer kept, or one older than `keep`, waits for the read. A background read that fails keeps the old answer."""
import threading
import time
from typing import Callable

_kept: dict = {}                 # key -> (time read, value)
_busy: set = set()               # keys being read in the background
_lock = threading.Lock()
MAX_KEYS = 2000


def get(key, read: Callable, fresh: float = 3600, keep: float = 86400, now: float | None = None):
    """`read()`'s answer for `key`: the kept one when it is younger than `keep` (read again behind it once it is older
    than `fresh`), else read now (its error raised, as without this)."""
    now = time.time() if now is None else now
    with _lock:
        hit = _kept.get(key)
    if hit is not None and now - hit[0] < keep:
        if now - hit[0] >= fresh:
            _behind(key, read)
        return hit[1]
    value = read()
    _put(key, value)
    return value


def _put(key, value) -> None:
    with _lock:
        if len(_kept) >= MAX_KEYS and key not in _kept:
            _kept.pop(min(_kept, key=lambda k: _kept[k][0]))        # the oldest goes
        _kept[key] = (time.time(), value)


def _behind(key, read: Callable) -> None:
    with _lock:
        if key in _busy:
            return
        _busy.add(key)

    def run():
        try:
            _put(key, read())
        except Exception as e:                                     # the old answer stays
            print("background re-read failed:", key, str(e)[:120])
        finally:
            with _lock:
                _busy.discard(key)
    threading.Thread(target=run, daemon=True).start()


def clear() -> None:
    with _lock:
        _kept.clear()
