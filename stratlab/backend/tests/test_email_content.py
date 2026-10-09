"""What the emails say: the results alert's figures in its body, the money calendar's dates from the calendar's own
tax dates, a weekly brief that is its own issue, a US brief with US news, the receipt's GST invoice details, and one
format for dates, money and subjects (the app's own: "7 Oct 2026", ₹ never "INR")."""
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401  (the app imports its modules in a fixed order)
from app import alerts, email_kit as kit, email_previews as P, lifecycle

KINDS = list(P.registry())


@pytest.fixture(scope="module")
def built():
    return {k: P.describe(k, True) for k in KINDS}


def _visible(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<style>.*?</style>|<[^>]+>", " ", html, flags=re.S))


def _body_and_footer(html: str) -> tuple[str, str]:
    """The email's body (title to button) and its footer, as a reader sees them."""
    body, _, footer = html.partition("Manage emails")
    return _visible(body), _visible(footer)


# ---------- the results alert ----------
def test_results_alert_has_its_figures_in_the_body_and_the_filing_as_a_link(built):
    d = built["result_alert"]
    body, footer = _body_and_footer(d["html"])
    for fig in ("Revenue from operations", "₹64,259 crore", "Net profit", "₹12,040 crore"):
        assert fig in body and fig not in footer, fig
    assert ">Read the filing</a>" in d["html"] and "tcs-results.pdf</" not in d["html"]        # a link, not a raw address
    assert _visible(d["html"].split("<body", 1)[1]).count("TCS results are out") == 1                              # said once, as the title
    assert "Open the company page" in d["html"]


def test_the_results_message_keeps_every_fact_on_its_own_line():
    from app import results
    text = results.out_text({"symbol": "TCS", "date": "2026-10-05", "out": {
        "at": "2026-10-05T16:40", "title": "Q2 results", "url": "https://example.com/r.pdf", "numbers": [{"label": "Net profit", "value": "₹12,040 crore"}]}})
    assert text.splitlines() == ["TCS results are out: Q2 results (Mon 5 Oct).", "As stated in the filing:", "- Net profit: ₹12,040 crore",
                                 "Read the filing: https://example.com/r.pdf", "From the company's filing. Not investment advice."]


def test_a_footnote_at_the_end_of_a_line_takes_only_the_small_print():
    html, _ = kit.message("StratLab: X", "TCS filed its results. As stated: Revenue ₹5 crore. From the filing. Not investment advice.",
                          "/alerts", "L", "why")
    body, footer = _body_and_footer(html)
    assert "Revenue ₹5 crore" in body and "Not investment advice" in footer and "Revenue" not in footer


# ---------- the money calendar ----------
def test_money_calendar_reminder_dates_the_third_advance_tax_instalment_15_december(built):
    from app import money_calendar as C
    third = next(e for e in C.tax_dates(2026) if e["title"].startswith("Advance tax, third"))
    assert third["date"] == "2026-12-15"
    today = P._today()
    nxt = next(e for e in C.tax_between(today + timedelta(days=1), today + timedelta(days=400)) if e["kind"] == "advance_tax")
    text = built["money_calendar"]["text"]
    assert nxt["title"] in text and f"on {kit.fmt_date(nxt['date'], weekday=True)}".upper() in text.upper()
    sent_on = date.fromisoformat(nxt["date"]) - timedelta(days=7)
    assert text.startswith(f"STRATLAB | Money calendar · {kit.fmt_date(sent_on, year=False, weekday=True)}")   # dated the day it goes
    assert "3rd instalment" not in text
    assert kit.fmt_date(nxt["date"]) in built["advance_tax"]["subject"]                     # the advance tax email agrees


# ---------- the briefs ----------
def test_the_weekly_brief_is_its_own_issue_not_a_copy_of_the_daily(built):
    daily, weekly = built["market_in"], built["market_weekly"]
    assert weekly["subject"].startswith("Market Brief India, week to ") and "week to" not in daily["subject"]

    def lead(t):
        return re.search(r"^NIFTY 50: (\S+)", t, re.M).group(1)
    assert lead(daily["text"]) != lead(weekly["text"])
    assert "on the day" not in weekly["text"] and "below its high" not in weekly["text"]
    bank = next(ln for ln in weekly["text"].splitlines() if ln.startswith("- NIFTY BANK"))
    assert bank.endswith("over the week")
    assert re.search(r"Week to Sat \d{1,2} [A-Z][a-z]{2}", weekly["text"])                  # the digest goes on Saturday


def test_the_us_brief_has_us_news(built):
    us = built["market_us"]["text"]
    for india in ("Tata Motors", "RBI", "NIFTY", "SENSEX", "₹"):
        assert india not in us, india


def test_links_in_rows_look_like_links(built):
    html = built["market_in"]["html"]
    for title in ("Auto moved from Improving", "TCS matches the Stage 2 rule", "RBI keeps the repo rate unchanged"):
        a = re.search(r'<a href="[^"]+" class="([^"]+)" style="color:([^;]+);[^"]*">' + re.escape(title), html)
        assert a and a.group(1) == "c-blue" and a.group(2) == kit.L["blue"], title


# ---------- one format ----------
def test_dates_and_money_follow_the_app(built):
    assert kit.fmt_date("2026-10-07") == "7 Oct 2026" and kit.fmt_date("2026-10-07", year=False, weekday=True) == "Wed 7 Oct"
    assert kit.fmt_date("2026-10-07", weekday=True) == "Wed, 7 Oct 2026" and kit.fmt_date(date(2026, 9, 3), year=False) == "3 Sep"
    assert kit.money(3250, "INR", signed=True) == "+₹3,250" and kit.money(-1200.5, "USD", 2, signed=True) == "−$1,200.50"
    assert kit.money(100000, "INR") == "₹1,00,000" and kit.money(5, "SGD") == "5 SGD"
    for kind, d in built.items():
        both = d["subject"] + "\n" + d["text"]
        assert not re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun),? 0\d\b|\b0\d (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", both), kind
        assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", re.sub(r"https?://\S+", "", both)), kind     # no ISO dates for readers
        assert not re.search(r"\d INR\b|\bINR \d", both), kind
    assert "+₹3,250" in built["my_stocks"]["text"] and "+₹41,800" in built["my_stocks"]["text"]


def test_subjects_follow_one_rule():
    for kind in KINDS:
        s = P.describe(kind)["subject"]
        assert not s.startswith("StratLab:") and not s[:1].islower(), (kind, s)
    assert kit.subject_line("StratLab: 3 of your alerts fired") == "3 of your alerts fired"
    assert kit.subject_line("StratLab alert: x") == "X" and kit.subject_line("Welcome to StratLab") == "Welcome to StratLab"


def test_email_subjects_are_sent_by_the_rule(monkeypatch):
    from app.config import settings
    got = []
    monkeypatch.setattr(settings, "BREVO_API_KEY", "k")
    monkeypatch.setattr(alerts, "_send_brevo", lambda to, subject, *a: got.append(subject))
    alerts.send_email("a@example.com", "StratLab: TCS results\nare out", "x")
    assert got == ["TCS results are out"]


# ---------- the receipt ----------
def test_receipt_carries_the_gst_invoice_details(monkeypatch):
    # R9P-003: the preview carries GST lines only when the seller set in Admin → Invoices has a GSTIN (a real payment gets
    # exactly that); the plain variant for an empty seller is tested in test_review_r9p. So this one sets a seller with a GSTIN.
    from app import invoices
    seller = {"legal_name": "StratLab Labs LLP", "address": "Pune", "state": "27", "gstin": "27ABCDE1234F1Z5", "prefix": "SL"}
    monkeypatch.setattr(invoices, "seller", lambda: {**{f: "" for f in invoices.FIELDS}, **seller})
    text = P.describe("lifecycle_receipt", True)["text"]
    inv = lifecycle.sample_invoice(datetime.now(timezone.utc))
    taxable, _ = invoices.backed_out(inv["total"])
    for fact in (kit.money(taxable, "INR", 2), "CGST 9%", "SGST 9%", kit.money(inv["total"], "INR", 2), "GSTIN ", "SAC 998431",
                 "Billed to", "Place of supply:", "GST included in the price.", inv["number"]):
        assert fact in text, fact
    assert re.search(r"Date: \d{1,2} [A-Z][a-z]{2} \d{4}", text)


def test_receipt_from_a_real_invoice_shows_igst_and_the_buyers_gstin(monkeypatch):
    from app import db, invoices
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    invoices.save_seller({"legal_name": "StratLab Labs LLP", "address": "Pune", "state": "27", "gstin": "27ABCDE1234F1Z5"})
    invoices.save_billing("u-1", {"name": "Acme Pvt Ltd", "state": "29", "gstin": "29ABCDE1234F1Z5", "country": "IN"})
    inv = invoices.make({"id": "pay_1", "amount": 49900, "currency": "INR", "created_at": 1791331200}, {"id": "u-1", "email": "a@example.com"},
                        "basic", "month")
    _, html, text = lifecycle.build("receipt", {"id": "u-1"}, {"invoice": inv, "plan": "basic", "period": "month"})
    for fact in ("IGST 18%", "₹76.12", "₹422.88", "₹499.00", "StratLab Labs LLP", "GSTIN 27ABCDE1234F1Z5", "Acme Pvt Ltd",
                 "GSTIN 29ABCDE1234F1Z5", "Place of supply: Karnataka", "IGST included in the price."):
        assert fact in text, fact
    assert "CGST" not in text and "&lt;" not in html


def test_an_unregistered_seller_says_so_on_the_receipt(monkeypatch):
    inv = {"number": "SL/2026-27/0002", "total": 499.0, "currency": "INR", "date": "2026-10-07", "taxes": [],
           "seller": {"legal_name": "StratLab", "gstin": ""}, "buyer": {"name": "A"}, "item": {"description": "Basic", "taxable": 499.0},
           "note": "The supplier is not registered under GST, so no GST is charged.", "place_of_supply": "Maharashtra"}
    _, _, text = lifecycle.build("receipt", {}, {"invoice": inv, "plan": "basic"})
    assert "Not registered under GST" in text and "no GST charged" in text and "GSTIN" not in text


def test_an_old_invoice_without_tax_details_still_makes_a_receipt():
    _, _, text = lifecycle.build("receipt", {}, {"invoice": {"number": "SL/2026-27/0007", "total": 2999.0, "currency": "INR", "date": "2026-10-07"}})
    assert "₹2,999.00" in text and "7 Oct 2026" in text and "TAX INVOICE" not in text
