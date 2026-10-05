"""A made-up exchange ETF list and NAV file lines for the ETF price-against-NAV tests and the browser tests' world.
Every number here is synthetic.

SILVERBEES trades 6.1% above its iNAV, GOLDBEES 0.79% below, NIFTYBEES 0.19% above; BANKBEES has no NAV in the file
(only its iNAV gap shows); LIQUIDBEES trades at its iNAV; ODDETF has no price (left out)."""
from datetime import date, timedelta

# symbol, name, ISIN, price, iNAV, NAV (None: not in the NAV file)
ETFS = [
    ("SILVERBEES", "Nippon India Silver ETF", "INF204KC1402", "105.20", "99.15", 98.40),
    ("GOLDBEES", "Nippon India ETF Gold BeES", "INF204KB17I5", "81.20", "81.85", 82.00),
    ("NIFTYBEES", "Nippon India ETF Nifty 50 BeES", "INF204KB14I2", "270.50", "270.00", 269.80),
    ("BANKBEES", "Nippon India ETF Nifty Bank BeES", "INF204KB15I9", "560.00", "567.40", None),
    ("LIQUIDBEES", "Nippon India ETF Nifty 1D Rate Liquid BeES", "INF732E01037", "1,000.00", "1000", 1000.0),
    ("ODDETF", "Some ETF", "INF000X01011", "-", "-", None),
]


def answer(stamp: str = "03-Oct-2026 15:30:00") -> dict:
    """The exchange's /api/etf answer, in its shape (as read live in October 2026): numbers as text, "assets" naming the
    underlying, no ISIN (that is in the ETF securities file, securities_csv). The live answer's "nav" is the last
    published NAV; these ETFs give an indicative NAV instead ("iNavValue"), the case where a source has one."""
    return {"timestamp": stamp, "navDate": stamp[:11], "data": [
        {"symbol": s, "assets": name.split("ETF ")[-1], "ltP": p, "iNavValue": i, "chn": "0.5", "per": "0.4"}
        for s, name, isin, p, i, _ in ETFS]}


def isins() -> dict:
    return {s: isin for s, _, isin, *_ in ETFS}


def securities_csv() -> str:
    """The exchange's ETF securities file (eq_etfseclist.csv), in its columns."""
    head = "Symbol,Underlying Asset,SecurityName,DateofListing,MarketLot,ISINNumber,FaceValue,ETF Underlying,Underlying Key"
    return "\n".join([head] + [f"{s},{name},{s}ETF,01-Jan-10,1,{isin},1,EQUITY,{name}" for s, name, isin, *_ in ETFS]) + "\n"


def nav_lines(day: date) -> str:
    """The ETFs' section of the industry body's daily NAV file, dated `day`."""
    out = ["", "Open Ended Schemes(Other Scheme - Other  ETFs)", "", "Nippon India Mutual Fund", ""]
    for i, (s, name, isin, _, _, nav) in enumerate(ETFS):
        if nav is not None:
            out.append(f"{990100 + i};{isin};-;{name};{nav:.4f};{day.strftime('%d-%b-%Y')}")
    return "\n".join(out) + "\n"


def navs(day: date) -> dict:
    """The parsed NAV data for just these ETFs (what money_mf_nav.daily() would return)."""
    from app import money_mf_nav
    header = "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n"
    return money_mf_nav.parse(header + nav_lines(day))


def weekdays_before(day: date, n: int) -> list[date]:
    out, d = [], day
    while len(out) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return sorted(out)


def seed_history(today: date, n: int = 30):
    """n trading days of stored closes and NAVs: SILVERBEES's gap widening from 1% to about 6%, the others steady."""
    import json
    from app import db, etf_nav
    for k, d in enumerate(weekdays_before(today, n)):
        rows = {}
        for s, _, _, p, _, nav in ETFS:
            if nav is None:
                continue
            g = (1 + 5 * k / max(1, n - 1)) / 100 if s == "SILVERBEES" else {"GOLDBEES": -0.008, "NIFTYBEES": 0.002}.get(s, 0.0)
            rows[s] = [round(nav * (1 + g), 2), nav]
        db.set_setting(etf_nav.DAY_KEY + d.isoformat(), json.dumps(rows))
    etf_nav.forget()
