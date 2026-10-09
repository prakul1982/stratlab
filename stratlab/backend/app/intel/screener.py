"""Indian company fundamentals from Screener.in's public company pages.

Screener has no API, so this reads the page the way Hindsight did, but from the
server (no public CORS proxies). If Screener changes its layout, the parser
degrades to whatever it can still find instead of failing the whole page."""
import copy
from datetime import datetime, timezone
import re

import httpx
from bs4 import BeautifulSoup

from .net import BROWSER_UA, Source, SourceError, num


_CITE = re.compile(r"\s*\[\d{1,3}\]")
# where a profile's own words end and its pasted breakdowns begin: "[1] Revenue Breakup Q3FY26 [1] BFSI : 31.9% …"
_BREAKDOWN = re.compile(r"\s*(?:\[\d{1,3}\]\s*)?\b(?:Revenue|Business|Segment(?:al)?|Geograph\w*|Product|Order book|Key)\s+"
                        r"(?:Breakup|Break-up|Mix|Split|Share|Wise|Highlights?)\b.*$", re.I | re.S)


def clean_profile(text: str | None) -> str | None:
    """A company profile as people read it: no "[1]" footnote marks and no breakdown lists pasted after the
    description (R5O-027). Nothing left: None."""
    if not text:
        return text
    t = _BREAKDOWN.sub("", str(text))
    t = _CITE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" :;,-")
    return t or None


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).replace(" ", " ").strip() if el else ""


def _label(el) -> str:
    return re.sub(r"\s*\+\s*$", "", _text(el)).strip()


def _table(section) -> dict | None:
    """{"cols": [...], "rows": {label: [numbers]}} from a section's first data table."""
    if section is None:
        return None
    table = section.find("table", class_="data-table") or section.find("table")
    if table is None:
        return None
    head = table.find("thead")
    cols = [_text(th) for th in (head.find_all("th") if head else [])][1:]
    rows = {}
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        label = _label(tds[0])
        if label:
            rows[label] = [num(_text(td)) for td in tds[1:]]
    return {"cols": cols, "rows": rows} if rows else None


def _row(table: dict | None, *prefixes: str) -> list:
    if not table:
        return []
    for label, vals in table["rows"].items():
        if any(label.lower().startswith(p.lower()) for p in prefixes):
            return vals
    return []


def parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {"name": _text(soup.find("h1")), "ratios": {}, "growth": {}, "pros": [], "cons": []}
    cid = re.search(r'data-company-id="(\d+)"', html)
    if cid:
        out["company_id"] = cid.group(1)       # for the balance-sheet breakdown (cash), fetched separately

    ratios = soup.find(id="top-ratios")
    for li in ratios.find_all("li") if ratios else []:
        n, v = li.find(class_="name"), li.find(class_="value")
        if n and v:
            out["ratios"][_text(n)] = _text(v)

    prof = soup.find(class_="company-profile")
    if prof:
        paras = [_text(p) for p in prof.find_all("p")]
        paras = [p for p in paras if len(p) > 30]
        if paras:
            about = clean_profile(" ".join(paras[:2]))
            if about:
                out["about"] = about[:1200]
        for a in prof.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "screener.in" not in href and "bseindia" not in href and "nseindia" not in href:
                out.setdefault("website", href)

    for sec_id, key in (("quarters", "quarters"), ("profit-loss", "pl"), ("balance-sheet", "balance"),
                        ("cash-flow", "cashflow"), ("ratios", "ratios_table"), ("shareholding", "shareholding")):
        t = _table(soup.find(id=sec_id))
        if t:
            out[key] = t

    for tb in soup.find_all("table", class_="ranges-table"):
        th = tb.find("th")
        title = _text(th)
        rows = {}
        for tr in tb.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                rows[_text(tds[0]).rstrip(":").strip()] = _text(tds[1])
        key = ("sales" if "Sales" in title else "profit" if "Profit" in title
               else "price" if "Price" in title else "roe" if "Equity" in title else None)
        if key:
            out["growth"][key] = rows

    peers = soup.find(id="peers")       # the exchange-style classification: sector › industry › basic industry
    path = [_text(a) for a in (peers.find_all("a", href=True) if peers else []) if a["href"].startswith("/market/")]
    if path:
        out["industry_path"] = path[:4]

    for cls in ("pros", "cons"):
        box = soup.find(class_=cls)
        if box:
            out[cls] = [_text(li) for li in box.find_all("li") if _text(li)][:6]
    return out


def _pe(p: dict, price: float | None) -> float | None:
    """P/E as the page's own numbers give it: the price over the trailing twelve months' earnings per share (the EPS
    row's TTM column: profit that belongs to the shareholders), else over the latest year's; none for a loss. The
    source's own "Stock P/E" doesn't always reconcile with the consolidated figures beside it (TCS, October 2026: 14.0
    against 2,075 / 137.64 = 15.1), so it is only the fallback when the page has no EPS row. US filings' ratios are
    worked out from the filings (sec.ratios) and stand as they are."""
    r = p.get("ratios") or {}
    pl = p.get("pl") or {}
    eps = next((v for k, v in (pl.get("rows") or {}).items() if str(k).upper().startswith("EPS")), None)
    if p.get("region") == "US" or not eps or not price:
        return num(r.get("Stock P/E"))
    cols = [str(c).strip().upper() for c in pl.get("cols") or []]
    pairs = [(c, num(v)) for c, v in zip(cols, eps)]
    ttm = next((v for c, v in pairs if c == "TTM"), None)
    years = [v for c, v in pairs if c != "TTM" and v is not None]
    latest = ttm if ttm is not None else (years[-1] if years else None)
    if latest is None:
        return num(r.get("Stock P/E"))
    return round(price / latest, 1) if latest > 0 else None


SHARES_DRIFT = 0.015           # the source's market value and its share capital disagree by more than this: use the capital
# ...unless the balance sheet's count is this much lower: then it is the shares outstanding net of those the company's
# employee trusts hold (treasury shares, which Ind AS takes out of share capital), not a count the source missed
TRUST_GAP = 0.05


def market_cap(cap_cr: float | None, price: float | None, equity_cr: float | None, face: float | None) -> float | None:
    """Market value in crore: price times the shares in issue. The source's own figure is price times its share count at
    the moment it was read, which can lag (TCS, 8 Oct 2026: the screener said 370.3 crore shares, the company page
    361.7, from two reads). The share capital over the face value counts the shares from the balance sheet; when the
    two differ by more than SHARES_DRIFT, that count is used, so every page multiplies the price by the same number of
    shares. A balance-sheet count more than TRUST_GAP below the source's is net of the shares the company's own trusts
    hold, which are still in issue, so the source's count stands (R8V-005: M&M's 559 crore of ₹5 shares, 111.8 crore,
    against 124 crore in issue, cut its value from ₹3.42 to ₹3.08 lakh crore at the same close)."""
    if not price or price <= 0:
        return cap_cr
    shares = (equity_cr / face) if equity_cr and face and face > 0 else None
    if not shares or shares <= 0:
        return cap_cr
    if not cap_cr:
        return round(price * shares, 2)
    source = cap_cr / price
    if abs(source / shares - 1) > SHARES_DRIFT and shares >= source * (1 - TRUST_GAP):
        return round(price * shares, 2)
    return cap_cr


def summary(p: dict) -> dict:
    """The handful of numbers the research page and the AI need."""
    r = p.get("ratios", {})
    pl, bal = p.get("pl"), p.get("balance")
    sales = [v for v in _row(pl, "Sales", "Revenue") if v is not None]
    profit = [v for v in _row(pl, "Net Profit") if v is not None]
    opm = [v for v in _row(pl, "OPM", "Financing Margin") if v is not None]
    reserves = [v for v in _row(bal, "Reserves") if v is not None]
    equity = [v for v in _row(bal, "Equity Capital") if v is not None]
    price = num(r.get("Current Price"))
    book = num(r.get("Book Value"))
    hl = r.get("High / Low", "")
    hi_lo = [num(x) for x in hl.split("/")] if "/" in hl else [None, None]
    # "Latest YoY" is the latest reported year against the year before: full years only, never the trailing twelve
    # months (which overlap the last year by nine months) against the last year
    years = [str(c).strip().upper() != "TTM" for c in (pl or {}).get("cols") or []]
    sales_all, profit_all = _row(pl, "Sales", "Revenue"), _row(pl, "Net Profit")
    n_cols = max(len(years), len(sales_all), len(profit_all))
    year_at = [i for i in range(n_cols) if (years[i] if i < len(years) else True)]      # the full years' columns, in order
    cell = lambda vals, i: vals[i] if i is not None and 0 <= i < len(vals) else None     # noqa: E731
    latest, before = (year_at[-1] if year_at else None), (year_at[-2] if len(year_at) > 1 else None)
    s_now, s_prev, p_now, p_prev = cell(sales_all, latest), cell(sales_all, before), cell(profit_all, latest), cell(profit_all, before)
    # the last reported year's, as its definition says and as the year table beside it shows (TCS FY26: 49,454 of
    # 2,67,021 = 18.5%; the trailing twelve months' 18.1% sat next to the FY26 figures). Both from that year's own column:
    # a blank profit there is a blank margin, never the profit of an earlier year over this year's revenue (R10V-001:
    # Deutsche Bank's 20.1% was 2023's profit over 2025's revenue)
    net_margin = (p_now / s_now * 100) if p_now is not None and s_now else None
    face = num(r.get("Face Value"))
    # debt to equity: the balance sheet's latest column for both, never the debt of one year over the equity of another
    last = lambda label: (lambda row: row[-1] if row and row[-1] is not None else None)(_row(bal, label))      # noqa: E731
    borrow_now, reserves_now, capital_now, whole_now = last("Borrowings"), last("Reserves"), last("Equity Capital"), last("Equity")
    if _row(bal, "Reserves"):             # Indian pages: reserves and share capital together (none for the newest year: no net worth)
        net_worth = (reserves_now + (capital_now or 0)) if reserves_now is not None else None
    else:
        net_worth = whole_now             # US filings: one shareholders' equity row
    return {
        "market_cap_cr": market_cap(num(r.get("Market Cap")), price, equity[-1] if equity else None, face), "price": price,
        "high52": hi_lo[0], "low52": hi_lo[1] if len(hi_lo) > 1 else None,
        "pe": _pe(p, price), "book_value": book, "pb": (price / book) if price and book else None,
        "div_yield": num(r.get("Dividend Yield")), "roce": num(r.get("ROCE")), "roe": num(r.get("ROE")),
        "face_value": num(r.get("Face Value")),
        "net_margin": net_margin, "opm": opm[-1] if opm else None,
        "sales_yoy": ((s_now / s_prev - 1) * 100) if s_now is not None and s_prev is not None and s_prev > 0 else None,
        # a change from a loss isn't a growth rate: none then
        "profit_yoy": ((p_now / p_prev - 1) * 100) if p_now is not None and p_prev is not None and p_prev > 0 else None,
        "debt_cr": borrow_now,
        "debt_equity": (borrow_now / net_worth) if borrow_now is not None and net_worth else None,
        "sales_cr": sales[-1] if sales else None, "profit_cr": profit[-1] if profit else None,
    }


def _years_of(p: dict) -> int:
    pl = p.get("pl") or {}
    return sum(1 for c in pl.get("cols") or [] if str(c).upper() != "TTM")


def _pick(pages: dict) -> dict:
    """Consolidated numbers, unless they go back much less far than the standalone ones (a subsidiary set up
    recently): then standalone, with a note saying so."""
    con, std = pages.get("consolidated"), pages.get("standalone")
    if con and con.get("pl") and not (std and std.get("pl") and _years_of(con) < 6 and _years_of(std) >= _years_of(con) + 2):
        return {**con, "basis": "consolidated"}
    if std and std.get("pl"):
        note = (f"Standalone results: the consolidated accounts only go back {_years_of(con)} years." if con and con.get("pl") else None)
        return {**std, "basis": "standalone", "basis_note": note}
    return {**(con or std), "basis": "consolidated" if con else "standalone"}


class Screener(Source):
    name = "Screener.in"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://www.screener.in", per_minute=20, burst=6, transport=transport,
                         headers={"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml"})

    def _page(self, path: str) -> dict | None:
        html = self.fetch(path, ttl=6 * 3600, kind="text")
        if "top-ratios" not in html:
            if "<h1" not in html:          # not a company page at all: a block or check page, not "no such company"
                self.cache.set((path, (), "text"), None, 0)
                self._failed(True)
                raise SourceError(self.name, f"{self.name} sent a page that isn't a company page (it may be blocking us).", busy=True)
            return None
        # parsing is most of a company page's time: kept while the same cached page is served, and a fresh copy
        # handed out each time so no caller can change another's numbers
        seen = self.cache.get(("parsed", path))
        if seen and seen[0] is html:
            p = seen[1]
        else:
            p = parse(html)
            p["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="minutes")    # for the pages' "as of" line
            self.cache.set(("parsed", path), (html, p), 6 * 3600)
        if not p["ratios"]:
            return None
        return {**copy.deepcopy(p), "url": f"https://www.screener.in{path}"}

    def _schedule(self, p: dict, parent: str, section: str, line: str) -> dict | None:
        """One line of the site's breakdown of a statement line ({column: value}), as its page shows when the line is
        opened: cash inside Other Assets, fixed assets bought inside Cash from Investing Activity. None when it can't
        be read (busy: asked again next time); never counts as an outage."""
        key = ("schedule", p["company_id"], p.get("basis"), parent, line)
        got = self.cache.get(key)
        if got is None:
            if not self.limit.take():
                return None
            got = {}
            try:
                r = self.http.get(f"/api/company/{p['company_id']}/schedules/",
                                  params={"parent": parent, "section": section,
                                          "consolidated": "true" if p.get("basis") == "consolidated" else ""})
                data = r.json() if r.status_code == 200 else {}
                row = next((v for k, v in (data.items() if isinstance(data, dict) else ())
                            if isinstance(v, dict) and re.match(line, k, re.I)), None)
                got = {str(k).strip(): num(str(v)) for k, v in (row or {}).items()}
            except (httpx.HTTPError, ValueError):
                got = {}
            self.cache.set(key, got, 6 * 3600 if got else 1800)
        return got

    def _with_line(self, p: dict, table: str, name: str, parent: str, section: str, line: str) -> dict:
        """`p` with the breakdown line added to one of its tables as `name`, when the table doesn't have it yet."""
        t = p.get(table) or {}
        cols, rows = t.get("cols") or [], t.get("rows") or {}
        if not p.get("company_id") or not cols or any(k.lower().startswith(name.lower().split()[0]) for k in rows):
            return p
        got = self._schedule(p, parent, section, line) or {}
        vals = [got.get(str(c).strip()) for c in cols]
        if not any(v is not None for v in vals):
            return p
        return {**p, table: {**t, "rows": {**rows, name: vals}}}

    def with_cash(self, p: dict) -> dict:
        """`p` with a "Cash Equivalents" row in its balance sheet, from the site's breakdown of Other Assets (the
        page itself folds cash into that line). Unchanged when the breakdown can't be read."""
        return self._with_line(p, "balance", "Cash Equivalents", "Other Assets", "balance-sheet", r"cash")

    def with_capex(self, p: dict) -> dict:
        """`p` with a "Capex" row in its cash flow statement: the fixed assets it bought each year, from the site's
        breakdown of Cash from Investing Activity (the page shows only the total). Unchanged when it can't be read."""
        return self._with_line(p, "cashflow", "Capex", "Cash from Investing Activity", "cash-flow", r"fixed assets purchased")

    RENAMED = {"TATAMOTORS": "TMPV"}   # known symbol changes only: a fuzzy site search can land on another company

    def company(self, symbol: str) -> dict:
        sym = re.sub(r"[^A-Z0-9&\-]", "", symbol.upper())
        if not sym:
            raise SourceError(self.name, "That isn't a company symbol.")
        missing = self.cache.get(("missing", sym))
        if missing:                              # asked recently and the site has no such company
            raise SourceError(self.name, missing)
        last, reloaded = None, False
        base = f"/company/{sym}/"
        for attempt in (0, 1):
            pages = {}
            # consolidated first; companies without subsidiaries only have standalone numbers
            for kind, path in (("consolidated", base + "consolidated/"), ("standalone", base)):
                try:
                    p = self._page(path)
                except SourceError as e:
                    last = e
                    continue
                if p:
                    pages[kind] = p
            if pages:
                got = _pick(pages)
                if (got.get("pl") or {}).get("cols") or reloaded or self.cache.get(("reloaded", sym)):
                    return got
                # a company page that came without its results tables (a partial page under load) isn't kept for hours:
                # asked once more, fresh. A company with no results yet gets the same answer twice.
                reloaded = True
                self.cache.set(("reloaded", sym), True, 3600)      # a company without results yet: not asked twice each time
                for kind, path in (("consolidated", base + "consolidated/"), ("standalone", base)):
                    self.cache.set((path, (), "text"), None, 0)
                    self.cache.set(("parsed", path), None, 0)
                pages = {}
                for kind, path in (("consolidated", base + "consolidated/"), ("standalone", base)):
                    try:
                        p = self._page(path)
                    except SourceError:
                        continue
                    if p:
                        pages[kind] = p
                return _pick(pages) if pages else got
            new = self.RENAMED.get(sym) if attempt == 0 else None
            if not new:
                break
            base = f"/company/{new}/"
        err = last or SourceError(self.name, f"Screener.in has no page for {sym}.")
        if not getattr(err, "busy", False):
            self.cache.set(("missing", sym), str(err), 6 * 3600)
        raise err
