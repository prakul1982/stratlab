"""DATA lane (4 Nov): the four findings the monthly company audit left open after SECMEM.

- JSPR, NCEL, SCNI (US): a line named like revenue that isn't sales (a milestone or lease figure from a note, an oil-and-gas
  disclosure, a broker's trading line) was read as revenue, or kept a year without sales from being one. The income statement's
  own arithmetic now decides: an operating result of exactly the operating costs earned nothing, whatever the notes tag.
- BSE:532621 (Morarjee Textiles): the audit read its few recent BSE sessions as a share "listed recently", though its company
  page is its NSE listing (MORARJEE-BZ), traded all year; and a share whose listing is years old but whose prices on record start
  within the year lost the start date of its range.
Fixtures are shaped like each company's SEC company facts (values as filed); no live source is called."""
from datetime import timedelta

import pytest

from app import audit, deepdive
from app.intel import sec
from tests import world as W


def _row(v, y, accn, start=None, form="10-K"):
    return {"start": start or f"{y}-01-01", "end": f"{y}-12-31", "val": v, "form": form, "filed": f"{y + 1}-03-01", "accn": accn,
            "fy": y, "fp": "FY"}


def _facts(years: dict, form: str = "10-K") -> dict:
    """{year: {concept: value}} -> the companyfacts shape, each year from its own annual report."""
    out: dict = {}
    for y, concepts in years.items():
        for c, v in concepts.items():
            out.setdefault(c, {"units": {"USD": []}})["units"]["USD"].append(_row(v, y, f"0001-{y + 1}-000001", form=form))
    return {"cik": 1, "entityName": "X", "facts": {"us-gaap": out}}


def _sales(p, year):
    rows = p["pl"]["rows"]
    return (rows.get("Sales") or rows.get("Revenue"))[p["pl"]["cols"].index(year)]


# JSPR (10-K): a $9 m milestone (2021, 2023) and $8.3 m of "sales-type lease revenue" (2024) from the notes, a cost of revenue
# tagged in 2025; every year's operating loss is exactly its operating expenses
JSPR = {2021: {"RevenueRecognitionMilestoneMethodRevenueRecognized": 9_000_000, "OperatingExpenses": 36_833_000,
               "OperatingIncomeLoss": -36_833_000, "NetIncomeLoss": -30_637_000},
        2022: {"OperatingExpenses": 51_196_000, "OperatingIncomeLoss": -51_196_000, "NetIncomeLoss": -37_685_000},
        2023: {"RevenueRecognitionMilestoneMethodRevenueRecognized": 9_000_000, "OperatingExpenses": 68_861_000,
               "OperatingIncomeLoss": -68_861_000, "NetIncomeLoss": -64_465_000},
        2024: {"SalesTypeLeaseRevenue": 8_300_000, "OperatingExpenses": 76_239_000, "OperatingIncomeLoss": -76_239_000,
               "NetIncomeLoss": -71_269_000},
        2025: {"CostOfRevenue": 41_635_000, "OperatingExpenses": 83_883_000, "OperatingIncomeLoss": -83_883_000,
               "NetIncomeLoss": -75_801_000}}
# NCEL (20-F under US GAAP): an oil-and-gas results-of-operations line of $18.5 m in 2021 and 2022 beside losses of its costs
NCEL = {2020: {"OperatingExpenses": 2_299_370, "OperatingIncomeLoss": -2_299_370, "NetIncomeLoss": -2_861_435},
        2021: {"ResultsOfOperationsSalesOrTransfersToEntitysOtherOperations": 18_500_000, "OperatingExpenses": 11_860_621,
               "OperatingIncomeLoss": -11_860_621, "NetIncomeLoss": -11_946_078},
        2022: {"ResultsOfOperationsSalesOrTransfersToEntitysOtherOperations": 18_500_000, "OperatingExpenses": 15_482_364,
               "OperatingIncomeLoss": -15_482_364, "NetIncomeLoss": -16_495_680},
        2023: {"OperatingExpenses": 11_807_063, "OperatingIncomeLoss": -11_807_063, "NetIncomeLoss": -12_172_029}}
# SCNI (20-F): 2023 tags a broker's "principal transactions revenue" of $25.6 m and its operating loss without the minus sign;
# its first sales come in 2024
SCNI = {2022: {"OperatingExpenses": 11_061_000, "OperatingIncomeLoss": -11_061_000, "NetIncomeLoss": -5_796_000},
        2023: {"PrincipalTransactionsRevenue": 25_596_000, "OperatingExpenses": 9_706_000, "OperatingIncomeLoss": 9_706_000,
               "NetIncomeLoss": -6_500_000},
        2024: {"Revenues": 658_000, "CostOfRevenue": 1_238_000, "GrossProfit": -580_000, "OperatingExpenses": 8_058_000,
               "OperatingIncomeLoss": -8_638_000, "NetIncomeLoss": 4_796_000}}


@pytest.mark.parametrize("sym,years,form,none,sold", [
    ("JSPR", JSPR, "10-K", ["Dec 2021", "Dec 2022", "Dec 2023", "Dec 2024", "Dec 2025"], {}),
    ("NCEL", NCEL, "20-F", ["Dec 2020", "Dec 2021", "Dec 2022", "Dec 2023"], {}),
    ("SCNI", SCNI, "20-F", ["Dec 2022", "Dec 2023"], {"Dec 2024": 0.66}),
])
def test_a_line_named_revenue_beside_a_loss_of_exactly_the_costs_is_not_sales(sym, years, form, none, sold):
    """The audit's "Revenue or profit missing" (1 Nov) for JSPR 2021/2023/2024, NCEL 2021-22 and SCNI 2023: years without sales."""
    p = sec.build(_facts(years, form), None, symbol=sym)
    assert p["no_revenue"] == none and p["sales_untagged"] == []
    for y in none:
        assert _sales(p, y) is None, y
    for y, v in sold.items():
        assert _sales(p, y) == pytest.approx(v, abs=0.01)
    found = audit.check_numbers({**p, "region": "US"}, deepdive.numbers(p), {})
    assert not [i for i in found if i["level"] == "gap" and i["area"] == "Numbers"], found
    assert not [i for i in found if "labels that line in its own way" in i["detail"]]


# every revenue line the reader takes, on its own as a company's only one
ONLY_LINES = [c for c in sec.TOP_LINE + sec.REVENUE_ELSE]


@pytest.mark.parametrize("concept", ONLY_LINES)
def test_every_revenue_line_gives_way_to_the_statements_arithmetic_and_stands_when_it_adds_up(concept):
    """The rule holds for every line the reader takes, and for annual and quarterly figures alike: beside an operating result of
    exactly minus the operating costs (or the costs filed without the sign) it is a note's figure; beside an operating result
    that is the sales less the costs it is the revenue, as before."""
    for op in (-40_000_000, 40_000_000):
        p = sec.build(_facts({2024: {concept: 12_000_000, "OperatingExpenses": 40_000_000, "OperatingIncomeLoss": op,
                                     "NetIncomeLoss": -39_000_000}}), None, symbol="X")
        assert _sales(p, "Dec 2024") is None and p["no_revenue"] == ["Dec 2024"], (concept, op)
    p = sec.build(_facts({2024: {concept: 12_000_000, "OperatingExpenses": 40_000_000, "OperatingIncomeLoss": -28_000_000,
                                 "NetIncomeLoss": -27_000_000}}), None, symbol="X")
    assert _sales(p, "Dec 2024") == pytest.approx(12.0) and p["no_revenue"] == [], concept
    # the quarter's figure follows the same arithmetic
    q = {"start": "2024-10-01", "end": "2024-12-31", "form": "10-Q", "filed": "2025-02-01", "accn": "0001-25-000009"}
    facts = {"us-gaap": {concept: {"units": {"USD": [{**q, "val": 3_000_000}]}},
                         "OperatingExpenses": {"units": {"USD": [{**q, "val": 10_000_000}]}},
                         "OperatingIncomeLoss": {"units": {"USD": [{**q, "val": -10_000_000}]}}}}
    assert "2024-12-31" not in sec.revenue(facts, "quarter")
    facts["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"][0]["val"] = -7_000_000
    assert sec.revenue(facts, "quarter")["2024-12-31"] == 3_000_000


def test_a_nil_revenue_stays_nil_and_a_negative_narrower_line_is_not_sales():
    """A revenue of nothing beside a loss of the costs is still the right figure (nil, not unknown); a grant line below nil
    (SCNI's IFRS years: grants netted off research costs) is a deduction, never revenue."""
    p = sec.build(_facts({2024: {"Revenues": 0, "OperatingExpenses": 5_000_000, "OperatingIncomeLoss": -5_000_000,
                                 "NetIncomeLoss": -5_000_000}}), None, symbol="X")
    assert _sales(p, "Dec 2024") == 0
    rev = sec.revenue(_facts({2017: {"RevenueFromGovernmentGrants": -2_971_000, "NetIncomeLoss": -9_000_000}})["facts"], "annual")
    assert "2017-12-31" not in rev
    rev = sec.revenue(_facts({2017: {"RevenueFromGovernmentGrants": -2_971_000, "LicensesRevenue": 400_000}})["facts"], "annual")
    assert rev["2017-12-31"] == 400_000                          # the next line with a figure of sales


# ---------- BSE:532621: a share's prices on record, from the listing its page shows ----------
def test_a_bse_code_whose_company_nse_lists_is_judged_on_its_nse_listings_prices(monkeypatch):
    """The audit read BSE:532621's few BSE sessions (first one within 60 days) as "Listed recently" and then held its page, the
    NSE listing traded all year, to a since-listing range. Every BSE code with an NSE twin is priced as its page is; a code of a
    company only BSE lists keeps its own listing."""
    from app import main
    twins = {"532621": "MORARJEE", "500325": "RELIANCE"}
    monkeypatch.setattr(main, "nse_twin_of", lambda code: twins.get(code))
    asked = []
    monkeypatch.setattr(main.universes, "resolve", lambda reg, m, members: asked.append(members[0]["symbol"]) or ([], ["x"]))
    for sym in ("532621", "BSE:532621", "500325", "BSE:543210", "543210", "TCS"):
        main.price_status(sym)
    assert asked == ["MORARJEE", "MORARJEE", "RELIANCE", "BSE:543210", "543210", "TCS"]
    # a twin map that can't be read leaves the code as it is
    monkeypatch.setattr(main, "nse_twin_of", lambda code: (_ for _ in ()).throw(RuntimeError("offline")))
    asked.clear()
    main.price_status("532621")
    assert asked == ["532621"]


def test_an_old_share_whose_prices_on_record_start_this_year_keeps_that_start_date(monkeypatch):
    """A share listed years ago (its listing's first trade in 2007) whose candles start weeks ago (suspended, then trading again):
    its range is marked as covering the prices on record from its first candle, never left as a full year's with no date."""
    from app import main
    from app.intel.company import ist_date
    w = W.build(monkeypatch)
    try:
        hub = main.research_hub
        first = (ist_date() - timedelta(days=20)).isoformat()
        bars = [{"t": f"{(ist_date() - timedelta(days=d)).isoformat()}T00:00:00+05:30", "o": 10, "h": 11, "l": 9, "c": 10, "v": 100}
                for d in range(20, 0, -1)]
        monkeypatch.setattr(hub.kite, "history", lambda *a, **k: bars)
        for listed, want in (("2007-12-03", first), (None, None)):
            monkeypatch.setattr(hub.yahoo, "meta", lambda s, ft=listed: {"name": "Reliance", "currency": "INR", "first_trade": ft})
            rng = hub._company_in("RELIANCE", lean=True)["range52"]
            if want:
                assert rng.get("traded_from") == want and "since" not in rng, rng
                got = audit.check_listing({"range52": rng, "quote": {"price": 10}}, {"region": "IN", "ratios": {}}, {"years": []}, {})
                assert [i["level"] for i in got] == ["fact"] and f"Prices on record only from {first}" in got[0]["detail"]
            else:                                            # no first trade known: the first candle is all there is to go by
                assert rng.get("since") == first, rng
        # a first trade within the year, before the candles: that day, as before (SECMEM 6)
        within = (ist_date() - timedelta(days=100)).isoformat()
        monkeypatch.setattr(hub.yahoo, "meta", lambda s: {"name": "Reliance", "currency": "INR", "first_trade": within})
        assert hub._company_in("RELIANCE", lean=True)["range52"].get("traded_from") == within
    finally:
        w["close"]()


def test_a_bse_code_shown_as_its_nse_listing_falls_back_to_the_code_for_its_numbers(monkeypatch):
    """532621 opened as MORARJEE-BZ with no financials: the fundamentals source knows the company only by its BSE code. Any page
    opened by a BSE code and shown as its NSE twin reads the numbers under the code when the NSE symbol has none."""
    from app import main
    from app.intel.net import SourceError
    w = W.build(monkeypatch)
    try:
        hub = main.research_hub
        real = hub.screener.company
        asked = []

        def company(sym):
            asked.append(sym)
            if sym == "RELIANCE":
                raise SourceError("Screener.in", "the fundamentals source has nothing for that.")
            return real("RELIANCE")
        monkeypatch.setattr(hub.screener, "company", company)
        c = hub._company_in("500325", lean=True)
        assert c["symbol"] == "RELIANCE" and asked == ["RELIANCE", "500325"]
        assert all(s["ok"] for s in c["sources"] if s["source"] == "Fundamentals"), c["sources"]
        asked.clear()
        with pytest.raises(Exception):
            hub._fundamentals("RELIANCE")                     # opened by its NSE symbol: no code to fall back to
        assert asked == ["RELIANCE"]
    finally:
        w["close"]()
