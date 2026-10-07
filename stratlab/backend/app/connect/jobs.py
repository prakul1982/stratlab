"""The background work of "connect once": the daily Interactive Brokers read, and the reminder when no statement has
arrived in the inbox for 40 days. One thread checks every 30 minutes; each piece decides for itself whether it is due."""
import threading
import time
from datetime import datetime, timezone

from .. import alerts
from . import ibkr, state, sync
from .redact import mask

REMIND_AFTER_DAYS = 40
CHECK_EVERY = 1800

REMINDER_SUBJECT = "No statement has reached your StratLab inbox in 40 days"
REMINDER_TEXT = ("Your monthly statements usually arrive by the 10th. If your email filter has stopped, check it, or upload this "
                 "month's statement by hand in Settings, Connected accounts.")


def _days_since(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    return (now - datetime.fromisoformat(iso).astimezone(timezone.utc)).total_seconds() / 86400


def reminder_due(box: dict, now: datetime) -> bool:
    """An inbox that has had no statement for 40 days since it was made (or since the last one), and wasn't reminded in the
    last 40 days."""
    if not box.get("local"):
        return False
    ok_at = (box.get("last") or {}).get("at") if (box.get("last") or {}).get("status") == "ok" else None
    quiet = _days_since(ok_at or box.get("created_at"), now)
    if quiet is None or quiet < REMIND_AFTER_DAYS:
        return False
    since_reminder = _days_since(box.get("reminded_at"), now)
    return since_reminder is None or since_reminder >= REMIND_AFTER_DAYS


def run_reminders(now: datetime | None = None) -> int:
    """Remind each user whose inbox is quiet. Each reminder is marked before it is sent, so it goes once. How many sent."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    for uid, rec in state.everyone():
        box = rec.get("inbox") or {}
        if not reminder_due(box, now):
            continue
        state.update(uid, "inbox", reminded_at=now.isoformat(timespec="seconds"))
        profile = sync.profile_for(uid)
        if not profile:
            continue
        try:
            alerts.notify(profile, REMINDER_SUBJECT, REMINDER_TEXT, background=False, url="/settings#accounts")
            sent += 1
        except Exception as e:
            print("statement inbox reminder failed:", mask(type(e).__name__))
    return sent


class Job:
    def __init__(self):
        self.status = {"last_run": None, "ibkr": None, "ibkr_at": None, "reminders": 0, "reminders_at": None, "last_error": None}
        self.lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self.lock.locked()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="connect-once").start()

    def tick(self, now: datetime | None = None, part: str = "all") -> None:
        """One pass: the daily read (`ibkr`), the quiet-inbox reminders (`reminders`), or both. Each is the same work the
        timer does: only the users that are due are touched."""
        now = now or datetime.now(timezone.utc)
        stamp = now.isoformat(timespec="seconds")
        if part in ("all", "ibkr"):
            self.status["ibkr"] = ibkr.run_daily(now)
            self.status["ibkr_at"] = stamp
        if part in ("all", "reminders"):
            self.status["reminders"] = run_reminders(now)
            self.status["reminders_at"] = stamp
        self.status["last_run"] = stamp

    def run_now(self, part: str = "all") -> bool:
        """For the admin's Run now: in the background, one at a time. False when a pass is already running."""
        if part not in ("all", "ibkr", "reminders") or not self.lock.acquire(blocking=False):
            return False

        def work():
            try:
                self.tick(part=part)
                self.status["last_error"] = None
            except Exception as e:
                self.status["last_error"] = mask(str(e))[:200]
                print("connect-once job:", mask(type(e).__name__))
            finally:
                self.lock.release()
        threading.Thread(target=work, daemon=True, name="connect-once-now").start()
        return True

    def _loop(self):
        time.sleep(120)                              # after start-up traffic
        while True:
            try:
                with self.lock:
                    self.tick()
                self.status["last_error"] = None
            except Exception as e:
                self.status["last_error"] = mask(str(e))[:200]
                print("connect-once job:", mask(type(e).__name__))
            time.sleep(CHECK_EVERY)
