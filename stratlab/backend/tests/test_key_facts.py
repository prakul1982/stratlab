"""The plain-number rows next to a company's AI read: worked out from reported results and prices, never scored."""
from datetime import date, timedelta

from app.intel import key_facts as K

COLS = ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "TTM"]
REPORTED = {
    "pl": {"cols": COLS, "rows": {
        "Sales": [100, 110, 125, 140, 160, 165], "OPM %": [18, 19, 21, 20, 22, 22],
        "Interest": [5, 5, 6, 6, 8, 8], "Profit before tax": [20, 22, 26, 30, 32, 33], "Net Profit": [15, 16, 19, 22, 24, 25]}},
    "balance": {"cols": COLS[:-1], "rows": {"Equity Capital": [10] * 5, "Reserves": [90, 100, 110, 120, 140],
                                            "Borrowings": [40, 40, 45, 50, 60]}},
    "cashflow": {"cols": COLS[:-1], "rows": {"Cash from Operating Activity": [14, 18, 20, 24, 26]}},
    "ratios": {"ROCE": "19.5", "ROE": "16.2"},
}


def bars(closes: list[float]) -> list[dict]:
    start = date(2025, 1, 1)
    return [{"t": (start + timedelta(days=i * 365 / 250)).isoformat(), "o": c, "h": c, "l": c, "c": c} for i, c in enumerate(closes)]


def rows(out):
    return {r["id"]: {i["label"]: i["text"] for i in r["items"]} for r in out}


def test_rows_from_reported_numbers_and_prices():
    rising = [100 + i * 0.5 for i in range(260)]
    got = rows(K.build({"metrics": []}, REPORTED, bars(rising)))
    assert got["growth"]["Sales, 3 years"] == "13.3% a year" and got["growth"]["Net profit, 3 years"] == "14.5% a year"
    assert got["price"]["Price vs 50-day average"].endswith("above") and got["price"]["Price vs 200-day average"].endswith("above")
    assert got["price"]["1-year price change"].startswith("+") and got["price"]["Stage (150-day average)"] == "Stage 2 (advancing)"
    assert got["debt"]["Debt to equity"] == "0.40" and got["debt"]["Interest cover"] == "5.0x"
    assert got["debt"]["Cash from operations"] == "106% of net profit over 5 years"
    assert got["margins"]["EBITDA margin, 5 years"] == "18% → 19% → 21% → 20% → 22% (Mar 2021 to Mar 2025)"
    assert got["margins"]["ROCE"] == "19.5%" and got["margins"]["ROE"] == "16.2%"


def test_missing_sources_leave_lines_out_and_nothing_is_a_score():
    c = {"metrics": [{"title": "Growth", "items": [{"label": "Revenue 3Y", "value": 12.0, "unit": "%±"}]},
                     {"title": "Financial health", "items": [{"label": "Interest coverage", "value": 9.25, "unit": "x"}]}]}
    got = rows(K.build(c, None, [{"t": "2026-01-01", "c": 5}]))   # too few candles for any price line
    assert got == {"growth": {"Sales, 3 years": "12.0% a year"}, "debt": {"Interest cover": "9.2x"}}
    assert K.build({}, None, None) == []
    falling = [200 - i * 0.5 for i in range(260)]
    price = rows(K.build({}, None, bars(falling)))["price"]
    assert price["Price vs 200-day average"].endswith("below") and price["1-year price change"].startswith("-")


def test_banks_have_no_debt_or_margin_lines():
    bank = {**REPORTED, "pl": {"cols": COLS, "rows": {**REPORTED["pl"]["rows"], "Financing Margin %": [1] * 6}}}
    got = rows(K.build({}, bank, None))
    assert "debt" not in got and "EBITDA margin, 5 years" not in got.get("margins", {})
