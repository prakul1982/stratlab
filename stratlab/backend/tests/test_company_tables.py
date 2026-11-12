"""Lane c-f2: a company's peers, statements and shareholding by quarter (app/company_tables.py), trimmed on the server by plan:
Free sees a teaser, Basic everything (tables), Pro the downloads (export). Fixtures only, no network."""
import csv
import io
import zipfile

import pytest

from app import company_tables as T
from tests import world

FREE, BASIC, PRO = (world.headers(t) for t in ("free-token", "basic-token", "pro-token"))


def row(sym, ind, cap, sector="Information Technology", **k):
    return {"symbol": sym, "name": f"{sym} Ltd", "industry": ind, "sector": sector, "market_cap": cap, "sales_cagr_3y": k.get("g", 10.0),
            "opm": k.get("opm", 20.0), "net_margin": k.get("net", 12.0), "roce": k.get("roce", 18.0), "roe": k.get("roe", 15.0),
            "pe": k.get("pe", 25.0), "foreign": k.get("foreign")}


# an IT services industry of twelve companies around OWNCO's market value, a bank, a lone company and a foreign filer
INDEX = {"at": "2026-10-28T10:00:00+00:00", "rows": [
    row("OWNCO", "IT Services", 100000, g=12.3, opm=24.0, net=19.0, roce=55.0, pe=28.0),
    *[row(f"P{i:02d}", "IT Services", 100000 * (1.15 ** (i if i % 2 else -i)), pe=20 + i) for i in range(1, 13)],
    row("BANKA", "Private Bank", 500000, sector="Financials", opm=None, roce=None, roe=16.5, net=21.0, pe=18.0),
    row("BANKB", "Private Bank", 400000, sector="Financials", opm=None, roce=None, roe=14.0, net=19.0, pe=15.0),
    row("BANKC", "Private Bank", 300000, sector="Financials", opm=None, roce=None, roe=12.0, net=17.0, pe=12.0),
    row("LONE", "Space Tourism", 900, sector="Industrials"),
    row("MAKER", "Machinery", 800, sector="Industrials"), row("MAKER2", "Machinery", 1000, sector="Industrials"),
    row("FOREIGN", "IT Services", 100500, foreign=True),
]}


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    monkeypatch.setitem(T._wire, "index", lambda region: INDEX)
    yield built
    built["close"]()


# ---------- peers ----------
def test_peers_are_the_same_industry_nearest_in_market_value():
    own, peers, basis = T.peer_set(INDEX["rows"], "OWNCO")
    assert own["symbol"] == "OWNCO" and basis == "industry" and len(peers) == T.PEERS_MAX
    caps = [abs(__import__("math").log(p["market_cap"] / own["market_cap"])) for p in peers]
    assert caps == sorted(caps)                                    # nearest first
    assert "FOREIGN" not in {p["symbol"] for p in peers}            # a foreign filer only beside foreign filers
    assert "OWNCO" not in {p["symbol"] for p in peers}


def test_too_small_an_industry_widens_to_the_sector_and_none_is_said():
    _, peers, basis = T.peer_set(INDEX["rows"], "LONE")
    assert basis == "sector" and {p["symbol"] for p in peers} == {"MAKER", "MAKER2"}
    assert T.peer_set(INDEX["rows"], "NOSUCH") == (None, [], "none")
    _, peers, basis = T.peer_set([row("A", "X", 10, sector="S")], "A")
    assert (peers, basis) == ([], "none")


def test_a_lender_is_compared_on_return_on_equity():
    v = T.peers_view("IN", "BANKA", INDEX["rows"], None, {"full": True, "export": True})
    assert v["return_label"] == "ROE" and v["lender"] is True
    assert v["own"]["ret"] == 16.5 and v["own"]["ebitda"] is None
    assert [x["ret"] for x in v["rows"]] == [14.0, 12.0]
    # the stored page's own word wins over the index's shape
    assert T.peers_view("IN", "OWNCO", INDEX["rows"], {"bank": True}, {"full": True, "export": True})["return_label"] == "ROE"


def test_median_row_is_of_the_peers_shown():
    m = T.median_row([{"market_cap": 10, "sales_growth": 1.0, "ebitda": None, "net": 5.0, "ret": 3.0, "pe": 10.0},
                      {"market_cap": 30, "sales_growth": 3.0, "ebitda": None, "net": 7.0, "ret": 5.0, "pe": None}])
    assert m["market_cap"] == 20 and m["sales_growth"] == 2.0 and m["ebitda"] is None and m["ebitda_n"] == 0 and m["pe"] == 10.0 and m["pe_n"] == 1


def test_peers_by_plan(w):
    c = w["client"]
    free = c.get("/research/company/IN/OWNCO/peers", headers=FREE).json()
    assert len(free["rows"]) == T.PEERS_FREE and free["total"] == T.PEERS_MAX and free["own"]["symbol"] == "OWNCO"
    assert free["own"]["own"] is True and free["can_sort"] is False and free["can_export"] is False
    assert free["locked"]["plan"] == "basic" and "other 7 peers" in free["locked"]["message"] and "Basic plan" in free["locked"]["message"]
    assert free["median"]["pe_n"] == T.PEERS_FREE
    basic = c.get("/research/company/IN/OWNCO/peers", headers=BASIC).json()
    assert len(basic["rows"]) == T.PEERS_MAX and basic["can_sort"] is True and basic["locked"] is None
    assert basic["rows"][:3] == free["rows"]                         # the teaser is the nearest three of the full table
    assert basic["export_locked"]["plan"] == "pro" and "Pro plan" in basic["export_locked"]["message"]
    pro = c.get("/research/company/IN/OWNCO/peers", headers=PRO).json()
    assert pro["can_export"] is True and pro["export_locked"] is None
    assert c.get("/research/company/IN/OWNCO/peers").status_code == 401          # signed in only (visitors see the public page)
    assert c.get("/research/company/XX/OWNCO/peers", headers=PRO).status_code == 400
    assert c.get("/research/company/IN/..%2Fx/peers", headers=PRO).status_code in (400, 404)


def test_peers_csv_is_pro_only(w):
    c = w["client"]
    for h in (FREE, BASIC):
        r = c.get("/research/company/IN/OWNCO/peers.csv", headers=h)
        assert r.status_code == 402 and "Pro plan" in r.json()["detail"]["message"]
    r = c.get("/research/company/IN/OWNCO/peers.csv", headers=PRO)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="stratlab-OWNCO-peers.csv"' in r.headers["content-disposition"]
    lines = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert lines[0][2] == "Market value (₹ crore)" and lines[0][6] == "ROCE (%)"
    assert lines[1][0] == "OWNCO" and len(lines) == 1 + 1 + T.PEERS_MAX + 1 and lines[-1][1] == "Median of the peers"


def test_csv_cells_never_start_a_formula():
    out = T._csv(["a"], [["=1+1"], ["-5"], [-5], ["x"]]).decode("utf-8-sig").splitlines()
    assert out[1:] == ["'=1+1", "'-5", "-5", "x"]


# ---------- statements ----------
def page():
    """A fundamentals page: six years and TTM of profit and loss, a balance sheet with a half-year column and one year missing, two years
    of cash flow, fourteen quarters."""
    years = ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    qs = [f"{m} {y}" for y in (2023, 2024, 2025, 2026) for m in ("Mar", "Jun", "Sep", "Dec")][:14]
    return {"name": "Own Co", "basis": "consolidated", "fetched_at": "2026-10-28T09:00",
            "pl": {"cols": years + ["TTM"], "rows": {"Sales +": [100, 110, 120, 130, 150, 180, 190], "Operating Profit": [20, 22, 25, 26, 30, 36, 38],
                                                     "Net Profit +": [10, 11, 12, 13, 15, 18, 19], "EPS in Rs": [1, 1.1, 1.2, 1.3, 1.5, 1.8, 1.9]}},
            "balance": {"cols": years[:3] + years[4:] + ["Sep 2026"], "rows": {"Equity Capital": [10, 10, 10, 10, 10, 10],
                                                                               "Reserves": [40, 50, 60, 80, 90, 95], "Borrowings": [25, 25, 30, 30, 20, 20]}},
            "cashflow": {"cols": years[-2:], "rows": {"Cash from Operating Activity": [16, 21]}},
            "quarters": {"cols": qs, "rows": {"Sales": list(range(30, 44)), "Net Profit": list(range(3, 17))}},
            "shareholding": {"cols": qs, "rows": {"Promoters +": [50.0] * 14, "FIIs +": [20.0 + i / 10 for i in range(14)],
                                                  "DIIs +": [15.0] * 14, "Public +": [15.0 - i / 10 for i in range(14)],
                                                  "No. of Shareholders": [1000 + i for i in range(14)]}}}


def test_statements_in_full_never_fill_a_missing_figure():
    v = T.statements_view(page(), "IN", "OWNCO", {"full": True, "export": False}, ["consolidated"])
    assert v["cols"] == ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"] and v["years_stored"] == 6
    keys = [s["key"] for s in v["sections"]]
    assert keys == ["pl", "balance", "cashflow", "ratios_table"]
    sec = {s["key"]: {r["label"]: r for r in s["rows"]} for s in v["sections"]}
    assert sec["pl"]["Sales"]["values"] == [100, 110, 120, 130, 150, 180] and sec["pl"]["Sales"]["kind"] == "money"   # no TTM, "+" dropped
    assert sec["pl"]["EPS in Rs"]["kind"] == "per_share"
    assert sec["balance"]["Reserves"]["values"] == [40, 50, 60, None, 80, 90]           # Mar 2024 not stored: None, the half-year left out
    assert sec["cashflow"]["Cash from Operating Activity"]["values"] == [None, None, None, None, 16, 21]
    ratios = sec["ratios_table"]
    assert ratios["Sales growth %"]["values"][1] == 10.0 and ratios["Sales growth %"]["values"][0] is None
    assert ratios["EBITDA margin %"]["values"][-1] == 20.0 and ratios["Net margin %"]["values"][-1] == 10.0
    assert ratios["Return on equity %"]["values"][3] is None and ratios["Return on equity %"]["values"][-1] == 18.0
    assert ratios["Debt to equity"]["values"][-1] == 0.2 and ratios["Debt to equity"]["kind"] == "ratio"
    assert all(r.get("worked") for r in ratios.values())
    assert len(v["quarters"]["cols"]) == T.QUARTERS_MAX and v["quarters"]["cols"][-1] == "Jun 2026"
    assert v["notes"] == [T.MISSING_NOTE] and v["locked"] is None and v["export_locked"]["plan"] == "pro"


def test_statements_for_free_are_the_latest_three_years_of_profit_and_loss():
    v = T.statements_view(page(), "IN", "OWNCO", {"full": False, "export": False}, ["consolidated", "standalone"])
    assert v["cols"] == ["Mar 2024", "Mar 2025", "Mar 2026"] and [s["key"] for s in v["sections"]] == ["pl"]
    assert v["sections"][0]["rows"][0]["values"] == [130, 150, 180] and v["quarters"] is None
    assert v["locked"]["plan"] == "basic" and "All 6 years" in v["locked"]["message"] and "standalone and consolidated" in v["locked"]["message"]
    assert v["hidden"] == {"years": 3, "sections": ["Balance sheet", "Cash flow", "Ratios"], "quarters": 12}
    assert v["notes"] == []                                         # nothing missing in what it sees


def test_a_lender_has_no_ebitda_margin_or_debt_to_equity():
    p = page()
    p["pl"]["rows"] = {"Revenue": p["pl"]["rows"]["Sales +"], "Financing Profit": [5] * 7, "Net Profit": p["pl"]["rows"]["Net Profit +"]}
    v = T.statements_view(p, "IN", "BANKA", {"full": True, "export": True}, ["consolidated"])
    labels = {r["label"] for s in v["sections"] if s["key"] == "ratios_table" for r in s["rows"]}
    assert v["lender"] and "Revenue growth %" in labels and "EBITDA margin %" not in labels and "Debt to equity" not in labels


def test_statements_endpoint_by_plan_india(w):
    c = w["client"]
    free = c.get("/research/company/IN/RELIANCE/statements", headers=FREE).json()
    assert free["unit"] == "₹ crore" and len(free["cols"]) == 3 and [s["key"] for s in free["sections"]] == ["pl"]
    assert free["locked"]["plan"] == "basic" and free["quarters"] is None
    basic = c.get("/research/company/IN/RELIANCE/statements", headers=BASIC).json()
    assert basic["cols"][-1] == "Mar 2025" and len(basic["cols"]) == basic["years_stored"] == 6
    assert {"pl", "balance", "cashflow", "ratios_table"} <= {s["key"] for s in basic["sections"]}
    assert basic["quarters"]["cols"][-1] == "Jun 2025" and basic["notes"] == [T.MISSING_NOTE]      # the cash flow has two years
    assert basic["can_export"] is False and basic["export_locked"]["plan"] == "pro"
    assert c.get("/research/company/IN/RELIANCE/statements", headers=PRO).json()["can_export"] is True


def test_statements_endpoint_us(w):
    v = w["client"].get("/research/company/US/AAPL/statements", headers=BASIC).json()
    assert v["region"] == "US" and v["unit"].startswith("$") and v["bases"] == ["consolidated"]
    assert v["sections"][0]["key"] == "pl" and v["sections"][0]["rows"][0]["label"] == "Sales"


def test_other_basis_is_offered_only_for_the_same_company(monkeypatch):
    p = page()

    class Scr:
        def company(self, s):
            return dict(p)

        def _page(self, path):
            assert path == "/company/OWNCO/"
            return {**p, "pl": {**p["pl"], "rows": {"Sales": [1, 2, 3, 4, 5, 6, 7]}}}
    monkeypatch.setitem(T._wire, "screener", lambda: Scr())
    monkeypatch.setitem(T._wire, "bse_code", lambda s: None)
    got = T.india_pages("OWNCO")
    assert set(got) == {"consolidated", "standalone"} and got["standalone"]["pl"]["rows"]["Sales"][0] == 1
    v = T._statements("IN", "OWNCO", "standalone", {"full": True, "export": True})
    assert v["basis"] == "standalone" and v["bases"] == ["consolidated", "standalone"]
    # Free sees the page's own basis whatever it asks for
    assert T._statements("IN", "OWNCO", "standalone", {"full": False, "export": False})["basis"] == "consolidated"

    class Other(Scr):
        def _page(self, path):
            return {**p, "name": "Someone Else"}
    monkeypatch.setitem(T._wire, "screener", lambda: Other())
    assert set(T.india_pages("OWNCO")) == {"consolidated"}


def test_statement_downloads_are_pro_only(w):
    c = w["client"]
    for h in (FREE, BASIC):
        assert c.get("/research/company/IN/RELIANCE/statements.xlsx", headers=h).status_code == 402
        assert c.get("/research/company/IN/RELIANCE/statements.csv", headers=h).status_code == 402
    r = c.get("/research/company/IN/RELIANCE/statements.xlsx", headers=PRO)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    book = z.read("xl/workbook.xml").decode()
    assert 'name="Profit and loss"' in book and 'name="Quarters"' in book and 'name="Balance sheet"' in book
    r = c.get("/research/company/IN/RELIANCE/statements.csv", headers=PRO)
    text = r.content.decode("utf-8-sig")
    assert r.status_code == 200 and text.startswith('"Profit and loss (₹ crore, consolidated)",Mar 2020')
    assert c.get("/research/company/IN/RELIANCE/statements.pdf", headers=PRO).status_code == 404


# ---------- shareholding ----------
def test_holding_quarters_reads_the_table():
    qs = T.holding_quarters(page()["shareholding"])
    assert len(qs) == T.QUARTERS_MAX and qs[-1]["quarter"] == "Jun 2026"
    assert qs[-1]["promoters"] == 50.0 and qs[-1]["fiis"] == 21.3 and qs[-1]["public"] == 13.7 and qs[-1]["shareholders"] == 1013
    assert qs[-1]["government"] is None and qs[-1]["pledge"] is None
    assert T.holding_quarters(None) == [] and T.holding_quarters({"cols": [], "rows": {}}) == []


def test_shareholding_by_plan(w):
    c = w["client"]
    free = c.get("/research/company/IN/RELIANCE/shareholding", headers=FREE).json()
    assert free["available"] and len(free["quarters"]) == 1 and free["quarters"][0]["quarter"] == "Jun 2025"
    assert free["quarters"][0]["promoters"] == 50.07
    assert free["chart"] is False and free["locked"]["plan"] == "basic" and "last 5 quarters" in free["locked"]["message"]
    assert "pledged" in free["pledge_note"]
    basic = c.get("/research/company/IN/RELIANCE/shareholding", headers=BASIC).json()
    assert len(basic["quarters"]) == 5 and basic["chart"] is True and basic["locked"] is None
    assert basic["keys"] == ["promoters", "fiis", "diis", "public"] and basic["quarters"][-1]["shareholders"] > 0
    us = c.get("/research/company/US/AAPL/shareholding", headers=BASIC).json()
    assert us["available"] is False and "Holders above 5%" in us["note"] and us["quarters"] == []


def test_no_advice_words_in_what_the_tables_say():
    from app.intel.grounding import ADVICE
    words = [T.MISSING_NOTE, T.PLEDGE_NOTE, T.US_NOTE, *T.BASIS_WORDS.values()]
    v = T.statements_view(page(), "IN", "OWNCO", {"full": False, "export": False}, ["consolidated"])
    words += [v["locked"]["message"]]
    assert not [x for x in words if ADVICE.search(x)]
