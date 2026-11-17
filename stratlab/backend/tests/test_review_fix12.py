"""fix12: what fix11 left of LIVE10A / LIVE10B / CX2. Each test is built on what the reviewer saw."""
import json
import threading
import time

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import ai as A, company as C, routes as research_routes


# ---------- LIVE10A-010: "Reading the headlines…" for up to an hour during the session ----------
def _open_market(monkeypatch, store):
    q = {"price": 25375.55, "change_pct": 0.33, "prev_close": 25291.1, "at": "2026-11-17T07:58:00+00:00"}
    monkeypatch.setattr(research_routes, "_levels_now", lambda r, wait: ([C.index_level("S&P 500", q, "US")], None))
    monkeypatch.setattr(research_routes, "market_open", lambda r, now=None: True)
    monkeypatch.setattr(A, "get", lambda kind, key: store.get(repr((kind, key))))
    monkeypatch.setattr(A, "peek", lambda kind, key: repr((kind, key)) in store)

    def keep(kind, key, out, ttl, persist=True):
        store[repr((kind, key))] = json.loads(json.dumps(out))
        return out
    monkeypatch.setattr(A, "keep", keep)


def test_a_new_hours_first_visit_gets_the_sessions_latest_read_at_once_while_the_new_one_is_written(monkeypatch):
    store, calls = {}, []
    _open_market(monkeypatch, store)
    gate = threading.Event()

    def slow(profile, kind, key, ttl, refresh, build, **k):
        calls.append(key)
        gate.wait(5)                       # the AI writing the new hour's read, held up
        return {"tone": f"read {len(calls)}", "hot": [], "flows": [], "themes": [], "generated_at": 100.0 + len(calls)}
    monkeypatch.setattr(research_routes, "ai_call", slow)
    # the session's first read: waited for, and kept as the session's latest
    gate.set()
    first = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u1"}).body)
    assert first["tone"] == "read 1" and not first.get("updating")
    # the hour turns (a new key): the next visit is answered at once with the latest read, marked, and the new one is written behind it
    gate.clear()
    monkeypatch.setattr(research_routes, "mood_key", lambda indices, is_open: ("another hour",))
    t0 = time.time()
    second = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u2"}).body)
    assert time.time() - t0 < 1.0, "the visit waited for the AI"
    assert second["tone"] == "read 1" and second["updating"] is True
    # a third visit while it is being written starts no second write
    json.loads(research_routes.pulse_ai("US", "", False, {"id": "u3"}).body)
    gate.set()
    for _ in range(50):
        if not research_routes._pulse_running:
            break
        time.sleep(0.05)
    assert len(calls) == 2


def test_a_read_of_an_earlier_session_is_never_shown_as_this_sessions(monkeypatch):
    store, calls = {}, []
    _open_market(monkeypatch, store)
    store[repr(("pulse", ("US", "", research_routes.PULSE_LATEST)))] = {
        "tone": "yesterday", "hot": [], "flows": [], "themes": [], "generated_at": 1.0, "session": [["S&P 500", "2026-11-16"]]}

    def call(profile, kind, key, ttl, refresh, build, **k):
        calls.append(key)
        return {"tone": "today", "hot": [], "flows": [], "themes": [], "generated_at": 5.0}
    monkeypatch.setattr(research_routes, "ai_call", call)
    got = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u1"}).body)
    assert got["tone"] == "today" and not got.get("updating") and calls


# ---------- CX2: a company's 30 Oct filing listed twice on its page ----------
def test_a_filing_sent_again_with_a_new_link_is_one_row_that_says_it_was_listed_twice():
    from app.intel import filings as fl
    a = {"id": "2", "symbol": "ACME", "at": "2026-10-30T19:10", "category": "results", "severity": "info", "label": "Financial results", "subject": "Financial Results",
         "text": "Acme Limited has informed the Exchange about the results for the quarter ended September 30, 2026", "url": "https://x.example/b.pdf"}
    b = {**a, "id": "1", "at": "2026-10-30T18:40", "url": "https://x.example/a.pdf"}
    other = {**a, "id": "3", "text": "Acme Limited has informed the Exchange about a press release", "url": "https://x.example/c.pdf"}
    got = fl.without_repeats([a, b, other])
    assert [i["id"] for i in got] == ["2", "3"] and got[0]["copies"] == 2 and "copies" not in got[1]
    assert fl.report(type("F", (), {"announcements": lambda self, s: [a, b, other]})(), "ACME")["items"][0]["copies"] == 2


# ---------- CX2: Apple's page named no exchange, and read "Manufacturing · Electronic computers" over "Same sector: Information Technology" ----------
def test_a_us_page_names_its_exchange_from_the_secs_filing_list():
    from app.intel import sec
    subs = {"tickers": ["AAPL"], "exchanges": ["Nasdaq"]}
    assert sec.listings(subs) == {"AAPL": "Nasdaq"}
    assert sec.for_symbol({"listings": sec.listings(subs)}, "aapl")["listed_on"] == "Nasdaq"
    assert sec.listings({"tickers": ["BRK.B", "BRK.A"], "exchanges": ["NYSE", "NYSE"]}) == {"BRK-B": "NYSE", "BRK-A": "NYSE"}
    assert "listed_on" not in sec.for_symbol({"listings": {}}, "XYZ")
    import inspect
    from app import main as m
    assert 'exchange, red = p.get("listed_on") or "Listed in the US", None' in inspect.getsource(m.stock_page_facts)


def test_a_us_pages_line_under_its_name_uses_the_sector_its_same_sector_list_names():
    from app import stock_pages
    from tests.test_stock_pages_r5v import _facts
    assert stock_pages._sp500_sectors().get("AAPL") == "Information Technology"
    page = stock_pages.render(_facts(region="US", symbol="AAPL", name="Apple Inc.", exchange="Nasdaq", currency="USD", unit="$ million",
                                     industry=["Manufacturing", "Electronic Computers"]), "US", "AAPL", None)
    assert ">Nasdaq · Information Technology · Electronic computers</p>" in page and "Manufacturing" not in page
    # a company outside the S&P 500 keeps the SEC's division; India's are left as listed
    assert stock_pages.sector_first("US", "ZZZZ", ["Manufacturing", "Electronic computers"]) == ["Manufacturing", "Electronic computers"]
    assert stock_pages.sector_first("IN", "AAPL", ["Industrials"]) == ["Industrials"]


# ---------- CX2: "Profit, last 12 months ₹82,011 cr" on the public page against ₹82,228 cr in the deep dive ----------
def test_the_profit_worked_out_from_a_one_decimal_p_e_is_said_to_three_figures():
    from app import stock_pages
    from tests.test_stock_pages_r5v import _facts
    # 18,20,000 / 22.2 = 81,982: a P/E given to one decimal can't give the profit to the crore
    f = _facts(price=1344.8, market_cap=1_820_000.0, pe=22.2, profit_ttm=95625.0)
    assert stock_pages.about(stock_pages.owners_profit(f)) == 82000
    page = stock_pages.render(f, "IN", "ACME", None)
    assert "about ₹82,000 cr" in page and "81,982" not in page
    assert stock_pages.about(3.4712) == __import__("pytest").approx(3.47) and stock_pages.about(None) is None
