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
                      transactional="It is a one-off message, so it has no unsubscribe link."),
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
             "at": datetime.now(IST).isoformat(timespec="minutes")}
    issue["html"], issue["text"] = write.render(issue)
    return issue


def _market(region: str, weekly: bool = False) -> tuple[str, str, str]:
    day = _today()
    if region == "IN":
        indices = [{"name": "NIFTY 50", "price": 22555.75, "change_pct": 0.62, "from_high_pct": 1.8},
                   {"name": "SENSEX", "price": 74210.3, "change_pct": 0.55, "from_high_pct": 1.9},
                   {"name": "INDIA VIX", "price": 13.2, "change_pct": -3.1},
                   {"name": "NIFTY BANK", "price": 48120.4, "change_pct": -0.21}]
        scan = {"group": "NIFTY 50", "st_s2": [{"symbol": "TCS"}, {"symbol": "INFY"}], "stage2": [{"symbol": "LT"}]}
        rotation = [{"sector": "Auto", "from": "improving", "to": "leading"}, {"sector": "Banks", "from": "leading", "to": "weakening"}]
    else:
        indices = [{"name": "S&P 500", "price": 5712.6, "change_pct": -0.34, "from_high_pct": 2.4},
                   {"name": "Nasdaq 100", "price": 19840.2, "change_pct": -0.52}, {"name": "VIX", "price": 16.8, "change_pct": 4.2}]
        scan = {"group": "S&P 500", "st_s2": [{"symbol": "AAPL"}], "stage2": []}
        rotation = []
    heads = [{"headline": "Monthly sales update filed by Tata Motors", "url": "https://example.com/tata-motors"},
             {"headline": "RBI keeps the repo rate unchanged", "url": "https://example.com/rbi"}]
    facts = {"kind": "market", "region": region, "day": day.isoformat(), "weekly": weekly, "indices": indices,
             "rotation": rotation, "scan": scan, "headlines": heads}
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


def _alerts_email(subject: str, text: str, path: str, label: str, why: str) -> tuple[str, str, str]:
    html, plain = kit.message(subject, text, path, label, why, date=kit.today_label())
    return subject, html, plain


def _stock_alert() -> tuple[str, str, str]:
    from . import stock_alerts
    subject, body = stock_alerts.message(["RELIANCE rose above ₹2,900 (now ₹2,912.40)", "HDFCBANK fell more than 3% today (now −3.4%)",
                                          "TCS closed above its 50-day average"])
    return _alerts_email(subject, stock_alerts.bulleted(body), "/alerts", "Price and stock alerts", "You get this because you set these alerts on StratLab.")


def _events() -> tuple[str, str, str]:
    from . import market_events as M
    day = _today() + timedelta(days=1)
    text = M.reminder_text([{"title": "RBI policy decision", "time": "10:00"}, {"title": "NIFTY weekly expiry"}], 1, day)
    return _alerts_email(f"StratLab: RBI policy decision and 1 more, {day:%d %b}", text, "/trade/events", "Market events",
                         "You get this because you turned on market event reminders on StratLab.")


def _fo() -> tuple[str, str, str]:
    text = ("Changes to the exchange's F&O contracts for stocks on your watchlist or in your paper sessions:\n"
            "- TATAMOTORS: lot size changes from 1,425 to 1,500 from the November series\n"
            "- PNB: added to the ban list\n\n"
            "From the exchange's contract file and circulars. Facts, not advice.")
    return _alerts_email("StratLab: F&O contract changes for TATAMOTORS, PNB", text, "/trade/fo-changes", "F&O changes",
                         "You get this because you turned on F&O change alerts on StratLab.")


def _money_calendar() -> tuple[str, str, str]:
    from . import money_calendar as C
    d = (_today() + timedelta(days=7)).isoformat()
    text = C.reminder_text([{"date": d, "title": "Advance tax: 3rd instalment"}, {"date": d, "title": "Mutual fund SIP: Nifty index fund"}], 7)
    return _alerts_email("StratLab: 2 money dates coming up", text, "/money/calendar", "Money calendar",
                         "You get this because you turned on reminders in your money calendar.")


def _result() -> tuple[str, str, str]:
    text = ("TCS results are out: Q2 results (5 Oct 2026). As stated: Revenue ₹64,259 cr; Net profit ₹12,040 cr. "
            "https://example.com/tcs-results From the company's filing. Not investment advice.")
    return _alerts_email("TCS results are out", text, "/research/IN/TCS", "Results", "You get this because you follow TCS on StratLab.")


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
    d = A.due_dates(_today().year)[2]
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
    return confirm_email("you@example.com", kit.site("/email/confirm?t=sample"))


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
    out = {"kind": kind, "name": name, "group": group, "subject": subject, "unsubscribe": unsub, "transactional": tx}
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
