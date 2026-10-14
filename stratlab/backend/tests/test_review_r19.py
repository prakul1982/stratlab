"""Round 19: the emails a live review read."""
from datetime import datetime, timedelta, timezone

from app import lifecycle, weekly
from app.newsletter import content, write

IST = timezone(timedelta(hours=5, minutes=30))


def test_the_receipt_from_block_has_no_placeholder_wording_until_the_seller_is_set():
    inv = {"number": "SL/1", "total": 499.0, "currency": "INR", "taxes": [], "seller": {"legal_name": "", "gstin": ""},
           "buyer": {"name": "A"}, "item": {"description": "Basic", "taxable": 499.0}}
    _, _, text = lifecycle.build("receipt", {}, {"invoice": inv, "plan": "basic"})
    assert "StratLab" in text and "not set yet" not in text and "GST" not in text.split("Invoice details")[-1].replace("no GST charged", "")
    assert lifecycle.sample_invoice(datetime.now(timezone.utc))["seller"]["legal_name"] != "StratLab (invoice details not set yet)"


def test_a_headline_cut_at_a_single_letter_ends_at_its_last_word():
    t = "Why did market crash today? Nifty hits fresh 52-week low, Sensex tanks over 1,000 pts. 7 triggers behind R"
    assert content.tidy_title(t).endswith("7 triggers behind…")
    assert content.tidy_title("Sensex ends higher as the rupee gains against the dollar after the RBI policy, say analysts at A") .endswith("A")


def test_a_trailing_publisher_is_dropped_when_it_is_shown_beside_the_headline():
    assert content.drop_publisher("Stocks rally - Reuters", "Reuters") == "Stocks rally"
    assert content.drop_publisher("Stocks rally - Reuters", None) == "Stocks rally - Reuters"
    rows = [{"headline": "Wall Street stocks rally on jobs data - Reuters", "url": "https://x.example/a", "source": "Reuters", "at": None}]
    assert content.pick_headlines("US", rows, "0000-00-00", "9999-99-99")[0]["headline"] == "Wall Street stocks rally on jobs data"


def test_pundit_and_off_topic_items_are_not_brief_headlines():
    for t in ("Jim Cramer's top 10 things to watch in the stock market Friday", "University endowment stocks hit by new tax"):
        assert not content.headline_ok("US", t)
    assert content.headline_ok("US", "Wall Street stocks close higher as inflation cools")


def test_a_headline_has_the_same_short_link_in_both_parts():
    issue = {"id": "market.IN.2026-10-10-weekly", "kind": "market", "region": "IN", "day": "2026-10-10", "weekly": True, "subject": "s", "title": "t",
             "indices": [{"name": "NIFTY 50", "price": 22520.45, "change_pct": 0.44}], "summary": "x",
             "sections": [{"title": "Headlines", "items": [{"text": "Sensex gains", "url": "https://news.google.com/rss/articles/CBMi", "source": "Mint", "lines": []}]}]}
    html, text = write.render(issue)
    link = "/news-link/market.IN.2026-10-10-weekly/0"
    assert link in html and link in text and "news.google.com" not in html
    assert "as of the 15:30 IST close of 9 Oct 2026" in text


def test_a_restated_tiles_summary_is_dropped_and_my_stocks_filing_wording_is_neutral():
    assert write.robotic("The NIFTY 50 price is 22520.45 with a 0.44 percent change.")
    assert write.robotic("NIFTY 50 rose to 22520.45.") and not write.robotic("NIFTY 50 rose 0.44% to 22,520.45 over the week.")
    lines = write.stock_lines({"filings": [{"label": "Order win", "severity": "amber", "subject": "Order win."}]}, "2026-10-01")
    assert lines[0]["text"].startswith("New filing: Order win") and "worth a look" not in lines[0]["text"]


def test_the_weekly_admin_summary_counts_what_it_lists():
    checks = [{"fail": 1, "failed": ["Prices: IN"]}, {"fail": 1, "failed": ["Prices: IN", "Prices: US"]}, {"fail": 1, "failed": ["Fund"]},
              {"fail": 1, "failed": ["Fund"]}, {"fail": 1, "failed": ["Fund"]}, {"fail": 0}]
    facts = {"stats": {"users": 9, "new": 4, "paid": {}, "paying": {}, "given": {}, "experiments": 0, "ai": 0}, "checks": checks, "audits": {},
             "errors": 4, "errors_since_restart": 0, "errors_before_restart": 23, "admin_url": None}
    subject, text = weekly.summary(datetime(2026, 10, 12, 9, 0, tzinfo=IST), facts)
    assert subject == "StratLab weekly: 4 new users, 5 runs with failures, 4 server errors"
    assert "5 with failures: Fund (3 runs), Prices: IN (2 runs), Prices: US" in text
    assert "- 4 server errors this week; 23 more from before the last restart are kept" in text
