"""The ZIP a broker gives for its tax P&L: the equity files read and checked against the summary sheet, F&O,
commodity and currency streamed into per-year totals and checked against the workbook's sheets for them, the other
segments left out by name and unread, each tax P&L line kept with its own buy, the bigger upload limits, and hostile
ZIPs (bombs, ZIPs inside ZIPs, paths that climb out, too many files, password-protected, damaged)."""
import base64
import io
import random
import zipfile
from pathlib import Path

import pytest

from app import guard, holdings_file as hf, tax_lots as T
from tests import tradebook_maker as M, world

ZIP = Path(__file__).parent / "fixtures" / "taxpnl" / "zerodha_taxpnl_2024_2025.zip"
PRO = world.headers("pro-token")
TODAY = "2026-10-04"
EXITS = "Tradewise Exits from 2024-04-01 to 2025-03-31-"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def make_zip(files: list[tuple[str, bytes]], method=zipfile.ZIP_DEFLATED, flags: int = 0) -> bytes:
    """A ZIP of these files; `flags` set in every header afterwards (the writer won't set the encrypted bit)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", method) as z:
        for name, data in files:
            z.writestr(zipfile.ZipInfo(name, (2025, 6, 23, 9, 46, 0)), data, method)
    data = bytearray(out.getvalue())
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        i = data.find(sig)
        while flags and i >= 0:
            data[i + off] |= flags
            i = data.find(sig, i + 4)
    return bytes(data)


def short_csv(rows: int = 1) -> bytes:
    line = ["TCS", "INE467B01029", "2024-06-03", "2025-01-15", 1, 3800, 4100, 300, 226, 0, 300, 0, 0, 0.1, 0, 0, 0, 0, 0.02, 0, 4.1]
    return M._csv([M.PNL_HEAD] + [line] * rows).encode()


def send(c, data: bytes, name: str = "taxpnl.zip", mode: str = "add", headers=PRO):
    """The page's way: the file itself as the body, its name and the mode in the query."""
    return c.post(f"/tax/import?filename={name}&mode={mode}", headers={**headers, "Content-Type": "application/octet-stream"}, content=data)


# ---------- reading the ZIP ----------
def test_the_zip_is_read_and_checked_against_the_summary():
    got = hf.parse_trades(ZIP.read_bytes(), ZIP.name)
    assert (got["broker"], got["kind"], len(got["trades"]), got["problems"]) == ("Zerodha", "pnl", 16, [])
    assert [(f["section"], f["lines"]) for f in got["files"]] == [("Commodity", 2), ("Equity short term", 3), ("Equity long term", 2),
                                                                  ("Equity intraday", 3), ("F&O", 4), ("Currency", 1)]
    assert got["check"][:3] == [{"section": "Equity short term", "file": 4300.0, "summary": 4300, "ok": True},
                                {"section": "Equity long term", "file": 13000.0, "summary": 13000, "ok": True},
                                {"section": "Equity intraday", "file": 80.0, "summary": 80, "ok": True}]
    assert [(c["section"], c["file"], c["ok"]) for c in got["check"][3:]] == [
        ("F&O", -1212.5, True), ("F&O turnover", 3787.5, True), ("Commodity", 1500.0, True), ("Commodity turnover", 2500.0, True),
        ("Currency", 100.0, True), ("Currency turnover", 100.0, True)]
    skipped = {s["name"].rsplit("-", 1)[-1]: s["reason"] for s in got["skipped"]}
    assert set(skipped) == {"Non Equity.csv"}                                                    # no __MACOSX junk listed
    assert "other rules" in skipped["Non Equity.csv"]
    assert not any(t["symbol"] in ("NIFTY24SEP25000CE", "GOLDBEES", "CRUDEOIL24AUGFUT") for t in got["trades"])
    wipro = next(t for t in got["trades"] if t["symbol"] == "WIPRO" and t["side"] == "B")
    assert wipro["fmv"] == 310 and wipro["d"] == "2017-06-12"                                   # 15,500 for 50 shares


def test_the_sample_zip_is_what_the_maker_writes():
    assert hf.parse_trades(M.zerodha_tax_zip(), "z.zip") == hf.parse_trades(ZIP.read_bytes(), "z.zip")


def test_fno_is_streamed_and_other_segments_never_unpacked(monkeypatch):
    opened = []
    real = hf._unpack
    monkeypatch.setattr(hf, "_unpack", lambda zf, info, budget, cap=None: opened.append(info.filename) or real(zf, info, budget, cap))
    hf.parse_trades(ZIP.read_bytes())
    # the three equity files and the workbook are unpacked; F&O, commodity and currency stream; the rest stay shut
    assert len(opened) == 4 and not any(k in n for n in opened for k in ("F&O", "Commodity", "Currency", "Non Equity", "__MACOSX"))


# ---------- F&O, commodity and currency ----------
def test_fno_totals_per_segment_and_year():
    biz = {b["seg"]: b for b in hf.parse_trades(ZIP.read_bytes())["business"]}
    f = biz["fno"]
    assert (f["fy"], f["trades"], f["pnl"], f["turnover"], f["turnover_contract"]) == (2024, 4, -1212.5, 4587.5, 3787.5)
    assert f["charges"] == pytest.approx(220) and f["stt"] == pytest.approx(22.5)
    assert f["options"] == {"pnl": 1287.5, "turnover": 2087.5, "trades": 3} and f["futures"] == {"pnl": -2500, "turnover": 2500, "trades": 1}
    assert [b["u"] for b in f["by"]] == ["BANKNIFTY", "NIFTY", "RELIANCE"]
    assert (biz["commodity"]["pnl"], biz["commodity"]["charges"]) == (1500, pytest.approx(71.2))
    assert biz["currency"]["pnl"] == 100
    assert (f["first"], f["last"]) == ("2024-09-12", "2024-11-06")


def test_fno_alone_and_other_brokers_shapes():
    alone = hf.parse_trades(M._csv(M.TAX_FNO).encode(), EXITS + "F&O.csv")
    assert (alone["broker"], alone["kind"], alone["trades"]) == ("Zerodha", "business", [])
    assert alone["business"][0]["pnl"] == -1212.5
    # another broker's F&O P&L of the obvious shape, named or not: contract, exit date, buy and sell values
    other = M._csv([["Contract", "Buy Date", "Sell Date", "Qty", "Buy Amount", "Sell Amount", "Total Charges"],
                    ["NIFTY24DEC24000PE", "02/12/2024", "05/12/2024", 75, "7,500", "9,000", 45],
                    ["USDINR24DECFUT", "02/12/2024", "05/12/2024", 1000, 85000, 84900, 12]]).encode()
    for name in ("fno_pnl.csv", "pnl.csv"):
        got = hf.parse_trades(other, name)
        segs = {b["seg"]: b for b in got["business"]}
        if name == "pnl.csv":                                          # told apart by the contract
            assert got["kind"] == "business" and segs["fno"]["pnl"] == 1500 and segs["fno"]["charges"] == 45
            assert segs["currency"]["pnl"] == -100
        else:                                                          # the file's name says F&O: all of it
            assert list(segs) == ["fno"] and segs["fno"]["pnl"] == 1400
    # an F&O tradebook (each buy and sale) isn't a P&L: said plainly
    tradebook = M._csv([["trade_date", "tradingsymbol", "trade_type", "quantity", "price"], ["2024-12-02", "NIFTY24DEC24000PE", "buy", 75, 100]]).encode()
    with pytest.raises(hf.FileError, match="only from Zerodha's tax P&L for now"):
        hf.parse_trades(tradebook, "fno_tradebook.csv")
    with pytest.raises(hf.FileError, match="Futures, options and other non-equity trades are left out"):
        hf.parse_trades(tradebook, "tradebook.csv")                  # not named: its contracts aren't taken for shares
    # an equity tax P&L (it has ISINs) is still read as equity
    assert hf.parse_trades(M._csv(M.TAX_SHORT).encode(), "pnl.csv")["kind"] == "pnl"


def test_fno_lines_that_cant_be_read_are_listed():
    rows = M.TAX_FNO + [["NIFTY24SEP25000PE", "2024-09-10", "someday", 1, 1, 1, 5, 5] + [0] * 9,
                        ["NIFTY24SEP25000PE", "2024-09-10", "2024-09-11", 1, 1, 1, "", ""] + [0] * 9,
                        ["Total", "", "", "", "", "", -1212.5]]
    got = hf.parse_trades(M._csv(rows).encode(), EXITS + "F&O.csv")
    assert got["business"][0]["trades"] == 4 and [p["reason"] for p in got["problems"]] == [
        "The exit date couldn't be read.", "No profit or loss on this line."]


def test_a_big_fno_file_streams_within_its_own_cap():
    line = ["NIFTY24SEP25000CE", "2024-09-10T10:00:00", "2024-09-12T14:00:00", 25, 3012.5, 4100, 1087.5, 1087.5] + [1] * 9
    n = 70000                                                        # more lines than a tradebook may have, ~7 MB
    data = M._csv([M.DERIV_HEAD] + [line] * n).encode()
    got = hf.parse_trades(make_zip([(EXITS + "F&O.csv", data)]))
    assert got["business"][0]["trades"] == n and got["business"][0]["pnl"] == pytest.approx(1087.5 * n)
    # over its 20 MB: left out with the reason, the rest of the ZIP still read
    huge = b"x" * (hf.FNO_MAX_BYTES + 10)
    got = hf.parse_trades(make_zip([(EXITS + "F&O.csv", huge), (EXITS + "Equity - Short Term.csv", short_csv())]))
    assert "larger than 20 MB unpacked" in got["skipped"][0]["reason"] and got["trades"]
    with pytest.raises(hf.FileError, match="larger than 20 MB"):
        hf.parse_trades(huge, EXITS + "F&O.csv")


def test_fno_summary_that_differs_or_a_missing_file_is_flagged():
    sheets = [("Equity and Non Equity", M.TAX_SUMMARY), ("F&O", M.deriv_summary("F&O", (1287.5, 1287.5), (-2400, 2400)))]
    got = hf.parse_trades(make_zip([(EXITS + "F&O.csv", M._csv(M.TAX_FNO).encode()), ("taxpnl.xlsx", M.make_workbook(sheets))]))
    fno = {c["section"]: c for c in got["check"]}
    assert fno["F&O"]["ok"] is False and fno["F&O"]["summary"] == -1112.5 and fno["F&O turnover"]["ok"] is False
    no_file = hf.parse_trades(make_zip([(EXITS + "Equity - Short Term.csv", short_csv()), ("taxpnl.xlsx", M.make_workbook(sheets))]))
    assert {"section": "F&O", "file": None, "summary": -1112.5, "ok": False, "what": "pnl"} in no_file["check"]


def test_a_summary_that_differs_is_flagged():
    rows = [r if r[1:2] != ["Short Term profit"] else [None, "Short Term profit", 4999] for r in M.TAX_SUMMARY]
    check = hf.parse_trades(M.zerodha_tax_zip(rows))["check"]
    assert check[0] == {"section": "Equity short term", "file": 4300.0, "summary": 4999, "ok": False}
    # long-term sales in the summary but no long-term file in the ZIP: said, not hidden
    no_long = make_zip([(EXITS + "Equity - Short Term.csv", M._csv(M.TAX_SHORT).encode()),
                        ("taxpnl.xlsx", M.make_xlsx(M.TAX_SUMMARY, "Equity and Non Equity"))])
    check = hf.parse_trades(no_long)["check"]
    assert {"section": "Equity long term", "file": None, "summary": 13000, "ok": False} in check


def test_the_summary_or_another_segment_alone_gets_a_plain_answer():
    with pytest.raises(hf.FileError, match="summary page of a tax P&L"):
        hf.parse_trades(M.make_xlsx(M.TAX_SUMMARY), "taxpnl-2024_2025-Q1-Q4.xlsx")
    with pytest.raises(hf.FileError, match="Non-equity file of a tax P&L"):
        hf.parse_trades(M._csv(M.TAX_NON_EQUITY).encode(), EXITS + "Non Equity.csv")
    with pytest.raises(hf.FileError, match="No equity, F&O, commodity or currency trades were found in that ZIP.*Non Equity"):
        hf.parse_trades(make_zip([(EXITS + "Non Equity.csv", M._csv(M.TAX_NON_EQUITY).encode()), ("notes.pdf", b"%PDF-1.4")]))
    # a ZIP of F&O only is fine: business income, no trades
    only = hf.parse_trades(make_zip([(EXITS + "F&O.csv", M._csv(M.TAX_FNO).encode())]))
    assert only["kind"] == "business" and only["trades"] == [] and only["business"][0]["pnl"] == -1212.5


def test_a_big_tax_pnl_file_is_read_whole():
    # more lines than a holdings file may have: every one counts (a busy year runs to thousands)
    got = hf.parse_trades(make_zip([(EXITS + "Equity - Short Term.csv", short_csv(6000))]))
    assert len(got["trades"]) == 12000 and got["check"] == []
    assert len(hf.parse_trades(short_csv(6000), "short.csv")["trades"]) == 12000


# ---------- each line keeps its own buy ----------
def test_a_tax_pnl_line_keeps_its_buy_and_isnt_taken_for_intraday():
    trades = hf.parse_trades(ZIP.read_bytes())["trades"]
    c = T.compute(trades, today=TODAY)
    y = T.year(2024, c["realised"], c["intraday"])
    sym = {k: v["symbol"] for k, v in c["names"].items()}
    rel = sorted((r["bought"], r["sold"], r["qty"], r["term"]) for r in c["realised"] if sym[r["key"]] == "RELIANCE")
    assert rel == [("2024-05-10", "2024-09-16", 10, "ST"), ("2024-09-16", "2024-12-02", 5, "ST")]
    assert {sym[i["key"]] for i in c["intraday"]} == {"INFY", "SBIN"} and y["intraday"]["count"] == 2   # one line a company a day
    charges = sum(t["charges"] for t in trades if t["side"] == "S" and t["src"] == "pnl")
    gross = 4300 + 13000 + 80
    lt_relief = 2000                                                     # WIPRO grandfathered at its 31 Jan 2018 value
    total = y["stcg"]["net"] + y["ltcg"]["net"] + y["intraday"]["pnl"]
    assert total == pytest.approx(gross - lt_relief - charges, abs=0.05)
    assert c["unmatched"] == [] and c["open"] == []


def test_half_a_line_falls_back_to_first_in_first_out():
    buy = {"d": "2024-01-02", "side": "B", "qty": 5, "price": 100, "sym": "A", "src": "pnl", "tid": "pnl:x:b"}
    sale = {"d": "2024-03-01", "side": "S", "qty": 5, "price": 120, "sym": "A", "src": "pnl", "tid": "pnl:y:s"}
    r = T.compute([buy, sale], today=TODAY)["realised"]
    assert len(r) == 1 and r[0]["gain"] == 100


# ---------- hostile ZIPs ----------
def test_zip_bomb_stops_at_the_caps(monkeypatch):
    zeros = b"0" * (hf.TAX_MAX_BYTES + 1)                  # ~10 KB packed, more than 10 MB unpacked
    bomb = make_zip([(EXITS + "Equity - Short Term.csv", zeros)])
    assert len(bomb) < 100_000
    with pytest.raises(hf.FileError, match="larger than 10 MB unpacked"):
        hf.parse_trades(bomb)
    # many files each under the cap, together over the total
    monkeypatch.setattr(hf, "ZIP_MAX_UNPACKED", 3 * 1024 * 1024)
    many = make_zip([(f"{EXITS}Equity - Short Term {i}.csv", b"0" * (1024 * 1024 + 1)) for i in range(4)])
    with pytest.raises(hf.FileError, match="unpacks to more than 3 MB"):
        hf.parse_trades(many)


def test_a_header_that_lies_about_the_size_changes_nothing():
    data = bytearray(make_zip([(EXITS + "Equity - Short Term.csv", b"0" * (hf.TAX_MAX_BYTES + 5000))]))
    for sig, off in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):         # claim 100 bytes unpacked, in both headers
        i = data.find(sig)
        data[i + off:i + off + 4] = (100).to_bytes(4, "little")
    with pytest.raises(hf.FileError):
        hf.parse_trades(bytes(data))


def test_zips_inside_zips_are_refused():
    inner = make_zip([(EXITS + "Equity - Short Term.csv", short_csv())])
    for files in ([("inner.zip", inner)], [("a/b/inner.ZIP", inner)], [(EXITS + "Equity - Short Term.csv", inner)]):
        with pytest.raises(hf.FileError, match="another ZIP inside it"):
            hf.parse_trades(make_zip(files))
    # an Excel workbook is a ZIP too, and is fine
    assert hf.parse_trades(make_zip([("tradewise.xlsx", M.make_xlsx(M.ZERODHA_PNL))]))["trades"]


@pytest.mark.parametrize("name", ["../" + EXITS + "Equity - Short Term.csv", "/etc/Equity - Short Term.csv",
                                  "C:/Equity - Short Term.csv", "a/../../Equity - Short Term.csv", "a\\..\\..\\x.csv", "x\x01.csv"])
def test_paths_that_climb_out_are_refused(name):
    with pytest.raises(hf.FileError, match="file paths we don't accept"):
        hf.parse_trades(make_zip([(EXITS + "Equity - Intraday.csv", short_csv()), (name, short_csv())]))


def test_too_many_files_password_and_damage():
    with pytest.raises(hf.FileError, match="more than 200 files"):
        hf.parse_trades(make_zip([(f"f{i}.txt", b"x") for i in range(hf.ZIP_MAX_ENTRIES + 1)]))
    with pytest.raises(hf.FileError, match="password-protected"):
        hf.parse_trades(make_zip([(EXITS + "Equity - Short Term.csv", short_csv())], flags=0x1))
    whole = make_zip([(EXITS + "Equity - Short Term.csv", short_csv(50))])
    with pytest.raises(hf.FileError):
        hf.parse_trades(whole[:len(whole) // 2])
    junk_only = make_zip([("__MACOSX/._x.csv", b"\x00\x05"), (".DS_Store", b"\x00"), ("folder/", b"")])
    with pytest.raises(hf.FileError, match="No equity, F&O"):
        hf.parse_trades(junk_only)


def test_random_damage_never_crashes_the_reader():
    rng = random.Random(11)
    good = ZIP.read_bytes()
    for i in range(300):
        data = bytearray(good)
        for _ in range(rng.randint(1, 30)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        if i % 5 == 0:
            data = data[:rng.randrange(len(data))]
        try:
            got = hf.parse_trades(bytes(data))
        except hf.FileError:
            continue
        for t in got["trades"]:
            assert t["side"] in ("B", "S") and t["qty"] > 0 and len(t["d"]) == 10
        T.compute(got["trades"], today=TODAY)


# ---------- through the app ----------
def test_upload_the_zip_as_the_body(w):
    c = w["client"]
    r = send(c, ZIP.read_bytes())
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["broker"], j["kind"], j["added"]) == ("Zerodha", "pnl", 16)
    assert all(x["ok"] for x in j["check"]) and len(j["skipped"]) == 1 and len(j["files"]) == 6
    assert j["business"] == {"lines": 7, "added": 3, "replaced": 0, "same": 0, "years": [2024]}
    y = next(y for y in j["report"]["years"] if y["fy"] == 2024)
    assert y["intraday"]["count"] == 2 and y["stcg"]["net"] < 4300 and y["ltcg"]["net"] < 13000      # less charges and grandfathering
    assert [s["seg"] for s in y["business"]["segments"]] == ["fno", "commodity", "currency"]
    assert y["business"]["net"] == pytest.approx(-1212.5 - 220 + 1500 - 71.2 + 100 - 47.61)
    again = send(c, ZIP.read_bytes()).json()                                                          # the same ZIP again
    assert again["added"] == 0 and again["business"]["same"] == 3 and again["business"]["added"] == 0
    assert again["report"]["business_lines"] == 7
    # the older way, base64 in JSON, still works and gives the same
    old = c.post("/tax/import", headers=PRO, json={"filename": "z.zip", "data": base64.b64encode(ZIP.read_bytes()).decode(), "mode": "replace"})
    assert old.status_code == 200 and old.json()["added"] == 16


def test_damaged_zips_through_the_app_never_crash(w):
    c = w["client"]
    rng = random.Random(5)
    good = ZIP.read_bytes()
    for i in range(40):
        data = bytearray(good)
        for _ in range(rng.randint(1, 20)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        body = bytes(data[:rng.randrange(len(data))] if i % 4 == 0 else data)
        r = send(c, body, rng.choice(["t.zip", "", "../x.zip", "F&O.csv", "a" * 300]))
        assert r.status_code in (200, 400, 413, 422), (i, r.status_code, r.text[:200])
        assert r.json()


def test_upload_limits(w):
    c = w["client"]
    big = send(c, b"PK\x03\x04" + b"0" * hf.TAX_MAX_BYTES)
    assert big.status_code == 413 and "10 MB" in big.json()["detail"]["message"]
    raw = base64.b64encode(b"x" * (hf.TAX_MAX_BYTES + 10)).decode()
    assert c.post("/tax/import", headers=PRO, json={"filename": "x.csv", "data": raw}).status_code == 413
    # a file between the holdings cap (2 MB) and the tax cap (10 MB) is read
    mid = short_csv(1) + b"\n" * (3 * 1024 * 1024)
    assert send(c, mid, "short.csv").status_code == 200
    assert send(c, b"", "x.csv").status_code == 400
    assert c.post("/tax/import", headers=PRO, json={"filename": "x.csv"}).status_code == 422
    assert c.post("/tax/import", headers={**PRO, "Content-Type": "application/json"}, content=b"{nope").status_code == 422
    assert c.post("/tax/import?mode=sideways", headers=PRO, content=b"x").status_code == 422
    assert send(c, ZIP.read_bytes(), headers={}).status_code == 401
    # the holdings import keeps its 2 MB
    h = c.post("/holdings/import", headers=PRO, json={"filename": "h.csv", "data": base64.b64encode(b"x" * (hf.MAX_BYTES + 10)).decode()})
    assert h.status_code == 413


def test_the_guard_allows_a_bigger_body_only_for_the_tax_import():
    assert guard.max_body({"method": "POST", "path": "/tax/import"}) == hf.TAX_MAX_REQUEST == 25 * 1024 * 1024
    assert guard.max_body({"method": "POST", "path": "/holdings/import"}) == guard.MAX_BODY
    assert guard.max_body({"method": "GET", "path": "/tax/import"}) == guard.MAX_BODY
    # base64 of a full 10 MB file fits inside it
    assert hf.TAX_MAX_BYTES * 4 // 3 + 100 < hf.TAX_MAX_REQUEST


def test_the_guard_turns_away_a_body_over_25_mb(w):
    c = w["client"]
    r = send(c, b"0" * (hf.TAX_MAX_REQUEST + 1))
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large" and "25 MB" in r.json()["detail"]["message"]
    other = c.post("/holdings/import", headers=PRO, content=b"0" * (guard.MAX_BODY + 1))
    assert other.status_code == 413 and "8 MB" in other.json()["detail"]["message"]
