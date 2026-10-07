"""ETFs, REITs, InvITs and Sovereign Gold Bonds: telling them apart from a broker's file, keeping them in My Holdings
with their badge, and taxing each kind under its own rules in the tax report."""
import base64

import pytest

from app import holdings, holdings_file as hf, instrument_kinds as I, tax_lots as T, tax_total
from tests import tradebook_maker as M, world

PRO = world.headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


# ---------- classification ----------
@pytest.mark.parametrize("symbol,isin,name,code", [
    ("RELIANCE", "INE002A01018", "Reliance Industries Ltd", "stock"),
    ("NIFTYBEES", "INF204KB14I2", "", "etf-equity"),
    ("GOLDBEES", "INF204KB17I5", "", "etf-gold"),
    ("", "INF204KB17I5", "Nippon India ETF Gold BeES", "etf-gold"),
    ("SILVERBEES", "", "", "etf-silver"),
    ("LIQUIDBEES", "INF732E01037", "", "etf-debt"),
    ("EBBETF0430", "", "Bharat Bond ETF April 2030", "etf-debt"),
    ("MON100", "INF247L01AP3", "Motilal Oswal Nasdaq 100 ETF", "etf-intl"),
    ("MAFANG", "", "", "etf-intl"),
    ("CPSEETF", "", "CPSE ETF", "etf-equity"),
    ("EMBASSY", "INE041025011", "Embassy Office Parks REIT", "reit"),
    ("MINDSPACE-RR", "", "", "reit"),
    ("INDIGRID", "", "", "invit"),
    ("PGINVIT", "", "", "invit"),
    ("XYZ-IV", "", "", "invit"),
    ("", "", "IRB InvIT Fund", "invit"),
    ("SGBMAY29I-GB", "IN0020210079", "", "sgb"),
    ("SGBMAR28X", "", "", "sgb"),
    ("", "IN0020200153", "2.50% Gold Bonds 2028 Sr-II", "sgb"),
    ("", "INF000A01000", "Mutual fund units XYZ - Direct Plan Growth", "mf"),
    ("NSE:GOLDBEES", "", "", "etf-gold"),
    ("GOLDMAN", "", "Goldman Sachs Ltd", "stock"),
])
def test_classify(symbol, isin, name, code):
    assert I.classify(symbol, isin, name) == code


def test_labels_and_tax_classes():
    assert [I.label(c) for c in ("stock", "etf-equity", "etf-gold", "etf-debt", "etf-intl", "reit", "invit", "sgb")] == \
        ["Shares", "Equity ETF", "Gold ETF", "Debt ETF", "International ETF", "REIT", "InvIT", "Gold bond"]
    assert [I.tax_class(c) for c in ("stock", "etf-equity", "reit", "invit", "etf-gold", "etf-silver", "etf-intl", "etf-debt", "sgb")] == \
        ["equity", "equity", "equity", "equity", "other", "other", "other", "debt", "sgb"]
    assert I.sgb_maturity("SGBMAY29I-GB") == "2029-05" and I.sgb_maturity("GOLDBEES") is None


# ---------- the tax rule each sale follows ----------
@pytest.mark.parametrize("code,symbol,bought,sold,head", [
    # gold ETF bought before 1 Apr 2023: listed units, long term after 12 months at 12.5% (sale from 23 Jul 2024)
    ("etf-gold", "GOLDBEES", "2022-01-10", "2024-10-01", "lt"),
    ("etf-gold", "GOLDBEES", "2024-01-10", "2024-10-01", "slab"),        # section 50AA: bought from 1 Apr 2023, sold before 1 Apr 2025
    ("etf-gold", "GOLDBEES", "2024-01-10", "2025-06-01", "lt"),          # narrowed definition from FY 2025-26: 12 months, 12.5%
    ("etf-gold", "GOLDBEES", "2025-01-10", "2025-06-01", "slab"),        # short term
    ("etf-intl", "MON100", "2023-05-01", "2025-05-02", "lt"),
    ("etf-debt", "LIQUIDBEES", "2023-05-01", "2026-05-02", "slab"),     # debt fund bought from 1 Apr 2023: always slab
    ("etf-debt", "LIQUIDBEES", "2022-05-01", "2025-05-02", "lt"),       # bought before: as listed units
    ("etf-gold", "GOLDBEES", "2019-01-10", "2023-03-01", "old"),        # before 23 Jul 2024, after 36 months: indexation rules
    ("etf-gold", "GOLDBEES", "2022-01-10", "2023-03-01", "slab"),       # before 23 Jul 2024, within 36 months
    ("sgb", "SGBMAY29I", "2023-06-01", "2024-03-01", "slab"),            # sold on the exchange within 12 months
    ("sgb", "SGBMAY29I", "2023-06-01", "2024-09-01", "lt"),              # after 12 months, from 23 Jul 2024: 12.5%
    ("sgb", "SGBMAY29I", "2022-06-01", "2024-03-01", "old"),
    ("sgb", "SGBAUG24I", "2017-08-01", "2024-08-20", "exempt"),         # redeemed at maturity before FY 2026-27: exempt
    ("sgb", "SGBNOV26I", "2019-01-01", "2026-11-20", "lt"),             # at maturity from 1 Apr 2026, bought on the exchange
])
def test_treatment(code, symbol, bought, sold, head):
    assert I.treatment(code, symbol, bought, sold, T.fy_of(sold))[0] == head


def lots(symbol, isin, buy, sell, qty=10, bp=100.0, sp=150.0, name=""):
    base = {"symbol": symbol, "isin": isin, "name": name}
    return [{**base, "d": buy, "side": "B", "qty": qty, "price": bp, "tid": f"{symbol}{buy}b"},
            {**base, "d": sell, "side": "S", "qty": qty, "price": sp, "tid": f"{symbol}{sell}s"}]


def test_report_puts_each_kind_under_its_head():
    trades = (lots("NIFTYBEES", "", "2024-05-01", "2025-06-02") +                     # equity ETF: LTCG 112A, 500
              lots("EMBASSY", "", "2024-05-01", "2025-06-02", name="Embassy Office Parks REIT") +   # REIT: 112A too
              lots("GOLDBEES", "", "2024-05-01", "2025-06-02", sp=200.0) +            # gold ETF: 12.5% under 112, 1,000
              lots("SGBMAY29I", "", "2025-05-01", "2025-09-01", bp=9000, sp=9300) +   # gold bond within a year: slab, 3,000
              lots("LIQUIDBEES", "", "2024-05-01", "2025-07-01", bp=1000, sp=1010))   # debt ETF: slab, 100
    rep = T.report(trades, {}, {}, {}, [], "2025-10-01")
    y = next(y for y in rep["years"] if y["fy"] == 2025)
    assert y["ltcg"]["gains"] == 1000 and y["count"] == 2                       # only NIFTYBEES and EMBASSY in the share rules
    assert y["exemption"]["used"] == 1000
    u = y["units"]
    assert {(r["key"], r["head"]) for r in u["rows"]} == {("GOLDBEES", "lt"), ("SGBMAY29I", "slab"), ("LIQUIDBEES", "slab")}
    assert (u["lt"]["taxable"], u["lt"]["tax"], u["slab"]["taxable"]) == (1000, 125, 3100)
    assert rep["kinds"] == {"NIFTYBEES": "Equity ETF", "EMBASSY": "REIT", "GOLDBEES": "Gold ETF", "SGBMAY29I": "Gold bond",
                            "LIQUIDBEES": "Debt ETF"}
    assert any("REIT and InvIT distributions" in n for n in rep["unit_notes"])
    total = y["total"]
    assert total["income"]["normal"] == 3100 and total["income"]["special"] == 1000          # slab gains; 12.5% gains
    assert any("ETFs and gold bonds taxed at slab rates" in s for s in total["steps"])
    assert any(l["label"].startswith("Non-equity short-term gains") for l in total["lines"])


def test_unit_losses_set_off_within_their_own_rules():
    trades = (lots("GOLDBEES", "", "2023-01-01", "2025-06-02", sp=200.0) +            # LT gain 1,000
              lots("SGBMAY29I", "", "2025-05-01", "2025-09-01", bp=9000, sp=8900))      # ST loss 1,000
    y = next(y for y in T.report(trades, {}, {}, {}, [], "2025-10-01")["years"] if y["fy"] == 2025)
    assert (y["units"]["lt"]["taxable"], y["units"]["slab"]["taxable"], y["units"]["carry_forward"]) == (0, 0, {"st": 0, "lt": 0})


def test_reit_units_before_july_2024_needed_36_months():
    trades = lots("EMBASSY", "", "2022-01-03", "2024-03-01", name="Embassy Office Parks REIT")   # 26 months: short term then
    y = next(y for y in T.report(trades, {}, {}, {}, [], "2024-10-01")["years"] if y["fy"] == 2023)
    assert y["stcg"]["gains"] == 500 and y["ltcg"]["gains"] == 0
    shares = lots("ITC", "", "2022-01-03", "2024-03-01")                                       # the same dates for shares: long term
    y = next(y for y in T.report(shares, {}, {}, {}, [], "2024-10-01")["years"] if y["fy"] == 2023)
    assert y["ltcg"]["gains"] == 500


def test_estimate_takes_slab_gains_as_other_income():
    v = tax_total.default_inputs()
    a = tax_total.estimate(2025, {**v, "other": 1500000, "salary": 0}, [], 0, 0)
    b = tax_total.estimate(2025, {**v, "other": 1400000, "salary": 0}, [], 0, 0, slab_gains=100000)
    assert a["total"] == b["total"] and b["income"]["normal"] == 1500000


# ---------- reading the files ----------
def test_tradebook_keeps_etfs_and_gold_bonds():
    csv = ("symbol,isin,trade_date,exchange,segment,series,trade_type,quantity,price,trade_id\n"
           "GOLDBEES,INF204KB17I5,2024-05-02,NSE,EQ,EQ,buy,10,60,1\n"
           "SGBMAY29I,IN0020210079,2024-05-02,NSE,EQ,GB,buy,1,7000,2\n"
           "EMBASSY,INE041025011,2024-05-02,NSE,EQ,RR,buy,10,350,3\n").encode()
    got = hf.parse_trades(csv, "tradebook.csv")
    assert [t["symbol"] for t in got["trades"]] == ["GOLDBEES", "SGBMAY29I", "EMBASSY"] and got["problems"] == []


def test_non_equity_file_leaves_out_company_bonds():
    rows = [M.PNL_HEAD, ["GOLDBEES", "INF204KB17I5", "2024-04-15", "2024-11-20", 100, 6100, 6600, 500, 219, 0, 500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ["SGBMAY29I", "IN0020210079", "2023-04-15", "2024-11-20", 1, 6000, 7500, 1500, 584, 0, 1500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ["945ABCL27", "INE001X07015", "2023-04-15", "2024-11-20", 1, 1000, 1010, 10, 584, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]
    got = hf.parse_trades(M._csv(rows).encode(), "Tradewise Exits from 2024-04-01 to 2025-03-31-Non Equity.csv")
    assert sorted({(t["symbol"], t["kind"]) for t in got["trades"]}) == [("GOLDBEES", "etf-gold"), ("SGBMAY29I", "sgb")]
    assert [p["reason"] for p in got["problems"]] == [hf.NOT_COVERED]
    with pytest.raises(hf.FileError, match="Nothing in that file is covered"):
        hf.parse_trades(M._csv([rows[0], rows[3]]).encode(), "Non Equity.csv")


# ---------- through the app ----------
def test_holdings_badges_and_unpriced_units(w):
    c = w["client"]
    csv = ("Symbol,ISIN,Qty,Avg price\nRELIANCE,INE002A01018,5,2500\nSGBMAY29I-GB,IN0020210079,4,4800\n"
           "EMBASSY,INE041025011,20,360\n,INF174KA1HS9,10,55\n").encode()
    csv = csv.replace(b"Symbol,ISIN,Qty,Avg price", b"Symbol,ISIN,Name,Qty,Avg price").replace(b",5,2500", b",,5,2500")
    csv = csv.replace(b",4,4800", b",,4,4800").replace(b",20,360", b",,20,360").replace(b",10,55", b",Kotak Gold ETF,10,55")
    r = c.post("/holdings/import", headers=PRO, json={"filename": "h.csv", "data": base64.b64encode(csv).decode(), "mode": "replace"})
    assert r.status_code == 200, r.text
    rows = {x["symbol"]: x for x in r.json()["holdings"]["rows"]}
    assert (rows["SGBMAY29I-GB"]["kind"], rows["SGBMAY29I-GB"]["kind_label"], rows["SGBMAY29I-GB"]["sector"]) == ("sgb", "Gold bond", "Sovereign Gold Bonds")
    assert (rows["EMBASSY"]["kind"], rows["EMBASSY"]["sector"]) == ("reit", "REITs and InvITs")
    # an ISIN alone, for an ETF the day's lists don't have (the demo broker lists GOLDBEES, so a made-up one): kept by its ISIN
    assert rows["INF174KA1HS9"]["kind_label"] == "Gold ETF"
    assert rows["RELIANCE"]["kind"] == "stock" and r.json()["unmatched"] == []
    saved = {i["symbol"]: i for i in holdings.load("u-pro")["items"]}
    assert saved["EMBASSY"]["kind"] == "reit" and "kind" not in saved["RELIANCE"]


def test_tax_report_api_shows_the_units(w):
    c = w["client"]
    csv = ("symbol,isin,trade_date,trade_type,quantity,price,trade_id\n"
           "GOLDBEES,INF204KB17I5,2023-01-02,buy,10,50,1\nGOLDBEES,INF204KB17I5,2025-06-02,sell,10,80,2\n").encode()
    r = c.post("/tax/import?filename=tb.csv&mode=replace", headers={**PRO, "Content-Type": "application/octet-stream"}, content=csv)
    assert r.status_code == 200, r.text
    y = next(y for y in r.json()["report"]["years"] if y["fy"] == 2025)
    assert y["units"]["lt"]["taxable"] == 300 and y["count"] == 0 and r.json()["report"]["kinds"]["GOLDBEES"] == "Gold ETF"
    out = c.get("/tax/export?fy=2025&format=csv", headers=PRO)
    assert out.status_code == 200 and "ETFs and gold bonds taxed under other rules" in out.text and "Gold ETF" in out.text
