"""The earnings-call calendar: every upcoming results call and meeting with analysts or investors, India and the US, with
its date, time and zone and the links its company's filings give; after the event, links to the transcript, the audio
recording and the presentation once a later filing carries them.

India: the evening read of the exchange's announcements for the whole market (redflags.py, one call a day) also hands
over the filings about calls and meetings with analysts or investors (`meet_rows`): their notices, transcripts,
recordings and presentations. A notice's PDF is read once (its first pages, text and link targets) for the event's date,
time and zone and for a webcast or dial-in registration link; a recording's for its audio link; a transcript's for the
day the call was held. At most MAX_READS documents a run, the newest notices first; what isn't read waits for the next
run, and what is still unread past its days is kept with its filing link alone. Companies listed only on BSE are not in
the exchange's list, so not here.

US: the results calendar's US rows (results.py: the session the company announced, before the open or after the close,
from the US market calendar) and, once filed, the earnings release (8-K, item 2.02).

Stored as one document per region (concalls:IN: the events from a month back to two months ahead, the filings waiting
for a read, and the filings already seen). Links are only ever ones a filing carries: the filing itself, or a link
written in it. Facts only: a date, a time as filed, a type and links; never a view on the company."""
import io
import json
import re
import threading
import zlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import db
from .intel import filings
from .intel.net import SourceError, TTLCache

KEY = "concalls:IN"                    # {"events": [...], "pending": [...], "seen": {id: day}, "through", "at", ...}
IST = ZoneInfo("Asia/Kolkata")
FIRST_DAYS = 30                        # how far back the first run reads the exchange's daily lists
OVERLAP = 2                            # days read again each run (late filings)
MAX_READS = 300                        # filings' PDFs read in one run
MAX_PDF = 6 * 1024 * 1024              # a notice or a transcript's cover is a few hundred KB; a bigger file is left unread
PAGES = 3                              # pages of a filing read: the letter and its enclosure (a call's details)
NOTICE_DAYS = 45                       # an event this long after its notice is still read from it (notices come up to ~4 weeks ahead)
FOLLOW_DAYS = 21                       # a transcript, recording or presentation filed this long after a call is that call's
DECK_BEFORE = 2                        # ...and a presentation up to this many days before it
KEEP_BEHIND, KEEP_AHEAD = 35, 75       # the events kept, around today
PENDING_DAYS = {"notice": 30, "recording": 14, "transcript": 14, "outcome": 14}
SEEN_DAYS = 12
UPCOMING_DAYS = 30                     # the page's "coming up" window
PAST_DAYS = 21                         # ...and its "held" window
MAX_ROWS = 400                         # rows in one answer
NOTE = {
    "IN": "From the companies' own filings with the exchange: each notice's date, time and zone as filed, and only links the "
          "filings carry. After a call, its transcript, recording or presentation once a later filing has it. Not advice.",
    "US": "Results days and the session each company announced (before the open or after the close, US Eastern time), and the "
          "earnings release once it is filed with the SEC. Not advice.",
}
TYPE_NAME = {"call": "Earnings call", "meet": "Analyst or investor meet", "results": "Results"}
LINK_NAME = {"notice": "Notice", "join": "Webcast or dial-in", "transcript": "Transcript", "audio": "Audio", "recording": "Recording",
             "presentation": "Presentation", "release": "Earnings release (8-K)", "outcome": "Outcome"}
_lock = threading.Lock()
_mem = TTLCache(max_items=8, max_bytes=24 * 1024 * 1024)


# ---------- which filings are about calls and meetings ----------
AUDIO = re.compile(r"\baudio\b|\brecording\b|\bvideo\b|\breplay\b", re.I)
HELD = re.compile(r"\boutcome\b|\bheld on\b|\bwas held\b", re.I)
NOTICE = re.compile(r"\bschedule\b|\bintimation\b|\binform\w*\b.{0,60}\b(?:will|is scheduled|to be held|shall)\b|\bwill be held\b|"
                    r"\bis scheduled\b|\bto be held\b|\bparticipat\w*\b|\binvit\w*\b|\bconference\b(?!\s*call)", re.I)
MEETISH = re.compile(r"analysts?\s*/\s*institutional|investors?\s*(?:/\s*analysts?\s*)?meet|analysts?\s*meet|con\.?\s?call|concall|"
                     r"earnings?\s*(?:conference\s*)?call|conference call|investors?\s*conference|investors?\s*call|analysts?\s*call|"
                     r"schedule of meet|group meeting|one[- ]on[- ]one", re.I)


def kind_of(subject: str, text: str, url: str | None, category: str | None = None) -> str | None:
    """What a filing about calls and meetings is: "notice" (a call or meeting to come), "transcript", "recording" (its
    audio or video), "presentation", "outcome" (a call held, without its transcript or recording), or None when it
    is about something else (a shareholders' meeting, results, a board meeting)."""
    from .deepdive import PRESENTATION, TRANSCRIPT, _agm
    hay = f"{subject or ''} {text or ''} {filings.file_words(url)}"
    if _agm(hay):
        return None
    meet = category in ("concall", "investor_meet") or bool(MEETISH.search(hay))
    if TRANSCRIPT.search(hay):
        return "transcript"
    if meet and AUDIO.search(hay):
        return "recording"
    if category == "presentation" or PRESENTATION.search(hay):
        return "presentation"
    if not meet:
        return None
    if HELD.search(hay) and not NOTICE.search(f"{subject or ''} {text or ''}"):
        return "outcome"
    return "notice"


def meet_rows(raw: list[dict]) -> list[dict]:
    """The exchange's whole-market list's filings about calls and meetings with analysts or investors, each with its
    company's symbol and name: {id, symbol, company, at, kind, subject, text, url}. The id is the same each time the
    same filing is read."""
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9&\-._]{1,20}", sym):
            continue
        for it in filings.normalise([r]):
            kind = kind_of(it["subject"], it["text"], it["url"], it["category"])
            if not kind or not it["url"]:
                continue
            fid = f"{sym}|{it['at']}|{zlib.crc32((it['subject'] + it['url']).encode()):08x}"
            if fid in seen:
                continue
            seen.add(fid)
            out.append({"id": fid, "symbol": sym, "company": str(r.get("sm_name") or "").strip()[:80] or None, "at": it["at"],
                        "kind": kind, "subject": it["subject"][:160], "text": it["text"][:300], "url": it["url"]})
    return out


# ---------- reading a filing ----------
def pdf_read(data: bytes, pages: int = PAGES) -> tuple[str, list[str]]:
    """A PDF's text (its first `pages` pages) and the link targets on those pages. A large file is read in a short-lived
    process (pdf_proc), text only."""
    from . import pdf_proc
    if len(data) >= pdf_proc.SUBPROCESS_BYTES:
        texts, _ = pdf_proc.page_texts(data, pages)
        return "\n".join(t for t in texts if t), []
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    text, uris = [], []
    for page in reader.pages[:pages]:
        try:
            text.append(page.extract_text() or "")
        except Exception:
            continue
        try:
            for a in page.get("/Annots") or []:
                act = (a.get_object() or {}).get("/A")
                uri = act.get_object().get("/URI") if act is not None else None
                if uri:
                    uris.append(str(uri))
        except Exception:
            continue
    return "\n".join(text), uris


URL_TEXT = re.compile(r"(?:https?://|www\.)[^\s\"'<>()\[\]{}|]+", re.I)
JOIN = re.compile(r"diamondpass|choruscall|zoom\.us|webex|teams\.microsoft|teams\.live|youtube\.com|youtu\.be|webcast|livestream|"
                  r"register|registration|gotowebinar|bigmarker|meet\.google|vimeo\.com|on24|streamyard|airmeet|hubilo|"
                  r"globalmeet|webinar|join", re.I)
AUDIO_FILE = re.compile(r"\.(?:mp3|m4a|wav|aac|ogg|mp4|wma)(?:$|\?)", re.I)
EXCHANGE_HOSTS = re.compile(r"(?:^|\.)(?:nseindia\.com|bseindia\.com|sebi\.gov\.in)$", re.I)


def _clean(url: str) -> str | None:
    """A link as a browser would open it, or None when it isn't a web address (an email, an exchange's site, a
    malformed or over-long string)."""
    u = str(url or "").strip().rstrip(".,;:)")
    if u.lower().startswith("www."):
        u = "https://" + u
    m = re.match(r"^(https?)://([A-Za-z0-9.\-]+)(?::\d+)?(/[^\s]*)?$", u)
    if not m or len(u) > 400 or "." not in m.group(2) or re.fullmatch(r"[\d.]+", m.group(2)):
        return None
    if EXCHANGE_HOSTS.search(m.group(2)):
        return None
    return u


def links_in(text: str, uris: list[str]) -> list[str]:
    """Every web address a filing carries: its link targets, then the ones written in its text (a link broken across
    a line by the PDF is joined back)."""
    joined = re.sub(r"((?:https?://|www\.)\S+)[ \t]*\n[ \t]*(\S*[/=?&]\S*)", lambda m: m.group(1) + m.group(2), text or "")
    out = []
    for u in list(uris or []) + [m.group(0) for m in URL_TEXT.finditer(joined)]:
        c = _clean(u)
        if c and c not in out:
            out.append(c)
    return out


def typed_links(kind: str, urls: list[str]) -> list[dict]:
    """The links worth showing, each with what it is: a webcast or dial-in registration (a notice's), an audio file or
    a recording's page (a recording's), a transcript or presentation PDF. A company's home page, an email or anything
    else isn't shown."""
    from .deepdive import PRESENTATION, TRANSCRIPT
    out = []
    for u in urls:
        path = re.sub(r"^https?://[^/]+", "", u)
        words = re.sub(r"[_\-+/%.]+", " ", u)
        if AUDIO_FILE.search(path):
            k = "audio"
        elif path.lower().split("?")[0].endswith(".pdf"):
            k = "transcript" if TRANSCRIPT.search(words) else "presentation" if PRESENTATION.search(words) else None
        elif kind == "notice" and JOIN.search(u):
            k = "join"
        elif kind in ("recording", "outcome") and len(path.strip("/")) > 1 and re.search(r"audio|record|webcast|replay|call|investor|conference", words, re.I):
            k = "recording"
        elif kind == "transcript" and len(path.strip("/")) > 1 and TRANSCRIPT.search(words):
            k = "transcript"
        else:
            k = None
        if k and not any(x["u"] == u for x in out):
            out.append({"k": k, "u": u})
    return out[:6]


_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATES = [
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*(?:day of\s+)?" + _MON + r"[\s\-/.,']*(\d{4})\b", re.I), "dmy"),
    (re.compile(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})\b", re.I), "mdy"),
    (re.compile(r"\b(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{4})\b"), "dmy"),
]
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
TIME = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?\s?m\b\.?|p\.?\s?m\b\.?|hrs?\b\.?|hours\b)|\b([01]?\d|2[0-3]):([0-5]\d)\b", re.I)
ZONE = re.compile(r"\b(IST|GMT|BST|SGT|HKT|JST|CET|CEST|UTC|EST|EDT|ET)\b|(indian standard time|india time)", re.I)
RESCHEDULED = re.compile(r"reschedul|postpon|revised (?:date|schedule)|change in (?:the )?(?:date|schedule)|preponed", re.I)


def dated(text: str) -> list[tuple[int, int, date]]:
    """Every date written in a filing: (start, end, day), in the order they appear."""
    text = _tidy(text)
    found = []
    for rx, order in DATES:
        for m in rx.finditer(text):
            g = m.groups()
            try:
                if order == "mdy":
                    d = date(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1]))
                elif g[1].isdigit():
                    d = date(int(g[2]), int(g[1]), int(g[0]))
                else:
                    d = date(int(g[2]), MONTHS[g[1][:3].lower()], int(g[0]))
            except (ValueError, KeyError):
                continue
            found.append((m.start(), m.end(), d))
    found.sort()
    out, last = [], -1                     # one date per place in the text (two patterns can read the same words)
    for s, e, d in found:
        if s >= last:
            out.append((s, e, d))
            last = e
    return out


def time_of(text: str) -> str | None:
    """The first clock time in `text` as 24-hour "HH:MM" ("4:00 PM" → "16:00", "15:00 hrs" → "15:00")."""
    for m in TIME.finditer(text or ""):
        if m.group(4) is not None:
            h, mi = int(m.group(4)), int(m.group(5))
        else:
            h, mi, suffix = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower().replace(".", "").replace(" ", "")
            if suffix in ("am", "pm"):
                if not 1 <= h <= 12:
                    continue
                h = (h % 12) + (12 if suffix == "pm" else 0)
            elif m.group(2) is None and not 0 <= h <= 23:
                continue
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
    return None


def zone_of(text: str) -> str | None:
    m = ZONE.search(text or "")
    if not m:
        return None
    return "IST" if m.group(2) else m.group(1).upper()


def _day(iso) -> date | None:
    try:
        return date.fromisoformat(str(iso)[:10])
    except ValueError:
        return None


CALL_WORDS = re.compile(r"earnings?\s*(?:conference\s*)?call|conference\s*call|con\.?\s?call|concall|results?\s*call|post[- ]results?|"
                        r"investors?(?:\s*(?:and|&)\s*analysts?)?\s*call|analysts?(?:\s*(?:and|&)\s*investors?)?\s*call|earnings?\s*webinar", re.I)
MEET_WORDS = re.compile(r"group\s*meet|one[- ]on[- ]one|1\s*on\s*1|investors?'?\s*conference(?!\s*call)|annual .{0,40}conference(?!\s*call)|\bforum\b|\bsummit\b|"
                        r"road\s*show|non[- ]deal|in[- ]person|\bphysical\b|investors?\s*day|\bmeetings?\s+with\b", re.I)


def _tidy(text: str) -> str:
    """A PDF's text with the breaks its layout puts inside numbers put back ("202 6", "11 th")."""
    text = re.sub(r"\b(20\d) ?\n? ?(\d)\b", r"\1\2", text or "")
    return re.sub(r"(\d)\s+(st|nd|rd|th)\b", r"\1\2", text)


def notice_event(row: dict, text: str) -> dict | None:
    """The event a notice announces: {type "call" or "meet", dates (the days after the filing it names, up to
    NOTICE_DAYS), time, tz}, or None when it names no day ahead. A call is on the first day it names after the filing;
    a schedule of meetings lists its days. The exchange's own subject for every such filing ("Analysts/Institutional
    Investor Meet/Con. Call Updates") says nothing about which it is, so it is left out of the reading."""
    filed = _day(row.get("at"))
    if not filed:
        return None
    body = _tidy(filings.MEET_SUBJECT.sub(" ", f"{row.get('subject') or ''}. {row.get('text') or ''}\n{text or ''}"))
    calls = len(CALL_WORDS.findall(body))        # a call named more than once is a call, whatever the letter says around it
    is_call = calls >= 2 or (calls == 1 and not MEET_WORDS.search(body))
    found = dated(body)
    ahead = [(s, e, d) for s, e, d in found if filed < d <= filed + timedelta(days=NOTICE_DAYS)]
    if not ahead:
        # a call or meeting the same day: its day written after "on" ("will be meeting the investors on Monday, November
        # 10"), not the letter's own date at its head
        ahead = [(s, e, d) for s, e, d in found if d == filed and re.search(r"\bon\s+(?:\w+day,?\s+)?(?:the\s+)?$", body[max(0, s - 30):s], re.I)]
    if not ahead and re.search(r"\b(?:later )?today\b", body, re.I):
        ahead = [(len(body), len(body), filed)]
    if not ahead:
        return None
    s, e, first = ahead[0]
    near = body[e:e + 160]
    tm = time_of(near) or (time_of(body) if is_call else None)
    tz = (zone_of(near) or zone_of(body)) if tm else None
    days = [first] if is_call else sorted({d for _, _, d in ahead})[:12]
    return {"type": "call" if is_call else "meet", "dates": [d.isoformat() for d in days], "time": tm, "tz": tz,
            "rescheduled": bool(RESCHEDULED.search(body))}


def held_on(row: dict, text: str) -> date | None:
    """The day a transcript's or recording's call was held, when the filing says it ("held on November 5, 2026")."""
    filed = _day(row.get("at"))
    body = f"{row.get('subject') or ''}. {row.get('text') or ''}\n{text or ''}"
    for m in re.finditer(r"\b(?:held|conducted|hosted|organi[sz]ed)\b(?:\s+\w+){0,3}?\s+on\b", body, re.I):
        got = [d for s, _, d in dated(body[m.end():m.end() + 60]) if filed is None or filed - timedelta(days=60) <= d <= filed]
        if got:
            return got[0]
    if re.search(r"\b(?:held|was held)\s+today\b", body, re.I):
        return filed
    return None


# ---------- the store ----------
def load() -> dict:
    hit = _mem.get(KEY)
    if hit is not None:
        return hit
    try:
        raw = db.json_value(db.get_setting(KEY), {})
    except Exception:
        raw = {}
    out = {"events": [e for e in raw.get("events") or [] if isinstance(e, dict) and e.get("date") and e.get("symbol")],
           "pending": [p for p in raw.get("pending") or [] if isinstance(p, dict) and p.get("id")],
           "seen": raw.get("seen") if isinstance(raw.get("seen"), dict) else {},
           **{k: raw.get(k) for k in ("through", "at", "read", "unread", "last_error")}}
    _mem.set(KEY, out, 300)
    return out


def save(doc: dict) -> None:
    db.set_setting(KEY, json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    _mem.set(KEY, None, 0)


def forget() -> None:
    _mem.clear()


def _add_link(ev: dict, k: str, url: str | None, at: str | None) -> None:
    if not url or any(x["u"] == url for x in ev["links"]):
        return
    ev["links"].append({"k": k, "u": url, "at": (at or "")[:16]})


def _event(row: dict, typ: str, day: str, **kw) -> dict:
    return {"id": f"{row['symbol']}|{day}|{typ}", "symbol": row["symbol"], "name": row.get("company"), "date": day, "type": typ,
            "filed": row["at"][:16], "links": [], **kw}


def apply_notice(events: dict, row: dict, ev: dict | None) -> None:
    """Put a read notice's event in `events` ({id: event}): a new event, or the links added to the same company's
    event on the same day. A rescheduled call replaces the company's earlier upcoming call."""
    if not ev:
        return
    first = ev["dates"][0]
    if ev["type"] == "call" and ev.get("rescheduled"):
        for k, e in list(events.items()):
            if e["symbol"] == row["symbol"] and e["type"] == "call" and e["date"] != first and e["filed"] < row["at"][:16] and e["date"] >= row["at"][:10]:
                del events[k]
    eid = f"{row['symbol']}|{first}|{ev['type']}"
    e = events.get(eid) or _event(row, ev["type"], first)
    if len(ev["dates"]) > 1:
        e["until"] = max(ev["dates"][-1], e.get("until") or "")
        e["dates"] = sorted(set(e.get("dates") or []) | set(ev["dates"]))[:12]
    if ev.get("time") and (not e.get("time") or row["at"][:16] >= e["filed"]):
        e["time"], e["tz"] = ev["time"], ev.get("tz")
    e["name"] = e.get("name") or row.get("company")
    _add_link(e, "notice", row["url"], row["at"])
    for x in row.get("links") or []:
        if x["k"] in ("join", "presentation"):
            _add_link(e, x["k"], x["u"], row["at"])
    events[eid] = e


def apply_followup(events: dict, row: dict, held: date | None) -> None:
    """Put a transcript, recording, outcome or presentation on its call: the company's call on the day it says it was
    held, else its latest call or meeting up to FOLLOW_DAYS before the filing (a presentation: up to DECK_BEFORE days
    after it). A transcript or recording that matches none is a call of its own, on the day it was held (or filed)."""
    filed = _day(row["at"])
    mine = [e for e in events.values() if e["symbol"] == row["symbol"]]
    match = None
    if held:
        match = next((e for e in mine if e["date"] == held.isoformat() and e["type"] == "call"), None) or \
            next((e for e in mine if e["date"] <= held.isoformat() <= (e.get("until") or e["date"])), None)
    if match is None and filed:
        lo, hi = (filed - timedelta(days=FOLLOW_DAYS)).isoformat(), (filed + timedelta(days=DECK_BEFORE if row["kind"] == "presentation" else 0)).isoformat()
        near = [e for e in mine if lo <= e["date"] <= hi]
        near.sort(key=lambda e: (e["type"] == "call", e["date"]))
        match = near[-1] if near else None
    if match is None:
        if row["kind"] == "presentation" or not filed:
            return
        day = (held or filed).isoformat()
        match = events.setdefault(f"{row['symbol']}|{day}|call", _event(row, "call", day, from_followup=True))
    kind = {"transcript": "transcript", "recording": "recording", "outcome": "outcome", "presentation": "presentation"}[row["kind"]]
    own = [x for x in row.get("links") or [] if x["k"] in ("audio", "recording", "transcript", "presentation")]
    if kind == "recording" and own:
        for x in own:
            _add_link(match, x["k"], x["u"], row["at"])
        _add_link(match, "outcome", row["url"], row["at"])
    else:
        _add_link(match, kind, row["url"], row["at"])
        for x in own:
            if x["k"] in ("audio", "recording"):
                _add_link(match, x["k"], x["u"], row["at"])


def process(doc: dict, rows: list[dict], read=None, limit: int = MAX_READS, today: date | None = None) -> dict:
    """Add the day lists' new rows to the store, read what can be read (notices first, newest first; `read(url)` gives a
    filing's (text, link targets) or raises), and put each read filing on the calendar. Returns counts."""
    today = today or datetime.now(IST).date()
    seen = {k: v for k, v in (doc.get("seen") or {}).items() if v >= (today - timedelta(days=SEEN_DAYS)).isoformat()}
    pending = {p["id"]: p for p in doc.get("pending") or []}
    for r in rows:
        if r["id"] in seen or r["id"] in pending:
            continue
        pending[r["id"]] = {**r, "tries": 0}
    events = {e["id"]: e for e in doc.get("events") or []}
    # notices first, the newest first (the calls coming up); then what was filed after calls, the oldest first, so a
    # call's notice is on the calendar before its transcript looks for it
    notices = sorted((p for p in pending.values() if p["kind"] == "notice"), key=lambda p: p["at"], reverse=True)
    follow = sorted((p for p in pending.values() if p["kind"] != "notice"), key=lambda p: p["at"])
    reads = failed = 0
    busy = False
    for p in notices + follow:
        age = (today - (_day(p["at"]) or today)).days
        text, uris, done = "", [], False
        if p["kind"] != "presentation" and read is not None and reads < limit and not busy:
            try:
                text, uris = read(p["url"])
                done = True
            except SourceError as e:
                failed += 1
                p["tries"] = p.get("tries", 0) + 1
                busy = bool(getattr(e, "busy", False))
            except Exception:
                failed += 1
                p["tries"] = p.get("tries", 0) + 1
            reads += 1
        give_up = p["kind"] == "presentation" or age > PENDING_DAYS.get(p["kind"], 14) or p.get("tries", 0) >= 2
        if not done and not give_up:
            continue
        row = {**p, "links": typed_links(p["kind"], links_in(text, uris)) if done else []}
        if p["kind"] == "notice":
            apply_notice(events, row, notice_event(row, text) if done else notice_event(row, ""))
        else:
            apply_followup(events, row, held_on(row, text))
        pending.pop(p["id"], None)
        seen[p["id"]] = p["at"][:10]
    lo, hi = (today - timedelta(days=KEEP_BEHIND)).isoformat(), (today + timedelta(days=KEEP_AHEAD)).isoformat()
    doc["events"] = sorted((e for e in events.values() if lo <= (e.get("until") or e["date"]) and e["date"] <= hi), key=lambda e: (e["date"], e["symbol"]))
    keep = (today - timedelta(days=max(PENDING_DAYS.values()) + 1)).isoformat()
    doc["pending"] = [{k: v for k, v in p.items() if k != "text" or p["kind"] == "notice"} for p in pending.values() if p["at"][:10] >= keep]
    doc["seen"] = seen
    return {"reads": reads, "failed": failed, "pending": len(doc["pending"]), "events": len(doc["events"]), "busy": busy}


class Reader:
    """A filing's PDF, read for its text and links: only on the exchange's document hosts, MAX_PDF at most."""

    def __init__(self, docs=None):
        from .docs import Docs
        self.docs = docs or Docs()

    def __call__(self, url: str) -> tuple[str, list[str]]:
        from . import docs, memguard
        if not docs.allowed(url):
            raise SourceError("the exchange", "That filing isn't on the exchange's document site.")
        data = self.docs._download(url, (), MAX_PDF)
        if not data[:5].startswith(b"%PDF"):
            raise SourceError("the exchange", "The link didn't return a PDF.")
        with memguard.heavy("concalls"):
            return pdf_read(data)


def after_india(feed, today: date | None = None, read=None, sleep=None) -> dict | None:
    """After the evening's read of the exchange's lists (redflags.Runner.run_india): the days' filings about calls and
    meetings (the lists just read come from the feed's memory), then the reads. None when the feed can't give them."""
    fn = getattr(feed, "market_meets", None)
    if not callable(fn):
        return None
    today = today or datetime.now(IST).date()
    with _lock:
        doc = load()
        doc = {**doc, "events": list(doc["events"]), "pending": list(doc["pending"]), "seen": dict(doc["seen"])}
        try:
            start = date.fromisoformat(doc["through"]) - timedelta(days=OVERLAP)
        except (KeyError, TypeError, ValueError):
            start = today - timedelta(days=FIRST_DAYS)
        start = max(start, today - timedelta(days=FIRST_DAYS))
        rows, through, last_error, day = [], doc.get("through"), None, start
        while day <= today:
            try:
                rows += fn(day)
                through = day.isoformat()
            except SourceError as e:
                last_error = str(e)[:160]
                if getattr(e, "busy", False):
                    break
            day += timedelta(days=1)
            if sleep:
                sleep(0.25)
        got = process(doc, rows, read if read is not None else Reader(), today=today)
        doc.update(through=through, at=datetime.now(IST).isoformat(timespec="minutes"), read=got["reads"], unread=got["pending"],
                   last_error=last_error)
        save(doc)
        return {**got, "through": through, "error": last_error}


# ---------- the page ----------
def _link_out(x: dict) -> dict:
    return {"kind": x["k"], "label": LINK_NAME.get(x["k"], x["k"].title()), "url": x["u"], "filed": x.get("at") or None}


LINK_ORDER = {"join": 0, "notice": 1, "transcript": 2, "audio": 3, "recording": 4, "presentation": 5, "outcome": 6, "release": 7}


def india_rows(frm: date, to: date) -> list[dict]:
    out = []
    for e in load()["events"]:
        last = e.get("until") or e["date"]
        if last < frm.isoformat() or e["date"] > to.isoformat():
            continue
        links = sorted((_link_out(x) for x in e.get("links") or []), key=lambda x: LINK_ORDER.get(x["kind"], 9))
        out.append({"id": e["id"], "region": "IN", "symbol": e["symbol"], "name": e.get("name") or e["symbol"], "date": e["date"],
                    "until": e.get("until"), "dates": e.get("dates"), "time": e.get("time"), "tz": e.get("tz"),
                    "session": None, "type": e["type"], "type_label": TYPE_NAME[e["type"]], "links": links,
                    "noticed": not e.get("from_followup")})
    return out


def us_rows(frm: date, to: date) -> list[dict]:
    from . import results
    out = []
    for r in results.between("US", frm, to):
        links = []
        o = r.get("out") or {}
        if str(o.get("url") or "").startswith("https://"):
            links.append({"kind": "release", "label": LINK_NAME["release"], "url": o["url"], "filed": o.get("at")})
        out.append({"id": f"{r['symbol']}|{r['date']}|results", "region": "US", "symbol": r["symbol"], "name": r.get("name") or r["symbol"],
                    "date": r["date"], "until": None, "dates": None, "time": None, "tz": "ET" if r.get("when") else None,
                    "session": r.get("when"), "type": "results", "type_label": TYPE_NAME["results"], "links": links, "noticed": True})
    return out


TEASER_LINKS = {"notice", "join"}       # what a plan without the full calendar sees of a call's links (plans.py earnings_calls)


def view(region: str, scope: str = "all", mine: set[str] | None = None, when: str = "upcoming", kind: str = "all", q: str = "",
         today: date | None = None, limit: int = MAX_ROWS, full: bool = True) -> dict:
    """The calendar's rows: `when` "upcoming" (today to UPCOMING_DAYS ahead, soonest first) or "past" (the last PAST_DAYS,
    latest first, with what was filed after); `kind` "call", "meet" or "all"; `mine` the person's stocks (scope "mine").
    Without `full` (a plan without the full calendar): this week's rows only (to Sunday), each with its notice and webcast
    or dial-in link, and none of what was filed after a call."""
    region = "US" if region == "US" else "IN"
    today = today or datetime.now(ZoneInfo("America/New_York") if region == "US" else IST).date()
    past = when == "past" and full
    frm, to = (today - timedelta(days=PAST_DAYS), today - timedelta(days=1)) if past else (today, today + timedelta(days=UPCOMING_DAYS))
    if not full:
        to = today + timedelta(days=6 - today.weekday())
        scope, kind, q = "all", "all", ""
    rows = india_rows(frm, to) if region == "IN" else us_rows(frm, to)
    for r in rows:
        if not full:
            r["links"] = [x for x in r["links"] if x["kind"] in TEASER_LINKS]
        if r["until"] and not past and r["date"] < today.isoformat():
            r["date"] = next((d for d in r.get("dates") or [] if d >= today.isoformat()), r["until"])     # a run of meetings under way
        r["mine"] = bool(mine) and r["symbol"] in mine
    counts = {"call": sum(r["type"] == "call" for r in rows), "meet": sum(r["type"] == "meet" for r in rows), "results": sum(r["type"] == "results" for r in rows)}
    if scope == "mine":
        rows = [r for r in rows if r["mine"]]
    if kind in ("call", "meet") and region == "IN":
        rows = [r for r in rows if r["type"] == kind]
    words = [w for w in re.findall(r"[a-z0-9&]+", (q or "").lower())][:5]
    if words:
        rows = [r for r in rows if all(w in f"{r['symbol']} {r['name']}".lower() for w in words)]
    rows.sort(key=lambda r: (r["date"], r["time"] or "99", r["name"]), reverse=False)
    if past:
        rows.sort(key=lambda r: r["date"], reverse=True)
    st = load() if region == "IN" else {}
    from . import results
    at = st.get("at") if region == "IN" else results.load("US").get("at")
    return {"region": region, "scope": "mine" if scope == "mine" else "all", "when": "past" if past else "upcoming", "kind": kind,
            "today": today.isoformat(), "from": frm.isoformat(), "to": to.isoformat(), "updated_at": at, "matching": len(rows),
            "rows": rows[:limit], "more": max(0, len(rows) - limit), "counts": counts, "note": NOTE[region],
            "pending": region == "IN" and not st.get("through"), "full": full}


def calendar_dates(uid: str, days: int, frm: date | None = None) -> list[dict]:
    """The money calendar's hook (money_calendar.HOOKS): the calls and meetings of the person's holdings and watchlist,
    for the list and the private feed. [{date, title, detail, kind, id, url}]."""
    from . import money_calendar
    from .plans import allows, plan_of
    try:
        if not allows(plan_of(db.cached_profile(uid)), "earnings_calls"):     # the feed's calls are part of the full calendar
            return []
    except Exception:
        return []
    held, watch = money_calendar.tracked(uid)
    want = set(held) | {s for r, s in watch if r == "IN"}
    if not want:
        return []
    today = datetime.now(IST).date()
    frm = frm or today
    to = today + timedelta(days=max(1, min(days, KEEP_AHEAD)))
    out = []
    for r in india_rows(frm, to):      # US results days are already the money calendar's own (holdings_events)
        if r["symbol"] not in want:
            continue
        when = f" at {r['time']}{' ' + r['tz'] if r['tz'] else ''}" if r["time"] else ""
        first = next((x["url"] for x in r["links"] if x["kind"] == "join"), None) or next((x["url"] for x in r["links"] if x["kind"] == "notice"), None)
        out.append({"date": r["date"], "title": f"{r['symbol']}: {r['type_label'].lower()}{when}", "kind": f"concall_{r['type']}",
                    "id": r["id"], "detail": f"{r['name']}: {r['type_label'].lower()}{when}, as its filing with the exchange says."
                    + (f" Link from the filing: {first}" if first else ""), "url": f"/research/IN/{r['symbol']}"})
    return out
