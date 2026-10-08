"""Every email StratLab sends, rendered with made-up details, for the owner to look at: GET /admin/email-previews lists
them and GET /admin/email-previews/{kind} returns one (subject, HTML and plain text; ?format=html shows just the page).

Each sample goes through the same builder the real email uses, so what the owner sees is what readers get. Nothing is
sent. The two emails that have no module of their own (the address confirmation and the admin's test email) are built
here and used by the app too."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, HTMLResponse

from . import admin, email_kit as kit
from .responses import err

router = APIRouter(tags=["admin"])
IST = ZoneInfo("Asia/Kolkata")


# ---------- emails built only here ----------
def confirm_email(to: str, link: str) -> tuple[str, str, str]:
    """The link that confirms the address newsletters go to (works for 3 days)."""
    subject = "Confirm your StratLab email"
    html, text = kit.render(
        "Confirm your email", [
            kit.card("Address to confirm", [kit.Row(to)]),
            kit.para("The link works for 3 days. If you didn't ask for this, ignore this email and nothing changes."),
        ], kit.Footer(why="You get this because someone asked to send StratLab emails to this address.",
                      transactional="It is a one-off message, so it has no unsubscribe link.", manage=kit.MANAGE_NEWSLETTERS),
        label="Confirm email", date=kit.today_label(), summary="Confirm that StratLab may send newsletters and reminders to this address.",
        cta=("Confirm my email", link), subject=subject)
    return subject, html, text


def test_email() -> tuple[str, str, str]:
    subject = "StratLab test email"
    html, text = kit.render(
        "Your email is working", [
            kit.para("Problems found by the daily check will arrive like this: a title, a short line, the facts, and one button to the right page."),
        ], kit.Footer(why="You get this because an admin sent a test from Admin.", transactional="It is a one-off test."),
        label="Test email", date=kit.today_label(), summary="Your StratLab alert emails are working.",
        cta=("Open Admin", "/admin"), subject=subject)
    return subject, html, text


# ---------- samples ----------
def _today() -> date:
    return datetime.now(IST).date()


def _issue(facts: dict) -> dict:
    """An issue as the newsletter job stores it, with the plain template summary (no AI call in a preview)."""
    from .newsletter import job, write
    issue = {"id": job.issue_id(facts["kind"], facts.get("region") or "sample", facts["day"], facts["weekly"]), "kind": facts["kind"],
             "region": facts.get("region"), "day": facts["day"], "weekly": facts["weekly"], "subject": write.subject(facts),
             "sections": write.sections(facts), "summary": write.template(facts), "ai": False, "title": write.headline(facts),
             "label": write.type_label(facts), "indices": facts.get("indices") or [],
             # the weekly digest is gathered on Saturday morning; a daily issue right now
             "at": (datetime.combine(date.fromisoformat(facts["day"]), datetime.min.time(), IST).replace(hour=8) if facts["weekly"]
                    else datetime.now(IST)).isoformat(timespec="minutes")}
    issue["html"], issue["text"] = write.render(issue)
    return issue


def _saturday(day: date) -> date:
    """The weekly digest's day: the Saturday on or before `day` (the job sends it on Saturday morning)."""
    return day - timedelta(days=(day.weekday() - 5) % 7)


# made-up figures, each set shaped as its own issue: a day's move and distance from the high for the daily brief,
# the move over the five sessions for the weekly one (content.index_moves gives the weekly issue no "from high")
SAMPLE_INDICES = {
    ("IN", False): [{"name": "NIFTY 50", "price": 22555.75, "change_pct": 0.62, "from_high_pct": 1.8},
                    {"name": "SENSEX", "price": 74210.3, "change_pct": 0.55, "from_high_pct": 1.9},
                    {"name": "INDIA VIX", "price": 13.2, "change_pct": -3.1},
                    {"name": "NIFTY BANK", "price": 48120.4, "change_pct": -0.21}],
    ("IN", True): [{"name": "NIFTY 50", "price": 22410.2, "change_pct": -1.34}, {"name": "SENSEX", "price": 73755.9, "change_pct": -1.18},
                   {"name": "INDIA VIX", "price": 14.6, "change_pct": 8.9}, {"name": "NIFTY BANK", "price": 47630.15, "change_pct": -2.05}],
    ("US", False): [{"name": "S&P 500", "price": 5712.6, "change_pct": -0.34, "from_high_pct": 2.4},
                    {"name": "Nasdaq 100", "price": 19840.2, "change_pct": -0.52}, {"name": "VIX", "price": 16.8, "change_pct": 4.2}],
    ("US", True): [{"name": "S&P 500", "price": 5688.1, "change_pct": 0.91}, {"name": "Nasdaq 100", "price": 19702.4, "change_pct": 1.27},
                   {"name": "VIX", "price": 15.9, "change_pct": -6.4}],
}
SAMPLE_HEADLINES = {
    "IN": [{"headline": "Monthly sales update filed by Tata Motors", "url": "https://example.com/tata-motors"},
           {"headline": "RBI keeps the repo rate unchanged", "url": "https://example.com/rbi"}],
    "US": [{"headline": "Federal Reserve leaves its policy rate unchanged", "url": "https://example.com/fed"},
           {"headline": "Apple files its annual report with the SEC", "url": "https://example.com/apple-10k"}],
}


def _stored_market(region: str, weekly: bool) -> dict | None:
    """The newest Market Brief actually built for the region (daily or weekly), with its rendered email: its real
    figures, never made-up ones beside a real date (R6O-021: "week to 3 Oct: NIFTY 50 -1.34%" where the week was
    -3.11%). None when none is stored."""
    try:
        from .newsletter import job
        return next((i for i in job.recent("market", region, 12) if bool(i.get("weekly")) == weekly and i.get("html") and i.get("text")), None)
    except Exception:
        return None


def _last_weekday(day: date) -> date:
    """The weekday before `day`: a daily sample is of a session that has closed, never of a day still to come."""
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _market(region: str, weekly: bool = False) -> tuple[str, str, str]:
    real = _stored_market(region, weekly)
    if real:
        html, text = kit.preview_links(real["html"], real["text"])
        return real["subject"], html, text
    day = _saturday(_today()) if weekly else _last_weekday(_today())
    if region == "IN":
        scan = ({"group": "NIFTY 50", "st_s2": [{"symbol": "HDFCBANK"}], "stage2": [{"symbol": "MARUTI"}, {"symbol": "TITAN"}]} if weekly
                else {"group": "NIFTY 50", "st_s2": [{"symbol": "TCS"}, {"symbol": "INFY"}], "stage2": [{"symbol": "LT"}]})
        rotation = ([{"sector": "IT", "from": "lagging", "to": "improving"}] if weekly
                    else [{"sector": "Auto", "from": "improving", "to": "leading"}, {"sector": "Banks", "from": "leading", "to": "weakening"}])
    else:
        scan = {"group": "S&P 500", "st_s2": [{"symbol": "AAPL"}], "stage2": []}
        rotation = []
    facts = {"kind": "market", "region": region, "day": day.isoformat(), "weekly": weekly,
             "indices": SAMPLE_INDICES[(region, weekly)], "rotation": rotation, "scan": scan, "headlines": SAMPLE_HEADLINES[region]}
    issue = _issue(facts)
    html, text = kit.preview_links(issue["html"], issue["text"])
    return issue["subject"], html, text


def _my_stocks() -> tuple[str, str, str]:
    day = _today()
    since = (day - timedelta(days=1)).isoformat()
    facts = {"kind": "my_stocks", "uid": "sample", "day": day.isoformat(), "weekly": False, "since": since,
             "stocks": [
                 {"symbol": "TATAMOTORS", "region": "IN", "price": 925.4, "change_pct": 3.4, "stage": 2, "stage_before": 1, "stage_changed": True,
                  "filings": [{"severity": "amber", "label": "Order win", "subject": "Wins a bus order", "url": "https://example.com/f1"}],
                  "headlines": [{"headline": "Monthly sales update filed at 4:12 pm", "url": "https://example.com/n1"}]},
                 {"symbol": "HDFCBANK", "region": "IN", "price": 1612.0, "change_pct": -1.1, "stage": 2,
                  "deals": [{"text": "A block deal of 2.1 lakh shares was disclosed.", "url": "https://example.com/d1"}]}],
             "results": [{"symbol": "TCS", "region": "IN", "date": (day + timedelta(days=2)).isoformat(), "purpose": "Quarterly results",
                          "when": "after market hours", "out": None}],
             "actions": [{"symbol": "INFY", "region": "IN", "text": "Dividend of ₹22 per share", "ex_date": (day + timedelta(days=4)).isoformat(),
                          "record_date": (day + timedelta(days=5)).isoformat()}],
             "unchanged": ["RELIANCE", "ITC"],
             "paper": [{"name": "Momentum test", "closed": 2, "pnl": 3250, "total": 41800, "total_pct": 4.2, "currency": "INR"}]}
    issue = _issue(facts)
    html, text = kit.preview_links(issue["html"], issue["text"])
    return issue["subject"], html, text


def _alerts_email(subject: str, text: str, path: str, label: str, why: str, date: str | None = None) -> tuple[str, str, str]:
    """An alert as alerts.send_message emails it."""
    html, plain = kit.message(subject, text, path, label, why, date=date or kit.today_label())
    return kit.subject_line(subject), html, plain


def _stock_alert() -> tuple[str, str, str]:
    from . import stock_alerts
    subject, body = stock_alerts.message(["RELIANCE rose above ₹2,900 (now ₹2,912.40)", "HDFCBANK fell more than 3% today (now −3.4%)",
                                          "TCS closed above its 50-day average"])
    return _alerts_email(subject, stock_alerts.bulleted(body), "/alerts", "Price and stock alerts", "You get this because you set these alerts on StratLab.")


def _events() -> tuple[str, str, str]:
    from . import market_events as M
    day = _today() + timedelta(days=1)
    text = M.reminder_text([{"title": "RBI policy decision", "time": "10:00"}, {"title": "NIFTY weekly expiry"}], 1, day)
    return _alerts_email(f"StratLab: RBI policy decision and 1 more, {M._short(day)}", text, "/trade/events", "Market events",
                         "You get this because you turned on market event reminders on StratLab.")


def _fo() -> tuple[str, str, str]:
    text = ("Changes to the exchange's F&O contracts for stocks on your watchlist or in your paper sessions:\n"
            "- TATAMOTORS: lot size changes from 1,425 to 1,500 from the November series\n"
            "- PNB: added to the ban list\n\n"
            "From the exchange's contract file and circulars. Facts, not advice.")
    return _alerts_email("StratLab: F&O contract changes for TATAMOTORS, PNB", text, "/trade/fo-changes", "F&O changes",
                         "You get this because you turned on F&O change alerts on StratLab.")


def _money_calendar() -> tuple[str, str, str]:
    """The reminder for the next tax date in the calendar, with its date from the calendar's own tax dates (never one
    written here), as it goes out 7 days before: dated the day it would be sent."""
    from . import money_calendar as C
    days, today = 7, _today()
    nxt = next(e for e in C.tax_between(today + timedelta(days=1), today + timedelta(days=400)) if e["kind"] == "advance_tax")
    due = date.fromisoformat(nxt["date"])
    sip = {"date": nxt["date"], "title": "SIP: Nifty 50 index fund, ₹5,000", "cat": "money"}
    text = C.reminder_text([nxt, sip], days)
    return _alerts_email("StratLab: 2 money dates coming up", text, "/money/calendar", "Money calendar",
                         "You get this because you turned on reminders in your money calendar.",
                         date=kit.fmt_date(due - timedelta(days=days), year=False, weekday=True))


def _result() -> tuple[str, str, str]:
    """The results message, built by results.out_text from a filing as results.india_out reads it."""
    from . import results
    filed = (_today() - timedelta(days=1)).isoformat()
    row = {"symbol": "TCS", "region": "IN", "date": filed, "purpose": "Quarterly results",
           "out": {"at": f"{filed}T16:40", "title": "Financial results for the quarter ended 30 September 2026",
                   "url": "https://example.com/tcs-results.pdf",
                   "numbers": [{"label": "Revenue from operations", "value": "₹64,259 crore"},
                               {"label": "Net profit", "value": "₹12,040 crore"}]}}
    return _alerts_email("StratLab: TCS results are out", results.out_text(row), "/research/IN/TCS", "Results",
                         "You get this because you follow TCS on StratLab.")


def _scan() -> tuple[str, str, str]:
    text = "3 stocks in NIFTY 50 newly match your Stage 2 scan: TCS, INFY, LT.\nFacts from the scan you set, not advice."
    return _alerts_email("StratLab: 3 new matches on your scan", text, "/research", "Scan alert", "You get this because you turned on scan alerts on StratLab.")


def _admin() -> tuple[str, str, str]:
    text = ("2 checks are failing:\n- Prices: the last update is 3 hours old\n- Newsletter job: last run failed\n"
            "Facts from the daily check.")
    return _alerts_email("StratLab: 2 checks failing", text, "/admin", "Admin alert", "You get this because you are a StratLab admin.")


def _screens() -> tuple[str, str, str]:
    from . import screens
    parts = [({"name": "Quality at a fair price", "region": "IN", "filters": screens.clean("IN", {"sector": ["Information Technology"], "stage": [2], "ranges": {"pe": {"min": 5, "max": 25}}})},
              [{"name": "Tata Consultancy Services", "symbol": "TCS"}, {"name": "Infosys", "symbol": "INFY"}])]
    subject, text, html = screens.note(parts, datetime.now(ZoneInfo("UTC")).isoformat(timespec="minutes"))
    html, text = kit.preview_links(html, text)
    return subject, html, text


def _advance_tax() -> tuple[str, str, str]:
    from . import money_advance_tax as A
    today = _today()
    d = next(x for fy in (today.year - 1, today.year, today.year + 1) for x in A.due_dates(fy) if x["date"] > today.isoformat())
    subject, html, text = A.reminder_email(d, 7)
    html, text = kit.preview_links(html, text)
    return subject, html, text


def _lifecycle(kind: str):
    def build():
        from . import lifecycle
        subject, html, text = lifecycle.build(kind, {"id": "sample", "email": "you@example.com"}, lifecycle.sample(kind))
        html, text = kit.preview_links(html, text)
        return subject, html, text
    return build


def _confirm() -> tuple[str, str, str]:
    from .config import settings
    return confirm_email("you@example.com", f"{settings.PUBLIC_API_URL}/email/confirm?t=sample")      # as alerts.confirm_url makes it


# kind: (name, group, builder, one-click unsubscribe, can't be turned off)
def registry() -> dict:
    from . import lifecycle
    out = {
        "market_in": ("Market brief, India (daily)", "Newsletters", lambda: _market("IN"), True, False),
        "market_us": ("Market brief, US (daily)", "Newsletters", lambda: _market("US"), True, False),
        "market_weekly": ("Weekly brief, India (Saturday)", "Newsletters", lambda: _market("IN", True), True, False),
        "my_stocks": ("My stocks", "Newsletters", _my_stocks, True, False),
        "screens": ("Weekly screens", "Newsletters", _screens, True, False),
        "advance_tax": ("Advance tax reminder", "Reminders", _advance_tax, True, False),
        "stock_alert": ("Price and stock alerts", "Alerts", _stock_alert, False, False),
        "scan_alert": ("Scan and filing alerts", "Alerts", _scan, False, False),
        "result_alert": ("Results alert", "Alerts", _result, False, False),
        "events": ("Market events reminder", "Reminders", _events, False, False),
        "fo_changes": ("F&O contract changes", "Alerts", _fo, False, False),
        "money_calendar": ("Money calendar reminder", "Reminders", _money_calendar, False, False),
        "admin_alert": ("Admin alert", "Admin", _admin, False, True),
        "confirm": ("Confirm your email", "Account", _confirm, False, True),
        "test": ("Test email", "Admin", test_email, False, True),
    }
    for kind, (name, tx) in lifecycle.EMAILS.items():
        out[f"lifecycle_{kind}"] = (name, "Welcome and billing" if tx or kind == "welcome" else "Tips and reminders",
                                    _lifecycle(kind), not tx, tx)
    return out


def describe(kind: str, full: bool = False) -> dict:
    name, group, build, unsub, tx = registry()[kind]
    subject, html, text = build()
    out = {"kind": kind, "name": name, "group": group, "subject": kit.subject_line(subject), "unsubscribe": unsub, "transactional": tx}
    if full:
        out.update(html=html, text=text)
    return out


@router.get("/admin/email-previews")
def email_previews(_=Depends(admin.admin_profile)):
    """Every email type, with its subject as the sample renders it. Open one with /admin/email-previews/{kind}."""
    out = []
    for kind in registry():
        try:
            out.append(describe(kind))
        except Exception as e:                       # one broken sample must not hide the others
            out.append({"kind": kind, "name": registry()[kind][0], "group": registry()[kind][1], "error": str(e)[:200]})
    return {"previews": out}


@router.get("/admin/email-previews/{kind}")
def email_preview(kind: str, format: str = "json", _=Depends(admin.admin_profile)):
    """One email with made-up details: subject, HTML and text (or just the page with ?format=html, or the plain text with
    ?format=text). Nothing is sent."""
    if kind not in registry():
        err(404, "not_found", "There's no such email.")
    got = describe(kind, full=True)
    if format == "html":
        return HTMLResponse(got["html"])
    if format == "text":
        return PlainTextResponse(got["text"])
    return got
