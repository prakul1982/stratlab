"""The exchange's insider-trading disclosures as it publishes them since May 2026: a list of filings
(/api/corporates-pit-gg: company, regulation, time and the links to each filing's documents) and each filing's XBRL
document on the exchange's archive, which holds the trades. The old list (/api/corporates-pit) answers nothing.

Two sources here:
- real samples (tests/fixtures/insider): six filings of 28 Oct-5 Nov 2026 as the exchange served them, the people's
  names replaced with "Person A".."Person I" and their identification numbers, signatories and places taken out;
- the tests' world: the made-up RELIANCE disclosures of `world.deal_rows()`, each written as a filing and a document
  in the exchange's format, so every page reads them through the real reader."""
import json
from datetime import datetime
from pathlib import Path

import httpx

DIR = Path(__file__).parent / "fixtures" / "insider"
ARCHIVE = "https://nsearchives.nseindia.com/corporate/"


def fixture_list() -> dict:
    return json.loads((DIR / "list.json").read_text())


def fixture_doc(url: str) -> bytes:
    return (DIR / url.rsplit("/", 1)[-1]).read_bytes()


def fixture_transport(calls: list | None = None, refuse: set | None = None) -> httpx.MockTransport:
    """The exchange answering the samples: the list for any window, and each document (or a refusal for the names in
    `refuse`)."""
    def handler(r: httpx.Request):
        if calls is not None:
            calls.append((r.url.host, r.url.path, dict(r.url.params)))
        if r.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        if r.url.path == "/api/corporates-pit-gg":
            rows = fixture_list()["data"]
            sym = r.url.params.get("symbol")
            return httpx.Response(200, json={"data": [x for x in rows if not sym or x["symbol"] == sym]})
        if r.url.path == "/api/corporates-pit":
            return httpx.Response(200, json={"acqNameList": [], "data": []})
        name = r.url.path.rsplit("/", 1)[-1]
        if refuse and name in refuse:
            return httpx.Response(403, text="Access Denied")
        f = DIR / name
        if r.url.path.startswith("/corporate/xbrl/") and f.exists():
            return httpx.Response(200, content=f.read_bytes(), headers={"content-type": "application/xml"})
        return httpx.Response(404, text="Not found")
    return httpx.MockTransport(handler)


# ---------- the world's made-up disclosures, written in the exchange's format ----------
def _day(v) -> datetime | None:
    s = str(v or "").strip()
    for fmt in ("%d-%b-%Y %H:%M", "%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _num(v) -> str | None:
    s = str(v if v is not None else "").replace(",", "").strip()
    try:
        float(s)
    except ValueError:
        return None
    return s


def document(row: dict) -> str:
    """One old-shape disclosure row as the exchange's XBRL document (one person, one trade)."""
    def fact(name, value, ctx="Disclosure1", unit=""):
        if value is None or value == "":
            return ""
        return f'<in-bse-co:{name} contextRef="{ctx}"{unit}>{value}</in-bse-co:{name}>'
    iso = lambda v: (_day(v) or datetime(1970, 1, 1)).date().isoformat() if v else None   # noqa: E731
    pct = _num(row.get("afterAcqSharesPer"))
    filed = _day(row.get("date")) or _day(row.get("acqtoDt"))
    return ('<?xml version="1.0" encoding="UTF-8"?><!--PIT V2.0 (30-04-2026)-->'
            '<xbrli:xbrl xmlns:in-bse-co="http://www.bseindia.com/xbrl/co/2017-09-15/in-bse-co" xmlns:xbrli="http://www.xbrl.org/2003/instance">'
            + fact("Symbol", row.get("symbol"), "MainI") + fact("NameOfTheCompany", "Reliance Industries Limited", "MainI")
            + fact("DateOfFiling", filed.date().isoformat() if filed else None, "MainI")
            + fact("DisclosureUnderRegulation", "Regulation 7 (2)", "MainI")
            + fact("TypeOfInstrument", row.get("secType")) + fact("CategoryOfPerson", row.get("personCategory"))
            + fact("NameOfThePerson", row.get("acqName"))
            + fact("SecuritiesAcquiredOrDisposedNumberOfSecurity", _num(row.get("secAcq")), unit=' unitRef="shares" decimals="INF"')
            + fact("SecuritiesAcquiredOrDisposedValueOfSecurity", _num(row.get("secVal")), unit=' unitRef="INR" decimals="0"')
            + fact("SecuritiesAcquiredOrDisposedTransactionType", row.get("tdpTransactionType"))
            + fact("SecuritiesHeldPostAcquistionOrDisposalPercentageOfShareholding", f"{float(pct) / 100:.6f}" if pct else None,
                   unit=' unitRef="pure" decimals="INF"')
            + fact("DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyFromDate", iso(row.get("acqfromDt")))
            + fact("DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyToDate", iso(row.get("acqtoDt")))
            + fact("ModeOfAcquisitionOrDisposal", row.get("acqMode"))
            + "</xbrli:xbrl>")


def world_filings(pit: list[dict]) -> list[dict]:
    """The list's rows for the world's disclosures: one filing each, at the time the row says it was filed."""
    out = []
    for i, row in enumerate(pit):
        filed = _day(row.get("date")) or _day(row.get("acqtoDt"))
        out.append({"appId": str(9000 + i), "symbol": row.get("symbol"), "companyName": "Reliance Industries Limited",
                    "regulation": "Regulation 7 (2)", "typeOfSubmission": "Original", "prevAppId": None, "revisionRemark": None,
                    "broadcastDateTime": filed.strftime("%d-%b-%Y %H:%M:%S") if filed else None,
                    "ixbrl": f"{ARCHIVE}ixbrl/IT_W{i}_WEB.html", "xmlFileName": f"{ARCHIVE}xbrl/IT_W{i}_WebXMLFile.xml"})
    return out


def world_answer(r: httpx.Request, pit: list[dict]):
    """The world's answer for an insider-trading path, or None when it isn't one."""
    if r.url.path == "/api/corporates-pit":
        return httpx.Response(200, json={"acqNameList": [], "data": []})
    if r.url.path == "/api/corporates-pit-gg":       # any window: like the world's other deal feeds, the dates aren't applied
        sym = r.url.params.get("symbol")
        return httpx.Response(200, json={"data": [x for x in world_filings(pit) if not sym or x["symbol"] == sym]})
    name = r.url.path.rsplit("/", 1)[-1]
    if r.url.path.startswith("/corporate/xbrl/IT_W") and name.endswith("_WebXMLFile.xml"):
        try:
            row = pit[int(name[4:].split("_", 1)[0])]
        except (ValueError, IndexError):
            return httpx.Response(404, text="Not found")
        return httpx.Response(200, text=document(row), headers={"content-type": "application/xml"})
    return None
