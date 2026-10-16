"""US holders above 5%, from the Schedule 13D and 13G filings in each company's SEC filing list.

Anyone who comes to hold more than 5% of a US company's shares files a Schedule 13D (an active stake) or 13G (a
passive one), and an amendment when it changes. The SEC lists these filings under the company they are about, so the
filing list the app already reads for the company pages has them: form, date and document. The holder's name and the
share of the class are in the document's cover page; they are read from it once per filing (a few at a time, newest
first) and stored, so a page never waits on the SEC.

Facts as filed: the form, the date, who filed and the percentage they reported. Nothing here says what a holder will do.
Stored with the red-flag filings (redflags.Months, prefix redflags:13dg:)."""
import re
from datetime import date, timedelta

# the forms as the SEC lists them: the older "SC 13D" and the "SCHEDULE 13D" used since December 2024
FORMS = {"SC 13D": ("13D", False), "SC 13D/A": ("13D", True), "SCHEDULE 13D": ("13D", False), "SCHEDULE 13D/A": ("13D", True),
         "SC 13G": ("13G", False), "SC 13G/A": ("13G", True), "SCHEDULE 13G": ("13G", False), "SCHEDULE 13G/A": ("13G", True)}
KIND_WORDS = {"13D": "Schedule 13D (active stake)", "13G": "Schedule 13G (passive stake)"}
LOOKBACK_DAYS = 400                 # how far back a company's list goes
NAME_MAX = 90


def filing_label(kind: str, amendment: bool) -> str:
    return f"{'Amendment to ' if amendment else ''}{KIND_WORDS[kind]}"


def items_from_subs(subs: dict, symbol: str, company: str | None, today: date, days: int = LOOKBACK_DAYS) -> list[dict]:
    """The 13D and 13G filings in a company's SEC filing list within `days`: [{id, symbol, company, at, form, kind,
    amendment, label, url, holder, pct, shares}] (holder, pct and shares are filled in by read_cover)."""
    rec = ((subs or {}).get("filings") or {}).get("recent") or {}
    forms, dates, accs, docs = (rec.get(k) or [] for k in ("form", "filingDate", "accessionNumber", "primaryDocument"))
    cik = int((subs or {}).get("cik") or 0)
    cut = (today - timedelta(days=days)).isoformat()
    out = []
    for form, at, acc, doc in zip(forms, dates, accs, docs):
        if form not in FORMS or not at or at < cut or not acc or filed_by(acc) == cik:
            continue
        kind, amend = FORMS[form]
        folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
        out.append({"id": f"{symbol}|{acc}", "symbol": symbol, "company": company, "at": at, "form": form, "kind": kind,
                    "amendment": amend, "label": filing_label(kind, amend), "url": f"{folder}/{doc}" if doc else folder + "/",
                    "holder": None, "pct": None, "shares": None, "read": False})
    return out


def filed_by(acc: str) -> int | None:
    """The CIK an accession number was filed under (its first ten digits: the filer or its agent)."""
    digits = re.sub(r"\D", "", acc or "")
    return int(digits[:10]) if len(digits) >= 10 else None


_SUFFIX = re.compile(r"\b(?:the|inc|incorporated|corp|corporation|co|company|ltd|plc|holdings?|group|n\.?a|llc|lp)\b\.?", re.I)


def _core(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _SUFFIX.sub(" ", (name or "").lower()))


def about_itself(item: dict) -> bool:
    """A filing the company made as a holder of someone else's shares, not one about the company. The SEC's filing list
    for a company also carries the 13D/13G filings it files itself (R43A-004: JPMorgan's list showed its own stakes in
    other companies as holders of JPM, one also under CPAY): filed under the company's own CIK, or naming the company as
    the reporting person."""
    m = re.search(r"/edgar/data/(\d+)/(\d{18})", item.get("url") or "")
    if m and int(m.group(1)) == filed_by(m.group(2)):
        return True
    holder, company = _core(item.get("holder") or ""), _core(item.get("company") or "")
    return bool(holder and company and holder == company)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_NAME = re.compile(r"names?\s+of\s+reporting\s+persons?\.?\s*(?P<name>.{2,260}?)\s+(?:\(?\s*2\s*\)?\s*\.?\s*)?check\s+the\s+appropriate", re.I)
_IRS = re.compile(r"(?:i\.?\s?r\.?\s?s\.?\s+identification\s+nos?\.?\s+of\s+above\s+persons?\s*(?:\(\s*entities\s+only\s*\))?|\(\s*entities\s+only\s*\))\s*", re.I)
_PCT = re.compile(r"percent\s+of\s+class\s+represented\s+by\s+amount\s+in\s+row\s*\(?\s*9\s*\)?\s*[:.]?\s*(?P<pct>\d{1,3}(?:\.\d+)?)\s*%?", re.I)
_SHARES = re.compile(r"aggregate\s+amount\s+beneficially\s+owned\s+by\s+each\s+reporting\s+person\s*[:.]?\s*(?P<n>\d[\d,]*(?:\.\d+)?)", re.I)


def read_cover(text: str) -> dict:
    """The first reporting person's name, the percent of the class and the shares from a 13D/13G document's text
    ("Names of Reporting Persons … Percent of class represented by amount in row (9)"). Anything not found is None;
    {"holder", "pct", "shares", "others"} (others: how many more reporting persons the cover lists)."""
    flat = _flat(text)
    out = {"holder": None, "pct": None, "shares": None, "others": 0}
    m = _NAME.search(flat)
    if m:
        name = _IRS.sub("", m.group("name")).strip(" :-")
        name = re.sub(r"\s+\d{2}-\d{7}$", "", name).strip()          # a tax number after the name
        if name and not re.fullmatch(r"[\d\s.,-]+", name):
            out["holder"] = name[:NAME_MAX]
    m = _PCT.search(flat)
    if m:
        try:
            pct = float(m.group("pct"))
            out["pct"] = pct if 0 < pct <= 100 else None
        except ValueError:
            pass
    m = _SHARES.search(flat)
    if m:
        try:
            out["shares"] = float(m.group("n").replace(",", ""))
        except ValueError:
            pass
    out["others"] = max(0, len(re.findall(r"names?\s+of\s+reporting\s+persons?", flat, re.I)) - 1)
    return out


def read_pending(items: list[dict], document, limit: int = 40) -> tuple[list[dict], int]:
    """Read the covers of items not read yet (newest first, at most `limit`) with `document(url) -> text`. Returns
    (the items that were read, how many reads failed). A filing whose cover can't be read is marked read all the
    same, so one odd document isn't asked for every day."""
    done, failed = [], 0
    for it in sorted((i for i in items if not i.get("read")), key=lambda i: i["at"], reverse=True)[:limit]:
        try:
            cover = read_cover(document(it["url"]))
        except Exception as e:
            failed += 1
            if getattr(e, "busy", False):          # the SEC is busy: stop, the rest wait for the next run
                break
            cover = {"holder": None, "pct": None, "shares": None, "others": 0}
        it.update(holder=cover["holder"], pct=cover["pct"], shares=cover["shares"], others=cover["others"], read=True)
        done.append(it)
    return done, failed
