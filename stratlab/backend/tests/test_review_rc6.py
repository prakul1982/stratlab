"""RC-6, the main review (the whole app, end to end, as a new visitor, a trader, an investor, a money user): what broke in the
flows, each with the test that proves it."""
import pytest

from app import main, suggest
from app.us_ticker import canon, canon_in
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    main.suggester.clear()
    yield built
    main.suggester.clear()
    built["close"]()


PRO = world.headers("pro-token")


# ---------- RC6-001 (RC5-010): a symbol as another site or a broker writes it ----------
def test_an_indian_symbol_with_its_exchange_around_it_is_the_symbol():
    for typed in ("TCS.NS", "tcs.bo", "TCS-EQ", "NSE:TCS", "nse : tcs", "BSE:TCS", "TCS"):
        assert canon_in(typed) == "TCS", typed
    assert canon_in("BAJAJ-AUTO") == "BAJAJ-AUTO" and canon_in("M&M") == "M&M" and canon_in("500325") == "500325"
    assert canon_in(".NS") == ".NS" and canon_in("") == ""         # a lone affix is left as it is
    assert canon("IN", "TCS.NS") == "TCS" and canon("US", "BRK.B") == "BRK-B" and canon("US", "AAPL") == "AAPL"


def test_the_search_finds_a_company_by_its_symbol_written_either_way():
    us = suggest.index(suggest.us_rows([{"symbol": "BRK-B", "name": "Berkshire Hathaway Inc."}, {"symbol": "BF-B", "name": "Brown-Forman Corp"},
                                        {"symbol": "AAPL", "name": "Apple Inc."}]), "US")
    for typed in ("BRK.B", "brk/b", "brk b", "BRK-B", "BRKB"):
        assert [r["symbol"] for r in suggest.rank(typed, us)][:1] == ["BRK-B"], typed       # "BRK.B" found nothing
    assert [r["symbol"] for r in suggest.rank("BF.B", us)][:1] == ["BF-B"]
    ind = suggest.index(suggest.india_rows([{"symbol": "TCS", "name": "TATA CONSULTANCY SERV", "exchange": "NSE"},
                                            {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto", "exchange": "NSE"},
                                            {"symbol": "M&M", "name": "Mahindra & Mahindra", "exchange": "NSE"}]), "IN")
    for typed in ("TCS.NS", "tcs.bo", "TCS-EQ", "NSE:TCS", "nse: tcs"):
        assert [r["symbol"] for r in suggest.rank(typed, ind)][:1] == ["TCS"], typed
    assert [r["symbol"] for r in suggest.rank("bajaj-auto.ns", ind)][:1] == ["BAJAJ-AUTO"]
    assert [r["symbol"] for r in suggest.rank("M&M.NS", ind)][:1] == ["M&M"]
    assert suggest.rank(".NS", ind) == [] and suggest.rank("NSE:", ind) == []


def test_a_company_page_and_its_public_page_open_by_the_ticker_other_sites_write(w):
    c = w["client"]
    plain = c.get("/research/company/IN/TCS", headers=PRO)
    assert plain.status_code == 200
    for typed in ("TCS.NS", "TCS.BO", "TCS-EQ", "tcs.ns"):
        r = c.get(f"/research/company/IN/{typed}", headers=PRO)
        assert r.status_code == 200 and r.json()["symbol"] == "TCS", typed        # RC5-010: 404 "Couldn't find TCS.NS"
    pub = c.get("/stocks/in/TCS.NS", follow_redirects=False)
    assert pub.status_code == 301 and pub.headers["location"] == "/stocks/in/TCS"
    assert c.get("/stocks/in/NOSUCHCO.NS", follow_redirects=False).status_code == 404


# ---------- RC6-003: a broker's "Stock name" column that holds the symbol ----------
def test_a_name_column_that_holds_the_exchanges_symbol_is_matched():
    from app import holdings
    listed = {"TCS": "Tata Consultancy Services", "INFY": "Infosys", "M&M": "Mahindra & Mahindra"}
    equity = lambda s: {"symbol": s, "exchange": "NSE", "name": listed[s]} if s in listed else None
    m = holdings.Matcher(equity, lambda n: None, lambda c: None, listed, True)
    for name in ("TCS", "INFY EQ", "TCS-EQ", "m&m"):
        got, why = m.match({"name": name, "symbol": "", "isin": ""})
        assert why is None and got["symbol"] == name.upper().replace("-EQ", "").replace(" EQ", ""), name
    got, why = m.match({"name": "Some Unlisted Company Ltd", "symbol": "", "isin": ""})
    assert got is None and why
    assert holdings.clean_symbol("INFY EQ") == "INFY" and holdings.clean_symbol("RELIANCE") == "RELIANCE"


def test_a_file_whose_stock_column_holds_symbols_imports(w):
    import base64
    c = w["client"]
    csv = "Stock Name,Quantity,Average Buy Price\nTCS,10,\"3,200.50\"\nINFY,15,1450\n"
    r = c.post("/holdings/import", headers=world.headers("free-token"),
               json={"filename": "paytm_style.csv", "data": base64.b64encode(csv.encode()).decode()})
    assert r.status_code == 200, r.text
    held = {h["symbol"]: h for h in c.get("/holdings", headers=world.headers("free-token")).json()["rows"]}
    assert set(held) == {"TCS", "INFY"} and held["TCS"]["qty"] == 10 and held["TCS"]["avg"] == 3200.5


def test_a_tradebook_with_a_net_rate_and_an_executed_date_and_time_is_read(w):
    import base64
    c = w["client"]
    csv = ("Executed date and time,Scrip Name,Buy/Sell,Qty,Net Rate\n"
           "03-06-2024 10:00 AM,TCS,B,10,3900\n02-12-2024 10:00 AM,TCS,S,10,4300\n")
    r = c.post("/tax/import", headers=world.headers("basic-token"),
               json={"filename": "any_broker_tradebook.csv", "data": base64.b64encode(csv.encode()).decode()})
    assert r.status_code == 200, r.text          # 400 "couldn't find a column for the price or value by a name we know"
    assert r.json()["read"] == 2
