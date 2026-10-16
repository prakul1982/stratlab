"""Round 37 (16 Oct evening, code review): brief headlines about one sector or company survive a main-index move;
a record intraday high or 'best start to the year' isn't an early-trade story."""
from app.newsletter import content

IDX = [{"name": "NIFTY 50", "price": 25000.0, "change_pct": 0.65}, {"name": "NIFTY BANK", "price": 55000.0, "change_pct": 0.06}]


def test_sector_and_company_headlines_are_kept_on_a_clear_index_day():
    for t in ("Bank stocks fall as RBI holds rates", "IT shares slip after Accenture outlook",
              "Adani shares tumble on probe news", "Nifty ends higher; metal stocks lower"):
        assert not content.contradicts(t, "IN", IDX), t


def test_whole_market_headlines_against_the_main_index_still_go():
    for t in ("Stock markets trade lower as banks drag", "Indian shares fall on global cues", "Dalal Street slips"):
        assert content.contradicts(t, "IN", IDX), t


def test_early_story_needs_an_early_moment():
    assert not content.early_story("Nifty hits record intraday high, ends at peak")
    assert not content.early_story("Stocks set for best start to year")
    for t in ("India Set for Mixed Open", "Markets trade lower during early session", "Sensex opens higher",
              "Stocks seen to open lower", "Shares rise in intraday trade"):
        assert content.early_story(t), t


def test_us_names_keep_how_companies_write_them():
    from app import stock_pages as sp
    assert sp.proper_name("JPMORGAN CHASE & CO") == "JPMorgan Chase & Co"
    assert sp.proper_name("ASML HOLDING NV") == "ASML Holding NV"
    assert sp.proper_name("AMAZON COM INC") == "Amazon.com Inc"
    assert sp.proper_name("MICROSOFT CORP") == "Microsoft Corp"
