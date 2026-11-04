"""A background job's last status, kept in the database so it survives a restart (R5O-016).

Jobs keep their status in memory, and a job that already ran today doesn't run again after a restart (its run marker is
in the database), so after every deploy Admin said "Not run yet" for most data feeds until their next scheduled time.
Each job calls keep() when it has run; Admin reads kept(), which is the running server's status once it has run the
job, and until then the last one stored, marked `before_restart`."""
import json
import threading
import time

from . import db

RUN_KEYS = ("last_run", "read", "recorded", "last_at")
_written: dict[str, str] = {}          # what was last written for each job, so an unchanged status isn't written again
_lock = threading.Lock()


def _has_run(st: dict) -> bool:
    return any(st.get(k) for k in RUN_KEYS)


def kept(key: str, st: dict) -> dict:
    """`st` (a job's status in memory) when it has a run in it, which is then stored; else the stored one."""
    if _has_run(st):
        try:
            text = json.dumps(st, default=str, sort_keys=True)[:4000]
            with _lock:
                fresh = _written.get(key) != text
                _written[key] = text
            if fresh:
                db.set_setting(f"jobstatus:{key}", text)
        except Exception as e:                  # the page still shows what's in memory
            with _lock:
                _written.pop(key, None)
            print("job status: couldn't keep", key, str(e)[:120])
        return st
    try:
        saved = db.json_value(db.get_setting(f"jobstatus:{key}"), {})
    except Exception:
        saved = {}
    return {**saved, "before_restart": True} if _has_run(saved) else st


def keep(key: str, job) -> None:
    """Store a job's status now (called by the job when it has run). Never raises."""
    try:
        kept(key, dict(getattr(job, "status", None) or {}))
    except Exception as e:
        print("job status:", key, str(e)[:120])



class Status(dict):
    """A job's status that stores itself whenever a run is written into it (R6O-003): a job marked as done for the
    day before its run finished (ETF closes, India VIX, the news readers) was stored without its run, and after a
    restart Admin said "Not run yet" beside fresh data. `key` None: kept in memory only."""

    def __init__(self, key: str | None, *a, **kw):
        super().__init__(*a, **kw)
        self.key = key

    def _changed(self, keys) -> None:
        if self.key and any(k in RUN_KEYS and self.get(k) for k in keys):
            try:
                kept(self.key, dict(self))
            except Exception as e:                  # never breaks the job
                print("job status:", self.key, str(e)[:120])

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        self._changed([k])

    def update(self, *a, **kw):
        before = set(self)
        super().update(*a, **kw)
        self._changed(set(kw) | (set(dict(*a)) if a else set()) | (set(self) - before))


# ---------- a job stuck or running too long (LIVE3-006) ----------
# Admin showed "Market breadth · Running · 15 h ago": the running flag beside the last finished run's time, with nothing to say how
# long the run had been going or whether that was too long, and "Needs your attention" silent. Every job row now carries when its run
# started (the runner's own start, else when Admin first saw it running) and is a Problem once it has run longer than STUCK_AFTER.
STUCK_AFTER = 2 * 3600          # seconds: longer than any job's run takes (India's first breadth run, the longest, is 20 to 25 minutes)
_seen_running: dict[str, float] = {}


def running_since(key: str, running: bool, started: float | None = None) -> float | None:
    """When a job's current run began (epoch seconds), or None when it isn't running: the runner's own start when it keeps one,
    else the first time it was seen running."""
    if not running:
        _seen_running.pop(key, None)
        return None
    if started:
        _seen_running.pop(key, None)
        return float(started)
    return _seen_running.setdefault(key, time.time())


class JobTimeout(RuntimeError):
    pass


def bounded(fn, seconds: float, what: str):
    """fn() in its own thread, waited for at most `seconds`: a run whose source never answers no longer holds its job's thread (and
    every later run) for ever (LIVE3-006). Past the limit JobTimeout is raised and the job tries again at its next turn; the stuck
    thread is left to end on its own (a Python thread can't be stopped), and the runner lets a new run take over from it."""
    box: dict = {}

    def work():
        try:
            box["out"] = fn()
        except BaseException as e:          # handed to the caller
            box["err"] = e
    t = threading.Thread(target=work, daemon=True, name=f"job-{what}")
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise JobTimeout(f"{what} ran longer than {round(seconds / 60)} minutes and was stopped; it runs again at its next turn.")
    if "err" in box:
        raise box["err"]
    return box.get("out")
