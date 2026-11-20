"""The market mood read on a clock (LIVE8A-006): after each market's close, once its closing prints have settled, the mood read for
that session is written for everyone, so the first person to open Pulse after a close sees that session's read, not the previous
one's while it is written (on Saturday 14 Nov the India mood still said "Read Thu 12 Nov" at 08:17 IST, 16 hours after Friday's
close, until someone opened the page).

Bounded: it is tried every five minutes from READ_AT until GIVE_UP in the market's own time on a trading day; once a read is written
(or one was already there for the session) the day is done; past GIVE_UP the day is left to the first visitor, as before. It writes
only through the Pulse route's own read (intel.routes.pulse_ai), with the same key, checks and cache: a read already written for the
session is served, never written again, and it counts against nobody's daily reads.

LIVE9A-001: the job wrote only the AI's headlines read; the Mood card itself (the headline, its lines and every table: intel/mood.py's
payload) was still read again only when someone opened the page, so at 00:54 IST on Tue 17 Nov India's card said "Read Sat 14 Nov" over
the 16 Nov index levels. The job now reads that payload too, and a day is done only when both are of the session that closed.

LIVE10A-001: India's read was first tried at 16:10 IST, 40 minutes after the 15:30 close, so a visit in between (16:05 IST on 17 Nov) got
the 14:47 intraday read still saying "so far today"; it is now tried from 15:45 IST, once the closing auction (to 15:40) is done. A day
whose read is still not written an hour after it was first tried is a check in the self-healing sweep (re-run, then Needs your attention)
and a line in the logs, so a read that stops running is seen before a visitor sees an old session.

LIVE11A-002: a day is done only when the card's tables carry the breadth count of the session that closed (see intel/mood.tables_of)."""
import json
import threading
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from . import autofix, db, leader

# market -> (its time zone, when the read is first tried, when the day is given up), local times
TIMES = {"IN": ("Asia/Kolkata", "15:45", "21:00"), "US": ("America/New_York", "16:40", "21:30")}
SYSTEM = {"id": "system:mood", "_plan": "pro", "plan": "pro", "email": None}      # the clock, not a person: counts against nobody
KEY = "moodjob:"                  # moodjob:<market> = the last trading day its read was written for
# fix11 (LIVE10A-010): the Mood card read once soon after each open too, so the first visit of a session is answered with that session's
# figures, not the read kept from the night before ("16 Nov session · the 17 Nov session's are being read" at 13:28 IST). One read per
# market per trading day, the card's tables only (no AI read).
OPEN_TIMES = {"IN": ("Asia/Kolkata", "09:30", "15:00"), "US": ("America/New_York", "09:45", "15:30")}
OPEN_KEY = "moodjob-open:"
# LIVE15A-002: at 14:36 IST India's card still carried its 09:34 read (a "Mixed … NIFTY 50 down" line, a 178/318 count and Nifty Bank
# +0.06% under live rows of NIFTY 50 +1.02% and NIFTY BANK +1.51%) because nobody had opened the page since the open's read. While a
# market trades (from its open read to its close) the card is read again every SESSION_EVERY seconds, at most SESSION_MAX times a day.
SESSION_EVERY = 900.0
SESSION_MAX = 30
LATE_AFTER = 60                   # minutes after READ_AT with no read written: the day is late (LIVE10A-001)


class Job:
    def __init__(self, read=None, mood=None, opening=None, session=None, warm=None):
        self.read = read or _pulse_read
        self.warm = warm                         # LIVE20A-002: the first pass takes up each market's kept card (an older release's read again)
        self._warmed = False
        self.mood = mood or _mood_payload        # LIVE9A-001: the Mood card's own payload, of the session that closed
        self.opening = opening                   # fix11: the card's payload read once after the open (the clock's job sets it)
        self.session = session                   # LIVE15A-002: the card's payload read again during the session (the clock's job sets it)
        self._in_session: dict[str, tuple[str, int, float]] = {}      # market -> (day, reads today, when the last one was asked)
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

    def late(self, region: str, now: datetime) -> str | None:
        """LIVE10A-001: what is wrong when the read of today's session is still not written LATE_AFTER minutes after it was first
        tried (and the day not yet given up), else None."""
        day = self.due(region, now)
        if not day:
            return None
        tz, at, _ = TIMES[region]
        local = now.astimezone(ZoneInfo(tz))
        first = datetime.combine(day, datetime.strptime(at, "%H:%M").time(), ZoneInfo(tz))
        mins = int((local - first).total_seconds() // 60)
        if mins < LATE_AFTER:
            return None
        last = (self.status.get("last_seen") or {}).get(region) or "no pass of the job yet"
        return f"The {region} mood read of {day.isoformat()} is not written {mins} min after it was first tried ({last})."

    def checks(self, now: datetime | None = None) -> list:
        """LIVE10A-001: one self-healing check per market: late when its read isn't written an hour after the close's read time; the
        remedy runs a pass of the job at once."""
        now = now or datetime.now(timezone.utc)
        return [autofix.Check(id=f"job:mood-read:{r}", name=f"Market mood read after the close ({r})", problem=self.late(r, now),
                              fix=lambda: self.tick(datetime.now(timezone.utc)), fix_text="ran the mood read again",
                              action="Open Admin → Data and jobs and press Log for the mood read: it says what the read waited on.",
                              to="/admin/data") for r in TIMES]

    def open_due(self, region: str, now: datetime) -> date | None:
        """The trading day whose after-the-open read is due now in `region`, or None."""
        from .data.calendar import is_trading_day
        tz, at, until = OPEN_TIMES[region]
        local = now.astimezone(ZoneInfo(tz))
        day, hhmm = local.date(), local.strftime("%H:%M")
        if hhmm < at or hhmm > until or not is_trading_day(region, day) or db.get_setting(OPEN_KEY + region) == day.isoformat():
            return None
        return day

    def tick_open(self, now: datetime) -> dict:
        """Each market just opened: its Mood card read once for the session; done when the read is of today's session."""
        out = {}
        for region in OPEN_TIMES if self.opening else ():
            day = self.open_due(region, now)
            if not day:
                continue
            try:
                session = self.opening(region)
            except Exception as e:
                out[region] = f"failed: {str(e)[:80]}"
                print(f"mood read job: {region} {day} open: {out[region]}")
                continue
            if session == day.isoformat():
                db.set_setting(OPEN_KEY + region, day.isoformat())
                out[region] = "written"
            else:
                out[region] = f"tables of {session or 'no session'}"
        return out

    def tick_session(self, now: datetime) -> dict:
        """LIVE15A-002: each market trading now (after its open read's time, before its close) has its Mood card read again when its last
        such read was asked SESSION_EVERY ago, at most SESSION_MAX times a day, so a visit mid-session never gets the morning's read."""
        from .data.calendar import is_trading_day
        from .intel.company import market_open
        out = {}
        for region in OPEN_TIMES if self.session else ():
            tz, at, _ = OPEN_TIMES[region]
            local = now.astimezone(ZoneInfo(tz))
            day = local.date().isoformat()
            if local.strftime("%H:%M") < at or not is_trading_day(region, local.date()) or not market_open(region, now):
                continue
            was_day, n, last = self._in_session.get(region, ("", 0, 0.0))
            if was_day != day:
                n, last = 0, 0.0
            if n >= SESSION_MAX or now.timestamp() - last < SESSION_EVERY:
                continue
            self._in_session[region] = (day, n + 1, now.timestamp())
            try:
                out[region] = self.session(region) or "no session"
            except Exception as e:
                out[region] = f"failed: {str(e)[:80]}"
                print(f"mood read job: {region} {day} in session: {out[region]}")
        return out

    def tick(self, now: datetime) -> dict:
        """Each market whose read is due: the read asked for once; written (or already there), the day is done."""
        if self.warm and not self._warmed:
            self._warmed = True
            for region in TIMES:
                try:
                    self.warm(region)
                except Exception as e:
                    print("mood read job: warm:", region, str(e)[:120])
        try:
            self.tick_open(now)
        except Exception as e:
            print("mood read job: open read:", str(e)[:120])
        try:
            self.tick_session(now)
        except Exception as e:
            print("mood read job: in-session read:", str(e)[:120])
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
                # LIVE9A-001: the card's tables and headline first (no AI in them, so they never wait on it); a payload still of an
                # earlier session (the closes not in yet) is tried again on the next pass, as an AI read not possible yet is
                session = self.mood(region, day.isoformat())
                if session != day.isoformat():
                    out[region] = f"tables of {session or 'no session'}"
                    print(f"mood read job: {region} {day}: {out[region]}")
                    continue
                got = self.read(region)
            except Exception as e:
                out[region] = f"failed: {str(e)[:80]}"
                self.status["last_error"] = out[region]
                print(f"mood read job: {region} {day}: {out[region]}")        # LIVE9A-001: a day not written is seen in the logs
                continue
            if got and not got.get("unavailable"):
                db.set_setting(KEY + region, day.isoformat())
                self.status["written"][region] = day.isoformat()
                out[region] = "written"
            else:
                out[region] = (got or {}).get("code") or "not yet"
                print(f"mood read job: {region} {day}: AI read {out[region]}")
        self.status["last_run"] = now.isoformat(timespec="minutes")
        self.status.setdefault("last_seen", {}).update(out)       # what each market's last pass got (LIVE10A-001: said by the late check)
        for region in out:
            why = self.late(region, now)
            if why:
                print("mood read job: late:", why)
        return out


def _pulse_read(region: str) -> dict:
    """The Pulse route's own mood read for a market, as a dict (its JSON body)."""
    from .intel import routes
    r = routes.pulse_ai(region=region, focus="", refresh=False, profile=SYSTEM)
    try:
        return json.loads(r.body)
    except Exception:
        return {}


def _mood_payload(region: str, day: str | None = None) -> str | None:
    """LIVE9A-001: the Mood card's payload read now and kept (memory and the database) for everyone; the session it is of. One kept since
    the close for `day` is not read again (a pass that waits only on the AI read)."""
    from .intel import mood as mood_mod
    from .intel import routes
    hub = routes.mood_hub()
    hit = hub.payloads.kept(region)
    # LIVE11A-002: the day is done only once the tables carry that session's breadth count too; until the evening count lands each pass
    # reads again (the US read of 16:47 ET carried the previous session's count under the day's index moves)
    if day and hit and not (hit[1] or {}).get("is_open") and mood_mod.tables_of(hit[1]) == day:
        return day
    return mood_mod.tables_of(hub.refresh_now(region))


def _mood_open(region: str) -> str | None:
    """fix11: the Mood card's payload read now, during the session, and kept for everyone; the session it is of."""
    from .intel import routes
    return (routes.mood_hub().refresh_now(region) or {}).get("session")


def _mood_warm(region: str) -> None:
    """LIVE20A-002: the kept card taken up as the server starts; one kept by an earlier release is read again now (in the background)."""
    from .intel import routes
    routes.mood_hub().warm(region)


job = Job(opening=_mood_open, session=_mood_open, warm=_mood_warm)
autofix.source(lambda: job.checks())          # LIVE10A-001: a read not written an hour after its time is re-run, then shown to the owner
