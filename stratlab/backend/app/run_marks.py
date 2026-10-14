"""A job's "ran today" marker that says how far the run got, so a deploy killing it mid-run doesn't lose the rest.

The marker (one setting) is {"day", "status": "running"|"done", "beat", "sent": [recipient ids]}. A run claims it,
records each recipient BEFORE sending to them (at most once: a kill between the record and the send drops that one
message, never doubles it), and marks it done at the end. A "running" marker whose beat is older than STALE seconds
is an unfinished run: the next pass resumes it and skips the recipients already recorded. A fresh one is still being
worked on. A plain day string, as the jobs wrote before, reads as done.

Settings have no compare-and-set; a plain read-then-write is enough because the leader lease (leader.py) keeps one
job runner, bar the brief hand-off on a release.
"""
import json
import time

from . import db

STALE = 600.0          # seconds without a beat before a running marker counts as unfinished
BEAT_EVERY = 60.0      # beat() saves at most this often


def read(key: str) -> dict | None:
    raw = db.get_setting(key)
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        d = None
    if not isinstance(d, dict):
        return {"day": raw, "status": "done", "beat": 0.0, "sent": []}
    return {"day": d.get("day"), "status": d.get("status") or "done", "beat": float(d.get("beat") or 0),
            "sent": [u for u in d.get("sent") or [] if isinstance(u, str)]}


def status(key: str, day: str, now: float | None = None, once: bool = False) -> str | None:
    """None: not started today (or a run to resume: unfinished and quiet), "done", or "running" (live: leave it).
    `once`: the key is already unique to the run, so a marker of any day counts (older ones hold a timestamp)."""
    m = read(key)
    if not m or (m["day"] != day and not once):
        return None
    if m["status"] == "done":
        return "done"
    return "running" if (time.time() if now is None else now) - m["beat"] < STALE else None


class Run:
    def __init__(self, key: str, day: str, sent=()):
        self.key, self.day, self.sent = key, day, list(sent)
        self._seen = set(self.sent)
        self.beat_at = 0.0
        self.save("running")

    def save(self, state: str = "running") -> None:
        self.beat_at = time.time()
        db.set_setting(self.key, json.dumps({"day": self.day, "status": state, "beat": self.beat_at, "sent": self.sent},
                                            separators=(",", ":")))

    def seen(self, uid: str) -> bool:
        return uid in self._seen

    def record(self, uid: str) -> None:
        """Write the recipient down before sending to them."""
        self._seen.add(uid)
        self.sent.append(uid)
        self.save()

    def beat(self) -> None:
        if time.time() - self.beat_at >= BEAT_EVERY:
            self.save()

    def done(self) -> None:
        self.save("done")


def claim(key: str, day: str, now: float | None = None, once: bool = False) -> Run | None:
    """A new run for `day`, or the unfinished one to resume; None when it is done or being worked on."""
    if status(key, day, now, once) is not None:
        return None
    m = read(key)
    return Run(key, day, m["sent"] if m and (m["day"] == day or once) else ())
