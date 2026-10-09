"""One at a time per key, so a dozen requests that all need the same answer ask for it once.

A page opens with a dozen calls at once, each carrying the same sign-in token for the same person: without this each one
asks the sign-in service whether the token is good and reads the person's profile, a dozen identical round trips
(R9R-010: /mine fired about 17 calls on a cold load). With it the first asks; the others wait for it and then find the
answer in the cache the first filled. The block gets a dict that the calls waiting on the same key share while any of them
is still there, for a note such as "this failed, don't try again" that must not outlive them."""
import threading
from contextlib import contextmanager


class Flights:
    def __init__(self):
        self._lock = threading.Lock()
        self._held: dict[str, list] = {}          # key -> [lock, how many are using it, the shared dict]

    @contextmanager
    def hold(self, key: str):
        """Take the key's lock for the block, yielding the dict shared by everyone holding or waiting on the key; the lock
        and the dict are forgotten when the last of them leaves."""
        with self._lock:
            entry = self._held.setdefault(key, [threading.Lock(), 0, {}])
            entry[1] += 1
        try:
            with entry[0]:
                yield entry[2]
        finally:
            with self._lock:
                entry[1] -= 1
                if entry[1] <= 0 and self._held.get(key) is entry:
                    del self._held[key]

    def __len__(self):
        return len(self._held)
