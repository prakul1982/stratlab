"""A short paper trading report after each market closes, sent by Telegram or email to people who
turned alerts on. One message per person per market per day, covering every session they run there."""
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .data.calendar import is_trading_day

# when to send, in the market's own time: a few minutes after the close, so the last candle is in
SEND_AT = {
    "IN": ("Asia/Kolkata", time(15, 45)),       # after the derivatives segment's 15:40 close (data/sessions.py)
    "US": ("America/New_York", time(16, 10)),
    "UK": ("Europe/London", time(16, 40)),
    "EU": ("Europe/Berlin", time(17, 40)),
    "JP": ("Asia/Tokyo", time(15, 40)),
    "FX": ("America/New_York", time(17, 5)),     # the forex day ends at 17:00 New York
    "MCX": ("Asia/Kolkata", time(23, 40)),       # 10 minutes after MCX's 23:30 close (see start(): 00:05 on the next day once it closes at 23:55)
    "CDS": ("Asia/Kolkata", time(17, 15)),       # after the currency segment's 17:00 close
    "CMDTY": ("America/New_York", time(17, 10)),  # after CME's 17:00 daily break
    "CRYPTO": ("UTC", time(23, 55)),             # crypto never closes: the report covers the UTC day
}
MCX_AFTER = timedelta(minutes=10)                # MCX's report goes out this long after its close
WINDOW = timedelta(hours=3)                      # after this, a missed report (server down) is skipped
SETTING = "daily_reports_sent"
PREFS = "prefs:"                                 # app_settings key prefix for per-person choices


def start(market: str, day: date) -> datetime:
    """When the report for `day` may go out, in the market's own time: after the close, which for MCX is 23:30 or, while
    US daylight saving is off, 23:55 (options/data.py), so that report goes out after midnight."""
    tz, at = SEND_AT[market]
    if market == "MCX":
        from .options.data import expiry_time
        return datetime.combine(day, datetime.strptime(expiry_time("MCX", day), "%H:%M").time(), tzinfo=ZoneInfo(tz)) + MCX_AFTER
    return datetime.combine(day, at, tzinfo=ZoneInfo(tz))


def due(market: str, now: datetime) -> str | None:
    """The report day (a date in the market's own time) if its report is due now, else None. A window that opens late
    in the evening runs past midnight, so yesterday is the report day while still inside its window."""
    if market not in SEND_AT:
        return None
    local = now.astimezone(ZoneInfo(SEND_AT[market][0]))
    for day in (local.date(), local.date() - timedelta(days=1)):
        if is_trading_day(market, day) and start(market, day) <= local < start(market, day) + WINDOW:
            return day.isoformat()
    return None


def traded_today(sessions: list, market: str, day: str) -> bool:
    """False on a holiday: no session in that market saw a price that day, so there's nothing to report. A price from a
    later day counts (a report sent after midnight, while crypto and MCX sessions already have the new day's prices)."""
    tz = zone_of(market)
    for s in sessions:
        t = getattr(s, "last_tick_at", None)
        try:
            if t and datetime.fromisoformat(str(t)).astimezone(tz).date().isoformat() >= day:
                return True
        except ValueError:
            continue
    return False


def zone_of(market: str) -> ZoneInfo:
    """The one zone a report's day is counted in: the market's own (UTC for crypto), the same one `due` and
    `traded_today` use."""
    return ZoneInfo(SEND_AT.get(market, ("UTC", None))[0])


def day_of(v, tz: ZoneInfo) -> str:
    """The date of a stamp in the report's zone. A stamp with a zone (a signal session's trades carry India's, its
    signal log UTC) is converted; one without is already the market's own time (a bar's time)."""
    try:
        t = datetime.fromisoformat(str(v))
    except ValueError:
        return str(v)[:10]
    return (t.astimezone(tz) if t.tzinfo else t).date().isoformat()


def summarise(s, day: str) -> dict:
    """What one session did on `day`: closed trades, their P&L, what's still open, and the account."""
    kind = getattr(s, "kind", "single")
    snap = s.snapshot()
    acct = snap["account"]
    tz = zone_of(getattr(s, "market", "IN"))
    _day = lambda v: day_of(v, tz)
    if kind == "group":
        trades = [t for m in s.members for t in m.engine.trades if _day(t["exit_t"]) == day]
        open_n = acct.get("open", 0)
    elif snap.get("kind") == "options":
        trades = [t for t in s.engine.trades if _day(t["closed"]) == day]
        open_n = 1 if snap.get("position") else 0
    elif kind == "signal":                      # moved by outside signals: today's trades and what became of the signals
        trades = [t for t in s.trades if _day(t["exit_t"]) == day]
        open_n = 1 if acct.get("qty") else 0
    else:
        trades = [t for t in s.engine.trades if _day(t["exit_t"]) == day]
        open_n = 1 if acct.get("qty") else 0
    return {"name": s.name, "currency": s.inst.get("currency") or ("INR" if getattr(s, "market", "IN") == "IN" else "USD"),
            "closed": len(trades), "wins": sum(1 for t in trades if t["pnl"] > 0), "pnl": sum(t["pnl"] for t in trades),
            "open": open_n, "unrealised": acct.get("unrealised") or 0.0,
            "equity": acct["equity"], "capital": acct["capital"],
            **({"signals": s.signal_counts(day)} if kind == "signal" else {})}


def _money(x: float, cur: str) -> str:
    """+₹200, −$35: the currency's sign, as everywhere else in the app (a currency without one keeps its code)."""
    from .email_kit import money
    return money(x, cur or "INR", signed=True)


def _pct(x: float) -> str:
    """+2.5%, −5.5% with the same real minus as the amount beside it (R28-008); a move that rounds to zero has no sign."""
    from .email_kit import pct
    return pct(x, 1)


def text(market_name: str, day: str, rows: list[dict]) -> str:
    """The report in the shape the alert emails read: each session a small card (its name over rows "label: figure"), the signed amounts in
    green and red, and the same lines as plain text for a phone message (LIVE1C-034: every session was a block of one-weight sentences)."""
    from .email_kit import fmt_date
    d = fmt_date(day, year=False, weekday=True)
    lines = [f"StratLab daily report: {market_name}, {d}", ""]
    for r in rows:
        total = r["equity"] - r["capital"]
        pct = total / r["capital"] * 100 if r["capital"] else 0
        lines.append(f"{r['name']}:")
        if r["closed"]:
            lines += [f"- Trades closed today: {r['closed']} ({r['wins']} won)", f"- Result of those: {_money(r['pnl'], r['currency'])}"]
        else:
            lines.append("- Trades closed today: none")
        if r["open"]:
            lines.append(f"- Open now: {r['open']}, {_money(r['unrealised'], r['currency'])} on paper")
        lines.append(f"- Since the start: {_money(total, r['currency'])} ({_pct(pct)})")
        sig = r.get("signals")
        if sig and sig["received"]:
            extra = [f"{sig['late']} late" if sig["late"] else "", f"{sig['refused']} refused" if sig["refused"] else ""]
            extra = [x for x in extra if x]
            lines.append(f"- Signals: {sig['received']} arrived" + (f" ({', '.join(extra)}; see the session's signal log)" if extra else ""))
    lines += ["", "Paper trading only: no real orders. Turn this report off in Settings → Notifications → Alerts."]
    return "\n".join(lines)


def wants_report(db, uid: str) -> bool:
    try:
        return json.loads(db.get_setting(PREFS + uid) or "{}").get("daily_report", True)
    except Exception:
        return True


class Reporter:
    def __init__(self, db):
        self.db = db
        self.sent: dict[str, str] | None = None          # "user:market" -> last day sent

    def _load(self):
        """The sent list as the database has it now (another container may have led and sent since), merged with what
        this one marked: the newer day per key wins, so a stale copy is never written back."""
        try:
            stored = json.loads(self.db.get_setting(SETTING) or "{}")
            if not isinstance(stored, dict):
                stored = {}
        except Exception:
            stored = {}
        merged = dict(self.sent or {})
        for k, v in stored.items():
            if v >= merged.get(k, ""):
                merged[k] = v
        self.sent = merged

    def run(self, sessions: list, now: datetime | None = None, *, can_alert, send, market_name) -> list[tuple[str, str]]:
        """Send what's due. Returns (user, market) pairs sent, for tests and logs."""
        now = now or datetime.now(timezone.utc)
        groups: dict[tuple[str, str], list] = {}
        for s in sessions:
            groups.setdefault((s.user_id, getattr(s, "market", "IN")), []).append(s)
        out = []
        for (uid, market), items in groups.items():
            day = due(market, now)
            if not day:
                continue
            self._load()
            key = f"{uid}:{market}"
            if self.sent.get(key) == day:
                continue
            self.sent[key] = day                          # mark first: a failure mustn't cause a flood of retries
            self.sent = {k: v for k, v in self.sent.items() if v >= (date.fromisoformat(day) - timedelta(days=7)).isoformat()}
            try:
                self.db.set_setting(SETTING, json.dumps(self.sent))
            except Exception as e:
                print("could not save the report log:", e)
            try:
                if not traded_today(items, market, day):
                    continue
                profile = self.db.get_profile(uid)
                if not can_alert(profile) or not wants_report(self.db, uid):
                    continue
                rows = [summarise(s, day) for s in sorted(items, key=lambda x: x.name)]
                # the subject names the day, as every other email's does (R69-006: "StratLab daily report: India" alone)
                from .email_kit import fmt_date
                send(profile, f"StratLab daily report: {market_name(market)}, {fmt_date(day, year=False, weekday=True)}",
                     text(market_name(market), day, rows))
                out.append((uid, market))
            except Exception as e:
                print("daily report failed:", uid, market, e)
        return out
