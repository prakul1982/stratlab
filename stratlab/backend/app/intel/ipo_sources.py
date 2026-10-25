"""The public sources behind the IPO section (ipo.py): what the exchanges, the regulators and the US calendar say about each
issue, read into one row shape. Nothing here forecasts a listing or says what to do with an issue.

India (every field comes from one of these, and the page says which):
  - NSE's public-issue pages: the upcoming list, the issues open now, the past issues (with their listing date), and each
    issue's own page (issue period, price band, bid lot, the issue's size in words, the offer document, and the bids
    received by category, counted over both exchanges while it is open, and again when it has closed).
  - BSE's public-issue list: dates, price band and size of the issues on its main board and its SME platform (the
    issues NSE does not list), and its table of how listed issues have traded since their listing.
  - SEBI's lists of draft offer documents (DRHP) and red herring documents (RHP) filed with it.
US: the public IPO calendar (intel/us_calendar.py: expected, priced and filed offerings) and the SEC's EDGAR filings
(the S-1 or F-1 and its amendments, and the final prospectus). Both are read from the server; the names of the sources
that are not regulators are never shown to users."""
import html as htmllib
import re
from datetime import date, datetime

from .net import BROWSER_UA, Source, SourceError, num

SEC_UA = "StratLab research (contact@stratlab.studio)"      # the SEC asks automated users to say who they are
SEBI_LISTING = "/sebiweb/home/HomeAction.do"
SEBI_KINDS = {"draft": 10, "red_herring": 11}               # the listings' own numbers (smid) for the two lists read here
SERIES_SEGMENT = {"EQ": "mainboard", "BE": "mainboard", "SME": "sme"}      # NSE's series; DEBT and the like are not shares
OFFER_FORMS = ("S-1", "S-1/A", "F-1", "F-1/A", "424B4", "424B1", "424B3", "424B5")      # the filings an IPO's documents are among
DOC_RANK = {"424B4": 5, "424B1": 5, "424B3": 4, "424B5": 4, "S-1/A": 3, "F-1/A": 3, "S-1": 2, "F-1": 2}   # which is the one to read


# ---------- small readers ----------
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def day_of(s) -> date | None:
    """A day written 30-Oct-2026, 19-OCT-2026, 2026-10-23, 2026-10-23T00:00:00, 10/22/2026 or Oct 21, 2026; else None."""
    t = str(s or "").strip()
    if not t or t == "-":
        return None
    for fmt, cut in (("%Y-%m-%d", 10), ("%d-%b-%Y", 11), ("%m/%d/%Y", 10), ("%b %d, %Y", 12), ("%d %b %Y", 11)):
        try:
            return datetime.strptime(t[:cut].title() if "%b" in fmt else t[:cut], fmt).date()
        except ValueError:
            continue
    return None


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def whole(s) -> int | None:
    """1,36,00,000 or 17000000 or 3.028233E7 as a whole number of shares."""
    n = num(s)
    return int(round(n)) if n is not None and n >= 0 else None


def band(text) -> tuple[float | None, float | None]:
    """(low, high) of "Rs.153 to Rs.162", "Rs. 153 to  Rs. 162 per Equity shares", "1585.00 - 1665.00" or a single price
    ("Rs.94", "586"): the low and high are the same for a single price."""
    nums = [n for n in (num(x) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", str(text or ""))) if n and n > 0]
    if not nums:
        return None, None
    return (nums[0], nums[1]) if len(nums) >= 2 else (nums[0], nums[0])


def name_key(name) -> str:
    """A company's name reduced for matching it across lists: lower case, no "Limited", "Ltd", "Pvt" or punctuation."""
    t = re.sub(r"\(.*?\)", " ", str(name or "").lower().replace("&", " and "))
    t = re.sub(r"\b(limited|ltd|pvt|private|public|the|inc|corp|corporation|co|company|plc|holdings?)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def clean(s) -> str:
    return " ".join(htmllib.unescape(str(s or "")).split())


# an exchange names an issue that did not go ahead in its list: "ABC Limited-Issue Withdrawn", "ABC Limited - Issue postponed"
ISSUE_STATUS = re.compile(r"\s*[-–—:]?\s*\(?\s*(?:issue\s+)?(withdrawn|postponed|deferred|cancell?ed)\s*\)?\s*$", re.I)
# the Social Stock Exchange's fund raises are listed beside the IPOs: a zero coupon, zero principal instrument of a "For Profit
# Social Enterprise" or a "Not for Profit Organisation", not shares
SOCIAL = re.compile(r"\s*[-–—:]?\s*\(?\s*(?:(?:for[- ]profit social enterprise|not[- ]for[- ]profit organi[sz]ation|social stock exchange)"
                    r"\s*(?:\(\s*(?:FPSE|NPO|SSE)\s*\))?|(?:FPSE|NPO))\s*\)?\s*$", re.I)
STATUS_WORD = {"withdrawn": "withdrawn", "postponed": "postponed", "deferred": "postponed", "cancelled": "cancelled", "canceled": "cancelled"}


def classify(name) -> tuple[str, str | None, bool]:
    """(the company's name without the exchange's note, "withdrawn" / "postponed" / "cancelled" or None, whether the listing is a
    Social Stock Exchange fund raise): "Zenith Foods Limited-Issue Withdrawn" is ("Zenith Foods Limited", "withdrawn", False)."""
    n, status, social = clean(name), None, False
    for _ in range(2):                       # a note may stand behind another ("... (FPSE) - Issue Withdrawn")
        m = ISSUE_STATUS.search(n)
        if m and m.start() > 0:
            status, n = status or STATUS_WORD[m.group(1).lower()], n[:m.start()].rstrip(" -–—:,")
            continue
        m = SOCIAL.search(n)
        if m and m.start() > 0:
            social, n = True, n[:m.start()].rstrip(" -–—:,")
            continue
        break
    return n, status, social


def _note(row: dict, status: str | None, social: bool) -> None:
    """The exchange's note on an issue onto its row, only when there is one (a normal issue's row is unchanged)."""
    if status:
        row["issue_status"] = status
    if social:
        row["social"] = True


# ---------- NSE ----------
def nse_upcoming(raw) -> list[dict]:
    """NSE's list of issues still to open: [{symbol, name, series, segment, open, close, low, high, size_shares}]. An empty
    list comes as {} or []."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not r.get("symbol"):
            continue
        seg = SERIES_SEGMENT.get(str(r.get("series") or "EQ").upper())
        low, high = band(r.get("issuePrice"))
        if seg is None:
            continue
        name, status, social = classify(r.get("companyName"))
        out.append({"symbol": str(r["symbol"]).strip().upper(), "name": name, "series": r.get("series"),
                    "segment": seg, "open": iso(day_of(r.get("issueStartDate"))), "close": iso(day_of(r.get("issueEndDate"))),
                    "low": low, "high": high, "size_shares": whole(r.get("issueSize"))})
        _note(out[-1], status, social)
    return out


def nse_current(raw) -> list[dict]:
    """NSE's list of issues open now, in the same shape (it names the symbol, series, dates, price and size the way the upcoming
    list does)."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not r.get("symbol"):
            continue
        seg = SERIES_SEGMENT.get(str(r.get("series") or "EQ").upper())
        low, high = band(r.get("issuePrice") or r.get("priceBand"))
        if seg is None:
            continue
        name, status, social = classify(r.get("companyName"))
        out.append({"symbol": str(r["symbol"]).strip().upper(), "name": name, "series": r.get("series"),
                    "segment": seg, "open": iso(day_of(r.get("issueStartDate"))), "close": iso(day_of(r.get("issueEndDate"))),
                    "low": low, "high": high, "size_shares": whole(r.get("issueSize") or r.get("noOfSharesOffered"))})
        _note(out[-1], status, social)
    return out


def nse_past(raw) -> list[dict]:
    """NSE's past issues: [{symbol, name, series, segment, open, close, listing, low, high, price}]. `listing` is None until
    the exchange has a listing date ("-"); `price` is the issue price once it is fixed."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not r.get("symbol"):
            continue
        seg = SERIES_SEGMENT.get(str(r.get("securityType") or "").upper())
        if seg is None:
            continue
        low, high = band(r.get("priceRange"))
        price = num(r.get("issuePrice"))
        name, status, social = classify(r.get("company"))
        out.append({"symbol": str(r["symbol"]).strip().upper(), "name": name, "series": r.get("securityType"),
                    "segment": seg, "open": iso(day_of(r.get("ipoStartDate"))), "close": iso(day_of(r.get("ipoEndDate"))),
                    "listing": iso(day_of(r.get("listingDate"))), "low": low, "high": high or price,
                    "price": price if price and price > 0 else None})
        _note(out[-1], status, social)
    return out


# the sub-rows of a subscription table that say nothing a reader needs ("Cut Off" and "Price bids" under retail)
_SKIP_SUB = re.compile(r"^(cut ?off|price bids?)$", re.I)


def category_label(name: str, sr: str) -> str:
    """The exchange's category name in plain words: "Qualified Institutional Buyers(QIBs)" → "Qualified institutional buyers"."""
    n = clean(name)
    if re.match(r"qualified institutional", n, re.I):
        return "Qualified institutional buyers"
    if re.match(r"non.?institutional", n, re.I):
        if re.search(r"more than ten lakh", n, re.I):
            return "Non-institutional, bids over ₹10 lakh"
        if re.search(r"two lakh.*(?:upto|up to|to).*ten lakh", n, re.I):
            return "Non-institutional, bids of ₹2 lakh to ₹10 lakh"
        return "Non-institutional investors"
    if re.match(r"retail", n, re.I):
        return "Retail individual investors"
    if re.match(r"employee", n, re.I):
        return "Employees"
    if re.match(r"shareholder", n, re.I):
        return "Shareholders"
    if re.match(r"market maker", n, re.I):
        return "Market maker"
    if re.match(r"total", n, re.I):
        return "Total"
    return re.sub(r"\s*\(.*?\)\s*", " ", n).strip().capitalize()


def subscription(rows: list, stamp=None, times: float | None = None) -> dict | None:
    """The bids received by category: [{label, sr, offered, bid, times}] for the main categories (and the two non-institutional
    bands), and the total. `rows` are the exchange's rows (key names differ between its answers; an SME issue's rows have no
    size per category, only the bids). `times` is the exchange's own count for the whole issue, used when the total row has
    none. None until some bid is in (an issue that has not opened shows all zeros)."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        sr = str(r.get("srNo") or "").strip()
        if sr in ("Sr.No.",):
            continue
        offered = num(r.get("noOfSharesOffered", r.get("noOfShareOffered")))
        bid = num(r.get("noOfsharesBid", r.get("noOfSharesBid", r.get("noOfshareBid"))))
        got = num(r.get("noOfTime", r.get("noOfTotalMeant")))
        name = clean(r.get("category"))
        is_total = bool(re.match(r"total", name, re.I))
        main = is_total or bool(re.fullmatch(r"\d+(\.\d+)?", sr))      # 1, 2, 2.1, 2.2, 3, 4; not 1(a), 2.1(b), 3(a)
        if not main or _SKIP_SUB.match(name) or (not is_total and not offered and not bid):
            continue
        out.append({"label": category_label(name, sr), "sr": sr or "total", "offered": int(offered) if offered else None,
                    "bid": int(bid) if bid is not None else None, "times": round(got, 2) if got else None})
    total = next((r for r in out if r["sr"] == "total"), None)
    if not out or not total or not (total.get("bid") or 0) > 0:
        return None
    if not total["times"] and times:
        total["times"] = round(times, 2)
    return {"rows": out, "times": total["times"], "as_of": clean(stamp) or None}


def _as_of(text) -> str | None:
    """"Updated as on 19-Oct-2026 19:00:47 hrs" / "As on 19-Oct-2026 19:00:00 IST" → "2026-10-19 19:00"."""
    m = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(\d{1,2}:\d{2})", str(text or ""))
    d = day_of(m.group(1)) if m else None
    return f"{d.isoformat()} {m.group(2)}" if d else None


ISSUE_SHARES = re.compile(r"([\d,]{4,})\s*(?:fully paid[- ]up\s*)?equity shares", re.I)
AMOUNT = r"(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d+)?)\s*(million|mn|lakhs?|lacs?|crores?|cr)\b"
TO_CRORE = {"million": 0.1, "mn": 0.1, "lakh": 0.01, "lakhs": 0.01, "lac": 0.01, "lacs": 0.01, "crore": 1.0, "crores": 1.0, "cr": 1.0}


def _crore(m) -> float | None:
    n = num(m.group(1)) if m else None
    return round(n * TO_CRORE[m.group(2).lower()], 2) if n else None


def issue_split(text) -> dict:
    """Fresh issue and offer for sale in an issue's own words ("Fresh issue up to 1,36,00,000 Equity Shares and offer for sale
    up to 34,00,000 Equity shares", or "Fresh Issue aggregating upto Rs. 5000 million and Offer for Sale aggregating upto
    Rs.2020 million"): {fresh, ofs} in shares and {fresh_cr, ofs_cr} in rupees crore, each None when the words don't give it,
    and {total_cr} when they give a total ("aggregating to 4,283.02 lakhs")."""
    t = clean(text)
    out = {"fresh": None, "ofs": None, "fresh_cr": None, "ofs_cr": None, "total_cr": None}
    fresh = re.search(r"fresh issue\b(.{0,90}?)(?=offer for sale|offer-for-sale|\bofs\b|$)", t, re.I)
    sale = re.search(r"(?:offer for sale|offer-for-sale|\bofs\b)\b(.{0,120})", t, re.I)
    for key, m in (("fresh", fresh), ("ofs", sale)):
        part = m.group(1) if m else ""
        sh = re.search(r"([\d,]{4,})\s*(?:fully paid[- ]up\s*)?equity", part, re.I)
        am = re.search(AMOUNT, part, re.I)
        if sh and not (am and am.start() < sh.start()):
            out[key] = whole(sh.group(1))
        elif am:
            out[key + "_cr"] = _crore(am)
    # a plain issue of N shares: "Initial Public Offer of 45,56,400 Equity Shares at the aggregating to 4,283.02 lakhs"
    if out["fresh"] is None and out["ofs"] is None and out["fresh_cr"] is None and out["ofs_cr"] is None:
        m = ISSUE_SHARES.search(t)
        if m and re.search(r"offer for sale|\bofs\b", t, re.I) and not re.search(r"fresh", t, re.I):
            out["ofs"] = whole(m.group(1))
        elif m and re.search(r"fresh", t, re.I) and not re.search(r"offer for sale|\bofs\b", t, re.I):
            out["fresh"] = whole(m.group(1))
        tot = re.search(r"aggregating (?:up ?to |to )?(?:Rs\.?\s*)?([\d,]+(?:\.\d+)?)\s*(million|mn|lakhs?|lacs?|crores?|cr)\b", t, re.I)
        if tot:
            out["total_cr"] = _crore(tot)
        if m and out["fresh"] is None and out["ofs"] is None and re.search(r"initial public offer", t, re.I):
            out["fresh"] = whole(m.group(1))              # an issue of shares with no word of a sale: all new shares
    return out


def nse_detail(raw) -> dict:
    """One issue's own page on NSE, read into facts. {} when it is not an issue page.
    Keys: isin, industry, listing (ISO day), open, close, low, high, face_value, lot, retail_max, issue_text, fresh, ofs,
    issue_type, lead_managers, registrar, docs [{kind, label, url}], subscription (None until bids are in)."""
    if not isinstance(raw, dict) or not ((raw.get("issueInfo") or {}).get("dataList")):
        return {}
    meta = raw.get("metaInfo") if isinstance(raw.get("metaInfo"), dict) else {}
    info = {}
    for r in ((raw.get("issueInfo") or {}).get("dataList") or []):
        if isinstance(r, dict) and r.get("title"):
            info[clean(r["title"]).lower()] = clean(r.get("value")).strip('"').strip()
    out = {"isin": meta.get("isin") or None, "industry": meta.get("industry") or None, "listing": iso(day_of(meta.get("listingDate")))}
    period = re.findall(r"\d{1,2}-[A-Za-z]{3}-\d{4}", info.get("issue period", ""))
    out["open"] = iso(day_of(period[0])) if period else None
    out["close"] = iso(day_of(period[1])) if len(period) > 1 else None
    out["low"], out["high"] = band(info.get("price range"))
    fv = re.search(r"([\d.]+)", info.get("face value", ""))
    out["face_value"] = num(fv.group(1)) if fv else None
    lot = re.search(r"([\d,]+)", info.get("bid lot", "") or info.get("lot size", "") or info.get("market lot", "") or info.get("minimum order quantity", ""))
    out["lot"] = whole(lot.group(1)) if lot else None
    rm = re.search(r"Rs\.?\s*([\d,]+)", info.get("maximum subscription amount for retail investor", ""), re.I)
    out["retail_max"] = whole(rm.group(1)) if rm else None
    out["issue_text"] = info.get("issue size") or None
    out.update({k: v for k, v in issue_split(info.get("issue size")).items()})
    out["issue_type"] = info.get("issue type") or None
    leads = info.get("book running lead managers") or info.get("lead manager") or info.get("lead managers") or ""
    out["lead_managers"] = [clean(x) for x in re.split(r",| and (?=[A-Z])", leads) if clean(x)][:8]
    out["registrar"] = info.get("name of the registrar") or None
    docs = []
    for title, value in info.items():
        if re.search(r"prospectus|offer document|abridged", title) and re.match(r"https://nsearchives\.nseindia\.com/\S+", value):
            kind = "DRHP" if "draft" in title else "RHP" if "red herring" in title else "Prospectus"
            docs.append({"kind": kind, "label": title.title(), "url": value.split()[0]})
    out["docs"] = docs
    # the bids counted over both exchanges (activeCat), else NSE's own (bidDetails)
    active = raw.get("activeCat") if isinstance(raw.get("activeCat"), dict) else {}
    graph = raw.get("demandGraphALL") if isinstance(raw.get("demandGraphALL"), dict) and raw["demandGraphALL"].get("TOTAL_BIDS") else raw.get("demandGraph")
    count = num((graph or {}).get("noOfTimesIssueSubscribed")) if isinstance(graph, dict) else None
    sub = subscription(active.get("dataList"), active.get("updateTime"), count)
    out["subscription"] = sub or subscription(raw.get("bidDetails"), None, count)
    if out["subscription"] and not out["subscription"].get("as_of"):
        out["subscription"]["as_of"] = _as_of(((raw.get("demandGraphALL") or {}).get("timestamp")) or ((raw.get("demandGraph") or {}).get("timestamp")))
    if out["subscription"]:
        out["subscription"]["as_of"] = _as_of(out["subscription"]["as_of"]) or out["subscription"]["as_of"]
    return out


def nse_zip_pdf(names: list[str]) -> str | None:
    """Which file in an offer document's ZIP is the document itself (the ZIP also holds the general information document)."""
    pdfs = [n for n in names if n.lower().endswith(".pdf") and not n.endswith("/")]
    best = [n for n in pdfs if re.search(r"red herring|rhp|prospectus|drhp|offer document", n, re.I) and not re.search(r"gid|general information|abridged|addend", n, re.I)]
    return (best or [n for n in pdfs if not re.search(r"gid|general information", n, re.I)] or [None])[0]


# ---------- BSE ----------
def bse_issues(raw) -> list[dict]:
    """BSE's public-issue list, the initial public offers only (it also lists rights issues, buy-backs and debt):
    [{code, name, segment, open, close, low, high, face_value, size_shares, status, ipo_no}]. status: F forthcoming, L live."""
    out = []
    for r in ((raw or {}).get("Table") if isinstance(raw, dict) else None) or []:
        if not isinstance(r, dict) or str(r.get("IR_flag") or "").upper() != "IPO":
            continue
        plat = str(r.get("eXCHANGE_PLATFORM") or "").lower()
        seg = "sme" if plat == "sme" else "mainboard" if plat == "mainboard" else None
        if seg is None or not r.get("Scrip_cd"):
            continue
        low, high = band(r.get("Price_Band"))
        name, status, social = classify(r.get("LONG_NAME") or r.get("Scrip_Name"))
        out.append({"code": str(r["Scrip_cd"]), "name": name, "segment": seg,
                    "open": iso(day_of(r.get("Start_Dt"))), "close": iso(day_of(r.get("End_Dt"))), "low": low, "high": high,
                    "face_value": num(r.get("Face_Val")), "size_shares": whole(r.get("IssueSize")), "status": str(r.get("Status") or ""),
                    "ipo_no": r.get("IPO_NO")})
        _note(out[-1], status, social)
    return out


def bse_performance(raw) -> list[dict]:
    """BSE's table of how its listed issues have traded: [{name, short, issue_price, listed, day_close, latest, url}]."""
    out = []
    for r in ((raw or {}).get("Table") if isinstance(raw, dict) else None) or []:
        if not isinstance(r, dict) or not r.get("CompanyName"):
            continue
        out.append({"name": clean(r["CompanyName"]), "short": clean(r.get("Company_Short_Name")), "issue_price": num(r.get("IssuePrice")),
                    "listed": iso(day_of(r.get("ListedOn"))), "day_close": num(r.get("ListingDayClose")), "latest": num(r.get("CurrentPrice")),
                    "url": r.get("IMAGE") if str(r.get("IMAGE") or "").startswith("https://www.bseindia.com/") else None})
    return out


# ---------- SEBI ----------
def sebi_listing(page: str) -> list[dict]:
    """SEBI's list of offer documents filed with it (one page of it): [{date, url, title, company, kind}]. kind: drhp, rhp,
    addendum, udrhp, prospectus or other."""
    out = []
    for m in re.finditer(r"<td>\s*([A-Z][a-z]{2} \d{1,2}, \d{4})\s*</td>\s*<td>\s*<a href=\"([^\"]+)\"[^>]*?title=\"([^\"<]*)", page or ""):
        d, url, title = day_of(m.group(1)), m.group(2), clean(m.group(3))
        if not d or not url.startswith("https://www.sebi.gov.in/"):
            continue
        low = title.lower()
        kind = ("udrhp" if "udrhp" in low else "addendum" if "addendum" in low else "corrigendum" if "corrigendum" in low
                else "drhp" if re.search(r"\bdrhp\b|draft red herring", low) else "rhp" if re.search(r"\brhp\b|red herring", low)
                else "prospectus" if "prospectus" in low and "abridged" not in low else "other")
        company = re.split(r"\s+[–-]\s+(?:DRHP|RHP|UDRHP|Addendum|Corrigendum|Prospectus|Draft)\b|\s*[–-]\s*(?:UDRHP|DRHP|RHP)", title, maxsplit=1, flags=re.I)[0]
        company = re.sub(r"\s*(?:-|–)?\s*(?:Addendum|Corrigendum)\b.*$", "", company, flags=re.I)
        out.append({"date": d.isoformat(), "url": url, "title": title, "company": clean(company), "kind": kind})
    return out


def sebi_entry_pdf(page: str) -> str | None:
    """The offer document's PDF on one of SEBI's filing pages (the viewer on the page loads it)."""
    m = re.search(r"file=(https://www\.sebi\.gov\.in/sebi_data/attachdocs/[^'\"&\s]+\.pdf)", page or "", re.I)
    return m.group(1) if m else None


# ---------- EDGAR ----------
def efts_hits(raw) -> list[dict]:
    """EDGAR's search answer as one row per filing: [{form, date, cik, name, symbol, accession, file}]."""
    out, seen = [], set()
    for h in (((raw or {}).get("hits") or {}).get("hits") or []) if isinstance(raw, dict) else []:
        s = h.get("_source") or {}
        names, ciks = s.get("display_names") or [], s.get("ciks") or []
        if not names or not ciks or not s.get("adsh") or s["adsh"] in seen:
            continue
        seen.add(s["adsh"])
        m = re.match(r"(.*?)\s{1,}(?:\(([A-Z0-9.,\- ]+)\)\s+)?\(CIK", names[0])
        out.append({"form": s.get("form"), "date": s.get("file_date"), "cik": str(ciks[0]).lstrip("0"), "name": clean(m.group(1) if m else names[0]),
                    "symbol": (m.group(2) or "").split(",")[0].strip() if m and m.group(2) else None,
                    "accession": s["adsh"], "file": str(h.get("_id") or "").partition(":")[2] or None})
    return out


def offering_docs(sub: dict) -> dict:
    """A company's IPO documents from its EDGAR filing list (data.sec.gov submissions): {cik, name, symbol, industry, docs} with
    docs [{form, date, url, link}] (`url` the document itself, `link` its filing page) newest first, the final prospectus ahead of an amendment ahead of the first filing."""
    rec = ((sub or {}).get("filings") or {}).get("recent") or {}
    cik = str((sub or {}).get("cik") or "").lstrip("0")
    docs = []
    for i, form in enumerate(rec.get("form") or []):
        if form not in OFFER_FORMS:
            continue
        try:
            acc, primary, filed = rec["accessionNumber"][i], rec["primaryDocument"][i], rec["filingDate"][i]
        except (KeyError, IndexError):
            continue
        if not primary or not cik:
            continue
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
        docs.append({"form": form, "date": filed, "url": f"{base}/{primary}", "link": f"{base}/{acc}-index.htm"})
    docs.sort(key=lambda d: (DOC_RANK.get(d["form"], 0), d["date"]), reverse=True)
    tickers = (sub or {}).get("tickers") or []
    return {"cik": cik, "name": clean((sub or {}).get("name")), "symbol": tickers[0] if tickers else None,
            "industry": clean((sub or {}).get("sicDescription")) or None, "docs": docs}


def filing_index(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"


# ---------- the sources ----------
class Sebi(Source):
    name = "SEBI"
    STALE_FOR = 5

    def __init__(self, transport=None):
        super().__init__("https://www.sebi.gov.in", per_minute=20, burst=4, transport=transport, timeout=25,
                         headers={"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})

    def listing(self, kind: str, ttl: float = 3 * 3600) -> list[dict]:
        """The newest page of SEBI's draft ("draft") or red herring ("red_herring") offer documents."""
        got = self.fetch(SEBI_LISTING, {"doListing": "yes", "sid": 3, "s": "", "ssid": 15, "smid": SEBI_KINDS[kind]}, ttl=ttl, kind="text")
        rows = sebi_listing(got)
        if not rows and "sample_1" not in str(got):
            raise SourceError(self.name, "SEBI sent something that isn't its list of offer documents.", busy=True)
        return rows

    def pdf(self, page_url: str, ttl: float = 24 * 3600) -> str | None:
        """The offer document's address on one of SEBI's filing pages."""
        path = page_url.removeprefix("https://www.sebi.gov.in")
        return sebi_entry_pdf(self.fetch(path, None, ttl=ttl, kind="text"))


class Edgar(Source):
    """The SEC's EDGAR: the full-text search (to find a company's IPO filing by name) and the filing lists (data.sec.gov)."""
    name = "The SEC"
    STALE_FOR = 5

    def __init__(self, transport=None):
        super().__init__("https://efts.sec.gov", per_minute=40, burst=5, transport=transport, timeout=25,
                         headers={"User-Agent": SEC_UA, "Accept": "application/json"})

    def search(self, name: str, since: date, until: date, ttl: float = 6 * 3600) -> list[dict]:
        got = self.fetch("/LATEST/search-index", {"q": f'"{name}"', "forms": ",".join(OFFER_FORMS), "dateRange": "custom",
                                                  "startdt": since.isoformat(), "enddt": until.isoformat()}, ttl=ttl)
        if not isinstance(got, dict) or "hits" not in got:
            raise SourceError(self.name, "The SEC sent something that isn't its search answer.", busy=True)
        return efts_hits(got)

    def filings(self, cik: str, ttl: float = 3 * 3600) -> dict:
        got = self.fetch(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", None, ttl=ttl)
        if not isinstance(got, dict) or "filings" not in got:
            raise SourceError(self.name, "The SEC sent something that isn't a filing list.", busy=True)
        return got

    def docs_for(self, name: str, today: date) -> dict | None:
        """The IPO documents of the company called `name`: the search finds its filings, the one whose name is the same."""
        want = name_key(name)
        if len(want) < 3:
            return None
        hits = [h for h in self.search(name, date(today.year - 2, today.month, 1), today) if name_key(h["name"]) == want]
        if not hits:
            return None
        return offering_docs(self.filings(hits[0]["cik"]))
