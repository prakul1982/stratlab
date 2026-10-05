"""The exchange's shareholding-pattern filings for the tests and the browser tests' world, from real samples trimmed to
what the parser reads (tests/fixtures/shareholding): XPRO India and Safari Industries for the quarters to 31 Mar and
30 Jun 2026, and HDFC Bank for 30 Jun 2026. The list rows are the exchange's own (list.json); only their XBRL links
point at the fixture files here.

Facts in the samples, as filed: Ashish Kacholia held 3.91% of XPRO India in both quarters and 1.84% of Safari in both;
HSBC Small Cap Fund held 4.41% of Safari in March and isn't listed in June (below 1%); Invesco India Flexi Cap Fund is
new in Safari's June list at 3.73%."""
import json
from pathlib import Path

import httpx

DIR = Path(__file__).parent / "fixtures" / "shareholding"
ARCHIVE = "https://nsearchives.nseindia.com/corporate/xbrl/"
MONTHS = {"MAR": "03-31", "JUN": "06-30", "SEP": "09-30", "DEC": "12-31"}


def _quarter(day: str) -> str:
    """"30-JUN-2026" → "2026-06-30"."""
    d, m, y = day.split("-")
    return f"{y}-{MONTHS[m.upper()]}"


def rows() -> list[dict]:
    """The exchange's list rows that have a fixture document, each pointing at it."""
    out = []
    for r in json.loads((DIR / "list.json").read_text()):
        name = f"{r['symbol']}_{_quarter(r['date'])}.xml"
        if (DIR / name).exists():
            out.append({**r, "xbrl": ARCHIVE + name})
    return out


def answer(r: httpx.Request):
    """The fake exchange's answer for a shareholding path, or None when it isn't one."""
    if r.url.path == "/api/corporate-share-holdings-master":
        sym = r.url.params.get("symbol")
        got = [x for x in rows() if not sym or x["symbol"] == sym]
        return httpx.Response(200, json=got)
    if r.url.path.startswith("/corporate/xbrl/"):
        f = DIR / r.url.path.rsplit("/", 1)[-1]
        if f.suffix == ".xml" and f.exists():
            return httpx.Response(200, content=f.read_bytes(), headers={"content-type": "application/xml"})
        return httpx.Response(404, text="Not found")
    return None


def seed(symbols=("XPROINDIA", "SAFARI", "HDFCBANK"), also: dict | None = None):
    """Store the fixtures' filings as the job would have (and, with `also`, a fixture under another symbol, e.g.
    {"RELIANCE": "SAFARI"} for a company page in the browser tests' world)."""
    from app import shareholders as S
    for row in S.list_rows(rows()):
        targets = [row["symbol"]] if row["symbol"] in symbols else []
        targets += [k for k, v in (also or {}).items() if v == row["symbol"]]
        for t in targets:
            parsed = S.parse_xbrl((DIR / row["url"].rsplit("/", 1)[-1]).read_bytes())
            S.store(t, {**row, "symbol": t}, {**parsed, "name": parsed["name"] if t == row["symbol"] else f"{t.title()} (sample holders)"})
