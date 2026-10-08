"""A background job's last status, kept in the database so it survives a restart (R5O-016).

Jobs keep their status in memory, and a job that already ran today doesn't run again after a restart (its run marker is
in the database), so after every deploy Admin said "Not run yet" for most data feeds until their next scheduled time.
Each job calls keep() when it has run; Admin reads kept(), which is the running server's status once it has run the
job, and until then the last one stored, marked `before_restart`."""
import json
import threading

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
