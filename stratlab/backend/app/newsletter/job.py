"""Building, storing and sending the newsletters.

The Market Brief goes out after each trading day's close (India 16:15 IST, US 16:30 New York) and as a weekly
digest on Saturday morning (IST). My Stocks goes after India's close, or on Saturday, as each reader chose, and only
when something changed for their stocks. Each issue is stored as news:<kind>:<region or uid>:<day>, and every run
is remembered in the database before anything is sent, so a restart never sends twice."""
import json
import re
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .. import alerts, db, newsletter_prefs
from ..plans import access_plan, allows
from . import content, write

KINDS = ("market", "my_stocks")
SEND_AT = {"IN": ("Asia/Kolkata", "16:15"), "US": ("America/New_York", "16:30")}
WEEKLY_AT = ("Asia/Kolkata", 5, "08:00")         # Saturday morning, India time
INDEX_CAP = 60
_ID = re.compile(r"^(market|my_stocks)\.([A-Za-z0-9\-]{1,64})\.(\d{4}-\d{2}-\d{2}(?:-weekly)?)$")


# ---------- storage ----------
def day_key(day: str, weekly: bool) -> str:
    return f"{day}-weekly" if weekly else day


def issue_id(kind: str, scope: str, day: str, weekly: bool) -> str:
    """kind.scope.day, like market.IN.2026-10-02 or my_stocks.<uid>.2026-10-03-weekly."""
    return f"{kind}.{scope}.{day_key(day, weekly)}"


def parse_id(iid: str) -> tuple[str, str, str] | None:
    m = _ID.match(iid or "")
    return m.groups() if m else None


def _key(kind: str, scope: str, dkey: str) -> str:
    return f"news:{kind}:{scope}:{dkey}"


def _index_key(kind: str, scope: str) -> str:
    return f"news-index:{kind}:{scope}"


def _json(raw, default):
    try:
        v = json.loads(raw or "null")
    except (ValueError, TypeError):
        return default
    return v if isinstance(v, type(default)) else default


def load(iid: str) -> dict | None:
    parts = parse_id(iid)
    if not parts:
        return None
    return _json(db.get_setting(_key(*parts)), {}) or None


def ids(kind: str, scope: str) -> list[str]:
    return [i for i in _json(db.get_setting(_index_key(kind, scope)), []) if isinstance(i, str)]


def save(issue: dict) -> dict:
    """Store an issue and put it first in its index (the newest 60 are kept listed)."""
    kind, scope, dkey = parse_id(issue["id"])
    db.set_setting(_key(kind, scope, dkey), json.dumps(issue))
    db.set_setting(_index_key(kind, scope), json.dumps([issue["id"]] + [i for i in ids(kind, scope) if i != issue["id"]][:INDEX_CAP - 1]))
    return issue


def recent(kind: str, scope: str, limit: int = 20) -> list[dict]:
    out = []
    for iid in ids(kind, scope)[:max(1, min(INDEX_CAP, limit))]:
        issue = load(iid)
        if issue:
            out.append(issue)
    return out


def last_issue(kind: str, scope: str) -> dict | None:
    return next(iter(recent(kind, scope, 1)), None)


# ---------- building ----------
def make_issue(facts: dict, scope: str) -> dict:
    s = write.summary(facts)
    issue = {"id": issue_id(facts["kind"], scope, facts["day"], facts["weekly"]), "kind": facts["kind"],
             "region": facts.get("region"), "day": facts["day"], "weekly": facts["weekly"], "subject": write.subject(facts),
             "sections": write.sections(facts), "summary": s["text"], "ai": s["ai"],
             "at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="minutes")}
    if facts["kind"] == "my_stocks":
        issue["uid"] = facts["uid"]
    issue["html"], issue["text"] = write.render(issue)
    return issue


def build_market(region: str, day: date, weekly: bool = False, store: bool = True) -> dict | None:
    """The region's Market Brief for a day (or the week to it): the stored one when it exists, else built now.
    None when every source failed."""
    if store:
        have = load(issue_id("market", region, day.isoformat(), weekly))
        if have:
            return have
    facts = content.market_facts(region, day, weekly)
    if not any(k in facts for k in ("indices", "rotation", "scan", "headlines")):
        return None
    issue = make_issue(facts, region)
    return save(issue) if store else issue


def build_stocks(uid: str, day: date, weekly: bool = False, store: bool = True) -> dict | None:
    """The user's My Stocks issue, or None when nothing changed for their stocks."""
    if store:
        have = load(issue_id("my_stocks", uid, day.isoformat(), weekly))
        if have:
            return have
    last = last_issue("my_stocks", uid)
    facts = content.stock_facts(uid, day, weekly, since=(last or {}).get("at"))
    if not facts["changed"]:
        return None
    issue = make_issue(facts, uid)
    return save(issue) if store else issue


# ---------- readers ----------
def address(profile: dict) -> str | None:
    """Where newsletters go: the alert email set in Account, else the address they sign in with."""
    return alerts.newsletter_email(profile)


def confirmed(profile: dict) -> bool:
    """The reader confirmed that address from the link sent to it."""
    return alerts.email_confirmed(profile)


def allowed(profile: dict, what: str, how: str) -> bool:
    """The plan allows this choice: the weekly Market Brief for everyone, the daily one on Basic and up, My Stocks on Pro."""
    plan = access_plan(profile)
    if what == "my_stocks":
        return allows(plan, "newsletter_stocks")
    return how != "daily" or allows(plan, "newsletter")


def subscribers() -> list[dict]:
    """Each reader's choices, with their uid."""
    out = []
    for _, raw in db.all_settings_with_prefix(newsletter_prefs.KEY):
        sub = _json(raw, {})
        if sub.get("uid"):
            out.append({"uid": sub["uid"], **newsletter_prefs.get(sub["uid"])})
    return out


def teaser(profile: dict, issue: dict):
    """Two lines by phone notification or Telegram, for readers who set those up (the email is already on its way)."""
    quiet = {**profile, "alert_email": None, "email": None}         # never a second email
    if not alerts.jobs_for(quiet, "", ""):
        return
    first = re.split(r"(?<=\.)\s", issue.get("summary") or "", maxsplit=1)[0][:160]
    alerts.notify(quiet, issue["subject"], f"{issue['subject']}\n{first}".strip(), url=f"/news/{issue['id']}")


def deliver(profile: dict, issue: dict, what: str) -> bool:
    """Email the issue (and send the teaser). True when the email went."""
    sent = False
    to = address(profile)
    if to and confirmed(profile) and alerts.email_ready():
        unsub = alerts.unsubscribe_url(profile["id"], what)
        html, text = (x.replace(write.UNSUBSCRIBE, unsub) for x in (issue["html"], issue["text"]))
        try:
            alerts.send_email(to, issue["subject"], text, html=html,
                              headers=alerts.list_unsubscribe_headers(profile["id"], what))
            sent = True
        except Exception as e:
            print("newsletter email failed:", str(e)[:160])
    try:
        teaser(profile, issue)
    except Exception as e:
        print("newsletter teaser failed:", str(e)[:160])
    return sent


# ---------- the schedule ----------
class Job:
    """Checks every five minutes what is due; each run is marked in the database before sending, so it runs once."""

    def __init__(self):
        self.last: dict[str, str] = {}
        self.status = {"last_run": None, "sent": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="newsletters").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("newsletters:", e)
            time.sleep(300)

    def due(self, name: str, now: datetime, tz: str, at: str, region: str | None = None, weekday: int | None = None) -> date | None:
        """The local day when `name` is due now and hasn't run today; a trading day in `region`, or on `weekday`."""
        from ..data.calendar import is_trading_day
        local = now.astimezone(ZoneInfo(tz))
        day = local.date()
        if local.strftime("%H:%M") < at or self.last.get(name) == day.isoformat():
            return None
        if (weekday is not None and day.weekday() != weekday) or (region and not is_trading_day(region, day)):
            return None
        if db.get_setting(f"newsjob:{name}") == day.isoformat():          # already ran today (before a restart)
            self.last[name] = day.isoformat()
            return None
        return day

    def mark(self, name: str, day: date):
        self.last[name] = day.isoformat()
        db.set_setting(f"newsjob:{name}", day.isoformat())

    def tick(self, now: datetime) -> int:
        sent, ran = 0, False
        for region, (tz, at) in SEND_AT.items():
            day = self.due(f"market-{region}", now, tz, at, region=region)
            issue = build_market(region, day) if day else None
            if issue:                      # every source down: try again on the next check
                self.mark(f"market-{region}", day)
                sent, ran = sent + self.send_market(region, issue, False), True
        day = self.due("stocks", now, *SEND_AT["IN"], region="IN")
        if day:
            self.mark("stocks", day)
            sent, ran = sent + self.run_stocks(day, False), True
        tz, weekday, at = WEEKLY_AT
        day = self.due("weekly", now, tz, at, weekday=weekday)
        if day:
            self.mark("weekly", day)
            for region in SEND_AT:
                issue = build_market(region, day, True)
                sent += self.send_market(region, issue, True) if issue else 0
            sent, ran = sent + self.run_stocks(day, True), True
        if ran:
            self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
        return sent

    def send_market(self, region: str, issue: dict, weekly: bool) -> int:
        """Send the region's issue (built once, for everyone) to its readers."""
        what, sent = f"market_{region.lower()}", 0
        for sub in subscribers():
            how = sub.get(what)
            if how == "off":
                continue
            profile = db.get_profile(sub["uid"])
            daily_ok = allowed(profile, what, "daily")
            # daily readers get each day's issue; weekly ones, and daily ones whose plan no longer has it, the digest
            if (not weekly and how == "daily" and daily_ok) or (weekly and (how == "weekly" or not daily_ok)):
                sent += deliver(profile, issue, what)
        return sent

    def run_stocks(self, day: date, weekly: bool) -> int:
        sent, how = 0, "weekly" if weekly else "daily"
        for sub in subscribers():
            if sub.get("my_stocks") != how:
                continue
            profile = db.get_profile(sub["uid"])
            if not allowed(profile, "my_stocks", how):
                continue
            try:
                issue = build_stocks(sub["uid"], day, weekly)
            except Exception as e:
                print("my stocks issue failed:", str(e)[:160])
                continue
            if issue:
                sent += deliver(profile, issue, "my_stocks")
        return sent
