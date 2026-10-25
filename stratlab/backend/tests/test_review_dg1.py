"""25 Oct 2026 deep audit of the Money data and maths (DG-001 .. DG-060, and DP2-001 .. DP2-040 on the same pages): holdings
valued at the last close while live prices are off, gold and gold bonds too; a gain or loss of some lines said to be of
those lines; floating-rate loans on their rate path everywhere, the 7 Oct 2026 repo hike in the history; the 31 Jan 2018
NAVs from the scheme's NAV history; odd fund rows said, index funds counted as equity; the SIP test from stored history
with ETF charges right; one gold price across pages. Saved real files are read where the facts come from a page."""
import base64
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import holdings, holdings_file as hf, last_session, main, official_close
from tests import world

FIX = Path(__file__).parent / "fixtures"
PRO = world.headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    main._PRICED.clear()
    yield built
    main._PRICED.clear()
    built["close"]()


def upload(c, name: str, data: bytes | None = None, mode="replace"):
    raw = data if data is not None else (FIX / "holdings" / name).read_bytes()
    return c.post("/holdings/import", headers=PRO, json={"filename": name, "data": base64.b64encode(raw).decode(), "mode": mode})


def _sessions() -> tuple[str, str]:
    """The latest completed session and the one before it."""
    d = last_session.latest_day("IN")
    return d, last_session.on_or_before("IN", date.fromisoformat(d) - timedelta(days=1)).isoformat()


# ---------- DP2-001, DG-002: the last close while live prices are off ----------
def test_offline_holdings_are_valued_at_the_stored_close_with_its_move(w, monkeypatch):
    c = w["client"]
    assert upload(c, "zerodha_console_holdings.xlsx").status_code == 200
    day, before = _sessions()
    official_close.save(day, {"RELIANCE": 1190.0, "TCS": 3000.0, "HDFCBANK": 1000.0, "NIFTYBEES": 257.22})
    official_close.save(before, {"RELIANCE": 1180.0, "TCS": 3030.0, "NIFTYBEES": 258.0})
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    main._PRICED.clear()
    v = c.get("/holdings", headers=PRO).json()
    rows = {r["symbol"]: r for r in v["rows"]}
    rel = rows["RELIANCE"]
    assert rel["price"] == 1190.0 and rel["value"] == 50 * 1190 and rel["price_from"] == "close"
    assert rel["day"] == 50 * 10.0 and rel["session"] == day                            # Friday's move, of Friday's session
    assert rows["HDFCBANK"]["price"] == 1000.0 and rows["HDFCBANK"]["day"] is None      # no close of the session before
    # the BSE-only and restricted-series lines have no stored close: the close in the file stands for them
    assert rows["TINYCO"]["price"] == 22.0 and rows["TINYCO"]["price_from"] == "file" and rows["TINYCO"]["day"] is None
    assert v["closes"] == {"day": day, "close": 4, "file": 2}
    assert v["totals"]["pnl"] is not None and v["totals"]["pnl_partial"] is None       # every line priced: the whole portfolio's
    assert v["prices_at"].startswith(day)


def test_the_files_previous_close_is_kept_and_dated_by_the_session(w, monkeypatch):
    rows = {r["symbol"]: r for r in hf.parse((FIX / "holdings" / "zerodha_console_holdings.xlsx").read_bytes())["rows"]}
    assert rows["RELIANCE"]["close"] == 2902.1 and rows["NIFTYBEES"]["close"] == 271.3      # "Previous Closing Price"
    c = w["client"]
    upload(c, "zerodha_console_holdings.xlsx")
    saved = {i["symbol"]: i for i in holdings.load("u-pro")["items"]}
    assert saved["RELIANCE"]["file_close"] == 2902.1 and saved["RELIANCE"]["file_close_day"] == last_session.latest_day("IN")
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    main._PRICED.clear()
    v = c.get("/holdings", headers=PRO).json()
    assert {r["price_from"] for r in v["rows"]} == {"file"} and v["closes"]["file"] == 6 and v["totals"]["pnl"] is not None
    # an old file's close isn't passed off as today's: beyond FILE_CLOSE_DAYS the line is at cost
    old = (date.fromisoformat(last_session.latest_day("IN")) - timedelta(days=main.FILE_CLOSE_DAYS + 3)).isoformat()
    holdings.save("u-pro", [{**i, "file_close_day": old} for i in holdings.load("u-pro")["items"]], "Zerodha Console", stamped=True)
    main._PRICED.clear()
    v = c.get("/holdings", headers=PRO).json()
    assert v["closes"] is None and all(r["price"] is None for r in v["rows"])


# ---------- DG-001, DG-050: a gain or loss of some lines is of those lines ----------
def test_a_gain_of_one_line_of_nine_is_said_to_be_of_that_line():
    items = [{"symbol": "AAPL", "market": "US", "qty": 5, "avg": 150}] + [{"symbol": f"S{n}", "qty": 10, "avg": 100} for n in range(8)]
    v = holdings.view(items, {}, {"AAPL": {"price": 347.73, "change": -0.5, "change_pct": -0.14}}, 94.94)
    t = v["totals"]
    assert t["pnl_partial"] == {"priced": 1, "lines": 9} and t["pnl"] == round(5 * (347.73 - 150) * 94.94, 2)
    whole = holdings.view(items[1:], {f"S{n}": {"price": 110, "change": 1} for n in range(8)})
    assert whole["totals"]["pnl_partial"] is None


# ---------- DG-003, DG-004 ----------
def test_etfs_are_split_by_what_they_hold_and_zero_lines_are_said():
    v = holdings.view([{"symbol": "NIFTYBEES", "kind": "etf-equity", "qty": 10, "avg": 250}, {"symbol": "GOLDBEES", "kind": "etf-gold", "qty": 10, "avg": 100}], {})
    assert sorted(a["sector"] for a in v["allocation"]) == ["Equity ETFs", "Gold ETFs"]
    got = hf.parse(b"Symbol,Qty,Avg\nRELIANCE,40,1200\nINFY,-5,1500\nTCS,0,3000\n")
    assert [p["text"] for p in got["problems"]] == ["INFY", "TCS"] and "below 0" in got["problems"][0]["reason"]


# ---------- DG-010, DG-060: one gold price, the last one read while the broker is off ----------
def test_gold_and_gold_bonds_keep_the_last_price_while_the_broker_is_off(w, monkeypatch):
    import json
    from app import db
    c = w["client"]
    main._nw_prices.clear()
    db.set_setting(main.GOLD_LAST, json.dumps({"per_g": 14215.0, "at": "2026-10-23T23:30+05:30"}))
    prov = main.markets.provider("MCX")
    monkeypatch.setattr(prov, "ready", lambda: False)
    c.delete("/money/net-worth", headers=PRO)
    c.post("/money/net-worth/items", headers=PRO, json={"kind": "gold", "name": "R test gold", "grams": 50, "purity": 22})
    v = c.post("/money/net-worth/items", headers=PRO, json={"kind": "sgb", "units": 20, "issue_price": 6213}).json()
    rows = {r["kind"]: r for r in v["assets"]}
    assert rows["gold"]["value"] == round(50 * 14215 * 22 / 24, 2) and rows["gold"]["basis"] == "market price"
    assert rows["sgb"]["value"] == 20 * 14215 and not v["totals"]["partial"]          # not the issue price, nothing left out
    g = c.get("/money/gold", headers=PRO).json()
    assert g["per_10g"] == 142150 and g["as_of"].startswith("2026-10-23") and g["duty_pct"] == 15.0
    main._nw_prices.clear()


# ---------- DP2-040: Friday's close of a currency pair, from the point the source stamps Saturday ----------
def test_usd_inr_tile_ends_on_fridays_close_not_thursdays():
    import httpx
    from app.data.yahoo_markets import YahooProvider
    from app.intel.yahoo import Yahoo
    raw = (FIX / "fx" / "yahoo_usdinr_1d_2026-10-25.json").read_bytes()      # the source's answer, read on 25 Oct 2026
    y = Yahoo(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=raw, headers={"content-type": "application/json"})))
    prov = YahooProvider("FX", y)
    bars = prov.history(prov.instrument("USDINR=X"), "1d", 10)
    assert bars[-1]["t"][:10] == "2026-10-23" and round(bars[-1]["c"], 2) == 94.94        # RBI's reference rate that day: 94.9432
    assert round(bars[-2]["c"], 2) == 94.31 and all(datetime.fromisoformat(b["t"][:10]).weekday() < 5 for b in bars)


# ---------- DG-011, DG-012, DG-013: a floating loan on its rate path everywhere ----------
LOAN = {"kind": "loan", "loan_type": "home", "principal": 5000000, "rate": 8.5, "tenure_months": 240, "start": "2023-04-15",
        "benchmark": "repo", "reset_months": 3, "last_reset": "2026-07-01"}


def test_the_7_oct_2026_hike_is_in_the_repo_history_as_rbi_announced_it():
    import html
    import re
    from app import rbi_rates
    page = (FIX / "rates" / "rbi_mpc_resolution_2026-10-07.html").read_text()
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    assert "increase the policy repo rate under the liquidity adjustment facility (LAF) by 25 bps to 5.50 per cent" in text
    assert rbi_rates.REPO_HISTORY[-1] == ("2026-10-07", 5.50)
    home = rbi_rates.parse((FIX / "rates" / "rbi_home_2026-10-25.html").read_text())
    assert home["repo"] == 5.50 and "tbills" not in home and home["gsec_date"] == "2026-10-22"


def test_net_worth_check_and_prepay_owe_the_same_on_the_rate_path(w):
    from app import loan_check, money_networth as nw, rbi_rates
    c = w["client"]
    c.delete("/money/net-worth", headers=PRO)
    v = c.post("/money/net-worth/items", headers=PRO, json=LOAN).json()
    row = v["liabilities"][0]
    item = nw.load("u-pro")["items"][0]
    check = loan_check.check(item, nw.today(), rbi_rates.repo_history())
    assert row["value"] == check["outstanding"]                                   # one balance on the page, not two
    fixed = nw.loan_state(5000000, 8.5, 240, date(2023, 4, 15), nw.today())
    assert row["value"] < fixed["outstanding"] and row["facts"]["rate_now"] == check["expected"] < 8.5
    assert "floating rate since" in row["rule"]
    p = c.post("/money/net-worth/prepay", headers=PRO, json={"id": item["id"], "amount": 100000}).json()
    assert p["rate"] == check["expected"] and p["outstanding"] == row["value"]
    # a rise after a cut: the new EMI is set against the old rate's EMI for the same months, so it goes up (DG-012)
    rise = [ch for ch in check["changes"] if ch["to"] > ch["from"]]
    assert all(ch["emi_change"] > 0 for ch in rise)
    nxt = loan_check.rate_path(item, nw.today(), rbi_rates.repo_history())
    assert nxt["repo_now"] == 5.50 and nxt["next_expected"] == round(5.50 + nxt["spread"], 2)


# ---------- DP2-005, DP2-006, DG-015, DG-016 ----------
def test_zero_entries_are_refused_and_added_money_is_marked_in_the_snapshot(w):
    from app import money_networth as nw
    c = w["client"]
    c.delete("/money/net-worth", headers=PRO)
    r = c.post("/money/net-worth/items", headers=PRO, json={"kind": "cash", "value": 0})
    assert r.status_code == 422 and "above 0" in r.json()["detail"]["message"]
    c.post("/money/net-worth/items", headers=PRO, json={"kind": "cash", "value": 125000})
    v = c.post("/money/net-worth/items", headers=PRO, json={"kind": "fd", "principal": 100000, "rate": 7, "start": "2026-10-01", "maturity": "2027-10-01"}).json()
    today_snap = [h for h in nw.history("u-pro") if h["d"] == nw.today().isoformat()][0]
    fd = next(r for r in v["assets"] if r["kind"] == "fd")["value"]
    assert today_snap["added"] == round(125000 + fd, 2)                           # both entries of the day, not a gain
    ppf = c.post("/money/net-worth/items", headers=PRO, json={"kind": "ppf", "balance": 800000, "as_of": "2026-04-01", "paid_since": 150000}).json()
    row = next(r for r in ppf["assets"] if r["kind"] == "ppf")
    assert "₹1,50,000 deposited since" in row["rule"] and row["value"] > 950000
    csv = c.get("/money/net-worth/export", headers=PRO).text
    assert "matured: no" in csv and "matured: False" not in csv
    assert all(len(line.split(",")[4]) <= 10 for line in csv.splitlines()[1:] if line.startswith("Asset"))


# ---------- DG-040, DG-042: T-bills while RBI's page shows none; compounding compared ----------
def test_tbills_last_read_stay_dated_while_the_page_shows_none(w, monkeypatch):
    from app import fixed_income as F, rbi_rates as R
    old = (FIX / "rates" / "rbi_home_rates.html").read_text()            # 5 Oct 2026: cut-offs on the page
    new = (FIX / "rates" / "rbi_home_2026-10-25.html").read_text()       # 25 Oct 2026: "91 day T-bills : -%*"
    page = {"t": old}
    monkeypatch.setattr(R, "fetch_text", lambda url=R.URL: page["t"])
    R.forget()
    first = R.current()["rates"]
    assert first.get("tbills") and first.get("tbills_at")
    page["t"] = new
    R.forget()
    R._mem.update(rates=first, at=0.0)            # the copy kept, old enough to read again
    got = R.current()["rates"]
    assert got["tbills_blank"] is True and got["tbills_last"]["rates"] == first["tbills"]
    v = c_rates = w["client"].get("/money/rates?slab=30", headers=PRO).json()
    bills = [r for r in v["market"] if r["key"].startswith("tbill")]
    assert bills and all("as last read" in r["how"] for r in bills) and "no Treasury bill cut-offs" in v["tbill_note"]
    td5 = next(r for r in c_rates["small_savings"]["rows"] if r["key"] == "td5")
    assert F.effective(7.5, "Compounded quarterly, paid yearly") == 7.71 and td5["effective"] == 7.71
    assert F.effective(7.7, "Compounded yearly, paid at maturity") is None
    R.forget()


# ---------- DG-020 .. DG-025, DP2-017: mutual funds ----------
def test_31_jan_2018_nav_comes_from_the_schemes_nav_history(w, monkeypatch):
    import json
    from app import money_mf_nav as N
    raw = json.loads((FIX / "mf" / "amfi_nav_history_120716_2018-01.json").read_text())   # AMFI's answer, read 25 Oct 2026
    asked = []
    monkeypatch.setattr(N, "fetch_history", lambda code, a, b: asked.append((code, a, b)) or raw)
    N.forget()
    assert N.nav_on(raw, "2018-01-31") == 71.3422 and N.nav_on(raw, "2018-01-30") == 71.4873
    assert N.gf_one("120716") == 71.3422 and asked == [("120716", N.GF_FROM, N.GF_DAY)]
    N.forget()
    assert N.gf_one("120716") == 71.3422 and len(asked) == 1                # saved for everyone
    N.forget()


def test_odd_fund_rows_are_said_and_index_funds_are_equity():
    from app import money_mf as M
    csv = (b"Date,Scheme,AMFI code,Units,Amount,Type\n"
           b"2024-01-10,X Corporate Bond Fund - Direct Growth,900020,2551.943,70000,Purchase\n"
           b"2024-06-10,X Corporate Bond Fund - Direct Growth,900020,-6000,200000,Redemption\n"
           b"2024-02-10,X Flexi Cap Fund - Direct Growth,900021,-50,-5000,Purchase\n")
    got = M.parse_csv(csv)
    assert [p["line"] for p in got["problems"]] == [4] and "negative units" in got["problems"][0]["reason"]
    data = {"schemes": got["schemes"], "txns": got["txns"], "kinds": {}, "fmv": {}, "files": []}
    c = M.compute(data, {s["k"]: "debt" for s in got["schemes"]}, {})
    k = got["schemes"][0]["k"]
    assert round(c["short"][k], 3) == 3448.057 and round(c["short_sale"][k]) == round(3448.057 * 200000 / 6000)
    assert M.broad_of("Other Scheme - Index Funds", "equity") == ("Equity", "Index funds")


def test_elss_units_redeemed_inside_the_lock_in_are_counted():
    from app import money_mf as M
    s = {"k": "F|E", "name": "X ELSS Tax Saver Fund - Direct Growth", "folio": "F"}
    tx = [{"k": "F|E", "d": "2023-12-10", "t": "purchase", "u": 100.0, "a": 10000.0, "n": 100.0},
          {"k": "F|E", "d": "2026-08-01", "t": "redeem", "u": -40.0, "a": 6000.0, "n": 150.0}]
    c = M.compute({"schemes": [s], "txns": tx, "kinds": {}, "fmv": {}}, {"F|E": "equity"}, {}, {"F|E"})
    assert c["elss_early"]["F|E"] == 40.0
    late = M.compute({"schemes": [s], "txns": [tx[0], {**tx[1], "d": "2027-01-10"}], "kinds": {}, "fmv": {}}, {"F|E": "equity"}, {}, {"F|E"})
    assert not late["elss_early"]


def test_import_counts_say_the_kept_schemes_and_the_stamp_duty_lines():
    from app import money_mf as M
    got = M.read_file((FIX / "mf" / "synthetic_cas.pdf").read_bytes(), "x.pdf", "ABCDE1234F")
    _, counts = M.merge(M.empty(), got, 1)
    assert counts["schemes"] == 2 and counts["kept"] == 1                  # "from 1 of the file's 2 schemes"
    _, counts = M.merge(M.empty(), got, None)
    assert (counts["added"], counts["charges"], counts["kept"]) == (7, 2, 2)  # 5 transactions, a stamp duty and an STT line


# ---------- DG-030, DG-031, DP2-002: the SIP test from stored history, ETF charges right ----------
def test_sip_test_runs_offline_from_the_search_and_etfs_pay_no_stt(w, monkeypatch):
    from app import sip_test as S
    c = w["client"]
    online = c.get("/instruments/search?q=INFY&market=IN", headers=PRO).json()[0]["id"]
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    rows = c.get("/instruments/search?q=INFY&market=IN", headers=PRO).json()
    assert rows and rows[0]["id"] == "IN:INFY" and rows[0]["stored"] is True
    r = c.post("/invest/sip-test", headers=PRO, json={"legs": [{"inst_id": "IN:INFY"}], "years": 2})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["invested"] > 0 and online != "IN:INFY"
    # an ETF's purchase has no STT: only fees, stamp duty and GST
    assert S.charge_rate("in_etf") < S.charge_rate("in_eq") - 0.0009
    assert S.cost_kind({"symbol": "NIFTYBEES", "type": "EQ", "name": "Nippon India ETF Nifty 50 BeES"}) == "in_etf"
    assert S.cost_kind({"symbol": "RELIANCE", "type": "EQ", "name": "Reliance Industries"}) == "in_eq"
    q, spent, stamp = S.buy(10000, 257.22, 0, "in_etf")
    assert q == 38 and round(spent - q * 257.22, 2) == round(q * 257.22 * (0.0000317 * 1.18 + 0.00015), 2)
