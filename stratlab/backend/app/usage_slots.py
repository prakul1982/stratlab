"""Usage slots held while a slow call runs, so parallel requests can't each pass the same "used < limit" check."""
import threading
from collections import defaultdict
from contextlib import contextmanager

_lock = threading.Lock()
_held: dict[tuple[str, str], int] = defaultdict(int)


@contextmanager
def hold(user_id: str, kind: str, check):
    """`check(held)` runs under the lock with the number of slots already held (and so about to be used) for this
    user and kind, and raises to refuse. The slot is released when the block ends, however it ends: the caller records
    the usage inside the block on success, so a failed call never uses any of the allowance."""
    key = (user_id, kind)
    with _lock:
        check(_held[key])
        _held[key] += 1
    try:
        yield
    finally:
        with _lock:
            _held[key] -= 1
            if _held[key] <= 0:
                _held.pop(key, None)
