"""Release 23 (the owner's outside reviews of 8 live decks: "the biggest improvement would be a sector-specific analytical engine"): each sector's
own operating figures from the filings, with their source and period (banks' and insurers' results XBRL filed with the exchange, US companies'
SEC company facts), shown for the right families only, and valuation peers of similar market value in the company's own sector, the whole market
only where a sector has too few (and said). Synthetic filings only; no source is called."""
import pytest

from app import deck
from app.intel import sector_metrics as S
from app.intel import theme_data as D
from tests.test_export import plain, table_of, texts
from tests.test_r18_deck import bank_theme, deck_of
from tests.test_r20_deck import co, placements, test_every_rule_holds_on_every_synthetic_theme as every_rule, us_map_theme
from tests.test_theme1 import facts


# ---------- synthetic filings ----------
def xbrl(end, q_start, ytd_start, q=None, ytd=None, at=None, meta=None, kind="fin"):
    """A results filing in the exchange's XBRL shape: the quarter (OneD), the year to date (FourD), the period end (OneI), a segment context
    whose figures must be ignored, figures as filed (rupees, ratios as fractions)."""
    ns = f"http://www.bseindia.com/xbrl/{kind}/2019-09-30/in-bse-{kind}"
    ctx = [("OneD", f"<xbrli:startDate>{q_start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>", ""),
           ("FourD", f"<xbrli:startDate>{ytd_start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>", ""),
           ("OneI", f"<xbrli:instant>{end}</xbrli:instant>", ""),
           ("SegD", f"<xbrli:startDate>{q_start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>",
            '<xbrli:segment><xbrldi:explicitMember dimension="x:SegmentAxis">x:RetailMember</xbrldi:explicitMember></xbrli:segment>')]
    head = "".join(f'<xbrli:context id="{i}"><xbrli:entity><xbrli:identifier scheme="s">X</xbrli:identifier>{seg}</xbrli:entity>'
                   f"<xbrli:period>{p}</xbrli:period></xbrli:context>" for i, p, seg in ctx)
    body = ""
    for cid, part in (("OneD", {**(meta or {}), **(q or {})}), ("FourD", ytd or {}), ("OneI", at or {})):
        body += "".join(f'<f:{k} contextRef="{cid}">{v}</f:{k}>' for k, v in part.items())
    body += '<f:InterestEarned contextRef="SegD">1</f:InterestEarned><f:PercentageOfGrossNpa contextRef="SegD">0.9</f:PercentageOfGrossNpa>'
    return (f'<?xml version="1.0"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
            f'xmlns:f="{ns}">{head}{body}</xbrli:xbrl>').encode()


CR = 10_000_000          # rupees in a crore


def bank_doc(end, q_start, ytd_start, ie, iexp, gnpa=0.0111, nnpa=0.0037, cet1=0.1887, roa=0.0091, prov=None, adv=None, dep=None, profit=100, assets=None):
    at = {"Advances": adv * CR, "Deposits": dep * CR, "Assets": (assets or adv * 1.5) * CR} if adv else {}
    return xbrl(end, q_start, ytd_start, meta={"Symbol": "BANKA", "NatureOfReportStandaloneConsolidated": "Standalone"},
                q={"InterestEarned": ie * CR, "InterestExpended": iexp * CR, "PercentageOfGrossNpa": gnpa, "PercentageOfNpa": nnpa, "CET1Ratio": cet1,
                   "ReturnOnAssets": roa / 2},
                ytd={"ReturnOnAssets": roa, "ProvisionsOtherThanTaxAndContingencies": (prov or 0) * CR, "InterestEarned": ie * 2 * CR,
                     "ProfitLossForThePeriod": profit * CR}, at=at)


SEP26 = bank_doc("2026-09-30", "2026-07-01", "2026-04-01", 1000, 600, prov=30, adv=11600, dep=11880)
SEP25 = bank_doc("2025-09-30", "2025-07-01", "2025-04-01", 900, 535, adv=10000, dep=10000)
DEC26 = bank_doc("2026-12-31", "2026-10-01", "2026-04-01", 1050, 620, gnpa=0.0105, roa=0.0141)
DEC25 = bank_doc("2025-12-31", "2025-10-01", "2025-04-01", 950, 560)


# ---------- 1. banks ----------
def test_a_banks_results_filing_gives_npa_capital_roa_nii_growth_advances_deposits_and_credit_cost_with_period_and_source():
    cur, ago = S.parse_results(SEP26), S.parse_results(SEP25)
    assert cur["end"] == "2026-09-30" and cur["ytd_start"] == "2026-04-01" and cur["standalone"] and cur["symbol"] == "BANKA"
    assert cur["q"]["InterestEarned"] == 1000 * CR                    # the segment context's figure is not the bank's
    got = S.bank_figures(cur, ago, filed="2026-10-17")
    v = {k: x["v"] for k, x in got.items()}
    assert v["gnpa_f"] == 1.11 and v["nnpa_f"] == 0.37 and v["cet1"] == 18.87                 # filed as fractions, shown as %
    # ROA: the half year's profit annualised over average total assets (the filed ROA, 0.91% here, is on each bank's own basis)
    assert v["roa_f"] == pytest.approx(100 * 2 / ((11600 * 1.5 + 10000 * 1.5) / 2) * 100, abs=0.005)
    assert v["nii_q"] == 400.0 and v["nii_growth_f"] == pytest.approx((400 / 365 - 1) * 100, abs=0.05)
    assert v["advances_growth"] == 16.0 and v["deposit_growth_f"] == 18.8
    assert v["credit_cost"] == pytest.approx(30 * 2 / ((11600 + 10000) / 2) * 100, abs=0.005)   # provisions annualised over average advances
    assert got["gnpa_f"]["period"] == "Sep 2026" and got["roa_f"]["period"] == "6 months to Sep 2026, annualised"
    assert "roa_f" not in S.bank_figures(cur)                           # no year-earlier balance sheet: no ROA
    assert got["advances_growth"]["period"] == "Sep 2026 on Sep 2025"
    assert got["cet1"]["source"] == "Results filed with the exchange on 2026-10-17, standalone"
    assert "nim" not in got and "casa" not in got                   # the banking format states neither
    # a figure filed as a percent already is read as one; a CET1 outside any bank's range is left out
    odd = S.parse_results(bank_doc("2026-09-30", "2026-07-01", "2026-04-01", 1000, 600, gnpa=1.11, cet1=0.9))
    assert S.bank_figures(odd)["gnpa_f"]["v"] == 1.11 and "cet1" not in S.bank_figures(odd)


class FakeNse:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def _get(self, path, params, referer=None, circuit="main"):
        self.calls.append((path, params["symbol"], params.get("type")))
        return {"data": self.rows}


def lst(qe, url, cons="Standalone", when="17-Oct-2026 17:46:30", typ="Integrated Filing- Financials"):
    return {"qe_Date": qe, "consolidated": cons, "xbrl": url, "broadcast_Date": when, "type": typ}


ARCH = "https://nsearchives.nseindia.com/corporate/xbrl/"


def test_the_exchange_list_keeps_standalone_filings_of_the_familys_format_the_newest_of_each_quarter():
    rows = S.filing_rows({"data": [lst("30-SEP-2026", ARCH + "INTEGRATED_FILING_BANKING_2_WEB.xml", when="18-Oct-2026 10:00:00"),
                                   lst("30-SEP-2026", ARCH + "INTEGRATED_FILING_BANKING_1_WEB.xml"),
                                   lst("30-SEP-2026", ARCH + "INTEGRATED_FILING_BANKING_3_WEB.xml", cons="Consolidated", when="19-Oct-2026 10:00:00"),
                                   lst("30-JUN-2026", ARCH + "INTEGRATED_FILING_GOVERNANCE_4_WEB.xml", typ="Integrated Filing- Governance"),
                                   lst("30-JUN-2026", ARCH + "INTEGRATED_FILING_INDAS_5_WEB.xml")]}, "bank")
    assert [(r["end"].isoformat(), r["url"].rsplit("/", 1)[1]) for r in rows] == [("2026-09-30", "INTEGRATED_FILING_BANKING_2_WEB.xml")]
    assert S.filing_rows({"data": [lst("30-SEP-2026", ARCH + "INTEGRATED_FILING_GI_1_WEB.xml")]}, "insurer")[0]["kind"] == "GI"


def test_a_bank_whose_latest_quarter_has_no_balance_sheet_takes_advances_from_the_half_year_filings_in_five_reads_at_most():
    docs = {ARCH + "INTEGRATED_FILING_BANKING_D26_WEB.xml": DEC26, ARCH + "INTEGRATED_FILING_BANKING_D25_WEB.xml": DEC25,
            ARCH + "INTEGRATED_FILING_BANKING_S26_WEB.xml": SEP26, ARCH + "INTEGRATED_FILING_BANKING_S25_WEB.xml": SEP25,
            ARCH + "INTEGRATED_FILING_BANKING_J26_WEB.xml": SEP26}
    nse = FakeNse([lst("31-DEC-2026", ARCH + "INTEGRATED_FILING_BANKING_D26_WEB.xml"), lst("30-SEP-2026", ARCH + "INTEGRATED_FILING_BANKING_S26_WEB.xml"),
                   lst("30-JUN-2026", ARCH + "INTEGRATED_FILING_BANKING_J26_WEB.xml"), lst("31-DEC-2025", ARCH + "INTEGRATED_FILING_BANKING_D25_WEB.xml"),
                   lst("30-SEP-2025", ARCH + "INTEGRATED_FILING_BANKING_S25_WEB.xml")])
    read = []
    got = S.read_india("BANKA", "bank", nse, fetch=lambda u: read.append(u) or docs[u], pause=0)
    assert nse.calls == [(S.LIST_PATH, "BANKA", "Integrated Filing- Financials")] and len(read) == 4
    m = got["metrics"]
    assert got["end"] == "2026-12-31" and m["gnpa_f"]["v"] == 1.05 and m["gnpa_f"]["period"] == "Dec 2026"
    assert m["roa_f"]["period"] == "6 months to Sep 2026, annualised"           # from the half-year balance sheets
    assert m["nii_growth_f"]["period"] == "Quarter to Dec 2026 on Dec 2025"
    assert m["advances_growth"]["v"] == 16.0 and m["advances_growth"]["period"] == "Sep 2026 on Sep 2025"
    assert S.read_india("NBFC", "bank", FakeNse([lst("30-SEP-2026", ARCH + "INTEGRATED_FILING_INDAS_9_WEB.xml")]), fetch=lambda u: b"")["metrics"] == {}


# ---------- 2. insurers ----------
LIFE = xbrl("2026-09-30", "2026-07-01", "2026-04-01", meta={"Symbol": "LIFEA"}, q={"SolvencyRatio": 1.97, "GrossPremiumIncome": 27115 * CR},
            ytd={"SolvencyRatio": 1.97, "PersistencyRatio13ThMonth": 0.8755, "ExpensesOfManagementRatio": 0.1168}, kind="ins")
LIFE_AGO = xbrl("2025-09-30", "2025-07-01", "2025-04-01", q={"GrossPremiumIncome": 25000 * CR}, kind="ins")
GENERAL = xbrl("2026-09-30", "2026-07-01", "2026-04-01", meta={"Symbol": "GENA"}, q={"SolvencyRatio": 0.0275, "GrossPremiumsWritten": 7702 * CR},
               ytd={"IncurredClaimRatio": 0.7446, "CombinedRatio": 1.0697}, kind="ins")


def test_an_insurers_filing_gives_solvency_claims_combined_ratio_persistency_and_premium_growth_and_nothing_it_doesnt_state():
    life = S.insurer_figures(S.parse_results(LIFE), S.parse_results(LIFE_AGO), "LI", filed="2026-10-27")
    assert {k: x["v"] for k, x in life.items()} == {"solvency": 1.97, "persistency_13": 87.55, "premium_growth": 8.5}
    assert life["persistency_13"]["period"] == "6 months to Sep 2026" and life["premium_growth"]["period"] == "Quarter to Sep 2026 on Sep 2025"
    gen = S.insurer_figures(S.parse_results(GENERAL), None, "GI")
    # one insurer files its solvency ratio in hundredths (0.0275 for 2.75 times)
    assert {k: x["v"] for k, x in gen.items()} == {"solvency": 2.75, "claims_ratio": 74.46, "combined_ratio": 106.97}
    assert "vnb_margin" not in life                                     # VNB, APE and embedded value aren't in the insurance formats
    stated = S.parse_results(xbrl("2026-09-30", "2026-07-01", "2026-04-01", ytd={"ValueOfNewBusiness": 50.0, "AnnualisedPremiumEquivalent": 200.0}))
    assert S.insurer_figures(stated)["vnb_margin"]["v"] == 25.0          # ...and shown where a filing states them


# ---------- 3. US company facts ----------
def flow(val, end, start, form="10-K", filed=None):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed or end, "fy": int(end[:4]), "fp": "FY"}


def inst(val, end, form="10-K"):
    return {"end": end, "val": val, "form": form, "filed": end}


def companyfacts(rpo=True, parts=False):
    g = {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [flow(800e6, "2025-01-31", "2024-02-01"), flow(1000e6, "2026-01-31", "2025-02-01")]}},
         "ShareBasedCompensation": {"units": {"USD": [flow(230e6, "2026-01-31", "2025-02-01")]}},
         "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [flow(350e6, "2026-01-31", "2025-02-01")]}},
         "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [flow(80e6, "2026-01-31", "2025-02-01")]}}}
    if rpo:
        g["RevenueRemainingPerformanceObligation"] = {"units": {"USD": [inst(1500e6, "2025-07-31", "10-Q"), inst(2000e6, "2026-01-31"), inst(2250e6, "2026-07-31", "10-Q")]}}
    if parts:
        g["ContractWithCustomerLiabilityCurrent"] = {"units": {"USD": [inst(500e6, "2025-01-31"), inst(600e6, "2026-01-31")]}}
        g["ContractWithCustomerLiabilityNoncurrent"] = {"units": {"USD": [inst(100e6, "2025-01-31"), inst(150e6, "2026-01-31")]}}
    else:
        g["ContractWithCustomerLiability"] = {"units": {"USD": [inst(600e6, "2025-01-31"), inst(750e6, "2026-01-31")]}}
    return {"cik": 1, "entityName": "Soft Co", "facts": {"us-gaap": g}}


def test_us_company_facts_give_sbc_share_rpo_cover_and_growth_deferred_revenue_growth_and_fcf_margin():
    got = S.us_figures(companyfacts())
    assert got.pop("_end") == "2026-01-31"
    v = {k: x["v"] for k, x in got.items()}
    assert v == {"sbc_share": 23.0, "fcf_margin": 27.0, "rpo_cover": 2.0, "rpo_growth": 50.0, "deferred_growth": 25.0}
    assert got["sbc_share"]["period"] == "Fiscal year to Jan 2026" and got["rpo_growth"]["period"] == "Jul 2026 on Jul 2025"
    assert got["rpo_cover"]["period"] == "Jan 2026, over the fiscal year to Jan 2026"
    assert "SEC" in got["fcf_margin"]["source"]
    # no RPO filed: none shown; deferred revenue filed in current and non-current parts is added up
    other = S.us_figures(companyfacts(rpo=False, parts=True))
    assert "rpo_growth" not in other and "rpo_cover" not in other and other["deferred_growth"]["v"] == 25.0


# ---------- 4. the deck: the right families only ----------
def bank_pieces(f):
    """Each bank's piece as the store keeps it, from its own synthetic filings (a bank's ratios a little apart from the next one's)."""
    out = {}
    for i, sym in enumerate(sorted(s for s in f if s.startswith(("PVT", "PSU")))):
        cur = S.parse_results(bank_doc("2026-09-30", "2026-07-01", "2026-04-01", 1000 + i * 10, 600, gnpa=0.010 + i * 0.001, nnpa=0.003, cet1=0.15 + i * 0.002,
                                       prov=30, adv=11000 + i * 100, dep=11500))
        ago = S.parse_results(SEP25)
        out[sym] = {"family": "bank", "kind": "BANKING", "end": "2026-09-30", "metrics": S.bank_figures(cur, ago, filed="2026-10-17")}
    return out


def reader_of(pieces, asked=None):
    def get(sym, fam):
        if asked is not None:
            asked.append((sym, fam))
        return pieces.get(sym)
    return get


def test_a_bank_theme_shows_its_filed_figures_in_the_layer_tables_findings_economics_and_a_page_of_its_own():
    region, m, f = bank_theme()[:3]
    pieces = bank_pieces(f)
    asked = []
    v, slides = deck_of(region, m, f, metrics=reader_of(pieces, asked))
    assert asked and all(fam == "bank" for _, fam in asked)
    fams = v["sections"]["sector"]["families"]
    placed = {c["symbol"] for x in v["layers"] for c in x["companies"] if c.get("status") != "unverified"} & set(pieces)
    assert set(fams) == {"bank"} and fams["bank"]["n"] == len(placed) >= 8
    assert {"gnpa_f", "cet1", "advances_growth", "credit_cost", "roa_f"} <= set(fams["bank"]["keys"])
    t = texts(slides)
    sector = table_of(slides, "Sector operating figures: banks")
    assert sector["head"][0] == "Company" and "CET1 ratio" in sector["head"] and "Credit cost" in sector["head"] and sector["head"][-1] == "Period"
    assert plain(sector["rows"])[0][-1] == "Sep 2026" and plain(sector["rows"])[-1][0] == "Median (companies)"
    assert "From the quarterly results filed with the exchange (banking format)" in t
    # changed on purpose (R25): how each filed figure is worked out is on the one page of how the figures are built, with its period, source and limits
    notes = table_of(slides, deck.NOTES_TITLE)
    assert notes["head"] == ["Figure", "What it measures, how it is worked out", "Period and source", "Limitation"]
    how = {r[0]: r[1] for x in slides if x.title.startswith(deck.NOTES_TITLE) for b in x.blocks if b["kind"] == "table" for r in plain(b["rows"])}
    assert how["Credit cost"].startswith("Provisions other than tax for the year to date, annualised") and "CET1 ratio" in how
    assert "NIM and CASA aren't elements of the banking results format" in t
    # one number per metric: the filed gross NPA replaces the page tables' own, in the layer tables too
    row = next(c for x in v["layers"] for c in x["companies"] if c["symbol"] == "PVT0")
    assert row["gnpa"] == row["gnpa_f"] == pieces["PVT0"]["metrics"]["gnpa_f"]["v"] != f["PVT0"]["lender"]["gnpa"]
    layer = next(s for s in slides if s.title.startswith("Layer 1 ·"))
    head = next(b for b in layer.blocks if b["kind"] == "table")["head"]
    assert "Gross NPA" in head and "Deposit growth" in head and "SBC / revenue" not in head and "Solvency" not in head
    body = plain(next(b for b in layer.blocks if b["kind"] == "table")["rows"])
    assert next(r for r in body if r[0] == "Private Lender 0 Ltd")[head.index("Gross NPA")] == "1.4%" == f"{row['gnpa_f']:.1f}%"      # the filed figure
    findings = next(s for s in slides if s.title == "Key findings")
    card = next(it for b in findings.blocks if b["kind"] == "cards" for it in b["items"] if it["title"] == "Sector operating figures")
    assert card["lines"][0].startswith(f"Median of the {len(placed)} banks with filed figures: gross NPA ")
    assert len(next(b for b in findings.blocks if b["kind"] == "cards")["items"]) <= 6
    assert "Median advances growth" in t and "The figures show the two rates, not the funding mix." in t
    assert "SBC" not in t and "Solvency" not in t and "Combined ratio" not in t
    every_rule("banks with filed figures", v, slides)


def insurer_theme():
    life = [co(f"LIF{i}", f"Life Co {i} Ltd", "sells life insurance policies", "Life Insurance") for i in range(3)]
    gen = [co(f"GEN{i}", f"General Co {i} Ltd", "sells general insurance policies", "General Insurance") for i in range(3)]
    m = {"sector": "Insurance", "summary": "Life and general insurers.", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
         "value_chain": [{"layer": "Life insurance", "description": "Life policies.", "companies": life},
                         {"layer": "General insurance", "description": "Motor, health and property policies.", "companies": gen}], "placements": placements(6)}
    f, pieces = {}, {}
    for i, c in enumerate(life + gen):
        ind = ("Financial Services", "Insurance", "Life Insurance" if c in life else "General Insurance")
        f[c["ticker"]] = {**facts(c["ticker"], c["name"], [3000, 3400, 3900, 4500 + i * 200], [None] * 4, [300, 340, 390, 450 + i * 20], cap=90000 - i * 8000,
                                  pe=60.0, roce=None, de=None, industry=ind), "roe": 12.0 + i, "pb": 6.0 - i * 0.3}
        doc = (xbrl("2026-09-30", "2026-07-01", "2026-04-01", q={"SolvencyRatio": 1.9 + i * 0.1, "GrossPremiumIncome": 1000 * CR},
                    ytd={"PersistencyRatio13ThMonth": 0.85 + i * 0.01}) if c in life else
               xbrl("2026-09-30", "2026-07-01", "2026-04-01", q={"SolvencyRatio": 0.02 + i * 0.001, "GrossPremiumsWritten": 1000 * CR},
                    ytd={"IncurredClaimRatio": 0.70 + i * 0.01, "CombinedRatio": 1.02 + i * 0.01}))
        pieces[c["ticker"]] = {"family": "insurer", "end": "2026-09-30", "metrics": S.insurer_figures(S.parse_results(doc), None, "LI" if c in life else "GI")}
    return "IN", m, f, pieces


def test_an_insurer_theme_shows_solvency_and_the_general_insurers_ratios_never_a_banks_or_a_us_companys():
    region, m, f, pieces = insurer_theme()
    v, slides = deck_of(region, m, f, metrics=reader_of(pieces))
    fam = v["sections"]["sector"]["families"]["insurer"]
    assert fam["n"] == 6 and fam["medians"]["solvency"]["n"] == 6 and fam["medians"]["combined_ratio"]["n"] == 3
    sector = table_of(slides, "Sector operating figures: insurers")
    assert {"Solvency ratio", "Claims ratio", "Combined ratio", "13th-month persistency"} <= set(sector["head"])
    rows = {r[0]: r for r in plain(sector["rows"])}
    assert rows["Life Co 0 Ltd"][sector["head"].index("Solvency ratio")] == "1.90x" and rows["General Co 0 Ltd"][sector["head"].index("Solvency ratio")] == "2.30x"
    gen = next(s for s in slides if "General insurance" in s.title and s.title.startswith("Layer"))
    head = next(b for b in gen.blocks if b["kind"] == "table")["head"]
    assert "Solvency" in head and "Combined ratio" in head and "Gross NPA" not in head
    t = texts(slides)
    assert "Median combined ratio" in t and "VNB, APE and embedded value aren't elements of the insurance results formats" in t
    assert "CET1" not in t and "SBC" not in t and "RPO" not in t
    every_rule("insurers with filed figures", v, slides)


def test_a_us_theme_shows_sbc_rpo_deferred_revenue_and_fcf_and_an_indian_industrial_theme_shows_none():
    region, m, f = us_map_theme()
    pieces = {}
    for i, sym in enumerate(sorted(f)):
        got = S.us_figures(companyfacts())
        got.pop("_end")
        got = {k: {**x, "v": round(x["v"] + i, 1)} for k, x in got.items()}
        pieces[sym] = {"family": "us", "end": "2026-01-31", "metrics": got}
    asked = []
    v, slides = deck_of(region, m, f, metrics=reader_of(pieces, asked))
    assert {fam for _, fam in asked} == {"us"}
    sector = table_of(slides, "Sector operating figures: US companies")
    assert {"SBC / revenue", "RPO growth", "Deferred revenue growth", "FCF margin", "RPO / revenue"} <= set(sector["head"])
    assert plain(sector["rows"])[0][-1] == "FY Jan 2026"
    t = texts(slides)
    assert "Median RPO growth" in t and "Gross NPA" not in t and "Solvency" not in t
    every_rule("US with filed figures", v, slides)
    # an Indian theme of manufacturers: no family, so no reading, no page, no column
    cos = [co(f"MK{i}", f"Maker {i} Ltd", "makes auto parts", "Auto Components & Equipments") for i in range(4)]
    mk = {"sector": "Auto parts", "summary": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0, "placements": placements(4),
          "value_chain": [{"layer": "Parts", "description": "Parts.", "companies": cos}]}
    fk = {c["ticker"]: facts(c["ticker"], c["name"], [900, 1000, 1100, 1200 + i], [15, 16, 17, 18], [60, 70, 80, 90], cap=50000 - i * 500) for i, c in enumerate(cos)}
    asked = []
    v2, slides2 = deck_of("IN", mk, fk, metrics=reader_of({}, asked))
    assert asked == [] and v2["sections"]["sector"] == {} and not any(s.title.startswith("Sector operating figures") for s in slides2)


def test_figures_not_read_yet_are_pending_and_the_dive_says_which():
    region, m, f = bank_theme()[:3]
    v, slides = deck_of(region, m, f, metrics=lambda s, fam: None)
    placed = {c["symbol"] for x in v["layers"] for c in x["companies"]}
    assert v["sections"]["sector"]["families"] == {} and set(v["sections"]["sector"]["pending"]) == placed and len(placed) >= 8
    assert not any(s.title.startswith("Sector operating figures") for s in slides)


def test_the_reader_serves_a_kept_piece_reads_within_its_budget_and_queues_the_rest(monkeypatch):
    kept = {"KEPT": {"family": "bank", "metrics": {"cet1": {"v": 15.0, "period": "Sep 2026", "source": "x"}}}}
    read, queued = [], []
    monkeypatch.setattr(S, "stored", lambda r, s: kept.get(s))
    monkeypatch.setattr(S, "read", lambda r, s, fam: read.append(s) or {"family": fam, "metrics": {}})
    monkeypatch.setattr(S, "queue", lambda r, s, fam: queued.append(s))
    get = S.reader("IN", budget=60)
    assert get("KEPT", "bank") == kept["KEPT"] and read == []
    assert get("NEW", "bank") == {"family": "bank", "metrics": {}} and read == ["NEW"]
    late = S.reader("IN", budget=0)
    assert late("LATE", "bank") is None and queued == ["LATE"]
    assert S.reader("IN", fresh=True, budget=60)("KEPT", "bank") == {"family": "bank", "metrics": {}}       # a Refresh reads it again
    S.queue("IN", "X", "bank")                                          # no source set up (the tests): nothing queued, no thread
    assert S._q == []


# ---------- 5. valuation peers in the same sector ----------
def test_peers_are_of_similar_value_in_the_same_sector_outside_the_theme_else_with_the_theme_else_none_and_said():
    # changed on purpose (R27): sector first, then size; with too few comparable peers a company has none (never the whole market)
    rows = [{"symbol": "A", "cap": 10000, "pe": 30.0, "sales_3y": 10.0, "roce": 20.0, "sector": "Financial Services"},
            {"symbol": "B", "cap": 10000, "pe": 20.0, "sales_3y": 10.0, "roce": 20.0, "sector": "Metals"}]
    fin = [{"symbol": f"F{i}", "market_cap": 8000 + i * 100, "pe": 15.0, "sales_cagr_3y": 8.0, "roce": 12.0, "sector": "Financial Services"} for i in range(10)]
    other = [{"symbol": f"O{i}", "market_cap": 9000, "pe": 40.0, "sales_cagr_3y": 2.0, "roce": 5.0, "sector": "Chemicals"} for i in range(5)]
    huge = [{"symbol": "H", "market_cap": 900000, "pe": 99.0, "sector": "Financial Services"}]
    got = D.peers_section(rows, fin + other + huge)
    # A: ten financial companies of similar value outside the theme; B: too few metal companies: no comparable peer set, left out
    assert got["pe"]["sets"] == {"sector": 1, "none": 1} and got["pe"]["peers"] == 15.0 and got["pe"]["n"] == 1 and got["pe"]["none"] == 1
    assert deck.peer_set_words(got["pe"]) == "(own sector, similar market value, outside the theme)"
    assert "with comparable peers (own sector, similar market value, outside the theme)" in deck.pe_peer_line(got["pe"])
    assert deck.pe_peer_line(got["pe"]).endswith("; 1 with no comparable peer set (left out)")
    # nine outside the theme and one of the theme's own of the same sector: the theme's other companies are counted
    theme_mate = {"symbol": "T", "cap": 9000, "pe": 15.0, "sector": "Financial Services"}
    with_mate = D.peers_section([rows[0], theme_mate], fin[:9] + [{**theme_mate, "market_cap": 9000}] + other)
    assert with_mate["pe"]["sets"].get("sector_theme") == 1
    mk = D.peers_section(rows[1:], other)
    assert mk["pe"]["sets"] == {"none": 1} and mk["pe"]["n"] == 0 and deck.peer_set_words(mk["pe"]) == "(no comparable peer set)"
    # a lender is never a non-lender's peer (the same kind of accounts)
    banks = [{**m, "bank": True} for m in fin]
    assert D.peers_section(rows[:1], banks)["pe"]["sets"] == {"none": 1}
