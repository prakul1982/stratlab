"""MW-1: Market Watch's lists (kept per user, the first one the Research watchlist), the plans' limits said plainly, prices and
lines of closes read once for everyone, the visitor's fixed board, and the limits on charts that keep drawings."""
import pytest

from app import drawings_store as DS, watch_quotes as WQ, watch_store as WS
from tests import world

PRO = world.headers("pro-token")
BASIC = world.headers("basic-token")
FREE = world.headers("free-token")
OTHER = world.headers("admin-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    WQ.forget()
    # the limit tests fill lists with made-up symbols: the "does StratLab know it" check has its own test
    from app import watch_routes
    real = watch_routes._known
    monkeypatch.setattr(watch_routes, "_known", lambda it: None if it["symbol"].startswith("C") and it["symbol"].endswith("-USD") and it["symbol"] != "BTC-USD" else real(it))
    yield built
    built["close"]()


def item(market, symbol, name=None, kind=None):
    return {"market": market, "symbol": symbol, "name": name or symbol, **({"kind": kind} if kind else {})}


def lists(c, h):
    return c.get("/watch/lists", headers=h).json()


# ---------- the first list is the Research watchlist ----------
def test_needs_a_signed_in_user(w):
    c = w["client"]
    for path in ("/watch/lists", "/watch/quotes?ids=IN:INFY", "/watch/spark?ids=IN:INFY", "/watch/stream?ids=IN:INFY"):
        assert c.get(path).status_code == 401, path
    assert c.put("/watch/lists/default/items", json={"items": []}).status_code == 401


def test_the_first_list_is_the_research_watchlist_and_keeps_other_markets_in_order(w):
    c = w["client"]
    first = lists(c, PRO)
    assert [x["id"] for x in first["lists"]] == ["default"] and first["lists"][0]["name"] == "Watchlist" and first["lists"][0]["default"] is True
    # a stock starred on Research appears in the first list
    c.put("/research/watchlist", headers=PRO, json={"items": [{"region": "IN", "symbol": "INFY", "name": "Infosys"}]})
    assert [i["id"] for i in lists(c, PRO)["lists"][0]["items"]] == ["IN:INFY"]
    # a stock, an index, bitcoin and forex added in the Market Watch order
    put = c.put("/watch/lists/default/items", headers=PRO, json={"items": [
        item("CRYPTO", "BTC-USD", "Bitcoin"), item("IN", "INFY", "Infosys"), item("IN", "^NSEI"), item("FX", "EURUSD=X", "EUR/USD"), item("US", "AAPL")]})
    assert put.status_code == 200, put.text
    got = put.json()["lists"][0]["items"]
    assert [i["id"] for i in got] == ["CRYPTO:BTC-USD", "IN:INFY", "IN:^NSEI", "FX:EURUSD=X", "US:AAPL"]
    assert {i["id"]: i["kind"] for i in got} == {"CRYPTO:BTC-USD": "crypto", "IN:INFY": "stock", "IN:^NSEI": "index", "FX:EURUSD=X": "fx", "US:AAPL": "stock"}
    assert got[2]["name"] == "NIFTY 50"
    # the Research watchlist holds only the stocks, in the same order: nothing is kept twice
    research = c.get("/research/watchlist", headers=PRO).json()["items"]
    assert [(i["region"], i["symbol"]) for i in research] == [("IN", "INFY"), ("US", "AAPL")]
    # a stock starred later on Research joins the end of the first list, whatever else is on it
    c.put("/research/watchlist", headers=PRO, json={"items": [*research, {"region": "IN", "symbol": "TCS", "name": "TCS"}]})
    assert [i["id"] for i in lists(c, PRO)["lists"][0]["items"]][-1] == "IN:TCS"
    # and one removed there leaves the first list
    c.put("/research/watchlist", headers=PRO, json={"items": [i for i in research if i["symbol"] != "INFY"]})
    assert "IN:INFY" not in [i["id"] for i in lists(c, PRO)["lists"][0]["items"]]


def test_an_unknown_instrument_is_refused_and_bad_items_are_dropped(w):
    c = w["client"]
    bad = c.put("/watch/lists/default/items", headers=PRO, json={"items": [item("IN", "ZZZZQQ")]})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "unknown_symbol"
    ok = c.put("/watch/lists/default/items", headers=PRO, json={"items": [item("MARS", "X"), {"symbol": "A"}, item("IN", "INFY"), item("in", "infy"), item("US", "bad symbol!")]})
    assert [i["id"] for i in ok.json()["lists"][0]["items"]] == ["IN:INFY"]
    assert c.put("/watch/lists/default/items", headers=PRO, json={"items": [item("FX", "NOPE=X")]}).status_code == 400


# ---------- named lists ----------
def test_named_lists_are_created_renamed_filled_reordered_and_deleted(w):
    c = w["client"]
    a = c.post("/watch/lists", headers=PRO, json={"name": "  Crypto   watch "}).json()["lists"]
    assert [x["name"] for x in a] == ["Watchlist", "Crypto watch"]
    lid = a[1]["id"]
    c.post("/watch/lists", headers=PRO, json={"name": "Metals"})
    got = c.put(f"/watch/lists/{lid}/items", headers=PRO, json={"items": [item("CRYPTO", "ETH-USD", "Ethereum"), item("CRYPTO", "BTC-USD", "Bitcoin")]}).json()["lists"]
    assert [i["id"] for i in got[1]["items"]] == ["CRYPTO:ETH-USD", "CRYPTO:BTC-USD"]
    assert c.patch(f"/watch/lists/{lid}", headers=PRO, json={"name": "Coins"}).json()["lists"][1]["name"] == "Coins"
    ids = [x["id"] for x in lists(c, PRO)["lists"]]
    flipped = c.put("/watch/order", headers=PRO, json={"ids": [ids[2], ids[1]]}).json()["lists"]
    assert [x["name"] for x in flipped] == ["Watchlist", "Metals", "Coins"]
    assert c.post("/watch/lists", headers=PRO, json={"name": "coins"}).status_code == 400            # the same name twice
    assert c.post("/watch/lists", headers=PRO, json={"name": "Watchlist"}).status_code == 400
    assert c.post("/watch/lists", headers=PRO, json={"name": "   "}).status_code == 400
    assert c.patch("/watch/lists/default", headers=PRO, json={"name": "Mine"}).status_code == 400
    assert c.delete("/watch/lists/default", headers=PRO).status_code == 400
    assert [x["name"] for x in c.delete(f"/watch/lists/{lid}", headers=PRO).json()["lists"]] == ["Watchlist", "Metals"]
    assert c.delete(f"/watch/lists/{lid}", headers=PRO).status_code == 404


def test_one_person_never_reaches_anothers_lists(w):
    c = w["client"]
    mine = c.post("/watch/lists", headers=PRO, json={"name": "Private"}).json()["lists"][1]["id"]
    c.put(f"/watch/lists/{mine}/items", headers=PRO, json={"items": [item("CRYPTO", "BTC-USD")]})
    assert [x["name"] for x in lists(c, OTHER)["lists"]] == ["Watchlist"]
    assert c.put(f"/watch/lists/{mine}/items", headers=OTHER, json={"items": []}).status_code == 404
    assert c.patch(f"/watch/lists/{mine}", headers=OTHER, json={"name": "Taken"}).status_code == 404
    assert c.delete(f"/watch/lists/{mine}", headers=OTHER).status_code == 404
    assert lists(c, PRO)["lists"][1]["items"][0]["id"] == "CRYPTO:BTC-USD"
    # the first list is the person's own Research watchlist too
    c.put("/watch/lists/default/items", headers=PRO, json={"items": [item("CRYPTO", "ETH-USD")]})
    assert lists(c, OTHER)["lists"][0]["items"] == []


def test_a_list_is_bounded(w):
    c = w["client"]
    lid = c.post("/watch/lists", headers=PRO, json={"name": "Big"}).json()["lists"][1]["id"]
    many = [item("CRYPTO", f"C{i}-USD") for i in range(WS.HARD_SYMBOLS + 40)]
    assert c.put(f"/watch/lists/{lid}/items", headers=PRO, json={"items": many}).status_code == 422     # past the most a request may hold
    ok = c.put(f"/watch/lists/{lid}/items", headers=PRO, json={"items": many[:WS.HARD_SYMBOLS]})
    assert ok.status_code == 200 and len(ok.json()["lists"][1]["items"]) == WS.HARD_SYMBOLS
    name = c.post("/watch/lists", headers=PRO, json={"name": "x" * 150}).json()["lists"][2]["name"]
    assert len(name) == WS.NAME_MAX


# ---------- the plans' limits ----------
def test_free_keeps_one_list_of_twenty_and_says_so_plainly(w):
    c = w["client"]
    got = lists(c, FREE)
    assert got["limits"]["lists"] == 1 and got["limits"]["symbols"] == 20 and got["limits"]["next"]["lists"] == "Basic"
    refused = c.post("/watch/lists", headers=FREE, json={"name": "Second"})
    assert refused.status_code == 402 and refused.json()["detail"]["code"] == "plan_limit"
    assert refused.json()["detail"]["message"].startswith("The Free plan keeps 1 watchlist. Basic keeps 10.")
    assert refused.json()["detail"]["plan"] == "basic"
    twenty = [item("CRYPTO", f"C{i}-USD") for i in range(20)]
    assert c.put("/watch/lists/default/items", headers=FREE, json={"items": twenty}).status_code == 200
    more = c.put("/watch/lists/default/items", headers=FREE, json={"items": [*twenty, item("CRYPTO", "BTC-USD")]})
    assert more.status_code == 402 and "keeps 20 symbols in a list. Basic keeps 100." in more.json()["detail"]["message"]
    # a list may be reordered or shrunk at the limit
    assert c.put("/watch/lists/default/items", headers=FREE, json={"items": list(reversed(twenty))}).status_code == 200
    assert c.put("/watch/lists/default/items", headers=FREE, json={"items": twenty[:5]}).status_code == 200


def test_a_list_longer_than_the_plan_keeps_stays_and_cannot_grow(w):
    c = w["client"]
    uid = "u-free"
    WS.save_default(uid, WS.clean_items([item("CRYPTO", f"C{i}-USD") for i in range(25)]))      # kept from a higher plan
    assert len(lists(c, FREE)["lists"][0]["items"]) == 25
    grow = c.put("/watch/lists/default/items", headers=FREE, json={"items": [*[item("CRYPTO", f"C{i}-USD") for i in range(25)], item("CRYPTO", "BTC-USD")]})
    assert grow.status_code == 402
    swap = c.put("/watch/lists/default/items", headers=FREE, json={"items": [*[item("CRYPTO", f"C{i}-USD") for i in range(24)], item("CRYPTO", "BTC-USD")]})
    assert swap.status_code == 200 and len(swap.json()["lists"][0]["items"]) == 25


def test_the_research_watchlist_page_obeys_the_same_cap(w):
    c = w["client"]
    big = [{"region": "US", "symbol": s, "name": s} for s in ("AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ")]
    assert c.put("/research/watchlist", headers=FREE, json={"items": big}).status_code == 200            # six: under 20
    over = [{"region": "IN", "symbol": f"S{i}", "name": "x"} for i in range(21)]
    r = c.put("/research/watchlist", headers=FREE, json={"items": over})
    assert r.status_code == 402 and "Basic keeps 100" in r.json()["detail"]["message"]


def test_basic_keeps_ten_lists_of_a_hundred_and_pro_has_no_limit(w):
    c = w["client"]
    for n in range(9):
        assert c.post("/watch/lists", headers=BASIC, json={"name": f"L{n}"}).status_code == 200
    eleventh = c.post("/watch/lists", headers=BASIC, json={"name": "L9"})
    assert eleventh.status_code == 402 and "keeps 10 watchlists. Pro has no limit." in eleventh.json()["detail"]["message"]
    lid = lists(c, BASIC)["lists"][1]["id"]
    hundred = [item("CRYPTO", f"C{i}-USD") for i in range(100)]
    assert c.put(f"/watch/lists/{lid}/items", headers=BASIC, json={"items": hundred}).status_code == 200
    assert c.put(f"/watch/lists/{lid}/items", headers=BASIC, json={"items": [*hundred, item("CRYPTO", "BTC-USD")]}).status_code == 402
    for n in range(12):
        assert c.post("/watch/lists", headers=PRO, json={"name": f"P{n}"}).status_code == 200
    assert lists(c, PRO)["limits"]["lists"] is None and lists(c, PRO)["limits"]["symbols"] is None


def test_plans_page_numbers_and_the_account_see_the_new_limits(w):
    c = w["client"]
    me = c.get("/me", headers=FREE).json()
    free, basic, pro = (me["plans"][p] for p in ("free", "basic", "pro"))
    assert (free["watchlists"], free["watchlist_symbols"], free["chart_saves"], free["chart_indicators"]) == (1, 20, 3, 3)
    assert (basic["watchlists"], basic["watchlist_symbols"], basic["chart_saves"], basic["chart_indicators"]) == (10, 100, None, 10)
    assert (pro["watchlists"], pro["watchlist_symbols"], pro["chart_saves"], pro["chart_indicators"]) == (None,) * 4
    assert me["plan_info"]["watchlists"] == 1 and me["plan_info"]["chart_indicators"] == 3


# ---------- charts that keep drawings ----------
def trend(i="d1"):
    return {"id": i, "kind": "trend", "points": [{"t": 1_700_000_000_000, "p": 100}, {"t": 1_710_000_000_000, "p": 120}]}


def test_free_keeps_drawings_on_three_charts_and_says_so_before_the_fourth(w):
    c = w["client"]
    assert c.get("/me/drawings/summary", headers=FREE).json() == {"charts": 0, "limit": 3, "indicators": 3, "saved": False, "next": {"charts": "Basic", "indicators": "Basic"}}
    for s in ("INFY", "TCS", "RELIANCE"):
        assert c.put(f"/me/drawings/IN/{s}", headers=FREE, json={"drawings": [trend()]}).status_code == 200
    assert c.get("/me/drawings/summary", headers=FREE).json()["charts"] == 3
    fourth = c.put("/me/drawings/IN/WIPRO", headers=FREE, json={"drawings": [trend()]})
    assert fourth.status_code == 402 and fourth.json()["detail"]["code"] == "plan_limit"
    assert fourth.json()["detail"]["message"].startswith("The Free plan keeps 3 charts with saved drawings and indicators. Basic has no limit.")
    # a chart already kept stays editable; clearing one makes room
    assert c.put("/me/drawings/IN/INFY", headers=FREE, json={"drawings": [trend(), trend("d2")]}).status_code == 200
    assert c.put("/me/drawings/IN/TCS", headers=FREE, json={"drawings": []}).status_code == 200
    assert c.put("/me/drawings/IN/WIPRO", headers=FREE, json={"drawings": [trend()]}).status_code == 200
    # an empty chart is never refused: nothing is kept
    assert c.put("/me/drawings/IN/HDFCBANK", headers=FREE, json={"drawings": []}).status_code == 200
    # Basic and Pro keep every chart
    for s in ("A", "B", "C", "D", "E"):
        assert c.put(f"/me/drawings/US/{s}", headers=BASIC, json={"drawings": [trend()]}).status_code == 200


def studies(n):
    return [{"id": f"s{i}", "type": "sma", "params": [10 + i], "slot": i} for i in range(n)]


def test_indicators_on_a_chart_are_limited_by_plan(w):
    c = w["client"]
    ok = c.put("/me/drawings/IN/INFY", headers=FREE, json={"drawings": [], "layout": {"studies": studies(3)}})
    assert ok.status_code == 200
    four = c.put("/me/drawings/IN/INFY", headers=FREE, json={"drawings": [], "layout": {"studies": studies(4)}})
    assert four.status_code == 402 and "keeps 3 indicators on a chart. Basic keeps 10." in four.json()["detail"]["message"]
    assert c.put("/me/drawings/IN/INFY", headers=BASIC, json={"drawings": [], "layout": {"studies": studies(10)}}).status_code == 200
    assert c.put("/me/drawings/IN/INFY", headers=BASIC, json={"drawings": [], "layout": {"studies": studies(11)}}).status_code in (402, 422)
    assert c.put("/me/drawings/IN/INFY", headers=PRO, json={"drawings": [], "layout": {"studies": studies(12)}}).status_code == 200


def test_drawings_stay_private_between_people(w):
    c = w["client"]
    c.put("/me/drawings/IN/INFY", headers=PRO, json={"drawings": [trend()]})
    assert c.get("/me/drawings/IN/INFY", headers=OTHER).json()["drawings"] == []
    assert c.get("/me/drawings/summary", headers=OTHER).json()["charts"] == 0


# ---------- prices ----------
def test_quotes_for_stocks_an_index_crypto_forex_and_gold(w):
    c = w["client"]
    ids = "IN:INFY,US:AAPL,IN:^NSEI,US:^GSPC,CRYPTO:BTC-USD,FX:EURUSD=X,CMDTY:GC=F,IN:NOPE123"
    got = c.get(f"/watch/quotes?ids={ids}", headers=PRO).json()["quotes"]
    assert set(got) == set(ids.split(","))
    for k in ("IN:INFY", "US:AAPL", "IN:^NSEI", "US:^GSPC", "CRYPTO:BTC-USD", "FX:EURUSD=X", "CMDTY:GC=F"):
        q = got[k]
        assert q and q["price"] > 0, k
        assert q["change_pct"] is None or abs(q["change_pct"]) < 100, k
        assert q["prev_close"] is None or q["prev_close"] > 0, k
    assert got["IN:INFY"]["currency"] == "INR" and got["US:AAPL"]["currency"] == "USD" and got["CRYPTO:BTC-USD"]["currency"] == "USD"
    assert got["IN:NOPE123"] is None


def test_other_markets_prices_are_read_once_for_everyone(w, monkeypatch):
    c = w["client"]
    seen = []
    real = WQ.registry_quote
    monkeypatch.setattr(WQ, "registry_quote", lambda i: (seen.append(i), real(i))[1])
    for h in (PRO, BASIC, FREE, OTHER):
        got = c.get("/watch/quotes?ids=CRYPTO:BTC-USD", headers=h).json()["quotes"]
        assert got["CRYPTO:BTC-USD"]["price"] > 0
    assert seen == ["CRYPTO:BTC-USD"]                    # four people, one read (quote_share keeps it 15 seconds)


def test_quotes_are_bounded_and_throttled(w):
    c = w["client"]
    many = ",".join(f"CRYPTO:C{i}-USD" for i in range(60))
    got = c.get(f"/watch/quotes?ids={many}", headers=PRO).json()["quotes"]
    assert len(got) == WQ.MAX_IDS
    last = None
    for _ in range(45):
        last = c.get("/watch/quotes?ids=IN:INFY", headers=BASIC)
        if last.status_code == 429:
            break
    assert last.status_code == 429


def test_sparks_are_short_cached_and_left_out_when_unknown(w):
    c = w["client"]
    got = c.get("/watch/spark?ids=IN:INFY,CRYPTO:BTC-USD,US:AAPL,IN:NOPE123", headers=PRO).json()["sparks"]
    assert set(got) == {"IN:INFY", "CRYPTO:BTC-USD", "US:AAPL"}
    for closes in got.values():
        assert 2 <= len(closes) <= WQ.SPARK_POINTS and all(x > 0 for x in closes)
    assert len(WQ._sparks._d) == 3


def test_a_visitor_sees_one_fixed_board_with_no_account(w):
    c = w["client"]
    r = c.get("/public/markets/watch")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=10"
    rows = r.json()["rows"]
    assert [x["id"] for x in rows] == [i for i, _ in WQ.PUBLIC_BOARD]
    priced = [x for x in rows if x.get("price")]
    assert len(priced) >= 8 and all(isinstance(x["spark"], list) for x in rows)
    # no way to ask it for anything else
    assert c.get("/public/markets/watch?ids=IN:INFY").json()["rows"] == rows


def test_the_stream_says_why_nothing_is_streamed_when_the_market_is_closed(w, monkeypatch):
    from app.intel import company
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    c = w["client"]
    with c.stream("GET", "/watch/stream?ids=IN:INFY,US:AAPL", headers=PRO) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    assert "event: hello" in text and '"reason":"closed"' in text and '"poll":["IN:INFY","US:AAPL"]' in text and "event: bye" in text
