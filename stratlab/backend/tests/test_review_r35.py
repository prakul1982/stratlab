"""R35 (16 Oct India brief): the evening brief's headlines and the summary's prices."""
from app import main  # noqa: F401, I001  (first: the app loads its modules in a fixed order)
from app.newsletter import content, write

CLOSE = [{"name": "NIFTY 50", "price": 23146.15, "change_pct": 0.65}, {"name": "SENSEX", "price": 74729.27, "change_pct": 0.56},
         {"name": "NIFTY BANK", "price": 55844.0, "change_pct": 0.06}]
DAY = ("2026-10-16", "2026-10-16")


def test_a_daily_brief_leaves_out_stories_about_the_open_and_early_trade():
    for t in ("India Set for Mixed Open as Asian Markets Rebound", "Stocks open higher; Nifty above 23,100",
              "Sensex, Nifty trade flat in early session", "Markets in pre-open: Nifty indicated higher"):
        assert not content.headline_ok("IN", t, *DAY, CLOSE), t
    for t in ("Sensex, Nifty end higher as IT stocks rally", "Nifty 50 rises 150 points led by Tech Mahindra",
              "Markets end higher on IT gains"):
        assert content.headline_ok("IN", t, *DAY, CLOSE), t
    # a weekly brief passes no index moves and keeps them (it is a summary of the week's stories)
    assert content.headline_ok("IN", "India Set for Mixed Open as Asian Markets Rebound", "2026-10-12", "2026-10-16", None)


def test_the_market_falling_contradicts_a_clear_rise_in_the_main_index_even_with_another_flat():
    assert content.contradicts("Stock markets trade lower amid profit-taking", "IN", CLOSE)
    assert not content.contradicts("Stock markets trade higher amid buying", "IN", CLOSE)
    flat = [dict(i, change_pct=0.1) for i in CLOSE]
    assert not content.contradicts("Stock markets trade lower amid profit-taking", "IN", flat)


def test_the_summary_writes_prices_with_two_decimals():
    assert write.two_decimals("Tech Mahindra Limited jumped 8.48% to 1,790.0.") == "Tech Mahindra Limited jumped 8.48% to 1,790.00."
    assert write.two_decimals("NIFTY 50 rose 0.65% to 23,146.15 and 1,23,456.7") == "NIFTY 50 rose 0.65% to 23,146.15 and 1,23,456.70"
    assert write.two_decimals("up 8.5% in 2026") == "up 8.5% in 2026"
