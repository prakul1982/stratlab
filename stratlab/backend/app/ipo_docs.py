"""An IPO's offer document, read: the draft or red herring prospectus an Indian company files with SEBI, or the S-1, F-1 or
final prospectus a US company files with the SEC.

Two kinds of reading, kept apart:
  - Facts read by fixed rules from the places the document always puts them (the cover page's promoters and selling
    shareholders, the "Objects of the Offer" section, the summary financial tables, a US prospectus's offering terms and
    use of proceeds). Each carries the page it came from, and a fact the rules can't find is left out, never guessed.
    These are on the IPO's page for everyone (ipo.py).
  - A summary the AI writes from the document's own passages (Basic and up): every statement has to carry a quote that
    is really in the document (docs.quote_found), and a sentence that sounds like advice is dropped. It is made once per
    document and kept for everyone (ipo:sum:<document>).

Facts only, in the document's own words and figures. Nothing here says whether an issue is worth applying for."""
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone

import httpx

from . import db, docs
from .ai_providers import AIError, complete, extract_json
from .http_retry import real_transport
from .intel.ipo_sources import SEC_UA, nse_zip_pdf
from .intel.net import BROWSER_UA, SourceError

SUM_KEY = "ipo:sum:"                  # ipo:sum:<document id> = the AI's summary of that document, once
FACTS_KEY = "ipo:facts:"              # ipo:facts:<document id> = the facts read from it by rules
HOSTS = ("nsearchives.nseindia.com", "archives.nseindia.com", "www.sebi.gov.in", "www.sec.gov")
MAX_BYTES = 40 * 1024 * 1024          # a red herring prospectus with its annexures runs to 15 MB, a US prospectus to 60 MB of pictures
HTML_HEAD = 3_600_000                 # the first part of a US prospectus holds everything read here (the summary, the risks, the proceeds)
MAX_PAGES = 190                       # pages of an Indian offer document read (the summary tables, the objects and the business are in them)
READER = 2                            # how the documents are read: raise it to read them again (2: the proceeds table, the first risk factors, the KPIs, the shareholding and the peer ratios, O7)
SUMMARY_READER = 2                    # (2: the business and its segments only: the rest is read by rules into tables)


def doc_id(url: str) -> str:
    """A short stable id for a document's address."""
    return hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:16]


# ---------- fetching ----------
def _client(transport=None) -> httpx.Client:
    return httpx.Client(timeout=60, transport=transport or real_transport(), follow_redirects=False,
                        headers={"User-Agent": BROWSER_UA, "Accept": "application/pdf,text/html,*/*;q=0.8"})


def download(url: str, limit: int = MAX_BYTES, head: int | None = None, transport=None) -> bytes:
    """The body at `url` (an exchange's, SEBI's or the SEC's own host only), following redirects that stay on those hosts.
    `head`: only its first bytes (a US prospectus is read from its start)."""
    target = url
    try:
        with _client(transport) as http:
            for _ in range(4):
                u = httpx.URL(target)
                if u.scheme != "https" or u.host not in HOSTS:
                    raise SourceError("the document's site", "That document isn't on an exchange's, SEBI's or the SEC's own site.")
                headers = {"User-Agent": SEC_UA, "Accept": "text/html,*/*;q=0.8"} if u.host.endswith("sec.gov") else \
                    {"Referer": "https://www.nseindia.com/"} if "nseindia" in u.host else {"Referer": "https://www.sebi.gov.in/"}
                with http.stream("GET", target, headers=headers) as r:
                    if 300 <= r.status_code < 400:
                        target = str(httpx.URL(target).join(r.headers.get("location", "")))
                        continue
                    if r.status_code >= 400:
                        raise SourceError("the document's site", f"The document couldn't be downloaded ({r.status_code}).", busy=r.status_code >= 500 or r.status_code == 429)
                    buf = bytearray()
                    cap = head or limit
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) >= cap:
                            if head:
                                return bytes(buf[:head])
                            raise SourceError("the document's site", "The document is too large to read here.")
                    return bytes(buf)
    except httpx.HTTPError as e:
        raise SourceError("the document's site", f"Couldn't reach the document ({e.__class__.__name__}).", busy=True) from None
    raise SourceError("the document's site", "The document moved too many times.")


def pdf_from(data: bytes) -> bytes:
    """The offer document's PDF: the bytes themselves, or the one inside a ZIP (NSE serves each issue's documents zipped)."""
    if data[:4] == b"PK\x03\x04":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise SourceError("the document's site", "The offer document's ZIP couldn't be opened.") from None
        pick = nse_zip_pdf(z.namelist())
        if not pick:
            raise SourceError("the document's site", "The ZIP holds no offer document.")
        data = z.read(pick)
    if not data[:5].startswith(b"%PDF"):
        raise SourceError("the document's site", "The link didn't return a PDF.")
    return data


def pdf_pages(data: bytes, max_pages: int = MAX_PAGES) -> list[str]:
    """The text of each page (the first `max_pages`), one string per page."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out = []
    for page in reader.pages[:max_pages]:
        try:
            out.append(docs.fix_rupee(page.extract_text() or ""))
        except Exception:              # one bad page mustn't lose the document
            out.append("")
    return out


def html_text(raw: bytes) -> str:
    """A US prospectus's text from the first part of its HTML: tags, scripts and styles dropped, entities read."""
    import html as htmllib
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", t)
    t = re.sub(r"(?i)</(p|div|tr|li|h\d|table)>|<br\s*/?>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = htmllib.unescape(t).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


# ---------- India: finding the places ----------
HEAD_SKIP = re.compile(r"\.{4,}|\s\d{1,3}\s*$")           # a contents line: dot leaders or a trailing page number


def section(pages: list[str], title: str, span: int = 6, start: int = 0) -> tuple[int, str] | None:
    """(page number, text) of the section headed `title` (a line by itself, in capitals, not a line of the contents or a
    cross-reference) and the next `span` pages. None when it isn't in the pages read."""
    pat = re.compile(rf"^\s*(?:SECTION [IVX]+\s*[–:-]\s*)?{title}\s*$", re.M)
    for i in range(start, len(pages)):
        m = pat.search(pages[i])
        if not m or HEAD_SKIP.search(m.group(0)):
            continue
        body = pages[i][m.start():] + "\n" + "\n".join(f"\n<<{j + 1}>>\n{pages[j]}" for j in range(i + 1, min(len(pages), i + span)))
        return i + 1, body
    return None


def _flat(s: str) -> str:
    return " ".join(s.split())


# ---------- India: the facts ----------
def promoters(pages: list[str]) -> list[str]:
    """The promoters named on the cover: "OUR PROMOTERS: A, B AND C" (in capitals)."""
    cover = "\n".join(pages[:4])
    m = re.search(r"(?:OUR PROMOTERS?|THE PROMOTERS? OF OUR COMPANY|PROMOTERS? OF OUR COMPANY)\s*(?:ARE)?\s*:\s*(.+?)(?:\n\s*(?:DETAILS|TYPE|FRESH|OFFER|THE OFFER|[A-Z ]{12,}:)|\n\n)", cover, re.S)
    if not m:
        return []
    names = re.split(r",\s*(?:AND\s+)?|\s+AND\s+|\n", _flat(m.group(1)).strip(" ."))
    out = []
    for n in names:
        n = n.strip(" .")
        if 3 <= len(n) <= 70 and not re.search(r"\d|DETAILS|OFFER", n):
            out.append(n.title().replace("S.P.A", "S.p.A").replace("S.R.L", "S.r.l").replace("Llp", "LLP").replace("Llc", "LLC"))
    return out[:12]


SELLER = re.compile(r"(Promoter Group|Promoter|Investor|Other|Individual)\s*Selling\s*Share\s*holders?", re.I)
ENDS_ENTRY = re.compile(r"million|negligible|^[\d.]+[#^*]*$|^Up to|Equity Shares?\b.*aggregating", re.I)


def selling_holders(pages: list[str]) -> list[dict]:
    """The selling shareholders in the cover's table: [{name, kind}], kind "Promoter", "Promoter Group", "Investor" or "Other".
    A table the rules can't tell apart (columns side by side) gives none; the page then says to see the document."""
    cover = "\n".join(pages[:4])
    start = re.search(r"DETAILS OF THE (?:OFFER FOR SALE|SELLING SHAREHOLDER)", cover, re.I)
    if not start:
        return []
    end = re.search(r"\n\s*(?:\^|#|\*|\(\d\)|RISKS? IN RELATION|GENERAL RISK|LISTING)", cover[start.end():])
    lines = [ln.strip() for ln in cover[start.end(): start.end() + (end.start() if end else 3000)].split("\n") if ln.strip()]
    out, seen = [], set()
    for i, ln in enumerate(lines):
        m = SELLER.search(ln)
        if not m or re.match(r"(NAME OF|TYPE)", ln, re.I):
            continue
        name = re.split(r"[#^*]\s*", ln[: m.start()])[-1].strip(" ,")
        j = i - 1
        while j >= 0 and not (name and not name.startswith("(") and re.match(r"[A-Z0-9]", name)) or (j >= 0 and not ENDS_ENTRY.search(lines[j]) and not re.match(r"NAME OF|TYPE|SHARES|AMOUNT|WEIGHTED", lines[j], re.I) and len(name) < 90 and name != ln[: m.start()].strip(" ,") and j >= i - 5):
            if j < 0 or ENDS_ENTRY.search(lines[j]) or re.match(r"NAME OF|TYPE|SHARES|AMOUNT|WEIGHTED|ACQUISITION", lines[j], re.I):
                break
            name = (lines[j] + " " + name).strip(" ,")
            j -= 1
        name = re.split(r"[#^*]\s*", _flat(name))[-1]
        name = re.sub(r"\s*\((?:represented|held|vide|through|acting)\b.*$", "", name, flags=re.I)
        name = re.sub(r"\s*\(?(?:held jointly|jointly with).*$", "", name, flags=re.I).strip(" ,(")
        kind = m.group(1).title()
        key = re.sub(r"\W+", "", name.lower())
        if 3 <= len(name) <= 90 and not re.search(r"\d{3}|[)]$", name) and key not in seen:
            seen.add(key)
            out.append({"name": name, "kind": kind})
    return out[:14]


def objects(pages: list[str]) -> dict | None:
    """What the issue's money is for, in the document's own words: {"page", "text"} (up to ~650 characters of "We propose to
    utilise the Net Proceeds towards ..." or "The objects of the Offer are ..."), or None."""
    got = section(pages, r"OBJECTS OF THE (?:OFFER|ISSUE)", span=5)
    if not got:
        return None
    page, text = got
    flat = _flat(re.sub(r"\n<<\d+>>\n", "\n", text))
    for pat in (r"(?:we|our company|the company)\s+propos(?:e|es|ed)\s+to\s+(?:utili[sz]e|deploy)\s+(?:the )?(?:net )?(?:proceeds|issue proceeds|offer proceeds)[^.]{0,40}(?:towards|for|in)\b.{40,900}",
                r"the objects of the (?:offer|issue) (?:are|is)\b.{30,900}"):
        m = re.search(pat, flat, re.I)
        if m:
            body = re.split(r"\s+(?:In addition to (?:the|these)|Further,|For further details|The objects as set out)", m.group(0), maxsplit=1)[0]
            return {"page": page, "text": clip_words(body, 650)}
    return None


def clip_words(text: str, size: int = 650) -> str:
    """`text` cut at a word (never inside one, RC2A-007: "...creating a public market fo"), with an ellipsis when it was cut."""
    t = _flat(text).rstrip(" ,;")
    if len(t) <= size:
        return t
    cut = t[:size].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def tidy_summary(items: dict | None) -> dict | None:
    """A stored summary's quotes with one an older read cut inside a word (300 characters, no ending) cut at the word before it."""
    if not items:
        return items

    def tidy(st):
        q = st.get("quote") if isinstance(st, dict) else None
        if q and len(q) >= 299 and not q.endswith((".", ")", "”", '"', "…", ";")):
            return {**st, "quote": clip_words(q, len(q) - 1)}
        return st

    return {k: (tidy(v) if isinstance(v, dict) else [tidy(x) for x in v] if isinstance(v, list) else v) for k, v in items.items()}


MONEY_TABLE = re.compile(r"\bS\.?\s*No\b.{0,30}\bParticulars\b", re.I)


def objects_view(obj: dict | None) -> dict | None:
    """The "objects of the offer" fact for the page. A text that is a table of the document (S. No., Particulars, amounts) is given as its
    lines too, [{"label", "figures"}], with the header's unit, so the page shows a list, not a run of numbers squeezed into a column
    (RC2A-007: Jio Platforms'); a text cut mid-word by an older read is cut at a word."""
    if not obj or not obj.get("text"):
        return obj
    text = _flat(obj["text"])
    out = {**obj, "text": text if len(text) < 640 or text.endswith((".", ")", "”", "…", ";")) else clip_words(text, len(text) - 1)}
    if MONEY_TABLE.search(text):
        head = re.search(r"\(\s*(?:in\s*)?(?:₹|Rs\.?|INR)\s*(?:in\s*)?(million|mn|lakhs?|crores?)\s*\)|\bin\s+(?:₹|Rs\.?\s*)?(million|mn|lakhs?|crores?)\b", text, re.I)
        body = text[head.end():] if head else MONEY_TABLE.sub("", text, count=1)
        items = []
        for m in re.finditer(r"(?:^|\s)(\d{1,2})\.\s+(.+?)(?=\s\d{1,2}\.\s+[A-Z(]|$)", body.strip()):
            label, figs = m.group(2), []
            while (t := re.search(r"\s((?:\[●\]|[\d,]+(?:\.\d+)?)[*#^]*)$", label)):
                figs.insert(0, t.group(1))
                label = label[:t.start()]
            if label.strip():
                items.append({"label": label.strip(" ,;"), "figures": " ".join(figs) or None})
        if len(items) >= 2:
            out["table"] = {"unit": (head.group(1) or head.group(2)).lower() if head else None, "rows": items[:12]}
            out["text"] = text[:MONEY_TABLE.search(text).start()].strip()         # (the lead-in; the lines are the table)
    return out


MONTH_END = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s*(\d{4})")
TO_CRORE = {"million": 0.1, "mn": 0.1, "lakh": 0.01, "lakhs": 0.01, "crore": 1.0, "crores": 1.0}
UNIT = re.compile(r"(?:₹|Rs\.?|INR)\s*(?:in\s*)?(million|mn|lakhs?|crores?)|\bin\s+(?:₹|Rs\.?\s*)?(million|mn|lakhs?|crores?)\b|\b(million|lakhs?|crores?)\b", re.I)
NUM = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?\)?(?![\w.])|(?<![\w-])-(?![\w-])")      # a figure, or a dash for nil
PREFIX = r"(?:\(?[a-z0-9]{1,3}\)\s*|\(?[IVX]{1,5}\)?\.?\s+|\d{1,2}\.\s+)?"
FIN_LABELS = (("revenue", re.compile(r"\bRevenue\s+from\s+operations\b", re.I), None),
              ("income", re.compile(r"\bTotal\s+income\b", re.I), re.compile(r"expense|comprehensive", re.I)),
              ("profit", re.compile(r"\b(?:profit|loss)\b.{0,40}\b(?:after tax|for the (?:year|period)|from the (?:year|period)|for the period/year)", re.I),
               re.compile(r"before|continuing|discontinued|comprehensive|attributable|share of|per share|exceptional|equity holders|other than", re.I)))


FIN_NAME = {"revenue": "Revenue from operations", "income": "Total income", "profit": "Profit for the year"}


def _val(tok: str) -> float | None:
    t = tok.strip()
    if t == "-":
        return 0.0
    neg = (t.startswith("(") and t.endswith(")")) or t.startswith("-")
    try:
        v = float(re.sub(r"[(),\-]", "", t))
    except ValueError:
        return None
    return -v if neg else v


def table_rows(page: str) -> list[tuple[str, list[float | None]]]:
    """A page's table lines as (label, figures): a label that wraps over several lines is joined, and a line that ends in
    three or more figures closes it."""
    rows, buf = [], ""
    for ln in page.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        toks = list(NUM.finditer(ln))
        tail = []
        for m in reversed(toks):                        # the figures at the end of the line, if it ends in them
            if ln[m.end():].strip(" #^*") == "" or (tail and ln[m.end(): tail[-1].start()].strip() == ""):
                tail.append(m)
            else:
                break
        if len(tail) >= 3:
            first = tail[-1].start()
            rows.append((_flat(f"{buf} {ln[:first]}"), [_val(m.group()) for m in reversed(tail)]))
            buf = ""
        elif toks and not tail:
            buf = ln if len(ln) < 120 else ""
        else:
            buf = _flat(f"{buf} {ln}")[-200:]
    return rows


def financials(pages: list[str]) -> dict | None:
    """The last three financial years' revenue, total income and profit from the summary profit and loss, in crore:
    {"page", "unit", "years": ["Mar 2026", ...], "rows": [{key, label, values}]}. The tables lead with part-year columns
    and end with the three full years, so the last three figures on each line are the years; the years are named from the
    header's own dates and must be three year-ends a year apart. Anything the rules can't read this way gives None."""
    start = next((i for i, p in enumerate(pages) if re.search(r"^\s*SUMMARY (?:OF )?(?:THE )?FINANCIAL INFORMATION\s*$", p, re.M)
                  and not re.search(r"\.{4,}", p[:300])), None)
    if start is None:
        return None
    for i in range(start, min(len(pages), start + 12)):
        pg = pages[i]
        m = re.search(r"Revenue\s+from\s+operations", pg, re.I)
        if not m or not re.search(r"profit and loss|statement of profit", pg, re.I):
            continue
        head = _flat(pg[: m.start()])[-1500:]
        um = UNIT.search(head)
        unit = next((g for g in um.groups() if g), None).lower() if um else None
        dates = [(mm.group(1), int(mm.group(2)), int(mm.group(3))) for mm in MONTH_END.finditer(head)]
        years = dates[-3:]
        if unit not in TO_CRORE or len(years) < 3 or len({(a, b) for a, b, _ in years}) != 1:
            continue
        ys = [c for _, _, c in years]
        if len(set(ys)) != 3 or max(ys) - min(ys) != 2:
            continue
        found = table_rows(pg)
        rows = []
        for key, want, skip in FIN_LABELS:
            for label, vals in found:
                if want.search(label) and not (skip and skip.search(label)) and all(v is not None for v in vals[-3:]):
                    rows.append({"key": key, "label": FIN_NAME[key], "values": [round(v * TO_CRORE[unit], 2) for v in vals[-3:]]})
                    break
        if not any(r["key"] in ("revenue", "income") for r in rows):
            continue
        return {"page": i + 1, "unit": "₹ crore", "years": [f"{mn[:3]} {y}" for mn, _, y in years], "rows": rows}
    return None


# ---------- India: the tables of the red herring prospectus (O7) ----------
def _crore(v: float | None, unit: str = "million") -> float | None:
    return None if v is None else round(v * TO_CRORE[unit], 2)


def _amount(tok: str) -> float | None:
    """A figure of a table cell ("1,339.44", "(2.81)", "-", "[●]" is None, "NA" is None); a percent sign and a note mark are ignored."""
    t = tok.strip().rstrip("*#^%x")
    if not t or t in ("NA", "N.A.", "N.A", "[●]", "NM", "–"):
        return None
    return _val(t)


def utilisation(pages: list[str]) -> dict | None:
    """The table of how the net proceeds of the fresh issue are to be used (the "Utilisation of Net Proceeds" table, in the document's own
    ₹ million): {"page", "unit", "rows": [{"label", "amount"}]} in ₹ crore, an amount still to be fixed ("[●]", general corporate purposes)
    being None. The table's own total line is left out."""
    for i, pg in enumerate(pages):
        m = re.search(r"Utili[sz]ation of (?:the )?Net Proceeds\s*\n", pg)
        if not m or re.search(r"\.{4,}", pg[:400]):
            continue
        body = pg[m.end():] + "\n" + (pages[i + 1] if i + 1 < len(pages) else "")
        um = re.search(r"\(\s*(?:in\s*)?(?:₹|Rs\.?|INR)\s*(?:in\s*)?(million|mn|lakhs?|crores?)", body, re.I)
        if not um or "Particulars" not in body[um.end(): um.end() + 120]:
            continue
        unit = {"mn": "million"}.get(um.group(1).lower(), um.group(1).lower())
        if unit not in TO_CRORE:
            continue
        end = re.search(r"\n\s*\(\d\)\s|\nProposed Schedule|\nFor further details", body[um.end():])
        tbl = body[um.end(): um.end() + (end.start() if end else 1500)]
        lines = [ln.strip() for ln in tbl.split("\n") if ln.strip()]
        rows, buf = [], ""
        for ln in lines:
            ln = ln.lstrip(") ").strip()
            if not ln:
                continue
            if re.match(r"Particulars", ln, re.I) or re.match(r"^(?:<<\d+>>|\d{1,4}|\))$", ln):
                continue
            m2 = re.search(r"((?:Up to\s+)?[\d,]+(?:\.\d+)?|\[●\])\s*$", ln)
            if m2 and (buf or re.search(r"[A-Za-z]", ln[: m2.start()])):
                label = _flat(f"{buf} {ln[: m2.start()]}").strip(" ,;")
                label = re.sub(r"\s*\(\d\)$", "", label)
                if label and not re.match(r"(?:Total|Net Proceeds|Gross proceeds|\(Less\))", label, re.I):
                    rows.append({"label": label, "amount": _crore(_amount(re.sub(r"(?i)up to\s+", "", m2.group(1))), unit)})
                buf = ""
            else:
                buf = _flat(f"{buf} {ln}")
        if len(rows) >= 2:
            return {"page": i + 1, "unit": "₹ crore", "rows": rows[:12]}
    return None


RISK_HEAD = re.compile(r"(?ms)^[ \t]*(\d{1,3})\.\s+([A-Z][^\n]*(?:\n(?![ \t]*\n)[^\n]+){0,6}?\.)[ \t]*\n[ \t]*\n")


def risk_headings(pages: list[str], limit: int = 12) -> list[dict]:
    """The risk factors the document lists first, as it words them: [{"n", "page", "text"}]. The section's risks are numbered, each a
    heading sentence then its text, and a prospectus orders them from the most material down, so the first are the ones it
    puts first. Numbers that don't follow on (a numbered list inside a risk's text) are left out."""
    start = next((i for i, pg in enumerate(pages) if re.search(r"^\s*(?:SECTION [IVX]+\s*[–:-]\s*)?RISK FACTORS\s*$", pg, re.M)
                  and not re.search(r"\.{4,}", pg[:400]) and not HEAD_SKIP.search(pg[:200])), None)
    if start is None:
        return []
    out, want = [], 1
    for i in range(start, min(len(pages), start + 70)):
        for m in RISK_HEAD.finditer(pages[i]):
            n = int(m.group(1))
            text = _flat(m.group(2))
            if n < want or n > want + 3 or not 30 <= len(text) <= 460:
                continue
            want = n + 1
            out.append({"n": n, "page": i + 1, "text": text})
            if len(out) >= limit:
                return out
    return out


KPI_ROWS = (("revenue", re.compile(r"^Revenue from Operations", re.I), "crore"), ("ebitda", re.compile(r"^Operating EBITDA(?!\s*Margin)|^EBITDA(?!\s*Margin)", re.I), "crore"),
            ("ebitda_margin", re.compile(r"^(?:Operating )?EBITDA\s*Margin", re.I), "pct"), ("pat", re.compile(r"^PAT(?!\s*Margin)", re.I), "crore"),
            ("pat_margin", re.compile(r"^PAT\s*Margin", re.I), "pct"), ("roe", re.compile(r"^ROE", re.I), "pct"), ("roce", re.compile(r"^ROCE", re.I), "pct"),
            ("net_debt", re.compile(r"^Net Debt(?!\s*/)", re.I), "crore"), ("net_worth", re.compile(r"^Net worth", re.I), "crore"),
            ("debt_equity", re.compile(r"^Net Debt\s*/\s*Equity", re.I), "x"), ("order_book", re.compile(r"^Total Order Book", re.I), "crore"))
KPI_HEAD = re.compile(r"Key Performance Indicators\s+As at and for\s+(?P<period>.+?)\s+Our Company\s+(?P<peers>.+?)\s*$", re.I)


def kpis(pages: list[str]) -> dict | None:
    """The key performance indicators the document sets beside its listed peers' (the "Comparison of KPIs with our listed industry peers"
    tables, one block for each period): {"page", "unit", "peers": [names], "periods": [{"label", "values": {key: v}, "peers":
    {key: [v, ...]}}]}, money in ₹ crore, the document's ratios and percents as they are. Needs the table's own header lines; None when
    the document has none."""
    for i, pg in enumerate(pages):
        if not KPI_HEAD.search(_flat(pg).replace("\n", " ")) and not re.search(r"Key Performance Indicators\s+As at and for", pg):
            continue
        if re.search(r"\.{4,}", pg[:300]):
            continue
        blocks, start = [], i
        for j in range(i, min(len(pages), i + 4)):
            blocks.append(pages[j])
        text = "\n".join(blocks)
        um = re.search(r"(?:in|In)\s*(?:₹|Rs\.?)\s*(million|mn|crore|lakh)", "\n".join(pages[max(0, i - 3):i + 1]) + text[:600])
        unit = {"mn": "million"}.get(um.group(1).lower(), um.group(1).lower()) if um else "million"
        periods = []
        cur = None
        for ln in text.split("\n"):
            ln = ln.strip()
            h = KPI_HEAD.search(ln)
            if h:
                cur = {"label": re.sub(r"\s+", " ", h.group("period")).strip(), "values": {}, "peers": {}}
                peers = h.group("peers").split()
                cur["_peers"] = peers
                periods.append(cur)
                continue
            if cur is None or not ln:
                continue
            for key, pat, kind in KPI_ROWS:
                if pat.search(ln) and key not in cur["values"]:
                    toks = re.findall(r"(?<![\w.])\(?-?[\d,]+(?:\.\d+)?\)?%?[*#^]*|\bNA\b|(?<=\s)-(?=\s|$)", re.sub(r"^[A-Za-z /&()\-]+?\d{0,2}\s(?=[\d(-])", "", ln, count=1))
                    vals = [_amount(t) for t in toks]
                    if not vals:
                        break
                    conv = (lambda v: _crore(v, unit)) if kind == "crore" else (lambda v: v)
                    cur["values"][key] = conv(vals[0])
                    cur["peers"][key] = [conv(v) for v in vals[1:]]
                    break
        periods = [p for p in periods if p["values"]]
        if len(periods) >= 2:
            names = periods[0].get("_peers") or []
            for p in periods:
                p.pop("_peers", None)
            return {"page": i + 1, "unit": "₹ crore", "peers": names, "periods": periods[:8]}
    return None


def shareholding(pages: list[str]) -> dict | None:
    """The pre-offer shareholding of the promoters, the rest of the promoter group and the largest other holders, from the table the
    document gives before the offer's capital structure: {"page", "rows": [{"group", "name", "shares", "pct"}], "post": bool} with
    the post-offer shares when the price band is fixed; a "[●]" (to be filled in after allotment) leaves `post_pct` None. Names that
    wrap over lines are joined; a sub-total line is kept as its own row."""
    for i, pg in enumerate(pages):
        if not re.search(r"Pre-Offer shareholding as\s*(?:\n\s*)?on the date", pg, re.I) or re.search(r"\.{4,}", pg[:300]):
            continue
        text = pg + "\n" + (pages[i + 1] if i + 1 < len(pages) else "")
        start = re.search(r"Promoters\s*\n", text)
        if not start:
            continue
        rows, group, buf, skipping = [], "Promoters", "", False
        for ln in text[start.start():].split("\n"):
            ln = ln.strip()
            if not ln:
                continue
            if re.match(r"^\d{3}$", ln):                      # a page break: the table's header lines repeat, then its rows go on
                skipping, buf = True, ""
                continue
            if skipping:
                if re.match(r"^\d+\.\s+\S|^(Promoters?|Promoter Group|Additional top|Other public|Public)\b", ln):
                    skipping = False
                else:
                    continue
            if re.match(r"(Promoters?|Promoter Group.*|Additional top.*|Other public.*|Public)\s*$", ln, re.I) and not buf:
                group = ln.strip()
                continue
            if re.match(r"(Total|Notes?:|\*|#|\^)", ln):
                if re.match(r"Total", ln):
                    break
                continue
            m = re.search(r"([\d,]{5,})\s+([\d.]+)%\s+(.*)$", ln)
            if not m:
                buf = _flat(f"{buf} {ln}") if not re.match(r"^\d+\.\s*$", ln) else buf
                continue
            head = ln[: m.start()].strip()
            name = _flat(f"{buf} {head}")
            buf = ""
            name = re.sub(r"^\d+\.\s+", "", name).strip()
            if re.fullmatch(r"[-*#^ ]*", name):
                name = "Public shareholders"
            if not name:
                continue
            tail = re.findall(r"\[●\]|[\d,]{5,}|[\d.]+%", m.group(3))
            post_pct = next((float(t.rstrip("%")) for t in tail if t.endswith("%")), None)
            rows.append({"group": group, "name": name, "shares": int(m.group(1).replace(",", "")), "pct": float(m.group(2)), "post_pct": post_pct,
                         "total": bool(re.match(r"Sub-total", name, re.I))})
        if len(rows) >= 2:
            return {"page": i + 1, "rows": rows[:40]}
    return None


def peer_table(pages: list[str]) -> dict | None:
    """The comparison of accounting ratios with listed industry peers: {"page", "company": {...}, "peers": [{"name", "price", "revenue",
    "eps", "nav", "pe", "ronw"}]} with the document's own figures (revenue in ₹ crore, a peer's P/E as the document computed it at the
    closing price of the date it names, "price_on"). The company's own row has no P/E before the price is set."""
    for i, pg in enumerate(pages):
        if not re.search(r"Comparison of accounting ratios with listed industry peers", pg, re.I) or re.search(r"\.{4,}", pg[:300]):
            continue
        m = re.search(r"Closing\s*price on\s*([A-Za-z]+\s+\d{1,2},?\s*\d{4})", pg, re.I)
        on = _flat(m.group(1)) if m else None
        um = re.search(r"in\s*₹\s*(million|crore|lakh)", pg, re.I)
        unit = um.group(1).lower() if um else "million"
        body = pg[pg.index("Listed Peers") if "Listed Peers" in pg else 0:]
        head = pg[:pg.index("Listed Peers")] if "Listed Peers" in pg else ""
        company_line = None
        hm = re.search(r"((?:[A-Z][A-Za-z.&,’' ()-]+\n){1,4})\s*[\d.]+\s+(?:N\.?A\.?)\s+([\d,]+\.\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+([\d.]+)\s+(?:N\.?A\.?|[\d.]+x?)\s+([\d.]+)", head)
        peers, buf = [], ""
        lines = [ln.strip() for ln in re.split(r"\n", body) if ln.strip()]
        for ln in lines:
            if re.match(r"(Listed Peers|Notes?:|\(i\))", ln):
                if ln.startswith(("Notes", "(i)")):
                    break
                continue
            nm = re.search(r"([\d.]+)\s+([\d,]+\.\d+|N\.?A\.?)\s+([\d,]+(?:\.\d+)?)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+([\d,.]+)\s+([\d,.]+x|N\.?A\.?)\s+(-?[\d.]+)\s*$", ln)
            if nm:
                name = _flat(f"{buf} {ln[: nm.start()]}").strip()
                name = re.sub(r"\s*\([“\"'‘].*?[”\"'’]\)\s*", " ", name).strip()
                buf = ""
                if name:
                    f = lambda t: _amount(t.replace(",", "").rstrip("x"))      # noqa: E731
                    peers.append({"name": name, "price": f(nm.group(2)), "revenue": _crore(f(nm.group(3)), unit), "eps": f(nm.group(5)),
                                  "nav": f(nm.group(6)), "pe": f(nm.group(7)), "ronw": f(nm.group(8))})
            else:
                buf = _flat(f"{buf} {ln}")[-160:] if not re.match(r"^\(.*\)$", ln) else buf
        co = None
        if hm:
            co = {"revenue": _crore(_amount(hm.group(2).replace(",", "")), unit), "eps": _amount(hm.group(4)), "nav": _amount(hm.group(5)), "ronw": _amount(hm.group(6))}
        if peers:
            return {"page": i + 1, "price_on": on, "company": co, "peers": peers[:8]}
    return None


def eps_rows(pages: list[str]) -> dict | None:
    """The document's earnings per share by year (basic and diluted, as adjusted for changes in capital, its consolidated basis):
    {"page", "rows": [{"period", "basic", "diluted"}]}."""
    for i, pg in enumerate(pages):
        m = re.search(r"Basic EPS \(in ₹\)\s+Diluted EPS \(in ₹\)", pg)
        if not m or re.search(r"\.{4,}", pg[:300]):
            continue
        rows = []
        for ln in pg[m.end():].split("\n"):
            ln = ln.strip()
            mm = re.match(r"(March\s+\d{1,2},\s*\d{4}|Three months ended [A-Za-z]+\s+\d{1,2},\s*\d{4}\*?)\s+(\(?-?[\d.]+\)?)\s+(\(?-?[\d.]+\)?)", ln)
            if mm:
                rows.append({"period": mm.group(1).rstrip("*"), "basic": _amount(mm.group(2)), "diluted": _amount(mm.group(3))})
            elif rows and re.match(r"(Weighted Average|\*|Notes?)", ln):
                continue
            elif rows and not ln:
                break
        if rows:
            return {"page": i + 1, "rows": rows}
    return None


# ---------- the passages the AI is given ----------
def india_excerpt(pages: list[str]) -> str:
    """The passages of an Indian offer document the summary is written from: the cover (promoters, selling shareholders), the
    business, the first risk factors, the summary financial tables and the objects. Each is marked with its PDF page."""
    parts = []

    def add(title: str, got: tuple[int, str] | None, limit: int):
        if got:
            parts.append(f"[{title}, PDF page {got[0]}]\n{_flat(re.sub(r'<<[0-9]+>>', ' ', got[1]))[:limit]}")

    parts.append("[Cover, PDF pages 1-2]\n" + _flat("\n".join(pages[:2]))[:4500])
    add("Business", section(pages, r"OUR BUSINESS", span=3), 6500)
    add("Overview of the business", section(pages, r"(?:OVERVIEW|BUSINESS OVERVIEW|SUMMARY OF (?:THE )?BUSINESS)", span=2), 3500)
    add("Risk factors", section(pages, r"RISK FACTORS", span=4), 7000)
    fin = section(pages, r"SUMMARY (?:OF )?(?:THE )?FINANCIAL INFORMATION", span=7)
    if fin:
        pl = re.search(r"(?i)summary (?:restated )?(?:consolidated )?profit and loss|restated statement of profit", fin[1])
        add("Summary financial information", (fin[0], fin[1][pl.start():] if pl else fin[1]), 5000)
    add("Objects of the offer", section(pages, r"OBJECTS OF THE (?:OFFER|ISSUE)", span=3), 4500)
    add("Promoters", section(pages, r"OUR PROMOTERS AND PROMOTER GROUP", span=2), 3500)
    return "\n\n".join(parts)


def us_cut(text: str, start: str, length: int, after: int = 0) -> str:
    """`length` characters from the first line (not in the contents) that begins `start`, from the `after`th character."""
    for m in re.finditer(rf"(?im)^\s*{start}\s*$", text):
        if m.start() > after:
            return _flat(text[m.end(): m.end() + length])
    return ""


def us_excerpt(text: str) -> str:
    """The passages of a US prospectus the summary is written from: the cover, the summary (business and strengths), the risks the
    summary lists, the offering terms with the use of proceeds and the summary financial data."""
    body_at = text.find("Prospectus summary", 4000)
    parts = [f"[Cover]\n{_flat(text[:3800])}"]
    for title, start, n in (("Summary of the business", r"(?:Overview|Our company|Company overview|Our business|Business overview)", 4800),
                            ("Risks the summary lists", r"Summary of (?:the )?(?:principal |material |key )?risks?(?: related to our business| factors)?|Risk factors summary|Summary risk factors", 5200),
                            ("The offering", r"The offering", 4200),
                            ("Summary financial data", r"Summary (?:consolidated )?(?:historical )?(?:financial|operating) (?:and other )?data|Summary consolidated financial (?:and operating )?data", 6500)):
        got = us_cut(text, start, n, max(body_at - 200, 0))
        if got:
            parts.append(f"[{title}]\n{got}")
    return "\n\n".join(parts)


# ---------- US: the facts ----------
def us_facts(text: str) -> dict:
    """The offering's terms from a US prospectus's cover and "The offering": shares offered by the company and by selling
    stockholders, the price (or range), the listing and the use of proceeds in the document's own words."""
    cover = _flat(text[:6000])
    out: dict = {}
    m = re.search(r"We are offering ([\d,]+) (?:shares|American depositary shares|ADSs|units)", cover)
    out["company_shares"] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r"[Tt]he selling (?:stock|share)holders? (?:named in this prospectus )?(?:are|is) offering ([\d,]+)", cover)
    out["selling_shares"] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r"initial public offering price (?:is|will be|of)\s+\$([\d.,]+) per", cover)
    out["price"] = float(m.group(1).replace(",", "")) if m else None
    m = re.search(r"between \$([\d.,]+) and \$([\d.,]+) per", cover)
    out["range"] = [float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))] if m else None
    m = re.search(r"(?:listing|list|quotation) (?:of (?:our|the) [a-z ]+ )?on (?:the )?((?:The )?Nasdaq (?:Global Select|Global|Capital) Market|New York Stock Exchange|NYSE American|NYSE)"
                  r"(?:[^.“\"]{0,40}symbol (?:“|\")?([A-Z][A-Z.]{0,5}))?", cover)
    out["listing"] = _flat(m.group(1)) if m else None
    out["symbol"] = m.group(2).rstrip(".") if m and m.group(2) else None
    block = us_cut(text, r"Use of proceeds", 1300, 6000)
    if block:
        out["proceeds"] = re.split(r"\s+(?:Directed share program|Risk factors|Dividend policy|Lock-up|Conflicts of interest|Material U\.S\.)", block, maxsplit=1)[0][:900].rstrip(" ,;")
    return {k: v for k, v in out.items() if v not in (None, "")}


# ---------- the AI summary ----------
SUMMARY_SYSTEM = """You summarise an IPO offer document for an investor using ONLY the passages given. Reply with one JSON object:
{"business": {"text": "...", "quote": "..."},
 "segments": [{"text": "...", "quote": "..."}]}
Rules:
- business: one or two plain sentences on what the company does and where it earns its money.
- segments: up to 4 statements of how the company's revenue splits by business segment, product or geography, with the amounts or shares as the passages give them (one statement per segment or per period).
- Every "quote" is 8 to 30 consecutive words copied EXACTLY from the passages that support the text. Never invent a figure.
- Facts only, in plain English: no opinion, no view on whether to apply or invest, no words like attractive, strong, cheap, expensive, undervalued, buy or avoid.
- Leave segments empty (or business empty) when the passages don't say."""
ADVICE = re.compile(r"\b(buy|sell|hold|avoid|apply|subscribe|accumulate|attractive|undervalued|overvalued|bargain|cheap|expensive|"
                    r"recommend\w*|should|must|worth|opportunity|upside|downside|target|safe bet|multibagger|grey market|gmp)\b", re.I)
MAX_ITEMS = {"segments": 4}


def _numbers(s: str) -> set[str]:
    return {re.sub(r"[,\s]", "", n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s) if len(re.sub(r"\D", "", n)) >= 2}


def clean_summary(parsed: dict, excerpt: str) -> dict:
    """The AI's summary, kept only where it can be checked: a statement stays when its quote is really in the passages, the
    statement's own figures are in that quote, and it reads as a fact (no advice words)."""
    def keep(item) -> dict | None:
        if not isinstance(item, dict):
            return None
        text, quote = _flat(str(item.get("text") or "")), _flat(str(item.get("quote") or ""))
        if not (12 <= len(text) <= 420) or len(quote.split()) < 5 or ADVICE.search(text):
            return None
        if not docs.quote_found(quote, excerpt):
            return None
        if not _numbers(text) <= _numbers(quote):         # every figure the statement gives is in the words it quotes
            return None
        return {"text": text, "quote": clip_words(quote, 300)}      # (cut at a word, RC2A-007: "...shall not e")

    out: dict = {}
    b = keep(parsed.get("business"))
    out["business"] = b
    for k, n in MAX_ITEMS.items():
        got = [x for x in (keep(i) for i in (parsed.get(k) if isinstance(parsed.get(k), list) else [])) if x]
        out[k] = got[:n]
    return out


def summarise(excerpt: str, ai) -> dict:
    """The summary of an offer document from its excerpt: {"business", "financials", "objects", "risks", "promoters"} or raises."""
    raw = complete(SUMMARY_SYSTEM, "PASSAGES:\n" + excerpt, gemini=ai[0] if ai else None, anthropic=ai[1] if ai else None, max_tokens=2600, kind="long")
    parsed = extract_json(raw)
    return clean_summary(parsed if isinstance(parsed, dict) else {}, excerpt)
