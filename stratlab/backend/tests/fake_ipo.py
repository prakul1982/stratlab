"""The IPO section's sources as the saved real files have them (tests/fixtures/ipo: fetched on 25 Oct 2026 from the exchanges'
public-issue pages, SEBI's lists, the public IPO calendar and the SEC's EDGAR): fake clients with the same methods the real ones
have, for the unit tests and the browser tests' fake world. `down` names the sources that fail."""
import gzip
import json
import re
from datetime import date
from pathlib import Path

from app.intel import ipo_sources as S
from app.intel import us_calendar as U
from app.intel.net import SourceError

DIR = Path(__file__).parent / "fixtures" / "ipo"


def file(name: str):
    p = DIR / name
    return json.loads(p.read_text()) if name.endswith(".json") else p.read_text()


def pages_of(name: str) -> list[str]:
    """A saved offer document's pages (the ones the readers use are kept; the others are empty strings)."""
    got = json.load(gzip.open(DIR / f"{name}_pages.json.gz", "rt", encoding="utf8"))
    out = [""] * got["count"]
    for i, t in got["pages"].items():
        out[int(i)] = t
    return out


class NSE:
    def __init__(self, down: set | None = None, past: str = "nse_past.json", current: str | None = None):
        self.down, self.calls, self.past, self.current = down or set(), [], past, current
        self.hidden = set()                       # symbols whose issue page the exchange does not have (yet)

    def _check(self, what):
        self.calls.append(what)
        if what.split(":")[0] in self.down or what in self.down:
            raise SourceError("the exchange", f"{what} isn't answering.", busy=True)

    def ipo_upcoming(self):
        self._check("upcoming")
        return file("nse_upcoming.json")

    def ipo_current(self):
        self._check("current")
        return file(self.current) if self.current else []

    def ipo_past(self, frm, to):
        self._check("past")
        return file(self.past)

    def ipo_detail(self, symbol, series="EQ"):
        self._check(f"detail:{symbol}")
        if not (DIR / f"nse_detail_{symbol}.json").exists() or symbol in self.hidden:
            return {"companyName": symbol, "metaInfo": {}, "bidDetails": [{"category": "Total", "noOfSharesOffered": "0.0", "noOfTime": "0.00", "noOfsharesBid": "0.0", "srNo": None}],
                    "issueInfo": {"dataList": []}}
        return file(f"nse_detail_{symbol}.json")


class BSE:
    def __init__(self, down: set | None = None):
        self.down = down or set()

    def ipo_issues(self):
        if "bse" in self.down:
            raise SourceError("the exchange", "isn't answering.", busy=True)
        return file("bse_issues.json")

    def ipo_listed(self, year):
        if "bse" in self.down:
            raise SourceError("the exchange", "isn't answering.", busy=True)
        return file("bse_listed.json")


class Feed:
    def __init__(self, down: set | None = None, **nse):
        self.nse, self.bse = NSE(down, **nse), BSE(down)


class Sebi:
    """SEBI's lists: the first page of each as saved, and the draft list's pages 2 to 14 (the ones its "next" links give)."""

    def __init__(self, down: set | None = None):
        self.down, self.calls = down or set(), []
        self.pages = {"draft": 91, "red_herring": 52}

    def listing(self, kind, page=0):
        self.calls.append((kind, page))
        if "sebi" in self.down:
            raise SourceError("SEBI", "SEBI isn't answering.", busy=True)
        if page == 0:
            return S.sebi_listing(file("sebi_draft_list.html" if kind == "draft" else "sebi_red_herring_list.html"))
        if kind == "draft":
            got = json.load(gzip.open(DIR / "sebi_draft_pages.json.gz", "rt", encoding="utf8"))
            return S.sebi_listing(got[str(page)]) if str(page) in got else []
        return []

    def pdf(self, page_url):
        if "sfc" in page_url:
            return S.sebi_entry_pdf(file("sebi_entry_sfc_rhp.html"))
        return "https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/" + re.sub(r"\W+", "", page_url.rsplit("/", 1)[-1])[:30] + ".pdf"


class Calendar:
    def __init__(self, down: set | None = None):
        self.down, self.months = down or set(), []

    def ipos(self, month: date):
        self.months.append(month.strftime("%Y-%m"))
        if "calendar" in self.down:
            raise SourceError("the calendar", "isn't answering.", busy=True)
        name = f"us_calendar_{month:%Y-%m}.json"
        return U.ipo_rows(file(name)) if (DIR / name).exists() else []


class Edgar:
    def __init__(self, down: set | None = None):
        self.down, self.names, self.ciks, self.finals = down or set(), [], [], 0

    def final_prospectuses(self, since, until):
        self.finals += 1
        if "edgar" in self.down:
            raise SourceError("The SEC", "The SEC isn't answering.", busy=True)
        return [h for h in S.efts_hits(file("edgar_424b4_30d.json")) if since.isoformat() <= h["date"] <= until.isoformat()]

    def filings(self, cik, ttl=0):
        self.ciks.append(cik)
        if "edgar" in self.down:
            raise SourceError("The SEC", "The SEC isn't answering.", busy=True)
        name = {"1806540": "lycia", "1402328": "sunshine", "1997038": "iambic"}.get(str(cik))
        if name:
            return file(f"edgar_submissions_{name}.json")
        others = file("edgar_submissions_others.json")
        return others.get(str(cik)) or {"cik": cik, "filings": {"recent": {"form": ["10-K"], "filingDate": ["2025-03-01"]}}}      # (an unknown company: one already reporting)

    def docs_for(self, name, today):
        self.names.append(name)
        if "edgar" in self.down:
            raise SourceError("The SEC", "The SEC isn't answering.", busy=True)
        return S.offering_docs(file("edgar_submissions_iambic.json")) if "iambic" in name.lower() else None


def seed(today: date | None = None):
    """What the IPO job would have kept, for the fake world's browser tests: issues around today in every stage, made up from the
    saved real files' companies, their terms and bids (parsed from the real exchange pages), the facts and a summary of two real
    offer documents (one Indian, one US). Dates follow `today`, so an issue is open whenever the tests run."""
    from datetime import datetime, timedelta, timezone
    from app import db, ipo
    from app import ipo_docs as D
    today = today or date.today()
    fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")       # (a stored price read is fresh for an hour: the page does not read prices again)
    d = lambda n: (today + timedelta(days=n)).isoformat()      # noqa: E731
    bon = S.nse_detail(file("nse_detail_BONFIG.json"))
    mk = S.nse_detail(file("nse_detail_MKSONS.json"))
    rhp = lambda sym: [{"kind": "RHP", "label": "Red Herring Prospectus", "url": f"https://nsearchives.nseindia.com/content/ipo/RHP_{sym}.zip", "source": "nse"},
                       {"kind": "RHP", "label": f"{sym} RHP", "url": f"https://www.sebi.gov.in/filings/public-issues/oct-2026/{sym.lower()}-rhp_105327.html", "source": "sebi", "date": d(-3)}]
    base = {"market": "IN", "exchanges": ["NSE", "BSE"], "currency": "INR", "series": "EQ", "segment": "mainboard", "seen": d(-9)}
    open_row = {**base, "id": "in-bonfig", "name": "Bonfiglioli Transmissions Limited", "symbol": "BONFIG", "nkey": "bonfiglioli", "open": d(-1), "close": d(2),
                "low": 558.0, "high": 586.0, "lot": 25, "face_value": 10.0, "retail_max": 200000, "ofs": 43239042, "size_shares": 30282330, "isin": "INE28SO01013",
                "industry": "Industrial Products", "issue_type": "Book Building", "lead_managers": bon["lead_managers"], "registrar": bon["registrar"],
                "docs": rhp("BONFIG"), "sub": bon["subscription"], "sub_read": f"{today}T05:00:00+00:00", "detail_at": f"{today}T05:00:00+00:00"}
    rows_in = [
        open_row,
        {**base, "id": "in-mksons", "name": "M. K. Sons Fine Jewels Limited", "symbol": "MKSONS", "nkey": "mksons", "open": d(3), "close": d(5), "low": 153.0, "high": 162.0,
         "lot": 91, "size_shares": 17000000, "fresh": 13600000, "ofs": 3400000, "docs": rhp("MKSONS"), "detail_at": f"{today}T05:00:00+00:00"},
        {**base, "id": "in-bse-4907", "name": "Wiscon Industries Limited", "symbol": None, "series": None, "segment": "sme", "exchanges": ["BSE"], "nkey": "wiscon", "open": d(4), "close": d(6),
         "low": 194.0, "high": 204.0, "size_shares": 5392200, "bse_code": "4907"},
        {**base, "id": "in-bse-4902", "name": "Core4 Engineers Limited", "symbol": None, "series": None, "segment": "sme", "exchanges": ["BSE"], "nkey": "core4", "open": d(-6), "close": d(-3),
         "low": 88.0, "high": 93.0, "size_shares": 4350000, "bse_code": "4902"},
        {**base, "id": "in-zetwerk", "name": "Zetwerk Manufacturing Businesses Limited", "symbol": "ZETWERK", "nkey": "zetwerk", "open": d(-14), "close": d(-11), "listing": d(-8), "low": 143.0, "high": 151.0,
         "price": 151.0, "lot": 99, "ofs": 144525036, "size_shares": 144525036,
         "sub": {"rows": [{"label": "Total", "sr": "total", "offered": 144525036, "bid": 442000000, "times": 3.06}], "times": 3.06, "as_of": f"{d(-11)} 19:00"},
         "perf": {"issue_price": 151.0, "listing_price": 159.25, "listing_change_pct": 5.46, "day_close": 151.0, "day_change_pct": 0.0, "latest": 138.25, "change_pct": -8.44, "listed": d(-8), "latest_date": d(-1), "at": fresh, "basis": "prices"}},
        {**base, "id": "in-tonbo", "name": "Tonbo Imaging Limited", "symbol": "TONBO", "nkey": "tonbo", "open": d(-15), "close": d(-12), "listing": d(-9), "low": 665.0, "high": 700.0,
         "price": 700.0, "lot": 21, "size_shares": 12174046, "ofs": 12174046,
         "sub": {"rows": [{"label": "Total", "sr": "total", "offered": 12174046, "bid": 1654000000, "times": 135.9}], "times": 135.9, "as_of": f"{d(-12)} 19:00"},
         "perf": {"issue_price": 700.0, "listing_price": 1160.0, "listing_change_pct": 65.71, "day_close": 1190.0, "day_change_pct": 70.0, "latest": 1135.0, "change_pct": 62.14, "listed": d(-9), "latest_date": d(-1), "at": fresh, "basis": "prices"}},
        # the exchanges' notes on issues that did not go ahead, and a Social Stock Exchange raise: none of them is in a stage
        {**base, "id": "in-zenith", "name": "Zenith Foods Limited", "symbol": None, "series": None, "exchanges": ["BSE"], "nkey": "zenith", "open": d(-2), "close": d(1), "low": 100.0,
         "high": 110.0, "bse_code": "4911", "issue_status": "withdrawn"},
        {**base, "id": "in-orbit", "name": "Orbit Textiles Limited", "symbol": None, "series": None, "exchanges": ["BSE"], "nkey": "orbit", "open": d(6), "close": d(8), "low": 50.0,
         "high": 55.0, "bse_code": "4912", "issue_status": "postponed"},
        {**base, "id": "in-momsbelief", "name": "Rays of Belief Limited", "symbol": "MOMSBELIEF", "nkey": "raysofbelief", "open": d(-30), "close": d(-28), "low": 227.0, "high": 239.0,
         "social": True},
        {"id": "in-f-105347", "market": "IN", "segment": None, "name": "Hunger Pangs Limited", "symbol": None, "nkey": "hungerpangs", "exchanges": [], "currency": "INR", "filed": d(-4),
         "docs": [{"kind": "DRHP", "label": "Hunger Pangs Limited – DRHP", "url": "https://www.sebi.gov.in/filings/public-issues/oct-2026/hunger-pangs-limited-drhp_105347.html", "date": d(-4), "source": "sebi"}], "seen": d(-4)},
    ]
    us = {"market": "US", "currency": "USD", "segment": None, "seen": d(-9)}
    rows_us = [
        {**us, "id": "us-1100000-1", "name": "Northfield Biologics, Inc.", "symbol": "NFBX", "nkey": "northfield", "exchange": "NASDAQ Global Select", "low": 14.0, "high": 16.0, "shares": 8000000, "expected": d(3)},
        {**us, "id": "us-1273626-119431", "name": "Iambic Therapeutics, Inc.", "symbol": "IAM", "nkey": "iambic", "exchange": "NASDAQ Global Select", "low": 16.0, "high": 16.0, "price": 16.0, "shares": 9375000,
         "amount": 150000000.0, "priced": d(-8), "cik": "1997038", "industry": "Biological Products, (No Diagnostic Substances)",
         "docs": [{"kind": "424B4", "form": "424B4", "label": "424B4", "url": "https://www.sec.gov/Archives/edgar/data/1997038/000119312526422865/iambic_inception_424b4.htm",
                   "link": "https://www.sec.gov/Archives/edgar/data/1997038/000119312526422865/0001193125-26-422865-index.htm", "date": d(-9), "source": "sec"}],
         "perf": {"issue_price": 16.0, "listing_price": 19.5, "listing_change_pct": 21.88, "day_close": 21.0, "day_change_pct": 31.25, "latest": 18.4, "change_pct": 15.0, "listed": d(-8), "latest_date": d(-1), "at": fresh, "basis": "prices"}},
        {**us, "id": "us-1403574-119467", "name": "City Therapeutics, Inc.", "symbol": "CTY", "nkey": "citytherapeutics", "exchange": "NASDAQ Global Select", "low": 18.0, "high": 18.0, "price": 18.0,
         "shares": 11111111, "amount": 199999998.0, "priced": d(1)},
        {**us, "id": "us-1407089-119692", "name": "Nodthera Inc.", "symbol": None, "nkey": "nodthera", "amount": 100000000.0, "filed": d(-4)},
    ]
    ipo.save("IN", rows_in, {"problems": []}, as_of=f"{today}T05:00:00+00:00")
    ipo.save("US", rows_us, {"problems": []}, as_of=f"{today}T05:00:00+00:00")
    # the facts and a summary of two real documents: the Indian one is Bonfiglioli's red herring prospectus, the US one Iambic's
    pages = pages_of("bonfig_rhp")
    for row in (open_row,):
        doc = ipo.doc_to_read(row)
        db.set_setting(D.FACTS_KEY + ipo.doc_key(doc), json.dumps({
            "kind": "RHP", "url": doc["url"], "pages_read": len(pages), "promoters": D.promoters(pages), "selling": D.selling_holders(pages), "objects": D.objects(pages),
            "financials": D.financials(pages), "reader": D.READER, "read_at": f"{today}T05:00:00+00:00", "excerpt": D.india_excerpt(pages)}, ensure_ascii=False))
        q = "OUR PROMOTERS: SONIA BONFIGLIOLI, LUCIANO BONFIGLIOLI, LUISA LUSARDI, BON-FI S.R.L., AND BONFIGLIOLI S.P.A."
        db.set_setting(D.SUM_KEY + ipo.doc_key(doc), json.dumps({
            "reader": D.SUMMARY_READER, "at": f"{today}T05:00:00+00:00", "doc": doc["url"], "problem": None,
            "items": {"business": {"text": "The company's promoters are Italian and Indian family members and group companies; the offer is entirely a sale by one promoter.",
                                   "quote": "Up to 43,239,042 Equity Shares of face value of ₹ 10 each aggregating to ₹ [●] million"},
                      "financials": [], "objects": [{"text": "The objects of the offer are to carry out the offer for sale of up to 43,239,042 equity shares by the promoter selling shareholder, and to list the shares.",
                                                     "quote": "The objects of the Offer are to (i) to carry out the Offer for Sale of up to 43,239,042 Equity Shares"}],
                      "risks": [], "promoters": [{"text": "The promoters are Sonia Bonfiglioli, Luciano Bonfiglioli, Luisa Lusardi, Bon-Fi S.r.l. and Bonfiglioli S.p.A.", "quote": q}]}}, ensure_ascii=False))
    iam = rows_us[1]
    doc = ipo.doc_to_read(iam)
    text = D.html_text(gzip.open(DIR / "iambic_424b4_head.htm.gz").read())
    db.set_setting(D.FACTS_KEY + ipo.doc_key(doc), json.dumps({"kind": "424B4", "url": doc["url"], "us": D.us_facts(text), "reader": D.READER,
                                                              "read_at": f"{today}T05:00:00+00:00", "excerpt": D.us_excerpt(text)}, ensure_ascii=False))
    ipo.forget()
