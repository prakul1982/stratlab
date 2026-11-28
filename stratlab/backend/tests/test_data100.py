"""Lane data100 (27 Nov 2026): company data wrong at the source of every page and deck, found by the deck audits (deck96, deck99, fix98).

1. A subsidiary filing its annual report in its parent's combined report (Connecticut Light & Power and NSTAR Electric in Eversource's) was
   built from the parent's figures and cover: Eversource's $13.5 bn revenue, and a preferred share's price times Eversource's 375 million
   shares as its market value. Two tickers of one SEC registrant (Black Hills, renamed Bright Horizon Energy: BKH and HZN) were merged "by
   description" under the old one.
2. OneConstruction's 20-F tags −84 a share for −0.84: the count the earnings imply (157,274 shares) replaced its 16 million, a $0.19 m market
   value beside $49 m of revenue. No figure is built on a share count every count of the accounts puts far apart.
3. SpiceJet and Tata Elxsi: theme pieces kept from pages built before they had a year of revenue were never taken again.
4. A renamed US ticker (PSKY, now SKYD) was a 404 on its company page, a dead watchlist row and nothing in search.

The data is shaped like the real cases (Eversource's 2025 10-K, OneConstruction's 2026 20-F) but small and made here: nothing is read from
the network."""
import json

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the modules the others are built on)
from app import stock_pages
from app.intel import sec

ES, CLP, NST = 72741, 23426, 13372
ANNUAL = ("0001628280-26-008461", "2026-02-17")
QUARTER = ("0001628280-26-071541", "2026-11-06")

NS = ('xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
      'xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:dei="http://xbrl.sec.gov/dei/2025" '
      'xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:es="http://www.eversource.com/20251231"')
CLP_M, NST_M = "es:TheConnecticutLightAndPowerCompanyMember", "es:NstarElectricCompanyMember"
M = 1_000_000


def _ctx(cid, start, end, member=None):
    seg = (f'<xbrli:segment><xbrldi:explicitMember dimension="dei:LegalEntityAxis">{member}</xbrldi:explicitMember></xbrli:segment>'
           if member else "")
    per = f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>" if start else f"<xbrli:instant>{end}</xbrli:instant>"
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000072741</xbrli:identifier>{seg}'
            f"</xbrli:entity><xbrli:period>{per}</xbrli:period></xbrli:context>")


def combined_report(quarter=False) -> str:
    """Eversource's combined report as its XBRL gives it: Eversource's figures plain, each subsidiary registrant's under LegalEntityAxis,
    each cover's SEC number, shares and (Eversource's only) trading symbol."""
    figs = {"": (13547, 1692, 375_496_611), CLP_M: (5241, 551, 6_035_205), NST_M: (3987, 631, 200)}
    if quarter:
        figs = {"": (3600, 450, 377_027_555), CLP_M: (1400, 150, 6_035_205), NST_M: (1050, 170, 200)}
    ciks = {"": ES, CLP_M: CLP, NST_M: NST}
    names = {"": "EVERSOURCE ENERGY", CLP_M: "THE CONNECTICUT LIGHT AND POWER COMPANY", NST_M: "NSTAR ELECTRIC COMPANY"}
    ctxs, body = [], ""
    for i, (mem, (rev, prof, shares)) in enumerate(figs.items()):
        m_ = mem or None
        years = [("2025-07-01", "2025-09-30"), ("2026-07-01", "2026-09-30")] if quarter else [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31")]
        for k, (s, e) in enumerate(years):
            ctxs.append(_ctx(f"d{i}{k}", s, e, m_))
            r, p = (rev, prof) if k else (round(rev * 0.9), round(prof * 0.8))
            body += (f'<us-gaap:Revenues contextRef="d{i}{k}" unitRef="USD">{r * M}</us-gaap:Revenues>'
                     f'<us-gaap:NetIncomeLoss contextRef="d{i}{k}" unitRef="USD">{p * M}</us-gaap:NetIncomeLoss>'
                     f'<us-gaap:OperatingIncomeLoss contextRef="d{i}{k}" unitRef="USD">{round(r * 0.25) * M}</us-gaap:OperatingIncomeLoss>')
        ctxs += [_ctx(f"c{i}", None, "2026-10-31" if quarter else "2026-01-31", m_), _ctx(f"b{i}", None, years[-1][1], m_)]
        body += (f'<dei:EntityCentralIndexKey contextRef="c{i}">{ciks[mem]:010d}</dei:EntityCentralIndexKey>'
                 f'<dei:EntityRegistrantName contextRef="c{i}">{names[mem]}</dei:EntityRegistrantName>'
                 f'<dei:EntityCommonStockSharesOutstanding contextRef="c{i}" unitRef="sh">{shares}</dei:EntityCommonStockSharesOutstanding>'
                 f'<us-gaap:StockholdersEquity contextRef="b{i}" unitRef="USD">{rev * 1.2 * M:.0f}</us-gaap:StockholdersEquity>')
    body += '<dei:TradingSymbol contextRef="c0">ES</dei:TradingSymbol>'
    body += ('<us-gaap:EarningsPerShareBasic contextRef="d01" unitRef="USDsh">4.51</us-gaap:EarningsPerShareBasic>' if not quarter else "")
    units = ('<xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit><xbrli:unit id="sh"><xbrli:measure>xbrli:shares</xbrli:measure>'
             '</xbrli:unit><xbrli:unit id="USDsh"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>'
             '<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>')
    return f'<?xml version="1.0" encoding="utf-8"?><xbrli:xbrl {NS}>{"".join(ctxs)}{units}{body}</xbrli:xbrl>'


def subs(cik, name, tickers):
    filings = [("10-Q", *QUARTER, "es-20260930.htm"), ("10-K", *ANNUAL, "es-20251231.htm")]
    return {"cik": cik, "name": name, "sic": "4911", "sicDescription": "Electric Services", "tickers": tickers, "exchanges": ["OTC"] * len(tickers),
            "filings": {"recent": {"form": [f[0] for f in filings], "accessionNumber": [f[1] for f in filings], "filingDate": [f[2] for f in filings],
                                   "primaryDocument": [f[3] for f in filings], "items": [""] * len(filings)}, "files": []}}


def parent_facts_as_the_sec_files_them_for(cik):
    """NSTAR Electric's company facts as the SEC serves them: named "EVERSOURCE ENERGY", with Eversource's figures and cover from the
    combined quarterly report (the SEC copies the report's plain facts to each of its registrants)."""
    row = lambda end, val, start=None: {**({"start": start} if start else {}), "end": end, "val": val, "accn": QUARTER[0], "fy": 2026,  # noqa: E731
                                        "fp": "Q3", "form": "10-Q", "filed": QUARTER[1]}
    return {"cik": cik, "entityName": "EVERSOURCE ENERGY", "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [row("2026-10-31", 377_027_555)]}}},
        "us-gaap": {"Revenues": {"units": {"USD": [row("2026-09-30", 3600 * M, "2026-07-01")]}},
                    "StockholdersEquity": {"units": {"USD": [row("2025-12-31", 16_197 * M)]}}}}}


def transport(facts_of: dict, subs_of: dict, calls: list | None = None):
    tickers = {"0": {"cik_str": ES, "ticker": "ES", "title": "EVERSOURCE ENERGY"},
               "1": {"cik_str": CLP, "ticker": "CNTHP", "title": "CONNECTICUT LIGHT & POWER CO"},
               "2": {"cik_str": NST, "ticker": "NSARO", "title": "NSTAR ELECTRIC CO"}}

    def handler(r: httpx.Request):
        p = r.url.path
        if calls is not None:
            calls.append(p)
        if p == "/files/company_tickers.json":
            return httpx.Response(200, json=tickers)
        for cik in (ES, CLP, NST):
            if p == f"/submissions/CIK{cik:010d}.json":
                return httpx.Response(200, json=subs_of[cik])
            if p == f"/api/xbrl/companyfacts/CIK{cik:010d}.json":
                return httpx.Response(200, json=facts_of[cik]) if facts_of.get(cik) is not None else httpx.Response(404)
        if p.endswith("es-20251231_htm.xml"):
            return httpx.Response(200, text=combined_report())
        if p.endswith("es-20250930_htm.xml") or p.endswith("es-20260930_htm.xml"):
            return httpx.Response(200, text=combined_report(quarter=True))
        if "/Archives/" in p:
            return httpx.Response(200, text="<html><body><p>Annual report.</p></body></html>")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


SUBS = {ES: subs(ES, "EVERSOURCE ENERGY", ["ES"]), CLP: subs(CLP, "CONNECTICUT LIGHT & POWER CO", ["CNTHP", "CNLPL"]),
        NST: {**subs(NST, "NSTAR ELECTRIC CO", ["NSARO", "NSARP"]), "formerNames": [{"name": "NSTAR ELECTRIC CO /MA/"}]}}


# ---------- 1. a subsidiary in its parent's combined report: its own figures, no market value made of the parent's shares ----------
def test_a_combined_report_is_read_for_each_registrant_apart():
    """Fails on main: a combined report's plain figures (the main registrant's) were every registrant's, and the cover's share count added
    the subsidiaries' counts to the parent's (375,496,611 + 6,035,205 + 200)."""
    inst = sec.instance(combined_report())
    reg = sec.registrants(inst)
    assert reg["main"] == ES and set(reg["members"]) == {CLP, NST} and reg["symbols"] == {ES: ["ES"]}
    rev = lambda cik: {r["end"]: r["val"] for r in sec.instance_facts(inst, "10-K", ANNUAL[1], ANNUAL[0], cik)["us-gaap"]["Revenues"]["units"]["USD"]}  # noqa: E731
    assert rev(ES)["2025-12-31"] == 13547 * M and rev(None)["2025-12-31"] == 13547 * M
    assert rev(CLP)["2025-12-31"] == 5241 * M and rev(NST)["2025-12-31"] == 3987 * M
    assert sec.instance_facts(inst, "10-K", ANNUAL[1], ANNUAL[0], 99999) == {}         # a report that gives nothing of a company: nothing
    assert sec.cover_shares(inst)["value"] == 375_496_611 and sec.cover_shares(inst, ES)["value"] == 375_496_611
    assert sec.cover_shares(inst, CLP)["value"] == 6_035_205 and sec.cover_shares(inst, 99999) is None


def test_connecticut_light_and_power_is_built_from_its_own_figures_with_no_market_value():
    """Fails on main: CNTHP's page (and every theme reading it) showed Eversource's $13,547 m revenue and $1,692 m profit, and a market value
    of $19.1 bn: its preferred share's $50.90 times Eversource's 375 million shares. The SEC's company facts hold nothing of it; its figures
    are its own, under its member of the combined report; its common shares aren't listed, so no market value is made."""
    facts = {ES: None, CLP: {"cik": CLP, "entityName": "CONNECTICUT LIGHT & POWER CO", "facts": {}}, NST: None}
    p = sec.SEC(transport=transport(facts, SUBS)).company("CNTHP")
    rows = p["pl"]["rows"]
    assert rows["Sales"][p["pl"]["cols"].index("Dec 2025")] == pytest.approx(5241)
    assert rows["Net Profit"][p["pl"]["cols"].index("Dec 2025")] == pytest.approx(551)
    assert p["shares"] is None and p["cap_why"] == "subsidiary"
    assert p["filed_with"] == {"cik": ES, "name": "Eversource Energy"}
    assert sec.market_value(p, 50.90) is None


def test_nstar_electrics_facts_filed_under_eversources_name_are_not_its_own():
    """Fails on main: the SEC's company facts for NSTAR Electric are named "EVERSOURCE ENERGY" and carry Eversource's quarter and its
    377 million shares; the page showed a $27.9 bn market value and revenue of Eversource's. They are dropped: its own figures only."""
    facts = {ES: None, CLP: None, NST: parent_facts_as_the_sec_files_them_for(NST)}
    p = sec.SEC(transport=transport(facts, SUBS)).company("NSARO")
    cols, rows = p["pl"]["cols"], p["pl"]["rows"]
    assert rows["Sales"][cols.index("Dec 2025")] == pytest.approx(3987) and 13547 not in [round(v or 0) for v in rows["Sales"]]
    assert p["shares"] is None and p["cap_why"] == "subsidiary" and p["filed_with"]["cik"] == ES
    q = dict(zip(p["quarters"]["cols"], p["quarters"]["rows"]["Sales"]))
    assert q and 3600 not in [round(v or 0) for v in q.values()]                    # the parent's quarter is not its own


def test_a_companys_own_facts_cost_no_extra_read_and_the_parent_is_as_before():
    """Guard: Eversource itself (facts of its own, its latest annual report in them) is built from its facts as before, with its shares,
    and no report is read for it."""
    row = lambda end, val, start=None, accn=ANNUAL[0]: {**({"start": start} if start else {}), "end": end, "val": val, "accn": accn,  # noqa: E731
                                                        "fy": 2025, "fp": "FY", "form": "10-K", "filed": ANNUAL[1]}
    own = {"cik": ES, "entityName": "EVERSOURCE ENERGY", "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [row("2026-01-31", 375_496_611)]}}},
        "us-gaap": {"Revenues": {"units": {"USD": [row("2025-12-31", 13547 * M, "2025-01-01"), row("2024-12-31", 11901 * M, "2024-01-01")]}},
                    "NetIncomeLoss": {"units": {"USD": [row("2025-12-31", 1692 * M, "2025-01-01"), row("2024-12-31", 812 * M, "2024-01-01")]}}}}}
    calls = []
    p = sec.SEC(transport=transport({ES: own, CLP: None, NST: None}, SUBS, calls)).company("ES")
    assert p["shares"] == 375_496_611 and not p.get("filed_with") and not p.get("cap_why")
    assert not [c for c in calls if c.endswith("_htm.xml")]
    assert sec.own_name({"entityName": "NSTAR ELECTRIC CO /MA/"}, SUBS[NST]) and not sec.own_name({"entityName": "EVERSOURCE ENERGY"}, SUBS[NST])


def test_the_page_says_why_a_subsidiary_has_no_market_value():
    f = {"region": "US", "symbol": "CNTHP", "name": "Connecticut Light & Power Co", "price": 50.9, "market_cap": None, "cap_why": "subsidiary",
         "filed_with": {"cik": ES, "name": "Eversource Energy"}, "unit": "$ million", "years": []}
    assert stock_pages.cap_missing_reason(f) == "subsidiary"
    notes = " ".join(stock_pages._notes(f))
    assert "Eversource Energy" in notes and "combined report" in notes and "no market value" in notes


# ---------- 2. a mistyped earnings per share never replaces a share count the accounts confirm ----------
def oneg_facts(cover=16_000_000, avg=15_720_548, eps=-84.0, held=None):
    row = lambda end, val, start=None: {**({"start": start} if start else {}), "end": end, "val": val, "accn": "0001-26-1", "fy": 2026,  # noqa: E731
                                        "fp": "FY", "form": "20-F", "filed": "2026-07-23"}
    y = lambda s, e: (f"{s}-04-01", f"{e}-03-31")            # noqa: E731
    g = {"Revenues": {"units": {"USD": [row(y(2024, 2025)[1], 53_205_000, y(2024, 2025)[0]), row(y(2025, 2026)[1], 49_358_000, y(2025, 2026)[0])]}},
         "NetIncomeLoss": {"units": {"USD": [row(y(2024, 2025)[1], 898_000, y(2024, 2025)[0]), row(y(2025, 2026)[1], -13_211_000, y(2025, 2026)[0])]}},
         "EarningsPerShareBasic": {"units": {"USD/shares": [row(y(2025, 2026)[1], eps, y(2025, 2026)[0])]}},
         "CommonStockSharesOutstanding": {"units": {"shares": [row("2026-03-31", held or cover)]}},
         "StockholdersEquity": {"units": {"USD": [row("2026-03-31", 283_000)]}}}
    if avg:
        g["WeightedAverageNumberOfSharesOutstandingBasic"] = {"units": {"shares": [row(y(2025, 2026)[1], avg, y(2025, 2026)[0])]}}
    return {"cik": 2030834, "entityName": "OneConstruction Group Limited",
            "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [row("2026-03-31", cover)]}}}, "us-gaap": g}}


def test_onecontructions_mistyped_earnings_per_share_leave_its_16_million_shares():
    """Fails on main: −84 a share (for −0.84) put 157,274 shares in place of the 16 million on its cover, balance sheet and the year's
    average count, a $0.19 m market value against $49 m of revenue. The year's own average count agrees with the cover's: the count stands."""
    p = sec.build(oneg_facts(), {"name": "OneConstruction Group Ltd", "sic": "1600"}, symbol="ONEG")
    assert p["shares"] == 16_000_000 and not p.get("shares_apart")
    assert sec.market_value(p, 1.21) == pytest.approx(19.36)
    # guard: a cover count mistyped (Alibaba's: a tenth of its shares) is still put right by the earnings, which the average count confirms
    q = sec.build(oneg_facts(cover=1_600_000, eps=-0.84), {"name": "X", "sic": "1600"}, symbol="X")
    assert q["shares"] == pytest.approx(13_211_000 / 0.84, rel=1e-6) and not q.get("shares_apart")


def test_no_market_value_is_shown_on_a_share_count_the_accounts_put_far_apart():
    """A share count every count of the company's own accounts puts more than three times apart: the page shows no market value, says why,
    and the lists ranked by size leave it out."""
    p = sec.build(oneg_facts(cover=160_000, avg=15_720_548, eps=0.0, held=16_000_000), {"name": "X", "sic": "1600"}, symbol="X")
    assert p["shares_apart"] is True
    f = {"region": "US", "market_cap": 0.19, "price": 1.21, "shares_apart": True, "unit": "$ million", "sales_usd": 49.4, "years": []}
    assert stock_pages.cap_problem(f) == stock_pages.SHARES_APART and stock_pages.shown_cap(f) is None
    assert "three times apart from every count of the company's own accounts" in " ".join(stock_pages._notes(f))
    assert not sec.build(oneg_facts(), {"name": "X", "sic": "1600"}, symbol="X").get("shares_apart")


# ---------- 1b. the dive: one registrant once, a subsidiary in its parent's report out of totals adding both ----------
from app.intel import theme_base as TB  # noqa: E402
from app.intel import theme_data as TD  # noqa: E402
from app.intel import theme_listed as TL  # noqa: E402
from tests.test_theme1 import TODAY, facts as page_facts  # noqa: E402


def _sec_list():
    tickers = {f"T{i}": {"cik": 10_000 + i, "name": f"Other Co {i}"} for i in range(1200)}
    tickers.update({f"UT{i}": {"cik": 500 + i, "name": f"Utility {i} Inc"} for i in range(5)})
    tickers.update({"ES": {"cik": ES, "name": "EVERSOURCE ENERGY"}, "CNTHP": {"cik": CLP, "name": "CONNECTICUT LIGHT & POWER CO"},
                    "HZN": {"cik": 1130464, "name": "Bright Horizon Energy Corp"}, "BKH": {"cik": 1130464, "name": "Bright Horizon Energy Corp"}})
    return TL.from_sec(tickers, TODAY.isoformat())


def _utilities(listed):
    cos = [(f"UT{i}", f"Utility {i} Inc", 30000 - i * 1000, 3000 + i * 100) for i in range(5)] + [
        ("ES", "Eversource Energy", 27000, 13547), ("CNTHP", "Connecticut Light & Power Co", None, 5241),
        ("BKH", "Black Hills Corp", 6500, 2310), ("HZN", "Bright Horizon Energy Corp", 6500, 2310)]
    rows = [{"symbol": s, "name": n, "industry": "Electric Services", "market_cap": c} for s, n, c, _ in cos]
    ai = {"sector": "Electric utilities", "summary": "", "core": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 0,
          "value_chain": [{"layer": "Regulated electric utilities", "description": "Generate and deliver electricity to customers.",
                           "companies": [{"ticker": s, "name": n, "what": "generates and delivers electricity to customers", "verified": True}
                                         for s, n, _, _ in cos]}]}
    m = TB.with_base(ai, {**ai, "placements": {"checked": True, "pending": 0}}, rows, [])
    f = {}
    for s, n, cap, rev in cos:
        f[s] = {**page_facts(s, n, [rev * 0.8, rev * 0.9, rev * 0.95, rev], [35.0, 36.0, 37.0, 38.0], [rev * 0.1] * 4, cap=cap, pe=18.0,
                             industry=("Electric Services",)), "region": "US", "unit": "$ million", "annual_form": "10-K", "annual_filed": "2026-02-17"}
    f["CNTHP"]["filed_with"] = {"cik": ES, "name": "Eversource Energy"}
    return TD.build("US", "Electric utilities", m, TD.Sources(TODAY, facts=f.get, listed=listed))


def test_one_registrant_under_two_tickers_is_kept_once_under_the_secs_first():
    """Fails on main: Bright Horizon Energy (HZN) was kept under Black Hills (BKH) "by description": the SEC lists one registrant (CIK
    1130464, Black Hills renamed) under both, HZN first. Merged as one registrant, under HZN."""
    lst = _sec_list()
    assert TL.same_registrant("US", ["BKH", "HZN", "ES", "CNTHP"], lst) == {"BKH": "HZN"}
    assert TL.same_registrant("US", ["BRK.B", "BRK-A"], TL.from_sec({**{f"T{i}": {"cik": i + 9, "name": "x"} for i in range(1200)},
                                                                       "BRK-A": {"cik": 1, "name": "B"}, "BRK-B": {"cik": 1, "name": "B"}}, "d")) \
        == {"BRK.B": "BRK-A"}
    assert TL.same_registrant("IN", ["BKH", "HZN"], lst) == {} and TL.same_registrant("US", ["BKH", "HZN"], None) == {}
    dive = _utilities(lambda: lst)
    dup = {x["symbol"]: x for x in dive["duplicates"]}
    assert dup["BKH"]["kept"] == "HZN" and dup["BKH"]["by"] == "registrant"
    shown = {c["symbol"] for b in dive["layers"] for c in b["companies"]}
    assert "HZN" in shown and "BKH" not in shown


def test_a_subsidiary_in_its_parents_combined_report_is_out_of_totals_adding_both():
    """Fails on main: a US theme had no parent for any member ("No shareholding filing is read for US companies"), so a subsidiary filing in
    its parent's combined report, with figures of its own, would add its revenue twice. Its page says which report it files in."""
    dive = _utilities(lambda: _sec_list())
    assert [(p["symbol"], p["parent"], p.get("by")) for p in dive["parents"]] == [("CNTHP", "ES", "report")]
    lay = next(b for b in dive["layers"] if b["layer"] == "Regulated electric utilities")
    assert [d["symbol"] for d in lay["double"]] == ["CNTHP"]
    sure = [c for c in lay["companies"] if TD.in_calc(c)]
    assert lay["revenue"] == pytest.approx(sum(c["revenue"] for c in sure if c["symbol"] != "CNTHP"))
    from app import deck
    row = deck.parents_row({**dive, "region": "US"})
    assert "Connecticut Light & Power Co files its annual report in Eversource Energy's combined report" in row[1]
    assert TD.filed_in({"CNTHP": {}, "ES": {}}, {"CNTHP": {"filed_with": {"cik": ES}}}, None) == {}      # no list: nothing guessed


def test_the_deck_says_one_registrant_under_two_symbols():
    from app import deck
    rows = deck.confidence_rows({"duplicates": [{"symbol": "BKH", "name": "Black Hills Corp", "kept": "HZN", "kept_name": "Bright Horizon Energy Corp",
                                                 "by": "registrant"}], "layers": []}, {"total": 2}, TODAY)
    row = next(r for r in rows if r[0] == "Same company twice")
    assert "Black Hills Corp is Bright Horizon Energy Corp (one registrant under two symbols on the SEC's list)" in row[1]
    assert "under the symbol the SEC lists first" in row[2]


# ---------- 3. a theme piece behind its rebuilt page is taken again ----------
def test_a_piece_kept_before_its_page_had_figures_is_taken_again(monkeypatch):
    """Fails on main: SpiceJet's and Tata Elxsi's pieces were kept from pages built before they had a year of revenue (R56's stale
    consolidated page), so their rows stayed "(no figures)" while their pages showed five years: the rule re-took a piece only when its
    newest year was the page's and the revenues differed."""
    from app.intel import theme_routes as TR
    idx = {"TATAELXSI": (3757.0, "Mar 2026", "₹ crore"), "SPICEJET": (5326.0, "Mar 2025", "₹ crore"), "TCS": (255324.0, "Mar 2026", "₹ crore")}
    none = {"unit": "₹ crore", "years": [], "q": {"of": "Mar 2015 vs Mar 2014"}}
    assert TR.restated_since("IN", "TATAELXSI", none, idx) and TR.restated_since("IN", "SPICEJET", {**none, "years": [{"year": "Mar 2025"}]}, idx)
    older = {"unit": "₹ crore", "years": [{"year": "Mar 2025", "sales": 3729.0}]}
    assert TR.restated_since("IN", "TATAELXSI", older, idx)                         # the page has a newer year now
    same = {"unit": "₹ crore", "years": [{"year": "Mar 2026", "sales": 255324.0}]}
    assert not TR.restated_since("IN", "TCS", same, idx) and not TR.restated_since("IN", "NOPAGE", none, idx)
    monkeypatch.setattr(TR, "_index_sales", lambda region: idx)
    dive = {"layers": [{"companies": [{"symbol": "TATAELXSI", "unit": "₹ crore", "year": None, "revenue": None},
                                      {"symbol": "SPICEJET", "unit": "₹ crore", "year": None, "revenue": None},
                                      {"symbol": "TCS", "unit": "₹ crore", "year": "Mar 2026", "revenue": 255324.0}]}]}
    got = TR.pages_restated("IN", dive)
    assert "TATAELXSI" in got and "TCS" not in got
    assert "SPICEJET" not in got or TR.recent_year("Mar 2025")          # its page's year is past the 15 months shown: no new mark for it


# ---------- 4. a renamed US ticker finds its company's page, in the watchlist and in search ----------
@pytest.fixture
def store(monkeypatch):
    kept = {}
    monkeypatch.setattr(stock_pages, "_setting", lambda k: json.loads(kept[k]) if k in kept else None)
    monkeypatch.setattr(stock_pages, "_put", lambda k, v: kept.__setitem__(k, json.dumps(v)))
    pages = {2041610: "SKYD", 1077428: "TXCP", 1991261: "RNTZ"}
    monkeypatch.setattr(stock_pages, "us_page_of_cik", lambda cik: pages.get(cik))
    cos = stock_pages.Listed({"SKYD": {"name": "Skydance Corp", "sym": "SKYD", "bse": None}, "TXCP": {"name": "Texas Capital Bancshares", "sym": "TXCP", "bse": None},
                              "RNTZ": {"name": "Rantizo", "sym": "RNTZ", "bse": None}, "AAPL": {"name": "Apple Inc", "sym": "AAPL", "bse": None}})
    monkeypatch.setattr(stock_pages, "companies", lambda region: cos if region == "US" else stock_pages.Listed())
    stock_pages._renames_memo.clear()
    yield kept
    stock_pages._renames_memo.clear()


def test_a_ticker_that_left_the_secs_list_while_its_registrant_stayed_is_kept_as_renamed(store):
    filler = {f"T{i}": {"cik": 10_000 + i, "name": "x"} for i in range(1200)}
    assert stock_pages.keep_us_tickers({**filler, "TCBI": {"cik": 1077428, "name": "TEXAS CAPITAL"}, "EA": {"cik": 712515, "name": "EA"}}) == {}
    got = stock_pages.keep_us_tickers({**filler, "TXCP": {"cik": 1077428, "name": "TEXAS CAPITAL"}})
    assert got == {"TCBI": 1077428}                       # EA's registrant left the list (taken private): renamed nothing
    assert stock_pages.renamed_to("US", "TCBI") == "TXCP" and stock_pages.renamed_to("US", "EA") is None
    assert stock_pages.keep_us_tickers({"TXCP": {"cik": 1077428, "name": "x"}}) == {}           # a broken list changes nothing
    assert stock_pages.rename_aliases("US") == {"TCBI": ["TXCP"]}


def test_an_old_tickers_stored_page_names_its_registrant(store):
    """Fails on main: /stocks/us/PSKY was a 404 though its stored page names its registrant (Skydance Corp, CIK 2041610) in its SEC filing
    addresses; the address now redirects to SKYD's page. SKK (Rantizo's old ticker) likewise, by the SEC number its page keeps."""
    store["stocks:page:US:PSKY"] = json.dumps({"ts": 1, "facts": {"symbol": "PSKY", "filings": [
        {"at": "2026-08-07", "name": "Quarterly report", "url": "https://www.sec.gov/Archives/edgar/data/2041610/000204161026000012/psky-10q.htm"}]}})
    store["stocks:page:US:SKK"] = json.dumps({"ts": 1, "facts": {"symbol": "SKK", "cik": 1991261, "filings": []}})
    assert stock_pages.renamed_to("US", "PSKY") == "SKYD" and stock_pages.renamed_to("US", "SKK") == "RNTZ"
    assert stock_pages.renamed_to("US", "ZZZZ") is None
    assert stock_pages.current_symbol("US", "PSKY") == "SKYD" and stock_pages.current_symbol("US", "AAPL") == "AAPL"


def test_the_watchlist_gives_a_renamed_ticker_as_its_company_now(store):
    from app.intel import routes
    store["stocks:page:US:PSKY"] = json.dumps({"ts": 1, "facts": {"symbol": "PSKY", "cik": 2041610}})
    items = [{"region": "US", "symbol": "PSKY", "name": "Paramount Skydance Corp"}, {"region": "US", "symbol": "AAPL", "name": "Apple"},
             {"region": "IN", "symbol": "TCS", "name": "TCS"}]
    got = routes.current_items(items)
    assert got[0] == {"region": "US", "symbol": "SKYD", "was": "PSKY", "name": "Skydance Corp"}
    assert got[1:] == items[1:]


def test_search_finds_a_renamed_ticker_typed(store):
    from app import suggest
    filler = {f"T{i}": {"cik": 10_000 + i, "name": "x"} for i in range(1200)}
    stock_pages.keep_us_tickers({**filler, "TCBI": {"cik": 1077428, "name": "x"}})
    stock_pages.keep_us_tickers({**filler, "TXCP": {"cik": 1077428, "name": "x"}})
    rows = [{"market": "US", "symbol": "TXCP", "name": "Texas Capital Bancshares Inc", "_sym": "TXCP", "_code": "", "_isin": "", "id": "US:TXCP"},
            {"market": "US", "symbol": "TCBX", "name": "Third Coast Bancshares", "_sym": "TCBX", "_code": "", "_isin": "", "id": "US:TCBX"}]
    got = suggest.rank("TCBI", suggest.index(rows, "US"), 3)
    assert got and got[0]["symbol"] == "TXCP"


def test_sector_figures_are_never_read_from_another_registrants_facts():
    """Fails on main: NSTAR Electric's filed sector figures (capex share, cash flow) were read from the SEC's facts named for Eversource."""
    from app.intel import sector_metrics as sm

    class C:
        def cik(self, s):
            return NST

        def _json(self, path):
            return parent_facts_as_the_sec_files_them_for(NST)

        def submissions(self, cik):
            return SUBS[NST]
    got = sm.read_us("NSARO", C())
    assert got["metrics"] == {} and "another registrant" in got["none"]


def test_an_old_ticker_whose_page_names_a_listed_registrant_is_that_company():
    """SKK Holdings renamed itself Rantizo (CIK 1991261; the SEC lists only RNTZ): no list of names matches, but SKK's stored page names the
    registrant in its filings' SEC addresses. With RNTZ a member too it is the same company, kept once under RNTZ ("by": "registrant"),
    never "no longer listed"; alone it is read by RNTZ's page (renamed)."""
    tickers = {f"T{i}": {"cik": 10_000 + i, "name": f"Other Co {i}"} for i in range(1200)}
    tickers["RNTZ"] = {"cik": 1991261, "name": "Rantizo"}
    lst = TL.from_sec(tickers, "2026-11-27")
    page = {"symbol": "SKK", "filings": [{"url": "https://www.sec.gov/Archives/edgar/data/1991261/000199126126000031/skk-20f.htm"}]}
    assert TL.page_cik(page) == 1991261 and TL.page_cik({"cik": 7}) == 7 and TL.page_cik({}) is None
    assert TL.same_registrant("US", ["SKK", "RNTZ"], lst, page_ciks={"SKK": 1991261}) == {"SKK": "RNTZ"}
    assert TL.same_registrant("US", ["SKK", "RNTZ"], lst) == {}                       # nothing names its registrant: not guessed
    assert TL.renamed("US", "SKK", ["SKK Holdings Ltd"], lst, cik=1991261) == "RNTZ"
    assert TL.renamed("US", "SKK", ["SKK Holdings Ltd"], lst) is None


def test_a_subsidiarys_preferred_share_on_its_cover_is_no_listing_of_its_common_stock():
    """Guard: a combined report's cover listing a subsidiary's preferred share (PG&E's report lists Pacific Gas and Electric's first preferred
    stock) gives it no listed common stock, so no market value is made of that price and its common shares; its own common's symbol does."""
    xml = combined_report().replace(
        '<dei:TradingSymbol contextRef="c0">ES</dei:TradingSymbol>',
        '<dei:TradingSymbol contextRef="c0">ES</dei:TradingSymbol><dei:TradingSymbol contextRef="c1">CNTHP</dei:TradingSymbol>'
        '<dei:Security12bTitle contextRef="c1">Preferred Stock, $50 par value</dei:Security12bTitle>'
        '<dei:TradingSymbol contextRef="c2">NSTX</dei:TradingSymbol><dei:Security12bTitle contextRef="c2">Common Stock</dei:Security12bTitle>')
    reg = sec.registrants(sec.instance(xml))
    assert reg["symbols"].get(CLP) is None and reg["symbols"][NST] == ["NSTX"] and reg["symbols"][ES] == ["ES"]
