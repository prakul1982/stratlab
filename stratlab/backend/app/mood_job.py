"""The market mood read on a clock (LIVE8A-006): after each market's close, once its closing prints have settled, the mood read for
that session is written for everyone, so the first person to open Pulse after a close sees that session's read, not the previous
one's while it is written (on Saturday 14 Nov the India mood still said "Read Thu 12 Nov" at 08:17 IST, 16 hours after Friday's
close, until someone opened the page).

Bounded: it is tried every five minutes from READ_AT until GIVE_UP in the market's own time on a trading day; once a read is written
(or one was already there for the session) the day is done; past GIVE_UP the day is left to the first visitor, as before. It writes
only through the Pulse route's own read (intel.routes.pulse_ai), with the same key, checks and cache: a read already written for the
session is served, never written again, and it counts against nobody's daily reads."""
import json
import threading
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from . import db, leader

# market -> (its time zone, when the read is first tried, when the day is given up), local times
TIMES = {"IN": ("Asia/Kolkata", "16:10", "21:00"), "US": ("America/New_York", "16:40", "21:30")}
SYSTEM = {"id": "system:mood", "_plan": "pro", "plan": "pro", "email": None}      # the clock, not a person: counts against nobody
KEY = "moodjob:"                  # moodjob:<market> = the last trading day its read was written for


class Job:
    def __init__(self, read=None):
        self.read = read or _pulse_read
        self.status = {"last_run": None, "last_error": None, "written": {}}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="mood-read").start()

    def _loop(self):
        while True:
            try:
                if leader.leading():
                    self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("mood read job:", e)
            time.sleep(300)

    def due(self, region: str, now: datetime) -> date | None:
        """The trading day whose read is due now in `region`, or None (not a trading day, before READ_AT, after GIVE_UP, done)."""
        from .data.calendar import is_trading_day
        tz, at, give_up = TIMES[region]
        local = now.astimezone(ZoneInfo(tz))
        day = local.date()
        hhmm = local.strftime("%H:%M")
        if hhmm < at or hhmm > give_up or not is_trading_day(region, day):
            return None
        if db.get_setting(KEY + region) == day.isoformat():
            return None
        return day

    def tick(self, now: datetime) -> dict:
        """Each market whose read is due: the read asked for once; written (or already there), the day is done."""
        out = {}
        for region in TIMES:
            day = self.due(region, now)
            if not day:
                continue
            try:
                from . import stock_pages
                if stock_pages.settling(region, now):
                    out[region] = "settling"          # its closing prints aren't final yet: the next pass
                    continue
                got = self.read(region)
            except Exception as e:
                out[region] = f"failed: {str(e)[:80]}"
                self.status["last_error"] = out[region]
                continue
            if got and not got.get("unavailable"):
                db.set_setting(KEY + region, day.isoformat())
                self.status["written"][region] = day.isoformat()
                out[region] = "written"
            else:
                out[region] = (got or {}).get("code") or "not yet"
        self.status["last_run"] = now.isoformat(timespec="minutes")
        return out


def _pulse_read(region: str) -> dict:
    """The Pulse route's own mood read for a market, as a dict (its JSON body)."""
    from .intel import routes
    r = routes.pulse_ai(region=region, focus="", refresh=False, profile=SYSTEM)
    try:
        return json.loads(r.body)
    except Exception:
        return {}


job = Job()
