"""Round 76 (21 Oct 2026): plan views and the phone in dark mode — the backend side."""
from app.intel import company as C


def test_a_us_exchange_reads_in_its_everyday_name():
    # R76-008: AAPL's header said "NASDAQ NMS - GLOBAL MARKET"
    assert C.venue_name("NASDAQ NMS - GLOBAL MARKET") == "Nasdaq"
    assert C.venue_name("NEW YORK STOCK EXCHANGE, INC.") == "NYSE"
    assert C.venue_name("NYSE ARCA") == "NYSE Arca"
    assert C.venue_name("NYSE AMERICAN") == "NYSE American"
    assert C.venue_name("NYQ") == "NYSE" and C.venue_name("NMS") == "Nasdaq"
    assert C.venue_name("OTC MARKETS") == "OTC"
    assert C.venue_name("Milan") == "Milan" and C.venue_name(None) is None
    one = C.us_listing({"exchange": "NASDAQ NMS - GLOBAL MARKET", "currency": "USD"}, None, {})
    assert one["exchange"] == "Nasdaq"
