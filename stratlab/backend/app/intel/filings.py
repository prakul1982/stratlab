"""Company filings from the exchange (NSE corporate announcements), sorted into a timeline and checked against
fixed red-flag rules: fund raises (QIP, preferential, rights, warrants), promoter pledges, key resignations,
defaults, regulator action and rating downgrades.

Everything here is a fact from a public filing and a fixed keyword rule the user can read, never a judgement or
advice. The exchange's own wording and document link are always shown next to our label."""
import json
import re
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .. import db
from .net import BROWSER_UA, SourceError, TTLCache, RateLimit

IST = ZoneInfo("Asia/Kolkata")
WINDOW_DAYS = 90             # the "last 3 months" summary
LOOKBACK_DAYS = 365          # how far back the timeline goes

# (id, label, severity, patterns). First match wins, so the specific rules come before the broad ones.
# severity: "red" = a red flag the investor asked to see, "amber" = worth a look, "info" = routine.
RULES: list[tuple[str, str, str, list[str]]] = [
    ("auditor_resign", "Auditor resigned", "red", [r"resignation of (the )?(statutory |secretarial |internal )?auditor", r"auditors? .{0,40}resign"]),
    ("default", "Default or delayed payment", "red", [r"\bdefault\b", r"delay in (payment|servicing)", r"non[- ]payment of (interest|principal)"]),
    # a subsidiary wound up, struck off or dissolved is routine housekeeping, whoever certifies it (RELIANCE, Sep 2026:
    # "Roptonal Limited, a step-down subsidiary, stands dissolved ... certificate from Department of Insolvency, Cyprus")
    ("subsidiary_closed", "Subsidiary dissolved or struck off", "info", [
        r"subsidiar(y|ies)\b.{0,160}\b(dissolv|struck off|strike[- ]off|striking off|wound up|winding[- ]up|liquidat|deregist|ceased to exist)",
        r"\b(dissolution|striking off|strike[- ]off|winding[- ]up|liquidation)\b.{0,80}\bsubsidiar(y|ies)"]),
    # routine servicing of debt already raised: record dates, interest and redemption, allotments of NCDs and paper, and
    # the debt's own trading suspended for its record date (UGROCAP's "Suspension of Trading" read as a debt raise)
    ("debt_routine", "Debt servicing or allotment", "info", [
        r"(record date|redemption|interest payment|payment of interest|suspension of trading|allotment|allot(ted)?)\b.{0,120}"
        r"\b(ncds?|non[- ]convertible debentures?|debentures?|bonds?|commercial papers?)\b",
        r"\b(ncds?|non[- ]convertible debentures?|debentures?|bonds?|commercial papers?)\b.{0,120}"
        r"\b(record date|redemption|interest payment|payment of interest|suspension of trading|allotment|allotted)"]),
    ("suspension", "Trading suspended", "red", [r"suspension of trading", r"trading .{0,20}suspended"]),
    # a meeting the tribunal convened (of shareholders or creditors, on a merger or arrangement) and its voting results
    # are routine, and so is the company's clarification of a news report (R8O-003: AMBUJACEM's "Outcome of
    # NCLT-convened meeting", JUBLCPL's voting results and LICHSGFIN's "Clarification on media news" read as insolvency)
    ("court_meeting", "Tribunal-convened meeting", "info", [
        r"\bnclt[- ]convened\b", r"convened .{0,80}\b(nclt|national company law tribunal|tribunal)\b",
        r"\b(nclt|national company law tribunal|tribunal)\b.{0,60}\bconvened\b",
        r"meeting of (the )?(equity shareholders|shareholders|members|(secured |unsecured )?creditors)\b.{0,120}\b(nclt|tribunal)\b",
        r"\bvoting results?\b.{0,160}\b(nclt|tribunal|convened)\b", r"\b(nclt|tribunal|convened)\b.{0,160}\bvoting results?\b"]),
    ("news_clarification", "Clarification of a news report", "info", [
        r"clarification .{0,40}\b(media|news|article|rumou?rs?|report(ed|s)?)\b", r"\b(media|news) (report|item|article)s?\b.{0,80}\bclarif"]),
    # explicit insolvency or CIRP wording only: "NCLT" alone names the tribunal, which sanctions mergers too (R8O-003);
    # the company must be the debtor as well (DEBTOR, classify)
    ("insolvency", "Insolvency proceedings", "red", [r"corporate insolvency resolution", r"insolvency (and bankruptcy|resolution|proceedings?|petition|application)",
                                                     r"\bibc\b", r"\bcirp\b", r"initiation of .{0,30}insolvency"]),
    ("qip", "QIP (fund raise)", "red", [r"qualified institutions? placement", r"\bqip\b"]),
    ("preferential", "Preferential issue (fund raise)", "red", [r"preferential (issue|allotment|basis)"]),
    ("rights", "Rights issue (fund raise)", "red", [r"rights issue", r"issue .{0,20}on rights basis"]),
    ("warrants", "Warrants issued (fund raise)", "red", [r"convertible warrants", r"issue of warrants", r"allotment of warrants"]),
    ("fund_raise", "Fund raise approved or planned", "red", [r"fund[- ]?rais", r"raising of funds", r"raise funds"]),
    ("pledge", "Promoter pledge or encumbrance", "red", [r"\bpledge", r"encumbrance", r"regulation 31\b(?!\s*\(4\))"]),
    ("regulator", "Regulator or tax action", "red", [r"\bsebi\b.{0,40}(order|penalt|show cause|adjudicat)", r"show[- ]cause", r"search (and|&) seizure",
                                                   r"income tax (search|survey)", r"enforcement directorate", r"\bpenalty\b"]),
    ("rating_down", "Credit rating downgraded", "red", [r"downgrad", r"rating .{0,30}(revised|placed) .{0,30}(negative|watch)"]),
    ("kmp_resign", "Director or key officer resigned", "amber", [r"resignation", r"resigned", r"cessation"]),
    # a new borrowing: the filing raises or approves debt, not one that only names bonds (R6O-002)
    ("ncd", "Debt raise (NCDs or bonds)", "amber", [
        r"\b(issu\w*|rais\w*|approv\w*|offer\w*|placement|borrow\w*)\b.{0,80}\b(ncds?|non[- ]convertible debentures?|debentures?|bonds?|commercial papers?)\b",
        r"\b(ncds?|non[- ]convertible debentures?|debentures?|bonds?|commercial papers?)\b.{0,60}\b(issu(e|ed|ance)|rais(e|ed|ing)|approved|offer(ed)?|placement)\b"]),
    ("results", "Financial results", "info", [r"financial results", r"outcome of board meeting.{0,60}results", r"\bresults\b"]),
    # a shareholders' meeting's own transcript, recording or deck is neither an earnings call nor an analyst meeting
    ("agm", "Shareholder meeting", "info", [r"(?:transcript|recording|audio|proceedings|presentation|minutes)\b.{0,100}\b(?:annual|extra[- ]?ordinary|general) (?:general )?meeting",
                                             r"\b(?:annual|extra[- ]?ordinary) general meeting\b.{0,100}\b(?:transcript|recording|audio)",
                                             r"\b[ae]gm\b.{0,60}\b(?:transcript|recording|audio)", r"\b(?:transcript|recording|audio)\b.{0,60}\b[ae]gm\b",
                                             r"presentation .{0,60}(?:shareholders|postal ballot)"]),
    ("concall", "Earnings call", "info", [r"transcript", r"earnings call", r"conference call"]),
    ("investor_meet", "Analyst or investor meeting", "info", [r"analysts?/institutional investor meet", r"investor meet", r"analysts? meet"]),
    ("presentation", "Investor presentation", "info", [r"investor presentation", r"presentation"]),
    ("dividend", "Dividend", "info", [r"dividend"]),
    ("buyback", "Buyback", "info", [r"buy[- ]?back"]),
    ("order", "Order or contract", "info", [r"order (win|received|bagged)", r"bagging", r"receipt of (an )?order", r"award of contract", r"letter of award"]),
    ("deal", "Acquisition, merger or stake", "info", [r"acquisition", r"amalgamation", r"merger", r"scheme of arrangement", r"stake"]),
    ("rating", "Credit rating", "info", [r"credit rating", r"\brating\b"]),
    ("board", "Board meeting", "info", [r"board meeting"]),
    ("agm", "Shareholder meeting", "info", [r"\bagm\b", r"\begm\b", r"annual general meeting", r"postal ballot"]),
]
_COMPILED = [(i, label, sev, [re.compile(p, re.I) for p in pats]) for i, label, sev, pats in RULES]
FUND_RAISE = {"qip", "preferential", "rights", "warrants", "fund_raise"}
LABEL = {i: label for i, label, _, _ in RULES} | {"other": "Other update", "officer_change": "Director or officer change",
                                                  "insolvency_other": "Insolvency filing, the company not shown as the debtor"}
# raised when the rules change, so the stored whole-market list is read again (5: "NCLT" alone is no longer insolvency,
# tribunal-convened meetings and news clarifications are routine, R8O-003)
RULES_VERSION = 5

# R6O-002: the filing's subject says what it is about. A routine certificate is routine whatever its body names
# (ICICIBANK's "Certificate under SEBI (Depositories and Participants) Regulations, 2018" read as a debt raise).
ROUTINE_SUBJECT = re.compile(r"depositories and participants|regulation 74\s*\(5\)|trading window|loss of share certificate|"
                             r"duplicate share certificate|statement of investor complaints|newspaper|compliance certificate|"
                             r"transfer of (physical )?shares|dematerial", re.I)
# a generic subject ("Updates", "General Updates") names nothing: a flag needs the body to report a decision or an
# event, not a passing mention (TITAN's "Updates" read as a debt raise, RAYMONDREL's "General Updates" as a
# preferential issue), and a report on money already raised is routine
GENERIC_SUBJECT = re.compile(r"^\s*((general|other|others|miscellaneous)\s*)?(updates?|general|others?|miscellaneous|press release|disclosure|intimation)\s*$", re.I)
DECISION = re.compile(r"\b(approv\w*|allot\w*|resolved|decided|opened|launch\w*|initiat\w*|admitted|downgrad\w*|resign\w*|"
                      r"default\w*|delay\w*|creation of pledge|invoked|imposed|levied|search|seizure|show[- ]cause|penalt\w*|"
                      r"suspend\w*|revised|raising|raise)\b", re.I)
ROUTINE_TEXT = re.compile(r"monitoring agency|utili[sz]ation of (the )?(issue )?proceeds|statement of deviation|deviation or variation|"
                          r"depositories and participants|regulation 74|in[- ]principle approval|listing approval|trading approval|"
                          r"record date|payment of interest|interest payment|redemption", re.I)
# insolvency: only the listed company as the debtor in a case against it (R6O-002: MOL Meghmani's amalgamation,
# which the NCLT sanctions, and POLYCAB's filing on another company's insolvency, both read as its own)
DEBTOR = re.compile(r"against the company|(the|our) company (has been|was|is|stands) admitted|admitted .{0,80}(against|in respect of) the company|"
                    r"initiat\w* .{0,80}(of|against|in respect of) the company|moratorium|interim resolution professional|"
                    r"\birp\b|committee of creditors|\bcoc\b|(the )?company is under (cirp|corporate insolvency)|"
                    r"powers of the board .{0,40}suspended|nclt has admitted|admitted the (application|petition)", re.I)
OTHER_PARTY = re.compile(r"(the|our) company,? (as|being) an? (operational |financial )?creditor|filed by the company|"
                         r"(company|we) (has |have )?filed an? (application|petition)|"
                         r"claim (has been )?(filed|submitted|admitted)|subsidiar|step[- ]down|associate company|joint venture|customer|"
                         r"amalgamation|merger|scheme of arrangement|demerger", re.I)


def ist_now() -> datetime:
    """Now in India, without a zone, to compare with the exchange's (IST, zoneless) filing times."""
    return datetime.now(IST).replace(tzinfo=None)


# NSE files every meeting with analysts or investors under one subject that names calls too, so a call is told apart
# by the rest of the filing: an earnings or conference call, its audio recording or its transcript. A one-on-one
# meeting with an investor has no transcript to file; an earnings call has to have one.
MEET_SUBJECT = re.compile(r"analysts?\s*/\s*institutional investors? meet\s*/\s*con\.? ?call updates?", re.I)
CALL = re.compile(r"earnings? (?:conference )?call|conference call|con\.? ?call|concall|results? call|post[- ]results?|"
                  r"investors?(?: and analysts?)? call|analysts?(?: and investors?)? call|audio|recording|\btran?scr?i?pts?\b", re.I)


def file_words(url: str | None) -> str:
    """The words in a filing's PDF name: NSE keeps the name the company uploaded ("ACME_01082026190000_Q1FY27
    ConcallTranscript.pdf"), which often says what the filing is when its subject doesn't."""
    from urllib.parse import unquote, urlsplit
    url = (url or "")[:500]                   # from the exchange's feed: untrusted, and only the name is wanted
    try:
        path = urlsplit(url).path
    except ValueError:                        # a malformed link ("https://[..."): its words still count
        path = url.split("?", 1)[0].split("#", 1)[0]
    name = unquote(path.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", re.sub(r"[_\-.+]+", " ", name))


def is_call(subject: str | None, text: str | None, url: str | None = None) -> bool:
    """Whether a filing about a meeting with analysts or investors is about an earnings or conference call."""
    return bool(CALL.search(f"{MEET_SUBJECT.sub(' ', subject or '')} {text or ''} {file_words(url)}"))


# who left, for a resignation or cessation: a director or a key managerial person (managing director, CEO, CFO,
# company secretary, compliance officer) is worth a look; senior management below them, and a term that simply ended
# (completion of tenure, retirement, death) are routine changes. The exchange's generic subject ("Resignation of
# Director/KMP/SMP") names every kind, so it is read without that phrase.
_GENERIC_ROLES = re.compile(r"directors?\s*/\s*kmps?(\s*/\s*smps?)?|kmps?\s*/\s*smps?|\(?\s*smps?\s*\)?", re.I)
_KEY_ROLE = re.compile(r"\bdirector\b|managing director|\bmd\b|\bceo\b|chief executive|\bcfo\b|chief financial|company secretary|"
                       r"compliance officer|whole[- ]time director|independent director|\bchairman\b|\bchairperson\b|"
                       r"key managerial|\bkmp\b", re.I)
_SENIOR_ONLY = re.compile(r"senior management|\bsmp\b|\bhead\b|\bmanager\b|vice[- ]president|\bvp\b|\bpresident\b|"
                          r"general manager|\bofficer\b|\bchief\b", re.I)
_TERM_ENDED = re.compile(r"(completion|expiry|expiration|end) of (his |her |their )?(second |first )?(tenure|term)|"
                         r"\bretire(d|ment|s)?\b|superannuat|\bdemise\b|\bdeath\b|passed away|\bdeceased\b", re.I)


def _officer_change(desc: str, text: str) -> tuple[str, str]:
    """A resignation or cessation filing: a director or key officer who resigned is amber; a term that ended, or
    someone below the key officers, is a routine change."""
    hay = _GENERIC_ROLES.sub(" ", f"{desc or ''} || {text or ''}")
    if _TERM_ENDED.search(hay):
        return "officer_change", "info"
    if _KEY_ROLE.search(hay):
        return "kmp_resign", "amber"
    if text and _SENIOR_ONLY.search(hay):
        return "officer_change", "info"
    return "kmp_resign", "amber"              # nothing says who: kept, to be read


def classify(desc: str, text: str, url: str | None = None) -> tuple[str, str]:
    """(category id, severity) for one announcement, from the exchange's subject and summary (and its file's name).
    Earnings calls, meetings with analysts or investors, and shareholders' meetings are three different kinds."""
    hay = f"{desc or ''} || {text or ''}"
    if ROUTINE_SUBJECT.search(desc or ""):
        return "other", "info"
    generic = bool(GENERIC_SUBJECT.match(desc or ""))
    insolvency_named = False
    for cid, _, sev, rx in _COMPILED:
        if any(r.search(hay) for r in rx):
            if cid == "insolvency" and not (DEBTOR.search(hay) and not OTHER_PARTY.search(hay)):
                insolvency_named = True
                continue                      # not the company's own case: what the filing is otherwise about
            if generic and sev != "info" and (not DECISION.search(text or "") or ROUTINE_TEXT.search(text or "")):
                continue
            if cid == "investor_meet" and is_call(desc, text, url):
                return "concall", sev
            if cid == "kmp_resign":
                return _officer_change(desc, text)
            return cid, sev
    return ("insolvency_other", "info") if insolvency_named else ("other", "info")


def _date(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime((s or "").strip(), fmt)
        except ValueError:
            continue
    return None


def normalise(raw: list[dict]) -> list[dict]:
    """The exchange's rows as timeline items, newest first; rows without a date are dropped."""
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        when = _date(r.get("sort_date") or r.get("an_dt") or r.get("exchdisstime") or "")
        if not when:
            continue
        subject = str(r.get("desc") or "").strip()[:200]
        text = re.sub(r"\s+", " ", str(r.get("attchmntText") or "")).strip()[:600]
        key = r.get("seq_id") or (when.isoformat(), subject, text[:80])
        if key in seen:
            continue
        seen.add(key)
        link = str(r.get("attchmntFile") or "")
        cid, sev = classify(subject, text, link)
        out.append({"id": str(r.get("seq_id") or abs(hash(key)))[:40], "at": when.isoformat(timespec="minutes"),
                    "category": cid, "label": LABEL[cid], "severity": sev, "subject": subject, "text": text,
                    "url": link if link.startswith("https://") else None})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out


def flagged_rows(raw: list[dict]) -> list[dict]:
    """The red and amber announcements in the exchange's list for the whole market (rows of every company), each with
    its company's symbol and name: {id, symbol, company, at, category, label, severity, subject, url}. Routine
    filings are left out; the id is the same each time the same filing is read."""
    import zlib
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9&\-._]{1,20}", sym):
            continue
        for it in normalise([r]):
            if it["severity"] == "info":
                continue
            fid = f"{sym}|{it['at']}|{zlib.crc32(it['subject'].encode()):08x}"
            if fid in seen:
                continue
            seen.add(fid)
            out.append({"id": fid, "symbol": sym, "company": str(r.get("sm_name") or r.get("comp") or "").strip()[:80] or None,
                        "at": it["at"], "category": it["category"], "label": it["label"], "severity": it["severity"],
                        "subject": it["subject"][:160], "text": it["text"][:240], "url": it["url"]})
    return one_per_filing(out)


def _same_filing_key(i: dict) -> tuple:
    """What makes two rows one filing: the company, the day, the rule and the words (the subject, and the summary
    when it was kept). The exchange lists a filing again when it is revised or re-sent, with a new time and number."""
    norm = (lambda s: re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip())
    return (i.get("symbol"), str(i.get("at"))[:10], i.get("category"), norm(i.get("subject")), norm(i.get("text"))[:160])


def one_per_filing(items: list[dict]) -> list[dict]:
    """The rows with each filing once (the latest copy, which keeps its id), and `copies` when it was listed more
    than once (KSHITIJPOL's one resignation, 7 Oct 2026, three times)."""
    best: dict[tuple, dict] = {}
    for i in items:
        k = _same_filing_key(i)
        have = best.get(k)
        if have is None:
            best[k] = {**i}
            continue
        keep = i if (i["at"], i["id"]) > (have["at"], have["id"]) else have
        best[k] = {**keep, "copies": have.get("copies", 1) + 1}
    return list(best.values())


def summarise(items: list[dict], now: datetime | None = None) -> dict:
    """The last-3-months view: red flags, whether a fund raise happened, and counts by category."""
    now = now or ist_now()
    cutoff = (now - timedelta(days=WINDOW_DAYS)).isoformat()
    recent = [i for i in items if i["at"] >= cutoff]
    red = [i for i in recent if i["severity"] == "red"]
    counts: dict[str, int] = {}
    for i in recent:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    raise_ = [i for i in recent if i["category"] in FUND_RAISE]
    return {"days": WINDOW_DAYS, "total": len(recent), "red": len(red), "amber": sum(1 for i in recent if i["severity"] == "amber"),
            "fund_raise": bool(raise_), "fund_raise_last": raise_[0]["at"] if raise_ else None,
            "flags": [{"category": c, "label": LABEL[c], "count": n} for c, n in sorted(counts.items(), key=lambda kv: -kv[1])
                      if any(i["category"] == c and i["severity"] != "info" for i in recent)]}


_MEETING_ON = re.compile(r"(?:held|scheduled|convened|meet|meeting)\s+on\s+(?:[A-Za-z]+day,?\s+)?(?:the\s+)?"
                        r"(\d{1,2}(?:st|nd|rd|th)?[-/.\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/.,\s]+\d{4}|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})", re.I)


def _meeting_day(text: str):
    """The date in "board meeting to be held on 17-Oct-2026" (and the other ways companies write it)."""
    m = _MEETING_ON.search(text or "")
    if not m:
        return None
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", m.group(1), flags=re.I)
    raw = " ".join(re.split(r"[-/.,\s]+", raw))
    for fmt in ("%d %b %Y", "%d %B %Y", "%d %m %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def upcoming_results(items: list[dict], today=None) -> dict | None:
    """The next board meeting a company has announced to consider its results, from its own intimation filing:
    {"date", "subject", "url"}, or None when none is scheduled from today on."""
    today = today or ist_now().date()
    for i in items:                         # newest filing first: a later intimation replaces an earlier one
        if i.get("category") not in ("results", "board"):
            continue
        hay = f"{i.get('subject') or ''} {i.get('text') or ''}"
        if not re.search(r"result", hay, re.I) or not re.search(r"board", hay, re.I):
            continue
        day = _meeting_day(hay)
        if day and day >= today:
            return {"date": day.isoformat(), "subject": i.get("subject") or "", "url": i.get("url")}
    return None


# ---------- insider trades, substantial acquisitions, bulk and block deals ----------
DEALS_DAYS = 365                     # how far back a company's deals list goes
DEAL_KINDS = {"insider": "Insider trade", "sast": "Substantial acquisition", "bulk": "Bulk deal", "block": "Block deal"}
DEAL_PAGES = {                       # where the exchange lists each kind, for rows that carry no document of their own
    "insider": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading",
    "sast": "https://www.nseindia.com/companies-listing/corporate-filings-regulation-29",
    "bulk": "https://www.nseindia.com/report-detail/display-bulk-and-block-deals",
    "block": "https://www.nseindia.com/report-detail/display-bulk-and-block-deals",
}
RELATIONS = {"promoter": "Promoter", "director": "Director", "kmp": "Key officer", "employee": "Employee", "other": "Other"}


def _field(r: dict, *names: str):
    """The first of `names` the row has a value for, matched without regard to case (the feeds change it)."""
    low = {str(k).lower(): v for k, v in r.items()}
    for n in names:
        v = low.get(n.lower())
        if v is not None and str(v).strip() not in ("", "-", "NA", "Nil", "nil"):
            return v
    return None


def _amount(v) -> float | None:
    """A number as the exchange writes it ("1,23,456", "12.5"), or None."""
    if v is None or isinstance(v, (bool, dict, list)):
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return f if f == f and abs(f) < 1e15 else None


def _iso_day(v) -> str | None:
    """"02-Oct-2026 19:30", "2026-10-02 18:00:00" or "02-10-2026" as 2026-10-02."""
    s = str(v or "").strip()
    for cand in (s, s[:11], s[:10]):
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"):
            try:
                return datetime.strptime(cand.strip(), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _relation(text) -> str | None:
    """Who the person is to the company, in five plain groups."""
    t = str(text or "").lower()
    if not t:
        return None
    if "promoter" in t:
        return "promoter"
    if "director" in t:
        return "director"
    if "key managerial" in t or "kmp" in t:
        return "kmp"
    if "employee" in t or "designated" in t:
        return "employee"
    return "other"


def _side(text) -> str | None:
    """Which way the shares went: bought, sold, or a pledge made, released or invoked."""
    t = str(text or "").strip().lower()
    if "invo" in t:
        return "invoked"
    if "revo" in t or "release" in t:
        return "released"
    if "pledge" in t or "encumb" in t:
        return "pledged"
    if t in ("b", "buy", "p") or t.startswith(("acq", "purchase", "buy")):
        return "bought"
    if t in ("s", "sell") or t.startswith(("sale", "sell", "sold", "dispos")):
        return "sold"
    return None


def _mode(text, side) -> str:
    """How: on the open market, off market, a pledge, an employee stock option, or something else."""
    t = str(text or "").lower()
    if side in ("pledged", "released", "invoked") or "pledge" in t or "encumb" in t:
        return "pledge"
    if any(w in t for w in ("off market", "off-market", "inter-se", "inter se", "gift", "transmission")):
        return "off_market"
    if "esop" in t or "esos" in t or "stock option" in t:
        return "esop"
    if "market" in t:
        return "market"
    return "other"


def _deal(kind, symbol, day, filed, who, relation, side, mode, mode_text, qty, price, value, pct_after, url) -> dict | None:
    """One deal in the shape every page reads; None when it lacks what makes it a deal (a date, who, which way)."""
    import hashlib
    symbol = str(symbol or "").strip().upper()[:20]
    who = re.sub(r"\s+", " ", str(who or "")).strip()[:120]
    if not day or not who or not side or not symbol:
        return None
    qty = abs(qty) if qty is not None else None
    if value is None and qty and price:
        value = round(qty * price, 2)
    if price is None and qty and value:
        price = round(value / qty, 2)
    link = str(url or "")
    key = "|".join(str(p) for p in (kind, symbol, day, who, side, qty))
    return {"id": hashlib.sha1(key.encode()).hexdigest()[:16], "kind": kind, "label": DEAL_KINDS[kind], "symbol": symbol,
            "date": day, "filed": filed or day, "who": who, "relation": relation, "side": side, "mode": mode,
            "mode_text": str(mode_text or "").strip()[:60] or None, "qty": qty, "price": price, "value": value,
            "pct_after": pct_after, "url": link if link.startswith("https://") else DEAL_PAGES[kind]}


def _rows(raw) -> list[dict]:
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def insider_rows(raw) -> list[dict]:
    """The exchange's insider-trading (PIT) disclosures as deals. Only trades in the company's shares are kept:
    warrants and derivatives count differently."""
    out = []
    for r in _rows(raw):
        sec = str(_field(r, "secType", "securityType") or "equity").lower()
        if "equity" not in sec and "share" not in sec:
            continue
        side = _side(_field(r, "tdpTransactionType", "transactionType", "acqSaleType"))
        how = _field(r, "acqMode", "modeOfAcquisition", "mode")
        d = _deal("insider", _field(r, "symbol"), _iso_day(_field(r, "acqtoDt", "acqfromDt", "date", "intimDt")),
                  _iso_day(_field(r, "date", "intimDt", "broadcastDate")), _field(r, "acqName", "personName", "name"),
                  _relation(_field(r, "personCategory", "category")), side, _mode(how, side), how,
                  _amount(_field(r, "secAcq", "noOfSecurities", "quantity")), None, _amount(_field(r, "secVal", "value")),
                  _amount(_field(r, "afterAcqSharesPer", "afterAcqPer")), _field(r, "xbrl", "attachment"))
        if d:
            out.append(d)
    return out


def sast_rows(raw) -> list[dict]:
    """Substantial acquisitions and sales (the takeover code's regulation 29 disclosures) as deals."""
    out = []
    for r in _rows(raw):
        side = _side(_field(r, "acqSaleType", "transactionType", "type"))
        qty = _amount(_field(r, "noOfShareAcq", "noOfSharesAcquired") if side == "bought"
                      else _field(r, "noOfShareSale", "noOfSharesSold"))
        qty = qty if qty is not None else _amount(_field(r, "quantity", "noOfShare", "secAcq"))
        how = _field(r, "acquisitionMode", "acqMode", "modeOfAcquisition")
        d = _deal("sast", _field(r, "symbol"),
                  _iso_day(_field(r, "acqToDate", "acquisitionDate", "dateOfAcq", "acqFromDate", "timestamp", "date")),
                  _iso_day(_field(r, "timestamp", "date", "broadcastDate")), _field(r, "acquirerName", "acqName", "name"),
                  _relation(_field(r, "promoterType", "personCategory")), side, _mode(how, side), how, qty, None, None,
                  _amount(_field(r, "totAftShareAcqPer", "totAftAcqSharePer", "afterAcqSharesPer")),
                  _field(r, "attachement", "attachment", "xbrl"))
        if d:
            out.append(d)
    return out


def block_rows(raw, kind: str) -> list[dict]:
    """Bulk or block deals (`kind`) as the exchange lists them: who, which way, how many and at what price."""
    out = []
    for r in _rows(raw):
        d = _deal(kind, _field(r, "BD_SYMBOL", "symbol"), _iso_day(_field(r, "BD_DT_DATE", "date", "mTIMESTAMP")), None,
                  _field(r, "BD_CLIENT_NAME", "clientName", "client"), None, _side(_field(r, "BD_BUY_SELL", "buySell", "side")),
                  "market", None, _amount(_field(r, "BD_QTY_TRD", "qty", "quantity")),
                  _amount(_field(r, "BD_TP_WATP", "watp", "price")), None, None, None)
        if d:
            out.append(d)
    return out


def sort_deals(rows: list[dict]) -> list[dict]:
    """Newest first, each deal once."""
    seen, out = set(), []
    for d in sorted(rows, key=lambda d: (d["date"], d["filed"], d["who"]), reverse=True):
        if d["id"] not in seen:
            seen.add(d["id"])
            out.append(d)
    return out


# ---------- exchange surveillance lists (ASM, GSM, ESM, trade-to-trade, price bands, the F&O ban) ----------
SURV_PAGES = {                       # where the exchange publishes each list, for the explanations' links
    "asm": "https://www.nseindia.com/reports/asm",
    "gsm": "https://www.nseindia.com/reports/gsm",
    "esm": "https://www.nseindia.com/reports/esm",
    "fo_ban": "https://www.nseindia.com/market-data/securities-available-for-trading",
    "bands": "https://www.nseindia.com/market-data/securities-available-for-trading",
}
SEC_LIST = "https://nsearchives.nseindia.com/content/equities/sec_list.csv"
# the F&O ban file: today's under /content/fo, the older address under /archives, then the day-stamped copies
# (fo_secban_05102026.csv) of the last few days, newest first, in case the plain name isn't published
FO_BAN_URLS = ("https://nsearchives.nseindia.com/content/fo/fo_secban.csv",
               "https://nsearchives.nseindia.com/archives/fo/sec_ban/fo_secban.csv")
FO_BAN_DAILY = ("https://nsearchives.nseindia.com/archives/fo/sec_ban/fo_secban_{d}.csv",
                "https://nsearchives.nseindia.com/content/fo/fo_secban_{d}.csv")
FO_BAN_DAYS = 4
FO_BAN = FO_BAN_URLS[0]


def fo_ban_urls(today=None) -> list[str]:
    """Every address the F&O ban file may be at, in the order to try them."""
    day = today or ist_now().date()
    dated = [u.format(d=(day - timedelta(days=n)).strftime("%d%m%Y")) for n in range(FO_BAN_DAYS) for u in FO_BAN_DAILY]
    return [*FO_BAN_URLS, *dated]
T2T_SERIES = ("BE", "BZ")           # trade-to-trade: every trade settles by delivery
_ROMAN = {"0": 0, "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}
_STAGE = re.compile(r"stage\s*[-:._]?\s*(vi|iv|v|iii|ii|i|[0-6])\b", re.I)
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&\-_.]{0,19}$")


def stage_of(text) -> int | None:
    """The stage in "Stage II", "LTASM Stage - 4" or "stage-1"; None when the text names none."""
    m = _STAGE.search(str(text or ""))
    if not m:
        return None
    g = m.group(1).lower()
    return int(g) if g.isdigit() else _ROMAN.get(g)


def _sym(v) -> str | None:
    s = str(v or "").strip().upper()
    return s if _SYMBOL.match(s) else None


def _row_stage(r: dict) -> int | None:
    """A list row's stage: from a field named for it first (a bare "II" counts there), then any text that says one."""
    for k, v in r.items():
        key = str(k).lower()
        if any(w in key for w in ("stage", "indicator", "surv")):
            s = stage_of(v)
            if s is None and str(v or "").strip().lower() in _ROMAN:
                s = _ROMAN[str(v).strip().lower()]
            if s is not None:
                return s
    for v in r.values():
        if isinstance(v, str) and (s := stage_of(v)) is not None:
            return s
    return None


def stage_rows(raw) -> dict[str, int | None]:
    """{symbol: stage} from one of the exchange's surveillance lists, read loosely: the symbol from any field called
    symbol, the stage from whichever field states it. A list with rows but no readable symbol has changed shape."""
    rows = [r for _, rs in _lists_in(raw) for r in _rows(rs)]
    out: dict[str, int | None] = {}
    for r in rows:
        sym = _sym(_field(r, "symbol", "tradingSymbol", "scrip"))
        if sym:
            out[sym] = _row_stage(r)
    if rows and not out:
        raise ValueError("rows without symbols")
    return out


def _lists_in(data) -> list[tuple[str, list]]:
    """Every list of rows in an answer, with the key path that led to it ("longterm.data"), so the long-term and
    short-term halves of the ASM answer can be told apart whatever the exchange calls them."""
    out = []

    def walk(x, path, depth):
        if depth > 6:
            return
        if isinstance(x, list) and any(isinstance(r, dict) for r in x):
            out.append((path, x))
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{path}.{k}".lower() if path else str(k).lower(), depth + 1)
    walk(data, "", 0)
    return out


def asm_rows(data) -> dict[str, dict[str, int | None]]:
    """The ASM answer as {"lt": {symbol: stage}, "st": {...}}. Each half is told by its key (long/short) or, in one
    flat list, by each row's own wording (LT-ASM / ST-ASM)."""
    out: dict[str, dict] = {"lt": {}, "st": {}}
    lists = _lists_in(data)
    for path, rows in lists:
        side = "lt" if re.search(r"long|\blt", path) else "st" if re.search(r"short|\bst", path) else None
        for r in _rows(rows):
            sym = _sym(_field(r, "symbol", "tradingSymbol"))
            if not sym:
                continue
            which = side
            if which is None:
                text = " ".join(str(v) for v in r.values() if isinstance(v, str)).lower()
                which = "st" if re.search(r"short|st[- ]?asm", text) else "lt"
            out[which][sym] = _row_stage(r)
    if lists and not any(out.values()):
        raise ValueError("rows without symbols")
    return out


def fo_ban_rows(text: str) -> tuple[str | None, list[str]]:
    """The F&O ban file: ("2026-10-05" the trade date it states, [symbols]). The file reads "Securities in Ban For
    Trade Date 05-OCT-2026:" then "1,SYMBOL" lines (or NIL)."""
    text = str(text or "")
    if "<html" in text.lower() or not text.strip():
        raise ValueError("not the ban file")
    m = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})", text)
    day = _iso_day(m.group(1).title()) if m else None
    syms = []
    for line in text.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2 and parts[0].isdigit() and (s := _sym(parts[1])):
            syms.append(s)
    if not day and not syms:
        raise ValueError("no date and no rows")
    return day, sorted(set(syms))


def sec_list_rows(text: str) -> dict[str, dict]:
    """The exchange's securities-available-for-trading file: {symbol: {"series", "band"}} for the equity series, the
    band as the daily price limit in percent (None for "No Band")."""
    import csv
    import io
    out: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(str(text or "").replace("\x00", ""))):
        row = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items() if isinstance(k, str)}
        sym, series = _sym(row.get("symbol")), (row.get("series") or "").upper()
        if not sym or series not in ("EQ",) + T2T_SERIES:
            continue
        band = _amount(row.get("band") or row.get("price band") or row.get("price band %"))
        out[sym] = {"series": series, "band": band if band and 0 < band <= 100 else None}
    return out


# (path, referer, extra params, row reader) for each kind of deal; symbol and dates are added per call
DEAL_FEEDS = {
    "insider": ("/api/corporates-pit", DEAL_PAGES["insider"], {"index": "equities"}, insider_rows),
    "sast": ("/api/corporate-sast-reg29", DEAL_PAGES["sast"], {"index": "equities"}, sast_rows),
    "bulk": ("/api/historicalOR/bulk-block-short-deals", DEAL_PAGES["bulk"], {"optionType": "bulk_deals"},
             lambda raw: block_rows(raw, "bulk")),
    "block": ("/api/historicalOR/bulk-block-short-deals", DEAL_PAGES["block"], {"optionType": "block_deals"},
              lambda raw: block_rows(raw, "block")),
}


class NSEFilings:
    """NSE's public corporate-announcements feed. The site hands out session cookies on its home page and refuses
    API calls without them, so we visit the home page first and again whenever the cookies expire."""
    name = "the exchange"
    BASE = "https://www.nseindia.com"

    def __init__(self, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.http = httpx.Client(base_url=self.BASE, timeout=15, transport=transport, follow_redirects=True,
                                 headers={"User-Agent": BROWSER_UA, "Accept": "application/json, text/plain, */*",
                                          "Accept-Language": "en-US,en;q=0.9", "Referer": self.BASE + "/"})
        self.sleep = sleep
        self.limit = RateLimit(30, 5)
        self.cache = TTLCache(max_items=2000)
        self._primed = 0.0
        self._lock = threading.Lock()
        self._fails, self._down_until = 0, 0.0
        self._circuits: dict[str, tuple[int, float]] = {}       # the deal feeds' own breakers: (fails, down until)

    def _prime(self, force: bool = False):
        with self._lock:
            if not force and time.time() - self._primed < 600:
                return
            try:
                self.http.get("/", headers={"Accept": "text/html"})
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"Couldn't reach the exchange ({e.__class__.__name__}).", busy=True) from None
            self._primed = time.time()

    def _get(self, path: str, params: dict, referer: str | None = None, circuit: str = "main"):
        """One API call, with the same circuit breaker as the other sources: after three outages in a row the
        exchange is treated as down for a minute, so pages answer at once instead of queueing behind it. The deal
        feeds have a breaker of their own (`circuit`), so one of them breaking can't take the filings down with it."""
        if circuit != "main":
            return self._get_on(circuit, path, params, referer)
        if time.time() < self._down_until:
            raise SourceError(self.name, "The exchange feed isn't answering right now. Try again in a minute.", busy=True)
        try:
            out = self._get_once(path, params, referer)
        except SourceError as e:
            if e.busy:
                self._fails += 1
                if self._fails >= 3:
                    self._down_until, self._fails = time.time() + 60, 0
            raise
        self._fails = 0
        return out

    def _get_on(self, circuit: str, path: str, params: dict, referer: str | None):
        fails, down = self._circuits.get(circuit, (0, 0.0))
        if time.time() < down:
            raise SourceError(self.name, "The exchange feed isn't answering right now. Try again in a minute.", busy=True)
        try:
            out = self._get_once(path, params, referer)
        except SourceError as e:
            if e.busy:
                fails += 1
                self._circuits[circuit] = (0, time.time() + 60) if fails >= 3 else (fails, 0.0)
            raise
        self._circuits[circuit] = (0, 0.0)
        return out

    BACKOFF = (0.0, 2.0)            # the pause before each retry after a refusal: at once with fresh cookies, then later

    def _get_once(self, path: str, params: dict, referer: str | None = None):
        self._prime()
        headers = {"Referer": referer} if referer else None
        for attempt in range(len(self.BACKOFF) + 1):
            if not self.limit.take():
                raise SourceError(self.name, "The exchange feed is busy (our rate limit). Try again in a minute.", busy=True)
            try:
                r = self.http.get(path, params=params, headers=headers)
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"Couldn't reach the exchange ({e.__class__.__name__}).", busy=True) from None
            if r.status_code in (401, 403, 429) and attempt < len(self.BACKOFF):
                if self.BACKOFF[attempt] or r.status_code == 429:
                    self.sleep(max(self.BACKOFF[attempt], 1.0))
                self._prime(force=True)          # cookies expired, or a bot guard: fresh ones, then again
                if referer:                      # the quote API also wants the cookies set by the stock's own page
                    try:
                        self.http.get(referer, headers={"Accept": "text/html"})
                    except httpx.HTTPError:
                        pass
                continue
            if r.status_code in (401, 403, 429):  # turned away every time: a refusal to try again later, not a fact
                raise SourceError(self.name, f"The exchange feed refused the request ({r.status_code}). Try again later.", busy=True)
            if r.status_code >= 500:
                raise SourceError(self.name, f"The exchange feed is busy ({r.status_code}). Try again in a minute.", busy=True)
            if r.status_code >= 400:
                raise SourceError(self.name, f"The exchange feed has nothing for that ({r.status_code}).")
            try:
                return r.json()
            except ValueError:
                raise SourceError(self.name, "The exchange sent a page instead of data (it may be blocking us).", busy=True) from None
        raise SourceError(self.name, "The exchange feed refused the request after a fresh session. Try again later.", busy=True)

    def announcements(self, symbol: str, days: int = LOOKBACK_DAYS) -> list[dict]:
        key = (symbol, days)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        to = ist_now()
        data = self._get("/api/corporate-announcements", {
            "index": "equities", "symbol": symbol,
            "from_date": (to - timedelta(days=days)).strftime("%d-%m-%Y"), "to_date": to.strftime("%d-%m-%Y")})
        rows = data.get("data") if isinstance(data, dict) else data
        items = normalise(rows or [])
        self.cache.set(key, items, 1800)
        return items

    def market_flags(self, day) -> list[dict]:
        """The red and amber filings of every NSE company on one day (flagged_rows), from the exchange's list for the
        whole market: one call a day. A day still in progress is read again after a few minutes."""
        key = ("market", day.isoformat())
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        text = day.strftime("%d-%m-%Y")
        data = self._get("/api/corporate-announcements", {"index": "equities", "from_date": text, "to_date": text},
                         referer="https://www.nseindia.com/companies-listing/corporate-filings-announcements")
        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise SourceError(self.name, "The exchange's announcements list wasn't in the expected shape.")
        out = flagged_rows(rows)
        self.cache.set(key, out, 900)
        return out

    def board_meetings(self, frm: datetime, to: datetime) -> list[dict]:
        """Every board meeting companies told the exchange about between two dates, as the exchange lists them
        (symbol, company, meeting date, purpose). One call for the whole market, cached for an hour."""
        key = ("meetings", frm.date().isoformat(), to.date().isoformat())
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        data = self._get("/api/corporate-board-meetings", {"index": "equities", "from_date": frm.strftime("%d-%m-%Y"),
                                                           "to_date": to.strftime("%d-%m-%Y")},
                         referer="https://www.nseindia.com/companies-listing/corporate-filings-board-meetings")
        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise SourceError(self.name, "The exchange's board-meeting list wasn't in the expected shape.")
        rows = [r for r in rows if isinstance(r, dict)]
        self.cache.set(key, rows, 3600)
        return rows

    def corporate_actions(self, frm: datetime | None = None, to: datetime | None = None, symbol: str | None = None) -> list[dict]:
        """The exchange's corporate actions (dividends, bonus issues, splits, buybacks, rights), as it lists them:
        every company's with an ex-date between two dates, or one company's whole history. Cached for an hour."""
        params = {"index": "equities"}
        if symbol:
            params["symbol"] = symbol
        if frm and to:
            params.update(from_date=frm.strftime("%d-%m-%Y"), to_date=to.strftime("%d-%m-%Y"))
        key = ("actions",) + tuple(sorted(params.items()))
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        data = self._get("/api/corporates-corporateActions", params,
                         referer="https://www.nseindia.com/companies-listing/corporate-filings-actions")
        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise SourceError(self.name, "The exchange's corporate-actions list wasn't in the expected shape.")
        rows = [r for r in rows if isinstance(r, dict)]
        self.cache.set(key, rows, 3600)
        return rows

    def _quote(self, symbol: str) -> dict:
        """The exchange's quote for one stock, asked the way its own quote page asks (it refuses bare requests)."""
        from urllib.parse import quote as q
        data = self._get("/api/quote-equity", {"symbol": symbol},
                         referer=f"https://www.nseindia.com/get-quotes/equity?symbol={q(symbol)}")
        return data if isinstance(data, dict) else {}

    def industry(self, symbol: str) -> list[str]:
        """The exchange's own classification: macro sector › sector › industry › basic industry."""
        key = ("industry", symbol)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        info = self._quote(symbol).get("industryInfo") or {}
        path = []
        for k in ("macro", "sector", "industry", "basicIndustry"):
            v = str(info.get(k) or "").strip()
            if v and v not in path:
                path.append(v)
        self.cache.set(key, path, 7 * 86400)
        return path

    # each index's constituent file in the exchange's archive (the same host as the list of companies). The live
    # index API sits behind the website's bot checks and turned the server away, so NIFTY 500, Midcap 150 and Smallcap
    # 250 never had a list of stocks and their breadth was never counted (R5O-013); the file is read first.
    INDEX_FILES = {"NIFTY 50": "ind_nifty50list.csv", "NIFTY 500": "ind_nifty500list.csv",
                   "NIFTY MIDCAP 150": "ind_niftymidcap150list.csv", "NIFTY SMALLCAP 250": "ind_niftysmallcap250list.csv",
                   "NIFTY NEXT 50": "ind_niftynext50list.csv", "NIFTY 100": "ind_nifty100list.csv", "NIFTY 200": "ind_nifty200list.csv"}
    INDEX_URL = "https://nsearchives.nseindia.com/content/indices/"

    def index_file(self, index: str) -> list[str]:
        """An index's stocks from its constituent file in the exchange's archive ("Company Name,Industry,Symbol,...")."""
        import csv
        import io
        name = self.INDEX_FILES.get(index.upper())
        if not name:
            raise SourceError(self.name, f"No constituent file is known for {index}.")
        try:
            r = self.http.get(self.INDEX_URL + name, headers={"Accept": "text/csv,*/*"})
        except httpx.HTTPError as e:
            raise SourceError(self.name, f"Couldn't reach the exchange's list for {index} ({e.__class__.__name__}).", busy=True) from None
        if r.status_code >= 400:
            raise SourceError(self.name, f"The exchange's list for {index} was refused ({r.status_code}).")
        out = []
        for row in csv.DictReader(io.StringIO(r.text)):
            row = {str(k or "").strip().upper(): str(v or "").strip() for k, v in row.items()}
            sym = row.get("SYMBOL", "").upper()
            if sym and re.fullmatch(r"[A-Z0-9&\-]{1,20}", sym):
                out.append(sym)
        return list(dict.fromkeys(out))

    def index_members(self, index: str) -> list[str]:
        """The stocks in an NSE index (e.g. "NIFTY 500"): the constituent file in the exchange's archive, else its live
        index list; cached for a day."""
        key = ("index", index)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        try:
            got = self.index_file(index)
        except SourceError:
            got = []
        if len(got) >= 20:
            self.cache.set(key, got, 86400)
            return got
        data = self._get("/api/equity-stockIndices", {"index": index},
                         referer="https://www.nseindia.com/market-data/live-equity-market")
        rows = (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise SourceError(self.name, f"The exchange's list for {index} wasn't in the expected shape.")
        out = [str(r.get("symbol")).strip().upper() for r in rows
               if isinstance(r, dict) and r.get("symbol") and str(r.get("symbol")).strip().upper() != index.upper()]
        if not out:
            raise SourceError(self.name, f"The exchange's list for {index} came back empty.")
        out = list(dict.fromkeys(out))
        self.cache.set(key, out, 86400)
        return out

    EQUITY_LIST = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

    def all_equities(self) -> list[dict]:
        """Every company listed on NSE's main board (series EQ and BE), from the exchange's own daily file:
        [{symbol, name, listed, isin}] with the listing date as ISO. New listings appear the day they list."""
        import csv
        import io
        try:
            r = self.http.get(self.EQUITY_LIST, headers={"Accept": "text/csv,*/*"})
        except httpx.HTTPError as e:
            raise SourceError(self.name, f"Couldn't reach the exchange's list of companies ({e.__class__.__name__}).", busy=True) from None
        if r.status_code >= 400:
            raise SourceError(self.name, f"The exchange's list of companies was refused ({r.status_code}).")
        out = []
        for row in csv.DictReader(io.StringIO(r.text)):
            row = {str(k or "").strip().upper(): str(v or "").strip() for k, v in row.items()}
            sym, series = row.get("SYMBOL", "").upper(), row.get("SERIES", "").upper()
            if not sym or series not in ("EQ", "BE") or sym.endswith(("-RE", "-PP")):
                continue                        # rights entitlements and partly paid shares aren't companies
            try:
                listed = datetime.strptime(row.get("DATE OF LISTING", ""), "%d-%b-%Y").date().isoformat()
            except ValueError:
                listed = None
            out.append({"symbol": sym, "name": row.get("NAME OF COMPANY") or sym, "listed": listed,
                        "isin": row.get("ISIN NUMBER", "").upper() or None})
        if len(out) < 100:                      # the real file has about two thousand; fewer means a broken answer
            raise SourceError(self.name, f"The exchange's list of companies looked wrong ({len(out)} companies).")
        return list({c["symbol"]: c for c in out}.values())

    def holidays(self, segment: str = "CM") -> list[str]:
        """The exchange's published trading holidays, as ISO dates (it lists the current year, and the next one once
        announced, usually in December). `segment`: "CM" equities, "CD" currency derivatives."""
        data = self._get("/api/holiday-master", {"type": "trading"},
                         referer="https://www.nseindia.com/resources/exchange-communication-holidays")
        rows = (data or {}).get(segment) if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise SourceError(self.name, "The exchange's holiday list wasn't in the expected shape.")
        out = []
        for r in rows:
            raw = str((r or {}).get("tradingDate") or "").strip()
            try:
                out.append(datetime.strptime(raw, "%d-%b-%Y").date().isoformat())
            except ValueError:
                continue
        if not out:
            raise SourceError(self.name, "The exchange's holiday list came back empty.")
        return sorted(set(out))

    def last_price(self, symbol: str) -> float | None:
        """The exchange's own last traded price, for checking StratLab's prices against the source."""
        info = self._quote(symbol).get("priceInfo") or {}
        try:
            return float(info.get("lastPrice")) or None
        except (TypeError, ValueError):
            return None

    def _deals(self, kind: str, symbol: str | None, days: int, to: datetime | None) -> list[dict]:
        """One kind of deal from the exchange, for one company (`symbol`) or the whole market (None), over the `days`
        up to `to` (today). A feed that answers in a shape we can't read is an error, not an empty list."""
        to = to or ist_now()
        frm = to - timedelta(days=days)
        key = ("deals", kind, symbol, frm.date().isoformat(), to.date().isoformat())
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        path, referer, extra, read = DEAL_FEEDS[kind]
        dates = ({"from": frm.strftime("%d-%m-%Y"), "to": to.strftime("%d-%m-%Y")} if kind in ("bulk", "block")
                 else {"from_date": frm.strftime("%d-%m-%Y"), "to_date": to.strftime("%d-%m-%Y")})
        data = self._get(path, {**extra, **({"symbol": symbol} if symbol else {}), **dates}, referer=referer, circuit=kind)
        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise SourceError(self.name, f"The exchange's {DEAL_KINDS[kind].lower()} list wasn't in the expected shape.")
        if symbol:                          # a company's own list may leave its symbol out of each row
            rows = [r if _field(r, "symbol", "BD_SYMBOL") else {**r, "symbol": symbol} for r in _rows(rows)]
        out = sort_deals(read(rows))
        if symbol:
            out = [d for d in out if d["symbol"] == symbol.upper()]
        self.cache.set(key, out, 3600 if symbol else 1800)
        return out

    def insider_trades(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        """Trades by promoters, directors and key staff in the company's own shares (insider-trading disclosures),
        pledges made and released among them."""
        return self._deals("insider", symbol, days, to)

    def sast(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        """Substantial acquisitions and sales: holders crossing 5% and moving 2% at a time (the takeover code)."""
        return self._deals("sast", symbol, days, to)

    def bulk_deals(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        """Bulk deals: one client trading more than half a percent of the company's shares in a day."""
        return self._deals("bulk", symbol, days, to)

    def block_deals(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        """Block deals: large trades matched in the exchange's separate block-deal window."""
        return self._deals("block", symbol, days, to)

    # the surveillance lists: each read once a day for the whole market, behind a breaker of their own
    def _surv_json(self, path: str, what: str, read):
        key = ("surv", path)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        data = self._get(path, {}, referer=SURV_PAGES[what], circuit="surveillance")
        try:
            out = read(data)
        except (ValueError, TypeError, AttributeError):
            raise SourceError(self.name, f"The exchange's {what.upper()} list wasn't in the expected shape.") from None
        self.cache.set(key, out, 1800)
        return out

    def _surv_text(self, url: str) -> str:
        """One of the exchange's daily files, with the surveillance breaker: three outages in a row and it rests a
        minute."""
        fails, down = self._circuits.get("surveillance", (0, 0.0))
        if time.time() < down:
            raise SourceError(self.name, "The exchange's files aren't answering right now. Try again in a minute.", busy=True)
        busy = True
        try:
            try:
                r = self.http.get(url, headers={"Accept": "text/csv,text/plain,*/*"})
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"Couldn't reach the exchange's files ({e.__class__.__name__}).", busy=True) from None
            busy = r.status_code == 429 or r.status_code >= 500
            if r.status_code >= 400:
                raise SourceError(self.name, f"The exchange's file was refused ({r.status_code}).", busy=busy)
        except SourceError:
            if busy:
                fails += 1
                self._circuits["surveillance"] = (0, time.time() + 60) if fails >= 3 else (fails, 0.0)
            raise
        self._circuits["surveillance"] = (0, 0.0)
        return r.text

    def asm_list(self) -> dict[str, dict[str, int | None]]:
        """The Additional Surveillance Measure lists: {"lt": {symbol: stage}, "st": {symbol: stage}}."""
        return self._surv_json("/api/reportASM", "asm", asm_rows)

    def gsm_list(self) -> dict[str, int | None]:
        """The Graded Surveillance Measure list: {symbol: stage}."""
        return self._surv_json("/api/reportGSM", "gsm", stage_rows)

    def esm_list(self) -> dict[str, int | None]:
        """The Enhanced Surveillance Measure list (small companies): {symbol: stage}."""
        return self._surv_json("/api/reportESM", "esm", stage_rows)

    def fo_ban(self) -> tuple[str | None, list[str]]:
        """The securities in the F&O ban period: (the trade date the file is for, [symbols]). The exchange has moved
        this file before, so each known address is tried in turn: one that isn't there (404, or a page instead of the
        file) moves on to the next, while the exchange being down or busy stops at once (the breaker counts it)."""
        missing, shape = None, False
        for url in fo_ban_urls():
            try:
                return fo_ban_rows(self._surv_text(url))
            except SourceError as e:
                if e.busy:
                    raise
                missing = e
            except ValueError:
                shape = True
        if shape:
            raise SourceError(self.name, "The exchange's F&O ban file wasn't in the expected shape.")
        raise SourceError(self.name, f"The exchange's F&O ban file wasn't at any of its known addresses ({str(missing).rstrip('.')}).")

    def security_bands(self) -> dict[str, dict]:
        """Every equity's series (EQ, or BE/BZ for trade-to-trade) and daily price band, from the exchange's
        securities-available-for-trading file. Far fewer rows than the market has means a broken answer."""
        rows = sec_list_rows(self._surv_text(SEC_LIST))
        if len(rows) < 300:                 # the real file has a couple of thousand equities
            raise SourceError(self.name, f"The exchange's price-band file looked wrong ({len(rows)} securities).")
        return rows

    def etf_list(self):
        """Every ETF's last price and last published NAV, as the exchange's ETF page lists them (etf_nav.py reads it). One
        call for the whole market, behind a breaker of its own. It names each ETF's underlying, not the fund, and
        carries no ISIN: etf_securities() has those."""
        return self._get("/api/etf", {}, referer="https://www.nseindia.com/market-data/exchange-traded-funds-etf", circuit="etf")

    def etf_securities(self) -> dict[str, str]:
        """{symbol: ISIN} for every ETF the exchange lists, from its ETF securities file. Cached for a day."""
        hit = self.cache.get(("etf-isins",))
        if hit is not None:
            return hit
        out = etf_isins(self._surv_text(ETF_SECURITIES_URL))
        if not out:
            raise SourceError(self.name, "The exchange's ETF list file had no ISINs.")
        self.cache.set(("etf-isins",), out, 86400)
        return out

    CAS_PAGE = "https://www.nseindia.com/market-data/closing-auction-session"

    def cas_stocks(self):
        """The closing auction session's per-stock data as the exchange's CAS page shows it (closing_auction.py reads
        it): reference price, band, indicative equilibrium price and quantity, final price, imbalance, best bid and
        ask, and the list of eligible symbols. One call for the market, behind a breaker of its own."""
        return self._get("/api/NextApi/apiClient/casApi", {"functionName": "getCASData"}, referer=self.CAS_PAGE, circuit="cas")

    def cas_indices(self):
        """The F&O indices on the CAS page: value, previous close and the indicative close during the auction."""
        return self._get("/api/NextApi/apiClient/casApi", {"functionName": "getAllFnoIndexData"}, referer=self.CAS_PAGE, circuit="cas")


ETF_SECURITIES_URL = "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv"


def etf_isins(text: str) -> dict[str, str]:
    """{symbol: ISIN} from the exchange's ETF securities file ("Symbol,Underlying Asset,SecurityName,DateofListing,
    MarketLot,ISINNumber,..."), the columns found by name."""
    import csv
    import io
    rows = list(csv.reader(io.StringIO(text or "")))
    if not rows:
        return {}
    head = [c.strip().lower() for c in rows[0]]
    try:
        at_sym = head.index("symbol")
        at_isin = next(i for i, c in enumerate(head) if "isin" in c)
    except (ValueError, StopIteration):
        return {}
    out = {}
    for r in rows[1:]:
        if len(r) > max(at_sym, at_isin):
            sym, isin = r[at_sym].strip().upper(), r[at_isin].strip().upper()
            if sym and re.fullmatch(r"IN[A-Z0-9]{10}", isin):
                out[sym] = isin
    return out


BSE_ATTACH = "https://www.bseindia.com/xml-data/corpfiling/"
# What Chrome sends when bseindia.com's own announcements page asks api.bseindia.com for data (a cross-origin XHR on
# the same site): a full browser version string with the client hints that match it, the page's origin as both
# Origin and Referer (Chrome trims a cross-origin referrer to the origin), and the fetch metadata of a CORS call.
# A bot guard compares these: a short "Chrome/128.0" with no client hints, or an Origin on the page visit itself,
# looks like a script.
BSE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
BSE_CLIENT_HINTS = {"sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"'}
BSE_API_HEADERS = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.bseindia.com",
                   "Referer": "https://www.bseindia.com/", "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors",
                   "Sec-Fetch-Site": "same-site"}
BSE_PAGE_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1", "Upgrade-Insecure-Requests": "1"}


def bse_rows(table: list[dict]) -> list[dict]:
    """BSE's announcement rows in the shape NSE's take, so one set of rules reads both."""
    out = []
    for r in table if isinstance(table, list) else []:
        if not isinstance(r, dict):
            continue
        when = str(r.get("DissemDT") or r.get("NEWS_DT") or r.get("DT_TM") or "")[:19].replace("T", " ")
        name = str(r.get("ATTACHMENTNAME") or "").strip()
        folder = "AttachHis" if str(r.get("PDFFLAG") or "0").strip() not in ("0", "") else "AttachLive"
        subject = str(r.get("SUBCATNAME") or r.get("CATEGORYNAME") or "").strip()
        headline = str(r.get("NEWSSUB") or "").strip()
        # NEWSSUB reads "Company Ltd - 500325 - Investor Presentation": the part after the code says what it is
        tail = headline.split(" - ", 2)[-1] if headline.count(" - ") >= 2 else headline
        out.append({"seq_id": str(r.get("NEWSID") or ""), "sort_date": when,
                    "desc": subject if subject and subject != "-" else tail,
                    "attchmntText": f"{tail}. {r.get('HEADLINE') or ''}".strip(),
                    "attchmntFile": f"{BSE_ATTACH}{folder}/{name}" if name.lower().endswith(".pdf") and "/" not in name else ""})
    return out


class BSEFilings:
    """BSE's public corporate-announcements feed, for companies listed only on BSE (by six-digit scrip code). BSE's
    bot guard turns away requests that come without the cookies its website hands out (403), and refuses a burst of
    them, so we visit the website first, space the calls out, and on a refusal fetch fresh cookies and try again
    after a pause. A refusal that outlasts the retries is "busy" (try again later), not a fact about the company."""
    name = "the exchange"
    BASE = "https://api.bseindia.com/BseIndiaAPI/api"
    HOME = "https://www.bseindia.com/"
    PAGES = 6                       # 50 a page: about a year's filings for a busy small company
    WINDOW = 365                    # days one request covers: BSE answers a longer range with "Date range cannot exceed 12 months."
    GAP = 0.5                       # seconds between calls at least: a steady pace, not a burst
    BACKOFF = (2.0, 6.0)            # the pauses before each retry after a refusal (401, 403, 429)
    REST = 600                      # refused through every retry: leave BSE alone this long (ten minutes)

    def __init__(self, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.http = httpx.Client(base_url=self.BASE, timeout=15, transport=transport, follow_redirects=True,
                                 headers={"User-Agent": BSE_UA, "Accept-Language": "en-US,en;q=0.9", **BSE_CLIENT_HINTS})
        self.limit = RateLimit(30, 5)
        self.cache = TTLCache(max_items=2000)
        self.sleep = sleep
        self._fails, self._down_until = 0, 0.0
        self._primed, self._last = 0.0, 0.0
        self._refused_at: float | None = None      # when BSE last turned us away through every retry (None: answering)
        self._ok_at: float | None = None
        self._lock = threading.Lock()

    def state(self) -> dict:
        """Whether BSE is turning this server away right now, for the admin page: since when, and the last answer."""
        iso = lambda t: datetime.fromtimestamp(t, IST).isoformat(timespec="minutes") if t else None   # noqa: E731
        return {"refusing": self._refused_at is not None, "refused_at": iso(self._refused_at), "ok_at": iso(self._ok_at)}

    def _prime(self, force: bool = False):
        """Visit BSE's website for the session cookies its API checks for (kept for ten minutes), the way a browser
        opens the page: a navigation, with no Origin."""
        with self._lock:
            if not force and time.time() - self._primed < 600:
                return
            try:
                self.http.get(self.HOME, headers=BSE_PAGE_HEADERS)
            except httpx.HTTPError:
                pass                        # the API call itself says whether BSE is reachable
            self._primed = time.time()

    def _pace(self):
        """At least GAP seconds since the last call, whichever thread made it."""
        with self._lock:
            now = time.time()
            wait = self._last + self.GAP - now
            self._last = max(now, self._last + self.GAP)
        if wait > 0:
            self.sleep(wait)

    def _call(self, path: str, params: dict) -> dict:
        """One API call: paced, with fresh cookies and a pause before each retry when BSE turns it away."""
        if time.time() < self._down_until:
            raise SourceError(self.name, "The exchange feed isn't answering right now. Try again in a minute.", busy=True)
        self._prime()
        for attempt in range(len(self.BACKOFF) + 1):
            if not self.limit.take():
                raise SourceError(self.name, "The exchange feed is busy (our rate limit). Try again in a minute.", busy=True)
            self._pace()
            try:
                r = self.http.get(path, params=params, headers=BSE_API_HEADERS)
            except httpx.HTTPError as e:
                self._failed()
                raise SourceError(self.name, f"Couldn't reach the exchange ({e.__class__.__name__}).", busy=True) from None
            if r.status_code in (401, 403, 429):
                if attempt == len(self.BACKOFF):        # turned away every time: rest, and say try again later
                    self._down_until, self._fails = time.time() + self.REST, 0
                    self._refused_at = self._refused_at or time.time()
                    raise SourceError(self.name, f"The exchange feed refused the request ({r.status_code}). Try again later.", busy=True)
                wait = self.BACKOFF[attempt]
                try:                                    # a 429 may say how long to wait
                    wait = max(wait, min(30.0, float(r.headers.get("retry-after") or 0)))
                except ValueError:
                    pass
                self.sleep(wait)
                self._prime(force=True)
                continue
            if r.status_code >= 500:
                self._failed()
                raise SourceError(self.name, f"The exchange feed is busy ({r.status_code}). Try again in a minute.", busy=True)
            if r.status_code >= 400:
                raise SourceError(self.name, f"The exchange feed has nothing for that ({r.status_code}).")
            try:
                data = r.json()
            except ValueError:
                self._failed()
                raise SourceError(self.name, "The exchange sent a page instead of data (it may be blocking us).", busy=True) from None
            self._fails, self._refused_at, self._ok_at = 0, None, time.time()
            return data if isinstance(data, dict) else {}
        raise SourceError(self.name, "The exchange feed refused the request. Try again later.", busy=True)   # not reached

    def _page(self, code: str, frm: datetime, to: datetime, page: int) -> dict:
        data = self._call("/AnnSubCategoryGetData/w", {
            "pageno": page, "strCat": "-1", "strPrevDate": frm.strftime("%Y%m%d"), "strScrip": code,
            "strSearch": "P", "strToDate": to.strftime("%Y%m%d"), "strType": "C", "subcategory": "-1"})
        # a request BSE won't serve comes back as {"Status": false, "Message": "..."} and no table: say so, rather
        # than read it as a company that filed nothing
        if data.get("Status") is False and "Table" not in data:
            raise SourceError(self.name, "The exchange feed turned the request down: "
                                         f"{str(data.get('Message') or 'no reason given')[:120]}")
        return data

    def _failed(self):
        self._fails += 1
        if self._fails >= 3:
            self._down_until, self._fails = time.time() + 60, 0

    def announcements(self, code: str, days: int = LOOKBACK_DAYS) -> list[dict]:
        code = str(code).strip()
        if not code.isdigit():
            raise SourceError(self.name, "That isn't a BSE scrip code.")
        key = (code, days)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        to = ist_now()
        start = to - timedelta(days=days)
        rows: list[dict] = []
        while to >= start:                  # BSE serves at most twelve months a request: a year at a time, newest first
            frm = max(start, to - timedelta(days=self.WINDOW))
            rows += self._window(code, frm, to)
            to = frm - timedelta(days=1)
        items = normalise(rows)
        self.cache.set(key, items, 1800)
        return items

    def _window(self, code: str, frm: datetime, to: datetime) -> list[dict]:
        """One company's announcements between two dates, page by page (50 a page, up to PAGES pages)."""
        rows: list[dict] = []
        for page in range(1, self.PAGES + 1):
            table = self._page(code, frm, to, page).get("Table") or []
            rows += bse_rows(table)
            if len(table) < 50:
                break
        return rows

    def industry(self, code: str) -> list[str]:
        """BSE's own classification of a company, from its quote page's header: sector › industry › group › sub-group
        (the same four levels as NSE's). Cached for a week."""
        code = str(code).strip()
        if not code.isdigit():
            raise SourceError(self.name, "That isn't a BSE scrip code.")
        hit = self.cache.get(("industry", code))
        if hit is not None:
            return hit
        data = self._call("/ComHeadernew/w", {"quotetype": "EQ", "scripcode": code, "seriesid": ""})
        path: list[str] = []
        for names in (("Sector", "SectorName"), ("IndustryNew", "Industry"), ("IGroupName", "IGroup"), ("ISubGroupName", "ISubGroup")):
            v = str(_field(data, *names) or "").strip()
            if v and v not in path and v.upper() not in ("NA", "N.A.", "-"):
                path.append(v)
        self.cache.set(("industry", code), path, 7 * 86400)
        return path

    def corporate_actions(self, code: str) -> list[dict]:
        """One BSE company's corporate actions (dividends, bonus issues, splits...), as BSE lists them. Cached for an hour."""
        code = str(code).strip()
        if not code.isdigit():
            raise SourceError(self.name, "That isn't a BSE scrip code.")
        hit = self.cache.get(("actions", code))
        if hit is not None:
            return hit
        data = self._call("/DefaultData/w", {"Fdate": "", "Purposecode": "", "TDate": "", "ddlcategorys": "E",
                                             "ddlindustrys": "", "scripcode": code, "segmentid": "0", "strSearch": "S"})
        rows = data.get("Table") if isinstance(data, dict) else data
        rows = [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
        self.cache.set(("actions", code), rows, 3600)
        return rows


class IndiaFilings:
    """Filings for any Indian company: NSE's feed by symbol, or BSE's by scrip code for companies listed only on
    BSE (`code_of` says which: a BSE code, or None for an NSE company). Everything else is NSE's."""

    def __init__(self, nse, bse, code_of, twin_of=None):
        self.nse, self.bse, self.code_of, self.twin_of = nse, bse, code_of, twin_of

    def announcements(self, symbol: str, days: int = LOOKBACK_DAYS) -> list[dict]:
        code = self.code_of(symbol)
        if code:
            return self.bse.announcements(code, days)
        items = self.nse.announcements(symbol, days)
        if items or not self.twin_of:
            return items
        # NSE's feed answers nothing for some symbols whose company is listed and filing (Abbott India, Goodyear India):
        # the same company's filings under its BSE listing, when it has one
        try:
            twin = self.twin_of(symbol)
            return self.bse.announcements(twin, days) if twin else items
        except SourceError:
            return items

    def announcements_both(self, symbol: str, days: int = LOOKBACK_DAYS) -> list[dict]:
        """A company's filings from both exchanges it is listed on, each row marked with its `exchange` ("NSE" or
        "BSE"), newest first. A BSE-only company has BSE's alone. When one exchange doesn't answer the other's rows
        stand; only when neither answers is the error raised."""
        code = self.code_of(symbol)
        if code:
            return [{**i, "exchange": "BSE"} for i in self.bse.announcements(code, days)]
        rows: list[dict] = []
        err: SourceError | None = None
        try:
            rows += [{**i, "exchange": "NSE"} for i in self.nse.announcements(symbol, days)]
        except SourceError as e:
            err = e
        twin = None
        try:
            twin = self.twin_of(symbol) if self.twin_of else None
            if twin:
                rows += [{**i, "exchange": "BSE"} for i in self.bse.announcements(twin, days)]
        except SourceError:
            pass                              # BSE not answering: NSE's rows stand
        if not rows and err:               # NSE did not answer and BSE has nothing to add
            raise err
        rows.sort(key=lambda x: x["at"], reverse=True)
        return rows

    def industry(self, symbol: str) -> list[str]:
        code = self.code_of(symbol)
        return self.bse.industry(code) if code else self.nse.industry(symbol)

    def last_price(self, symbol: str) -> float | None:
        return None if self.code_of(symbol) else self.nse.last_price(symbol)

    def _nse_only(self, symbol: str | None):
        if symbol and self.code_of(symbol):
            raise SourceError(self.nse.name, "Deals and insider trades cover companies listed on NSE; this one is listed only on BSE.")

    def insider_trades(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        self._nse_only(symbol)
        return self.nse.insider_trades(symbol, days, to)

    def sast(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        self._nse_only(symbol)
        return self.nse.sast(symbol, days, to)

    def bulk_deals(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        self._nse_only(symbol)
        return self.nse.bulk_deals(symbol, days, to)

    def block_deals(self, symbol: str | None = None, days: int = DEALS_DAYS, to: datetime | None = None) -> list[dict]:
        self._nse_only(symbol)
        return self.nse.block_deals(symbol, days, to)

    def actions_of(self, symbol: str) -> tuple[str, list[dict]]:
        """("nse" or "bse", the company's corporate actions as that exchange lists them)."""
        code = self.code_of(symbol)
        return ("bse", self.bse.corporate_actions(code)) if code else ("nse", self.nse.corporate_actions(symbol=symbol))

    def __getattr__(self, name):
        return getattr(self.nse, name)


def report(feed, symbol: str) -> dict:
    """Timeline plus the 3-month summary for one company (NSE symbol, or a BSE-only one)."""
    items = feed.announcements(symbol)
    return {"symbol": symbol, "items": items[:200], "summary": summarise(items), "window_days": WINDOW_DAYS,
            "lookback_days": LOOKBACK_DAYS}


# ---------- the daily watchlist red-flag alert ----------
ALERT_KEY = "filingalert:"            # app_settings: filingalert:<uid> = {"uid", "on", "seen": ISO time of the newest filing seen}
SEND_AT = "20:30"                     # IST, after most companies have filed for the day
MAX_SYMBOLS = 25


def alert_state(uid: str) -> dict:
    try:
        return json.loads(db.get_setting(ALERT_KEY + uid) or "{}")
    except (ValueError, TypeError):
        return {}


def set_alert(uid: str, on: bool):
    st = alert_state(uid)
    st.update(uid=uid, on=bool(on))
    if on and not st.get("seen"):     # start from now: only filings made after switching on are sent
        st["seen"] = ist_now().isoformat(timespec="minutes")
    db.set_setting(ALERT_KEY + uid, json.dumps(st))


def watchlist_symbols(uid: str, region: str = "IN") -> list[str]:
    try:
        items = json.loads(db.get_setting(f"watchlist:{uid}") or "{}").get("items") or []
    except (ValueError, TypeError):
        items = []
    return [i["symbol"] for i in items if i.get("region") == region and i.get("symbol")][:MAX_SYMBOLS]


def followed_symbols(uid: str) -> list[str]:
    """The Indian stocks the person follows for red flags: what they hold (My Holdings, ETFs and bonds left out), then
    their watchlist, each once, as other pages count "your stocks"."""
    from .. import holdings, instrument_kinds
    held = [i["symbol"] for i in holdings.indian(holdings.load(uid)["items"])
            if instrument_kinds.base(i.get("kind") or instrument_kinds.classify(i["symbol"], i.get("isin"), i.get("name"))) == "stock"]
    out: list[str] = []
    for s in held + watchlist_symbols(uid):
        if s not in out:
            out.append(s)
    return out[:MAX_SYMBOLS]


def overview(feed, symbols: list[str]) -> dict:
    """The 3-month summary for each watchlist stock, the ones with red flags first."""
    rows, problems = [], []
    for sym in symbols:
        try:
            items = feed.announcements(sym)
        except SourceError as e:
            problems.append(f"{sym}: {e}")
            continue
        s = summarise(items)
        cutoff = (ist_now() - timedelta(days=WINDOW_DAYS)).isoformat()
        rows.append({"symbol": sym, "summary": s,
                     "flags": [i for i in items if i["severity"] != "info" and i["at"] >= cutoff][:5]})
    rows.sort(key=lambda r: (-r["summary"]["red"], -r["summary"]["amber"], r["symbol"]))
    return {"rows": rows, "problems": problems, "days": WINDOW_DAYS}


def alert_text(new: list[tuple[str, dict]]) -> str:
    parts = [f"{sym}: {i['label']}" for sym, i in new[:8]]
    more = f" and {len(new) - 8} more" if len(new) > 8 else ""
    return "New filings on your watchlist: " + "; ".join(parts) + more + ". From the exchange's filings; not advice."


class Alerts:
    """Once a day in the evening, send each subscriber the red and amber filings their watchlist stocks made since
    the last message."""

    def __init__(self, feed, notify, can_alert):
        self.feed, self.notify, self.can_alert = feed, notify, can_alert
        self.last_day = None
        self.status = {"last_run": None, "sent": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="filing-alerts").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(IST))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("filing alerts:", e)
            time.sleep(300)

    def due(self, now: datetime) -> str | None:
        local = now.astimezone(IST)
        day = local.date().isoformat()
        if local.strftime("%H:%M") < SEND_AT or self.last_day == day:
            return None
        if db.get_setting("filingalert-day") == day:         # already sent today (before a restart)
            self.last_day = day
            return None
        return day

    def tick(self, now: datetime):
        day = self.due(now)
        if not day:
            return
        self.last_day = day
        db.set_setting("filingalert-day", day)
        sent = 0
        for raw in db.settings_with_prefix(ALERT_KEY):
            try:
                sub = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not sub.get("on"):
                continue
            profile = db.get_profile(sub["uid"])
            symbols = followed_symbols(sub["uid"])
            if not symbols or not self.can_alert(profile):
                continue
            seen, newest, new = sub.get("seen") or "", sub.get("seen") or "", []
            for sym in symbols:
                try:
                    items = self.feed.announcements(sym)
                except SourceError:
                    continue
                for i in items:
                    if i["at"] > seen and i["severity"] != "info":
                        new.append((sym, i))
                    newest = max(newest, i["at"])
            if new:
                new.sort(key=lambda x: (x[1]["severity"] != "red", x[1]["at"]))
                self.notify(profile, "StratLab: new filings to look at", alert_text(new), url="/research/filings")
                sent += 1
            sub["seen"] = newest
            db.set_setting(ALERT_KEY + sub["uid"], json.dumps(sub))
        self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
