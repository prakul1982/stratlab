"""Tax report: reading each broker's tradebook and tax P&L, FIFO matching, every tax rule (12-month boundary, the
23 July 2024 rate change, financial-year edges, the exemption, set-off and carry forward, grandfathering, the old
section 10(38) exemption, intraday, bonuses and splits, charges), combining files without duplicates, the page and
its downloads, privacy and deletion, and odd or hostile files."""
import base64
import random
from pathlib import Path

import pytest

from app import db, holdings_file as hf, main, tax_export, tax_lots as T
from app.engine.costs import IN_LTCG, IN_LTCG_EXEMPT, IN_STCG
from tests import tradebook_maker, world

FIX = Path(__file__).parent / "fixtures" / "tradebooks"
PRO, FREE = world.headers("pro-token"), world.headers("free-token")
TODAY = "2026-10-04"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def upload(c, name: str, data: bytes | None = None, headers=PRO, mode="add"):
    raw = data if data is not None else (FIX / name).read_bytes()
    return c.post("/tax/import", headers=headers, json={"filename": name, "data": base64.b64encode(raw).decode(), "mode": mode})


def b(d, qty, price, key="A", **kw):
    return {"d": d, "side": "B", "qty": qty, "price": price, "sym": key, **kw}


def s(d, qty, price, key="A", **kw):
    return {"d": d, "side": "S", "qty": qty, "price": price, "sym": key, **kw}


def realised(trades, **kw):
    return T.compute(trades, today=TODAY, **kw)["realised"]


def fy(trades, year, **kw):
    c = T.compute(trades, today=TODAY, **kw)
    return T.year(year, c["realised"], c["intraday"])


# ---------- the rules ----------
def test_rates_come_from_the_shared_costs_module():
    assert (IN_STCG, IN_LTCG, IN_LTCG_EXEMPT) == (0.20, 0.125, 125000)
    assert T.rates("2024-07-22") == (0.15, 0.10) and T.rates("2024-07-23") == (IN_STCG, IN_LTCG)
    assert T.rates("2018-03-31") == (0.15, 0.0) and T.rates("2018-04-01") == (0.15, 0.10)


def test_financial_year_edges():
    assert T.fy_of("2025-03-31") == 2024 and T.fy_of("2025-04-01") == 2025 and T.fy_of("2024-01-01") == 2023
    assert T.fy_label(2024) == "FY 2024-25" and T.fy_label(1999) == "FY 1999-00"
    assert T.exemption(2024) == 125000 and T.exemption(2023) == 100000 and T.exemption(2018) == 100000 and T.exemption(2017) == 0


def test_twelve_months_is_short_term_a_day_more_is_long_term():
    r = realised([b("2023-07-22", 2, 100), s("2024-07-22", 1, 150), s("2024-07-23", 1, 150)])
    assert [x["term"] for x in r] == ["ST", "LT"]
    assert T.long_from("2023-07-22") == "2024-07-23"


def test_a_leap_day_buy():
    assert not T.long_term("2024-02-29", "2025-02-28") and T.long_term("2024-02-29", "2025-03-01")
    assert T.long_from("2024-02-29") == "2025-03-01"


def test_the_23_july_2024_switch_short_term():
    y = fy([b("2024-05-01", 2, 100), s("2024-07-22", 1, 200), s("2024-07-23", 1, 200)], 2024)
    got = {x["key"]: x for x in y["buckets"]}
    assert got["st_old"]["taxable"] == 100 and got["st_old"]["tax"] == 15.0          # 15% before
    assert got["st_new"]["taxable"] == 100 and got["st_new"]["tax"] == 20.0          # 20% from the 23rd
    assert y["tax"] == 35.0 and y["tax_with_cess"] == 36.4


def test_the_23_july_2024_switch_long_term_and_the_new_exemption():
    trades = [b("2020-01-01", 2, 100), s("2024-07-22", 1, 200_100), s("2024-07-23", 1, 100_100)]
    y = fy(trades, 2024)
    got = {x["key"]: x for x in y["buckets"]}
    # 2,00,000 at 10% and 1,00,000 at 12.5%; the ₹1.25 lakh goes against the 12.5% gains first, then 25,000 of the 10%
    assert got["lt_new"]["exempt"] == 100_000 and got["lt_new"]["tax"] == 0
    assert got["lt_old"]["exempt"] == 25_000 and got["lt_old"]["taxable"] == 175_000 and got["lt_old"]["tax"] == 17_500
    assert y["exemption"] == {"limit": 125000.0, "used": 125000.0, "left": 0.0}


def test_the_old_exemption_of_one_lakh():
    y = fy([b("2020-01-01", 1, 100), s("2023-06-01", 1, 150_100)], 2023)
    assert y["exemption"]["limit"] == 100000 and y["buckets"][0]["taxable"] == 50_000 and y["tax"] == 5000


def test_fiscal_year_boundary_splits_the_exemption():
    trades = [b("2020-01-01", 2, 100), s("2025-03-31", 1, 125_100), s("2025-04-01", 1, 125_100)]
    a, b_ = fy(trades, 2024), fy(trades, 2025)
    assert a["ltcg"]["gains"] == b_["ltcg"]["gains"] == 125_000 and a["tax"] == b_["tax"] == 0   # one exemption each year


def test_long_term_gains_before_april_2018_were_exempt():
    y = fy([b("2015-01-01", 1, 100), s("2018-03-15", 1, 500)], 2017)
    assert y["exempt_old"] == 400 and y["tax"] == 0 and y["buckets"] == []


def test_short_term_losses_against_long_term_gains_but_not_the_reverse():
    # ST loss of 50,000 wipes ST gains of 20,000 and then 30,000 of LT gains
    y = fy([b("2024-05-01", 1, 70_000, "X"), s("2024-09-01", 1, 20_000, "X"), b("2024-05-01", 1, 0, "Y"), s("2024-09-01", 1, 20_000, "Y"),
            b("2020-01-01", 1, 0, "Z"), s("2024-09-01", 1, 200_000, "Z")], 2024)
    lt = next(x for x in y["buckets"] if x["key"] == "lt_new")
    assert lt["after_setoff"] == 170_000 and lt["exempt"] == 125_000 and lt["tax"] == 45_000 * IN_LTCG
    assert y["carry_forward"] == {"st": 0, "lt": 0}
    # an LT loss doesn't touch ST gains: it is carried forward instead
    y = fy([b("2020-01-01", 1, 50_000, "X"), s("2024-09-01", 1, 10_000, "X"), b("2024-05-01", 1, 0, "Y"), s("2024-09-01", 1, 30_000, "Y")], 2024)
    assert y["tax"] == 30_000 * IN_STCG and y["carry_forward"] == {"st": 0, "lt": 40_000}
    assert any("carry forward" in st for st in y["steps"])


def test_losses_go_against_the_highest_rate_first():
    y = fy([b("2024-04-02", 1, 0, "X"), s("2024-06-01", 1, 10_000, "X"), b("2024-04-02", 1, 0, "Y"), s("2024-09-01", 1, 10_000, "Y"),
            b("2024-04-02", 1, 5000, "Z"), s("2024-10-01", 1, 0.01, "Z")], 2024)
    got = {x["key"]: x for x in y["buckets"]}
    assert got["st_new"]["after_setoff"] < 5001 and got["st_old"]["after_setoff"] == 10_000


def test_fifo_across_lots_and_charges():
    r = realised([b("2023-01-02", 10, 100, charges=20), b("2024-01-02", 10, 110, charges=10), s("2024-06-01", 15, 120, charges=30)])
    assert [(x["qty"], x["term"]) for x in r] == [(10, "LT"), (5, "ST")]
    assert r[0]["cost"] == 1020 and r[0]["sale"] == 1200 - 20 and r[0]["gain"] == 160    # charges on both sides
    assert r[1]["cost"] == 555 and r[1]["sale"] == 600 - 10


def test_intraday_is_apart_and_only_the_overlap():
    c = T.compute([b("2024-09-02", 30, 100), s("2024-09-02", 20, 105), s("2024-12-02", 10, 90)], today=TODAY)
    assert c["intraday"] == [{"key": "A", "d": "2024-09-02", "fy": 2024, "qty": 20, "buy": 2000, "sell": 2100, "pnl": 100}]
    assert [(x["qty"], x["gain"]) for x in c["realised"]] == [(10, -100)]                # the rest was delivery
    y = T.year(2024, c["realised"], c["intraday"])
    assert y["intraday"]["pnl"] == 100 and y["stcg"]["losses"] == 100                   # not mixed into capital gains


def test_a_sale_with_no_buy_in_the_files():
    c = T.compute([b("2024-01-01", 5, 100), s("2024-02-01", 8, 120)], today=TODAY)
    assert c["realised"][0]["qty"] == 5 and c["unmatched"] == [{"key": "A", "d": "2024-02-01", "qty": 3, "sale": 360}]


def test_bonus_shares_cost_nothing_and_are_held_from_the_bonus_date():
    acts = {"A": [{"kind": "bonus", "ratio": [1, 1], "factor": 2.0, "ex_date": "2024-03-01", "id": "x"}]}
    c = T.compute([b("2023-01-02", 10, 200), s("2024-06-01", 20, 150)], actions=acts, today=TODAY)
    assert [(x["qty"], x["cost"], x["term"], x["bonus"]) for x in c["realised"]] == [(10, 2000, "LT", False), (10, 0, "ST", True)]
    assert c["unmatched"] == []
    # a buy on the ex-date gets no bonus
    c = T.compute([b("2024-03-01", 10, 200)], actions=acts, today=TODAY)
    assert sum(l["qty"] for l in c["open"]) == 10


def test_a_split_keeps_cost_and_date():
    acts = {"A": [{"kind": "split", "factor": 5.0, "ex_date": "2024-03-01", "id": "y"}]}
    c = T.compute([b("2023-01-02", 10, 1000), s("2024-06-01", 50, 250)], actions=acts, today=TODAY)
    r = c["realised"]
    assert len(r) == 1 and r[0]["qty"] == 50 and r[0]["cost"] == 10_000 and r[0]["term"] == "LT" and r[0]["bought"] == "2023-01-02"
    # tax P&L lines already show it: they're left alone
    c = T.compute([b("2023-01-02", 10, 1000, src="pnl"), s("2024-06-01", 10, 1250, src="pnl")], actions=acts, today=TODAY)
    assert c["realised"][0]["qty"] == 10 and c["open"] == []


def test_grandfathering_at_the_31_jan_2018_price():
    def sale(price, fmv=150):
        return realised([b("2017-01-02", 1, 100), s("2019-06-03", 1, price)], fmv={"A": fmv})[0]
    assert sale(200)["gain"] == 50 and sale(200)["gf"] == "applied"        # cost is the higher 150
    assert sale(120)["gain"] == 0                                          # ...but no higher than the sale
    assert sale(90)["gain"] == -10                                         # actual cost when that's higher
    assert sale(200, fmv=80)["gain"] == 100                                # a lower FMV doesn't lower the cost
    missing = realised([b("2017-01-02", 1, 100), s("2019-06-03", 1, 200)])[0]
    assert missing["gf"] == "missing" and missing["gain"] == 100
    y = fy([b("2017-01-02", 1, 100), s("2019-06-03", 1, 200)], 2019)
    assert y["gf_missing"] == 1
    # bought on 1 Feb 2018: not grandfathered
    assert realised([b("2018-02-01", 1, 100), s("2019-06-03", 1, 200)], fmv={"A": 150})[0]["gf"] is None


def test_grandfathering_follows_a_split_and_a_value_from_the_file():
    acts = {"A": [{"kind": "split", "factor": 2.0, "ex_date": "2016-06-01", "id": "z"}]}
    # 1 share at 400 became 2 before 2018; the FMV is a share of 2018: 300 each
    r = realised([b("2015-01-02", 1, 400), s("2019-06-03", 2, 350)], actions=acts, fmv={"A": 300})
    assert r[0]["gf"] == "applied" and r[0]["cost"] == 600 and r[0]["gain"] == 100
    r = realised([b("2017-01-02", 2, 100, fmv=130), s("2019-06-03", 2, 200)])
    assert r[0]["cost"] == 260
    # a split going ex on 1 Feb 2018 comes after the 31 Jan valuation; a buy on 31 Jan itself is grandfathered
    acts = {"A": [{"kind": "split", "factor": 2.0, "ex_date": "2018-02-01", "id": "z"}]}
    r = realised([b("2018-01-31", 1, 400), s("2019-06-03", 2, 300)], actions=acts, fmv={"A": 500})
    assert r[0]["gf"] == "applied" and r[0]["cost"] == 500 and r[0]["gain"] == 100


def test_open_lots_below_cost_are_facts_only():
    c = T.compute([b("2025-01-10", 10, 500, "X"), b("2024-01-10", 5, 100, "Y"), b("2025-06-01", 3, 50, "Z")], today=TODAY)
    v = T.below_cost(c["open"], {"X": {"price": 400}, "Y": {"price": 150}}, "2025-10-01")
    assert [r["key"] for r in v["rows"]] == ["X"] and v["unpriced"] == 1
    x = v["rows"][0]
    assert x["loss"] == -1000 and x["term"] == "ST" and x["long_from"] == "2026-01-11" and x["days"] == 264
    assert v["st"] == -1000 and v["lt"] == 0


def test_holdings_check_flags_a_difference():
    c = T.compute([b("2024-01-10", 10, 500, "X")], today=TODAY)
    assert T.holdings_check(c["open"], [{"symbol": "X", "qty": 12}, {"symbol": "W", "qty": 1}]) == [{"key": "X", "files": 10, "holdings": 12}]
    assert T.holdings_check(c["open"], [{"symbol": "X", "qty": 10}]) == []


def test_merge_drops_duplicates_but_keeps_two_identical_fills_in_one_file():
    one = [b("2024-01-10", 10, 500, tid="1"), b("2024-01-10", 10, 500, tid="2"), b("2024-01-11", 1, 1), b("2024-01-11", 1, 1)]
    got, added, dup = T.merge([], one)
    assert added == 4 and dup == 0
    got, added, dup = T.merge(got, one)
    assert added == 0 and dup == 4 and len(got) == 4


def test_money_in_indian_style():
    assert T.money(125000) == "₹1,25,000" and T.money(-1234567.4) == "-₹12,34,567" and T.money(999) == "₹999"


# ---------- reading files ----------
def test_dates_as_brokers_write_them():
    for raw in ("2024-07-22", "2024-07-22T10:15:00", "22-07-2024", "22/07/2024 10:15 AM", "22-Jul-2024", "22 Jul 24",
                "Jul 22, 2024", "45495", "22.07.2024"):
        assert hf.day(raw) == "2024-07-22", raw
    assert hf.day("07/22/2024") == "2024-07-22"                 # month first only when the day can't be
    assert hf.day("31-02-2024") is None and hf.day("x") is None and hf.day("") is None and hf.day("99999999999") is None


def test_buy_and_sell_words():
    assert [hf.side(x) for x in ("BUY", "b", "Purchase", "Sell", "S", "sold", "SELL ", "hold", "")] == ["B", "B", "B", "S", "S", "S", "S", None, None]


def test_every_sample_tradebook_is_read():
    expect = {"zerodha_console_tradebook.csv": ("Zerodha Console", "trades", 7, 1), "groww_order_history.xlsx": ("Groww", "trades", 3, 0),
              "upstox_tradebook.csv": ("Upstox", "trades", 4, 0), "angel_one_tradebook.xlsx": ("Angel One", "trades", 2, 0),
              "icici_direct_tradebook.csv": ("ICICI Direct", "trades", 2, 0), "hdfc_securities_tradebook.xls": ("HDFC Securities", "trades", 2, 0),
              "zerodha_tax_pnl.xlsx": ("Zerodha", "pnl", 4, 0), "generic_trades.csv": ("CSV", "trades", 3, 0)}
    for name, (broker, kind, n, problems) in expect.items():
        got = hf.parse_trades((FIX / name).read_bytes(), name)
        assert (got["broker"], got["kind"], len(got["trades"]), len(got["problems"])) == (broker, kind, n, problems), name


def test_the_sample_files_are_what_the_maker_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(tradebook_maker, "DIR", tmp_path)
    monkeypatch.setattr(tradebook_maker, "ZIP_DIR", tmp_path / "taxpnl")      # checked in test_tax_zip
    tradebook_maker.write()
    for p in (p for p in tmp_path.iterdir() if p.is_file()):
        assert hf.parse_trades(p.read_bytes(), p.name) == hf.parse_trades((FIX / p.name).read_bytes(), p.name), p.name


def test_charges_without_stt_and_values_without_prices():
    angel = hf.parse_trades((FIX / "angel_one_tradebook.xlsx").read_bytes())["trades"]
    assert angel[0]["charges"] == 27.5                         # 52.30 in all less 24.80 STT
    icici = hf.parse_trades((FIX / "icici_direct_tradebook.csv").read_bytes())["trades"]
    assert icici[0]["charges"] == 42.7 and icici[0]["isin"] == "INE062A01020"
    groww = hf.parse_trades((FIX / "groww_order_history.xlsx").read_bytes())["trades"]
    assert groww[0]["price"] == 410.2 and groww[0]["t"] == "10:15 AM"
    assert not any(t["symbol"] == "TATASTEEL" and t["side"] == "S" for t in groww)   # the cancelled order


def test_tax_pnl_lines_become_a_buy_and_a_sale_with_the_fmv():
    t = hf.parse_trades((FIX / "zerodha_tax_pnl.xlsx").read_bytes())["trades"]
    assert (t[0]["side"], t[0]["d"], t[0]["price"], t[0]["fmv"]) == ("B", "2017-06-12", 260, 310)
    assert (t[1]["side"], t[1]["d"], t[1]["price"]) == ("S", "2024-12-16", 300) and t[2]["fmv"] is None


def test_files_we_cant_use_get_a_plain_answer():
    holdings_file = (Path(__file__).parent / "fixtures" / "holdings" / "upstox_holdings.csv").read_bytes()
    for data, words in ((b"", "empty"), (b"%PDF-1.4", "PDF"), (holdings_file, "holdings file"), (b"a,b\n1,2\n", "couldn't find any trades"),
                        (b"Date,Symbol,Type,Quantity,Price\n2024-01-01,X,HOLD,1,10\n", "buy or a sale"),
                        (b"Date,Symbol,Type,Quantity,Price\nsoon,X,BUY,1,10\n", "date couldn't be read"),
                        (b"Date,Symbol,Type,Quantity,Price\n2024-01-01,X,BUY,1,\n", "No price"),
                        (b"x" * (hf.TAX_MAX_BYTES + 1), "larger than")):
        with pytest.raises(hf.FileError) as e:
            hf.parse_trades(data)
        assert words in str(e.value), words


def test_random_files_never_crash_the_reader():
    rng = random.Random(7)
    good = (FIX / "zerodha_console_tradebook.csv").read_bytes()
    for i in range(300):
        data = bytearray(good)
        for _ in range(rng.randint(1, 40)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        if i % 3 == 0:
            data = bytes(rng.randrange(256) for _ in range(rng.randint(0, 400)))
        try:
            got = hf.parse_trades(bytes(data))
        except hf.FileError:
            continue
        for t in got["trades"]:
            assert t["side"] in ("B", "S") and t["qty"] > 0 and t["price"] > 0 and len(t["d"]) == 10
            T.compute(got["trades"], today=TODAY)


# ---------- through the app ----------
def test_every_broker_combined_into_one_report(w):
    c = w["client"]
    for p in sorted(FIX.iterdir()):
        r = upload(c, p.name)
        assert r.status_code == 200, (p.name, r.text)
    rep = c.get("/tax", headers=PRO).json()
    assert rep["trades"] == 27 and len(rep["files"]) == 8 and rep["disclaimer"].startswith("An estimate")
    y = next(y for y in rep["years"] if y["fy"] == 2024)
    assert y["intraday"] == {"count": 1, "buy": 36000.0, "sell": 36300.0, "pnl": 300.0}         # INFY bought and sold the same day
    rel = [r for r in y["rows"] if r["key"] == "RELIANCE"]
    assert [(r["qty"], r["term"], r["rate"]) for r in rel] == [(8, "LT", 0.10), (2, "LT", 0.125), (5, "LT", 0.125)]
    wipro = next(r for r in y["rows"] if r["key"] == "WIPRO")
    assert wipro["gf"] == "applied" and wipro["cost"] == 15000                                  # FMV from the tax P&L
    assert rep["fmv"]["WIPRO"]["source"] == "your file" and rep["fmv"]["SBIN"]["source"] == "looked up"
    old = next(y for y in rep["years"] if y["fy"] == 2019)
    assert old["rows"][0]["key"] == "SBIN" and old["rows"][0]["gf"] == "applied"               # ICICI's STABAN, by its ISIN
    assert y["exemption"]["used"] == y["ltcg"]["net"] and y["tax"] == round(y["stcg"]["net"] * IN_STCG, 2)
    assert {r["key"] for r in rep["below_cost"]["rows"]} <= {"TCS", "TATASTEEL", "ITC"}
    assert rep["names"]["NOTASTOCK"]["listed"] is False


def test_same_file_twice_adds_nothing_and_replace_starts_again(w):
    c = w["client"]
    first = upload(c, "upstox_tradebook.csv").json()
    again = upload(c, "upstox_tradebook.csv").json()
    assert first["added"] == 4 and again["added"] == 0 and again["duplicates"] == 4
    r = upload(c, "generic_trades.csv", mode="replace").json()
    assert r["report"]["trades"] == 3 and [f["name"] for f in r["report"]["files"]] == ["generic_trades.csv"]
    assert r["not_listed"] == ["NOTASTOCK"]


def test_problems_are_listed_with_lines(w):
    r = upload(w["client"], "zerodha_console_tradebook.csv").json()
    assert r["problem_count"] == 1 and r["problems"][0]["line"] == 9 and "Futures" in r["problems"][0]["reason"]
    bad = upload(w["client"], "x.csv", b"hello")
    assert bad.status_code == 400 and "couldn't find any trades" in bad.json()["detail"]["message"].lower() or "trades" in bad.text


def test_own_fmv_is_used_and_can_be_cleared(w):
    c = w["client"]
    upload(c, "icici_direct_tradebook.csv")
    r = c.put("/tax/fmv", headers=PRO, json={"symbol": "SBIN", "fmv": 310}).json()
    row = next(y for y in r["years"] if y["fy"] == 2019)["rows"][0]
    assert r["fmv"]["SBIN"] == {"value": 310, "source": "yours"} and row["cost"] == 31000
    r = c.put("/tax/fmv", headers=PRO, json={"symbol": "SBIN", "fmv": None}).json()
    assert r["fmv"]["SBIN"]["source"] == "looked up"
    assert c.put("/tax/fmv", headers=PRO, json={"symbol": "ITC", "fmv": 100}).status_code == 404


def test_holdings_are_compared(w):
    c = w["client"]
    c.post("/holdings/import", headers=PRO, json={"filename": "h.csv", "data": base64.b64encode(b"Symbol,Quantity,Average price\nTCS,5,3600\n").decode()})
    rep = upload(c, "zerodha_console_tradebook.csv").json()["report"]
    # 2 bought, and 2 more from the 1:1 bonus going ex today in the fake world's corporate actions
    assert rep["holdings_check"] == [{"key": "TCS", "files": 4, "holdings": 5}]


def test_downloads(w):
    c = w["client"]
    upload(c, "zerodha_console_tradebook.csv")
    csv_ = c.get("/tax/export?fy=2024&format=csv", headers=PRO)
    assert csv_.status_code == 200 and "attachment" in csv_.headers["content-disposition"] and "FY-2024-25" in csv_.headers["content-disposition"]
    text = csv_.text
    assert "not tax advice" in text and "RELIANCE,INE002A01018,2023-05-10,2024-06-14,8" in text
    pdf = c.get("/tax/export?fy=2024&format=pdf", headers=PRO)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    from pypdf import PdfReader
    import io
    words = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "FY 2024-25" in words and "not tax advice" in words and "Set-off rules" in words
    assert c.get("/tax/export?fy=1800&format=csv", headers=PRO).status_code == 422
    empty = c.get("/tax/export?fy=2010&format=pdf", headers=PRO)
    assert empty.status_code == 200


def test_csv_cells_are_not_formulas():
    y = T.year(2024, [], [])
    out = tax_export.to_csv(y, [{"key": "=HYPERLINK(1)", "bought": "2024-01-01", "sold": "2024-05-01", "qty": 1, "cost": 1, "sale": 2,
                                 "gain": 1, "term": "ST", "bonus": False, "gf": None, "rate": 0.15}], {})
    assert "'=HYPERLINK(1)" in out


def test_private_per_user_and_deletable(w):
    c = w["client"]
    upload(c, "upstox_tradebook.csv")
    assert c.get("/tax", headers=FREE).json()["trades"] == 0                    # someone else sees nothing
    assert db.get_setting("taxlots:u-pro")
    assert c.delete("/tax", headers=PRO).json() == {"deleted": True}
    assert db.get_setting("taxlots:u-pro") is None and c.get("/tax", headers=PRO).json()["trades"] == 0
    assert c.get("/tax").status_code == 401


def test_no_provider_names_or_advice_words(w):
    c = w["client"]
    for p in sorted(FIX.iterdir()):
        upload(c, p.name)
    import json
    text = json.dumps(c.get("/tax", headers=PRO).json()).lower()
    for bad in ("yahoo", "kite", "screener", "finnhub", "you should", "harvest now", "recommend"):
        assert bad not in text, bad
