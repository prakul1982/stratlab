"""My Holdings: reading each broker's holdings export, matching lines to listed companies (NSE first, then BSE-only),
the page's numbers and facts, manual edits, privacy and deletion, the plan limit, and the My Stocks newsletter."""
import base64
import json
from datetime import date
from pathlib import Path

import pytest

from app import db, holdings, holdings_file as hf, main
from app.config import settings
from app.intel import filings
from app.newsletter import content
from tests import world, xlsxmaker

FIX = Path(__file__).parent / "fixtures" / "holdings"
PRO, FREE = world.headers("pro-token"), world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def upload(c, name: str, data: bytes | None = None, headers=PRO, mode="replace", data_url=False):
    raw = data if data is not None else (FIX / name).read_bytes()
    b64 = base64.b64encode(raw).decode()
    if data_url:
        b64 = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + b64
    return c.post("/holdings/import", headers=headers, json={"filename": name, "data": b64, "mode": mode})


def held(r) -> dict:
    return {x["symbol"]: x for x in r.json()["holdings"]["rows"]}


# ---------- reading files ----------
def test_numbers_as_brokers_write_them():
    assert hf.number("1,23,456.50") == 123456.5 and hf.number("₹ 2,410.35") == 2410.35 and hf.number("Rs. 99") == 99
    assert hf.number("(1,250.00)") == -1250 and hf.number("-") is None and hf.number("") is None
    assert hf.number("abc") is None and hf.number("nan") is None and hf.number("1e999") is None


def test_every_sample_file_is_read_and_its_broker_recognised():
    expect = {"zerodha_console_holdings.xlsx": ("Zerodha Console", 6), "zerodha_kite_holdings.csv": ("Zerodha Kite", 4),
              "groww_holdings_statement.xlsx": ("Groww", 5), "icici_direct_portfolio.csv": ("ICICI Direct", 4),
              "upstox_holdings.csv": ("Upstox", 3), "angel_one_holding_report.xlsx": ("Angel One", 3),
              "hdfc_securities_portfolio.xls": ("HDFC Securities", 3), "generic.csv": ("CSV", 4)}
    for name, (broker, n) in expect.items():
        got = hf.parse((FIX / name).read_bytes(), name)
        assert (got["broker"], len(got["rows"])) == (broker, n), name


def test_zerodha_console_counts_pledged_shares_and_skips_the_summary_above():
    rows = {r["symbol"]: r for r in hf.parse((FIX / "zerodha_console_holdings.xlsx").read_bytes())["rows"]}
    assert rows["RELIANCE"]["qty"] == 50 and rows["RELIANCE"]["avg"] == 2410.35          # 40 available + 10 pledged
    assert rows["RELIANCE"]["isin"] == "INE002A01018" and "Invested Value" not in rows


def test_totals_notes_and_lines_without_a_quantity():
    csv = b"Symbol,Qty,Avg price\nRELIANCE,10,2500\nTCS,,3500\n\nNotes: prices as of close\nTotal,10,\nINFY,0,1500\n"
    got = hf.parse(csv)
    assert [r["symbol"] for r in got["rows"]] == ["RELIANCE"]                            # INFY at 0 is sold: left out
    assert got["problems"] == [{"line": 3, "text": "TCS", "reason": "No quantity on this line."}]


def test_a_bare_list_and_other_separators():
    assert [r["symbol"] for r in hf.parse(b"RELIANCE,10,2500\nTCS,5\n")["rows"]] == ["RELIANCE", "TCS"]
    got = hf.parse("Symbol;Quantity;Average Price\nSBIN;12;600,5\n".encode())        # semicolons
    assert got["rows"][0]["symbol"] == "SBIN" and got["rows"][0]["qty"] == 12
    got = hf.parse("Symbol\tQty\nITC\t7\n".encode("utf-16"))                              # tab separated, saved as UTF-16 by Excel
    assert got["rows"][0]["symbol"] == "ITC" and got["rows"][0]["avg"] is None


def test_files_we_cant_use_get_a_plain_answer():
    for data, words in ((b"", "empty"), (b"%PDF-1.4 ...", "PDF"), (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100, ".xls"),
                        (b"PK\x03\x04garbage", "couldn't be opened"), (b"hello,world\nfoo,bar\n", "couldn't find the holdings"),
                        (b"x" * (hf.MAX_BYTES + 1), "larger than"), (b"\x00\x01\x02" * 50, "doesn't look like")):
        with pytest.raises(hf.FileError) as e:
            hf.parse(data)
        assert words in str(e.value), words


def test_a_zip_bomb_stops_at_the_size_cap():
    import io
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"<worksheet>" + b" " * (hf.MAX_XML + 10) + b"</worksheet>")
    assert len(out.getvalue()) < hf.MAX_BYTES
    with pytest.raises(hf.FileError, match="too large"):
        hf.parse(out.getvalue())


# ---------- matching ----------
def offline_matcher():
    return holdings.Matcher(lambda s: None, lambda n: None, {"INE002A01018": "RELIANCE"}.get, {"RELIANCE": "Reliance Industries"}, False)


def test_offline_matching_uses_the_exchange_list_only():
    m = offline_matcher()
    assert m.match({"isin": "INE002A01018"})[0] == {"symbol": "RELIANCE", "exchange": "NSE", "name": "Reliance Industries"}
    assert m.match({"symbol": "NSE:RELIANCE"})[0]["symbol"] == "RELIANCE"
    hit, why = m.match({"symbol": "TINYCO"})
    assert hit is None and "offline" in why


def test_symbols_lose_the_exchange_around_them():
    assert [holdings.clean_symbol(s) for s in ("NSE:SBIN", "SBIN-EQ", "sbin.ns", "500325.BO", "M&M", "bad sym!")] == \
           ["SBIN", "SBIN", "SBIN", "500325", "M&M", ""]


def test_merge_adds_quantities_and_weights_the_average():
    got = holdings.merge([{"symbol": "ITC", "exchange": "NSE", "qty": 100, "avg": 410.0},
                          {"symbol": "ITC", "exchange": "NSE", "qty": 20, "avg": 395.0}])
    assert len(got) == 1 and got[0]["qty"] == 120 and round(got[0]["avg"], 2) == 407.5


# ---------- importing through the app ----------
def test_zerodha_console_import_nse_series_and_bse_only(w):
    r = upload(w["client"], "zerodha_console_holdings.xlsx")
    assert r.status_code == 200, r.text
    body, rows = r.json(), held(r)
    assert body["broker"] == "Zerodha Console" and body["imported"] == 6
    assert rows["SLOWCO-BE"]["exchange"] == "NSE"                                         # a restricted NSE series
    assert rows["TINYCO"]["exchange"] == "BSE"                                            # listed only on BSE
    assert rows["RELIANCE"]["exchange"] == "NSE"                                          # on both: the NSE one
    assert body["unmatched"] == []
    # an INF ISIN is a fund: kept as an ETF with its badge, in its own group rather than a sector
    assert (rows["NIFTYBEES"]["kind"], rows["NIFTYBEES"]["kind_label"], rows["NIFTYBEES"]["sector"]) == ("etf", "Equity ETF", "ETFs")
    assert rows["RELIANCE"]["kind"] == "stock" and rows["RELIANCE"]["kind_label"] is None


def test_groww_matches_by_isin_and_by_name(w):
    r = upload(w["client"], "groww_holdings_statement.xlsx", data_url=True)
    rows, body = held(r), r.json()
    assert set(rows) == {"INFY", "ITC", "TATASTEEL", "TINYCO"}                           # Tiny Co by name, on BSE
    assert body["unmatched"][0]["text"].startswith("INE000X01000") and body["unmatched"][0]["line"] == 11


def test_icici_codes_match_through_the_isin(w):
    rows = held(upload(w["client"], "icici_direct_portfolio.csv"))
    assert set(rows) == {"RELIANCE", "INFY", "SBIN", "ICICIBANK"} and rows["SBIN"]["qty"] == 80 and rows["SBIN"]["avg"] == 602.45


def test_each_other_broker(w):
    c = w["client"]
    kite = held(upload(c, "zerodha_kite_holdings.csv"))
    assert set(kite) == {"SBIN", "ICICIBANK", "WIPRO", "GOLDBEES"} and kite["GOLDBEES"]["kind_label"] == "Gold ETF"
    assert set(held(upload(c, "upstox_holdings.csv"))) == {"BHARTIARTL", "LT", "TINYCO"}
    angel = held(upload(c, "angel_one_holding_report.xlsx"))
    assert set(angel) == {"ASIANPAINT", "ITC"} and angel["ITC"]["qty"] == 120          # NSE and BSE lines add up
    hdfc = upload(c, "hdfc_securities_portfolio.xls")
    assert hdfc.json()["broker"] == "HDFC Securities" and set(held(hdfc)) == {"TCS", "HDFCBANK"}
    gen = upload(c, "generic.csv")
    assert set(held(gen)) == {"RELIANCE", "TCS", "TINYCO"}                                # 543210 is Tiny Co's BSE code
    assert gen.json()["unmatched"][0]["text"] == "NOTASTOCK"


def test_add_mode_keeps_what_was_there(w):
    c = w["client"]
    upload(c, "upstox_holdings.csv")
    rows = held(upload(c, "generic.csv", mode="add"))
    assert {"BHARTIARTL", "LT", "RELIANCE"} <= set(rows) and rows["TINYCO"]["qty"] == 140


def test_nothing_matched_leaves_the_saved_holdings_alone(w):
    c = w["client"]
    upload(c, "upstox_holdings.csv")
    r = upload(c, "x.csv", b"Symbol,Qty\nNOPE1,1\nNOPE2,2\n")
    assert r.status_code == 200 and r.json()["saved"] is False and len(r.json()["unmatched"]) == 2
    assert set(held(r)) == {"BHARTIARTL", "LT", "TINYCO"}


def test_the_page_values_positions_and_groups_sectors(w):
    c = w["client"]
    upload(c, "icici_direct_portfolio.csv")
    v = c.get("/holdings", headers=PRO).json()
    q = main.kite.quote(["RELIANCE"])["RELIANCE"]
    rel = next(r for r in v["rows"] if r["symbol"] == "RELIANCE")
    assert rel["value"] == round(20 * q["price"], 2) and rel["invested"] == round(20 * 2388.1, 2)
    assert rel["pnl"] == round(20 * q["price"] - 20 * 2388.1, 2) and rel["day"] == round(20 * q["change"], 2)
    assert v["prices"] is True and v["totals"]["count"] == 4 and v["source"] == "ICICI Direct"
    assert abs(sum(a["pct"] for a in v["allocation"]) - 100) < 0.5
    assert abs(v["totals"]["value"] - sum(r["value"] for r in v["rows"])) < 0.05
    assert all(r["sector"] for r in v["rows"])


def test_without_prices_the_page_still_adds_up(w, monkeypatch):
    c = w["client"]
    upload(c, "upstox_holdings.csv")
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    v = c.get("/holdings", headers=PRO).json()
    assert v["prices"] is False and v["totals"]["pnl"] is None and v["totals"]["value"] == v["totals"]["invested"] > 0


def test_view_math():
    v = holdings.view([{"symbol": "A", "qty": 10, "avg": 100, "sector": "IT"}, {"symbol": "B", "qty": 5, "avg": None, "sector": "Energy"},
                       {"symbol": "C", "qty": 2, "avg": 50, "sector": "IT"}],
                      {"A": {"price": 120, "change": 2, "change_pct": 1.69}, "B": {"price": 40, "change": -1, "change_pct": -2.44}})
    rows = {r["symbol"]: r for r in v["rows"]}
    assert rows["A"]["pnl"] == 200 and rows["A"]["pnl_pct"] == 20 and rows["A"]["day"] == 20
    assert rows["B"]["pnl"] is None and rows["B"]["value"] == 200                         # no average price: no gain or loss
    assert rows["C"]["value"] is None and rows["C"]["invested"] == 100                    # no price: counted at cost
    t = v["totals"]
    # R5O-004: value, cost, gain or loss and the day's change are of the same positions. B has no buy price, so it is
    # named under the totals and not in them (this expected 1,500 and a day of 15 before: value minus cost was 400
    # while the gain or loss said 200, the mismatch the owner saw)
    assert t["value"] == 1300 and t["invested"] == 1100 and t["value"] - t["invested"] == t["pnl"] == 200 and t["pnl_pct"] == 20
    assert t["day"] == 20 and t["day_pct"] == 1.69                                                  # 20 on yesterday's 1,180
    assert t["no_cost"] == {"count": 1, "symbols": ["B"], "value": 200}
    # the sector mix is still a share of everything held
    assert v["allocation"][0] == {"sector": "IT", "value": 1300, "pct": 86.7, "count": 2}


def test_upcoming_results_from_the_board_meeting_intimation():
    items = filings.normalise([
        {"desc": "Board Meeting Intimation", "attchmntText": "ACME has informed the Exchange about Board Meeting to be held on 21-Oct-2026 "
         "to inter-alia consider and approve the Financial Results for the quarter ended September 30, 2026", "sort_date": "2026-10-01 10:00:00", "seq_id": "9"},
        {"desc": "Board Meeting Intimation", "attchmntText": "meeting held on 20-Jul-2026 to consider results", "sort_date": "2026-07-05 10:00:00", "seq_id": "8"}])
    assert filings.upcoming_results(items, date(2026, 10, 3))["date"] == "2026-10-21"
    assert filings.upcoming_results(items, date(2026, 10, 22)) is None


def test_facts_per_stock_and_the_plan_gate_on_filings(w, monkeypatch):
    c = w["client"]
    upload(c, "icici_direct_portfolio.csv")
    f = c.get("/holdings/facts", headers=PRO).json()
    rel = f["rows"]["RELIANCE"]
    assert f["filings"] is True and rel["stage"] in (1, 2, 3, 4) and rel["red"] == 1 and "QIP (fund raise)" in rel["flags"]
    assert rel["recent"][0]["label"] == "QIP (fund raise)"
    # once payments are live, a free account sees the trend but not the filings
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)
    upload(c, "icici_direct_portfolio.csv", headers=FREE)
    f = c.get("/holdings/facts", headers=FREE).json()
    assert f["filings"] is False and f["filings_plan"] == "Basic" and f["rows"]["RELIANCE"]["red"] is None
    assert f["rows"]["RELIANCE"]["stage"] is not None


def test_free_plan_keeps_fewer_holdings_once_payments_are_live(w, monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)
    from app import plans
    monkeypatch.setitem(plans.PLANS["free"], "holdings", 2)
    c = w["client"]
    r = upload(c, "icici_direct_portfolio.csv", headers=FREE).json()
    assert r["imported"] == 2 and len(r["over_limit"]) == 2 and r["limit"] == 2
    items = [{"symbol": s, "qty": 1} for s in ("RELIANCE", "TCS", "INFY")]
    r = c.put("/holdings", headers=FREE, json={"items": items})
    assert r.status_code == 402 and "2 stocks" in r.json()["detail"]["message"]
    assert c.put("/holdings", headers=PRO, json={"items": items}).status_code == 200


def test_manual_add_edit_remove_and_delete(w):
    c = w["client"]
    r = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "reliance", "qty": 5, "avg": 2500}, {"symbol": "543210", "qty": 10},
                                                        {"symbol": "ZZZZ", "qty": 1}]})
    assert r.status_code == 200 and set(held(r)) == {"RELIANCE", "TINYCO"} and r.json()["unmatched"][0]["text"] == "ZZZZ"
    assert r.json()["holdings"]["source"] == "Manual"
    r = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 7, "avg": 2400}]})
    assert held(r)["RELIANCE"]["qty"] == 7 and set(held(r)) == {"RELIANCE"}
    for bad in ({"symbol": "RELIANCE", "qty": 0}, {"symbol": "RELIANCE", "qty": -3}, {"symbol": "RELIANCE", "qty": 1, "avg": -1}, {"symbol": "", "qty": 1}):
        assert c.put("/holdings", headers=PRO, json={"items": [bad]}).status_code == 422
    assert held(c.put("/holdings", headers=PRO, json={"items": []})) == {}                 # every row removed
    assert db.get_setting("holdings:u-pro") is None
    upload(c, "upstox_holdings.csv")
    assert c.delete("/holdings", headers=PRO).json() == {"deleted": True}
    assert c.get("/holdings", headers=PRO).json()["rows"] == [] and db.get_setting("holdings:u-pro") is None


def test_editing_while_market_data_is_offline_keeps_what_was_matched(w, monkeypatch):
    c = w["client"]
    upload(c, "upstox_holdings.csv")                                                      # TINYCO is BSE-only: not on the exchange list
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    r = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "TINYCO", "qty": 99, "avg": 20}, {"symbol": "LT", "qty": 6, "avg": 3120},
                                                        {"symbol": "RELIANCE", "qty": 2}]})
    rows = held(r)
    assert rows["TINYCO"]["qty"] == 99 and rows["TINYCO"]["exchange"] == "BSE" and "RELIANCE" in rows   # RELIANCE from the exchange list
    assert "BHARTIARTL" not in rows


def test_holdings_are_private(w):
    c = w["client"]
    upload(c, "upstox_holdings.csv")
    assert c.get("/holdings", headers=FREE).json()["rows"] == []
    assert c.get("/holdings").status_code == 401
    c.delete("/holdings", headers=FREE)                                                  # someone else deleting theirs
    assert len(c.get("/holdings", headers=PRO).json()["rows"]) == 3


def test_upload_size_limit_and_damaged_uploads(w):
    c = w["client"]
    r = upload(c, "big.csv", b"Symbol,Qty\n" + b"RELIANCE,1\n" * 250_000)
    assert r.status_code == 413 and "larger than 2 MB" in r.json()["detail"]["message"]
    r = c.post("/holdings/import", headers=PRO, json={"filename": "x.csv", "data": "not base64!!"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_upload"
    r = c.post("/holdings/import", headers={**PRO, "content-type": "application/json"}, content=b"{" + b" " * (9 * 1024 * 1024) + b"}")
    assert r.status_code == 413                                                           # the request guard's cap


def test_malformed_files_never_crash_the_route(w):
    """Every sample file, cut short, with bytes flipped or padded with junk: always a clear 200 or 4xx, never a 500."""
    import random
    rng, c = random.Random(11), w["client"]
    samples = [p.read_bytes() for p in sorted(FIX.iterdir())]
    samples += [xlsxmaker.make_xlsx([["Symbol", "Qty"], ["RELIANCE", 1]]), b"<html><table><tr><td>Symbol<td>Qty<tr><td>TCS<td>2",
                b'"Symbol","Qty"\n"RELIANCE,1\n', b"Symbol,Qty\n" + b"A" * 200_000 + b",1\n", b"\xef\xbb\xbfSymbol,Qty\nRELIANCE,1e400\n"]
    cases = 0
    for data in samples:
        for _ in range(30):
            d = bytearray(data)
            op = rng.choice(("cut", "flip", "junk", "dup"))
            if op == "cut":
                d = d[:rng.randrange(1, len(d) + 1)]
            elif op == "flip":
                for _ in range(rng.randrange(1, 20)):
                    d[rng.randrange(len(d))] = rng.randrange(256)
            elif op == "junk":
                d[rng.randrange(len(d)):rng.randrange(len(d))] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 300)))
            else:
                d = d + d
            main._recent.clear()
            r = upload(c, rng.choice(("h.csv", "h.xlsx", "h.xls", "")), bytes(d))
            cases += 1
            assert r.status_code in (200, 400, 413), (op, r.status_code, r.text[:300])
            assert r.json()
    assert cases == len(samples) * 30


def test_imports_are_throttled(w):
    c = w["client"]
    for _ in range(30):
        upload(c, "generic.csv")
    assert upload(c, "generic.csv").status_code == 429


def test_holdings_count_in_the_my_stocks_newsletter(w):
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"region": "IN", "symbol": "RELIANCE"}]}))
    upload(w["client"], "upstox_holdings.csv")
    got = content.my_stocks("u-pro")
    assert got[0] == ("IN", "RELIANCE") and {("IN", "BHARTIARTL"), ("IN", "LT"), ("IN", "TINYCO")} <= set(got)
    db.set_setting("holdings:u-pro", "{broken")                                          # a damaged row costs nothing
    assert content.my_stocks("u-pro") == [("IN", "RELIANCE")]


# ---------- hostile files ----------
def _zipped(sheet: bytes, extra: dict | None = None) -> bytes:
    import io
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return out.getvalue()


def test_millions_of_tiny_elements_dont_eat_the_memory():
    """A few kilobytes zipped can unpack to millions of empty rows or strings: read as a stream, never as a tree."""
    import tracemalloc
    rows = b"<worksheet><sheetData>" + b"<row/>" * 3_000_000 + b"</sheetData></worksheet>"
    strings = b"<sst>" + b"<si/>" * 3_000_000 + b"</sst>"
    for data in (_zipped(rows), _zipped(b"<worksheet><sheetData/></worksheet>", {"xl/sharedStrings.xml": strings})):
        assert len(data) < 100_000
        tracemalloc.start()
        try:
            with pytest.raises(hf.FileError):
                hf.parse(data)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert peak < 40 * 1024 * 1024, peak


def test_entity_tricks_in_a_spreadsheet_are_refused():
    """No document type declarations at all: no entity expansion (billion laughs) and nothing read from outside (XXE)."""
    head = (b'<row><c t="inlineStr"><is><t>Symbol</t></is></c><c t="inlineStr"><is><t>Qty</t></is></c></row>')
    laughs = (b'<?xml version="1.0"?><!DOCTYPE worksheet [<!ENTITY a "aaaaaaaaaa">'
              + b"".join(b'<!ENTITY %c "%s">' % (98 + i, (b"&%c;" % (97 + i)) * 10) for i in range(8))
              + b"]><worksheet><sheetData>" + head + b'<row><c t="inlineStr"><is><t>&i;</t></is></c><c><v>1</v></c></row></sheetData></worksheet>')
    xxe = (b'<?xml version="1.0"?><!DOCTYPE worksheet [<!ENTITY x SYSTEM "file:///etc/passwd">]><worksheet><sheetData>' + head
           + b'<row><c t="inlineStr"><is><t>&x;</t></is></c><c><v>1</v></c></row></sheetData></worksheet>')
    plain = (b'<?xml version="1.0"?><!DOCTYPE worksheet><worksheet><sheetData>' + head
             + b'<row><c t="inlineStr"><is><t>TCS</t></is></c><c><v>1</v></c></row></sheetData></worksheet>')
    for sheet in (laughs, xxe, plain):
        with pytest.raises(hf.FileError):
            hf.parse(_zipped(sheet))
    with pytest.raises(hf.FileError):                                                     # the strings file too
        hf.parse(_zipped(b"<worksheet/>", {"xl/sharedStrings.xml": laughs.replace(b"worksheet", b"sst")}))


def test_a_real_workbook_still_reads_as_a_stream():
    rows = hf.parse(xlsxmaker.make_xlsx([["Symbol", "Qty", "Avg price"], ["RELIANCE", 3, 2500], ["TCS", "4", "3,100.50"]]))["rows"]
    assert [(r["symbol"], r["qty"], r["avg"]) for r in rows] == [("RELIANCE", 3, 2500), ("TCS", 4, 3100.5)]


def test_a_file_of_lines_that_match_nothing_is_still_quick():
    """Each unmatched line used to walk the whole instrument list (F&O included) several times, so a small file of
    made-up lines took minutes of the server's time. Lookups go through an index now."""
    import time
    from datetime import date as day
    from tests import fake_kite
    k = fake_kite.online()
    k.kite.rows["NFO"] += [{"instrument_token": 900_000 + i, "tradingsymbol": f"OPT{i}CE", "name": f"OPT{i % 500}",
                            "segment": "NFO-OPT", "instrument_type": "CE", "lot_size": 50, "expiry": day(2030, 1, 1),
                            "strike": 100} for i in range(60_000)]
    m = holdings.Matcher(k.equity, k.equity_by_name, lambda c: None, {}, True)
    junk = [{"line": i, "symbol": f"ZZ{i}", "name": f"No Such Company {i}", "isin": "", "qty": 1} for i in range(1500)]
    real = [{"line": 0, "symbol": "RELIANCE", "qty": 1}, {"line": 0, "name": "Tiny Co Ltd", "qty": 1},
            {"line": 0, "symbol": "543210", "qty": 1}, {"line": 0, "symbol": "SLOWCO", "qty": 1}]
    k.equity("RELIANCE")                                   # the day's instrument list loads outside the timing
    t = time.time()
    found, missed = holdings.match_all(junk + real, m)
    assert time.time() - t < 3
    assert len(missed) == 1500
    assert {(f["symbol"], f["exchange"]) for f in found} == {("RELIANCE", "NSE"), ("TINYCO", "BSE"), ("SLOWCO-BE", "NSE")}


def test_manual_edits_are_throttled_too(w):
    c = w["client"]
    for _ in range(120):
        assert c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 1}]}).status_code == 200
    assert c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 1}]}).status_code == 429
