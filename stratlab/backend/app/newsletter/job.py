"""Building, storing and sending the newsletters.

The Market Brief goes out after each trading day's close (India 16:15 IST, US 16:50 New York, once the closing prints
have settled) and as a weekly
digest on Saturday morning (IST). My Stocks goes after India's close, or on Saturday, as each reader chose, and only
when something changed for their stocks. Each issue is stored as news:<kind>:<region or uid>:<day>, and every run
is remembered in the database before anything is sent, so a restart never sends twice."""
import json
import re
import threading
import time
from datetime import date, datetime, time as clock, timedelta
from zoneinfo import ZoneInfo

import httpx

from .. import alerts, db, email_kit as kit, leader, newsletter_prefs, run_marks
from ..plans import allows, plan_of
from . import content, write

KINDS = ("market", "my_stocks")
# the US brief waits for the closing prints to settle, as the public pages do (stock_pages.settle: 45 minutes after the
# 16:00 close), so its stock lines are the final closes (R13-003: built at 16:32 ET, V +2.83%, MA +2.56%, UNH +2.16%
# against final closes of +2.76%, +2.50% and +2.25%)
SEND_AT = {"IN": ("Asia/Kolkata", "16:15"), "US": ("America/New_York", "16:50")}
SEND_WORDS = "India 4:15 PM IST and US 4:50 PM New York time"     # what the pages promise (SEND_AT)
WEEKLY_AT = ("Asia/Kolkata", 5, "08:00")         # Saturday morning, India time
AFTER_CLOSE = {"market-IN", "market-US", "stocks"}   # issues built from the day's closes: never before they are final
INDEX_CAP = 60
# a send that couldn't start because the database timed out (15 Oct: the India brief went 19 minutes late) is tried again
# after these pauses, within the same check, before waiting for the next one
START_RETRY_PAUSES = (60, 120)
STOCKS_WAIT = timedelta(minutes=60)      # My stocks waits this long past the India slot for the brief, then goes without it
LATE_AFTER = timedelta(minutes=30)       # a daily brief not on its way this long after its slot: the admins are told
LATE_KEY = "newslate:"                   # app_settings: the day a region's late alert went, so a restart doesn't send it twice
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


def load(iid: str) -> dict | None:
    parts = parse_id(iid)
    if not parts:
        return None
    issue = db.json_value(db.get_setting(_key(*parts)), {}) or None
    return _plain_heads(issue) if issue else None


def _stored(iid: str) -> dict | None:
    """An issue exactly as stored, for the one-off repairs that rewrite what is stored."""
    parts = parse_id(iid)
    return (db.json_value(db.get_setting(_key(*parts)), {}) or None) if parts else None


def _plain_heads(issue: dict) -> dict:
    """A stored issue's Headlines by today's rules: a brief kept from before a headline rule was added shows (and
    re-sends) none of the stories that rule leaves out (R49-001: "Traders see it going even higher" on a brief stored the
    day before)."""
    from ..intel.news import plain_headline
    secs = issue.get("sections")
    if not isinstance(secs, list) or not any(isinstance(s, dict) and s.get("title") == "Headlines" for s in secs):
        return issue
    out = []
    for s in secs:
        if isinstance(s, dict) and s.get("title") == "Headlines":
            s = {**s, "items": [i for i in s.get("items") or [] if isinstance(i, dict) and plain_headline(i.get("text"))]}
            if not s["items"]:
                continue
        out.append(s)
    return {**issue, "sections": out}


def ids(kind: str, scope: str) -> list[str]:
    return [i for i in db.json_value(db.get_setting(_index_key(kind, scope)), []) if isinstance(i, str)]


def save(issue: dict) -> dict:
    """Store an issue and put it first in its index (the newest 60 are kept listed). A reader's My Stocks issue that
    falls off the index is deleted with its sent-to ledger: nothing lists it, and each reader adds one a day."""
    kind, scope, dkey = parse_id(issue["id"])
    db.set_setting(_key(kind, scope, dkey), json.dumps(issue))
    old = ids(kind, scope)
    kept = [issue["id"]] + [i for i in old if i != issue["id"]][:INDEX_CAP - 1]
    db.set_setting(_index_key(kind, scope), json.dumps(kept))
    if kind == "my_stocks":
        for iid in old:
            if iid not in kept and (parts := parse_id(iid)):
                try:
                    db.delete_setting(_key(*parts))
                    db.delete_setting(SENT + iid)
                except Exception as e:             # a row left behind never stops a save
                    print("newsletters: couldn't prune", iid, str(e)[:120])
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
    sections = write.sections(facts)
    issue = {"id": issue_id(facts["kind"], scope, facts["day"], facts["weekly"]), "kind": facts["kind"],
             "region": facts.get("region"), "day": facts["day"], "weekly": facts["weekly"], "subject": write.subject(facts),
             # the summary's counts are the sections' own (R6O-004)
             "sections": sections, "summary": write.fix_counts(s["text"], sections) if facts["kind"] == "market" else s["text"], "ai": s["ai"],
             "title": write.headline(facts), "label": write.type_label(facts), "indices": facts.get("indices") or [],
             "at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="minutes")}
    if facts["kind"] == "my_stocks":
        issue["uid"] = facts["uid"]
    else:
        facts_line(issue, facts, sections)
    issue["html"], issue["text"] = write.render(issue)
    return issue


def facts_line(issue: dict, facts: dict, sections: list[dict]) -> dict:
    """A Market Brief in one structure every day (R8B-007: 8 Oct's opened with the facts line, 9 Oct's with the AI's
    prose): the summary is always the facts line, and the AI's words, when they passed the checks, go under it."""
    if issue.get("ai"):
        issue["ai_summary"] = issue["summary"]
        issue["summary"] = write.fix_counts(write.template(facts), sections)
    else:
        issue.pop("ai_summary", None)
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


def repair_index_moves(region: str, days: int = 60) -> int:
    """Rebuild the index numbers of the daily Market Briefs stored in the last `days` days from that day's closes.
    Until Oct 2026 a day's change was read against the close about a week earlier; the levels were right. The rest of
    each issue (rotation, scans, headlines) stays as it was, and the summary becomes the plain template (the AI's
    restated the wrong changes). Issues stored before 6 Oct 2026 kept their indices only as text in the Indices
    section; those get the region's main indices rebuilt from the closes. Returns how many issues changed."""
    from datetime import timedelta
    fixed, cutoff = 0, (date.today() - timedelta(days=days)).isoformat()
    for iid in ids("market", region):
        issue = _stored(iid)
        if not issue or issue.get("weekly") or issue.get("day", "") < cutoff:
            continue
        day = date.fromisoformat(issue["day"])
        indices = []
        for i in issue.get("indices") or [{"name": n} for n, _ in content.INDICES.get(region, [])]:
            sym = dict(content.INDICES.get(region, [])).get(i["name"])
            got = content.index_close(sym, day) if sym else None
            indices.append({**i, **got} if got else i)
        indices = [i for i in indices if i.get("price") is not None]
        if not indices or indices == issue.get("indices"):
            continue
        rotation = next((s["items"] for s in issue.get("sections") or [] if s.get("title") == "Sector rotation"), [])
        f = {"kind": "market", "region": region, "day": issue["day"], "weekly": False, "indices": indices, "rotation": rotation}
        issue.update(indices=indices, subject=write.subject(f), title=write.headline(f), summary=write.template(f), ai=False)
        issue.pop("ai_summary", None)                 # the AI's words restated the wrong changes
        issue["sections"] = write.market_sections({**f, "rotation": []})[:1] + [s for s in issue.get("sections") or [] if s.get("title") != "Indices"]
        issue["html"], issue["text"] = write.render(issue)
        kind, scope, dkey = parse_id(iid)
        db.set_setting(_key(kind, scope, dkey), json.dumps(issue))       # in place: the list keeps its order
        fixed += 1
    return fixed


_ASCII_MINUS = re.compile(r"(^|[\s(:;,])-(?=\d)")
_PADDED_DAY = re.compile(r"\b(week to |\w{3} )0(\d)\b")
_QUADRANTS = re.compile(r"\b(leading|lagging|improving|weakening)\b", re.I)


def _house_style(text: str) -> str:
    """A stored brief's text in the app's style: a real minus sign and an unpadded day ("week to 3 Oct", "-3.11%"
    becomes "−3.11%")."""
    return _PADDED_DAY.sub(r"\1\2", _ASCII_MINUS.sub("\\1\u2212", text or ""))


def repair_briefs(region: str, days: int = 60, shifts=None) -> int:
    """The Market Briefs stored in the last `days` days, daily and weekly, in one style and with one rotation: dates
    and minus signs as the daily briefs write them (the weekly ones kept "week to 03 Oct" and "-3.11%"), and the
    Sector rotation section worked out again as the rotation page draws it (weekly candles; the 8 Oct brief said
    "Nifty IT moving from weakening to leading" from daily ones while the page showed Weakening). When the rotation
    can't be worked out again, the section is dropped rather than left to disagree with the page; an AI summary
    that spoke of the rotation becomes the plain template. Returns how many issues changed."""
    from datetime import timedelta
    shifts = shifts or content.rotation_shifts
    fixed, cutoff = 0, (date.today() - timedelta(days=days)).isoformat()
    for iid in ids("market", region):
        issue = _stored(iid)
        if not issue or issue.get("day", "") < cutoff:
            continue
        before = json.dumps(issue, sort_keys=True)
        day, weekly = date.fromisoformat(issue["day"]), bool(issue.get("weekly"))
        try:
            rotation = shifts(region, weekly, day)
        except Exception:
            rotation = []
        f = {"kind": "market", "region": region, "day": issue["day"], "weekly": weekly,
             "indices": issue.get("indices") or [], "rotation": rotation}
        if f["indices"]:
            issue.update(subject=write.subject(f), title=write.headline(f))
        else:
            issue.update(subject=_house_style(issue.get("subject", "")), title=_house_style(issue.get("title", "")))
        new_rot = write.market_sections({**f, "indices": []})
        new_rot = [s for s in new_rot if s.get("title") == "Sector rotation"]
        sections = []
        for s in issue.get("sections") or []:
            if s.get("title") == "Sector rotation":
                continue
            if s.get("title") == "Indices" and f["indices"]:
                sections += write.market_sections({**f, "rotation": []})[:1] + new_rot
                new_rot = []
                continue
            sections.append({**s, "items": [{**i, "text": _house_style(i.get("text", ""))} for i in s.get("items") or []]})
        issue["sections"] = (sections[:1] + new_rot + sections[1:]) if new_rot else sections
        if issue.get("ai") and _QUADRANTS.search(issue.get("ai_summary") or issue.get("summary") or ""):
            issue.update(summary=write.template(f), ai=False)
            issue.pop("ai_summary", None)
        else:
            issue["summary"] = _house_style(issue.get("summary", ""))
        if json.dumps(issue, sort_keys=True) == before:
            continue
        issue["html"], issue["text"] = write.render(issue)
        kind, scope, dkey = parse_id(iid)
        db.set_setting(_key(kind, scope, dkey), json.dumps(issue))       # in place: the list keeps its order
        fixed += 1
    return fixed


def repair_headlines(region: str, days: int = 60) -> int:
    """The Market Briefs stored in the last `days` days with the headline rules of R6O-004 and the summary's counts
    as their sections have them: a headline not about the market, an index or the economy goes; a title already in
    the same brief, or in an earlier daily brief, goes (a stored headline has no date: one an earlier brief carried
    is older than this brief's day); a title cut mid-word ends at its last whole word; "N sectors moved" is the
    Sector rotation section's count. Returns how many issues changed."""
    from datetime import timedelta
    fixed, cutoff = 0, (date.today() - timedelta(days=days)).isoformat()
    issues = sorted((x for x in (_stored(i) for i in ids("market", region)) if x and x.get("day", "") >= cutoff),
                    key=lambda x: (x.get("day", ""), bool(x.get("weekly"))))
    seen: set[str] = set()
    for issue in issues:
        before = json.dumps(issue, sort_keys=True)
        sections, mine = [], set()
        for s in issue.get("sections") or []:
            if s.get("title") != "Headlines":
                sections.append(s)
                continue
            keep = []
            for i in s.get("items") or []:
                title = content.tidy_title(content.drop_publisher(i.get("text"), i.get("source")))
                k = content.title_key(title)
                if not content.MARKET_WORDS[region].search(title) or content.OFF_TOPIC.search(title) or k in mine or (not issue.get("weekly") and k in seen):
                    continue
                mine.add(k)
                keep.append({**i, "text": title})
            if keep:
                sections.append({**s, "items": keep})
        if not issue.get("weekly"):
            seen |= mine
        issue["sections"] = sections
        issue["summary"] = write.fix_counts(issue.get("summary") or "", sections)
        if write.robotic(issue.get("ai_summary")):
            issue.pop("ai_summary", None)             # the tiles' numbers restated (R19-003)
            issue["ai"] = False
        html, text = write.render(issue)              # also the links, close date and wording of today's render (R19-004, R19-006)
        if json.dumps(issue, sort_keys=True) == before and (html, text) == (issue.get("html"), issue.get("text")):
            continue
        issue["html"], issue["text"] = html, text
        kind, scope, dkey = parse_id(issue["id"])
        db.set_setting(_key(kind, scope, dkey), json.dumps(issue))       # in place: the list keeps its order
        fixed += 1
    return fixed


_INDEX_LINE = re.compile(r"^(.+?):\s*([\d,]+(?:\.\d+)?)(?:,\s*([+−-]?[\d.]+)%)?")


def _indices_of(issue: dict) -> list[dict]:
    """The index moves a stored brief shows in its Indices section ("NIFTY 50: 22,231.80, −1.64% on the day")."""
    out = []
    for s in issue.get("sections") or []:
        if s.get("title") != "Indices":
            continue
        for i in s.get("items") or []:
            m = _INDEX_LINE.match(str(i.get("text") or ""))
            if not m:
                continue
            try:
                out.append({"name": m.group(1).strip(), "price": float(m.group(2).replace(",", "")),
                            "change_pct": float(m.group(3).replace("−", "-")) if m.group(3) else None})
            except ValueError:
                continue
    return out


def repair_r7(region: str, days: int = 60) -> int:
    """The stored Market Briefs by the R7O-005 rules: a headline that is a site's own title, a third party's trades
    worded as advice, politics, a story naming another day or contradicting the brief's own index moves, or one an
    earlier brief (the week's too) already carried, goes; a daily brief's AI summary names its own weekday, and a
    weekly one names none. Returns how many issues changed."""
    from datetime import timedelta
    fixed, cutoff = 0, (date.today() - timedelta(days=days)).isoformat()
    issues = sorted((x for x in (_stored(i) for i in ids("market", region)) if x and x.get("day", "") >= cutoff),
                    key=lambda x: (x.get("day", ""), bool(x.get("weekly"))))
    carried: list[tuple[str, set[str]]] = []          # (day, titles) of the briefs before, the weekly ones too
    for issue in issues:
        before = json.dumps(issue, sort_keys=True)
        day = str(issue.get("day") or "")
        weekly = bool(issue.get("weekly"))
        try:
            frm = (date.fromisoformat(day) - timedelta(days=6)).isoformat() if weekly else day
        except ValueError:
            continue
        seen = set().union(*[t for d, t in carried if (date.fromisoformat(day) - timedelta(days=7)).isoformat() <= d < day]) \
            if carried and not weekly else set()
        moves = [] if weekly else _indices_of(issue)
        sections, mine = [], set()
        for s in issue.get("sections") or []:
            if s.get("title") != "Headlines":
                sections.append(s)
                continue
            keep = []
            for i in s.get("items") or []:
                title = content.tidy_title(i.get("text"))
                k = content.title_key(title)
                if k in mine or k in seen or not content.headline_ok(region, title, frm, day, moves):
                    continue
                mine.add(k)
                keep.append({**i, "text": title})
            if keep:
                sections.append({**s, "items": keep})
        carried.append((day, mine))
        issue["sections"] = sections
        if issue.get("ai") and issue.get("ai_summary"):            # the AI's words under the facts line (R8B-007)
            text = write.own_weekday(issue["ai_summary"], issue)
            issue["ai_summary"] = text or None
            issue["ai"] = bool(text)
        elif issue.get("ai"):
            text = write.own_weekday(issue.get("summary") or "", issue)
            if not text:                               # every sentence named a weekday: the moves alone, as the template says them
                got = [m for m in _indices_of(issue) if m["change_pct"] is not None]
                text = "; ".join(f"{m['name']} {kit.pct(m['change_pct'])}" for m in got) + (" over the week." if weekly else " today.") if got else ""
                issue["ai"] = False
            issue["summary"] = text
        if json.dumps(issue, sort_keys=True) == before:
            continue
        issue["html"], issue["text"] = write.render(issue)
        kind, scope, dkey = parse_id(issue["id"])
        db.set_setting(_key(kind, scope, dkey), json.dumps(issue))       # in place: the list keeps its order
        fixed += 1
    return fixed


def repair_facts_line(region: str, days: int = 60) -> int:
    """The Market Briefs stored in the last `days` days by the R8B rules: one that opens with the AI's prose gets the facts
    line (the index moves and the rotation count, from the issue's own sections) first and the AI's words under it
    (R8B-007), and a headline worded as advice ("What Investors Should Know") goes (R8B-012). Returns how many changed."""
    from datetime import timedelta
    from ..intel.news import plain_headline
    fixed, cutoff = 0, (date.today() - timedelta(days=days)).isoformat()
    for iid in ids("market", region):
        issue = _stored(iid)
        if not issue or issue.get("day", "") < cutoff:
            continue
        before = json.dumps(issue, sort_keys=True)
        sections = []
        for sec in issue.get("sections") or []:
            if sec.get("title") == "Headlines":
                sec = {**sec, "items": [i for i in sec.get("items") or [] if plain_headline(i.get("text"))]}
                if not sec["items"]:
                    continue
            sections.append(sec)
        issue["sections"] = sections
        if issue.get("ai") and not issue.get("ai_summary"):
            rotation = next((sec["items"] for sec in sections if sec.get("title") == "Sector rotation"), [])
            f = {"kind": "market", "region": region, "day": issue["day"], "weekly": bool(issue.get("weekly")),
                 "indices": issue.get("indices") or _indices_of(issue), "rotation": rotation}
            if any(i.get("change_pct") is not None for i in f["indices"]):    # else no facts line to give
                facts_line(issue, f, sections)
        if json.dumps(issue, sort_keys=True) == before:
            continue
        issue["html"], issue["text"] = write.render(issue)
        kind, scope, dkey = parse_id(iid)
        db.set_setting(_key(kind, scope, dkey), json.dumps(issue))       # in place: the list keeps its order
        fixed += 1
    return fixed


_IST_STAMP = re.compile(r"Prices and numbers as of [^\n<]*\bIST\b")


def repair_us_stamp() -> int:
    """US briefs stored with "Prices and numbers as of 9 Oct 2026, 02:04 IST" in their email, which the page writes as
    "8 Oct 2026, 16:34 ET" (R7M-002): the stored email written again with New York's time. Returns how many changed."""
    fixed = 0
    for iid in ids("market", "US"):
        issue = _stored(iid)
        if not issue or not _IST_STAMP.search(issue.get("text") or ""):
            continue
        issue["html"], issue["text"] = write.render(issue)
        kind, scope, dkey = parse_id(iid)
        db.set_setting(_key(kind, scope, dkey), json.dumps(issue))       # in place: the list keeps its order
        fixed += 1
    return fixed


# ---------- readers ----------
def address(profile: dict) -> str | None:
    """Where newsletters go: the alert email set in Account, else the address they sign in with."""
    return alerts.newsletter_email(profile)


def confirmed(profile: dict) -> bool:
    """The reader confirmed that address from the link sent to it."""
    return alerts.email_confirmed(profile)


def allowed(profile: dict, what: str, how: str) -> bool:
    """The plan allows this choice: the weekly editions of both newsletters for everyone, the daily ones on Basic and up."""
    return how != "daily" or allows(plan_of(profile), "newsletter")


def subscribers() -> list[dict]:
    """Each reader's choices, with their uid."""
    out = []
    for _, raw in db.all_settings_with_prefix(newsletter_prefs.KEY):
        sub = db.json_value(raw, {})
        if sub.get("uid"):
            out.append({"uid": sub["uid"], **newsletter_prefs.get(sub["uid"])})
    return out


def teaser(profile: dict, issue: dict):
    """Two lines by phone notification or Telegram, for readers who set those up (the email is already on its way)."""
    quiet = {**profile, "alert_email": None, "email": None}         # never a second email
    if not alerts.jobs_for(quiet, "", ""):
        return
    first = re.split(r"(?<=\.)\s", issue.get("summary") or "", maxsplit=1)[0][:160]
    alerts.notify(quiet, issue["subject"], f"{issue['subject']}\n{first}".strip(), url=kit.news_path(issue["id"]))


# why a reader didn't get an issue, in the words Admin → Data and jobs uses (R7M-005)
WHY = {"unconfirmed": "email address not confirmed", "no_address": "no email address", "email_off": "email isn't set up on the server",
       "error": "the email failed to send", "profile": "the account couldn't be read", "nothing_new": "nothing changed for their stocks",
       # chose Daily, but their plan has the weekly edition only: they get Saturday's digest instead (R23-002: said as
       # "chose the other edition" before, so a daily reader left out looked like one who had picked weekly)
       "plan_weekly": "chose daily, but their plan has the weekly edition only"}
RETRY = ("unconfirmed", "no_address", "email_off", "error", "profile")       # worth trying again later the same day
SENT = "newssent:"          # app_settings: who an issue went to, so a retry never sends twice


def email_of(issue: dict) -> tuple[str, str]:
    """(html, text) of an issue's email, written from the stored issue at the moment it is sent: the same summary,
    sections and numbers the web page shows from that issue, so the two can never differ (R7T-009: the 8 Oct US email
    said "mixed on Tuesday" while the page, repaired after the send, said Thursday). A copy written when the issue was
    built is used only when the issue can't be written again."""
    try:
        return write.render(issue)
    except Exception as e:
        print("newsletter: email written at build time used,", issue.get("id"), str(e)[:120])
        return issue["html"], issue["text"]


def deliver_why(profile: dict, issue: dict, what: str, teaser_too: bool = True) -> str:
    """Email the issue (and send the teaser). "sent" when the email went, else why not: no_address, unconfirmed, email_off
    or error. Nothing here raises: one reader's failure never stops the others (R7M-005)."""
    try:
        to = address(profile)
        if not to:
            why = "no_address"
        elif not confirmed(profile):
            why = "unconfirmed"
        elif not alerts.email_ready():
            why = "email_off"
        else:
            html, text, headers = kit.finish(*email_of(issue), profile["id"], what)
            alerts.send_email(to, issue["subject"], text, html=html, headers=headers)
            why = "sent"
    except Exception as e:
        print("newsletter email failed:", str(e)[:160])
        why = "error"
    if teaser_too:
        try:
            teaser(profile, issue)
        except Exception as e:
            print("newsletter teaser failed:", str(e)[:160])
    return why


def deliver(profile: dict, issue: dict, what: str) -> bool:
    """Email the issue (and send the teaser). True when the email went."""
    return deliver_why(profile, issue, what) == "sent"


def ledger(iid: str) -> dict:
    """Who an issue went to ("sent"), who it didn't and why ("skipped": uid -> reason), and whether the run reached the
    end of its readers ("done")."""
    d = db.json_value(db.get_setting(SENT + iid), {}) or {}
    return {"sent": [u for u in d.get("sent") or [] if isinstance(u, str)],
            "skipped": {k: v for k, v in (d.get("skipped") or {}).items() if isinstance(k, str)}, "done": bool(d.get("done")),
            "beat": float(d.get("beat") or 0)}


def has_ledger(iid: str) -> bool:
    """Whether a send of this issue was recorded. One sent before the ledger existed (a deploy on the same day) has none, and
    is never sent again."""
    return bool(db.get_setting(SENT + iid))


def save_ledger(iid: str, led: dict) -> None:
    led["beat"] = time.time()             # a send still going keeps this fresh (see quiet)
    db.set_setting(SENT + iid, json.dumps(led))


def freeze_links(issue: dict) -> dict:
    """Keep the issue's headline links as they are when it is first sent (R23-004): its emails number them
    (/news-link/<issue>/<n>), and a later headline rule that drops a story from the stored issue must not move or
    break those numbers. Stored in place; an issue already frozen is left as it is."""
    if issue.get("kind", "market") != "market" or isinstance(issue.get("links"), list):
        return issue
    issue["links"] = write.headline_urls(issue)
    parts = parse_id(issue.get("id") or "")
    if parts:
        db.set_setting(_key(*parts), json.dumps(issue))       # in place: the list keeps its order
    return issue


def open_ledger(iid: str) -> None:
    """Write the issue's ledger (no one sent to yet) before its day is marked as run (R23-002). The day mark used to come
    first: a database error or a deploy between the mark and the ledger left an issue that was built and marked but had
    no ledger, which reads as "sent before the ledger existed" and is never sent, with nothing in Admin to say so. With
    the ledger first, a run cut short after the mark is picked up by catch_up; one cut short before it isn't marked, so
    the next check runs it again."""
    if not has_ledger(iid):
        save_ledger(iid, ledger(iid))


def retryable(led: dict) -> bool:
    return not led.get("done") or any(r in RETRY for r in led.get("skipped", {}).values())


def quiet(led: dict) -> bool:
    """A run that didn't finish and has made no progress for a while: it was cut short, not still sending."""
    return not led.get("done") and time.time() - led.get("beat", 0) >= run_marks.STALE


def due_today(region: str, now: datetime | None = None) -> str | None:
    """The region's trading day whose daily brief is due by now (its send time has passed), or None (not a trading day,
    or not yet time). For Admin: a due brief with no run recorded is said, not left out."""
    from ..data.calendar import is_trading_day
    tz, at = SEND_AT[region]
    local = (now or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo(tz))
    if local.strftime("%H:%M") < at:
        return None
    try:
        return local.date().isoformat() if is_trading_day(region, local.date()) else None
    except Exception:
        return None


def passing(e: Exception) -> bool:
    """An error that a try a minute later can get past: the database (or the network to it) timing out or dropping."""
    return isinstance(e, (httpx.TransportError, TimeoutError, ConnectionError))


def skipped_words(skipped: dict) -> dict:
    """{reason in words: how many} from a ledger's uid -> reason."""
    out: dict[str, int] = {}
    for r in skipped.values():
        out[WHY.get(r, r)] = out.get(WHY.get(r, r), 0) + 1
    return out


# ---------- the schedule ----------
class Job:
    """Checks every five minutes what is due; each run is marked in the database before sending, so it runs once."""

    def __init__(self, status_key: str | None = None):
        from .. import job_status
        if status_key:
            self.status_key = status_key
        self.last: dict[str, str] = {}
        self.hold: dict[str, float] = {}          # run name -> not asked again before this time (give_back)
        self.all_failed = False                   # the last record() was a read where every source failed
        self._open: dict[str, bool] = {}          # issue id -> whether some reader may still be sent it today (catch_up)
        self.sleep = time.sleep                   # the pause between tries to start a send (tests pass their own)
        self.alerted: set[tuple[str, str]] = set()    # (region, day) whose late-brief alert went (check_late)
        # stores itself whenever a run is written into it, so Admin has it after a restart (R6O-003)
        self.status = job_status.Status(self.status_key, {"last_run": None, "sent": 0, "last_error": None})

    def record(self, now: datetime, problems: list[str], parts: int | None = None, **extra) -> None:
        """How a read went, run by its own clock or by Admin's Run now (so Admin never shows an older run's problem
        after a newer good one): when, the problems (one per source that failed; the first is the last error) and,
        for a job that reads several sources, how many it tried (`parts`)."""
        problems = [str(p) for p in problems or []]
        self.all_failed = bool(problems) and bool(parts) and len(problems) >= parts
        self.status.update(last_run=now.isoformat(), problems=problems[:5], last_error=problems[0][:200] if problems else None,
                           parts=parts, **extra)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="newsletters").start()

    def repair_once(self):
        """Once per database: correct the daily briefs stored with the week-old day's change (see repair_index_moves)."""
        flag = "newsfix:index-day-change-2"      # -2: the first pass skipped issues stored before 6 Oct
        if db.get_setting(flag):
            return
        try:
            n = sum(repair_index_moves(r) for r in SEND_AT)
        except Exception as e:
            print("newsletters repair:", str(e)[:160])
            return
        db.set_setting(flag, datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"))
        print(f"newsletters: corrected the index moves in {n} stored briefs")

    def restyle_once(self):
        """Once per database: the stored briefs in one style, with the rotation page's rotation (see repair_briefs)."""
        flag = "newsfix:style-rotation-1"
        if db.get_setting(flag):
            return
        try:
            n = sum(repair_briefs(r) for r in SEND_AT)
        except Exception as e:
            print("newsletters restyle:", str(e)[:160])
            return
        db.set_setting(flag, datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"))
        print(f"newsletters: restyled {n} stored briefs")

    def headlines_once(self):
        """Once per database: the stored briefs' headlines and counts by today's rules (see repair_headlines)."""
        flag = "newsfix:headlines-counts-2"
        if db.get_setting(flag):
            return
        try:
            n = sum(repair_headlines(r) for r in SEND_AT)
        except Exception as e:
            print("newsletters headlines:", str(e)[:160])
            return
        db.set_setting(flag, datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"))
        print(f"newsletters: tidied the headlines and counts of {n} stored briefs")

    def r7_once(self):
        """Once per database: the stored briefs' headlines and weekdays by the R7O-005 rules (see repair_r7)."""
        flag = "newsfix:headlines-weekday-r7"
        if db.get_setting(flag):
            return
        try:
            n = sum(repair_r7(r) for r in SEND_AT)
        except Exception as e:
            print("newsletters r7:", str(e)[:160])
            return
        db.set_setting(flag, datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"))
        print(f"newsletters: checked the headlines and weekdays of {n} stored briefs")

    def facts_once(self):
        """Once per database: the stored Market Briefs in the one structure (see repair_facts_line)."""
        flag = "newsfix:facts-line-r8b"
        if db.get_setting(flag):
            return
        try:
            n = sum(repair_facts_line(r) for r in SEND_AT)
        except Exception as e:
            print("newsletters facts line:", str(e)[:160])
            return
        db.set_setting(flag, datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"))
        print(f"newsletters: put the facts line first in {n} stored briefs")

    def et_once(self):
        """Once per database: the stored US briefs' email in New York's time (see repair_us_stamp)."""
        flag = "newsfix:us-stamp-et"
        if db.get_setting(flag):
            return
        try:
            n = repair_us_stamp()
        except Exception as e:
            print("newsletters et:", str(e)[:160])
            return
        db.set_setting(flag, datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"))
        print(f"newsletters: stamped {n} stored US briefs in New York time")

    def _loop(self):
        booted = False
        while True:
            if not booted and leader.leading():      # a database error at boot is tried again next pass
                try:
                    self.repair_once()
                    self.restyle_once()
                    self.headlines_once()
                    self.r7_once()
                    self.et_once()
                    self.facts_once()
                    booted = True
                except Exception as e:
                    self.status["last_error"] = str(e)[:200]
                    print("newsletters: bootstrap:", e)
            try:
                if leader.leading():      # another container leads: it runs this pass
                    self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("newsletters:", e)
            try:
                if leader.leading():
                    self.check_late(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                print("newsletters: late check:", e)
            time.sleep(300)

    def check_late(self, now: datetime) -> list[str]:
        """Tell the admins (alerts.tell_admins) when a region's daily brief still isn't on its way LATE_AFTER past its
        slot, once per region and day. Returns the regions told about."""
        told = []
        for region, (tz, at) in SEND_AT.items():
            day = due_today(region, now)
            if not day or (region, day) in self.alerted:
                continue
            local = now.astimezone(ZoneInfo(tz))
            if local < datetime.combine(local.date(), clock.fromisoformat(at), ZoneInfo(tz)) + LATE_AFTER:
                continue
            name = f"market-{region}"
            if self.last.get(name) == day:
                continue
            try:                           # the database not answering is no reason to keep quiet: it is the likely cause
                if run_marks.status(f"newsjob:{name}", day) == "done" or db.get_setting(LATE_KEY + region) == day:
                    self.alerted.add((region, day))
                    continue
            except Exception as e:
                print("newsletters: late check couldn't read the run:", str(e)[:160])
            where = {"IN": "India", "US": "US"}.get(region, region)
            local_at = datetime.strptime(at, "%H:%M").strftime("%-I:%M %p")
            minutes = int((local - datetime.combine(local.date(), clock.fromisoformat(at), ZoneInfo(tz))).total_seconds() // 60)
            err = ((self.status.get("regions") or {}).get(region) or {}).get("error") or self.status.get("last_error")
            text = (f"The {where} Market Brief for {day} was due at {local_at} ({tz}) and still hasn't started sending, "
                    f"{minutes} minutes later." + (f" Last error: {str(err)[:200]}." if err else "")
                    + " It is tried again every five minutes; see Admin → Data and jobs.")
            self.alerted.add((region, day))
            alerts.tell_admins(f"{where} Market Brief is late ({day})", text, label="Admin alert")
            told.append(region)
            try:
                db.set_setting(LATE_KEY + region, day)
            except Exception as e:
                print("newsletters: late alert not recorded:", str(e)[:160])
        return told

    def due(self, name: str, now: datetime, tz: str, at: str, region: str | None = None, weekday: int | None = None) -> date | None:
        """The local day when `name` is due now and hasn't run today; a trading day in `region`, or on `weekday`."""
        from ..data.calendar import is_trading_day
        local = now.astimezone(ZoneInfo(tz))
        day = local.date()
        if local.strftime("%H:%M") < at or self.last.get(name) == day.isoformat() or time.time() < self.hold.get(name, 0):
            return None
        if (weekday is not None and day.weekday() != weekday) or (region and not is_trading_day(region, day)):
            return None
        if name in AFTER_CLOSE and region and not content.closed(region, day, now):
            return None                    # never with the day's pre-auction prices: the official closes first (R8B-001)
        st = run_marks.status(f"newsjob:{name}", day.isoformat())
        if st == "done":                   # already ran today (before a restart)
            self.last[name] = day.isoformat()
        if st:
            return None                    # "running": another container is on it; a quiet one is resumed
        return day

    # the key Admin keeps this job's status under across restarts (job_status); None: not kept
    status_key: str | None = None

    def mark(self, name: str, day: date):
        self.last[name] = day.isoformat()
        db.set_setting(f"newsjob:{name}", day.isoformat())
        self.keep()

    def give_back(self, name: str, seconds: float = 1800) -> None:
        """A read where every source failed doesn't use its slot up: the day mark is taken back, and the run is asked
        again after `seconds` (not on every five-minute check)."""
        self.last.pop(name, None)
        db.delete_setting(f"newsjob:{name}")
        self.hold[name] = time.time() + seconds

    def keep(self):
        if self.status_key:
            from .. import job_status
            job_status.keep(self.status_key, self)           # Admin shows its last run after a restart too

    def begin(self, name: str, day: date):
        """Claim a per-reader run (or the unfinished one to resume): its readers are recorded as they are sent to."""
        return run_marks.claim(f"newsjob:{name}", day.isoformat())

    def finish(self, name: str, day: date, run) -> None:
        run.done()
        self.last[name] = day.isoformat()
        self.keep()

    def run_market(self, region: str, day: date | None, weekly: bool, problems: list) -> tuple[int, bool]:
        """One region's issue for the day: built (or the stored one), its ledger opened, the day marked, then sent.
        (sent, whether it ran). Whatever goes wrong is said, per region, in Admin and the log; the day is marked only
        once the ledger is written, so a failure before that is tried again at the next check (R23-002)."""
        if not day:
            return 0, False
        name = f"weekly-{region}" if weekly else f"market-{region}"
        for pause in (*START_RETRY_PAUSES, None):
            try:
                issue = build_market(region, day, weekly)
                if not issue:                  # every source down: try again on the next check
                    return 0, False
                open_ledger(issue["id"])
                self.mark(name, day)
                break
            except Exception as e:
                if pause is not None and passing(e):
                    print(f"newsletters: couldn't start {region}{' weekly' if weekly else ''} ({type(e).__name__}); "
                          f"trying again in {pause} s")
                    self.sleep(pause)
                    continue
                return self._start_failed(region, day, weekly, e, problems)
        return self._send(region, issue, weekly, problems), True

    def _start_failed(self, region: str, day: date, weekly: bool, e: Exception, problems: list) -> tuple[int, bool]:
        """Said in Admin and the log, per region; the day stays open, so the next check tries again."""
        msg = f"{region}{' weekly' if weekly else ''}: {str(e)[:160]}"
        print("newsletters: run failed before sending,", msg)
        problems.append(msg)
        self._report(f"{region}-weekly" if weekly else region, {
            "issue": issue_id("market", region, day.isoformat(), weekly), "day": day.isoformat(), "weekly": weekly,
            "at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"), "readers": 0, "sent": 0, "other_edition": 0,
            "skipped": {}, "error": f"couldn't start the send ({str(e)[:160]}); tried again at the next check"})
        return 0, True

    def brief_started(self, name: str, day: date, now: datetime) -> bool:
        """Whether the India brief of `day` has been built and its send begun (the day is marked), so what follows it may go;
        past STOCKS_WAIT after its slot My stocks goes anyway, so a brief that can't be built doesn't hold it all day."""
        tz, at = (SEND_AT["IN"] if name.endswith("IN") and not name.startswith("weekly") else (WEEKLY_AT[0], WEEKLY_AT[2]))
        if now.astimezone(ZoneInfo(tz)) >= datetime.combine(day, clock.fromisoformat(at), ZoneInfo(tz)) + STOCKS_WAIT:
            return True
        if self.last.get(name) == day.isoformat():
            return True
        try:
            return run_marks.status(f"newsjob:{name}", day.isoformat()) == "done"
        except Exception:
            return False

    def tick(self, now: datetime) -> int:
        sent, ran, problems = 0, False, []
        for region, (tz, at) in SEND_AT.items():
            n, did = self.run_market(region, self.due(f"market-{region}", now, tz, at, region=region), False, problems)
            sent, ran = sent + n, ran or did
        day = self.due("stocks", now, *SEND_AT["IN"], region="IN")
        if day and not self.brief_started("market-IN", day, now):
            day = None                            # My stocks follows the India brief, never before it (R29B-020)
        run = self.begin("stocks", day) if day else None
        if run:
            try:
                sent, ran = sent + self.run_stocks(day, False, run), True
                self.finish("stocks", day, run)
            except Exception as e:                # left running: resumed once it has been quiet for a while
                problems.append(f"My stocks: {str(e)[:160]}")
                ran = True
        tz, weekday, at = WEEKLY_AT
        for region in SEND_AT:            # per region, like the daily brief: marked only once its issue is built
            n, did = self.run_market(region, self.due(f"weekly-{region}", now, tz, at, weekday=weekday), True, problems)
            sent += n
        day = self.due("weekly", now, tz, at, weekday=weekday)
        if day and not self.brief_started("weekly-IN", day, now):
            day = None
        run = self.begin("weekly", day) if day else None
        if run:
            try:
                sent, ran = sent + self.run_stocks(day, True, run), True
                self.finish("weekly", day, run)
            except Exception as e:
                problems.append(f"My stocks weekly: {str(e)[:160]}")
                ran = True
        sent += self.catch_up(now, problems)
        if ran:
            self.status.update(last_run=now.isoformat(), sent=sent, problems=problems[:5], last_error=problems[0][:200] if problems else None)
        return sent

    def _send(self, region: str, issue: dict, weekly: bool, problems: list, retry: bool = False) -> int:
        """send_market, with whatever goes wrong said instead of stopping the schedule: the day's run is already marked,
        so an error here used to end the region's sends for the day without a word (R7M-005)."""
        try:
            return self.send_market(region, issue, weekly, retry=retry)
        except Exception as e:
            print("newsletter send failed:", region, str(e)[:160])
            problems.append(f"{region}{' weekly' if weekly else ''}: {str(e)[:160]}")
            led = ledger(issue["id"]) if has_ledger(issue["id"]) else {"sent": [], "skipped": {}}
            self._report(f"{region}-weekly" if weekly else region, {
                "issue": issue["id"], "day": issue.get("day"), "weekly": weekly, "at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
                "readers": None, "sent": len(led["sent"]), "other_edition": 0, "skipped": skipped_words(led["skipped"]),
                "error": f"the send stopped ({str(e)[:160]}); the readers not reached are tried again during the day"})
            return 0

    def catch_up(self, now: datetime, problems: list) -> int:
        """Today's issues again for readers who didn't get them for a reason that can pass (the address was confirmed
        after the send, the email service or the database failed for a moment, a run cut short), once a reader qualifies.
        Only today's issues, each reader at most once (the ledger). Returns how many were sent."""
        total = 0
        for region, (tz, _) in SEND_AT.items():
            day = now.astimezone(ZoneInfo(tz)).date().isoformat()
            for weekly in (False, True):
                if self.last.get(f"weekly-{region}" if weekly else f"market-{region}") != day:
                    continue
                iid = issue_id("market", region, day, weekly)
                if self._open.get(iid) is False:
                    continue
                issue = load(iid)
                led = ledger(iid) if issue and has_ledger(iid) else None
                if led and not led["done"] and not quiet(led):
                    continue                  # still being sent (the old container, mid-deploy): not twice
                if not led or not retryable(led):
                    self._open[iid] = False
                    continue
                self._open[iid] = True
                total += self._send(region, issue, weekly, problems, retry=True)
        return total

    def _report(self, key: str, rep: dict) -> None:
        """Remember how a send went, per region, for Admin → Data and jobs (kept across restarts with the job's status).
        After a restart the status in memory starts empty: the regions kept from before it are taken up first, so the
        US run after a deploy no longer wipes out how that day's India run went (R23-002: Admin said nothing of it)."""
        regions = self.status.get("regions")
        if regions is None and self.status_key:
            try:
                from .. import job_status
                regions = (job_status.kept(self.status_key, {}) or {}).get("regions")
            except Exception as e:
                print("newsletters: couldn't read the kept runs,", str(e)[:120])
        regions = {k: v for k, v in dict(regions or {}).items() if isinstance(v, dict)}
        regions[key] = rep
        skipped = rep.get("skipped") or {}
        print(f"newsletters: {key} {rep.get('day')}: sent {rep.get('sent')} of {rep.get('readers')}"
              + (f", other edition {rep['other_edition']}" if rep.get("other_edition") else "")
              + (f", skipped {skipped}" if skipped else "") + (f", {rep['error']}" if rep.get("error") else ""))
        self.status.update(regions=regions, last_run=self.status.get("last_run") or rep["at"])

    def send_market(self, region: str, issue: dict, weekly: bool, retry: bool = False) -> int:
        """Send the region's issue (built once, for everyone) to its readers. Each reader's result is kept (who got it, who
        didn't and why): the next check sends it to readers who couldn't be reached before, and Admin shows the counts
        (R7M-005). With `retry`, only those readers are tried, and no teaser goes twice."""
        what, sent = f"market_{region.lower()}", 0
        if retry and not has_ledger(issue["id"]):
            return 0
        freeze_links(issue)                       # before the first email goes: its link numbers stay good (R23-004)
        led = ledger(issue["id"])
        if not retry or not led["done"]:
            save_ledger(issue["id"], led)         # from the first reader on, a run cut short can be picked up again
        readers = other = 0
        subs = subscribers()
        for sub in subs:
            how = sub.get(what)
            if how not in ("daily", "weekly"):
                continue
            readers += 1
            uid = sub["uid"]
            if uid in led["sent"]:
                continue
            if retry and led["done"] and led["skipped"].get(uid) not in RETRY:
                continue
            try:
                profile = db.get_profile(uid)
                daily_ok = allowed(profile, what, "daily")
            except Exception as e:
                print("newsletter reader failed:", str(e)[:160])
                led["skipped"][uid] = "profile"
                continue
            # daily readers get each day's issue; weekly ones, and daily ones whose plan no longer has it, the digest
            if not weekly and how == "daily" and not daily_ok:
                led["skipped"][uid] = "plan_weekly"       # said in Admin as such, not as a reader who chose weekly
                continue
            if not ((not weekly and how == "daily" and daily_ok) or (weekly and (how == "weekly" or not daily_ok))):
                other += 1
                led["skipped"].pop(uid, None)
                continue
            led["sent"].append(uid)               # written before the send: a kill in between drops one, never doubles
            save_ledger(issue["id"], led)
            why = deliver_why(profile, issue, what, teaser_too=not retry)
            if why == "sent":
                led["skipped"].pop(uid, None)
                sent += 1
            else:
                led["sent"].remove(uid)
                led["skipped"][uid] = why
        led["done"] = True
        save_ledger(issue["id"], led)
        self._open[issue["id"]] = retryable(led)
        self._report(f"{region}-weekly" if weekly else region, {
            "issue": issue["id"], "day": issue.get("day"), "weekly": weekly, "at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
            "readers": readers, "sent": len(led["sent"]), "other_edition": other, "skipped": skipped_words(led["skipped"])})
        return sent

    def run_stocks(self, day: date, weekly: bool, run=None) -> int:
        sent, readers, quiet, other, skipped = 0, 0, 0, 0, {}
        for sub in subscribers():
            how = sub.get("my_stocks")
            if how not in ("daily", "weekly"):
                continue
            readers += 1
            if run:
                if run.seen(sub["uid"]):      # sent before a restart cut the run short
                    continue
                run.beat()
            if not weekly and how != "daily":
                other += 1
                continue
            try:
                profile = db.get_profile(sub["uid"])
            except Exception as e:
                print("my stocks reader failed:", str(e)[:160])
                skipped["profile"] = skipped.get("profile", 0) + 1
                continue
            daily_ok = allowed(profile, "my_stocks", "daily")
            # as with the Market Brief: a daily reader whose plan no longer has daily editions gets the weekly one
            if not weekly and not daily_ok:
                skipped["plan_weekly"] = skipped.get("plan_weekly", 0) + 1
                continue
            if weekly and how == "daily" and daily_ok:
                other += 1
                continue
            try:
                issue = build_stocks(sub["uid"], day, weekly)
            except Exception as e:
                print("my stocks issue failed:", str(e)[:160])
                skipped["error"] = skipped.get("error", 0) + 1
                continue
            if not issue:
                quiet += 1
                continue
            why = deliver_why(profile, issue, "my_stocks")
            if why == "sent":
                sent += 1
            else:
                skipped[why] = skipped.get(why, 0) + 1
            if run:
                run.record(sub["uid"])        # after the send; one not sent got its teaser, so a resume doesn't repeat it
        words = {WHY.get(k, k): n for k, n in skipped.items()}
        if quiet:
            words[WHY["nothing_new"]] = quiet
        self._report("stocks-weekly" if weekly else "stocks", {
            "issue": None, "day": day.isoformat(), "weekly": weekly, "at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
            "readers": readers, "sent": sent, "other_edition": other, "skipped": words})
        return sent
