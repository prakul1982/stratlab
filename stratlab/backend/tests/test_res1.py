"""RES-1: the results calendar as tables a person can narrow: company size, sector, index, F&O and purpose, a sort, the counts, the
results days of earlier quarters kept for each company, their moves worked out from daily prices, and the options' implied move."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import db, results as R, screens
from app import fo_changes
from app.intel.net import SourceError
from tests import world as W
from tests.fake_db import headers

TODAY = date(2026, 10, 29)             # a Thursday
NIFTY500 = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "ZOMATO", "SMALLCO", "TINYCO"]


def meeting(sym, day, purpose="Financial Results", name=None):
    return {"region": "IN", "symbol": sym, "name": name or f"{sym} Ltd", "date": day.isoformat(), "when": None, "purpose": purpose, "url": None,
            "src": "exchange", "period": None}


def index_row(sym, cap, sector, price=100.0, q=None):
    r = {"symbol": sym, "name": f"{sym} Ltd", "sector": sector, "industry": None, "market_cap": cap, "cap_checked": True, "price": price,
         "price_at": "2026-10-28", "built_at": "2026-10-28T10:00:00+00:00"}
    if q:
        r.update(q_sales=q[0], q_profit=q[1], q_of="Sep 2026 vs Sep 2025")
    return r


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    # 600 listed companies by size so the ranks split into the screener's bands: TCS 1st, INFY 2nd, ... TINYCO beyond the 500th
    big = [index_row("TCS", 1_400_000, "Technology", 4000, (8.0, 6.5)), index_row("INFY", 700_000, "Technology", 1500, (4.0, -2.0)),
           index_row("RELIANCE", 1_800_000, "Energy", 1400, (10.0, 12.0)), index_row("HDFCBANK", 1_300_000, "Financial services", 1700)]
    filler = [index_row(f"CO{i}", 50_000 - i * 10, "Industrials") for i in range(1, 595)]
    mid = index_row("ZOMATO", 48_000, "Consumer services")             # the 204th by market value: a mid cap
    small = index_row("SMALLCO", 47_000, "Industrials")             # the 304th: a small cap
    tiny = index_row("TINYCO", 5, "Industrials")
    db.set_setting("screens:index:IN", json.dumps({"region": "IN", "at": "2026-10-28T12:00:00+00:00", "rows": big + filler + [mid, small, tiny]}))
    screens._mem.clear()
    db.set_setting("breadth:members:nifty500", json.dumps(NIFTY500))
    db.set_setting(fo_changes.KEY, json.dumps({"lots": {"months": ["2026-10"], "rows": {
        "TCS": {"name": "TCS", "index": False, "lots": {"2026-10": 175}}, "INFY": {"name": "Infosys", "index": False, "lots": {"2026-10": 400}},
        "NIFTY": {"name": "NIFTY", "index": True, "lots": {"2026-10": 75}}}}}))
    fo_changes._cache.clear()
    R._sets = None
    rows = [meeting("TCS", TODAY), meeting("INFY", TODAY), meeting("RELIANCE", TODAY + timedelta(days=1), "Financial Results/Dividend"),
            meeting("HDFCBANK", TODAY + timedelta(days=1)), meeting("ZOMATO", TODAY), meeting("SMALLCO", TODAY + timedelta(days=5)),
            meeting("TINYCO", TODAY), meeting("NOINDEX", TODAY)]
    R.save("IN", rows)
    yield world
    R.setup()
    world["close"]()


def symbols(v, on=None):
    return [r["symbol"] for wk in v["weeks"] for r in wk["rows"] if on is None or r["date"] == on]


def view(**kw):
    return R.view("IN", "u-pro", "all", today=TODAY, **kw)


def test_every_row_carries_what_the_app_keeps_about_the_company(w):
    v = view()
    tcs = next(r for wk in v["weeks"] for r in wk["rows"] if r["symbol"] == "TCS")
    assert tcs["cap"] == 1_400_000 and tcs["band"] == "large" and tcs["sector"] == "Technology" and tcs["last"] == 4000 and tcs["last_at"] == "2026-10-28"
    assert tcs["fo"] is True and tcs["indices"] == ["NIFTY 50", "NIFTY 500"]
    assert tcs["q"] == {"sales": 8.0, "profit": 6.5, "of": "Sep 2026 vs Sep 2025"}
    rel = next(r for wk in v["weeks"] for r in wk["rows"] if r["symbol"] == "RELIANCE")
    assert rel["fo"] is False and rel["q"]["profit"] == 12.0           # not in the F&O list the changes page keeps
    nothing = next(r for wk in v["weeks"] for r in wk["rows"] if r["symbol"] == "NOINDEX")
    assert nothing["cap"] is None and nothing["band"] is None and nothing["q"] is None and nothing["indices"] == []


def test_filter_by_size_uses_the_screeners_bands_and_says_how_many_have_no_value(w):
    big = view(size=["large"])
    assert set(symbols(big)) == {"TCS", "INFY", "RELIANCE", "HDFCBANK"} and big["matching"] == 4 and big["total"] == 8
    small = view(size=["micro", "small"])
    assert set(symbols(small)) == {"SMALLCO", "TINYCO"}
    assert small["unknown_size"] == 1                                    # NOINDEX has no market value: left out by the size, and counted
    assert set(symbols(view(size=["mid"]))) == {"ZOMATO"} and set(symbols(view(size=["small"]))) == {"SMALLCO"} and set(symbols(view(size=["micro"]))) == {"TINYCO"}
    assert view()["unknown_size"] == 0 and view(size=["huge"])["matching"] == 8     # a size that does not exist is no filter


def test_filter_by_sector_index_fo_and_purpose(w):
    assert set(symbols(view(sector="Technology"))) == {"TCS", "INFY"}
    assert set(symbols(view(index="nifty50"))) == {"TCS", "INFY", "RELIANCE", "HDFCBANK"}
    assert set(symbols(view(index="nifty500"))) == {"TCS", "INFY", "RELIANCE", "HDFCBANK", "ZOMATO", "SMALLCO", "TINYCO"}
    assert set(symbols(view(index="nothing"))) == set(symbols(view()))          # an index that does not exist is no filter
    fo = view(fo=True)
    assert set(symbols(fo)) == {"TCS", "INFY"} and fo["facets"]["fo"] == 2
    assert "RELIANCE" not in symbols(view(purpose="results")) and "RELIANCE" in symbols(view(purpose="more"))
    assert set(symbols(view(sector="Technology", fo=True, index="nifty50", purpose="results"))) == {"TCS", "INFY"}


def test_filter_by_day_and_counts_and_facets(w):
    tomorrow = view(on="tomorrow")
    assert set(symbols(tomorrow)) == {"RELIANCE", "HDFCBANK"} and tomorrow["total"] == 8 and tomorrow["matching"] == 2
    assert set(symbols(view(on="today"))) == {"TCS", "INFY", "ZOMATO", "TINYCO", "NOINDEX"}
    assert set(symbols(view(on="2026-11-03"))) == {"SMALLCO"}
    f = view()["facets"]
    assert {"name": "Technology", "count": 2} in f["sectors"] and [s["id"] for s in f["sizes"]] == ["large", "mid", "small", "micro"]
    assert next(i for i in f["indices"] if i["id"] == "nifty50")["count"] == 4
    assert view(sector="Technology")["facets"]["sectors"][0] == {"name": "Industrials", "count": 2}       # the offers count every company of the two weeks, not the narrowed ones


def test_sorting_puts_a_company_without_the_figure_last_and_my_stocks_first(w):
    today = symbols(view(on="today"))
    assert today[:2] == ["TCS", "INFY"] and today[-1] in ("NOINDEX", "TINYCO")            # largest market value first
    assert symbols(view(on="today", sort="name"))[0] == "INFY"                              # by name: INFY Ltd before TCS Ltd
    growth = symbols(view(on="today", sort="sales"))
    assert growth[:2] == ["TCS", "INFY"]                                                    # +8% then +4%, the ones without it after
    profit = view(on="today", sort="profit")
    assert symbols(profit)[:2] == ["TCS", "INFY"] and profit["filters"]["sort"] == "profit"
    assert view(sort="bad")["filters"]["sort"] == "cap"
    asc = symbols(view(on="today", sort="cap", desc=False))
    assert asc[0] == "TINYCO" and asc[-1] == "NOINDEX"                                      # smallest first, the one without a value last


def test_a_day_shows_its_first_rows_only_with_the_count(w):
    many = [meeting(f"CO{i}", TODAY) for i in range(1, 60)]
    R.save("IN", many)
    v = view(on="today", limit=25)
    assert len(symbols(v)) == 25 and v["weeks"][0]["days"][0] == {"date": TODAY.isoformat(), "count": 59, "shown": 25}
    assert v["matching"] == 59 and v["more"] == 34
    assert len(symbols(view(on="today", limit=25, day=TODAY.isoformat()))) == 59


# ---------- earlier results days and what the price did over them ----------
def test_days_gone_by_stay_on_a_companys_list_of_earlier_results_days(w):
    rows = [meeting("TCS", date(2026, 7, 9)), meeting("TCS", date(2026, 4, 10)), meeting("TCS", TODAY), meeting("INFY", date(2026, 10, 15))]
    assert R.add_past("IN", rows, TODAY) == 3                                 # today's is not a past one yet
    assert R.load_past("IN")["rows"] == {"TCS": ["2026-07-09", "2026-04-10"], "INFY": ["2026-10-15"]}
    assert R.add_past("IN", rows, TODAY) == 0                                 # again: nothing new
    R.add_past("IN", [meeting("TCS", date(2026, 1, d)) for d in range(1, 9)], TODAY)
    assert len(R.load_past("IN")["rows"]["TCS"]) == R.PAST_KEEP and R.load_past("IN")["rows"]["TCS"][0] == "2026-07-09"


def test_the_weekly_read_goes_back_sixteen_months_in_quarters(w):
    asked = []

    class Feed:
        def board_meetings(self, frm, to):
            asked.append((frm.date(), to.date()))
            return [{"bm_symbol": "TCS", "sm_name": "TCS", "bm_date": (to - timedelta(days=3)).strftime("%d-%b-%Y"), "bm_purpose": "Financial Results", "bm_desc": ""}]

    n = R.backfill("IN", {"in": Feed()}, TODAY)
    assert n == len(asked) == 6                                              # one day found in each of the six reads; the list keeps six
    assert asked[0][1] == TODAY - timedelta(days=1) and asked[-1][0] >= TODAY - timedelta(days=R.PAST_BACK_DAYS)
    assert all((b - a).days < R.PAST_CHUNK for a, b in asked)
    assert len(R.load_past("IN")["rows"]["TCS"]) == min(len(asked), R.PAST_KEEP)


def test_a_feed_that_is_down_leaves_the_stored_days_alone(w):
    R.add_past("IN", [meeting("TCS", date(2026, 7, 9))], TODAY)

    class Down:
        def board_meetings(self, frm, to):
            raise SourceError("the exchange", "busy", busy=True)

    assert R.backfill("IN", {"in": Down()}, TODAY) == 0
    assert R.load_past("IN")["rows"]["TCS"] == ["2026-07-09"]


def bars(closes: dict[str, float]):
    return [{"t": f"{d}T00:00:00+05:30", "c": c} for d, c in sorted(closes.items())]


def test_the_move_over_a_results_day_is_the_close_after_it_against_the_close_before(w):
    series = bars({"2026-07-08": 100, "2026-07-09": 101, "2026-07-10": 110, "2026-07-13": 111})
    assert R.reaction(series, date(2026, 7, 9)) == 10.0           # 100 to the 10th's 110: the results day and the next session
    assert R.reaction(series, date(2026, 7, 13)) == 0.91           # the last session so far: that day's close against the 10th's (110 to 111)
    assert R.reaction(series, date(2026, 7, 7)) is None            # nothing before it
    assert R.reaction([], date(2026, 7, 9)) is None


def test_moves_are_worked_out_from_daily_prices_once_and_kept(w):
    R.add_past("IN", [meeting("TCS", date(2026, 7, 9)), meeting("TCS", date(2026, 4, 10)), meeting("INFY", date(2026, 7, 16))], TODAY)
    asked = []
    prices = {"TCS": bars({"2026-04-09": 100, "2026-04-10": 100, "2026-04-13": 95, "2026-07-08": 100, "2026-07-09": 100, "2026-07-10": 104}),
              "INFY": bars({"2026-07-15": 200, "2026-07-16": 210, "2026-07-17": 190})}
    R.setup(history=lambda region, s, days: asked.append((region, s, days)) or prices[s])
    got = R.moves_for("IN", ["TCS", "INFY", "NOTHING"], TODAY)
    assert got["TCS"]["moves"] == {"avg": 4.5, "n": 2, "last": [4.0, -5.0], "dates": ["2026-07-09", "2026-04-10"]} and got["TCS"]["since"] is None
    assert got["INFY"]["moves"]["last"] == [-5.0] and got["NOTHING"] is None      # no earlier results day: no figure
    assert [a[1] for a in asked] == ["TCS", "INFY"] and all(a[2] == R.HISTORY_DAYS for a in asked)
    R.moves_for("IN", ["TCS", "INFY"], TODAY)
    assert len(asked) == 2                                                          # kept: the prices are not read again
    # a new results day for the company is a new reading
    R.add_past("IN", [meeting("TCS", date(2026, 10, 10))], TODAY)
    prices["TCS"] = prices["TCS"] + bars({"2026-10-09": 100, "2026-10-12": 103})
    assert R.moves_for("IN", ["TCS"], TODAY)["TCS"]["moves"]["last"][0] == 3.0 and len(asked) == 3


def test_only_a_few_companies_prices_are_read_in_one_ask(w):
    R.add_past("IN", [meeting(f"CO{i}", date(2026, 7, 9)) for i in range(1, 15)], TODAY)
    asked = []
    R.setup(history=lambda r, s, d: asked.append(s) or bars({"2026-07-08": 100, "2026-07-10": 101}))
    got = R.moves_for("IN", [f"CO{i}" for i in range(1, 15)], TODAY)
    assert len(asked) == R.MOVES_PER_ASK and sum(1 for v in got.values() if v) == R.MOVES_PER_ASK
    R.moves_for("IN", [f"CO{i}" for i in range(1, 15)], TODAY)
    assert len(asked) == 2 * R.MOVES_PER_ASK                                        # the next ask does the next six


def test_a_company_whose_prices_cannot_be_read_is_not_asked_again_until_its_days_change(w):
    R.add_past("IN", [meeting("TCS", date(2026, 7, 9))], TODAY)
    asked = []

    def down(region, s, days):
        asked.append(s)
        raise SourceError("the broker", "busy", busy=True)

    R.setup(history=down)
    assert R.moves_for("IN", ["TCS"], TODAY)["TCS"] is None
    R.moves_for("IN", ["TCS"], TODAY)
    assert asked == ["TCS"]


def test_since_the_results_is_the_latest_close_against_the_close_before_the_day(w):
    R.save("IN", [meeting("TCS", TODAY - timedelta(days=2)), meeting("INFY", TODAY), meeting("HDFCBANK", TODAY, "Financial Results")])
    R._since = None
    series = bars({"2026-10-26": 4000, "2026-10-27": 4010, "2026-10-28": 4200, "2026-10-29": 4180})
    asked = []
    R.setup(history=lambda r, s, d: asked.append(s) or series)
    got = R.moves_for("IN", ["TCS", "INFY"], TODAY)
    assert got["TCS"] == {"moves": None, "since": {"date": "2026-10-27", "pct": 4.5}}       # the latest close, 4180, against the 26th (the session before the 27th): 4000
    assert got["INFY"] is None and asked == ["TCS"]                                           # today's results are not out: nothing since
    R.moves_for("IN", ["TCS"], TODAY)
    assert asked == ["TCS"]                                                                   # kept for ten minutes
    # today's results once filed
    rows = [meeting("INFY", TODAY)]
    rows[0]["out"] = {"at": "2026-10-29T16:40", "title": "Results", "url": None, "numbers": []}
    R.save("IN", rows)
    assert R.recent_event("IN", "INFY", TODAY) == TODAY.isoformat()
    assert R.since_move(series, date(2026, 10, 30)) is None and R.since_move([], TODAY) is None


def test_moves_shown_on_the_row_and_sorted_by(w):
    R.add_past("IN", [meeting("TCS", date(2026, 7, 9)), meeting("INFY", date(2026, 7, 16))], TODAY)
    R.setup(history=lambda r, s, d: bars({"2026-07-08": 100, "2026-07-09": 100, "2026-07-15": 100, "2026-07-16": 100, "2026-07-10": 104, "2026-07-17": 92}))
    R.moves_for("IN", ["TCS", "INFY"], TODAY)
    v = view(on="today", sort="move")
    rows = {r["symbol"]: r for wk in v["weeks"] for r in wk["rows"]}
    assert rows["TCS"]["moves"] == {"avg": 4.0, "n": 1, "last": [4.0], "dates": ["2026-07-09"]}
    assert symbols(v)[:2] == ["INFY", "TCS"]                                         # the larger usual move first (8%, then 4%)
    assert rows["ZOMATO"]["moves"] is None


# ---------- the options' implied move ----------
def chain(spot=4000.0, expiry="2026-11-24", ce=60.0, pe=58.0):
    return {"spot": spot, "expiry": expiry, "atm": 4000,
            "rows": [{"strike": 3950, "ce": {"ltp": 90}, "pe": {"ltp": 30}}, {"strike": 4000, "ce": {"ltp": ce}, "pe": {"ltp": pe}}, {"strike": 4050, "ce": {"ltp": 30}, "pe": {"ltp": 90}}]}


def test_the_implied_move_is_the_money_straddle_over_the_price():
    assert R.straddle_move(chain()) == {"pct": 2.9, "strike": 4000, "expiry": "2026-11-24", "straddle": 118.0}
    assert R.straddle_move(chain(spot=4020)) ["strike"] == 4000
    assert R.straddle_move(chain(ce=None)) is None and R.straddle_move({"spot": None, "rows": []}) is None
    assert R.straddle_move({**chain(), "rows": []}) is None


def test_implied_moves_are_for_stocks_with_options_only_and_a_few_at_a_time(w):
    asked = []
    R.setup(options=lambda s, day: asked.append((s, day)) or R.straddle_move(chain()))
    got = R.implied_for(["TCS", "RELIANCE", "INFY"], "2026-10-29")
    assert got["TCS"]["pct"] == 2.9 and got["RELIANCE"] is None and got["INFY"]["pct"] == 2.9 and [a[0] for a in asked] == ["TCS", "INFY"]
    assert len(R.implied_for([f"S{i}" for i in range(20)])) == 8                      # no more than 8 in one ask
    R.setup(options=lambda s, day: (_ for _ in ()).throw(RuntimeError("no quote")))
    assert R.implied_for(["TCS"])["TCS"] is None                                      # a failed read is a blank, never a broken page
    R.setup()
    assert R.implied_for(["TCS"])["TCS"] is None                                       # no options source: blank


# ---------- the API ----------
def test_the_api_takes_the_filters_and_has_the_two_new_reads(w):
    c = w["client"]
    h = headers("pro-token")
    c.get("/me", headers=h)
    v = c.get("/research/results", params={"region": "IN", "scope": "all", "size": "large", "sector": "Technology", "fo": "true", "sort": "cap"}, headers=h)
    assert v.status_code == 200, v.text
    body = v.json()
    assert body["filters"]["size"] == ["large"] and body["filters"]["fo"] is True and "total" in body and "facets" in body
    assert c.get("/research/results", params={"scope": "all", "on": "never", "sort": "x'; drop"}, headers=h).json()["filters"]["sort"] == "cap"
    m = c.get("/research/results/moves", params={"region": "IN", "symbols": "TCS,INFY"}, headers=h)
    assert m.status_code == 200 and set(m.json()["moves"]) == {"TCS", "INFY"}
    i = c.get("/research/results/implied", params={"symbols": "TCS", "day": "2026-10-29"}, headers=h)
    assert i.status_code == 200 and "TCS" in i.json()["implied"]
    assert c.get("/research/results/moves", params={"symbols": "TCS"}).status_code == 401
    assert c.get("/research/results/IN/TCS", headers=h).status_code == 200            # the company route still answers


# ---------- the corporate actions calendar, narrowed the same way ----------
def corp(sym, purpose, ex, name=None):
    from app import corp_actions as C
    return [C.row("IN", sym, a, ex, name=name or f"{sym} Ltd", purpose=purpose) for a in C.parse_purpose(purpose, None, "₹")]


@pytest.fixture
def cw(w):
    from app import corp_actions as C
    rows = (corp("TCS", "Interim Dividend - Rs 12 Per Share", TODAY) + corp("INFY", "Bonus 1:1", TODAY + timedelta(days=1))
            + corp("RELIANCE", "Special Dividend - Rs 56 Per Share", TODAY + timedelta(days=1))
            + corp("HDFCBANK", "Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share", TODAY + timedelta(days=3))
            + corp("SMALLCO", "Interim Dividend - Rs 3 Per Share", TODAY + timedelta(days=3)) + corp("TINYCO", "Buy Back", TODAY - timedelta(days=3))
            + corp("NOINDEX", "Interim Dividend - Rs 1 Per Share", TODAY))
    C.save("IN", rows)
    return w


def cview(**kw):
    from app import corp_actions as C
    return C.view("IN", "u-pro", "all", today=TODAY, **kw)


def csyms(v):
    return [r["symbol"] for r in v["ahead"] + v["recent"]]


def test_corporate_actions_carry_the_companys_facts_and_a_dividends_yield(cw):
    v = cview()
    tcs = next(r for r in v["ahead"] if r["symbol"] == "TCS")
    assert tcs["cap"] == 1_400_000 and tcs["band"] == "large" and tcs["sector"] == "Technology" and tcs["last"] == 4000 and tcs["fo"] is True
    assert tcs["yield_pct"] == 0.3                                                      # ₹12 over the ₹4,000 close
    rel = next(r for r in v["ahead"] if r["symbol"] == "RELIANCE")
    assert rel["yield_pct"] == 4.0                                                      # ₹56 over ₹1,400
    assert next(r for r in v["ahead"] if r["symbol"] == "INFY")["yield_pct"] is None    # a bonus has no yield
    assert next(r for r in v["ahead"] if r["symbol"] == "NOINDEX")["yield_pct"] is None  # no close kept: no yield
    assert v["total"] == 7 and v["matching"] == 7 and set(v["facets"]) == {"sizes", "sectors", "indices", "fo"}


def test_corporate_actions_filters_by_kind_size_sector_index_fo_and_day(cw):
    assert set(csyms(cview(kind="dividend"))) == {"TCS", "RELIANCE", "SMALLCO", "NOINDEX"}
    assert set(csyms(cview(kind="buyback"))) == {"TINYCO"}
    assert set(csyms(cview(size=["large"]))) == {"TCS", "INFY", "RELIANCE", "HDFCBANK"}
    small = cview(size=["small", "micro"])
    assert set(csyms(small)) == {"SMALLCO", "TINYCO"} and small["unknown_size"] == 1 and small["matching"] == 2 and small["total"] == 7
    assert set(csyms(cview(sector="Technology"))) == {"TCS", "INFY"} and set(csyms(cview(index="nifty50"))) == {"TCS", "INFY", "RELIANCE", "HDFCBANK"}
    assert set(csyms(cview(fo=True))) == {"TCS", "INFY"}
    assert set(csyms(cview(on="tomorrow"))) == {"INFY", "RELIANCE"} and set(csyms(cview(on="today"))) == {"TCS", "NOINDEX"}
    assert set(csyms(cview(on=(TODAY + timedelta(days=3)).isoformat()))) == {"HDFCBANK", "SMALLCO"}
    assert set(csyms(cview(kind="dividend", sector="Technology", fo=True))) == {"TCS"}
    assert set(csyms(cview(index="nothing", size=["huge"]))) == set(csyms(cview()))   # an index or size that does not exist is no filter


def test_corporate_actions_sort_within_each_day_and_keep_the_days_in_order(cw):
    v = cview(sort="cap")
    days = [r["ex_date"] for r in v["ahead"]]
    assert days == sorted(days)                                                         # the next day first, whatever the sort
    assert [r["symbol"] for r in v["ahead"] if r["ex_date"] == (TODAY + timedelta(days=1)).isoformat()] == ["RELIANCE", "INFY"]     # the larger company first
    assert [r["symbol"] for r in cview(sort="yield")["ahead"] if r["ex_date"] == TODAY.isoformat()] == ["TCS", "NOINDEX"]            # 0.3%, then none
    assert [r["symbol"] for r in cview(sort="name")["ahead"] if r["ex_date"] == TODAY.isoformat()] == ["NOINDEX", "TCS"]
    assert cview(sort="bad")["filters"]["sort"] == "date"
    assert [r["symbol"] for r in v["recent"]] == ["TINYCO"]


def test_the_corporate_actions_api_takes_the_filters(cw):
    c = cw["client"]
    h = headers("pro-token")
    c.get("/me", headers=h)
    r = c.get("/research/corp-actions", params={"region": "IN", "scope": "all", "kind": "dividend", "size": "large", "fo": "true", "sort": "yield"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filters"]["size"] == ["large"] and body["filters"]["fo"] is True and "facets" in body and "total" in body
    assert c.get("/research/corp-actions", params={"scope": "all", "on": "x", "sort": "' or 1=1"}, headers=h).json()["filters"]["sort"] == "date"
