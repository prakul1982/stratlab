"""Round 16b, the US close (14 Oct 2026): each test is built on what the reviewer saw."""
from datetime import datetime, timezone

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import stock_pages
from app.intel import company as C, grounding, routes as research_routes

UTC = timezone.utc


def test_pulse_index_is_settling_with_the_stock_pages_rule():
    q = {"price": 7719.51, "change_pct": -1.10, "at": "2026-10-14T20:00:30+00:00"}
    assert C.index_level("S&P 500", q, "US", datetime(2026, 10, 14, 20, 2, tzinfo=UTC))["settling"] is True
    assert C.index_level("S&P 500", q, "US", datetime(2026, 10, 14, 20, 47, tzinfo=UTC))["settling"] is False
    assert C.index_level("S&P 500", {**q, "at": "2026-10-14T19:50:00+00:00"}, "US", datetime(2026, 10, 14, 19, 56, tzinfo=UTC))["settling"] is False


def test_the_mood_is_written_again_once_the_close_has_settled():
    row = {"name": "S&P 500", "day": "2026-10-14", "change_pct": -1.10}
    assert research_routes.mood_key([{**row, "settling": True}], False) != research_routes.mood_key([{**row, "settling": False}], False)


def test_inflow_and_outflow_only_for_institutional_flows():
    assert not grounding.flow_text("Political realignment in Ohio influencing flows away from favored sectors")
    assert grounding.flow_text("Foreign investors sold Indian shares")


def test_company_names_in_capitals_and_the_sector_word():
    assert stock_pages.proper_name("MICROSOFT CORP") == "Microsoft Corp"
    assert stock_pages.proper_name("AT&T INC") == "AT&T Inc"
    assert stock_pages.proper_name("IBM") == "IBM" and stock_pages.proper_name("Apple Inc.") == "Apple Inc."
    assert stock_pages.shown_industry(["Services", "Services-Prepackaged Software"]) == ["Services", "Prepackaged Software"]


def test_peer_names_lose_the_filing_state_suffix_and_all_caps():
    assert stock_pages.proper_name("APPLIED MATERIALS INC /DE") == "Applied Materials Inc"
    assert stock_pages.proper_name("EQUITY RESIDENTIAL /MD/") == "Equity Residential"
    assert stock_pages.proper_name("NVIDIA CORP") == "NVIDIA Corp"
    assert stock_pages.proper_name("ADVANCED MICRO DEVICES INC") == "Advanced Micro Devices Inc"
    assert stock_pages.proper_name("Broadcom Inc.") == "Broadcom Inc."
