"""Business updates for the tests and the browser tests' world.

The documents are the text of three real filings of 1 and 4 Oct 2026 (tests/fixtures/business_updates: Maruti
Suzuki's September sales, TVS Motor's September sales update and HDFC Bank's quarterly provisional figures), redrawn
as PDFs page by page (the rupee sign written "Rs", as the test PDFs' font has no rupee). The AI's replies are
written here the way a model answers, with quotes copied from those documents, plus made-up figures the checks must
throw away. SAMPLE is made up: a year of monthly updates for the browser tests' company page."""
import json
import re
from pathlib import Path

import httpx

from tests.pdfmaker import make_pdf_pages

DIR = Path(__file__).parent / "fixtures" / "business_updates"
ARCHIVE = "https://nsearchives.nseindia.com/corporate/"
FILES = {"MARUTI": "MARUTI_01102026125916_Sales.pdf", "TVSMOTOR": "TVSMOTOR_01102026150928_Salesupdatesept2026_sd.pdf",
         "HDFCBANK": "HDFCBANK_04102026220033_initial_Final_disclosure_Sep2026.pdf"}


def pages(name: str) -> list[list[str]]:
    """A fixture filing's pages as lines (latin-1 only)."""
    text = (DIR / f"{name}.txt").read_text().replace("₹", "Rs").replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-")
    text = text.encode("latin-1", "replace").decode("latin-1")
    parts = re.split(r"\[\[page \d+\]\]", text)
    return [[ln for ln in p.split("\n") if ln.strip()] for p in parts if p.strip()]


def pdf(name: str) -> bytes:
    return make_pdf_pages(pages(name))


def docs_transport(extra: dict[str, bytes] | None = None) -> httpx.MockTransport:
    """The exchange's archive serving the fixture filings (and `extra` {file name: PDF bytes})."""
    def handler(r: httpx.Request):
        name = r.url.path.rsplit("/", 1)[-1]
        if extra and name in extra:
            return httpx.Response(200, content=extra[name])
        if name in FILES.values():
            return httpx.Response(200, content=pdf(name))
        return httpx.Response(404, text="Not found")
    return httpx.MockTransport(handler)


def announcements(symbol: str) -> list[dict]:
    """The exchange's real announcement rows for MARUTI, TVSMOTOR or HDFCBANK (trimmed), as the feed returns them."""
    from app.intel.filings import normalise
    rows = json.loads((DIR / "announcements.json").read_text()).get(symbol, [])
    return normalise(rows)


# the model's answers, by company: quotes copied from the documents (as the PDFs give them back), plus figures the
# checks must drop: a number that isn't in its quote, and a quote that isn't in the document
REPLIES = {
    "MARUTI": {"period": "2026-09", "span": "month", "figures": [
        {"metric": "Total sales", "value": 236013, "unit": "units", "basis": "month", "prior": 189665, "headline": True,
         "quote": "Total Sales (Total Domestic + Export) 236,013 189,665 1,379,378 1,078,735", "page": 2},
        {"metric": "Domestic passenger vehicles", "value": 181838, "unit": "units", "basis": "month", "prior": 132820,
         "quote": "Total Domestic Passenger Vehicle Sales (PV) 181,838 132,820 1,080,240 795,446", "page": 2},
        {"metric": "Exports", "value": 44219, "unit": "units", "basis": "month", "prior": 42204,
         "quote": "Total Export Sales 44,219 42,204 232,855 207,459", "page": 2},
        {"metric": "Exports year to date", "value": 232855, "unit": "units", "basis": "month",
         "quote": "Total Export Sales 44,219 42,204 232,855 207,459", "page": 2},
        {"metric": "Wrong number", "value": 999999, "unit": "units", "basis": "month", "quote": "Total Export Sales 44,219 42,204", "page": 2},
        {"metric": "Made up", "value": 5000, "unit": "units", "basis": "month", "quote": "Maruti sold 5,000 flying cars in September 2026", "page": 2},
    ]},
    "TVSMOTOR": {"period": "2026-09", "span": "month", "figures": [
        {"metric": "Total sales", "value": 672790, "unit": "units", "basis": "month", "prior": 541064, "headline": True,
         "quote": "TVS Motor Company recorded 24% increase in sales with 672,790 units in September 2026 as against 541,064 units in September 2025.", "page": 2},
        {"metric": "Two-wheeler EVs", "value": 65799, "unit": "units", "basis": "month", "prior": 31266,
         "quote": "Two-wheeler EVs registered 110% increase in sales with 65,799 units in September 2026 as against 31,266 units in September 2025.", "page": 2},
    ]},
    "HDFCBANK": {"period": "2026-09", "span": "quarter", "figures": [
        {"metric": "Period-end deposits", "value": 33275, "unit": "Rs billion", "basis": "period end", "prior": 28018, "headline": True,
         "quote": "The Bank's period end deposits were approximately Rs 33,275 billion as of September 30, 2026, a growth of around 18.8% over Rs 28,018 billion as of September 30, 2025.", "page": 1},
        {"metric": "Average CASA deposits", "value": 9712, "unit": "Rs billion", "basis": "quarter", "prior": 8770,
         "quote": "The Bank's average CASA deposits were Rs 9,712 billion for the September 2026 quarter, a growth of around 10.7% over Rs 8,770 billion", "page": 1},
    ]},
}


def ai(system: str, text: str, **kw) -> str:
    """The model, for the business-update reads: the reply for the company named in the request."""
    m = re.search(r"COMPANY: (\S+)", text)
    return json.dumps(REPLIES.get(m.group(1) if m else "", {"period": None, "figures": []}))


def sample_reads(months: int = 14, end: str = "2026-09") -> dict:
    """Made-up monthly updates for one company: total sales rising 2% a month, each filing also stating the year-ago
    month, and exports. Every number is synthetic."""
    from app.biz_updates import shift
    out = {}
    for i in range(months):
        p = shift(end, -(months - 1 - i))
        total, prior, exports = 100000 + 2000 * i, 90000 + 1500 * i, 20000 + 300 * i
        filed = f"{shift(p, 1)}-01T12:00"
        q1 = f"Total sales {total:,} units in the month as against {prior:,} units a year earlier."
        out[f"s{i}"] = {"at": filed, "title": f"Monthly business update for {p}", "url": f"{ARCHIVE}SAMPLE_{p}.pdf",
                        "read_at": filed, "period": p, "span": "month", "problem": None,
                        "figures": [{"metric": "Total sales", "segment": None, "value": float(total), "unit": "units", "basis": "month",
                                     "prior": float(prior), "headline": True, "quote": q1, "page": 1},
                                    {"metric": "Exports", "segment": None, "value": float(exports), "unit": "units", "basis": "month",
                                     "prior": None, "headline": False, "quote": f"Exports {exports:,} units.", "page": 1}]}
    return out


def seed(symbols=("RELIANCE",)):
    """Store the made-up year of updates under each symbol, as the job would have."""
    from app import biz_updates as B
    for sym in symbols:
        for fid, r in sample_reads().items():
            B.save(sym, fid, r)
