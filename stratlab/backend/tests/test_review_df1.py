"""A harsh audit of the Invest data pages (DF-001 to DF-023): ETF prices against their NAV, business updates, named
holders in India and the US, the margin funding calculator, stock lending and the Invest home. The figures come from
the real files the audit checked against (tests/fixtures/*/df1/: the exchange's bhavcopy, the industry body's NAV
files, shareholding XBRLs, SEC covers, company filings), trimmed to the rows the tests read."""
import csv
import gzip
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app import main  # noqa: F401,I001  (first: the app loads the newsletter job before the modules built on it)
from app import db, etf_nav as E, exchange_days, money_mf_nav
from tests import world

FIX = Path(__file__).parent / "fixtures"
ETF = FIX / "etf" / "df1"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()
    E.forget()
    for m in (B, S, R):                  # the other modules' copies in memory, so nothing reaches the next test
        m.forget()


# ---------- the real files ----------
def bhav_rows() -> dict[str, dict[str, float]]:
    """{day: {symbol: official close}} from the exchange's cash bhavcopies of 5 to 23 Oct 2026 (ETF rows only)."""
    out: dict[str, dict[str, float]] = {}
    for r in csv.DictReader(io.StringIO((ETF / "bhavcopy_etf_rows_2026-10-05_to_23.csv").read_text())):
        out.setdefault(r["TradDt"], {})[r["TckrSymb"]] = float(r["ClsPric"])
    return out


def nav_history() -> dict[str, dict[str, float]]:
    """{isin: {day: NAV}} from the industry body's NAV history report."""
    out: dict[str, dict[str, float]] = {}
    for line in (ETF / "nav_history_2026-10-05_to_23.txt").read_text().splitlines():
        f = line.split(";")
        if len(f) == 8 and f[0].isdigit():
            out.setdefault(f[4], {})[money_mf_nav._day(f[7])] = float(f[6])
    return out


def full_closes_23() -> dict[str, float]:
    """Every official close of 23 Oct 2026 (the whole bhavcopy's symbol, series and close columns)."""
    text = gzip.decompress((ETF / "bhavcopy_2026-10-23_close_columns.csv.gz").read_bytes()).decode()
    return {s: v["close"] for s, v in exchange_days.cash_rows(text).items()}


ISIN = {"MONQ50": "INF247L01AU3", "MASPTOP50": "INF769K01HP3", "MAFANG": "INF769K01HF4", "GROWWN200": "INF666M01JV1",
        "GSEC10ABSL": "INF209KC1142", "LIQUIDBEES": "INF732E01037", "GROWWLIQID": "INF666M01IP5", "LIQUIDPLUS": "INF769K01MY5"}
# the exchange list's last trade on 23 Oct 2026 (the audit's page: MASPTOP50's ₹97.15 against its ₹96.67 close)
LAST = {"MONQ50": 221.50, "MASPTOP50": 97.15, "MAFANG": 246.90, "GROWWN200": 10.54, "GSEC10ABSL": 109.93,
        "LIQUIDBEES": 1000.01, "GROWWLIQID": 111.33, "LIQUIDPLUS": 1109.37}


def seed(monkeypatch, official: dict | None = None, volumes: dict | None = None):
    """The stored days from the real files (each day's official close against that day's NAV), the exchange's list as
    read at 15:48 on 23 Oct, and the NAV file of the weekend (the liquid ETFs dated Sunday 25 Oct)."""
    closes, hist = bhav_rows(), nav_history()
    for day, rows in closes.items():
        db.set_setting(E.DAY_KEY + day, json.dumps({s: [c, hist.get(ISIN[s], {}).get(day), 1] for s, c in rows.items()}))
    live = {"as_of": "2026-10-23T15:48+05:30", "rows": {s: {"name": s, "isin": i, "price": LAST[s], "inav": None, "underlying": None,
                                                              "nav": None, "nav_date": None, "volume": (volumes or {}).get(s)}
                                                          for s, i in ISIN.items()}}
    db.set_setting(E.LIVE_KEY, E._pack(live, "2026-10-23T10:18:00+00:00"))
    data = money_mf_nav.parse((ETF / "NAVAll_2026-10-24.txt").read_text())
    monkeypatch.setattr(E, "navs", lambda: data)
    monkeypatch.setattr(E, "official_closes", lambda day: (official or {}) if day == "2026-10-23" else closes.get(day, {}))
    E.forget()
    return data


# ---------- DF-001 / DF-002 / DF-003: wide gaps shown, with the days counted ----------
def test_widest_gap_is_shown_not_dropped(w, monkeypatch):
    seed(monkeypatch)
    t = E.table()
    top = t["rows"][0]
    # MONQ50 closed at 220.17 against its NAV of 118.3705: 86% above, the widest, and first (DF-001)
    assert top["symbol"] == "MONQ50" and top["nav_gap"] == 86.0 and top["nav_wide"] and not top["nav_mismatch"]
    assert top["nav_price"] == 220.17 and top["nav_price_day"] == "2026-10-23"
    assert "shown and said to be that wide" in t["note"]


def test_thirty_day_range_keeps_the_wide_days(w, monkeypatch):
    seed(monkeypatch)
    by = {r["symbol"]: r for r in E.table()["rows"]}
    # the audit's own arithmetic on the same files: MASPTOP50's 14 days ran 45.9% to 65.6% above, 56.7% on average,
    # MAFANG's 42.0% to 62.5%, 53.2% (DF-002); the page read 2 days, 45.9% to 48.3%
    m = by["MASPTOP50"]["days"]
    assert m["days"] == 14 and m["stored"] == 14 and round(m["low"], 1) == 45.9 and round(m["high"], 1) == 65.6 and round(m["avg"], 1) == 56.7
    f = by["MAFANG"]["days"]
    assert f["days"] == 14 and round(f["low"], 1) == 42.0 and round(f["high"], 1) == 62.5 and round(f["avg"], 1) == 53.2
    assert by["MONQ50"]["days"]["days"] == 14 and by["MONQ50"]["days"]["low"] > 50


def test_a_nav_of_another_unit_is_left_out_and_said_so():
    assert E.mismatched(1000, 100) and E.gap(1000, 100) is None
    assert E.mismatched(10, 100) and E.gap(10, 100) is None
    assert not E.mismatched(220.17, 118.3705) and E.gap(220.17, 118.3705) == 86.0


# ---------- DF-004: a gap left out today is out of the range too ----------
def test_doubtful_day_is_left_out_of_the_range(w, monkeypatch):
    seed(monkeypatch)
    g = {r["symbol"]: r for r in E.table()["rows"]}["GROWWN200"]
    # the official close 11.16 against the last trade 10.54, with a NAV of 10.4795: the close is doubted
    assert g["nav_doubtful"] and g["nav_gap"] is None
    assert g["days"]["days"] == 13 and g["days"]["stored"] == 14 and g["days"]["high"] < 6.5
    d = E.detail("GROWWN200")
    last = d["history"][-1]
    assert last["day"] == "2026-10-23" and last["gap"] is None and last["doubtful"]
    assert d["days"]["days"] == 13


# ---------- DF-005: the last trade's own day ----------
def test_last_trade_day_is_the_real_one(w, monkeypatch):
    full = full_closes_23()
    assert "GSEC10ABSL" not in full and "MONQ50" in full and len(full) > 2000       # the real 23 Oct bhavcopy
    seed(monkeypatch, official=full)
    by = {r["symbol"]: r for r in E.table()["rows"]}
    # GSEC10ABSL last traded on 19 Oct (₹109.93) and isn't in the 23 Oct bhavcopy: never "Last trade · 23 Oct"
    assert by["GSEC10ABSL"]["price_day"] == "2026-10-19"
    assert by["MONQ50"]["price_day"] == "2026-10-23"


def test_close_recorded_as_no_trade_when_missing_from_the_bhavcopy(w, monkeypatch):
    full = full_closes_23()
    data = seed(monkeypatch, official=full)
    db.delete_setting(E.DAY_KEY + "2026-10-23")
    E.forget()
    E.record_close("2026-10-23", E.load_live(), data)
    stored = json.loads(db.get_setting(E.DAY_KEY + "2026-10-23"))
    assert stored["GSEC10ABSL"][0] is None and stored["GSEC10ABSL"][2] == 0
    assert stored["MONQ50"] == [220.17, 118.3705, 1]


# ---------- DF-006: no weekend NAV dates ----------
def test_liquid_etf_nav_is_the_trading_days(w, monkeypatch):
    data = seed(monkeypatch)
    hist = (ETF / "nav_history_2026-10-05_to_23.txt").read_text()
    monkeypatch.setattr(E, "history_text", lambda day: hist if day == "2026-10-23" else "")
    by = {r["symbol"]: r for r in E.table()["rows"]}
    # the daily file dates the liquid ETFs Sunday 25 Oct; before the history report is read they show "closed day"
    assert by["LIQUIDPLUS"]["nav_date"] == "2026-10-23"            # the NAV stored with the 23 Oct close
    assert E.fill_day_navs(data) == 3
    E.forget()
    by = {r["symbol"]: r for r in E.table()["rows"]}
    for s in ("LIQUIDBEES", "GROWWLIQID", "LIQUIDPLUS"):
        assert by[s]["nav_date"] == "2026-10-23" and not by[s]["nav_closed_day"]
    # the industry body's 23 Oct NAV, not the 25 Oct one (1109.3801)
    assert by["LIQUIDPLUS"]["nav"] == 1109.0434 and by["LIQUIDPLUS"]["nav_price_day"] == "2026-10-23"
    assert E.fill_day_navs(data) == 0                                 # read once


def test_weekend_nav_with_no_trading_day_nav_is_marked(w, monkeypatch):
    data = seed(monkeypatch)
    for day in bhav_rows():
        db.delete_setting(E.DAY_KEY + day)
    E.forget()
    row = E.load_live()["rows"]["GROWWLIQID"]
    sch = E.nav_of(row, data, "GROWWLIQID")
    assert sch["date"] == "2026-10-25" and sch["closed_day"]


# ---------- DF-007 / DF-008: what the note says ----------
def test_note_says_no_inav_and_explains_overseas_navs(w, monkeypatch):
    seed(monkeypatch)
    note = E.table()["note"]
    assert "indicative NAV" in note and "isn't shown" in note
    assert "overseas closing prices" in note


# ---------- business updates (DF-009 to DF-013) ----------
from app import biz_updates as B  # noqa: E402
from app.intel.filings import normalise  # noqa: E402

BIZ = FIX / "business_updates" / "df1"


def biz_pages(name: str) -> list[str]:
    """A real filing's pages as the PDF reader gives them back (tests/fixtures/business_updates/df1/<file>.txt)."""
    import re
    text = (BIZ / f"{name}.txt").read_text()
    return [p.strip() for p in re.split(r"\[\[page \d+\]\]", text) if p.strip()]


def biz_items(name: str) -> list[dict]:
    return normalise(json.loads((BIZ / name).read_text()))


def read(at: str, period: str, figures: list[dict], **kw) -> dict:
    return {"at": at, "title": kw.get("title", "update"), "url": f"https://nsearchives.nseindia.com/corporate/{at}.pdf", "read_at": at,
            "period": period, "span": "month", "problem": None, "reader": B.READER,
            "figures": [{"segment": None, "unit": "units", "basis": "month", "prior": None, "headline": False, "quote": "q", "page": 1,
                         "own": True, **f} for f in figures]}


def test_the_periods_own_column_is_read():
    # Mahindra's September 2026 report: the columns run Sep-25 Sep-26 (production), Sep-25 Sep-26 (sales), ... (DF-009)
    pages = biz_pages("MM_09102026164235_MonthlyReportSept2026.pdf")
    reply = {"period": "2026-09", "span": "month", "figures": [
        {"metric": "Total vehicle production", "value": 102092, "unit": "vehicles", "basis": "month", "headline": True,
         "quote": "102092 121722 97744 113705 4458 4081", "page": 2},
        {"metric": "Total sales", "value": 97744, "unit": "vehicles", "basis": "month", "quote": "102092 121722 97744 113705 4458 4081", "page": 2}]}
    period, _, figs = B.clean_figures(reply, pages, "2026-10-09T16:42")
    by = {f["metric"]: f for f in figs}
    assert period == "2026-09"
    assert (by["Total vehicle production"]["value"], by["Total vehicle production"]["prior"]) == (121722, 102092)
    assert (by["Total sales"]["value"], by["Total sales"]["prior"]) == (113705, 97744)
    # the headline is the company's sales, not its production (DF-009)
    reads = {"mm": {**read("2026-10-09T16:42", "2026-09", []), "figures": figs}}
    assert B.headline(B.series(reads))["metric"] == "Total sales"


def test_a_column_already_right_is_left_alone():
    pages = biz_pages("ATULAUTO_SalesPerformance_September2026.pdf")
    reply = {"period": "2026-09", "figures": [{"metric": "Total", "value": 3716, "unit": "units", "basis": "month", "prior": 2971,
                                               "headline": True, "quote": "Total 3,716 2,971 25.08% 18,660 14,367 29.88%", "page": 1}]}
    _, _, figs = B.clean_figures(reply, pages, "2026-10-01T12:00")
    assert (figs[0]["value"], figs[0]["prior"]) == (3716, 2971)
    assert B.header_periods(pages[0], "2026-09")[:2] == ["2026-09", "2025-09"]


def test_sales_stand_over_a_later_production_filing():
    # Maruti filed its sales at 12:59 and its production at 13:32 on 1 Oct 2026; the production filing, read last, put
    # 2,42,011 produced at the top of "Automakers' monthly sales" (DF-010)
    pages = biz_pages("MARUTI_01102026133208_Production_Oct2026.pdf")
    reply = {"period": "2026-09", "figures": [{"metric": "Grand Total (Passenger Vehicles + Light Commercial Vehicles)", "value": 242011,
                                               "unit": "units", "basis": "month", "prior": 201915, "headline": True,
                                               "quote": "Grand Total (Passenger Vehicles + Light Commercial Vehicles) 242,011 201,915", "page": 1}]}
    _, _, made = B.clean_figures(reply, pages, "2026-10-01T13:32", production=True)
    assert made[0]["metric"].startswith("Production: ")
    sales = read("2026-10-01T12:59", "2026-09", [{"metric": "Total Sales (Total Domestic + Export)", "value": 236013, "prior": 189665, "headline": True},
                                                 {"metric": "Total Domestic Sales including LCV (PV+LCV)", "value": 185252, "prior": 135711}])
    reads = {"sales": sales, "prod": {**read("2026-10-01T13:32", "2026-09", []), "figures": made}}
    h = B.headline(B.series(reads))
    assert h["latest"]["value"] == 236013 and h["change_year"] == 24.4
    # an item titled as production is read as one
    item = next(i for i in B.updates(biz_items("ann_MARUTI.json")) if "Production" in i["title"])
    assert B.PRODUCTION.search(item["title"]) and not B.SALES.search(item["title"])


def test_a_subsidiarys_filing_is_not_the_companys_own():
    vecv = " ".join(" ".join(biz_pages("EICHERMOT_VECVSept26salesUpdate.pdf")).split())
    re_ = " ".join(" ".join(biz_pages("EICHERMOT_MonthlyBusinessUpdate1stOctober2026.pdf")).split())
    atul = " ".join(" ".join(biz_pages("ATULAUTO_SalesPerformance_September2026.pdf")).split())
    mm = " ".join(" ".join(biz_pages("MM_09102026164235_MonthlyReportSept2026.pdf")).split())
    assert B.NOT_OWN.search(vecv)                         # "sales volume of VE Commercial Vehicles Limited, an unlisted subsidiary"
    assert not B.NOT_OWN.search(re_) and not B.NOT_OWN.search(atul) and not B.NOT_OWN.search(mm)
    # both filed on 1 Oct 2026, VECV's read after Royal Enfield's: the headline is Royal Enfield's 1,33,958 (DF-011)
    eicher = {"re": read("2026-10-01T12:20", "2026-09", [{"metric": "Total motorcycles", "value": 133958, "prior": 124328, "headline": True}]),
              "vecv": read("2026-10-01T12:23", "2026-09", [{"metric": "Total VECV (Inclusive of EVs)", "value": 11396, "headline": True, "own": False}])}
    assert B.headline(B.series(eicher))["latest"]["value"] == 133958


def test_the_newest_period_heads_even_when_named_another_way():
    # Atul Auto: May's total was marked the headline; June to September's totals came under another name (DF-012)
    reads = {"may": read("2026-06-01T13:23", "2026-05", [{"metric": "Total 3W", "value": 3236, "headline": True}]),
             "sep": read("2026-10-01T12:00", "2026-09", [{"metric": "3W - IC Engine", "value": 3308},
                                                         {"metric": "Total (Domestic + Export)", "value": 4192}])}
    h = B.headline(B.series(reads))
    assert h["latest"]["period"] == "2026-09" and h["latest"]["value"] == 4192


def test_quarterly_updates_are_recognised():
    titan = [i for i in biz_items("ann_TITAN.json") if B.is_update(i)]
    dmart = [i for i in biz_items("ann_DMART.json") if B.is_update(i)]
    assert [i["subject"] for i in titan] == ["Updates"] and "Q2update" in titan[0]["url"]     # "Quarterly Update Q2 FY 2026-27" (DF-012)
    assert len(dmart) == 1 and "QuarterUpdate" in dmart[0]["url"]                              # "Company Update at the end of Quarter 2"
    assert not B.is_update({**titan[0], "text": "Titan Company Limited has informed the Exchange regarding 'Redemption of Commercial Paper'."})
    # a quarter's update in money and stores counts as one when it's opened to check
    assert B.SALES_TEXT.search("\n".join(biz_pages("DMART_03102026122118_ASLQuarterUpdateSep2026.pdf")))


def test_reads_by_an_older_reader_are_read_again(w, monkeypatch):
    items = biz_items("ann_ATULAUTO.json")
    ups = [u for u in B.candidates(items)]
    old = {u["id"]: {**read(u["at"], "2026-05", [{"metric": "Total 3W", "value": 1}]), "reader": 1} for u in ups}
    db.set_setting(B.KEY + "ATULAUTO", json.dumps({"reads": old}))
    B.forget()
    seen = []
    monkeypatch.setattr(B, "read_one", lambda sym, item, d, ai, known: seen.append(item["id"]) or read(item["at"], "2026-09", [{"metric": "Total", "value": 2}]))
    monkeypatch.setattr(B, "_ai_budget", lambda: True)
    got = B.read_new("ATULAUTO", items, None, None, limit=2)
    assert got["read"] == 2 and seen == [u["id"] for u in ups[:2]]
    seen.clear()
    B.read_new("ATULAUTO", items, None, None, limit=2)
    assert seen and seen[0] == ups[2]["id"]                      # the re-read ones aren't read a third time


def test_sector_lists_only_what_is_filed():
    assert "cement" not in B.SECTORS and "telecom" not in B.SECTORS               # nothing was ever filed to read (DF-013)
    assert {s for s, _ in B.SECTORS["airlines"]["symbols"]} == {"ADANIPORTS", "GMRAIRPORT"}
    assert "sales" not in B.SECTORS["power"]["label"].lower()


# ---------- named holders (DF-016 to DF-019) ----------
from app import shareholders as S  # noqa: E402

SHP = FIX / "shareholding" / "df1"


def shp(sym: str) -> dict:
    return S.parse_xbrl(gzip.decompress((SHP / f"{sym}_2026-09-30.xml.gz").read_bytes()))


def seed_lic():
    """Each company's quarter to 30 Jun 2026 as the page had it (its answer's "was" figures), and the quarter to 30 Sep
    2026 read from the company's real filing."""
    ans = json.loads((SHP / "lic_holdings_answer_2026-10-24.json").read_text())
    for r in ans["rows"]:
        if r["symbol"] == "AARTIIND":
            continue
        prev = {"name": r["company"], "isin": "", "holders": [{"name": r["names"][0], "kind": r["kind"], "group": r["group"],
                                                                "shares": r["prev_shares"], "pct": r["prev_pct"]}]}
        S.store(r["symbol"], {"quarter": "2026-06-30", "rec": "jun", "url": "https://nsearchives.nseindia.com/a.xml", "filed": "2026-07-20T10:00", "name": r["company"]}, prev)
        S.store(r["symbol"], {"quarter": "2026-09-30", "rec": "sep", "url": "https://nsearchives.nseindia.com/b.xml", "filed": "2026-10-20T10:00", "name": r["company"]}, shp(r["symbol"]))
    S.forget()
    return ans


def test_a_single_holder_flagged_category_is_read():
    # Hero MotoCorp filed LIC's 12,089,068 shares (6.04%) as a "Category" row with one shareholder (DF-016)
    by = {h["name"]: h for h in shp("HEROMOTOCO")["holders"]}
    assert by["LIFE INSURANCE CORPORATION OF INDIA"]["pct"] == 6.04 and by["LIFE INSURANCE CORPORATION OF INDIA"]["shares"] == 12089068
    names = {h["name"].upper() for h in shp("AMBUJACEM")["holders"]}
    assert "FOREIGN INSTITUTIONAL INVESTORS" not in names                       # a category's total stays out


def test_one_holder_under_its_filed_names():
    for name in ("LICI ULIP-GROWTH FUND", "LIC I New Pension Plus Growth Fund", "Life Insurance Corpn Of India",
                 "LIFE INSURANCE CORPORATION OF INDIA - P & GS Fund", "LIFE INSURANCE CORPORATION OF INDIA - ULIF004200910LICEND+GRW512",
                 "Life Insurance Corporation Of India with Sub Accounts", "LIFE INSURANCE CORPORATION OF INDIA ASM NON PAR",
                 "Life Insurance Corporation of India, LIC-P&GS Fund, LICI Funds", "LIFE INSURANCE CORPORATION OF INDIA LIMITED",
                 "LIFE INSURANCE CORPORATION OF INDIA (including other LIC funds consolidated based on PAN)",
                 "LIFE INSURANCE CORPORATION OF INDIA and LIFE INSURANCE CORPORATE OF INDIA P AND GS Fund"):
        assert S.entity(S.norm(name)) == "LIFE INSURANCE CORPORATION OF INDIA", name
    for other in ("LIC MUTUAL FUND", "LIC HOUSING FINANCE LIMITED", "NPS TRUST A/C LIC PENSION FUND SCHEME", "HDFC LIFE INSURANCE COMPANY LIMITED"):
        assert S.entity(S.norm(other)) != "LIFE INSURANCE CORPORATION OF INDIA", other


def test_renamed_holder_is_not_below_one_percent_or_out(w):
    seed_lic()
    h = S.holdings(["LIFE INSURANCE CORPORATION OF INDIA"])
    by = {r["symbol"]: r for r in h["rows"]}
    # the audit's examples: Ambuja's LICI ULIP-GROWTH FUND at 7.28%, unchanged; HUL 6.44%; PNB 9.38%; Tata Power 5.72%;
    # Hero 6.04%, up from 5.14%
    assert (by["AMBUJACEM"]["pct"], by["AMBUJACEM"]["change"], by["AMBUJACEM"]["renamed"]) == (7.28, "same", True)
    assert by["AMBUJACEM"]["names"] == ["LICI ULIP-GROWTH FUND"] and by["AMBUJACEM"]["prev_names"] == ["Life Insurance Corporation Of India"]
    assert by["HINDUNILVR"]["pct"] == 6.44 and by["PNB"]["pct"] == 9.38 and by["TATAPOWER"]["pct"] == 5.72
    assert (by["HEROMOTOCO"]["pct"], by["HEROMOTOCO"]["prev_pct"], by["HEROMOTOCO"]["change"]) == (6.04, 5.14, "up")
    assert by["COFORGE"]["change"] != "dropped"
    # Apollo Hospitals' filing names no LIC fund at all: that one is a true drop
    assert by["APOLLOHOSP"]["change"] == "dropped" and h["dropped"] == 1


def test_company_page_keeps_a_renamed_holder(w):
    seed_lic()
    v = S.company_view("AMBUJACEM")
    lic = next(x for x in v["holders"] if x["name"] == "LICI ULIP-GROWTH FUND")
    assert lic["change"] == "same" and lic["was_named"] == "Life Insurance Corporation Of India"
    assert not any("Life Insurance" in d["name"] for d in v["dropped"])


def test_follow_message_says_nothing_of_a_rename(w, monkeypatch):
    seed_lic()
    S.follow("u-basic", "LIC", ["LIFE INSURANCE CORPORATION OF INDIA"])
    co = S.company("AMBUJACEM")["q"]
    assert S.follow_changes("AMBUJACEM", "Ambuja Cements", co["2026-06-30"], co["2026-09-30"], "2026-09-30") == {}


def test_search_puts_lic_first_with_its_spellings(w):
    seed_lic()
    S.store("ABSL", {"quarter": "2026-09-30", "rec": "r", "url": "u", "filed": "2026-10-20T10:00", "name": "X"},
            {"name": "X", "isin": "", "holders": [{"name": "ADITYA BIRLA SUN LIFE INSURANCE COMPANY LIMITED", "kind": "Insurance company",
                                                   "group": "public", "shares": 1, "pct": 1.2}]})
    S.forget()
    g = S.search("Life Insurance")
    assert g[0]["label"].upper().startswith("LIFE INSURANCE CORPORATION OF INDIA")      # the best fit and the biggest first (DF-017)
    names = {n["name"] for n in g[0]["names"]}
    assert {"LICI ULIP-GROWTH FUND", "LIFE INSURANCE CORPORATION OF INDIA"} <= names                # every spelling, one group
    assert not any("LIFE INSURANCE CORPORATION" in x["label"].upper() for x in g[1:])
    assert g[0]["companies"] >= 7


def test_popular_holders_offered_before_typing(w, monkeypatch):
    seed_lic()
    c = w["client"]
    from tests.fake_db import headers
    monkeypatch.setattr(S, "_allowed", lambda p: True)
    body = c.get("/invest/holders", headers=headers("basic-token")).json()
    assert body["popular"] and body["popular"][0]["label"].upper().startswith("LIFE INSURANCE CORPORATION OF INDIA")


def test_quarters_read_by_an_older_parser_are_read_again(w):
    ans = seed_lic()
    raw = json.loads(db.get_setting(S.KEY + "HEROMOTOCO"))
    for q in raw["q"].values():
        q.pop("parser", None)
    db.set_setting(S.KEY + "HEROMOTOCO", json.dumps(raw))
    st = {"backfilled": True, "queue": []}
    assert S.requeue_old(st) == 2 and {x[0] for x in st["queue"]} == {"HEROMOTOCO"}
    assert ans


# ---------- US holders above 5% (DF-018) ----------
from app import redflags as R, us_holders as U  # noqa: E402
from app.intel.sec import html_text  # noqa: E402

US = FIX / "us_holders" / "df1"


def cover(name: str) -> dict:
    return U.read_cover(html_text(gzip.decompress((US / f"{name}.html.gz").read_bytes()).decode()))


def us_item(sym: str, acc: str, at: str, read: dict | None) -> dict:
    return {"id": f"{sym}|{acc}", "symbol": sym, "company": sym, "at": at, "form": "SCHEDULE 13G/A", "kind": "13G", "amendment": True,
            "label": "x", "url": f"https://www.sec.gov/Archives/edgar/data/1/{acc.replace('-', '')}/primary_doc.xml",
            "holder": None, "pct": None, "shares": None, "read": False, **({**read, "read": True} if read else {})}


def test_us_holders_can_be_found_by_holder_and_stay_in_date_order(w):
    # three real covers read (Reddit's Baillie Gifford, Lilly's endowment, Yum's JPMorgan), one filing unread between them
    rows = [us_item("RDDT", "0001088875-26-000071", "2026-10-21", cover("sec_RDDT_0001088875-26-000071")),
            us_item("LLY", "0000316011-26-000036", "2026-10-19", cover("sec_LLY_0000316011-26-000036")),
            us_item("TT", "0000000000-26-000001", "2026-10-17", None),
            us_item("YUM", "0000019617-26-000388", "2026-10-16", cover("sec_YUM_0000019617-26-000388"))]
    R.holds.add("US", rows)
    today = date(2026, 10, 23)
    every = R.holders_listing(today=today)
    assert [i["symbol"] for i in every["items"]] == ["RDDT", "LLY", "TT", "YUM"]           # by date, read or not
    assert every["newest"] == "2026-10-21" and every["unread"] == 1
    got = R.holders_listing(holder="baillie", today=today)
    assert [i["symbol"] for i in got["items"]] == ["RDDT"] and got["items"][0]["pct"] == 4.9 and got["holder"] == "baillie"
    assert got["unread"] == 1                                                              # said: one filing can't be matched yet
    assert [i["symbol"] for i in R.holders_listing(holder="jpmorgan chase", today=today)["items"]] == ["YUM"]
    assert R.holders_listing(holder="vanguard", today=today)["total"] == 0                 # a holder, never a company called that
    assert R.holder_matches("lilly endow", "LILLY ENDOWMENT, INC.") and not R.holder_matches("black rock", "BlackRock, Inc.")


def test_us_holder_search_is_a_paid_cross_company_view(w):
    from tests.fake_db import headers
    c = w["client"]
    assert c.get("/research/holders-us?symbol=AAPL&holder=vanguard", headers=headers("free-token")).status_code == 402
    r = c.get("/research/holders-us?holder=vanguard", headers=headers("basic-token"))
    assert r.status_code == 200 and r.json()["holder"] == "vanguard" and r.json()["covers"]
    assert R.COVER_READS >= 300


# ---------- stock lending across the market (DF-022) ----------
from app import slb  # noqa: E402


def test_lending_across_the_market_from_the_real_file():
    day, lines = slb.bhav_rows((FIX / "stock_desks" / "df1_SLBM_BC_23102026.DAT").read_text())
    closes = full_closes_23()
    rows = {s: {"p": closes.get(s), "l": ls, "a": [slb.annualised(slb.avg_fee(ln), closes.get(s), day, ln[1]) for ln in ls]} for s, ls in lines.items()}
    m = slb.market((day, {"rows": rows}))
    assert day == "2026-10-23" and m["day"] == day and m["stocks"] == len([s for s, ls in lines.items() if sum(ln[6] for ln in ls)])
    by = {r["symbol"]: r for r in m["rows"]}
    # ADANIPORTS: 223 shares lent for ₹111.50 in 4 trades, at ₹0.50 a share
    assert (by["ADANIPORTS"]["shares"], by["ADANIPORTS"]["fee_paid"], by["ADANIPORTS"]["trades"]) == (223, 111.5, 4)
    assert by["ADANIPORTS"]["ann"] == slb.annualised(0.5, closes["ADANIPORTS"], day, "2026-12-01")
    assert [r["shares"] for r in m["rows"]] == sorted((r["shares"] for r in m["rows"]), reverse=True)
