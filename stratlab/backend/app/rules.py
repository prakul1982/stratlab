"""Rates and rules: every rate and rule StratLab hard-codes, in one dated register, with where it lives, the source
it was checked against and the day.

The values themselves stay next to the code that uses them (engine/costs.py, tax_total.py and the rest); the register
reads them from there, so it can't drift from what the app actually uses. What it adds is when each area was last
reviewed against the official sources (REVIEWED), and the days in the year when a rule is known to change (1 April,
the quarterly small-savings rates, the SEC's fiscal year, FINRA's 1 January), so Admin → Data checks can say when a
review is due: more than STALE_DAYS since the last one, or a known change day passed since.

Reviewing: check each rule of an area against its source, change any value that moved (in its own module, with a
test), then move that area's date in REVIEWED. Tax-law changes are never
applied by themselves; rules_watch.py only alerts and shows them in Admin."""
from datetime import date
from .email_kit import inr as _inr

# the day each area was last checked against its official sources
REVIEWED = {
    "trading_costs": "2026-10-05",
    "tax": "2026-10-05",
    "interest_rates": "2026-10-05",
    "market_rules": "2026-10-05",
    "surveillance": "2026-10-04",
}
AREAS = {
    "trading_costs": "Trading costs",
    "tax": "Income tax",
    "interest_rates": "Interest rates",
    "market_rules": "Market rules",
    "surveillance": "Surveillance lists",
}
STALE_DAYS = 90

# days in every year when a rule is known to change: (month, day, area, what changes)
KNOWN_DAYS = [
    (1, 1, "interest_rates", "small-savings rates (PPF) for January to March"),
    (1, 1, "trading_costs", "FINRA's trading activity fee changes on 1 January"),
    (1, 1, "market_rules", "NSE's half-yearly index lot size review takes effect around now"),
    (4, 1, "tax", "a new financial year: the Finance Act's changes take effect"),
    (4, 1, "trading_costs", "Budget changes to STT and stamp duty take effect on 1 April"),
    (4, 1, "interest_rates", "small-savings rates for April to June, and the EPF rate for the year just ended"),
    (7, 1, "interest_rates", "small-savings rates (PPF) for July to September"),
    (7, 1, "market_rules", "NSE's half-yearly index lot size review takes effect around now"),
    (10, 1, "interest_rates", "small-savings rates (PPF) for October to December"),
    (10, 1, "trading_costs", "the SEC's fiscal year starts; its fee rate is reset for the year"),
]


def _pct(v: float) -> str:
    return f"{v * 100:.6g}%"


def _crore(v: float) -> str:
    return f"{_inr(v * 1e7, 2)} a crore"


def registry() -> list[dict]:
    """Every rule: {id, area, name, value, where, source, since}. `value` is read from the module that uses it."""
    from . import instrument_kinds as K, money_advance_tax as A, money_dividends as D, money_networth as N, tax_lots as L, tax_total as T
    from . import money_fx as FX, money_us_tax as U
    from .data import sessions as SS
    from .data.markets import BY_ID
    from .engine import costs as C
    from .intel import filings as F
    from .options import data as O, greeks as G

    nse_tx = "https://nsearchives.nseindia.com/content/circulars/FA73061.pdf (NSE, 27 Feb 2026)"
    budget26 = "https://www.indiabudget.gov.in/doc/memo.pdf (Finance Act 2026)"
    out: list[dict] = []

    def add(rid, area, name, value, where, source, since=None):
        out.append({"id": rid, "area": area, "name": name, "value": value, "where": where, "source": source, "since": since})

    # ---- trading costs
    add("stt_delivery", "trading_costs", "STT, equity delivery", f"{_pct(C.IN_EQUITY['stt'])} on buys and sells",
        "engine/costs.py IN_EQUITY", "https://incometaxindia.gov.in (Securities Transaction Tax rates)", "2004")
    add("stt_intraday", "trading_costs", "STT, equity intraday", f"{_pct(C.IN_EQUITY_MIS['stt_sell'])} on sells",
        "engine/costs.py IN_EQUITY_MIS", "https://incometaxindia.gov.in (Securities Transaction Tax rates)")
    add("stt_futures", "trading_costs", "STT, futures", f"{_pct(C.IN_FUTURES['stt_sell'])} on sells", "engine/costs.py IN_FUTURES",
        budget26, "2026-04-01")
    add("stt_options", "trading_costs", "STT, options", f"{_pct(C.IN_OPTIONS['stt_sell'])} of premium on sells (exercise also 0.15%, not modelled)",
        "engine/costs.py IN_OPTIONS", budget26, "2026-04-01")
    add("ctt", "trading_costs", "CTT, MCX", f"futures {_pct(C.IN_MCX_FUTURES['stt_sell'])}, options {_pct(C.IN_MCX_OPTIONS['stt_sell'])} on sells (non-agri)",
        "engine/costs.py IN_MCX_*", "Finance Act 2013 as amended (CTT)")
    add("nse_cash", "trading_costs", "NSE transaction charge with IPFT, cash", _crore(C.IN_EQUITY["exchange"]), "engine/costs.py IN_EQUITY",
        nse_tx, "2026-03-01")
    add("nse_fut", "trading_costs", "NSE transaction charge with IPFT, equity futures", _crore(C.IN_FUTURES["exchange"]),
        "engine/costs.py IN_FUTURES", nse_tx, "2026-03-01")
    add("nse_opt", "trading_costs", "NSE transaction charge with IPFT, equity options", _crore(C.IN_OPTIONS["exchange"]) + " of premium",
        "engine/costs.py IN_OPTIONS", nse_tx, "2026-03-01")
    add("bse_opt", "trading_costs", "BSE transaction charge, SENSEX and BANKEX options", _crore(C.IN_BSE_OPTIONS["exchange"]) + " of premium",
        "engine/costs.py IN_BSE_OPTIONS", "https://www.bseindia.com/static/members/TFEquity.aspx", "2024-10-01")
    add("mcx_tx", "trading_costs", "MCX transaction charge", f"futures {_crore(C.IN_MCX_FUTURES['exchange'])}, options {_crore(C.IN_MCX_OPTIONS['exchange'])} of premium",
        "engine/costs.py IN_MCX_*", "https://www.mcxindia.com (transaction charges circular, Oct 2024)", "2024-10-01")
    add("cds_tx", "trading_costs", "NSE currency transaction charge", f"futures {_crore(C.IN_CDS_FUTURES['exchange'])}, options {_crore(C.IN_CDS_OPTIONS['exchange'])} of premium",
        "engine/costs.py IN_CDS_*", "https://nsearchives.nseindia.com/corporate/BSE_27092024184037_NSEintimation.pdf", "2024-10-01")
    add("sebi_fee", "trading_costs", "SEBI turnover fee", _crore(C.IN_EQUITY["sebi"]), "engine/costs.py", "SEBI fees regulations (₹10 a crore)")
    add("stamp", "trading_costs", "Stamp duty on buys",
        f"delivery {_pct(C.IN_EQUITY['stamp_buy'])}, intraday {_pct(C.IN_EQUITY_MIS['stamp_buy'])}, futures {_pct(C.IN_FUTURES['stamp_buy'])}, "
        f"options {_pct(C.IN_OPTIONS['stamp_buy'])}, currency {_pct(C.IN_CDS_FUTURES['stamp_buy'])}",
        "engine/costs.py", "Indian Stamp Act 1899 as amended by the Finance Act 2019", "2020-07-01")
    add("gst", "trading_costs", "GST on brokerage and exchange charges", _pct(C.GST), "engine/costs.py GST", "CBIC GST rates (financial services, 18%)")
    add("sec_fee", "trading_costs", "US SEC fee (Section 31)", f"${C.US_SEC_FEE * 1e6:.2f} a million on sells", "engine/costs.py US_SEC_FEE",
        "https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2", "2026-04-04")
    add("finra_taf", "trading_costs", "US FINRA trading activity fee", f"${C.US_FINRA_TAF} a share sold, at most ${C.US_FINRA_CAP:.2f} a trade",
        "engine/costs.py US_FINRA_TAF", "https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule", "2026-01-01")
    add("uk_stamp", "trading_costs", "UK stamp duty (SDRT) on share buys", _pct(C.UK_STAMP), "engine/costs.py UK_STAMP",
        "https://www.gov.uk/guidance/stamp-duty-reserve-tax-rates")

    # ---- income tax
    add("cg_rates", "tax", "Listed share gains (111A / 112A; 196 / 198 of the 2025 Act)",
        f"short term {_pct(C.IN_STCG)}, long term {_pct(C.IN_LTCG)} above ₹{C.IN_LTCG_EXEMPT:,} a year (sales from {L.RATE_CHANGE})",
        "engine/costs.py, tax_lots.py", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2036604", L.RATE_CHANGE)
    add("slabs", "tax", "New regime slabs, FY 2025-26 on", ", ".join(f"{_pct(r)} to {_inr(t)}" if t != float("inf") else f"{_pct(r)} above"
                                                                    for t, r in T.NEW_2025), "tax_total.py NEW_2025",
        T.YEAR_SOURCES.get(2026, ""), "2025-04-01")
    new = T.rules(2026, "new")
    add("rebate", "tax", "Rebate (87A; 156 of the 2025 Act), new regime", f"up to ₹{new['rebate_max']:,} for income to ₹{new['rebate_limit']:,}, not on special-rate gains",
        "tax_total.py _rules", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2098406", "2025-04-01")
    add("surcharge", "tax", "Surcharge", ", ".join(f"{_pct(r)} above ₹{a:,}" for a, r in reversed(T.SURCHARGE))
        + f"; new regime capped at {_pct(new['sc_cap'])}, gains at {_pct(T.SPECIAL_SC_CAP)}", "tax_total.py SURCHARGE", T.YEAR_SOURCES.get(2026, ""))
    add("cess", "tax", "Health and education cess", _pct(T.CESS), "tax_total.py CESS", "Finance Act 2018")
    add("last_fy", "tax", "Last year the tax rules cover", f"FY {T.LAST_FY}-{str(T.LAST_FY + 1)[2:]}", "tax_total.py LAST_FY",
        "add the next year once its Finance Act is out (February)")
    add("new_act", "tax", "Income-tax Act, 2025 section numbers", ", ".join(f"{o}→{n}" for o, n in T.NEW_SECTIONS.items()),
        "tax_total.py NEW_SECTIONS", "https://cleartax.in/s/section-156-income-tax-act-2025 and the Act's concordance", "2026-04-01")
    add("itr_dates", "tax", "Return due dates", "31 Jul (no business income), 31 Aug (business, no audit, from FY 2025-26), 31 Oct (audit); "
        "belated 31 Dec; revised by 31 Mar (from FY 2025-26)", "money_calendar.py tax_dates, tax_total.py filing_facts, money_advance_tax.py",
        "https://cleartax.in/s/due-date-tax-filing (Finance Act 2026 amendment of section 139)", "2026-04-01")
    add("advance_tax", "tax", "Advance tax", f"due at {_inr(A.THRESHOLD)} or more; 15/45/75/100% by 15 Jun, Sep, Dec, Mar; 234B/234C {_pct(A.RATE)} a month",
        "money_advance_tax.py", "Income-tax Act 1961 sections 208-211, 234B, 234C (404, 424, 425 of the 2025 Act)")
    add("dividend_tds", "tax", "Dividend TDS", f"{_pct(D.TDS_RATE)} once a company's dividends pass {_inr(D.tds_threshold(2026))} a year",
        "money_dividends.py", "Finance Act 2025 (section 194; 393 of the 2025 Act)", "2025-04-01")
    add("us_withholding", "tax", "US dividend withholding", _pct(D.US_WITHHOLDING) + " (India-US treaty, Article 10, with a W-8BEN)",
        "money_dividends.py", "https://www.irs.gov/individuals/international-taxpayers/tax-treaty-tables")
    add("us_shares", "tax", "US (foreign) shares, capital gains",
        f"long term when held more than {U.LT_MONTHS} months: {_pct(U.LT_RATE)} without indexation for sales from {L.RATE_CHANGE} "
        f"({_pct(U.LT_RATE_OLD)} with indexation before); short term at the slab rate; no 112A exemption",
        "money_us_tax.py", "https://www.incometaxindia.gov.in/w/tax-on-long-term-capital-gains%E2%80%8B and "
        "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2036604 (Finance (No. 2) Act 2024)", L.RATE_CHANGE)
    add("rule115", "tax", "Foreign income in rupees (Rule 115; rule 206 of the 2026 Rules)",
        "SBI TT buying rate on the last day of the month before the transfer (gains) or the dividend; cost at the month "
        f"before the purchase; the last rate SBI published (up to {FX.STEP_BACK} days back) when it has none that day",
        "money_fx.py rule115", "https://www.incometaxindia.gov.in/w/rule-115-2")
    add("ttbr_data", "tax", "Where the TT buying rates come from",
        f"SBI's daily rate sheets as archived at {FX.SBI_URL.format(cur='USD')}; RBI reference rate fallback (labelled) "
        f"from {FX.RBI_URL}", "money_fx.py", "checked 4 Oct 2026: SBI from Jan 2020, RBI from 1998, both updated daily")
    add("ftc", "tax", "Foreign tax credit (section 90, Rule 128)",
        "the lower of the foreign tax and the Indian tax on that income, at the TT buying rate on the last day of the month "
        "before the tax was cut; Form 67 by the end of the assessment year (Form 44 from tax year 2026-27)",
        "money_us_tax.py ftc", "CBDT Notification 100/2022 (Rule 128(9)): https://x.com/IncomeTaxIndia/status/1560560670659059717",
        "2022-08-18")
    add("schedule_fa", "tax", "Schedule FA (foreign assets)",
        "calendar year ending in the financial year; Table A3 one line per lot with initial, peak and closing value and "
        "income, each at the TT buying rate on its own date; Black Money Act ₹10 lakh penalty, none from 1 Oct 2024 when "
        "assets other than property total ₹20 lakh or less", "money_us_tax.py schedule_fa",
        "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-03/Step%20by%20Step%20Guide%20FA%20FSI.pdf and "
        "https://taxguru.in/income-tax/budget-2024-amends-penalty-undisclosed-foreign-income-assets-itr.html", "2024-10-01")
    add("itr_layouts", "tax", "ITR schedule layouts (AY 2026-27)",
        "112A columns 1a to 14 with 1b (transfer before or from 23 Jul 2024) and one consolidated AE line on upload; CG "
        "Table F and OS dividends in five periods for 234C; ITR-3 intraday and F&O turnover and income separately, "
        "turnover as the sum of absolute profit and loss per trade (ICAI guidance note, 2022)", "money_itr.py",
        "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT__e-Filing_ITR%202_Validation%20Rules_AY%202026-27_V1.0.pdf and "
        "https://static.incometax.gov.in/iec/foservices/assets/itr-shared/documents/112A_115AD_CSV_Instructions.pdf", "2026-04-01")
    add("specified_fund", "tax", "Specified mutual fund (50AA)", f"bought from {K.SPECIFIED_FROM}: slab rate; from {K.SPECIFIED_NEW_DEF} only funds with more than 65% in debt",
        "instrument_kinds.py, money_mf.py", "Finance (No.2) Act 2024", K.SPECIFIED_NEW_DEF)
    add("sgb_tax", "tax", "Gold bond redemption", f"exempt at maturity; from FY {K.SGB_PRIMARY_ONLY_FY}-{str(K.SGB_PRIMARY_ONLY_FY + 1)[2:]} only for bonds bought at issue",
        "instrument_kinds.py", budget26, "2026-04-01")
    add("buyback", "tax", "Share buybacks", "capital gains in the shareholder's hands again from 1 Apr 2026 (dividend from 1 Oct 2024 to 31 Mar 2026); not modelled",
        "not used", "https://taxguru.in/income-tax/buy-taxation-finance-act-2026-resettling-unsettledae.html", "2026-04-01")

    # ---- interest rates
    add("ppf", "interest_rates", "PPF rate", N.PPF_RATE_NOTE, "money_networth.py PPF_RATE",
        "https://www.nsiindia.gov.in (small savings rates, notified each quarter)", "2026-10-01")
    add("epf", "interest_rates", "EPF rate", N.EPF_RATE_NOTE, "money_networth.py EPF_RATE",
        "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2234502 (CBT, 2 Mar 2026)", "2025-04-01")
    add("sgb_rate", "interest_rates", "Gold bond interest", f"{N.SGB_RATE}% a year on the issue price, {N.SGB_YEARS}-year term",
        "money_networth.py SGB_RATE", "https://www.rbi.org.in (SGB FAQs)")
    add("options_rate", "interest_rates", "Rate in the options model (Greeks, what-if)",
        f"{_pct(G.RATE)} a year, near the 91-day T-bill cut-off yield", "options/greeks.py RATE",
        "https://www.rbi.org.in (weekly T-bill auction results: 91-day cut-off 5.52% on 30 Sep 2026; repo 5.25%)",
        "2026-10-05")

    # ---- market rules
    add("freeze", "market_rules", "Index quantity freeze limits",
        ", ".join(f"{k} {v:,}" for k, v in O.FREEZE.items()) + f" (from {O.FREEZE_FROM})", "options/data.py FREEZE",
        "https://nsearchives.nseindia.com/content/circulars/FAOP76693.pdf (NSE/FAOP/76693, 1 Oct 2026)", O.FREEZE_FROM)
    add("lots", "market_rules", "F&O lot sizes and expiries", "read from the broker's instrument list every day (not hard-coded); "
        "NSE weekly expiry Tuesday, BSE Thursday since 1 Sep 2025", "options/data.py",
        "SEBI circular 26 May 2025 on expiry days")
    add("cds_units", "market_rules", "Currency contract size", f"{O.CDS_UNITS:,} units a lot", "options/data.py CDS_UNITS", "NSE currency derivatives contract specifications")
    hours = {m: BY_ID[m]["hours"] for m in ("IN", "MCX", "CDS", "US")}
    add("hours", "market_rules", "Market hours (local)", "; ".join(f"{m} {h['open']}-{h['close']}" for m, h in hours.items())
        + " (MCX to 23:55 when the US is off daylight saving)", "data/markets.py", "the exchanges' trading-hours pages")
    cas = SS.timetable(SS.CAS_FROM)
    add("closing_auction", "market_rules", "Closing auction (CAS) and India's session times",
        f"stocks with derivatives: continuous trading {cas.open}-{cas.cas_end}, closing auction {cas.auction[0]}-{cas.auction[1]} "
        f"(order entry ends at random 15:28-15:30), its price is the official close; other stocks to {cas.cash_end} "
        f"(close = VWAP of the last 30 minutes); futures and options to {cas.fo_end}; expiry settlement at the "
        f"underlying's close (indices from their constituents' closes; stocks at the volume-weighted average of the "
        f"exchanges' auction closes), fixed by {cas.settle_at}. SEBI's 12 Sep 2026 consultation proposes other "
        "timings and settlement prices: not in force", "data/sessions.py TIMES (live.py, group_live.py, options/)",
        f"{SS.SOURCES['sebi']} (SEBI HO/47/11/11(3)2025-MRD-POD2/I/2765/2026, 16 Jan 2026); NSE/CMTR/74466 and "
        f"NSE/FAOP/74467 (29 May 2026); NCL/CMPT/73370 (19 Mar 2026); consultation: {SS.SOURCES['consultation']}",
        SS.CAS_FROM)

    # ---- surveillance
    add("surv_lists", "surveillance", "Surveillance list addresses",
        f"ASM, GSM, ESM: NSE /api/reportASM, /api/reportGSM, /api/reportESM (JSON); F&O ban: {F.FO_BAN} (CSV); "
        f"price bands: {F.SEC_LIST} (CSV)", "intel/filings.py", "checked live every day by the platform check")
    return out


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def known_since(area: str, since: date, today: date) -> list[dict]:
    """Known change days for an area after `since`, up to and including today."""
    out = []
    for y in range(since.year, today.year + 1):
        for m, d, a, what in KNOWN_DAYS:
            day = date(y, m, d)
            if a == area and since < day <= today:
                out.append({"date": day.isoformat(), "what": what})
    return out


def next_known(area: str, today: date) -> dict | None:
    """The next known change day for an area after today."""
    days = sorted((date(y, m, d), what) for y in (today.year, today.year + 1) for m, d, a, what in KNOWN_DAYS
                  if a == area and date(y, m, d) > today)
    return {"date": days[0][0].isoformat(), "what": days[0][1]} if days else None


def review_status(today: date, reviewed: dict | None = None) -> list[dict]:
    """Each area: when it was last reviewed, how many days ago, the known change days passed since and the next one,
    and whether a review is due."""
    reviewed = reviewed or REVIEWED
    out = []
    for area, label in AREAS.items():
        at = _d(reviewed.get(area) or "2000-01-01")
        age = (today - at).days
        passed = known_since(area, at, today)
        out.append({"area": area, "label": label, "reviewed": at.isoformat(), "days": age, "passed": passed,
                    "next": next_known(area, today), "due": age > STALE_DAYS or bool(passed)})
    return out


def check(today: date, reviewed: dict | None = None, watch: dict | None = None) -> dict:
    """The platform-check row: a warning when any area is due a review, or the daily source watch found a change
    nobody has looked at yet."""
    rows = review_status(today, reviewed)
    due = [r for r in rows if r["due"]]
    pending = [s for s in (watch or {}).get("sources", []) if s.get("pending")]
    parts = []
    for r in due:
        why = (f"{r['passed'][-1]['what']} ({_d(r['passed'][-1]['date']):%-d %b})" if r["passed"]
               else f"over {STALE_DAYS} days")
        parts.append(f"{r['label']} reviewed {_d(r['reviewed']):%-d %b %Y}: due ({why})")
    if pending:
        parts.append("Changed at the source: " + ", ".join(s["name"] for s in pending))
    if not parts:
        oldest = min(rows, key=lambda r: r["reviewed"])
        nxt = min((r["next"] for r in rows if r["next"]), key=lambda n: n["date"], default=None)
        detail = (f"All {len(rows)} areas reviewed within {STALE_DAYS} days (oldest: {oldest['label']}, "
                  f"{_d(oldest['reviewed']):%-d %b %Y})" + (f"; next known change {_d(nxt['date']):%-d %b %Y}: {nxt['what']}." if nxt else "."))
        return {"name": "Rates and rules last reviewed", "area": "Rules", "state": "pass", "detail": detail, "seconds": None}
    return {"name": "Rates and rules last reviewed", "area": "Rules", "state": "warn", "detail": "; ".join(parts) + ".", "seconds": None}

