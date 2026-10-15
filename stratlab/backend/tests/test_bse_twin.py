"""An NSE company's BSE listing is found in the day's full BSE list (the pages' instrument list holds only BSE-only companies),
and Kite's raw lists are a day's cache that a new login resets."""
from app import main  # noqa: F401, I001  (first: the app loads the modules in the order they need)
from app import kite_service as ks

RAW = [{"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": "RELIANCE", "exchange_token": 500325, "name": "Reliance Industries Ltd"},
       {"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": "TATAMOTORS", "exchange_token": 500570, "name": "Tata Motors Ltd"},
       {"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": "BOND9", "exchange_token": 700009, "name": "Some Bond"},
       {"instrument_type": "DEBT", "segment": "BSE", "tradingsymbol": "NOTEQ", "exchange_token": 500999, "name": "Not Equity"}]


def test_the_code_is_found_by_symbol_then_by_company_name():
    assert ks.bse_code_in(RAW, "RELIANCE") == "500325"
    assert ks.bse_code_in(RAW, "TMCV", "Tata Motors Limited") == "500570"          # renamed on one exchange: the same company name
    assert ks.bse_code_in(RAW, "BOND9") is None and ks.bse_code_in(RAW, "NOTEQ") is None and ks.bse_code_in(RAW, "NOSUCH", "Nobody Ltd") is None
    assert ks.bse_code_in(None, "RELIANCE") is None


def test_a_company_on_both_exchanges_has_a_bse_twin_once_the_bse_list_has_been_read(monkeypatch):
    nse_row = {"exchange": "NSE", "type": "EQ", "symbol": "RELIANCE", "name": "Reliance Industries Ltd"}
    k = main.kite
    monkeypatch.setattr(k, "ready", lambda: True)
    monkeypatch.setattr(k, "by_symbol", lambda s, exchange="NSE": None)         # the pages' list has no BSE row for a dual listing
    monkeypatch.setattr(k, "equity", lambda s: nse_row if s == "RELIANCE" else None)
    monkeypatch.setattr(k, "equity_by_name", lambda n: nse_row)
    monkeypatch.setattr(k, "instruments_cached", lambda ex: None)               # the day's BSE list isn't read yet: as before
    assert main.bse_twin("RELIANCE") is None
    monkeypatch.setattr(k, "instruments_cached", lambda ex: RAW if ex == "BSE" else None)
    assert main.bse_twin("RELIANCE") == "500325"
    assert main.bse_twin("NOSUCH") is None
    monkeypatch.setattr(k, "ready", lambda: False)
    assert main.bse_twin("RELIANCE") is None


def test_a_new_login_resets_the_days_raw_lists(monkeypatch):
    k = ks.KiteService()
    reads = []
    monkeypatch.setattr(k, "_require", lambda: None)
    monkeypatch.setattr(k, "_throttle", lambda: None)
    monkeypatch.setattr(k.kite, "instruments", lambda ex: reads.append(ex) or [{"tradingsymbol": "X"}])
    monkeypatch.setattr(k.kite, "generate_session", lambda rt, api_secret=None: {"access_token": "tok"})
    monkeypatch.setattr(k, "_set_token", lambda t, d: None)
    from app import db
    monkeypatch.setattr(db, "set_setting", lambda key, v: None)
    assert k.instruments_cached("BSE") is None
    assert k.instruments_of("BSE") == [{"tradingsymbol": "X"}] and k.instruments_of("BSE") and reads == ["BSE"]
    assert k.instruments_cached("BSE")
    k.accept_request_token("rt")
    assert k.instruments_cached("BSE") is None
    k.instruments_of("BSE")
    assert reads == ["BSE", "BSE"]
