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
    "MCX": ("Asia/Kolkata", time(23, 45)),       # after MCX's 23:30 close
    "CDS": ("Asia/Kolkata", time(17, 15)),       # after the currency segment's 17:00 close
    "CMDTY": ("America/New_York", time(17, 10)),  # after CME's 17:00 daily break
    "CRYPTO": ("UTC", time(23, 55)),             # crypto never closes: the report covers the UTC day
}
WINDOW = timedelta(hours=3)                      # after this, a missed report (server down) is skipped
SETTING = "daily_reports_sent"
PREFS = "prefs:"                                 # app_settings key prefix for per-person choices


def due(market: str, now: datetime) -> str | None:
    """The market's local date if its report is due now, else None."""
    if market not in SEND_AT:
        return None
    tz, at = SEND_AT[market]
    local = now.astimezone(ZoneInfo(tz))
    if not is_trading_day(market, local.date()):
        return None
    start = datetime.combine(local.date(), at, tzinfo=local.tzinfo)
    return local.date().isoformat() if start <= local < start + WINDOW else None


def traded_today(sessions: list, market: str, day: str) -> bool:
    """False on a holiday: no session in that market saw a price today, so there's nothing to report."""
    tz = ZoneInfo(SEND_AT[market][0])
    for s in sessions:
        t = getattr(s, "last_tick_at", None)
        try:
            if t and datetime.fromisoformat(str(t)).astimezone(tz).date().isoformat() == day:
                return True
        except ValueError:
            continue
    return False


def _day(v) -> str:
    return str(v)[:10]


def summarise(s, day: str) -> dict:
    """What one session did on `day`: closed trades, their P&L, what's still open, and the account."""
    kind = getattr(s, "kind", "single")
    snap = s.snapshot()
    acct = snap["account"]
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
    return {"name": s.name, "currency": s.inst.get("currency") or ("INR" if getattr(s, "market", "IN") == "IN" else ""),
            "closed": len(trades), "wins": sum(1 for t in trades if t["pnl"] > 0), "pnl": sum(t["pnl"] for t in trades),
            "open": open_n, "unrealised": acct.get("unrealised") or 0.0,
            "equity": acct["equity"], "capital": acct["capital"],
            **({"signals": s.signal_counts(day)} if kind == "signal" else {})}


def _money(x: float, cur: str) -> str:
    """+₹200, −$35: the currency's sign, as everywhere else in the app (a currency without one keeps its code)."""
    from .email_kit import money
    return money(x, cur or "INR", signed=True)


def text(market_name: str, day: str, rows: list[dict]) -> str:
    from .email_kit import fmt_date
    d = fmt_date(day, year=False, weekday=True)
    lines = [f"StratLab daily report: {market_name}, {d}", ""]
    for r in rows:
        total = r["equity"] - r["capital"]
        pct = total / r["capital"] * 100 if r["capital"] else 0
        today = (f"{r['closed']} trade{'s' if r['closed'] != 1 else ''} closed ({r['wins']} won), {_money(r['pnl'], r['currency'])}"
                 if r["closed"] else "No trades closed")
        still = f"; {r['open']} open, {_money(r['unrealised'], r['currency'])} on paper" if r["open"] else ""
        lines.append(f"{r['name']}\n  Today: {today}{still}\n  Since start: {_money(total, r['currency'])} ({pct:+.1f}%)")
        sig = r.get("signals")
        if sig and sig["received"]:
            extra = [f"{sig['late']} late" if sig["late"] else "", f"{sig['refused']} refused" if sig["refused"] else ""]
            extra = [x for x in extra if x]
            lines.append(f"  Signals: {sig['received']} arrived" + (f" ({', '.join(extra)}; see the session's signal log)" if extra else ""))
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
        if self.sent is None:
            try:
                self.sent = json.loads(self.db.get_setting(SETTING) or "{}")
            except Exception:
                self.sent = {}

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
                send(profile, f"StratLab daily report: {market_name(market)}", text(market_name(market), day, rows))
                out.append((uid, market))
            except Exception as e:
                print("daily report failed:", uid, market, e)
        return out
