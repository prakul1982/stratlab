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
            out["about"] = " ".join(paras[:2])[:1200]
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


def summary(p: dict) -> dict:
    """The handful of numbers the research page and the AI need."""
    r = p.get("ratios", {})
    pl, bal = p.get("pl"), p.get("balance")
    sales = [v for v in _row(pl, "Sales", "Revenue") if v is not None]
    profit = [v for v in _row(pl, "Net Profit") if v is not None]
    opm = [v for v in _row(pl, "OPM", "Financing Margin") if v is not None]
    borrow = [v for v in _row(bal, "Borrowings") if v is not None]
    reserves = [v for v in _row(bal, "Reserves") if v is not None]
    equity = [v for v in _row(bal, "Equity Capital") if v is not None]
    price = num(r.get("Current Price"))
    book = num(r.get("Book Value"))
    hl = r.get("High / Low", "")
    hi_lo = [num(x) for x in hl.split("/")] if "/" in hl else [None, None]
    net_margin = (profit[-1] / sales[-1] * 100) if sales and profit and sales[-1] else None
    whole = [v for v in _row(bal, "Equity") if v is not None]       # US filings: one shareholders' equity row
    net_worth = (reserves[-1] + (equity[-1] if equity else 0)) if reserves else (whole[-1] if whole else None)
    return {
        "market_cap_cr": num(r.get("Market Cap")), "price": price,
        "high52": hi_lo[0], "low52": hi_lo[1] if len(hi_lo) > 1 else None,
        "pe": num(r.get("Stock P/E")), "book_value": book, "pb": (price / book) if price and book else None,
        "div_yield": num(r.get("Dividend Yield")), "roce": num(r.get("ROCE")), "roe": num(r.get("ROE")),
        "face_value": num(r.get("Face Value")),
        "net_margin": net_margin, "opm": opm[-1] if opm else None,
        "sales_yoy": ((sales[-1] / sales[-2] - 1) * 100) if len(sales) > 1 and sales[-2] else None,
        "profit_yoy": ((profit[-1] / profit[-2] - 1) * 100) if len(profit) > 1 and profit[-2] else None,
        "debt_cr": borrow[-1] if borrow else None,
        "debt_equity": (borrow[-1] / net_worth) if borrow and net_worth else None,
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

    def with_cash(self, p: dict) -> dict:
        """`p` with a "Cash Equivalents" row in its balance sheet, from the site's breakdown of Other Assets (the
        page itself folds cash into that line). Unchanged when the breakdown can't be read; never counts as an outage."""
        bal = p.get("balance") or {}
        cols, rows = bal.get("cols") or [], bal.get("rows") or {}
        if not p.get("company_id") or not cols or any(k.lower().startswith("cash") for k in rows):
            return p
        key = ("cash", p["company_id"], p.get("basis"))
        got = self.cache.get(key)
        if got is None:
            if not self.limit.take():
                return p                          # busy: no cash this time, asked again next time
            got = {}
            try:
                r = self.http.get(f"/api/company/{p['company_id']}/schedules/",
                                  params={"parent": "Other Assets", "section": "balance-sheet",
                                          "consolidated": "true" if p.get("basis") == "consolidated" else ""})
                data = r.json() if r.status_code == 200 else {}
                row = next((v for k, v in (data.items() if isinstance(data, dict) else ())
                            if isinstance(v, dict) and re.match(r"cash", k, re.I)), None)
                got = {str(k).strip(): num(str(v)) for k, v in (row or {}).items()}
            except (httpx.HTTPError, ValueError):
                got = {}
            self.cache.set(key, got, 6 * 3600 if got else 1800)
        vals = [got.get(str(c).strip()) for c in cols]
        if not any(v is not None for v in vals):
            return p
        return {**p, "balance": {**bal, "rows": {**rows, "Cash Equivalents": vals}}}

    RENAMED = {"TATAMOTORS": "TMPV"}   # known symbol changes only: a fuzzy site search can land on another company

    def company(self, symbol: str) -> dict:
        sym = re.sub(r"[^A-Z0-9&\-]", "", symbol.upper())
        if not sym:
            raise SourceError(self.name, "That isn't a company symbol.")
        missing = self.cache.get(("missing", sym))
        if missing:                              # asked recently and the site has no such company
            raise SourceError(self.name, missing)
        last = None
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
                return _pick(pages)
            new = self.RENAMED.get(sym) if attempt == 0 else None
            if not new:
                break
            base = f"/company/{new}/"
        err = last or SourceError(self.name, f"Screener.in has no page for {sym}.")
        if not getattr(err, "busy", False):
            self.cache.set(("missing", sym), str(err), 6 * 3600)
        raise err
