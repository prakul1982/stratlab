"""Records option chains during market hours, so option strategies can be backtested on real prices later.

Every few minutes it saves each chosen underlying's chain (current and next expiry, strikes around the
money): bid, ask, last price and open interest for every call and put, plus the spot price. Kite has no
history for expired options, so this recording is the only way to build one."""
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone

from ..data.calendar import is_trading_day

IST = timezone(timedelta(hours=5, minutes=30))
OPEN, CLOSE = dtime(9, 15), dtime(15, 30)
AROUND = 15                     # strikes each side of the money


def parse_targets(text: str) -> list[tuple[str, str]]:
    out = []
    for part in (text or "").split(","):
        if ":" in part:
            ex, name = part.strip().split(":", 1)
            if ex.upper() in ("NFO", "BFO") and name.strip():
                out.append((ex.upper(), name.strip().upper()))
    return out


def in_hours(now: datetime) -> bool:
    local = now.astimezone(IST)
    return is_trading_day("IN", local.date()) and OPEN <= local.time() <= CLOSE


def compact(chain: dict) -> list[list]:
    """[strike, ce bid, ce ask, ce ltp, ce oi, pe bid, pe ask, pe ltp, pe oi] per strike: about a third the size of the full rows."""
    def q(x):
        x = x or {}
        r2 = lambda v: round(v, 2) if isinstance(v, float) else v
        return [r2(x.get("bid")), r2(x.get("ask")), r2(x.get("ltp")), x.get("oi")]
    return [[r["strike"], *q(r.get("ce")), *q(r.get("pe"))] for r in chain.get("rows") or []]


class Recorder:
    def __init__(self, data, save, targets: list[tuple[str, str]], every_minutes: int = 5, prune=None, keep_days: int = 0):
        self.data, self.save = data, save          # save(row) writes one snapshot to the database
        self.prune, self.keep_days = prune, keep_days   # prune(iso) deletes snapshots older than iso
        self._pruned_day = None
        self.targets, self.every = targets, max(1, every_minutes) * 60
        self.status = {"enabled": bool(targets), "targets": [f"{e}:{n}" for e, n in targets], "every_minutes": self.every // 60,
                       "today": 0, "day": None, "last_at": None, "last_error": None,
                       "keep_days": keep_days}
        self._next = 0.0

    def prune_old(self, now: datetime):
        """Once a day, delete recordings older than keep_days so the database doesn't fill up."""
        day = now.astimezone(IST).date().isoformat()
        if not self.prune or self.keep_days <= 0 or self._pruned_day == day:
            return
        self._pruned_day = day
        try:
            self.prune((now - timedelta(days=self.keep_days)).isoformat())
        except Exception as e:
            self.status["last_error"] = f"clean-up: {str(e)[:200]}"

    def run_once(self, now: datetime | None = None) -> int:
        """Record every target now if it's due. Returns how many snapshots were saved."""
        now = now or datetime.now(timezone.utc)
        if self.targets:
            self.prune_old(now)
        if not self.targets or not in_hours(now) or not self.data.ready():
            return 0
        day = now.astimezone(IST).date().isoformat()
        if self.status["day"] != day:
            self.status.update(day=day, today=0)
        saved = 0
        for ex, name in self.targets:
            for choice in ("current", "next"):
                try:
                    ch = self.data.chain(ex, name, choice, around=AROUND)
                    if not ch.get("rows") or ch.get("spot") is None:
                        continue
                    if choice == "next" and ch["expiry"] == self.data.pick_expiry(ex, name, "current"):
                        continue          # only one expiry listed
                    self.save({"taken_at": now.isoformat(), "exchange": ex, "name": name, "expiry": ch["expiry"],
                               "spot": ch["spot"], "lot": ch.get("lot"), "chain": compact(ch)})
                    saved += 1
                except Exception as e:
                    msg = str(e)
                    if "option_snapshots" in msg:     # the table isn't there yet
                        msg = "The option_snapshots table is missing: run supabase/schema.sql again in the Supabase SQL editor."
                    self.status["last_error"] = f"{ex}:{name} {choice}: {msg[:200]}"
                    print("option snapshot failed:", self.status["last_error"])
        if saved:
            self.status["today"] += saved
            self.status["last_at"] = now.isoformat()
        return saved

    def start(self):
        if not self.targets:
            return

        def loop():
            while True:
                t = time.time()
                if t >= self._next:
                    self._next = t + self.every
                    try:
                        self.run_once()
                    except Exception as e:
                        self.status["last_error"] = str(e)[:200]
                time.sleep(15)
        threading.Thread(target=loop, daemon=True, name="option-recorder").start()
