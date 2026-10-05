"""US company pages checked against the SEC's own data (October 2026): trimmed real company-facts, filing lists and
20-F text in tests/fixtures/sec_live. Each case is a company the audit sheet flagged, or one a fix there broke."""
import gzip
import json
import os

import httpx
import pytest

from app import audit, deepdive
from app.intel import sec

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sec_live")


def load(name):
    with gzip.open(os.path.join(FIX, name + ".json.gz"), "rt") as fh:
        return json.load(fh)


def build(name, symbol=""):
    d = load(name)
    return sec.build(d["facts"], d["subs"], symbol=symbol)


def row(p, table, label):
    return dict(zip(p[table]["cols"], p[table]["rows"][label]))


# ---------- Exxon Mobil under its new holding company ----------
def _xom_transport(calls):
    new, old = load("xom_holdings"), load("exxon_mobil_corp")
    by_cik = {2115436: new, 34088: old}

    def handler(r: httpx.Request):
        calls.append(r.url.path)
        if r.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": 2115436, "ticker": "XOM", "title": "ExxonMobil Holdings Corp"}})
        for cik, d in by_cik.items():
            if r.url.path == f"/submissions/CIK{cik:010d}.json":
                return httpx.Response(200, json=d["subs"])
            if r.url.path == f"/api/xbrl/companyfacts/CIK{cik:010d}.json":
                return httpx.Response(200, json=d["facts"])
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_a_new_holding_company_shows_its_predecessors_years():
    # the holding company (8-K12B, July 2026) has filed one 10-Q; Exxon Mobil Corp, which filed it, has the 10-Ks
    with pytest.raises(sec.SourceError) as e:
        build("xom_holdings")
    assert e.value.args and "quarterly" in str(e.value).lower()
    calls = []
    p = sec.SEC(transport=_xom_transport(calls)).company("XOM")
    sales = row(p, "pl", "Sales")
    assert sales["Dec 2024"] == 349585.0 and sales["Dec 2025"] == 332238.0 and "TTM" in sales
    assert row(p, "pl", "Net Profit")["Dec 2025"] == 28844.0
    assert p["shares"] == 4111911960.0                       # today's count, from the holding company's cover page
    # debt due after a year tagged with leases (34,241), the part due within it (6,200) and commercial paper (3,059)
    assert row(p, "balance", "Borrowings")["Dec 2025"] == 43500.0
    assert any(d["kind"] == "annual_report" for d in p["documents"])          # the old company's 10-Ks
    assert not any(c.startswith("/submissions/CIK0001193125") for c in calls)  # a filing agent isn't a candidate


# ---------- banks, lessors and plant ----------
def test_a_banks_quarters_use_net_revenue_not_a_part_of_it():
    p = build("jpm")
    sales = row(p, "pl", "Sales")
    assert sales["Dec 2025"] == 182447.0
    assert 180000 < sales["TTM"] < 220000                    # four quarters of net revenue, not of lease income (~4,400)
    assert all(v is None or v > 30000 for v in p["quarters"]["rows"]["Sales"])


def test_capex_isnt_nil_when_plant_stopped_being_tagged_or_a_fleet_is_depreciated():
    jpm = build("jpm")                                       # premises folded into other assets from 2023
    assert all(v is None for v in jpm["cashflow"]["rows"]["Capex"])
    ayr = row(build("ayr"), "cashflow", "Capex")             # an aircraft lessor buying aircraft
    assert ayr["Feb 2026"] == 1710.76 and ayr["Feb 2025"] == 1588.2


def test_depreciation_is_a_cost_whatever_its_sign_and_from_ifrs_parts():
    aes = build("aes")
    dep = row(aes, "pl", "Depreciation")
    assert dep["Dec 2025"] == 1457.0                         # tagged -1,457 as a cash flow add-back
    op = row(aes, "pl", "Operating Profit")
    assert op["Dec 2025"] > 1457                             # EBITDA: profit plus depreciation, not minus
    azn = build("azn")                                       # plant, right-of-use and intangibles given apart
    assert row(azn, "pl", "Depreciation")["Dec 2025"] == round((879 + 404 + 4207), 2)
    assert row(azn, "pl", "Operating Profit")["Dec 2025"] == 13743.0 + 5490.0


def test_ifrs_bonds_and_loans_are_the_debt():
    facts = {"ifrs-full": {c: {"units": {"TWD": [{"end": "2024-12-31", "val": v, "accn": "a", "form": "20-F"}]}} for c, v in (
        ("NoncurrentPortionOfNoncurrentBondsIssued", 926604500000), ("CurrentBondsIssuedAndCurrentPortionOfNoncurrentBondsIssued", 57148000000),
        ("LongtermBorrowings", 31824400000), ("CurrentPortionOfLongtermBorrowings", 59857900000))}}   # TSMC, 2024
    assert sec._debt(facts, "TWD") == {"2024-12-31": 1075434800000}


# ---------- share counts and equity ----------
def test_a_share_count_from_years_ago_isnt_used():
    brk = build("brk")                                       # the cover page's single count stopped in 2011
    assert brk["shares"] is None
    r = sec.ratios(brk, 502.65)
    assert "Market Cap" not in r and "Book Value" not in r and "Stock P/E" not in r


def test_total_equity_with_a_large_minority_part_isnt_the_owners_equity():
    bn = build("bn")                                         # only the total is tagged; minorities were most of it
    assert row(bn, "balance", "Equity")["Dec 2025"] is None
    r = sec.ratios(bn, 36.92)
    assert "Book Value" not in r and "ROE" not in r and r["Market Cap"] > 50000
    facts = {"us-gaap": {"StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {"units": {"USD": [
        {"end": "2025-12-31", "val": 100e6, "accn": "a", "form": "10-K"}]}},
        "MinorityInterest": {"units": {"USD": [{"end": "2025-12-31", "val": 30e6, "accn": "a", "form": "10-K"}]}}}}
    assert sec._equity(facts) == {"2025-12-31": 70e6}


# ---------- revenue ----------
def test_a_drug_developer_whose_revenue_stopped_has_no_revenue_those_years():
    p = build("avir")                                        # Roche's payments in 2021, nothing after
    assert {"Dec 2022", "Dec 2023", "Dec 2024", "Dec 2025"} <= set(p["no_revenue"])
    found = audit.check_numbers(p, deepdive.numbers(p), {})
    assert not [i for i in found if i["level"] == "gap" and i["area"] == "Numbers"]


def test_a_mortgage_reit_gets_its_own_margin_note():
    p = build("adam")
    assert p["kind"] == "reit" and "mortgage" in p["margin_note"]
    assert all(v is None for v in p["pl"]["rows"]["OPM %"])


# ---------- depositary shares ----------
@pytest.mark.parametrize("sym,ratio", [("TSM", 5), ("BABA", 8), ("BP", 6), ("HDB", 3), ("SHEL", 2), ("TM", 10),
                                       ("PDD", 4), ("INFY", 1), ("NVO", 1), ("SONY", 1), ("BTI", 1), ("ASND", 1),
                                       ("AUTL", 1), ("AZUL", 500000)])
def test_the_ads_ratio_is_read_from_the_annual_report(sym, ratio):
    assert sec.ads_ratio(load("ads_texts")[sym]) == {"ratio": ratio, "ads": True}


def test_ordinary_shares_listed_directly_have_no_ratio():
    # AstraZeneca listed its ordinary shares on the NYSE in place of its ADSs in February 2026
    assert sec.ads_ratio(load("ads_texts")["AZN"]) == {"ratio": None, "ads": False}


@pytest.mark.parametrize("text,ratio", [
    ("American Depositary Shares, each representing one-half of one ordinary share", 0.5),
    ("each ADS represents 1/1,500th of a Class A share", 1 / 1500),
    ("ADSs, each of which represents twenty-five ordinary shares", 25),
    ("ADSs representing 18.5% of our share capital", None),
    ("ADSs representing 58.3 million ordinary shares", None),
])
def test_ratio_wording(text, ratio):
    got = sec.ads_ratios(text)
    assert (got[0] if got else None) == (pytest.approx(ratio) if ratio else None)


def test_market_value_counts_adss_and_the_page_says_so():
    p = sec.with_ads({"shares": 25_932_524_521, "currency": "USD", "pl": {"cols": ["Dec 2025"], "rows": {"Net Profit": [60000.0]}},
                      "balance": {"cols": ["Dec 2025"], "rows": {"Equity": [150000.0]}}}, 5)
    r = sec.ratios(p, 300.0)
    assert r["Market Cap"] == round(300 * 25_932_524_521 / 5 / 1e6, 1)
    assert r["Book Value"] == round(150000e6 / (25_932_524_521 / 5), 2)
    assert "five" in p["share_note"] and "per ordinary share" in p["share_note"]
    unknown = sec.with_ads({"shares": 10}, None)
    assert "ads_ratio" not in unknown and "couldn't be read" in unknown["share_note"]
    nums = deepdive.numbers({**build("azn"), "share_note": p["share_note"]})
    assert p["share_note"] in nums["notes"]


def test_price_symbols_for_share_classes_and_preferred_series():
    assert sec.price_symbol("BRK.B") == sec.price_symbol("BRK/B") == "BRK-B"
    assert sec.price_symbol("BAC.PRL") == sec.price_symbol("BAC/PL") == sec.price_symbol("BAC-PRL") == "BAC-PL"
    assert sec.price_symbol("AAPL") == "AAPL"
    assert sec.non_common("BAC/PL") and not sec.non_common("BRK/B")
