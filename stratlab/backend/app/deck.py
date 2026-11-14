"""A company deck from the deep dive, and a theme's deck from the theme deep dive, as PowerPoint or PDF: every figure from the
view passed in, each slide saying where it came from. Built from what the page already has; no extra AI.

Each slide is described once (a title, a takeaway line and positioned blocks: text, stat tiles, cards, flowing notes, tables,
charts) and drawn twice: by python-pptx for PowerPoint and by reportlab for PDF, so the two files show the same slides. The
look is the app's own (DECK, 5 Nov: "this is shite can you make it better; all the decks we are giving are not so good
looking"): the paper and ink colours of frontend/src/styles.css, its serif headings (Fraunces) over a sans body (IBM Plex
Sans), and the green and red candles of the StratLab mark (frontend/src/lib/brand.ts). Text is measured with the PDF fonts
(wider than PowerPoint's Calibri and Georgia), so what fits in the PDF fits in PowerPoint too; every text box is cut to its
box with an ellipsis, never left to overflow."""
import functools
import io
import os
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from .checklist import counts_line
from .deepdive import money, scale_for

# ---------- the look: the app's tokens (frontend/src/styles.css :root, the light theme; the dark theme for cover and section slides) ----------
PAPER, PAPER2, CARD, INK, INK2, MUTED = "F5F1E8", "EFE9DC", "FFFDF8", "1D1B17", "2E2B25", "5C574D"
LINE, LINE2, CHIP = "E2DAC8", "D8CFBA", "ECE6D8"
BLUE, ORANGE, UP, DOWN = "1F4FB5", "B4500F", "0F7452", "B23B3B"
BLUE_SOFT, UP_SOFT, DOWN_SOFT = "E4EAF7", "DDF1E8", "F6E0DE"
DARK, DARK2, DARK_LINE, ON_DARK, DARK_MUTED = "141311", "1F1D1A", "34312A", "EFE9DC", "B3AC9C"
WHITE = "FFFFFF"
# the mark (lib/brand.ts MARK and MARK_COLORS; unit/export.test.mjs keeps the two in step): the gradients' middle stops as flat fills
MARK_BOX = (254, 174, 156, 382)
MARK_PATHS = {
    "ribbon": "M266,308C268,322 300,338 330,352C370,372 400,392 404,418C408,432 394,448 390,460C390,440 360,416 320,396C285,378 262,362 257,343C254,330 258,316 266,308Z",
    "green": "M345,252C310,268 266,290 266,308C268,322 300,338 330,352C370,372 400,392 404,418V234Q404,230 400,230H361Q357,230 357,234V348L345,342Z",
    "red": "M257,343C262,362 285,378 320,396C362,416 391,436 390,460C390,480 350,510 316,530V405L306,399V453Q306,457 302,457H261Q257,457 257,453Z",
}
MARK_WICKS = {"greenWick": (381, 177, 10, 56), "redWick": (277, 455, 11, 98)}
MARK_FILL = {"ribbon": "FFFFFF", "greenWick": "12C48A", "green": "0C8A5C", "redWick": "FF444B", "red": "E6333C"}
GREEN_WICK = MARK_FILL["greenWick"]

W_IN, H_IN = 13.333, 7.5
M = 0.6                                   # side margin, inches
TOP, BOT = 1.8, 6.85                      # where a content slide's blocks start and end (the header above, the footer below)
CW = W_IN - 2 * M
DISCLAIMER = "Reported figures and the company's own words. Not investment advice."
STATE = {"pass": ("Meets threshold", UP), "watch": ("Between thresholds", MUTED), "fail": ("Outside threshold", DOWN), "na": ("No data", MUTED),
         "met": ("Met", UP), "missed": ("Missed", DOWN), "pending": ("Not due yet", MUTED), "unchecked": ("Can't check", MUTED)}
BODY_MIN = 11                             # no body text below 11 pt in the PDF (DECK: "slides mostly dense small tables", 7 pt text)

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_fonts_ready = False
_cover: dict = {}


def _fonts():
    """The PDF fonts, registered once. Body, Body-Bold and Head are DejaVu (every script, the rupee sign), as the other PDFs (the brief, the
    tax and ITR exports) use them; the decks draw in the app's Fraunces and IBM Plex Sans (Deck*), falling back to DejaVu for text those
    don't cover. Headings are measured with DejaVu Serif, wider than both Fraunces and PowerPoint's Georgia."""
    global _fonts_ready
    if _fonts_ready:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for name, f in (("Body", "DejaVuSans.ttf"), ("Body-Bold", "DejaVuSans-Bold.ttf"), ("Head", "DejaVuSerif.ttf"),
                    ("Deck", "IBMPlexSans-Regular.ttf"), ("Deck-Bold", "IBMPlexSans-SemiBold.ttf"), ("DeckHead", "Fraunces-SemiBold.ttf")):
        pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, f)))
        _cover[name] = set(pdfmetrics.getFont(name).face.charToGlyph)
    _fonts_ready = True


def _face(text: str, bold: bool = False, head: bool = False) -> str:
    """The font a line is drawn in: the app's, or DejaVu when the line has a character the app's font lacks."""
    _fonts()
    name = "DeckHead" if head else "Deck-Bold" if bold else "Deck"
    if all(ord(ch) in _cover[name] for ch in str(text)):
        return name
    return "Head" if head else "Body-Bold" if bold else "Body"


@functools.lru_cache(maxsize=200_000)
def _measure(text: str, size: float, bold: bool, head: bool) -> float:
    from reportlab.pdfbase import pdfmetrics
    _fonts()
    return pdfmetrics.stringWidth(text, "Head" if head else _face(text, bold), size) / 72


def _width(text: str, size: float, bold: bool = False, head: bool = False) -> float:
    """Width in inches of one line of text (headings in the widest serif, so a fitted heading fits in either file). Kept once measured
    (R35): a deck is laid out several times over (its pages, its tables' pages, the layout check), on the same words."""
    return _measure(str(text), size, bool(bold), bool(head))


def wrap(text: str, size: float, width: float, bold: bool = False, head: bool = False) -> list[str]:
    """Lines of at most `width`; a word wider than the line (a long link, a long name) is broken, never left sticking out."""
    lines, cur = [], ""
    for w in str(text).split():
        while _width(w, size, bold, head) > width and len(w) > 1:
            k = len(w) - 1
            while k > 1 and _width(w[:k], size, bold, head) > width:
                k -= 1
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:k])
            w = w[k:]
        nxt = f"{cur} {w}".strip()
        if cur and _width(nxt, size, bold, head) > width:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines or [""]


def _lh(size: float) -> float:
    return size * 1.25 / 72


def fit(paras: list[str], width: float, height: float, size: float, floor: float, bold=False, gap=0.35, head=False) -> float:
    """The largest size, from `size` down to `floor`, at which the paragraphs fit the box (line height 1.25)."""
    s = size
    while s > floor:
        lines = sum(len(wrap(p, s, width, bold, head)) for p in paras)
        if lines * _lh(s) + (len(paras) - 1) * gap * s / 72 <= height:
            return s
        s -= 0.5
    return floor


def fit_paras(paras: list[str], size: float, width: float, height: float, bold=False, head=False, gap=0.35, lines: int | None = None) -> list[str]:
    """The paragraphs cut to what the box holds at this size: whole lines, the last one ending in an ellipsis when cut. Both files draw
    this, so neither overflows its box."""
    out, used, count, room = [], 0.0, 0, height + 0.02

    def ending(text: str, n: int) -> str:            # the text cut to `n` lines with an ellipsis that still fits in them
        # R34 (GPT review of R31.9: summary-page qualifications ending "…one kind of…"): the whole sentences that fit, when one does
        kept = ""
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", str(text).strip()):
            nxt = f"{kept} {part}".strip()
            if len(wrap(nxt, size, width, bold, head)) > n:
                break
            kept = nxt
        if kept and kept[-1:] in ".!?":
            return kept
        got = wrap(text, size, width, bold, head)[:n]
        last = got[-1]
        while last and _width(last + "…", size, bold, head) > width:
            last = last[:last.rfind(" ")] if " " in last else last[:-1]
        # R40: never on a joining word ("Online retailers / and…"), while a word is left on its line
        cut = " ".join(got[:-1] + [last])
        return (_no_joiner(cut) or cut).rstrip(",;:. ") + "…"

    for k, p in enumerate(paras):
        got = wrap(p, size, width, bold, head)
        keep = 0
        for _ in got:
            need = _lh(size) + (gap * size / 72 if k and not keep else 0)
            if used + need > room or (lines is not None and count >= lines):
                break
            keep, used, count = keep + 1, used + need, count + 1
        if keep < len(got):
            if keep:
                out.append(ending(p, keep))
            elif out:
                out[-1] = ending(out[-1], len(wrap(out[-1], size, width, bold, head)))
            break
        out.append(p)
    return out


def sentences(text: str, limit: int) -> str:
    """Whole sentences up to `limit` characters: never stops mid-sentence."""
    text = re.sub(r"\[\d+\]", "", re.sub(r"\s+", " ", text or "")).strip()
    cut = text[:limit]
    if len(text) <= limit and text[-1:] in ".!?":
        return text
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if len(text) <= limit:                   # short: drop only a trailing half-sentence ("…East and Africa. It is")
        return text[:end + 1] if end > 0 else text
    if end > 0:                              # R35: the whole sentences that fit, however few (never a second one cut to "…monoclonal…")
        return cut[:end + 1]
    more = re.search(r"[.!?](?=\s|$)", text[limit:int(limit * 1.5)])
    if more:                                 # one sentence a little over the limit is said whole
        return text[:limit + more.end()]
    return _no_joiner(cut[:cut.rfind(" ")] if " " in cut else cut) + "…"


_CLAUSE_END = re.compile(r"[,;:](?=\s)|\s[–—-](?=\s)|\s(?=\()|(?<=\))(?=\s)")
_CLAUSE_LEAD = re.compile(r"\s(?:and|or|which|that|who|where|while|including|such as|as well as|along with|with|through|across|for)\s", re.I)


def whole_clause(text: str, limit: int) -> str:
    """A description for a table cell (m2, live R32 decks: "…(technical grade and formulations)…", "…aero-engines, avionics…"): the whole
    sentences that fit `limit` characters, as sentences() keeps them; where the first sentence alone is longer, its whole clauses that
    fit, the trailing clause dropped at the last comma, semicolon, colon, dash, bracket or joining word ("and", "including", "which"),
    with no ellipsis and no bracket left open."""
    got = sentences(text, limit)
    if not got.endswith("…"):
        return got
    text = re.sub(r"\[\d+\]", "", re.sub(r"\s+", " ", text or "")).strip()
    cut = text[:limit + 1]

    def closed(t: str) -> str:
        t = _no_joiner(t)
        while t.count("(") > t.count(")"):               # a bracket the cut left open goes with the clause it opened
            t = _no_joiner(t[:t.rfind("(")])
        return t.rstrip(" ,;:-–—(")
    least = max(24, int(limit * 0.4))
    for at in sorted({m.start() for rx in (_CLAUSE_END, _CLAUSE_LEAD) for m in rx.finditer(cut)}, reverse=True):
        kept = closed(text[:at])                         # the latest place a clause ends, or a new one is joined on
        if re.match(r"\s*(?:and|or)\s", text[at:], re.I) and re.search(r"\s(?:and|or|&)\s+[A-Za-z-]+$", kept):
            kept = closed(re.sub(r"\s(?:and|or|&)\s+[A-Za-z-]+$", "", kept))      # "…properties and Management [and Hospitality…]": the pair goes together
        if len(kept) >= least:
            return kept
    return closed(got[:-1])


_JOINER = re.compile(r"[\s,;:(–-]+(?:and|or|of|the|a|an|for|in|to|with|by|on|at|from|its|their|&)$", re.I)


def _no_joiner(text: str) -> str:
    """A cut text never ends on a joining word ("Pharma and…", "listed as…" stays; "of the…" doesn't): the words before it."""
    text = text.rstrip(" ,;:-–(")
    while _JOINER.search(text):
        text = _JOINER.sub("", text).rstrip(" ,;:-–(")
    return text


def clip(text: str, size: float, width: float, lines: int, bold=False, head=False) -> str:
    """At most `lines` lines of text at this size and width, ending in an ellipsis when cut."""
    got = wrap(text, size, width, bold, head)
    if len(got) <= lines:
        return str(text)
    # R34 (GPT review of R31.5: descriptions ending mid-thought): the whole sentences that fit, when at least one does; an ellipsis only then
    parts, kept = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", str(text).strip()), ""
    for p in parts:
        nxt = f"{kept} {p}".strip()
        if len(wrap(nxt, size, width, bold, head)) > lines:
            break
        kept = nxt
    if kept and kept[-1:] in ".!?":
        return kept
    return (fit_paras([str(text)], size, width, lines * _lh(size), bold, head) or [""])[0]


def _cr(v) -> str:
    if v is None:
        return "–"
    digits = f"{abs(v):.0f}"          # Indian grouping: 12,34,567
    if len(digits) > 3:
        last3, rest = digits[-3:], digits[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        digits = ",".join(parts + [last3])
    return (MINUS if v < 0 and digits.strip("0,") else "") + digits      # a tiny loss rounds to 0, never "-0"; the real minus (LIVE7A-014)


# a spreadsheet number format for Indian grouping: 1,23,45,678 from a crore, 1,23,456 from a lakh (DD-053)
INDIAN_FORMAT = "[>=10000000]##\\,##\\,##\\,##0;[>=100000]##\\,##\\,##0;##,##0"


def _plain(x, k: int, dp: int) -> str:
    """A figure divided by `k` to `dp` decimals with Western grouping; one that rounds to zero never prints as "-0"."""
    if x is None:
        return "–"
    text = f"{x / k:,.{dp}f}"
    return text.lstrip("-") if float(text.replace(",", "")) == 0 else text.replace("-", MINUS)


def cap_inr(cr: float) -> str:
    """A market value in crore as the company page writes it ("₹16.1 lakh cr", "₹4,512 cr"): DD-053's cover tile said
    "₹16.10 lakh cr" and wrapped, beside "₹16.1" on the page."""
    from .intel.grounding import crore_text
    return crore_text(cr)


MINUS = "−"                                 # one minus sign in every figure (the real one), never a hyphen beside it


def _pc(v, signed=False) -> str:
    """12.3%, −4.0% (signed: +12.3%); a figure that rounds to zero has no sign."""
    if v is None:
        return "–"
    text = f"{abs(v):.1f}"
    neg = v < 0 and float(text) != 0
    return f"{MINUS if neg else '+' if signed and float(text) != 0 else ''}{text}%"


def _pcw(v, whole: bool) -> str:
    """An EBITDA margin as precise as it is filed: whole points print as 13%, never 13.0% (the owner, 7 Nov: false precision); a median of
    two whole points keeps its half (16.5%)."""
    if v is None or not whole:
        return _pc(v)
    return _pc(v).replace(".0%", "%")


def _chg(v) -> str:
    """A change as the theme page writes it: +12.3%, −4.0% (the real minus); one that rounds to zero is 0.0%."""
    return _pc(v, signed=True)


def _times(v, dp: int = 1) -> str:
    """2.4x, −0.35x; a multiple that rounds to zero has no sign ("0.00x", never "−0.00x" or "-0.00x")."""
    if v is None:
        return "–"
    text = f"{abs(v):.{dp}f}"
    return f"{MINUS if v < 0 and float(text) != 0 else ''}{text}x"


def _pts(v) -> str:
    """A change in points, the sign from the rounded figure: a change that rounds to zero is "0.0 pts", never "+0.0" or "−0.0"."""
    if v is None:
        return "–"
    text = f"{abs(v):.1f}"
    return f"{'' if float(text) == 0 else '+' if v > 0 else MINUS}{text} pts"


def _med(s, f=lambda v: _pc(v)) -> str:
    return f(s["median"]) if s else "–"


def _span(s, f=lambda v: _pc(v)) -> str:            # LIVE7A-014: the real minus ("-14.1% to 23.6%" beside "−11% to 25%")
    if not s:
        return "–"
    if s["min"] == s["max"]:
        return f(s["min"])
    lo, hi = f(s["min"]), f(s["max"])
    # d1 (the live R41 decks: "Range −3.6% to 36%"): both ends of a range at one precision; a whole end beside a decimal one gets its ".0"
    dec = lambda t: re.search(r"\d\.\d", t)      # noqa: E731
    if bool(dec(lo)) != bool(dec(hi)):
        lo, hi = (re.sub(r"(\d)(%|x)$", r"\1.0\2", t) if not dec(t) else t for t in (lo, hi))
    return f"{lo} to {hi}"


def _day(iso) -> str:
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return str(iso or "–")


def _month(iso) -> str:
    """A quarter or month as people write it ("Sep 2026"), from "2026-09-30" or "2026-09"; anything else as it is."""
    m = re.match(r"^(\d{4})-(\d{2})", str(iso or ""))
    if not m or not 1 <= int(m.group(2)) <= 12:
        return str(iso or "–")
    return f"{date(2000, int(m.group(2)), 1).strftime('%b')} {m.group(1)}"


def _numeric(s) -> bool:
    """A figure cell, or one of the states that stand in a figure's place (R27, metric_registry: "–", "n/a", "n.c."), so its column aligns right."""
    return isinstance(s, str) and bool(re.match(r"^[+\-–−₹$]?\s?[\d.,]+", s.strip())) or s in ("–", "n/a", "n.c.")


def _short_link(url: str) -> str:
    try:
        u = urlparse(url)
        name = u.path.rstrip("/").split("/")[-1]
        return f"{(u.hostname or '').replace('www.', '')}/…/{name[:22]}" if name else (u.hostname or url)
    except ValueError:
        return url[:50]


def _n(k: int, one: str, many: str | None = None) -> str:
    return f"{k:,} {one if k == 1 else (many or one + 's')}"


# ---------- the slides, described once ----------
class Slide:
    """`kind`: "cover" (dark, the deck's first), "section" (dark, a part's opening: its number, its one line and what it holds) or
    "content". `subtitle` is the slide's takeaway: the one thing it shows, under the title."""

    def __init__(self, title: str, subtitle: str | None = None, dark: bool = False, eyebrow: str | None = None, kind: str | None = None):
        self.title, self.subtitle, self.dark, self.blocks = title, subtitle, dark, []
        self.kind = kind or ("cover" if dark else "content")
        self.eyebrow = eyebrow
        self.part, self.contents = "", []       # a section slide's number and [(title, page)]

    def add(self, kind: str, box: tuple, **kw):
        self.blocks.append({"kind": kind, "box": box, **kw})
        return self


IST = timezone(timedelta(hours=5, minutes=30))


def plan(v: dict, now: datetime | None = None) -> tuple[list[Slide], str]:
    """The deck's slides for one deep-dive view, and the footer line (dated in IST, as the page is: after 5:30 AM IST the UTC
    date is a day behind, R20-016)."""
    name, sym = v["name"], v["symbol"]
    n = v["numbers"]
    years = [y for y in n["years"] if y.get("sales") is not None]
    us = v.get("region") == "US" or (n.get("unit") or "").startswith("$")
    unit = n.get("unit") or ("$ million" if us else "₹ crore")      # a foreign filer's own currency: "CAD million"
    bank = bool(n.get("bank"))
    today = (now or datetime.now(timezone.utc)).astimezone(IST).strftime("%d %b %Y")
    footer = f"{name} ({sym}) · Deep dive · {today}"
    month = date(2000, int(n.get("fye") or 3), 1).strftime("%B")
    amt = lambda x: "–" if x is None else money(x, unit)  # noqa: E731
    eb = lambda part: f"{name} · {part}"  # noqa: E731

    def fig_for(values):                     # each chart and table picks its unit, exact to within 1% (see scale_for)
        k, label, dp = scale_for(values, us, unit)
        if k == 1 and not us:
            return k, label, _cr
        return k, label, (lambda x: _plain(x, k, dp))

    snap = v.get("snapshot") or {}
    vv = v.get("valuation") or {}
    group = ((v.get("checklist") or {}).get("industry") or {}).get("group")
    if vv.get("short"):
        val = (vv["short"], "–" if vv.get("value") is None else f"{vv['value']:.1f}×")
    elif group in ("lender", "insurer", "holding"):
        val = ("P/B", "–" if snap.get("pb") is None else f"{snap['pb']:.1f}")
    else:
        val = ("P/E", "–" if snap.get("pe") is None else f"{snap['pe']:.1f}")
    ret = ("ROE", _pc(snap.get("roe"))) if bank else ("ROCE", _pc(snap.get("roce")))
    lev = (("Dividend yield", _pc(snap.get("div_yield"))) if bank
           else ("Debt / equity", "–" if snap.get("debt_equity") is None else f"{snap['debt_equity']:.2f}"))
    cap = snap.get("market_cap_cr")              # the market value is in dollars whatever the filings' currency
    tiles = [("Market cap", ("Unavailable" if snap.get("cap_note") else "–") if cap is None else money(cap, "$ million") if us else cap_inr(cap)), val, ret, lev,
             ("Sales growth, 3y", _pc(n["growth"].get("sales_cagr_3y"), True)),
             ("Profit growth, 3y", _pc(n["growth"].get("profit_cagr_3y"), True))]
    slides: list[Slide] = []

    # 1. title
    s = Slide(name, f"{'US' if us else 'NSE'}: {sym} · Company deep dive", dark=True)
    # the cover's description is the company page's first paragraph (`cover`, DD-053), else the deep dive's profile
    s.add("text", (M, 2.75, 9.4, 2.15), paras=[sentences(v.get("cover") or v.get("about") or "", 430)], size=16, floor=12, color=ON_DARK)
    s.add("stats", (M, 5.15, CW, 1.25), items=tiles, dark=True)
    s.add("text", (M, 6.62, CW, 0.3), paras=[f"Prepared {today} with StratLab. {DISCLAIMER}"], size=10, floor=10, color=DARK_MUTED)
    slides.append(s)

    # 2. at a glance
    cl = v.get("checklist") or {}
    card = v.get("card") or {}
    s = Slide("At a glance", "The numbers that frame everything after this slide", eyebrow=eb("At a glance"))
    s.add("stats", (M, 1.75, CW, 1.25), items=tiles)
    left = []
    if cl.get("counts"):
        c = cl["counts"]
        left.append(("Investor checklist", f"{c.get('pass', 0)} of {sum(c.values())} meet the threshold",      # the big figure short, the full count below
                     [counts_line(c)] + [f"Outside: {x['label']}" for x in cl.get("checks", []) if x["state"] == "fail"][:3]))
    if card.get("rows"):
        checked = card["met"] + card["missed"]
        left.append(("Management report card", f"{card['met']} of {checked} targets met" if checked else "Nothing to settle yet",
                     [f"{card.get('unchecked', 0)} targets can't be checked from the numbers"] if card.get("unchecked") else []))
    why = vv.get("why") or "Most businesses are compared on price to earnings."
    left.append((f"How it's valued: {val[0]}", val[1], [sentences(why, 230)]))
    s.add("cards", (M, 3.3, CW, 3.45), items=[{"title": t, "value": x, "lines": ls} for t, x, ls in left], cols=len(left), fill=True, size=16)
    slides.append(s)

    # 3. sales and profit
    if years:
        # sales and profit side by side, each on its own scale: on one axis a profit a tenth of sales was a row of slivers
        # (DD-053); Indian figures grouped the Indian way, as the tables are
        sales_name = "Revenue" if bank else "Sales"
        ks, word_s, _ = fig_for([y["sales"] for y in years])
        kp, word_p, _ = fig_for([y["profit"] for y in years if y["profit"] is not None])
        g = n["growth"]
        msg = (f"{sales_name} grew {_pc(g.get('sales_cagr_3y'), True)} a year over three years, net profit {_pc(g.get('profit_cagr_3y'), True)}"
               if g.get("sales_cagr_3y") is not None and g.get("profit_cagr_3y") is not None else "Each on its own scale")
        s = Slide(f"{sales_name} and net profit", f"{msg}; financial years ending {month}", eyebrow=eb("Numbers"))
        cats = [y["year"].replace("Mar ", "FY") for y in years]
        s.add("columns", (M, 1.75, 4.3, 5.05), cats=cats, inr=not us,
              series=[(f"{sales_name} ({word_s})", [y["sales"] / ks for y in years], BLUE)])
        s.add("columns", (M + 4.5, 1.75, 4.3, 5.05), cats=cats, inr=not us,
              series=[(f"Net profit ({word_p})", [None if y["profit"] is None else y["profit"] / kp for y in years], ORANGE)])
        s.add("stack", (9.75, 1.85, W_IN - M - 9.75, 4.9), items=[
            ("Sales growth a year, 3 years", _pc(g.get("sales_cagr_3y"), True)), ("Sales growth a year, 5 years", _pc(g.get("sales_cagr_5y"), True)),
            ("Profit growth a year, 3 years", _pc(g.get("profit_cagr_3y"), True)), ("Profit growth a year, 5 years", _pc(g.get("profit_cagr_5y"), True))])
        slides.append(s)

    # 4. the last eight quarters
    q = n.get("quarters") or []
    if q:
        _, word, figq = fig_for([x for r in q[-8:] for x in (r["sales"], r["profit"])])
        down = sum(1 for r in q[-8:] if (r.get("sales_yoy") or 0) < 0)
        s = Slide("The last eight quarters", f"Sales and profit in {word}; growth on the same quarter a year before"
                  + (f"; sales were below a year before in {_n(down, 'quarter')}" if down else ""), eyebrow=eb("Numbers"))
        rows = [[r["quarter"], figq(r["sales"]), _pc(r["sales_yoy"], True), _pc(r["opm"]), figq(r["profit"])] for r in q[-8:]]
        tint = {(i, 2): DOWN for i, r in enumerate(q[-8:]) if (r.get("sales_yoy") or 0) < 0}
        s.add("table", (M, 1.75, CW, 5.0), head=["Quarter", "Revenue" if bank else "Sales", "vs a year ago",
                                                 "Financing margin" if bank else "EBITDA margin", "Net profit"],     # before depreciation (DD-052)
              rows=rows, widths=[2, 2, 1.6, 1.8, 2], colors=tint)
        slides.append(s)

    # 5. capex and cash (not for lenders: capex and free cash flow don't describe a bank)
    if years and not bank:
        recent = list(reversed(years))[:8]
        _, word, figc = fig_for([x for y in recent for x in (y["sales"], y["capex"], y["cfo"], y["fcf"], y["debt"])])
        s = Slide("Capex and cash", ("Capex as reported in the cash flow statement" if n.get("capex_reported") else
                                     "Capex estimated from the balance sheet: the rise in fixed assets and work in progress, plus depreciation")
                  + f". {word}.", eyebrow=eb("Numbers"))
        rows = [[y["year"], figc(y["sales"]), figc(y["capex"]), _pc(y["capex_pct_sales"]), figc(y["cfo"]), figc(y["fcf"]), figc(y["debt"])]
                for y in recent]
        tint = {(i, 5): DOWN for i, y in enumerate(recent) if (y.get("fcf") or 0) < 0}
        s.add("table", (M, 1.75, CW, 5.0), head=["Year", "Sales", "Capex", "Capex / sales", "Cash from operations",
                                                 "Free cash flow", "Debt"], rows=rows, widths=[1.4, 1.6, 1.6, 1.4, 2, 1.8, 1.6], colors=tint)
        slides.append(s)

    reads = v.get("reads") or {}
    b, p = reads.get("business"), reads.get("plans")
    # 6. business model
    if b:
        s = Slide("Business model", "From the company's investor presentation and annual report", eyebrow=eb("The business"))
        segs = [x for x in b.get("segments") or [] if x.get("share_pct") is not None]
        tw = 6.6 if segs else CW
        s.add("text", (M, 1.75, tw, 2.1), paras=[sentences(b.get("summary") or "", 600)], size=16, floor=12)
        if segs:
            s.add("hbars", (7.6, 1.7, W_IN - M - 7.6, 2.2), cats=[x["name"] for x in segs[:6]], vals=[x["share_pct"] for x in segs[:6]],
                  title="Share of revenue, %", fmt="pct0")
        cols = [("Customers", [b["customers"]] if b.get("customers") else []), ("What drives revenue", b.get("drivers", [])[:4]),
                ("Risks it names", b.get("risks", [])[:4])]
        s.add("cards", (M, 4.1, CW, 2.7), items=[{"title": t, "lines": ls} for t, ls in cols if ls], cols=3, bullets=True, fill=True, size=15)
        slides.append(s)

    # 7. the industry's own operating measures
    ms = (b or {}).get("measures") or []
    if ms:
        s = Slide(f"{b.get('industry') or 'Operating'} measures", "As the company states them, with the period and the change", eyebrow=eb("The business"))
        s.add("cards", (M, 1.75, CW, 5.0), cols=3, items=[
            {"title": m["name"], "value": m["value"],
             "lines": [" · ".join(x for x in (m.get("period"), m.get("change")) if x)]
             + ([f"{m['source']['title'][:40]}, {m['source']['at'][:10]}"] if m.get("source") else [])} for m in ms[:6]])
        slides.append(s)

    # 8. capex and growth plans
    if p and (p.get("capex") or p.get("outlook")):
        s = Slide("Capex and growth plans", "In management's own words, from the presentations and calls", eyebrow=eb("The business"))
        items = [{"title": c["what"], "value": " · ".join(x for x in (c.get("amount"), c.get("size")) if x) or None,
                  "pill": (c["status"], UP if c["status"] in ("done", "under way") else MUTED),
                  "lines": [x for x in (c.get("timeline") and f"When: {c['timeline']}",
                                        c.get("source") and f"{c['source']['title'][:40]}, {c['source']['at'][:10]}") if x]}
                 for c in (p.get("capex") or [])[:6]]
        items += [{"title": "Outlook", "lines": [f"“{(o.get('quote') or o['statement'])}”"]} for o in (p.get("outlook") or [])[:6 - len(items)]]
        s.add("cards", (M, 1.75, CW, 5.0), items=items, cols=3 if len(items) > 4 else 2, fill=len(items) <= 3, size=16)
        slides.append(s)

    # 9. management report card
    if card.get("rows"):
        checked = card["met"] + card["missed"]
        s = Slide("Management report card", (f"{card['met']} of {checked} targets that the numbers can settle were met" if checked
                                             else "What management said on past calls, and whether the numbers can settle it"), eyebrow=eb("Management"))
        s.add("stats", (M, 1.75, CW, 1.05), items=[("Met", str(card["met"])), ("Missed", str(card["missed"])),
                                                  ("Not due yet", str(card.get("pending", 0))), ("Can't check", str(card.get("unchecked", 0)))])
        rows, tint = [], {}
        for i, r in enumerate(card["rows"][:8]):
            fmt = amt if r["metric"] == "capex" else (lambda x: f"{x:g}%")
            tgt = "–" if r["low"] is None else fmt(r["low"]) + (f"–{fmt(r['high'])}" if r.get("high") is not None else "")
            label, color = STATE[r["result"]]
            rows.append([r["what"], r.get("period") or "–", tgt, "–" if r["actual"] is None else fmt(r["actual"]), label, r["said_at"][:10]])
            tint[(i, 4)] = color
        s.add("table", (M, 3.0, CW, 3.8), head=["What they said", "For", "Target", "Actual", "Result", "Said on"],
              rows=rows, widths=[5, 1, 1.5, 1.4, 1.4, 1.5], colors=tint)
        slides.append(s)

    # 10. investor checklist: every row, over as many slides as it takes (table_pages never drops one)
    if cl.get("checks"):
        c = cl["counts"]
        ind = (cl.get("industry") or {}).get("label")
        checks = cl["checks"]
        head, widths = ["Area", "Check", "Value", "Result"], [1.6, 4.2, 3.6, 1.2]
        rows = [[x["group"], x["label"], x["value"], STATE[x["state"]][0]] for x in checks]
        pages = table_pages(head, rows, widths, CW, 5.05, most=16)
        base = 0
        for pg, chunk in enumerate(pages):
            s = Slide("Investor checklist" + (f" ({pg + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      counts_line(c) + (f" · rules for: {ind}" if ind and ind != "General" else ""), eyebrow=eb("Investor checklist"))
            tint = {(i, 3): STATE[checks[base + i]["state"]][1] for i in range(len(chunk))}
            s.add("table", (M, 1.75, CW, 5.05), head=head, rows=chunk, widths=widths, colors=tint, numeric=[False, False, False, False])
            base += len(chunk)
            slides.append(s)

    # 11. say what's missing, so a deck without document reads isn't mistaken for a complete one
    if not b or not card.get("rows"):
        missing = []
        if not b:
            missing.append("The business model, the industry's own measures and the capex plans: press Read the documents.")
        if not card.get("rows"):
            missing.append("The management report card: press Check past calls.")
        s = Slide("Not in this deck yet", "These come from the company's own presentations and calls, not read yet for this company", eyebrow=eb("Still to read"))
        s.add("cards", (M, 1.85, CW, 2.4), items=[{"title": "Still to read", "lines": missing}], cols=1, bullets=True)
        s.add("text", (M, 4.5, CW, 0.6), paras=["Press those buttons on the company's deep dive page, then download the deck again."],
              size=15, floor=12, color=MUTED)
        slides.append(s)

    # 12. sources
    docs = v.get("documents") or []
    s = Slide("Sources", "Numbers: the company's reported annual and quarterly results. "
              + ("Filings: the company's reports to the SEC (10-K, 10-Q and 8-K)." if us else "Filings, presentations and call transcripts: the exchange (NSE)."),
              eyebrow=eb("Sources"))
    if docs:
        s.add("table", (M, 1.75, CW, 4.45), head=["Filed", "Document", "Link"],
              rows=[[x["at"][:10], x["title"], {"text": _short_link(x["url"]), "url": x["url"]}] for x in docs[:9]],
              widths=[1.3, 6.2, 4.6], numeric=[False, False, False])
    s.add("text", (M, 6.35, CW, 0.45), paras=[DISCLAIMER + " The AI reads can miss or misread things: check the source "
                                              "document before relying on a point."], size=12, floor=11, color=MUTED)
    slides.append(s)
    return slides, footer


# ---------- layout shared by both files ----------
def card_height(it: dict, cw: float, bullets: bool = False, size: float = 13) -> float:
    """How tall a card must be to show its title, value and lines at their full size."""
    iw = cw - 0.5
    tw = iw - (1.3 if it.get("pill") else 0)
    hh = 0.22 + 0.3 * len(wrap(clip(it["title"], 13, tw, 2, True), 13, tw, True)) + 0.12
    if it.get("value"):
        hh += len(wrap(it["value"], 22, iw, head=True)) * _lh(22) + 0.12
    lines = [("• " if bullets else "") + str(x) for x in it.get("lines") or [] if x]
    if lines:
        hh += sum(len(wrap(t, size, iw)) for t in lines) * _lh(size) + (len(lines) - 1) * 0.35 * size / 72
    if it.get("note"):
        hh += 0.12 + len(wrap(it["note"], BODY_MIN, iw)) * _lh(BODY_MIN)
    return hh + 0.28


def card_boxes(b: dict) -> list[tuple]:
    """(x, y, w, h) of each card: rows only as tall as their fullest card needs, within the block's box."""
    x, y, w, h = b["box"]
    items, gap = b["items"], 0.25
    if not items:
        return []
    cols = max(1, min(b.get("cols", 3), len(items)))
    rows = (len(items) + cols - 1) // cols
    cw, room = (w - gap * (cols - 1)) / cols, (h - gap * (rows - 1)) / rows
    out, yy = [], y
    for r in range(rows):
        row = items[r * cols:(r + 1) * cols]
        rh = min(room, max(max(card_height(it, cw, b.get("bullets")) for it in row), 1.0))
        if b.get("fill"):
            rh = room
        for i in range(len(row)):
            out.append((x + i * (cw + gap), yy, cw, rh))
        yy += rh + gap
    return out


def whole_lines(items: list[dict], box: tuple, cols: int, bullets: bool = False) -> list[dict]:
    """Cards whose lines all show in full at the smallest body size (R21: a findings card cut mid-sentence with an ellipsis): while a card
    doesn't fit its share of the box, its last line gives way, a whole sentence at a time."""
    items = [dict(it, lines=list(it.get("lines") or [])) for it in items]
    if not items:
        return items
    x, y, w, h = box
    cols = max(1, min(cols, len(items)))
    rows = (len(items) + cols - 1) // cols
    cw, room = (w - 0.25 * (cols - 1)) / cols, (h - 0.25 * (rows - 1)) / rows
    for it in items:
        while len(it["lines"]) > 1 and card_height(it, cw, bullets, BODY_MIN) > room:
            it["lines"].pop()
        # n1 (the outside review of the live R33 decks: three findings cards of one sentence still ended "…"): a card's one line that still
        # doesn't fit loses whole parts from its end (a sentence, a "; " clause, a part after ", " or " and "), never part of a word
        while it["lines"] and card_height(it, cw, bullets, BODY_MIN) > room:
            got = _shorter(it["lines"][-1])
            if not got:
                break
            it["lines"][-1] = got
    return items


def fit_chars(text: str, size: float, width: float) -> str:
    """One line no wider than `width`: characters dropped from the end, with an ellipsis."""
    if _width(text, size) <= width:
        return text
    full = text
    while text and _width(text + "…", size) > width:
        text = text[:-1]
    # R34 (GPT review of R31.5: "Semiconductor equipm…", "Defence syst…"): cut at the last whole word when one fits, never mid-word
    if text and len(text) < len(full) and full[len(text)].isalnum() and " " in text.strip():
        text = text[:text.rstrip().rfind(" ")]
        # never end on a joining word ("Pharma and…"): drop it while a word is left before it
        while re.search(r"\s(?:and|or|of|the|for|in|to|with|&)\s*$", text, re.I) and " " in text.strip():
            text = re.sub(r"\s+\S+\s*$", "", text)
    return text.rstrip(" ,;:-–(") + "…"


# R35 (the owner's review of the R31.11 decks: "Component…", "Tyre…", "Mahindra & Mahindra…" down every table and chart): a name that
# doesn't fit is said shorter, whole, before any of it is cut. Generic: no list of names, only the words every such name can lose.
# R38: and the legal endings of companies listed outside India and the US ("NXP Semiconductors N.V.", "Siemens AG", "Banco Santander, S.A."),
# in capitals only, so no English word is taken for one
_LEGAL_TAIL = re.compile(r"[\s,]+(?:ltd|limited|inc|incorporated|corp|corporation|co|company|plc|llc|"
                         r"(?-i:N\.?V|S\.?A|S\.?E|A\.?G|S\.?p\.?A|GmbH|B\.?V|AB|ASA|Oyj|KGaA|Tbk|Bhd|L\.?P))\.?$", re.I)
_KIND_TAIL = re.compile(r"\s+(?:makers?|manufacturers?|companies|providers?|producers?|suppliers?|operators?|businesses|firms|players)$", re.I)
_CORP_TAIL = re.compile(r"\s+(?:international|industries|enterprises|holdings|group|india)$", re.I)
_PAREN = re.compile(r"\s*\((?!\D*\d)[^()]*\)")
_LABEL_LIKE = re.compile(r"[^\W\d_][\w&'’.,()/+·:\- ]*$")


def label_forms(text: str, deep: bool = True) -> list[str]:
    """A label and its shorter ways of saying the same thing, longest first: "and" as "&", a company's legal ending left off ("Ltd",
    "Company Limited"), the kind of business left off a layer's name ("makers", "companies", "providers"), and (`deep`) a bracketed
    aside with no figure in it, then a name's last general word ("International", "Industries"). A figure, a sentence or a link has no shorter form."""
    text = str(text).strip()
    out = [text]
    if not _LABEL_LIKE.match(text) or len(text.split()) > 9 or re.search(r"[.!?] |\d[%x]|https?:", text):
        return out

    def add(t):
        t = t.strip(" ,;:-–&")
        if t and t != out[-1] and re.search(r"[^\W\d_]{2}", t):
            out.append(t)
    add(re.sub(r"\s+and\s+", " & ", out[-1]))
    t = out[-1]
    while _LEGAL_TAIL.search(t) and len(t.split()) > 1:
        t = _LEGAL_TAIL.sub("", t)
    add(t)
    if len(out[-1].split()) > 1:
        add(_KIND_TAIL.sub("", out[-1]))
    if deep:
        add(_PAREN.sub("", out[-1]))
        add(re.sub(r"^The\s+", "", out[-1]))
        t = _CORP_TAIL.sub("", out[-1])
        if len(t.split()) > 1 and t == _no_joiner(t):          # "Northfield Motherson International": the name without the last general word
            add(t)
    return out


def _distinct(given: list, short: list) -> list:
    """The shortened labels, with any two different names that came out the same given back in full (two layers are never one name)."""
    names = {}
    for g, t in zip(given, short):
        names.setdefault(t, set()).add(g)
    return [g if len(names[t]) > 1 else t for g, t in zip(given, short)]


def _holds(text: str, size: float, width: float, lines: int, bold: bool = False) -> bool:
    """Whether the text shows whole in this many lines of this width: every word on a line, none broken."""
    return all(_width(w, size, bold) <= width for w in text.split()) and len(wrap(text, size, width, bold)) <= lines


def short_label(text: str, size: float, width: float, lines: int = 1, bold: bool = False, tight: bool = False) -> str:
    """A label that fits `lines` lines of `width`, whole: as given when it fits, else its first shorter form that does (label_forms).
    `tight` (a one-line table row): a shorter form on one line before the name on two. Only a label no form of which fits is cut, at a
    whole word, with an ellipsis (the publication gate lists it)."""
    text = str(text)
    if _width(text, size, bold) <= width:
        return text
    if tight:
        for n in range(1, lines + 1):
            for t in label_forms(text, deep=n == lines):
                if _holds(t, size, width, n, bold):
                    return t
    else:
        for t in label_forms(text):
            if _holds(t, size, width, lines, bold):
                return t
    t = label_forms(text)[-1]
    rows, cur = [], ""
    for w in t.split():
        nxt = f"{cur} {w}".strip()
        if _width(nxt, size, bold) <= width:
            cur = nxt
        elif cur and len(rows) < lines - 1 and _width(w, size, bold) <= width:
            rows, cur = rows + [cur], w
        else:
            break
    else:
        return t
    rows = rows + [cur] if cur else rows
    while rows and _width(rows[-1] + "…", size, bold) > width:        # room for the ellipsis: whole words give way, never part of one
        rows[-1] = rows[-1][:rows[-1].rfind(" ")] if " " in rows[-1] else ""
        rows = [r for r in rows if r]
    kept = _no_joiner(" ".join(rows))
    if not kept:                               # one word wider than the line: nothing whole to keep
        kept = t.split()[0]
        while len(kept) > 1 and _width(kept + "…", size, bold) > width:
            kept = kept[:-1]
    return kept + "…"


def _fit_columns(b: dict, widths: list[float], size: float = BODY_MIN) -> list[float]:
    """A one-line table's column widths, with the room a column doesn't use given to the columns whose cells don't fit on one line (R35:
    "Component…" beside a half-empty figure column): first to short cells (a figure, a date), then to names. The total is unchanged."""
    pad = 0.22
    strong = set(b.get("strong") or ())
    hard, full = [], []
    for c, (hd, w) in enumerate(zip(b["head"], widths)):
        one = _width(str(hd), size, True) + pad
        need = one if one <= w + 1e-6 else max((_width(x, size, True) for x in str(hd).split()), default=0) + pad
        short = long_ = need
        for i, r in enumerate(b["rows"]):
            if isinstance(r, dict) or c >= len(r):
                continue
            t = _cell_text(r[c])
            cw = _width(t, size, i in strong) + pad
            long_ = max(long_, cw)
            if len(t) <= 16:
                short = max(short, cw)
        hard.append(short)
        full.append(long_)
    out = list(widths)
    for need in (hard, full):
        want = [max(0.0, n - w) for n, w in zip(need, out)]
        spare = [max(0.0, w - f) for w, f in zip(out, full)]
        tw, ts = sum(want), sum(spare)
        if tw <= 1e-6 or ts <= 1e-6:
            continue
        k = min(1.0, ts / tw)
        out = [w + a * k - sp * (tw * k / ts) for w, a, sp in zip(out, want, spare)]
    return out


ROW_MAX = 0.7                     # a table stretches its rows up to this to fill its box, so a short table doesn't sit in a half-empty slide


def _whole_words(b: dict, widths: list[float], numeric: list[bool]) -> list[float]:
    """Column widths widened so no header word is broken inside (the owner, 7 Nov: "Compani / es", "EV/EBITD / A") and a figure stays on one
    line ("₹3.04 lakh / cr"), taking the room from the columns with the most to spare; as given when the table is too narrow for that."""
    pad = 0.24
    need = []
    for c, (hd, w) in enumerate(zip(b["head"], widths)):
        n = max((_width(x, 13, True) for x in str(hd).split()), default=0) + pad
        cells = [r[c] for r in b["rows"] if not isinstance(r, dict)]
        # a figure, a short cell ("Mar 2026") and a link's text (fit_chars would cut it to "01 Oct 20…") stay on one line
        n = max([n] + [_width(_cell_text(x), 13) + pad + (0.06 if isinstance(x, dict) else 0) for x in cells
                       if isinstance(x, dict) or (numeric[c] and len(_cell_text(x)) <= 16) or len(_cell_text(x)) <= 9])
        # R38 (the live R36 Semiconductors deck: "Texas Instrument / s Inc"): no word of a cell is broken inside either, a link's or a
        # code's long run of characters aside
        n = max([n] + [_width(x, 13) + pad for v in cells if not isinstance(v, dict) for x in _cell_text(v).split() if len(x) <= 20])
        need.append(n)
    out = list(widths)
    for _ in range(len(out)):
        short = [c for c in range(len(out)) if out[c] < need[c] - 1e-6]
        if not short:
            break
        c = short[0]
        give = sorted(range(len(out)), key=lambda k: -(out[k] - need[k]))
        want = need[c] - out[c]
        for k in give:
            spare = out[k] - max(need[k], 0.6)
            if k == c or spare <= 0:
                continue
            take = min(spare, want)
            out[k] -= take
            out[c] += take
            want -= take
            if want <= 1e-6:
                break
        if want > 1e-6:
            need[c] = out[c]                  # as wide as the table allows; the other columns still get theirs
    return out


def _cell_text(v) -> str:
    return v["text"] if isinstance(v, dict) and "text" in v else ("" if v is None else str(v))


_COUNTED = re.compile(r"\S \(\d[\d,]*(?: of \d[\d,]*)?\)$")


def counted_cell(text: str) -> bool:
    """Whether a cell is a figure with its count in brackets ("74 days (59 of 90)", "19.5% (4)"): a median row's cell, never cut (R35, GPT
    reviews of R31.5-R31.9: Retail's sector table read "74 days (59…")."""
    return bool(_COUNTED.search(str(text or "")))


def _room_for_counts(b: dict, widths: list[float]) -> list[float]:
    """A compact table's column widths with room where the other columns can give it: for each figure-with-its-count on one line, and for
    the whole text of the columns the table names in `full` (the appendix's layer names). A column with a counted cell is given up to a
    quarter of each other column's width, and never so much that a cell of theirs that fits now would be cut; a `full` column is given
    only room the others don't use (at most 60% of it, so the figures keep their air). What still doesn't fit wraps onto a second line (a
    counted cell) or is cut with an ellipsis (a name: short_names says it in full)."""
    cols = range(len(widths))
    plain = [r for r in b["rows"] if not isinstance(r, dict)]
    own = [max([_width(str(b["head"][c]), BODY_MIN, True)] + [_width(_cell_text(r[c]), BODY_MIN) for r in plain]) + 0.22 for c in cols]
    counted = [max([0.0] + [_width(_cell_text(r[c]), BODY_MIN, True) + 0.22 for r in plain if counted_cell(_cell_text(r[c]))]) for c in cols]
    full = set(b.get("full") or ())
    out = list(widths)
    for need, givers in (({c: counted[c] for c in cols if counted[c]}, "quarter"), ({c: own[c] for c in full if c < len(widths)}, "slack")):
        short = {c: need[c] - out[c] for c in need if need[c] > out[c] + 1e-6}
        if not short:
            continue
        spare = {}
        for c in cols:
            if counted[c] or c in full:
                continue
            slack = out[c] - own[c]
            spare[c] = max(0.0, slack) * 0.6 if givers == "slack" else (out[c] * 0.25 if slack < 0 else min(out[c] * 0.25, slack))
        have, want = sum(spare.values()), sum(short.values())
        if have <= 1e-6:
            continue
        for c, x in short.items():
            out[c] += x * min(1.0, have / want)
        for c, x in spare.items():
            out[c] -= x * min(1.0, want / have)
    return out


def _two_line_width(text: str, size: float, bold: bool = False) -> float:
    """The narrowest column in which a text shows whole on two lines, no word broken (one line when it is one word)."""
    words = str(text).split()
    best = _width(" ".join(words), size, bold)
    for k in range(1, len(words)):
        best = min(best, max(_width(" ".join(words[:k]), size, bold), _width(" ".join(words[k:]), size, bold)))
    return best


def _keep_whole(b: dict, widths: list[float], size: float = BODY_MIN) -> list[float]:
    """A compact table's column widths with no column under what its cells need to show whole (m2, live R32 Semiconductors: a sector
    table's last page read "indie…" under "Compa/ny" and a median "+35…", its name and period columns given away to the counted cells):
    a header's widest word; a figure, a date or another short cell on one line; a figure with its count on two lines ("127 days" over
    "(79 of 95)"); a name in its shortest whole form (label_forms) on two lines. A column under its floor takes the room from the columns
    over theirs. As given when the table is too narrow for every floor."""
    pad = 0.22
    strong = set(b.get("strong") or ())
    floors = []
    for c, hd in enumerate(b["head"]):
        need = max((_width(x, size, True) for x in str(hd).split()), default=0.0)
        for i, r in enumerate(b["rows"]):
            if isinstance(r, dict) or c >= len(r):
                continue
            t = _cell_text(r[c])
            if not t:
                continue
            if counted_cell(t):
                need = max(need, _two_line_width(t, size, True))
            elif len(t) <= 16:
                need = max(need, _width(t, size, i in strong))
            elif not isinstance(r[c], dict):
                need = max(need, min(_two_line_width(f, size, i in strong) for f in label_forms(t)))
        floors.append(need + pad)
    short = {c: floors[c] - x for c, x in enumerate(widths) if floors[c] > x + 1e-6}
    if not short or sum(floors) > sum(widths) + 1e-6:
        return widths
    spare = {c: x - floors[c] for c, x in enumerate(widths) if x > floors[c] + 1e-6}
    want, have = sum(short.values()), sum(spare.values())
    out = list(widths)
    for c, x in short.items():
        out[c] += x
    for c, x in spare.items():
        out[c] -= x * want / have
    return out


def table_layout(b: dict, w: float, h: float) -> dict:
    """Column widths, the font size (13 down to 11 pt, never smaller) and each row's height so the table fits its box; rows that still
    don't fit are left out (callers page their rows with table_pages, so none is). A row {"group": text} is a full-width heading row."""
    total = sum(b["widths"])
    widths = [w * x / total for x in b["widths"]]
    plain = [r for r in b["rows"] if not isinstance(r, dict)]
    numeric = b.get("numeric") or [all(_numeric(r[c]) or r[c] == "" for r in plain if not isinstance(r[c], dict)) for c in range(len(b["head"]))]
    strong = set(b.get("strong") or ())
    colors = b.get("colors") or {}

    widths = _whole_words(b, widths, numeric)
    compact = bool(b.get("compact"))
    if compact:
        # a reference table (R20: the appendix ran 8 rows a page): every cell on one line at the smallest body size and rows only as tall
        # as their line. R35: no cell is cut to "Component…": a column takes the room its neighbours don't use, a name that still doesn't
        # fit is said shorter (short_label), and one that can't be takes a second line. A figure with its count in brackets (a median
        # row's cell) is never cut either: its column is widened where the others have room, and it wraps where they don't
        widths = _keep_whole(b, _room_for_counts(b, _fit_columns(b, widths)))       # m2: and no column under what its cells need whole
        st = set(b.get("strong") or ())
        given = b["rows"]

        def one(v, cw, i):
            t = _cell_text(v)
            if counted_cell(t):
                return v if isinstance(v, dict) else t
            return {**v, "text": fit_chars(t, BODY_MIN, cw - 0.2)} if isinstance(v, dict) else short_label(t, BODY_MIN, cw - 0.2, 2, i in st, tight=True)
        rows = [r if isinstance(r, dict) else [one(v, cw, i) for v, cw in zip(r, widths)] for i, r in enumerate(given)]
        plain_ = [i for i, r in enumerate(given) if not isinstance(r, dict)]
        for c in range(len(b["head"])):               # two different names never read the same once shortened
            col = [i for i in plain_ if c < len(given[i]) and not isinstance(given[i][c], dict) and not counted_cell(_cell_text(given[i][c]))]
            for i, t in zip(col, _distinct([_cell_text(given[i][c]) for i in col], [rows[i][c] for i in col])):
                rows[i][c] = t
        b = {**b, "rows": rows}
    pad, floor_h = (0.022, 0.22) if compact else (0.12, 0.32)

    def heights_at(size):
        line = size * 1.3 / 72
        hs = [max(len(wrap(hd, size, cw - 0.2, True)) for hd, cw in zip(b["head"], widths)) * line + pad + 0.02]
        for i, r in enumerate(b["rows"]):
            if isinstance(r, dict):
                hs.append(len(wrap(r["group"], size, w - 0.2, True)) * line + pad + 0.04)
            else:
                # a compact table's counted cell is measured bold (a median row is drawn bold, and its page was chosen without `strong`).
                # R40 (live Consumer retail deck: "Online retailers / and…"): a coloured cell (the highest and lowest layer) is drawn bold
                # too, so it is measured bold: measured plain, its row had a line too few and the name was cut
                hs.append(max(len(wrap(_cell_text(v), size, cw - 0.2, i in strong or (i, c) in colors or (compact and counted_cell(_cell_text(v)))))
                              for c, (v, cw) in enumerate(zip(r, widths))) * line + pad)
        return [max(floor_h, x) for x in hs]

    def lines_at(size):
        return [round((x - pad) / (size * 1.3 / 72)) for x in heights_at(size)[1:]]

    base = lines_at(BODY_MIN)
    for size in ((BODY_MIN,) if compact else (13, 12, 11)):
        if size > BODY_MIN and any(a > b_ for a, b_ in zip(lines_at(size), base)):
            continue                                   # a bigger size that wraps a cell 11 pt keeps on one line reads worse, not better
        heights = heights_at(size)
        if sum(heights) <= h:
            spare = h - sum(heights)
            if spare > 0 and len(heights) > 1 and not b.get("tight"):     # fill the box: short rows grow, up to ROW_MAX
                add = spare / len(heights)
                heights = [x + min(add, max(0.0, ROW_MAX - x)) for x in heights]
            return {"widths": widths, "size": size, "heights": heights, "rows": b["rows"], "numeric": numeric}
    keep, used = [], heights[0]
    for r, hh in zip(b["rows"], heights[1:]):
        if used + hh > h:
            break
        keep.append(r)
        used += hh
    return {"widths": widths, "size": BODY_MIN, "heights": heights[:len(keep) + 1], "rows": keep, "numeric": numeric}


def table_height(head: list, rows: list, widths: list, w: float) -> float:
    """How tall a table of these rows is at its natural size (no rows stretched)."""
    return sum(table_layout({"head": head, "rows": rows, "widths": widths, "tight": True}, w, 99)["heights"])


def table_pages(head: list, rows: list, widths: list, w: float, h: float, most: int = 14, first: tuple | None = None, strong=(), compact: bool = False) -> list[list]:
    """`rows` cut into pages a table of `head` shows in full in a w x h box (the first page in `first`, (w, h), when it is smaller): as
    many rows a page as fit (at most `most`), so no row is ever left off a slide. A page that starts inside a group repeats the group's
    heading, "(continued)"; a page never ends on a heading."""
    pages, i, group = [], 0, None
    while i < len(rows):
        pw, ph = first if (first and not pages) else (w, h)
        lead = [{"group": f"{group} (continued)"}] if group and not isinstance(rows[i], dict) else []
        n = min(most, len(rows) - i)
        while n > 1 and len(table_layout({"head": head, "rows": lead + rows[i:i + n], "widths": widths, "numeric": [False] * len(head), "strong": strong,
                                          "compact": compact}, pw, ph)["rows"]) < n + len(lead):
            n -= 1
        while n > 1 and isinstance(rows[i + n - 1], dict):
            n -= 1
        chunk = rows[i:i + n]
        for r in chunk:
            if isinstance(r, dict):
                group = r["group"]
        pages.append(lead + chunk)
        i += n
    even = -(-len(rows) // len(pages)) if pages else most
    # evening out only when it asks for fewer rows a page than this pass did: tall rows can make the evened pages end short again, and
    # asking for the same number again never ended (R15: a theme's PDF ran 5 minutes into a RecursionError and never downloaded)
    if len(pages) > 1 and most > 2 and even < most and len(pages[-1]) < max(3, len(pages[-2]) // 2):
        again = table_pages(head, rows, widths, w, h, even, first, strong, compact)
        if len(again) == len(pages):
            return again
    return pages


FLOW_TEXT, FLOW_SUB, FLOW_PAD, FLOW_SEP = 12, BODY_MIN, 0.24, 0.28
CONTENTS_MAX = 20                 # a section slide lists up to this many slides of its part (at 11 pt when it is that many)


def _flow_item_h(it: dict, w: float) -> float:
    hh = 0.32 if it.get("tags") else 0
    hh += len(wrap(it["text"], FLOW_TEXT, w)) * _lh(FLOW_TEXT)
    if it.get("sub"):
        hh += 0.07 + len(wrap(it["sub"], FLOW_SUB, w)) * _lh(FLOW_SUB)
    return hh


def flow_layout(b: dict) -> list[tuple]:
    """Items flowing down columns, then across: [(item, x, y, w, h)] for those that fit the box (each column a card)."""
    x, y, w, h = b["box"]
    cols, gap = b.get("cols", 2), 0.3
    cw = (w - gap * (cols - 1)) / cols
    iw = cw - 2 * FLOW_PAD
    out, c, yy = [], 0, y + FLOW_PAD
    for it in b["items"]:
        ih = _flow_item_h(it, iw)
        if yy + ih > y + h - FLOW_PAD and yy > y + FLOW_PAD:
            c, yy = c + 1, y + FLOW_PAD
        if c >= cols:
            break
        out.append((it, x + c * (cw + gap) + FLOW_PAD, yy, iw, ih))
        yy += ih + FLOW_SEP
    return out


def flow_pages(items: list, box: tuple, cols: int = 2) -> list[list]:
    pages, i = [], 0
    while i < len(items):
        k = max(1, len(flow_layout({"box": box, "cols": cols, "items": items[i:]})))
        pages.append(items[i:i + k])
        i += k
    return pages


def _mark_polys() -> list[tuple[str, list[tuple[float, float]]]]:
    """The mark's shapes as polygons in its own units: curves flattened to short lines, which either file can fill."""
    out = []

    def path(d):
        toks = re.findall(r"[MCVHQLZ]|-?\d+(?:\.\d+)?", d)
        pts, i, cur, cmd = [], 0, (0.0, 0.0), None
        while i < len(toks):
            if toks[i].isalpha():
                cmd = toks[i]
                i += 1
                if cmd == "Z":
                    continue
            num = lambda k: float(toks[i + k])  # noqa: E731
            if cmd in ("M", "L"):
                cur = (num(0), num(1))
                pts.append(cur)
                i += 2
            elif cmd == "H":
                cur = (num(0), cur[1])
                pts.append(cur)
                i += 1
            elif cmd == "V":
                cur = (cur[0], num(0))
                pts.append(cur)
                i += 1
            elif cmd == "C":
                p0, p1, p2, p3 = cur, (num(0), num(1)), (num(2), num(3)), (num(4), num(5))
                for k in range(1, 13):
                    t = k / 12
                    pts.append(tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * bq + 3 * (1 - t) * t * t * cq + t ** 3 * dq
                                     for a, bq, cq, dq in zip(p0, p1, p2, p3)))
                cur = p3
                i += 6
            elif cmd == "Q":
                p0, p1, p2 = cur, (num(0), num(1)), (num(2), num(3))
                for k in range(1, 5):
                    t = k / 4
                    pts.append(tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * bq + t * t * cq for a, bq, cq in zip(p0, p1, p2)))
                cur = p2
                i += 4
            else:
                i += 1
        return pts

    for key in ("ribbon", "greenWick", "green", "redWick", "red"):
        if key in MARK_WICKS:
            x, y, w, h = MARK_WICKS[key]
            out.append((MARK_FILL[key], [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
        else:
            out.append((MARK_FILL[key], path(MARK_PATHS[key])))
    return out


# ---------- drawing: the blocks, once, over a few primitives each file implements ----------
def title_size(sl) -> float:
    """A slide's title size. R35: a title too long for its line at the usual size is set smaller (a cover's on two lines), never cut
    ("Utilities (Indian power, gas and water-linked…")."""
    if sl.kind == "cover":
        size = fit([sl.title], CW - 1.0, 0.75, 42, 28, head=True)
        return size if len(wrap(sl.title, size, CW - 1.0, head=True)) <= 1 else fit([sl.title], CW - 1.0, 0.8, 27, 18, head=True)
    if sl.kind == "section":
        return fit([sl.title], 5.7, 1.32, 38, 22, head=True)
    size = fit([sl.title], CW - 0.6, 0.55, 28, 22, head=True)
    return size if len(wrap(sl.title, size, CW - 0.6, head=True)) <= 1 else fit([sl.title], CW - 0.6, 0.6, 21, 16, head=True)     # smaller, then two lines


def headline_size(text: str) -> float:
    """A headline's size under its title: 14 pt on two lines, smaller when that is what shows it whole (three lines at 11 pt)."""
    return fit([text], CW, 0.58, 14, BODY_MIN)


def chart_title(title: str, w: float) -> tuple[float, int]:
    """(size, lines) for a chart's title: one line at 12 pt, else at 11, else two lines."""
    for size in (12, BODY_MIN):
        if _width(title, size, True) <= w:
            return size, 1
    return BODY_MIN, 2


def hbar_labels(cats: list, w: float, h: float) -> tuple[float, list[list[str]], float]:
    """A bar chart's label column, each bar's name in lines, and their size: the column as wide as the longest name up to 45% of the
    chart, a name on as many lines as a bar's share of the height holds (two, three for tall bars), said shorter before any of it is cut
    and set at 10 pt when that is what shows it whole (R35: "Life Insurance Corporation Of…")."""
    slot = max(h - 0.1, 0.2) / max(1, len(cats))
    for size in (BODY_MIN, 10):
        lines = 3 if slot >= 3 * _lh(size) else 2 if slot >= 0.3 else 1
        lw = min(w * 0.45, max([_width(str(c), size) for c in cats] or [0.5]) + 0.15)
        short = _distinct([str(c) for c in cats], [short_label(str(c), size, lw - 0.12, lines) for c in cats])
        got = [wrap(t, size, lw - 0.12) for t in short]
        if not any(ls[-1].endswith("…") and not str(c).endswith("…") for ls, c in zip(got, cats)):
            break
    return lw, got, size


def drawn_lines(b: dict) -> dict:
    """A line chart with only the series that have a line to draw: two points or more (R35: a layer's margins by year with no net margin
    on file stopped the PDF being made at all: "Polyline must have 2 or more points")."""
    return {**b, "series": [x for x in b["series"] if sum(1 for y in x[1] if y is not None) >= 2]}


def column_labels(cats: list, w: float, size: float) -> tuple[list[list[str]], float]:
    """A column chart's names under their columns, each in lines no wider than its column's share of the plot: two lines at most, at a
    smaller size (10 pt) when that shows more of them whole."""
    slot = max(0.3, w / max(1, len(cats)) - 0.08)
    for fs in dict.fromkeys((size, 10)):
        short = _distinct([str(c) for c in cats], [short_label(str(c), fs, slot, 2) for c in cats])
        got = [wrap(t, fs, slot) for t in short]
        if not any(ls[-1].endswith("…") and not str(c).endswith("…") for ls, c in zip(got, cats)):
            break
    return got, fs


class Canvas:
    """The slide frame and every block but charts, drawn with rect, text, line and poly (each file implements those)."""

    # primitives: rect(x, y, w, h, fill, line=None, radius=0.08), text(...), line(x1, y1, x2, y2, color, width), poly(points, fill)

    def clip(self, text, size, width, lines, bold=False, head=False):
        """Text cut to its lines (the module's clip); a method so the layout check hears of every cut (Probe)."""
        return clip(text, size, width, lines, bold, head)

    def label(self, text, size, width, lines=1, bold=False):
        """A label in its lines: said shorter before any of it is cut (short_label)."""
        return short_label(text, size, width, lines, bold)

    def _title_box(self, b):
        """A chart's title above it, and the box left for the chart. R35: a title too long for one line is set smaller, then on two
        lines ("Revenue against the same quarter a year before, the 14 largest…")."""
        x, y, w, h = b["box"]
        if not b.get("title"):
            return x, y, w, h
        size, lines = chart_title(b["title"], w)
        self.text(x, y, w, 0.3 + (lines - 1) * _lh(size), [self.clip(b["title"], size, w, lines, bold=True)], size, color=INK2, bold=True)
        drop = 0.36 + (lines - 1) * _lh(size)
        return x, y + drop, w, h - drop

    def b_table(self, b, lay=None):
        x, y, w, h = b["box"]
        lay = lay or table_layout(b, w, h)
        rows = [b["head"]] + lay["rows"]
        strong = set(b.get("strong") or ())
        colors = b.get("colors") or {}
        self.rect(x - 0.05, y - 0.05, w + 0.1, sum(lay["heights"]) + 0.1, CARD, line=LINE, radius=0.06)
        yy, k, size = y, -1, lay["size"]
        for r, (vals, hh) in enumerate(zip(rows, lay["heights"])):
            group = isinstance(vals, dict)
            if r > 0:
                k += 1
            if group:
                self.rect(x, yy, w, hh, PAPER2, radius=0)
                n = len(wrap(vals["group"], size, w - 0.2, True))
                self.text(x + 0.1, yy + (hh - n * _lh(size)) / 2, w - 0.2, hh, [vals["group"]], size, color=INK, bold=True)
            else:
                cx = x
                for c, (v, cw) in enumerate(zip(vals, lay["widths"])):
                    link = v if isinstance(v, dict) and v.get("url") else None
                    text = fit_chars(_cell_text(v), size, cw - 0.25) if link else _cell_text(v)
                    color = MUTED if r == 0 else colors.get((k, c), BLUE if link else INK)
                    bold = r == 0 or k in strong or (r > 0 and (k, c) in colors)
                    n = len(wrap(text, size, cw - 0.2, bold))
                    top = yy + (hh - n * _lh(size)) / 2
                    self.text(cx + 0.1, top, cw - 0.2, hh, [text], size, color=color, bold=bold,
                              align="right" if lay["numeric"][c] and c > 0 else "left", url=link["url"] if link else None)
                    cx += cw
            if r > 0 and k in strong:
                self.line(x, yy, x + w, yy, LINE2, 1)
            if r < len(rows) - 1:
                self.line(x, yy + hh, x + w, yy + hh, LINE2 if r == 0 else LINE, 1 if r == 0 else 0.6)
            yy += hh

    def mark(self, x, y, h):
        bx, by, bw, bh = MARK_BOX
        k = h / bh
        for fill, pts in _mark_polys():
            self.poly([(x + (px - bx) * k, y + (py - by) * k) for px, py in pts], fill)

    def frame(self, sl: Slide, n: int, total: int, footer: str):
        dark = sl.kind in ("cover", "section")
        self.page(DARK if dark else PAPER)
        if sl.kind == "cover":
            size = title_size(sl)
            self.text(M, 1.72, CW - 1.0, 0.8, [self.clip(sl.title, size, CW - 1.0, 2 if size < 28 else 1, head=True)], size, color=ON_DARK, head=True, name="Title")
            self.text(M, 1.36, CW, 0.3, [(sl.subtitle or "").upper()], 12, color=GREEN_WICK, bold=True)
            self.mark(M, 0.5, 0.62)
            self.text(M + 0.38, 0.62, 3, 0.4, ["StratLab"], 19, color=ON_DARK, head=True)
            return
        if sl.kind == "section":
            size = title_size(sl)
            self.text(M, 2.6, 5.7, 1.3, [self.clip(sl.title, size, 5.7, int(1.33 / _lh(size)), head=True)], size, color=ON_DARK, head=True, name="Title")
            self.text(M, 1.25, 3, 1.2, [sl.part], 66, color=GREEN_WICK, head=True)
            if sl.subtitle:
                size = fit([sl.subtitle], 5.5, 2.4, 17, 13)
                self.text(M, 4.05, 5.5, 2.4, [sl.subtitle], size, color=DARK_MUTED)
            self._contents(sl)
            self._footer(footer, n, total, dark=True)
            return
        size = title_size(sl)
        self.text(M, 0.5, CW - 0.6, 0.6, [self.clip(sl.title, size, CW - 0.6, max(1, int(0.62 / _lh(size))), head=True)], size, color=INK, head=True, name="Title")
        if sl.subtitle:
            two = len(wrap(sl.title, size, CW - 0.6, head=True)) > 1          # under a title on two lines, the headline starts a little lower
            size = headline_size(sl.subtitle)
            self.text(M, 1.16 if two else 1.08, CW, 0.56, [self.clip(sl.subtitle, size, CW, int(0.58 / _lh(size)))], size, color=INK2)
        if sl.eyebrow:
            self.text(M, 0.3, CW - 0.6, 0.22, [self.clip(sl.eyebrow.upper(), 10, CW - 0.6, 1, bold=True)], 10, color=MUTED, bold=True)
        self.mark(W_IN - M - 0.17, 0.32, 0.44)
        self._footer(footer, n, total, dark=False)

    def _footer(self, footer, n, total, dark):
        self.line(M, 7.0, W_IN - M, 7.0, DARK_LINE if dark else LINE2, 0.75)
        col = DARK_MUTED if dark else MUTED
        self.text(M, 7.08, 8.4, 0.24, [self.clip(f"StratLab · {footer}", 9.5, 8.4, 1)], 9.5, color=col)
        self.text(W_IN - M - 4, 7.08, 4, 0.24, [f"Not investment advice · {n} / {total}"], 9.5, color=col, align="right")

    def _contents(self, sl):
        x, w = 7.0, W_IN - M - 7.0
        self.text(x, 1.3, w, 0.26, ["IN THIS PART"], 11, color=DARK_MUTED, bold=True)
        rows = sl.contents[:CONTENTS_MAX]
        step = min(0.46, 5.2 / max(1, len(rows)))
        fs = 14 if step >= 0.36 else 12 if step >= 0.27 else BODY_MIN
        for i, (title, page) in enumerate(rows):
            yy = 1.72 + i * step
            self.line(x, yy, x + w, yy, DARK_LINE, 0.75)
            # R35 ("…grade and formulations) and…"): a long slide title is set smaller, then on two lines where its row holds them
            ts = next((z for z in (fs, 12, BODY_MIN) if z <= fs and _width(title, z) <= w - 0.7), BODY_MIN)
            lab = self.label(title, ts, w - 0.7, 2 if step >= 2 * _lh(ts) + 0.03 else 1)
            n = len(wrap(lab, ts, w - 0.7))
            self.text(x, yy + (step - n * ts * 1.25 / 72) / 2, w - 0.7, n * ts * 1.3 / 72, [lab], ts, color=ON_DARK)
            self.text(x + w - 0.6, yy + (step - fs * 1.25 / 72) / 2, 0.6, fs * 1.3 / 72, [str(page)], fs, color=DARK_MUTED, align="right")
        if rows:
            self.line(x, 1.72 + len(rows) * step, x + w, 1.72 + len(rows) * step, DARK_LINE, 0.75)

    def draw(self, sl: Slide, n: int, total: int, footer: str):
        self.frame(sl, n, total, footer)
        for b in sl.blocks:
            getattr(self, "b_" + b["kind"])(b)

    # ----- blocks -----
    def b_text(self, b):
        x, y, w, h = b["box"]
        size = fit(b["paras"], w, h, b.get("size", 14), b.get("floor", BODY_MIN), bold=b.get("bold", False), head=b.get("head", False))
        self.text(x, y, w, h, b["paras"], size, color=b.get("color", INK), bold=b.get("bold", False), head=b.get("head", False))

    def b_stats(self, b):
        x, y, w, h = b["box"]
        items, gap, dark = b["items"], 0.18, b.get("dark")
        cw = (w - gap * (len(items) - 1)) / len(items)
        for i, it in enumerate(items):
            label, value, note = it[0], str(it[1]), (it[2] if len(it) > 2 else None)
            cx = x + i * (cw + gap)
            self.rect(cx, y, cw, h, DARK2 if dark else CARD, line=DARK_LINE if dark else LINE)
            iw = cw - 0.36
            lab = self.label(label, BODY_MIN, iw, 2)
            lh = len(wrap(lab, BODY_MIN, iw)) * _lh(BODY_MIN)
            self.text(cx + 0.18, y + 0.13, iw, lh, [lab], BODY_MIN, color=DARK_MUTED if dark else MUTED)
            nh = min(0.6, len(wrap(note, BODY_MIN, iw)) * _lh(BODY_MIN)) if note else 0
            vy = y + 0.13 + lh + 0.06
            # R35 (every live cover: "Their market value" with its note and no figure): the figure always has its line; a long note gives way
            nh = min(nh, max(0.0, y + h - vy - 0.14 - _lh(15)))
            vh = y + h - vy - nh - (0.14 if note else 0.08)
            vs = fit([value], iw, min(vh, 26 * 1.3 / 72), 26, 15, head=True)       # one line where a size from 26 down to 15 allows
            if len(wrap(value, vs, iw, head=True)) > 1:
                vs = fit([value], iw, vh, 26, 13, head=True)
            self.text(cx + 0.18, vy, iw, vh, [value], vs, color=it[3] if len(it) > 3 else (ON_DARK if dark else INK), head=True)
            if note:
                self.text(cx + 0.18, y + h - 0.12 - nh, iw, nh, [note], BODY_MIN, color=DARK_MUTED if dark else MUTED)

    def b_stack(self, b):
        x, y, w, h = b["box"]
        step = h / len(b["items"])
        for i, (label, value) in enumerate(b["items"]):
            yy = y + i * step
            self.line(x, yy, x + w, yy, LINE2, 0.75)
            self.text(x, yy + 0.1, w, 0.3, [self.label(label, 12, w, 1)], 12, color=MUTED)
            self.text(x, yy + 0.42, w, 0.6, [value], 28, color=DOWN if value[:1] in "-−" else INK, head=True)

    def b_cards(self, b):
        for it, (cx, cy, cw, ch) in zip(b["items"], card_boxes(b)):
            self.rect(cx, cy, cw, ch, CARD, line=LINE)
            iw, yy = cw - 0.5, cy + 0.22
            tw = iw - (1.3 if it.get("pill") else 0)
            title = self.label(it["title"], 13, tw, 2, bold=True)
            self.text(cx + 0.25, yy, tw, 0.6, [title], 13, color=INK, bold=True)
            if it.get("pill"):
                label, color = it["pill"]
                self.rect(cx + cw - 1.45, yy - 0.02, 1.2, 0.3, color, radius=0.15)
                self.text(cx + cw - 1.45, yy + 0.02, 1.2, 0.26, [self.clip(label, BODY_MIN, 1.1, 1, bold=True)], BODY_MIN, color=WHITE, bold=True, align="center")
            yy += 0.3 * len(wrap(title, 13, tw, True)) + 0.12
            if it.get("value"):
                vs = fit([it["value"]], iw, 0.75, 22, 14, head=True)
                vp = fit_paras([it["value"]], vs, iw, 0.75, head=True)
                self.text(cx + 0.25, yy, iw, 0.75, [it["value"]], vs, color=it.get("value_color", INK), head=True)
                yy += len(wrap(vp[0] if vp else "", vs, iw, head=True)) * _lh(vs) + 0.12
            note_h = (0.12 + min(3, len(wrap(it["note"], BODY_MIN, iw))) * _lh(BODY_MIN)) if it.get("note") else 0
            lines = [str(x) for x in it.get("lines") or [] if x]
            if lines:
                room = cy + ch - 0.18 - yy - note_h
                paras = [("• " if b.get("bullets") else "") + x for x in lines]
                ls = fit(paras, iw, room, b.get("size", 13), BODY_MIN)
                self.text(cx + 0.25, yy, iw, room, paras, ls, color=INK2)
            if it.get("note"):
                self.text(cx + 0.25, cy + ch - 0.16 - note_h + 0.12, iw, note_h - 0.12, [it["note"]], BODY_MIN, color=MUTED)

    def b_flow(self, b):
        placed = flow_layout(b)
        if not placed:
            return
        x, y, w, h = b["box"]
        cols, gap = b.get("cols", 2), 0.3
        cw = (w - gap * (cols - 1)) / cols
        used = sorted({round((px - FLOW_PAD - x) / (cw + gap)) for _, px, _, _, _ in placed})
        bottom = max(py + ph for _, _, py, _, ph in placed) + FLOW_PAD
        for c in used:
            self.rect(x + c * (cw + gap), y, cw, bottom - y, CARD, line=LINE)
        last = {}
        for it, px, py, pw, ph in placed:
            c = round((px - FLOW_PAD - x) / (cw + gap))
            if c in last:
                self.line(px, py - FLOW_SEP / 2, px + pw, py - FLOW_SEP / 2, LINE, 0.75)
            last[c] = True
            yy = py
            if it.get("tags"):
                tx = px
                for label, fg, bg in it["tags"]:
                    tw = _width(label, BODY_MIN, True) + 0.24
                    self.rect(tx, yy, tw, 0.25, bg, radius=0.12)
                    self.text(tx, yy + 0.015, tw, 0.24, [label], BODY_MIN, color=fg, bold=True, align="center")
                    tx += tw + 0.1
                yy += 0.32
            th = len(wrap(it["text"], FLOW_TEXT, pw)) * _lh(FLOW_TEXT)
            self.text(px, yy, pw, th, [it["text"]], FLOW_TEXT, color=INK)
            yy += th
            if it.get("sub"):
                sh = len(wrap(it["sub"], FLOW_SUB, pw)) * _lh(FLOW_SUB)
                self.text(px, yy + 0.07, pw, sh, [it["sub"]], FLOW_SUB, color=BLUE if it.get("url") else MUTED, url=it.get("url"))


def _fmt(kind: str):
    """(python formatter, spreadsheet number format) for a chart's values."""
    return {"pct": (lambda v: _pc(v), '0.0"%"'), "pct0": (lambda v: f"{v:g}%".replace("-", MINUS), '0"%"'), "pctw": (lambda v: _pcw(v, True), 'General"%"'),
            "chg": (lambda v: f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.1f}%", '+0.0"%";-0.0"%";0.0"%"'),
            "x": (lambda v: f"{v:.1f}x", '0.0"x"'), "num1": (lambda v: f"{v:,.1f}", "#,##0.0"),
            # the theme deck's one formatter (R18): a whole value prints whole (15%, 43x), any other with one decimal; its values come rounded
            # to one decimal, so the spreadsheet's General prints them the same way
            "pct1": (lambda v: whole_figures(_pc(v)), 'General"%"'), "chg1": (lambda v: whole_figures(_chg(v)), '+General"%";-General"%";General"%"'),
            "x1": (lambda v: whole_figures(f"{v:.1f}x"), 'General"x"'), "num1t": (lambda v: whole_figures(f"{v:,.1f}"), "General"),
            # LIVE7A-014: a chart one of whose values has a decimal prints every value with one
            "pctk1": (lambda v: _pc(v), '0.0"%"'), "chgk1": (lambda v: _chg(v), '+0.0"%";-0.0"%";0.0"%"'),
            "xk1": (lambda v: f"{v:.1f}x", '0.0"x"'), "numk1": (lambda v: f"{v:,.1f}", "#,##0.0")}.get(kind, (lambda v: f"{v:,.0f}", "#,##0"))


# ---------- PowerPoint ----------
class PptxRenderer(Canvas):
    def __init__(self):
        from pptx import Presentation
        from pptx.util import Inches
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W_IN), Inches(H_IN)
        self.s = None

    @staticmethod
    def rgb(h):
        from pptx.dml.color import RGBColor
        return RGBColor.from_string(h)

    def page(self, bg):
        self.s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.s.background.fill.solid()
        self.s.background.fill.fore_color.rgb = self.rgb(bg)

    def text(self, x, y, w, h, paras, size, color=INK, bold=False, head=False, align="left", url=None, name=None, gap=0.35):
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Inches, Pt
        tb = self.s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(max(h, 0.1)))
        if name:
            tb.name = name
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        for i, para in enumerate(fit_paras(paras, size, w, h, bold, head, gap) or [""]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = {"right": PP_ALIGN.RIGHT, "center": PP_ALIGN.CENTER}.get(align, PP_ALIGN.LEFT)
            p.space_after = Pt(size * gap)
            r = p.add_run()
            r.text = str(para)
            f = r.font
            f.size, f.bold = Pt(size), bold
            f.name = "Georgia" if head else "Calibri"
            f.color.rgb = self.rgb(color)
            if url:
                r.hyperlink.address = url
        return tb

    def rect(self, x, y, w, h, fill, line=None, radius=0.08):
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Pt
        shp = self.s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        if radius:
            shp.adjustments[0] = min(0.5, radius / max(min(w, h), 0.01))
        shp.fill.solid()
        shp.fill.fore_color.rgb = self.rgb(fill)
        if line:
            shp.line.color.rgb = self.rgb(line)
            shp.line.width = Pt(0.75)
        else:
            shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def line(self, x1, y1, x2, y2, color, width=0.75):
        from pptx.enum.shapes import MSO_CONNECTOR
        from pptx.util import Inches, Pt
        c = self.s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
        c.line.color.rgb = self.rgb(color)
        c.line.width = Pt(width)

    def poly(self, pts, fill):
        from pptx.util import Emu
        e = [(int(px * 914400), int(py * 914400)) for px, py in pts]
        ff = self.s.shapes.build_freeform(e[0][0], e[0][1], scale=1.0)
        ff.add_line_segments(e[1:], close=True)
        shp = ff.convert_to_shape(Emu(0), Emu(0))
        shp.fill.solid()
        shp.fill.fore_color.rgb = self.rgb(fill)
        shp.line.fill.background()
        shp.shadow.inherit = False

    @staticmethod
    def _cell_lines(cell, top=None, bottom=None):
        """A table cell's borders: only the rules given (top, bottom), as the app's tables draw them."""
        from lxml import etree
        from pptx.oxml.ns import qn
        pr = cell._tc.get_or_add_tcPr()
        for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
            for old in pr.findall(qn(tag)):
                pr.remove(old)
        for k, (tag, color) in enumerate((("a:lnL", None), ("a:lnR", None), ("a:lnT", top), ("a:lnB", bottom))):
            ln = etree.Element(qn(tag), w=str(9525 if color else 0))
            if color:
                etree.SubElement(etree.SubElement(ln, qn("a:solidFill")), qn("a:srgbClr"), val=color)
            else:
                etree.SubElement(ln, qn("a:noFill"))
            pr.insert(k, ln)

    def b_table(self, b):
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.oxml.ns import qn
        from pptx.util import Emu, Inches, Pt
        x, y, w, h = b["box"]
        lay = table_layout(b, w, h)
        rows = [b["head"]] + lay["rows"]
        self.rect(x - 0.05, y - 0.05, w + 0.1, sum(lay["heights"]) + 0.1, CARD, line=LINE, radius=0.06)
        shape = self.s.shapes.add_table(len(rows), len(b["head"]), Inches(x), Inches(y), Inches(w), Inches(sum(lay["heights"])))
        t = shape.table
        t._tbl.tblPr.find(qn("a:tableStyleId")).text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"   # no style, no grid
        for i, cw in enumerate(lay["widths"]):
            t.columns[i].width = Emu(int(Inches(cw)))
        for r, hh in enumerate(lay["heights"]):
            t.rows[r].height = Emu(int(Inches(hh)))
        strong = set(b.get("strong") or ())
        colors = b.get("colors") or {}
        k = -1                                      # the index of a plain row among the given rows, as `colors` and `strong` count them
        for r, vals in enumerate(rows):
            group = isinstance(vals, dict)
            if r > 0:
                k += 1
            if group:
                t.cell(r, 0).merge(t.cell(r, len(b["head"]) - 1))
                vals = [vals["group"]] + [""] * (len(b["head"]) - 1)
            for c, v in enumerate(vals):
                cell = t.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = self.rgb(PAPER2 if group else CARD)
                self._cell_lines(cell, top=LINE2 if (r > 0 and k in strong) else None, bottom=LINE2 if r == 0 else LINE)
                cell.margin_left = cell.margin_right = Inches(0.1)
                cell.margin_top = cell.margin_bottom = Inches(0.03)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                if group and c > 0:
                    continue
                p = cell.text_frame.paragraphs[0]
                link = v if isinstance(v, dict) and v.get("url") else None
                run = p.add_run()
                text = _cell_text(v)
                run.text = fit_chars(text, lay["size"], lay["widths"][c] - 0.25) if link else text
                f = run.font
                f.size, f.name = Pt(lay["size"]), "Calibri"
                f.bold = r == 0 or group or k in strong or (r > 0 and (k, c) in colors)
                f.color.rgb = self.rgb(MUTED if r == 0 else colors.get((k, c), BLUE if link else INK))
                if link:
                    run.hyperlink.address = link["url"]
                if lay["numeric"][c] and c > 0 and not group:
                    p.alignment = PP_ALIGN.RIGHT

    def _chart_base(self, ch, legend: bool):
        from pptx.enum.chart import XL_LEGEND_POSITION
        from pptx.util import Pt
        ch.font.name, ch.font.size = "Calibri", Pt(11)
        ch.font.color.rgb = self.rgb(MUTED)
        ch.has_legend = legend
        if legend:
            ch.legend.position, ch.legend.include_in_layout = XL_LEGEND_POSITION.TOP, False
            ch.legend.font.size = Pt(11)

    def b_columns(self, b):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
        from pptx.util import Inches, Pt
        x, y, w, h = self._title_box(b)
        cd = CategoryChartData()
        cd.categories = [" ".join(ls) for ls in column_labels(b["cats"], w - 0.75, 11)[0]]
        for name, vals, _ in b["series"]:
            cd.add_series(name, vals)
        ch = self.s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
        self._chart_base(ch, True)
        plot = ch.plots[0]
        plot.gap_width, plot.overlap = 55, -10
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.font.size, dl.font.color.rgb = Pt(10), self.rgb(INK2)
        small = max((abs(v) for _, vs, _ in b["series"] for v in vs if v is not None), default=0) < 100
        # Indian figures grouped as the tables are (12,34,567), never 1,234,567 (DD-053)
        fmt = _fmt(b["fmt"])[1] if b.get("fmt") else ("#,##0.0;-#,##0.0" if small else INDIAN_FORMAT if b.get("inr") else "#,##0")
        dl.number_format, dl.number_format_is_linked = fmt, False
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        for series, (_, _, color) in zip(ch.series, b["series"]):
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = self.rgb(color)
            series.invert_if_negative = False
        va = ch.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = self.rgb(LINE)
        va.format.line.fill.background()
        va.tick_labels.font.size, va.tick_labels.font.color.rgb = Pt(10), self.rgb(MUTED)
        if b.get("inr") and not small and not b.get("fmt"):
            va.tick_labels.number_format, va.tick_labels.number_format_is_linked = INDIAN_FORMAT, False
        ca = ch.category_axis
        ca.tick_labels.font.size, ca.tick_labels.font.color.rgb = Pt(11), self.rgb(INK2)
        ca.format.line.color.rgb = self.rgb(LINE2)

    def b_hbars(self, b):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
        from pptx.util import Inches, Pt
        x, y, w, h = self._title_box(b)
        cd = CategoryChartData()
        _, labels, fs = hbar_labels(b["cats"], w, h)
        cd.categories = [" ".join(ls) for ls in labels]
        cd.add_series(b.get("title") or "", b["vals"])
        ch = self.s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
        self._chart_base(ch, False)
        plot = ch.plots[0]
        plot.gap_width = 45
        plot.has_data_labels = True
        plot.data_labels.number_format, plot.data_labels.number_format_is_linked = _fmt(b.get("fmt", "pct"))[1], False
        plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
        plot.data_labels.font.size = Pt(11)
        plot.data_labels.font.color.rgb = self.rgb(INK2)
        ser = ch.series[0]
        ser.invert_if_negative = False
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = self.rgb(BLUE)
        for j, color in enumerate(b.get("colors") or []):
            pt = ser.points[j]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = self.rgb(color)
        ch.value_axis.visible = False
        ch.value_axis.has_major_gridlines = False
        ch.category_axis.reverse_order = True
        ch.category_axis.format.line.color.rgb = self.rgb(LINE2)
        ch.category_axis.tick_labels.font.color.rgb = self.rgb(INK)
        ch.category_axis.tick_labels.font.size = Pt(fs)

    def b_lines(self, b):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_MARKER_STYLE
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        from pptx.util import Inches, Pt
        b = drawn_lines(b)
        if not b["series"]:
            return
        x, y, w, h = self._title_box(b)
        cd = CategoryChartData()
        cd.categories = b["cats"]
        for name, vals, *_ in b["series"]:
            cd.add_series(name, vals)
        ch = self.s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS if b.get("labels") else XL_CHART_TYPE.LINE, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
        self._chart_base(ch, True)
        for series, (_, _, color, *dash) in zip(ch.series, b["series"]):
            series.smooth = False
            series.format.line.color.rgb = self.rgb(color)
            series.format.line.width = Pt(2.25)
            if dash and dash[0]:
                series.format.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            series.marker.style = XL_MARKER_STYLE.CIRCLE if b.get("labels") else XL_MARKER_STYLE.NONE
            if b.get("labels"):
                series.marker.format.fill.solid()
                series.marker.format.fill.fore_color.rgb = self.rgb(color)
                series.marker.format.line.color.rgb = self.rgb(color)
        if b.get("labels"):
            plot = ch.plots[0]
            plot.has_data_labels = True
            plot.data_labels.number_format, plot.data_labels.number_format_is_linked = _fmt(b.get("fmt", "pct"))[1], False
            plot.data_labels.position = XL_LABEL_POSITION.ABOVE
            plot.data_labels.font.size = Pt(10)
        va = ch.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = self.rgb(LINE)
        va.format.line.fill.background()
        va.tick_labels.number_format, va.tick_labels.number_format_is_linked = _fmt(b.get("fmt", "pct"))[1], False
        va.tick_labels.font.size = Pt(10)
        ch.category_axis.tick_labels.font.size = Pt(10)
        ch.category_axis.format.line.color.rgb = self.rgb(LINE2)

    def bytes(self) -> bytes:
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


# ---------- PDF ----------
class PdfRenderer(Canvas):
    def __init__(self, title: str):
        from reportlab.pdfgen import canvas
        _fonts()
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=(W_IN * 72, H_IN * 72))
        self.c.setTitle(title)
        self.c.setAuthor("StratLab")
        self.started = False

    @staticmethod
    def col(h):
        from reportlab.lib.colors import HexColor
        return HexColor("#" + h)

    def _y(self, y):                 # inches from the top to points from the bottom
        return (H_IN - y) * 72

    def page(self, bg):
        if self.started:
            self.c.showPage()
        self.started = True
        self.rect(0, 0, W_IN, H_IN, bg, radius=0)

    def rect(self, x, y, w, h, fill, line=None, radius=0.08):
        self.c.setFillColor(self.col(fill))
        self.c.setStrokeColor(self.col(line or fill))
        self.c.setLineWidth(0.75)
        if radius:
            self.c.roundRect(x * 72, self._y(y + h), w * 72, h * 72, radius * 72, stroke=1 if line else 0, fill=1)
        else:
            self.c.rect(x * 72, self._y(y + h), w * 72, h * 72, stroke=1 if line else 0, fill=1)

    def line(self, x1, y1, x2, y2, color, width=0.75):
        self.c.setStrokeColor(self.col(color))
        self.c.setLineWidth(width)
        self.c.line(x1 * 72, self._y(y1), x2 * 72, self._y(y2))

    def poly(self, pts, fill):
        p = self.c.beginPath()
        p.moveTo(pts[0][0] * 72, self._y(pts[0][1]))
        for px, py in pts[1:]:
            p.lineTo(px * 72, self._y(py))
        p.close()
        self.c.setFillColor(self.col(fill))
        self.c.drawPath(p, stroke=0, fill=1)

    def text(self, x, y, w, h, paras, size, color=INK, bold=False, head=False, align="left", url=None, name=None, gap=0.35):
        self.c.setFillColor(self.col(color))
        yy = y
        for para in fit_paras(paras, size, w, h, bold, head, gap):
            for ln in wrap(para, size, w, bold, head):
                yy += _lh(size)
                face = _face(ln, bold, head)
                lw = _width(ln, size, bold) if not head else self.c.stringWidth(ln, face, size) / 72
                self.c.setFont(face, size)
                tx = x * 72 if align == "left" else (x + w - lw) * 72 if align == "right" else (x + (w - lw) / 2) * 72
                self.c.drawString(tx, self._y(yy - size * 0.28 / 72), ln)
                if url:
                    self.c.linkURL(url, (tx, self._y(yy), tx + lw * 72, self._y(yy - _lh(size))), relative=0)
            yy += gap * size / 72

    def _axes(self, chart, cats, size=11):
        chart.categoryAxis.categoryNames = cats
        chart.categoryAxis.labels.fontName, chart.categoryAxis.labels.fontSize = "Deck", size
        chart.categoryAxis.labels.fillColor = self.col(INK2)
        chart.categoryAxis.strokeColor = self.col(LINE2)
        chart.valueAxis.labels.fontName, chart.valueAxis.labels.fontSize = "Deck", 10
        chart.valueAxis.labels.fillColor = self.col(MUTED)
        chart.valueAxis.strokeColor = self.col(CARD)
        chart.valueAxis.gridStrokeColor = self.col(LINE)
        chart.valueAxis.visibleGrid = True

    def _legend(self, d, series, x, top, size=11):
        from reportlab.graphics.shapes import Rect, String
        tx = x
        for name, _, color, *_ in series:
            d.add(Rect(tx, top - 9, 10, 10, fillColor=self.col(color), strokeColor=None))
            d.add(String(tx + 15, top - 8, name, fontName=_face(name), fontSize=size, fillColor=self.col(INK2)))
            tx += 15 + _width(name, size) * 72 + 22

    def b_columns(self, b):
        from reportlab.graphics import renderPDF
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.shapes import Drawing
        x, y, w, h = self._title_box(b)
        d = Drawing(w * 72, h * 72)
        ch = VerticalBarChart()
        ch.x, ch.y, ch.width, ch.height = 44, 28, w * 72 - 54, h * 72 - 70
        ch.data = [list(vs) for _, vs, _ in b["series"]]
        small = max((abs(v) for _, vs, _ in b["series"] for v in vs if v is not None), default=0) < 100
        labels, fs = column_labels(b["cats"], ch.width / 72, 11 if len(b["cats"]) <= 8 else 10)
        deep = max(len(ls) for ls in labels) - 1                # a name on two lines: the plot gives up a line's height to it
        ch.y, ch.height = ch.y + deep * fs * 1.2, ch.height - deep * fs * 1.2
        self._axes(ch, ["\n".join(ls) for ls in labels], fs)
        ch.categoryAxis.labels.textAnchor = "middle"
        whole = _cr if b.get("inr") else (lambda v: f"{v:,.0f}")          # Indian grouping for Indian figures (DD-053)
        f = _fmt(b["fmt"])[0] if b.get("fmt") else (lambda v: f"{v:,.1f}") if small else whole
        ch.valueAxis.labelTextFormat = f
        vals = [v for _, vs, _ in b["series"] for v in vs if v is not None]
        if vals and min(vals) >= 0:
            ch.valueAxis.valueMin = 0
        ch.groupSpacing, ch.barSpacing = 8, 1
        for i, (_, _, color) in enumerate(b["series"]):
            ch.bars[i].fillColor = self.col(color)
            ch.bars[i].strokeColor = None
        bar_w = ch.width / max(1, len(b["cats"])) / max(1, len(b["series"]))
        ch.barLabelFormat = f
        ch.barLabels.fontName = "Deck"
        ch.barLabels.fontSize = 10 if bar_w >= 34 else 9 if bar_w >= 26 else 8
        ch.barLabels.fillColor = self.col(INK2)
        ch.barLabels.nudge = 8
        d.add(ch)
        self._legend(d, b["series"], ch.x, h * 72 - 6)
        renderPDF.draw(d, self.c, x * 72, self._y(y + h))

    def b_hbars(self, b):
        from reportlab.graphics import renderPDF
        from reportlab.graphics.charts.barcharts import HorizontalBarChart
        from reportlab.graphics.shapes import Drawing
        x, y, w, h = self._title_box(b)
        d = Drawing(w * 72, h * 72)
        ch = HorizontalBarChart()
        lw, labels, fs = hbar_labels(b["cats"], w, h)
        cats = ["\n".join(ls) for ls in labels]
        f = _fmt(b.get("fmt", "pct"))[0]
        vals = [v for v in b["vals"] if v is not None]
        rw = max((_width(f(v), BODY_MIN) for v in vals), default=0.4) + 0.12
        ch.x, ch.y, ch.width, ch.height = lw * 72, 4, (w - lw) * 72 - 4, h * 72 - 8
        data = list(reversed(b["vals"]))
        ch.data = [data]
        self._axes(ch, list(reversed(cats)), fs)
        ch.categoryAxis.labels.fillColor = self.col(INK)
        ch.categoryAxis.labelAxisMode = "low"          # R35: the names stay in their column; a bar below zero ran under its own name
        ch.valueAxis.visible = False
        ch.valueAxis.visibleGrid = False
        lo, hi = min([0.0] + vals), max([0.0] + vals)
        room = (hi - lo or 1) * rw * 72 / max(ch.width - 2 * rw * 72, 20)     # the value labels sit beyond each bar's end, inside the chart
        ch.valueAxis.valueMin = lo - (room if lo < 0 else 0)
        ch.valueAxis.valueMax = hi + room
        ch.bars[0].fillColor, ch.bars[0].strokeColor = self.col(BLUE), None
        for j, color in enumerate(reversed(b.get("colors") or [])):
            ch.bars[(0, j)].fillColor = self.col(color)
        ch.barSpacing, ch.groupSpacing = 0, max(3, ch.height / max(1, len(cats)) * 0.3)
        ch.barLabelFormat = f
        ch.barLabels.fontName, ch.barLabels.fontSize, ch.barLabels.fillColor = "Deck", BODY_MIN, self.col(INK2)
        ch.barLabels.boxTarget = "normal"
        # beyond each bar's end: the chart turns the anchor round for a bar below zero itself (R35: set by hand as well, it was turned twice
        # and the figure printed on the bar)
        ch.barLabels.boxAnchor, ch.barLabels.dx = "w", 4
        d.add(ch)
        renderPDF.draw(d, self.c, x * 72, self._y(y + h))

    def b_lines(self, b):
        from reportlab.graphics import renderPDF
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.shapes import Drawing
        b = drawn_lines(b)
        if not b["series"]:
            return
        x, y, w, h = self._title_box(b)
        d = Drawing(w * 72, h * 72)
        ch = HorizontalLineChart()
        f = _fmt(b.get("fmt", "pct"))[0]
        ch.x, ch.y, ch.width, ch.height = 46, 28, w * 72 - 62, h * 72 - 70
        ch.data = [list(vs) for _, vs, *_ in b["series"]]
        cats = list(b["cats"])
        every = max(1, -(-len(cats) // 8))
        self._axes(ch, [c if i % every == 0 or i == len(cats) - 1 else "" for i, c in enumerate(cats)], 10)
        ch.valueAxis.labelTextFormat = f
        vals = [v for _, vs, *_ in b["series"] for v in vs if v is not None]
        if vals:
            lo, hi = min(vals), max(vals)
            pad = (hi - lo) * 0.15 or abs(hi) * 0.1 or 1
            ch.valueAxis.valueMin, ch.valueAxis.valueMax = lo - pad, hi + pad
        ch.joinedLines = 1
        for i, (_, _, color, *dash) in enumerate(b["series"]):
            ch.lines[i].strokeColor = self.col(color)
            ch.lines[i].strokeWidth = 2.25
            if dash and dash[0]:
                ch.lines[i].strokeDashArray = (4, 3)
        if b.get("labels"):
            from reportlab.graphics.widgets.markers import makeMarker
            for i, (_, _, color, *_) in enumerate(b["series"]):
                ch.lines[i].symbol = makeMarker("FilledCircle", size=5, fillColor=self.col(color), strokeColor=self.col(color))
            ch.lineLabelFormat = f
            ch.lineLabels.fontName, ch.lineLabels.fontSize, ch.lineLabels.fillColor = "Deck", 10, self.col(INK2)
            ch.lineLabelNudge = 9
        d.add(ch)
        self._legend(d, b["series"], ch.x, h * 72 - 6)
        renderPDF.draw(d, self.c, x * 72, self._y(y + h))

    def bytes(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


# ---------- the layout check (R35) ----------
class Probe(Canvas):
    """A renderer that draws nothing: it lays a slide out exactly as the files do and notes every text that would be cut with an ellipsis
    ("cut"), shown without its last sentences or lines ("trimmed"), given to it already cut ("source"), a word broken across two lines
    ("broken") and table rows left off the slide ("rows"). [{"kind", "text" (as planned), "shown" (as drawn)}]."""

    def __init__(self):
        self.found, self._heard = [], set()

    def note(self, kind, text, shown=""):
        self.found.append({"kind": kind, "text": str(text), "shown": str(shown)})
        self._heard.add(str(shown))

    def page(self, bg):
        pass

    def rect(self, *a, **k):
        pass

    def line(self, *a, **k):
        pass

    def poly(self, *a, **k):
        pass

    def clip(self, text, size, width, lines, bold=False, head=False):
        got = clip(text, size, width, lines, bold, head)
        if got != str(text):
            self.note("cut" if got.endswith("…") else "trimmed", text, got)
        return got

    def label(self, text, size, width, lines=1, bold=False):
        got = short_label(text, size, width, lines, bold)
        if got.endswith("…") and not str(text).endswith("…"):
            self.note("cut", text, got)
        return got

    def text(self, x, y, w, h, paras, size, color=INK, bold=False, head=False, align="left", url=None, name=None, gap=0.35):
        paras = [str(p) for p in paras]
        shown = fit_paras(paras, size, w, h, bold, head, gap)
        for i, para in enumerate(paras):
            got = shown[i] if i < len(shown) else ""
            if got != para:
                self.note("cut" if got.endswith("…") else "trimmed", para, got)
            elif para in self._heard:
                continue
            elif para.endswith("…"):
                self.note("cut" if url else "source", para, para)
            elif not url and any(_width(x_, size, bold, head) > w + 0.01 for x_ in para.split()):
                self.note("broken", para, para)

    def b_table(self, b, lay=None):
        x, y, w, h = b["box"]
        lay = table_layout(b, w, h)
        if len(lay["rows"]) < len(b["rows"]):
            self.note("rows", f"{len(b['rows']) - len(lay['rows'])} of {len(b['rows'])} rows of the table", "")
        for r0, r1 in zip(b["rows"], lay["rows"]):               # a one-line table's cells, cut by the layout
            for v0, v1 in zip(r0, r1) if not isinstance(r0, dict) else ():
                if _cell_text(v1).endswith("…") and not _cell_text(v0).endswith("…"):
                    self.note("cut", _cell_text(v0), _cell_text(v1))
        super().b_table(b, lay)

    def _labels(self, cats, labels):
        for c, ls in zip(cats, labels):
            if ls and ls[-1].endswith("…") and not str(c).endswith("…"):
                self.note("cut", c, " ".join(ls))

    def b_columns(self, b):
        x, y, w, h = self._title_box(b)
        self._labels(b["cats"], column_labels(b["cats"], w - 0.75, 11 if len(b["cats"]) <= 8 else 10)[0])

    def b_hbars(self, b):
        x, y, w, h = self._title_box(b)
        self._labels(b["cats"], hbar_labels(b["cats"], w, h)[1])

    def b_lines(self, b):
        if drawn_lines(b)["series"]:
            self._title_box(b)


def probe(sl: Slide) -> list[dict]:
    """What the layout check finds on one slide (Probe)."""
    _fonts()
    p = Probe()
    p.draw(sl, 1, 1, "")
    return p.found


def _render(slides: list[Slide], footer: str, title: str, pdf: bool) -> bytes:
    """Slides as PowerPoint or as a PDF: the one renderer each deck goes through (a company's, a theme's)."""
    r = PdfRenderer(title) if pdf else PptxRenderer()
    for i, sl in enumerate(slides, 1):
        r.draw(sl, i, len(slides), footer)
    if not pdf:
        r.prs.core_properties.title = title
        r.prs.core_properties.author = "StratLab"
    return r.bytes()


def build(v: dict) -> bytes:
    """The deck as PowerPoint."""
    slides, footer = plan(v)
    return _render(slides, footer, f"{v['name']} ({v['symbol']}): company deep dive", pdf=False)


def build_pdf(v: dict) -> bytes:
    """The same deck as a PDF."""
    slides, footer = plan(v)
    return _render(slides, footer, f"{v['name']} ({v['symbol']}): company deep dive", pdf=True)


# ---------- a theme's deck (EXPORT, 4 Nov: "you forgot to put an export PDF or slides option in themes") ----------
THEME_DISCLAIMER = "Reported figures, the companies' own words and dated headlines. Not investment advice."
MEMBER_HEAD = ["Company", "Industry", "Market value", "What it does, in its own words", "In the theme by"]
MEMBER_WIDTHS = [2.6, 1.9, 1.3, 4.3, 2.0]
MEMBER_SLIDES = 12                        # at most this many slides of companies (in the appendix); the page's CSV has every one (the deck says so)
ONE_OFF = "†"                             # marks a net margin not reconciled (R44: above the EBITDA margin, or unusual, with nothing stored to give it): an anomaly flagged, never a cause named (R27)
ONE_OFF_NOTE = "net margin above the EBITDA margin, or unusual, that the company's own filed figures don't give"      # R44
ANOMALY_WHY = "the filing would show why"   # R27: what a figure that doesn't add up says instead of a guessed cause
AI_NOTE = "Written by AI from general knowledge, with no figures."
NOT_SHOWN = "No listed company is shown for this layer: none of the companies the map named has a description that shows it does this work."


def _sections(title: str, slides: list[Slide]) -> None:
    """Each section slide lists the slides of its part with their page numbers (a table that runs over slides is listed once)."""
    for i, s in enumerate(slides):
        if s.kind != "section":
            continue
        seen = []
        for j in range(i + 1, len(slides)):
            if slides[j].kind == "section":
                break
            base = re.sub(r" \(\d+ of \d+\)$", "", slides[j].title)
            if base.endswith(": operating figures"):          # follows its layer's slide, so the list never runs past the slide (R16: "stops at Layer 8")
                continue
            if base not in [t for t, _ in seen]:
                seen.append((base, j + 1))
        s.contents = seen


def short_names(head: list, rows: list, widths: list, col: int | None, what: str = "Layer", w: float = CW) -> str:
    """The key to a compact table's cut labels (R35): "Layer names in full: Large-scale… = Large-scale outsourcing and managed services;
    Digital… = Digital engineering and consulting or Digital marketing." for the names of column `col` that these rows show cut, in the
    order they appear; "" when none is cut. Two names cut to the same label are both said."""
    if col is None or not rows:
        return ""
    lay = table_layout({"head": head, "rows": rows, "widths": widths, "compact": True, "tight": True, "full": [col]}, w, 99)
    cut: dict = {}
    for full, shown in zip((r for r in rows if not isinstance(r, dict)), (r for r in lay["rows"] if not isinstance(r, dict))):
        a, b = _cell_text(full[col]), _cell_text(shown[col])
        if a != b and a not in cut.setdefault(b, []):
            cut[b].append(a)
    return (f"{what} names in full: " + "; ".join(f"{k} = {' or '.join(v)}" for k, v in cut.items()) + ".") if cut else ""


def note_h(text: str, w: float = CW) -> float:
    """The height a muted note under a table needs at 11 pt, so it is never cut (the owner, 7 Nov: the closing disclaimer was clipped)."""
    return len(wrap(text, BODY_MIN, w)) * _lh(BODY_MIN) + 0.04


NO_WORDS = "No description in its own words yet"          # LIVE6-007: the page's words for a company with none (theme_base.NO_WORDS)


def _what(text: str, name: str = "") -> str:
    """What a company does, as the page shows it, cleaned as a new read would be (theme_base.one_line): a "**Company Overview **" heading,
    "Incorporatedin1994" or a month's sales line never reaches a slide; nor a line that isn't its own words about its work (LIVE6-007:
    theme_base.own_words: "Fortinet, Inc. | What it does: Fortinet, Inc.", a filing's title)."""
    from .intel.theme_base import one_line, own_words
    return own_words(one_line(text), name) if text else ""


def shown_label(cos: list, k: int) -> str:
    """What the first k companies of a layer table are (R34): "the largest k of n by market value" only when they are the k largest; when
    companies in the layer's figures are listed first (live IT: three larger ones left out of figures sat below), it says so."""
    caps = [c.get("cap") or 0 for c in cos]
    if sorted(caps[:k], reverse=True) == sorted(caps, reverse=True)[:k]:
        return f"The largest {k} of {len(cos)} by market value"
    return f"The first {k} of {len(cos)}: companies in the layer's figures first, each group by market value"


ROLL_TITLE = "Who is in each layer's calculations"
ROLL_LINES = 2                    # a layer page names every company in and left out when that takes no more lines than this
ROLL_NAMES = 6                    # else this many names of each group; the rest are counted there and named in the appendix
ROLL_FULL = 40                    # a layer page names every company when the line stays short (roll_line); the appendix names every one (roll_rows)
from .intel.theme_data import CALC_KINDS as ROLL_WHY, in_calc, mostly_whole      # noqa: E402 (why a listed company is left out, in this order: one list, theme_data.calc_record)
# ex49 (R48): the mark on a left-out company's own row is its reason's kind (theme_data.out_reason), each with its note under the table
ROLL_TAG = {"different revenue model": "different model", "another business": "another business", "insufficient evidence": "insufficient evidence",
            "not confirmed in the theme": "not confirmed", "no figure stored": "no figures"}
KIND_OF = {"other business": "different revenue model", "way of earning not shown": "insufficient evidence", "not confirmed": "not confirmed in the theme",
           "no revenue figure": "no figure stored"}       # a record's kept key (theme_data.CALC_WHY) -> its kind, for a record with none


def why_kind(rec: dict) -> str:
    """ex49: a left-out record's reason kind (theme_data.CALC_KINDS)."""
    return rec.get("kind") or KIND_OF.get(rec.get("why"), "")


def why_label(rec: dict) -> str:
    """ex49: a left-out record's reason as a roll groups companies by it: its kind with what exactly ("different revenue model: platforms
    and marketplaces against the layer's retail", "insufficient evidence (no description of its own)")."""
    return rec.get("label") or why_kind(rec)


def label_kind(label: str) -> str:
    """ex49: the kind a roll's reason label is of ("insufficient evidence (no description of its own)" -> "insufficient evidence")."""
    return next((k for k in ROLL_WHY if label.startswith(k)), label)


def label_rank(label: str) -> int:
    return next((i for i, k in enumerate(ROLL_WHY) if label.startswith(k)), len(ROLL_WHY))


FIGURE_WORDS = {"ebitda": "EBITDA margin", "net": "net margin", "roe": "ROE", "roce": "ROCE"}


def part_note(c: dict, keys: tuple) -> str:
    """ex49 (R48): which part of a company in its layer's calculations is left out, and why: a figure not stored, or one whose state keeps it
    out of the median (not reconciled, invalid, or on another period basis: n.c.); "" when none is."""
    from .intel.theme_data import DEVELOPER_KEYS, STATE_WORDS, VERIFIED
    held, ver, nc = c.get("held") or {}, c.get("verify") or {}, set(c.get("nc") or ())
    gone, odd = [], []
    for k in keys:
        st = (held.get(k) or {}).get("state") or ((ver.get(k) or {}).get("state") if (ver.get(k) or {}).get("state") != VERIFIED else None)
        if k == "net" and c.get("one_off") and not st:
            st = "unverified_extreme"
        if k in DEVELOPER_KEYS and c.get("developer") and not st:     # d53: spending ahead of its revenue, its margins apart
            odd.append(f"{FIGURE_WORDS.get(k, k)} apart (costs over twice revenue)")
        elif st:
            odd.append(f"{FIGURE_WORDS.get(k, k)} {STATE_WORDS.get(st, 'held')}")
        elif k in nc:
            odd.append(f"{FIGURE_WORDS.get(k, k)} on another period basis")
        elif c.get(k) is None:
            gone.append(FIGURE_WORDS.get(k, k))
    parts = ([" and ".join(gone) + " not stored"] if gone else []) + odd
    return "partial: " + ", ".join(parts) if parts else ""
_LEGAL = re.compile(r"[,.]?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|n\.?v|s\.?a|ag)\.?$", re.I)


def layer_roll(layer: dict, cos: list, keys: tuple = ("ebitda", "net")) -> tuple[list, list]:
    """Who of a layer's listed companies is in its calculations and why each of the others is not (R35, GPT reviews of R31.5-R31.9: live IT
    said "13 companies (4 in the layer's calculations)" and named neither): ([(name, note)] in, [(name, why)] left out), in the page's order.
    In: confirmed, how it earns shown and of the layer's kind, with a revenue figure; its note says a whole company (in the revenue total,
    out of the medians where the layer has a company of its own) or figures in part (one of `keys` missing or left out of its median).
    Left out: one of ROLL_WHY. Lane m1: who is in and why each other is not is the row's kept record ("calc"), the same one the layer's
    "n" and every table's count are taken from."""
    from .intel.theme_data import calc_of
    wide = set(layer.get("company_wide") or []) | {c["symbol"] for c in cos if c.get("company_wide")}
    apart = layer.get("stats_over") != "all"
    ins, outs = [], []
    for c in cos:
        nm = _LEGAL.sub("", clean_name(c.get("name") or c.get("symbol") or "")).strip(" ,.") or str(c.get("symbol") or "")
        rec = calc_of(c)                  # lane m1: the company's kept record (theme_data.calc_record), never worked out again here
        if not rec["in"]:
            outs.append((nm, why_label(rec)))         # ex49: the reason's kind with what exactly
        elif c["symbol"] in wide and apart:
            ins.append((nm, "partial: whole company's figures, revenue only"))
        else:
            ins.append((nm, part_note(c, keys) if c.get("one_off") or c.get("nc") or c.get("developer") or any(c.get(k) is None for k in keys) else ""))
    return ins, outs


def roll_words(ins: list, outs: list, limit: int = ROLL_NAMES, short: bool = False) -> tuple[str, str, bool]:
    """(who is in, who is left out with why, whether a name was left off): "A, B, C (figures in part)", "other business: D, E; not
    confirmed: F", each group at most `limit` names and then "and 5 more". Lane m1 (the outside review of the live R32 IT deck: nine names
    with their one reason after the last of them read as three with none): the reason comes before the names it is of."""
    cut = False

    def some(names: list) -> str:
        nonlocal cut
        cut = cut or len(names) > limit
        return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")
    plain = [n for n, note in ins if not note]
    noted = [f"{n} ({note})" for n, note in ins if note]
    in_ = "; ".join(x for x in (some(plain), some(noted)) if x)
    # ex49: each precise reason, in its kind's order; `short`: each kind alone (a layer page's line with no room for them, the appendix's
    # roll saying each in full)
    outs = [(n, label_kind(w)) for n, w in outs] if short else outs
    labels = sorted(dict.fromkeys(w for _, w in outs), key=label_rank)
    out_ = "; ".join(f"{why}: {some([n for n, w in outs if w == why])}" for why in labels)
    return in_, out_, cut or (short and any(label_kind(w) != w for _, w in outs))


ROLL_HEAD, ROLL_WIDTHS = ["Layer", "In its calculations", "Left out, and why"], [2.6, 4.7, 5.0]
ROLL_MORE = " (continued)"        # a layer's appendix row that goes on naming its companies after the row before it


def roll_rows(name: str, ins: list, outs: list, h: float, w: float = CW) -> list[list]:
    """A layer's rows in the appendix's roll, every company named (n1, the outside review of the live R33 decks: a layer's single row taller
    than a page was left off it, and Retail's and Real Estate's rolls printed an empty page): one row when it fits a w x h table under the
    head, else the names cut evenly into as few rows as fit, each later one "<layer> (continued)", each left-out reason before its names in
    every row it reaches."""
    ins_ = [x for x in ins if not x[1]] + [x for x in ins if x[1]]
    outs_ = sorted(outs, key=lambda x: (label_rank(x[1]), x[1]))
    total = len(ins) + len(outs)

    def fits(r):
        return len(table_layout({"head": ROLL_HEAD, "rows": [r], "widths": ROLL_WIDTHS, "numeric": [False] * 3}, w, h)["rows"]) == 1
    rows: list[list] = []
    for k in range(1, max(1, len(ins_), len(outs_)) + 1):
        a, b = -(-len(ins_) // k), -(-len(outs_) // k)
        rows = []
        for j in range(k):
            pi, po = ins_[j * a:(j + 1) * a], outs_[j * b:(j + 1) * b]
            if j and not pi and not po:
                continue
            in_, out_, _ = roll_words(pi, po, total + 1)
            if j == 0:
                rows.append([name, f"{len(ins)} of {total}: {in_}" if in_ else f"0 of {total}", f"{len(outs)}: {out_}"])
            else:
                rows.append([name + ROLL_MORE, in_, out_])
        if all(fits(r) for r in rows):
            break
    return rows


def roll_line(ins: list, outs: list) -> tuple[str, bool]:
    """A layer page's note of who is in its calculations and who is left out with why, and whether it leaves a name off: every one named
    when that takes no more than ROLL_LINES lines, else ROLL_NAMES of each group (half as many when that is still too long) and where the
    rest are."""
    total = len(ins) + len(outs)
    for short, limit in [(False, n) for n in (ROLL_FULL, ROLL_NAMES, ROLL_NAMES // 2)] + [(True, ROLL_NAMES // 2)]:
        in_, out_, cut = roll_words(ins, outs, limit, short)
        line = roll_said(len(ins), total, len(outs), in_, out_, cut)
        if len(wrap(line.replace(f"⟦{ROLL_TITLE}⟧", "p. 00"), BODY_MIN, CW)) <= ROLL_LINES:
            break
    return line, cut


def roll_said(n_in: int, total: int, n_out: int, in_: str, out_: str, cut: bool) -> str:
    return (f"In the layer's calculations ({n_in} of {total}): {in_ or 'none'}. Left out ({n_out}): {out_}."
            + (f" Every one: appendix, ⟦{ROLL_TITLE}⟧." if cut else ""))


def kind_notes(cos: list, shown: set) -> list[str]:
    '''ex49 (R48): the notes of a layer table's left-out marks (ROLL_TAG), each kind once, its companies grouped by their exact reason:
    "(different model): eBay, Mercadolibre: the way of earning of “Platforms and marketplaces” (commissions ...), not the layer's, that of
    “Retail” (the margin on goods ...). Left out of this layer's figures and rankings."'''
    from .intel.theme_data import calc_of
    groups: dict = {}
    for c in cos:
        rec = calc_of(c)
        groups.setdefault(why_kind(rec), {}).setdefault(rec.get("detail") or "", []).append(clean_name(c.get("name") or c.get("symbol") or ""))
    out = []
    for kind in ROLL_WHY:
        tag = ROLL_TAG.get(kind)
        if kind not in groups or tag not in shown:
            continue
        said = []
        for detail, names in groups[kind].items():
            who = ", ".join(names) if len(names) <= 4 else f"{', '.join(names[:3])} and {len(names) - 3} more"
            if detail:
                said.append(f"{who}: {detail}")
        out.append(f"({tag}): " + ("; ".join(said) + ". " if said else "") + "Left out of this layer's figures and rankings.")
    return out


def layer_head(layer: dict, cos: list, amt) -> str:
    """A layer page's header (R30, the owner's review: "1 company, revenue ₹32,493 cr together" over 4 listed): the companies listed and, when
    fewer are in the figures, how many; the revenue is of those in the figures."""
    from .intel.theme_data import layer_counts
    got = layer_counts({"companies": cos})              # the layer's one list of rows (lane m1)
    listed, figs = got["listed"], got["n"]
    n = figs
    dbl = layer.get("double") or []
    # gl50: a listed subsidiary whose parent is in the layer too is left out of the revenue added together, and said so
    sub = ("; " + "; ".join(f"{clean_name(d['name'])} left out of it, as {clean_name(d['parent'])} holds {d['pct']:g}% and its figures include it"
                            for d in dbl)) if dbl else ""
    if listed > figs:
        return f"{_n(listed, 'company', 'companies')} ({figs} in the layer's calculations), revenue of those {amt(layer.get('revenue'))}{sub}"
    return f"{_n(n, 'company', 'companies')}, revenue {amt(layer.get('revenue'))} together{sub}"


def coverage(v: dict) -> dict:
    """How many companies are in the theme and how many have their key figures, with those figures' share of the theme's market value, in ONE
    wording used everywhere (R20, the owner: the universe against the figures, prominent and the same on every page): "182 in the exchange's
    industries · 60 with figures (97% of value)". "With figures" counts companies whose key figures exist (revenue or profit)."""
    members = v.get("members") or []
    p = v.get("placements") or {}
    total = p.get("total") or len({m["symbol"] for m in members})
    # R28: "with figures" is of the confirmed companies only (an unconfirmed one is listed, never in the figures); a dive kept from before
    # counted every listed company, so the smaller of its two counts (the confirmed ones with figures) is the one said
    known = [x for x in (v.get("with_figures"), v.get("members_with_figures")) if x is not None]
    n = min(known) if known else (v.get("figures") or {}).get("shown") or 0
    vs = value_share(v)
    share, valued = vs["share"], vs["valued"]
    base_n = max(0, (p.get("base") or 0) - (p.get("named") or 0))
    where = ("in the exchange's industries" if base_n and base_n >= total else "in the theme's list" if p.get("named") and not base_n and not p.get("added")
             else "in the theme")
    universe = f"{total:,} {where}"
    # R27: a share of value always names its denominator: whose market value it is a share of
    of_what = share_of_what(valued, total)
    figs = f"{n:,} with figures" + (f" ({share}% of {of_what})" if share is not None else "")
    line = f"{universe} · {figs}"
    return {"n": n, "total": total, "share": share, "text": line, "line": line, "universe": universe, "figs": figs, "valued": valued, "of_what": of_what}


def pct_of(part: float, whole: float):
    """A share in %, never rounded up to a whole that isn't there (R29, the owner's review of the live R27 Semiconductors deck: 58 companies
    with figures "cover 100% of the value of 105"): 100 only when the part is the whole; from 99 up, and under 1, to one decimal rounded down
    (99.6, 0.4); else whole points. None with no whole."""
    import math
    if not whole or whole <= 0 or part is None:
        return None
    if part >= whole:
        return 100
    x = part / whole * 100
    if x >= 99 or x < 1:
        d = math.floor(x * 10) / 10
        d = d if d > 0 or part <= 0 else 0.1
        return int(d) if float(d).is_integer() else d           # 99, never "99.0" (no false precision)
    return round(x)


def value_share(v: dict) -> dict:
    """The share of the theme's market value that its companies with figures have, worked out from the members alone (R29, P0): numerator the
    market value of the confirmed companies with figures (revenue, profit or a margin), denominator the market value of EVERY company in the
    stated universe that has one, with figures or not, confirmed or not (one universe: the companies the deck lists). Each company once.
    {"share", "valued" (companies with a market value), "with_value" (of them, with figures), "value_with", "value_all"}."""
    members = v.get("members") or []
    unsure = {s_ for s_, st in (v.get("status") or {}).items() if st == "unverified"}
    caps: dict = {}
    for m in members:
        c = m.get("cap")
        if m.get("symbol") and (m["symbol"] not in caps or not caps[m["symbol"]]):
            caps[m["symbol"]] = c if isinstance(c, (int, float)) and c > 0 else 0
    with_f = {m["symbol"] for m in members if m.get("symbol") and m["symbol"] not in unsure
              and (m.get("revenue") is not None or m.get("net") is not None or m.get("ebitda") is not None)}
    every = sum(caps.values())
    got = sum(caps.get(s_, 0) for s_ in with_f)
    return {"share": pct_of(got, every) if with_f else None, "valued": sum(1 for c in caps.values() if c),
            "with_value": sum(1 for s_ in with_f if caps.get(s_)), "value_with": got, "value_all": every}


_SHARE_CLAIM = re.compile(r"(\d+(?:\.\d+)?)% of (?:the value of the ([\d,]+) with one|the combined market value of the ([\d,]+) of [\d,]+ with one|"
                          r"the market value of all ([\d,]+))")


def share_flag(text: str, v: dict) -> str | None:
    """Why a stated share of market value isn't the one the members give (R29: the gate reproduces it): another share, or another count of
    companies with a market value. None when it reproduces, or when the text states none."""
    vs = value_share(v)
    for m in _SHARE_CLAIM.finditer(text or ""):
        said = float(m.group(1))
        if vs["share"] is None or abs(said - float(vs["share"])) > 1e-9:
            return f"share {m.group(1)}% of market value, the members give {vs['share']}%"
        if m.group(4):              # "of all N": N is the universe, every one of which has a market value
            if vs["valued"] < int(m.group(4).replace(",", "")):
                return f"all {m.group(4)} with a market value, the members give {vs['valued']}"
        elif int((m.group(2) or m.group(3)).replace(",", "")) != vs["valued"]:
            return f"{m.group(2) or m.group(3)} with a market value, the members give {vs['valued']}"
    return None


def share_of_what(valued: int, total: int) -> str:
    """The denominator of a share of market value, said (R27, the owner's review: "100% of value" must say of what): "the market value of all
    112", or "the combined market value of the 58 of 112 with one"."""
    return f"the market value of all {total:,}" if valued >= total else f"the combined market value of the {valued:,} of {total:,} with one"


def reconciled_counts(v: dict, cov: dict) -> dict:
    """The four counts every deck states, the same everywhere (R27, P0): companies considered (the eligible universe), confirmed members, those
    with figures, and those in each calculation (each median's own count)."""
    mem = v.get("membership") or {}
    sec = v.get("sections") or {}
    meds, val, gm, q = sec.get("medians") or {}, sec.get("valuation") or {}, sec.get("growth") or {}, sec.get("quarter") or {}
    confirmed = mem.get("confirmed") if mem.get("placed") else None
    each = [(label, k) for label, k in (
        ("EBITDA margin", (meds.get("ebitda") or {}).get("n")), ("net margin", (meds.get("net") or {}).get("n")), ("ROCE", (meds.get("roce") or {}).get("n")),
        ("ROE", (meds.get("roe") or {}).get("n") if (v.get("checks") or {}).get("lenders") else None), ("P/E", (val.get("pe") or {}).get("n")),
        ("revenue growth together", ((gm.get("aggregate") or {}).get("revenue_1y") or {}).get("n")),
        ("latest quarter", len(q.get("companies") or []) or None)) if k]
    # tx2 (R46, the outside review of the live Release 45 decks: "considered = rejected + members"): the companies the theme's industries
    # brought in that their own words show to be in another business are considered and screened out, never members (off_industry)
    rejected = screened_out(v)
    return {"considered": cov["total"] + rejected, "members": cov["total"], "rejected": rejected, "confirmed": confirmed,
            "checked": mem.get("placed"), "with_figures": cov["n"], "counted": v.get("members_with_figures") or 0, "each": each}


def screened_out(v: dict) -> int:
    """How many companies were considered and screened out as another business (theme_base.without_off_industry): never members."""
    return len({x["ticker"] for x in (v.get("placements") or {}).get("off_industry") or [] if isinstance(x, dict) and x.get("ticker")})


def counts_words(c: dict) -> str:
    """The four counts in one line: "Considered 112 · confirmed 60 (of 60 checked) · with figures 58 · in each calculation: EBITDA margin 55, ..."."""
    members = c.get("members", c["considered"])
    conf = ("confirmed " + f"{c['confirmed']:,}" + (f" (of {c['checked']:,} checked)" if c.get("checked") and c["checked"] < members else "")
            if c.get("confirmed") is not None else f"confirmed, with figures {c['counted']:,}")
    each = ", ".join(f"{label} {k:,}" for label, k in c["each"])
    # tx2 (R46): the companies screened out as another business are counted among those considered, said apart from the members
    out = f"{c.get('rejected') or 0:,} screened out as another business, {members:,} members" if c.get("rejected") else ""
    return f"Considered {c['considered']:,}" + (f" ({out})" if out else "") + f" · {conf} · with figures {c['with_figures']:,}" \
        + (f" · in each calculation: {each}" if each else "")


def membership_words(v: dict, total: int) -> str:
    """How the theme's companies got in and how many are confirmed (R17-012): "182 in the exchange's industry list; 167 confirmed by their own
    description, 15 not yet". The counts are of the companies whose membership was checked (the map the figures are worked out for)."""
    p = v.get("placements") or {}
    mem = v.get("membership") or {}
    base_n = max(0, (p.get("base") or 0) - (p.get("named") or 0))
    src = [f"{base_n:,} in the exchange's industry list"] if base_n else []
    if p.get("named"):
        src.append(f"{p['named']:,} named in the theme's list")
    if p.get("added"):
        src.append(f"{p['added']:,} added by the AI")
    head = f"{total:,} companies" + (f" ({', '.join(src)})" if src and (len(src) > 1 or base_n != total) else "")
    if src and len(src) == 1 and base_n == total:
        head = f"{total:,} in the exchange's industry list"
    if mem.get("placed") and mem["placed"] < total:
        # gl50 (R50, the rotating review: "100 of the 100 checked confirmed by their own description, 0 not yet" of 821, 588 and 317
        # companies): the companies not checked are said as such, never folded into "0 not yet"
        head += (f"; {mem['placed']:,} checked (the map's own picks, then the largest by market value): {mem.get('confirmed', 0):,} confirmed by "
                 f"their own description, {mem.get('not_confirmed', 0):,} not; {total - mem['placed']:,} not checked yet")
    elif mem.get("placed"):
        head += f"; {mem.get('confirmed', 0):,} confirmed by their own description, {mem.get('not_confirmed', 0):,} not yet"
    return head


def layer_common(layer: dict) -> str:
    """The one line a layer's page shows of what its companies have in common: how they earn (theme_base.by_model, R25: the owner's review,
    "avoid grouping businesses with fundamentally different revenue models"), from their own descriptions; "" when none is known."""
    model = layer.get("model") or {}
    line = str(model.get("line") or "").strip()
    if line and model.get("sparse"):           # R26: under half the layer's companies with a known model: said plainly, no "In common"
        return line
    return f"In common: {line[:1].lower()}{line[1:]}" if line else ""


def claim_layers(text: str, layers: list[str]) -> list[str]:
    """The layers a tailwind or risk names, by the layer's own words (at most two), so each claim says which part of the chain it is about."""
    from .intel.theme_data import _stems, does_the_work
    out = []
    for name in layers:
        words = _stems(name)
        if words and does_the_work(text, words):
            out.append(name)
    return out[:2]


OWN_MOVE = 1.0                    # points the named institutions' stake must move for a company to be listed among the ownership changes


def changed(x, by: float) -> bool:
    return x is not None and abs(x) >= by


REF = re.compile(r"⟦([^⟧]+)⟧")


def premium_words(p: float) -> str:
    """A P/E set against its peers' in words, one sign only: "23.7% below", "12.0% above", "level with"."""
    text = f"{abs(p):.1f}"
    return "level with" if float(text) == 0 else f"{text}% {'above' if p > 0 else 'below'}"


def peer_cover_words(val: dict) -> str:
    """How far comparable peers go (R29): "Comparable peer sets for 0 of the 24 companies with a P/E."."""
    pe_n = (val.get("pe") or {}).get("n") or 0
    pp = (val.get("peers") or {}).get("pe") or {}
    k = pp.get("n") or 0
    if k * 2 >= pe_n > 0 and pp.get("like") is False:          # d1
        return (f"Peer sets of similar size in their sector for {k} of the {pe_n} companies with a P/E, mostly of other industries than the "
                "companies' own: not like for like.")
    return f"Comparable peer sets for {k} of the {pe_n} companies with a P/E."


def descriptive_line(val: dict) -> str:
    """The descriptive valuation's headline (R29, when comparable peers cover under half): the theme's own medians, each with its count and
    range, and how far peers go; never a premium, a discount or a market comparison."""
    parts = []
    for key, label in (("pe", "P/E"), ("pb", "P/B"), ("ev_ebitda", "EV/EBITDA")):
        st = val.get(key) or {}
        if st.get("median") is not None and (st.get("n") or 0) >= MIN_BASE:
            parts.append(f"{label} {_times(st['median'])} ({_n(st['n'], 'company', 'companies')}, {_times(st['min'])} to {_times(st['max'])})")
    pe_n = (val.get("pe") or {}).get("n") or 0
    k = (((val.get("peers") or {}).get("pe") or {}).get("n")) or 0
    head = "The theme's own median " + ", ".join(parts) if parts else "The theme's own valuation"
    if k * 2 >= pe_n > 0 and (((val.get("peers") or {}).get("pe") or {}).get("like") is False):
        # d1: peers for most, but of other industries than the companies' own: not like for like, so no relative figure
        priced = f", prices at the {_day(val['price_at'])} close" if parts and val.get("price_at") else ""
        return f"{head}{priced}; the companies of similar size in their sector are mostly of other industries, so no relative figure"
    # m2 (live R32 Telecom: the one deck of 14 whose P/E line named no price date): the theme's own multiples are on prices too
    priced = f", prices at the {_day(val['price_at'])} close" if parts and val.get("price_at") else ""
    return f"{head}{priced}; comparable peers for {k} of {pe_n}, so no relative figure"


def layer_valuation_rows(val: dict):
    """(head, rows, widths) of each layer's own median P/E, P/B and EV/EBITDA with its count (R29: the descriptive valuation by layer); None
    with fewer than two layers to show."""
    lays = [x for x in val.get("by_layer") or [] if any(x.get(k) for k in ("pe", "pb", "ev_ebitda"))]
    if len(lays) < 2:
        return None
    rows = [[x["layer"]] + [_medn(x.get(k), None, _times) if x.get(k) else "–" for k in ("pe", "pb", "ev_ebitda")] for x in lays]
    return ["Layer: its own medians (companies)", "P/E", "P/B", "EV/EBITDA"], rows, [3.1, 1.3, 1.3, 1.3]


def pe_peer_line(pp: dict) -> str:
    """The one P/E comparison the deck makes (R17-010: the findings said 8.2% above while the table's medians were 3.4% apart): the median P/E
    of the companies that have comparable peers against the median of their peers' medians, both over the same companies, and the gap is
    the ratio of those two medians, the two numbers the valuation table shows. Which peer set it is, and how many have none, said (R27)."""
    # d1: the peers most used, by name (the live Release 41 Banks deck named none)
    named = f" (peers most used: {', '.join(clean_name(x) for x in pp['names'])})" if pp.get("names") else ""
    return (f"Median P/E {_times(pp['theme'])} for the {_n(pp['n'], 'company', 'companies')} with comparable peers {peer_set_words(pp)}, "
            f"{premium_words(pp['premium'])} their peers' median of {_times(pp['peers'])}{named}"
            + (f" (prices at the {_day(pp['as_of'])} close)" if pp.get("as_of") else "") + no_peer_words(pp))       # LIVE6-006: one date format


def dated_peers(v: dict) -> dict:
    """The theme's comparisons with its peers as every slide reads them (R35, GPT reviews of R31.5-R31.9: the live Retail deck's P/E line
    named no price date): the P/E one carries the close its prices are of, the dive's own or, for a dive kept from before, the deck's
    "as of" day. publication_gate set it after the slides were written, so no line had it."""
    val = (v.get("sections") or {}).get("valuation") or {}
    found = val.get("peers") or {}
    if isinstance(found.get("pe"), dict) and not found["pe"].get("as_of") and v.get("as_of"):
        found["pe"]["as_of"] = str(v["as_of"])[:10]
    # m2: the valuation's own price day (descriptive_line: a theme with no comparable peers states its own P/E, on the same close)
    day = (found.get("pe") or {}).get("as_of") if isinstance(found.get("pe"), dict) else None
    if val and not val.get("price_at") and (day or v.get("as_of")):
        val["price_at"] = str(day or v["as_of"])[:10]
    return found


def peer_moved_line(pp: dict) -> str:
    """"Their peers' median P/E was 19.2x at the 2026-11-08 close and is 18.4x at the 2026-11-09 close: prices moved between the two closes."
    (R35: the stored run before this one, said only when the two are more than theme_data.PEER_MOVE % apart; "" otherwise). Neutral: the
    two figures, their days and what differs between the runs, never a cause guessed beyond that."""
    mv = pp.get("moved") or {}
    if not mv.get("from") or not mv.get("to"):
        return ""
    same_day = mv.get("on") and mv.get("on") == mv.get("at")
    k0, k1, n0, n1 = mv.get("peers_from"), mv.get("peers_to"), mv.get("n_from"), mv.get("n_to")
    count = (f"; {n0:,} of the theme's companies compared then, {n1:,} now" if n0 and n1 and n0 != n1 else "") + \
        (f"; {k0:,} peers behind it then, {k1:,} now" if k0 and k1 and k0 != k1 else "")
    if same_day:
        return (f"Their peers' median P/E was {_times(mv['from'])} at an earlier run on the {_day(mv['on'])} close and is {_times(mv['to'])} now: "
                f"the peers or their reported figures changed{count}.")
    return (f"Their peers' median P/E was {_times(mv['from'])} at the {_day(mv['on']) if mv.get('on') else 'earlier'} close and is {_times(mv['to'])} "
            f"at the {_day(mv['at']) if mv.get('at') else 'latest'} close: prices moved between the two closes{count}.")


def no_peer_words(pp: dict) -> str:
    """"; 3 with no comparable peer set (left out)", or "" (R27: a company without enough comparable peers is counted, never compared)."""
    k = pp.get("none") or (pp.get("sets") or {}).get("none") or 0
    return f"; {k} with no comparable peer set (left out)" if k else ""


def peer_set_words(pp: dict) -> str:
    """Which companies the peers are (R27, the owner's outside review: business model and sector first, then size, never the whole market):
    their own sector outside the theme, or the sector with the theme's other companies counted, each of similar market value.
    R40 (the owner's review of the live Release 39 decks: "outside the the theme" read in 13 decks, where "outside the theme for 93, the
    theme's other companies counted for 1" wraps after "the"): said as "this theme", so no wrap of the sentence puts one "the" beside
    another."""
    sets = {k: n for k, n in (pp.get("sets") or {}).items() if k != "none" and n}
    sec_n, th_n = sets.get("sector", 0), sets.get("sector_theme", 0)
    if not sets:
        return "(no comparable peer set)"
    if not th_n:
        return "(own sector, similar market value, outside this theme)"
    if not sec_n:
        return "(own sector, similar market value, this theme's other companies counted)"
    return f"(own sector, similar market value: outside this theme for {sec_n}, with this theme's other companies counted for {th_n})"


PEER_MIN = 10                     # theme_data.PEER_MIN: comparable peers a company needs for its relative comparison


def _refs(slides: list) -> None:
    """Page references: "⟦Valuation⟧" in a finding becomes "p. 31", the first slide whose title starts with it ("" when there's none)."""
    first = {}
    for i, s in enumerate(slides, 1):
        first.setdefault(re.sub(r" \(\d+ of \d+\)$", "", s.title), i)

    gone = []                     # R48: a reference that finds no page, kept for the publication gate (provenance_flags)

    def page(m):
        hit = next((p for t, p in first.items() if t.startswith(m.group(1))), None)
        if not hit:
            gone.append(m.group(1))
        return f"p. {hit}" if hit else ""

    def fix(x):
        return REF.sub(page, x).replace(" ()", "").replace("()", "").rstrip() if isinstance(x, str) else x
    for s in slides:
        s.subtitle = fix(s.subtitle)
        for b in s.blocks:
            if b.get("paras"):
                b["paras"] = [fix(x) for x in b["paras"]]
            if b.get("rows"):
                # a "Slide" column whose pages aren't in this deck is dropped with its empty cells (R19): no reference is lost there
                k = (b.get("head") or []).index("Slide") if "Slide" in (b.get("head") or []) else None

                def cell(j, x):
                    n = len(gone)
                    out = fix(x)
                    if j == k:
                        del gone[n:]
                    return out
                b["rows"] = [r if isinstance(r, dict) else [cell(j, x) for j, x in enumerate(r)] for r in b["rows"]]
            if b.get("items") and isinstance(b["items"][0], dict):
                b["items"] = [{**it, "lines": [fix(x) for x in it.get("lines") or []], "value": fix(it.get("value")), "title": fix(it.get("title")),
                               "note": fix(it.get("note"))} for it in b["items"]]
        if gone:
            slides[0].unresolved = list(getattr(slides[0], "unresolved", None) or []) + [(s.title, x) for x in gone]
            gone.clear()


UPDATES_TITLE = "Dated company updates"
_AUDITOR_KIND = re.compile(r"\b(statutory|secretarial|internal|cost|joint)\s+auditors?\b", re.I)
_AUDITOR_NEW = re.compile(r"\bappoint\w*\b.{0,120}\bauditors?\b|\bauditors?\b.{0,80}\b(?:appointed|appointment)\b|\bin place of\b|"
                          r"casual vacancy.{0,80}\b(?:fill|appoint)", re.I | re.S)
_AUDITOR_CLEAR = re.compile(r"\bno (?:other )?(?:material )?(?:concerns?|issues?|reasons?)\b|\b(?:has|have|had) not raised any\b|"
                            r"\bnot raised any (?:concerns?|issues?)\b|\bno concerns? (?:or issues? )?(?:was|were|has been|have been) raised\b", re.I)


def auditor_update(x: dict) -> tuple[str, str]:
    """(the event, its context) of an auditor's resignation as its filing states it (m2): which auditor when the filing's subject or text
    names the kind, and, only where those words say so, that a new auditor was appointed and that no concerns were raised. Fixed patterns
    over the stored filing; nothing is said that the filing doesn't."""
    words = f"{x.get('subject') or ''} {x.get('text') or ''}"
    kind = _AUDITOR_KIND.search(words)
    fact = f"Resignation of the {kind.group(1).lower()} auditor" if kind else "Resignation of an auditor"
    ctx = []
    if _AUDITOR_NEW.search(words):
        ctx.append("a new auditor was appointed")
    if _AUDITOR_CLEAR.search(words):
        ctx.append("the auditor raised no concerns")
    return fact, ("The filing says " + " and that ".join(ctx) + ".") if ctx else ""


def watch_list(v: dict, today: date) -> list[dict]:
    """"Dated company updates" (m2, the outside review of the live R32 decks; "Worth a watch" before: the owner, 7 Nov: a list only,
    rule-based; no view of what to do). Each row is one event as a neutral fact (`fact`), its exact day (`at`), whether it is scheduled or
    already announced or filed (`status`), where it is from (`source`, with the filing's `url` when held), what the source adds that a reader needs (`context`, "" when it
    adds nothing) and the slide it is on (`ref`): results filed but not yet in the figures, an auditor's resignation, a promoter stake
    move of a point or more, results scheduled in the next week, and an operating figure a quarter or more above or below a year before
    (not held). An entry with no day is not a dated update: a net margin above the EBITDA margin stays on the data-confidence page. No
    word says whether an event is good or bad."""
    sec = v.get("sections") or {}
    own, ev, q = sec.get("ownership") or {}, sec.get("events") or {}, sec.get("quarter") or {}
    out = []
    for x in q.get("earlier") or []:
        if x.get("filed_unread"):
            out.append({"name": x["name"], "fact": f"Quarterly results; the figures in this deck are still {x.get('of') or 'an earlier quarter'}",
                        "at": x["filed_unread"], "status": "Announced", "source": "Results filing", "ref": "The latest quarter"})
    for x in own.get("red_flags") or []:
        if "auditor" in str(x.get("label")).lower():
            fact, ctx = auditor_update(x)
            out.append({"name": x["name"], "fact": fact, "context": ctx, "at": x.get("at"), "status": "Announced", "source": "Exchange filing",
                        "url": x.get("url"), "ref": "Events"})
    for x in own.get("holdings") or []:
        if changed(x.get("promoter_change"), 1.0):
            out.append({"name": x["name"], "fact": f"Promoters' stake {_pts(x['promoter_change'])} to {_pc(x.get('promoter'))} in the quarter to {_month(x.get('quarter'))}",
                        "at": x.get("quarter"), "status": "Filed", "source": "Shareholding filing", "ref": "Ownership"})
    soon = (today + timedelta(days=7)).isoformat()
    for x in ev.get("results_due") or []:
        if str(x.get("date")) <= soon:
            # a day still ahead is scheduled; one already past, with no results stored for it, was the scheduled day (never "announced")
            ahead = str(x.get("date"))[:10] >= today.isoformat()
            out.append({"name": x["name"], "fact": results_purpose(x.get("purpose")), "at": x.get("date"),
                        "status": "Scheduled" if ahead else "Was scheduled", "context": "" if ahead else "No results for it are in this deck yet.",
                        "source": "Results calendar", "ref": "Events"})
    biz = v.get("business") or {}
    for g in (biz.get("layers") or []) + (biz.get("subs") or []):
        for r in g.get("rows") or []:
            if r.get("held") or biz_stale(r, today) or any(o["name"] == r["name"] and o["ref"] == "Operating" for o in out):
                continue
            if changed(r.get("change_year"), 25.0) and "%" not in (r.get("unit") or "") and r.get("filed"):
                out.append({"name": r["name"], "fact": f"{r.get('metric') or 'Operating figure'} {_bizchg(r['change_year'], r.get('unit'))} on a year before "
                                                         f"({_period(r.get('period'), r.get('span') or 'month')})", "at": r.get("filed"),
                            "status": "Filed", "source": "Operating update", "url": r.get("url"), "ref": "Operating"})
    seen, uniq = set(), []
    for x in out:
        k = (x["name"], x["fact"])
        if k not in seen and x.get("at"):
            seen.add(k)
            uniq.append(x)
    return uniq[:WATCH_MAX]


def results_purpose(purpose) -> str:
    """What a scheduled results day is for, as the calendar states it: "Financial results", or "Financial results; other business matters"
    (the calendar's own "Financial Results/Other business matters", in sentence case; an acronym keeps its capitals)."""
    parts = [p.strip() for p in re.split(r"\s*/\s*|\s*;\s*", str(purpose or "")) if p.strip()]
    said = "; ".join(" ".join(w.lower() if w.istitle() else w for w in p.split()) for p in parts)
    if not re.search(r"result", said, re.I):
        said = f"financial results; {said}" if said else "financial results"
    return said[:1].upper() + said[1:]


WATCH_MAX = 16
VERIFIED_SHOWN = 3         # R46: verified figures named on the data-confidence page; every one is on the source page


SOURCES_TITLE = "Figure sources"        # R46: the appendix page of every checked figure's source record


def source_words(src: dict | None, page: bool = True) -> str:
    """R46: a figure's source as its record holds it: the document, the period, (with `page`) the stored page it was read from and the day it was
    built; "source not stored" when the record has none (never a document made up)."""
    if not src:
        return "source not stored"
    bits = [src.get("document") or "document not stored", src.get("period") or "period not stored"]
    if src.get("filed"):
        bits[0] += f", filed {_day(src['filed'])}"
    if page and src.get("page"):
        bits.append(f"page {src['page']}" + (f", built {_day(src['built'])}" if src.get("built") else ""))
    return "; ".join(bits)


def bare(v) -> str:
    """R46: an amount in the unit a source record states once ("1,000", "−16,280", "2.5"), with the real minus."""
    x = f"{abs(v):,.1f}" if abs(v) < 10 else f"{abs(v):,.0f}"
    return (MINUS if v < 0 and float(x.replace(",", "")) != 0 else "") + x


def line_words(lines: list[dict] | None, unit) -> str:
    """R46: a figure's statement lines as stored, the unit said once and each line with its value ("₹ crore: revenue 511; net profit 316; tax
    rate not stored"), for a reader to work the figure out again."""
    from .intel.theme_data import gpts
    said = "; ".join(f"{x['line'].replace(' (EBITDA)', '')} " + ("not stored" if x.get("value") is None else gpts(x["value"]) if x.get("pct") else bare(x["value"]))
                     for x in lines or [])
    return f"{unit}: {said}" if said and unit else said


def shown_words(x: dict) -> str:
    """R46: what a checked figure's stored lines show, from its record, in the record's unit: net profit over revenue, and for a net margin above
    the EBITDA margin the gap with each stored line that covers it, or the lines not stored; the checks that flagged it otherwise. No cause
    beyond the lines."""
    from .intel.theme_data import pts
    got = {ln["key"]: ln.get("value") for ln in x.get("lines") or []}
    s_, p_ = got.get("sales"), got.get("profit")
    out = []
    br = x.get("bridge")
    if x.get("key") == "net" and s_ and s_ > 0 and p_ is not None and not br:
        out.append(f"net profit over revenue: {pts(p_ / s_ * 100)}")
    if br:
        lifts = [f"{LIFT_SHORT[i['key']]} {bare(i['value'])}" for i in br.get("items") or []]
        if br.get("gap") is not None and br["gap"] <= 0:
            out.append("at or below the year's operating profit")
        else:
            gap = f"above EBITDA by {bare(br['gap'])}" if br.get("gap") is not None else "above EBITDA"
            if x.get("state") == "verified_extreme":
                out.append(f"{gap}: covered by " + ", ".join(lifts))
            else:
                out.append(gap + (f"; {', '.join(lifts)} cover{'s' if len(lifts) == 1 else ''} part" if lifts else ""))
                from .intel.theme_data import missing_said
                out.append(missing_said(br) or "the stored lines don't cover it")       # ex49: which line is still missing, and why
    elif x.get("key") == "net" and x.get("state") == "verified_extreme":
        said = {(x.get("sign") or {}).get("why"), (x.get("sign_page") or {}).get("why")}
        out += [p for p in str(x.get("why") or "").split("; ")[1:] if p and p not in said]           # e.g. "at or below its 81.7% EBITDA margin"
    elif x.get("state") != "verified_extreme" or not out:
        out.append(", ".join(x.get("checks") or []) or STATE_WORDS.get(x.get("state"), ""))
    out += sign_words(x)
    return "; ".join(o for o in out if o)


def sign_words(x: dict) -> list[str]:
    """R48: what the year's stored lines show of a sign check, short, for the source page: the EBIT and the capital employed a negative ROCE
    is set against (and which explanation they give, or that they don't reconcile), and the year the page's own net margin is of."""
    from .intel.theme_data import pts
    out = []
    sg = x.get("sign")
    if sg:
        ce, eb = sg.get("capital") or {}, sg.get("ebit")
        cap = f"capital employed {bare(ce['value'])} (equity {bare(ce['equity'])}, debt {bare(ce['debt'])})" if ce else ""
        ebit = f"EBIT {bare(eb)} ({sg.get('ebit_how')})" if eb is not None else ""
        roce = pts(sg["roce"]) if sg.get("roce") is not None else "the ROCE"
        out.append({"negative_capital": f"{cap}: ROCE {roce} on negative capital",
                    "operating_loss": f"{ebit}: an operating loss, as ROCE {roce} says",
                    "other_year": f"{ebit} on {cap}" + (f", {pts(eb / ce['value'] * 100)}" if ce and eb is not None and ce.get("value") else "")
                                  + f"; ROCE {roce} not of the year (another year a loss)",
                    "lines_disagree": f"{ebit} on {cap}" + (f", {pts(eb / ce['value'] * 100)}" if ce and eb is not None and ce.get("value") else "")
                                      + f": ROCE {roce} not reconciled",
                    }.get(sg.get("kind"), f"ROCE {roce} beside a net profit: no EBIT or book value stored to reconcile them"))
    sp = x.get("sign_page")
    if sp:
        out.append(f"the page's own net margin is {sp['year']}'s" if sp.get("ok") else "the page's own net margin: no stored year gives it")
    return out


LIFT_SHORT = {"other_income": "other income", "before_tax": "items before tax", "tax_credit": "a tax credit", "after_tax": "items after tax"}


def verified_words(x: dict) -> str:
    """R46: one verified figure as the data-confidence page names it, enough to work it out again: the company, the figure, the year's net profit
    over its revenue (or the reason it is kept), the stored lines that cover a net margin above the EBITDA margin, and the source document."""
    from .intel.theme_data import amount
    parts = [p for p in str(x.get("why") or "").split("; ") if p]
    br, unit = x.get("bridge"), (x.get("source") or {}).get("unit")
    if br and br.get("gap") is not None and br["gap"] > 0 and br.get("items"):
        extra = [f"above EBITDA by {amount(br['gap'], unit)}: " + " and ".join(f"{LIFT_SHORT[i['key']]} {amount(i['value'], unit)}" for i in br["items"])]
    elif br and br.get("gap") is not None and br["gap"] <= 0:
        extra = ["at or below the year's operating profit"]
    else:
        extra = parts[1:]
    doc = (x.get("source") or {}).get("document") or "source not stored"
    return f"{x['name']}, {HELD_WORDS.get(x['key'], x['key'])} {_pc(x['value'])} (" + "; ".join(parts[:1] + extra + [doc]) + ")"


def only_arithmetic(x: dict) -> bool:
    """rv51 (R51, the outside review of the live Release 49 decks: "verified" must mean the calculation, accounting basis and supporting
    statement lines were checked): a kept figure whose check only worked its arithmetic out again (net profit over revenue), or whose
    accounting basis (consolidated or standalone) the stored page doesn't hold."""
    doc = str((x.get("source") or {}).get("document") or "")
    return x.get("state") == "verified_extreme" and (x.get("checked") == "arithmetic" or not doc or "consolidated or standalone is not stored" in doc)


def state_word(x: dict) -> str:
    """A checked figure's state as a deck says it (STATE_WORDS); rv51: "arithmetic reproduced" for one only_arithmetic."""
    return "arithmetic reproduced" if only_arithmetic(x) else STATE_WORDS.get(x.get("state"), "–")


def verified_row(vf: list[dict], short: bool = False) -> list[str]:
    """R46 (the outside review of the live R45 decks): the data-confidence page's "Verified figures": each named with what works it out again and
    its source document, every one with its stored page and lines on the appendix's source page; `short`, names only, for a page whose checks
    don't fit otherwise (no check is ever cut off the page). rv51 (R51): those whose calculation, accounting basis and statement lines were
    checked ("verified") apart from those whose arithmetic alone was worked out again ("arithmetic reproduced"), each with its period and the
    lines used (verified_words)."""
    full, arith = [x for x in vf if not only_arithmetic(x)], [x for x in vf if only_arithmetic(x)]
    shown = (full + arith)[:VERIFIED_SHOWN]
    said = "; ".join(x["name"] if short else verified_words(x) for x in shown) + (f"; and {len(vf) - VERIFIED_SHOWN} more" if len(vf) > VERIFIED_SHOWN else "")
    who = "Its" if len(vf) == 1 else "Each one's"
    if not arith:
        head = f"{_n(len(vf), 'unusual figure')} verified against {'its' if len(vf) == 1 else 'their'} own filed figures"
    elif not full:
        head = f"{_n(len(vf), 'unusual figure')}, arithmetic reproduced (net profit over revenue worked out again, nothing more checked)"
    else:
        head = f"{_n(len(vf), 'unusual figure')} checked: {len(full)} verified against their own filed figures, {len(arith)} arithmetic reproduced only"
    return ["Verified figures", f"{head}: {said}. {who} document, stored page and lines: ⟦{SOURCES_TITLE}⟧.", "Kept in every median and ranking."]


def gap_reasons(xs: list[dict]) -> str:
    """R46: why the stored lines don't explain each net margin above the EBITDA margin, counted by reason: the page built before profit before
    tax and tax were kept, a line the source gives none for, or lines that don't cover the gap."""
    from .intel.theme_data import LINE_WORDS
    old, gone, short = [], {}, []
    for x in xs:
        br = x.get("bridge") or {}
        if not br:
            continue
        if {"pbt", "tax_pct"} & set(br.get("unkept") or []):
            old.append(x)
        elif br.get("missing"):
            gone.setdefault(" or ".join(LINE_WORDS[k] for k in br["missing"]), []).append(x)
        else:
            short.append(x)
    # ex49 (R48): each company named with the lines it still needs (the stored page built before they were kept: read again once rebuilt)
    each = lambda g: "; ".join(f"{clean_name(x.get('name') or x.get('symbol') or '')}: {', '.join(LINE_WORDS[k] for k in (x.get('bridge') or {}).get('missing') or [])}"
                               for x in g[:6]) + (f"; and {len(g) - 6} more" if len(g) > 6 else "")      # noqa: E731
    bits = ([f"{_n(len(old), 'company', 'companies')} whose stored page holds no profit before tax or tax rate (built before these lines were kept; "
             f"read again once rebuilt), each still missing: {each(old)}"] if old else []) + \
        [f"{_n(len(g), 'company', 'companies')} with no {k} stored for the year ({each(g)})" for k, g in gone.items()] + (
            [f"{_n(len(short), 'company', 'companies')} whose stored lines don't cover the gap"] if short else [])
    return "; ".join(bits)


PARENTS_LABEL = "Parent and listed subsidiary"


def parents_row(v: dict) -> list[str] | None:
    """gl50 (R50, the rotating review of the live Cement deck: Grasim, whose whole-company figures consolidate UltraTech, and UltraTech both
    added into revenue totals): each pair of a parent and its listed subsidiary in the theme (theme_data.parents_of: the subsidiary's stored
    shareholding filing names the parent among its promoters with more than half its shares), and what the deck does: the subsidiary's revenue
    is left out of every total that adds the parent's (a layer's revenue, the theme's revenue and margins together); a figure of the two in
    different layers, and each one's market value and share of it, are each company's own, so the parent's includes its stake. None when the
    stored filings show none (a US theme: none is read)."""
    ps = [p for p in v.get("parents") or [] if isinstance(p, dict)]
    if not ps:
        if v.get("region") == "US":
            return [PARENTS_LABEL, "No shareholding filing is read for US companies, so a parent and its listed subsidiary are not detected; "
                                   "a total that adds both would count the subsidiary twice.", "Not checked."]
        return None
    each = "; ".join(f"{clean_name(p['name'])} is {p['pct']:g}% held by {clean_name(p['parent_name'])} (promoter, {p['quarter']} filing)"
                     + (", whose figures are its consolidated ones" if p.get("basis") == "consolidated" else ", whose figures are the whole company's"
                        if p.get("parent_wide") else "") for p in ps)
    return [PARENTS_LABEL, f"{each}.", "The subsidiary's revenue is left out of every total that adds the parent's; market values and their "
                                      "shares are each company's own, so the parent's includes its stake."]


def without_words(v: dict) -> list[str]:
    """d53: the confirmed companies with figures whose own words are not shown (no description in their own words is kept), by name."""
    out = []
    for x in v.get("layers") or []:
        for c in x.get("companies") or []:
            if c.get("status") != "unverified" and (c.get("revenue") is not None or c.get("profit") is not None) and not c.get("what"):
                out.append(clean_name(c.get("name") or c.get("symbol") or ""))
    return list(dict.fromkeys(out))


def wordless_said(names_: list) -> str:
    shown = ", ".join(names_[:5]) + (f" and {len(names_) - 5} more" if len(names_) > 5 else "")
    return f"{_n(len(names_), 'company', 'companies')} with figures have no description in their own words yet: {shown}."


PARTIAL_SHARE = 50          # d53: a theme whose checked companies are under this share of its list has a partial map, said wherever the map is


def partial_map(v: dict, cov: dict) -> str:
    """d53 (R53, the owner's review of the live R52 Biotech deck: 821 companies, 100 checked, 583 unread, while the deck read as a whole map):
    the sentence that says the map is partial when the companies checked are under PARTIAL_SHARE% of the theme's list, else ""."""
    mem = v.get("membership") or {}
    total = int(cov.get("total") or 0)
    # not checked: those whose membership was never checked, or those placed in "Other" because no word of theirs was read (d1 "unread")
    unread = len({mb["symbol"] for mb in v.get("members") or [] if mb.get("symbol") and mb.get("unread")})
    gone = max(total - int(mem.get("placed") or total), unread)
    n = total - gone
    if not total or n * 100 >= PARTIAL_SHARE * total:
        return ""
    return (f"A partial map: {n:,} of the theme's {total:,} companies were checked ({round(n * 100 / total)}%); {gone:,} are not checked yet, "
            "so the layers, medians and rankings are of the checked companies only.")


def adjacent_row(v: dict) -> list[str]:
    """d53 (R53, the owner's review: hospital operators in the Medical devices deck, device makers in the Hospitals deck): the adjacent
    participants, those whose principal business is of another kind than the theme's core members', by kind and name."""
    by: dict = {}
    for x in v.get("adjacent") or []:
        by.setdefault(x["kind"], []).append(clean_name(x["name"]))
    said = "; ".join(f"{k} {len(ns)} ({', '.join(ns[:4])}{f' and {len(ns) - 4} more' if len(ns) > 4 else ''})" for k, ns in by.items())
    return ["Core and adjacent", f"The theme's core members are {v.get('core_kind') or 'its own industry'}; {_n(sum(len(x) for x in by.values()), 'company', 'companies')} "
            f"whose principal business is another kind are adjacent participants: {said}.",
            "Shown, with their layer, as adjacent; in no total, median or ranking of the theme."]


def confidence_rows(v: dict, cov: dict, today: date, lender: bool = False) -> list[list[str]]:
    """The data-confidence page (the owner, 7 Nov): each check the figures went through, what it found and what the deck does about it."""
    ch = v.get("checks") or {}
    sec = v.get("sections") or {}
    val = sec.get("valuation") or {}
    rows = []                      # coverage: the table of counts under the checks (coverage_rows)
    names = lambda xs, k=4: ", ".join(x["name"] for x in xs[:k]) + (f" and {len(xs) - k} more" if len(xs) > k else "")  # noqa: E731
    if (v.get("membership") or {}).get("placed"):
        rows.append(["Universe", membership_words(v, cov["total"]) + ".", "Only confirmed companies count in a median or total."])
    par = parents_row(v)
    if par:
        rows.append(par)
    wordless = without_words(v)
    if ch.get("unverified"):
        rows.append(["Membership", f"{_n(len(ch['unverified']), 'company', 'companies')} with figures whose own words describe other work: {names(ch['unverified'])}."
                     + (f" {wordless_said(wordless)}" if wordless else ""), "Listed as not confirmed; left out of every median and total."])
    elif wordless:
        # d53 (R53, LIVE8A-004: "Every company with figures has words of its own ... Nothing held back" beside AMD, Intel, KLA and more with "No
        # description in its own words yet"): the real count of companies with figures and no words of their own, never a claim of every one
        rows.append(["Membership", wordless_said(wordless), "Kept in the figures by their official industry; nothing in their own words was checked."])
    else:
        rows.append(["Membership", "Every company with figures has words of its own, or a checked quote, that show the theme's work.", "Nothing held back."])
    part = partial_map(v, cov)
    if part:
        rows.append(["Partial map", part, "Every claim about the map is of its checked companies; the rest are listed, not placed."])
    if v.get("duplicates"):        # d53: one company under two symbols, kept once
        ds = v["duplicates"]
        rows.append(["Same company twice", f"{_n(len(ds), 'company', 'companies')} listed under two symbols with the same latest year, revenue and net profit: "
                     + "; ".join(f"{clean_name(x['name'])} is {clean_name(x['kept_name'])}" for x in ds[:4]) + (f"; and {len(ds) - 4} more" if len(ds) > 4 else "") + ".",
                     "Kept once, under the symbol with a market value, before any median, total or list."])
    if v.get("adjacent"):          # d53: adjacent participants apart from the theme's core members
        rows.append(adjacent_row(v))
    if v.get("developers"):        # d53: companies spending ahead of their revenue, apart from the margin medians
        rows.append(["Spending ahead of revenue", f"{_n(v['developers'], 'company', 'companies')} whose costs are over twice their revenue (EBITDA margin below −100%), "
                     "pre-revenue or early-stage.", "Their margins are shown on their rows, verified, and left out of every margin median and range."])
    if ch.get("verified"):         # R44: an unusual figure its own filed figures give: kept, and said so with the count
        rows.append(verified_row(ch["verified"]))
    if ch.get("one_off"):
        above = all(x.get("net") is not None and x.get("ebitda") is not None and x["net"] > x["ebitda"] for x in ch["one_off"])
        oo = ", ".join(f"{x['name']} ({_pc(x['net'])} net, {_pc(x['ebitda']).replace('.0%', '%')} EBITDA)" if x.get("ebitda") is not None and x.get("net") is not None
                       and x["net"] > x["ebitda"] else f"{x['name']} ({_pc(x['net'])} net: {x.get('why') or 'not reconciled'})" for x in ch["one_off"][:4]) \
            + (f" and {len(ch['one_off']) - 4} more" if len(ch["one_off"]) > 4 else "")
        with_, without = ch.get("net_with"), ch.get("net_without")
        moved = with_ is not None and without is not None and _pc(with_) != _pc(without)      # said only when leaving them out changes it (R18)
        rows.append(["Net above EBITDA margin" if above else "Net margin not reconciled",
                     # R46: why the stored lines don't explain it, counted by reason, never "no stored figure" where a line is stored
                     (f"Net margin above the EBITDA margin at {_n(len(ch['one_off']), 'company', 'companies')}, that the year's stored lines don't cover: {oo}."
                      if above else f"{_n(len(ch['one_off']), 'net margin')} unusual and not reconciled with the company's own filed figures: {oo}.")
                     + (f" {gap_reasons(ch['one_off'])[:1].upper()}{gap_reasons(ch['one_off'])[1:]}." if gap_reasons(ch["one_off"]) else "")
                     + f" Each one's lines: ⟦{SOURCES_TITLE}⟧.",
                     # m2: the flag has no day, so it is here and not among the dated updates; no cause is named (ANOMALY_WHY, R27)
                     "Marked † and left out of net-margin medians" + (f": the median net margin is {_pc(without)} without them, {_pc(with_)} with them" if moved else "")
                     + f"; {ANOMALY_WHY}."])
    if ch.get("held"):             # R30: a figure that failed a check: named with the check and its state (R44), never a cause
        hd = ch["held"]
        said = "; ".join(f"{x['name']}, {HELD_WORDS.get(x['key'], x['key'])} {_pc(x['value']) if x['key'] != 'pb' else str(x['value']) + 'x'} "
                         f"({STATE_WORDS.get(x.get('state'), 'invalid')}: {', '.join(x['checks'])})" for x in hd[:4]) + (f"; and {len(hd) - 4} more" if len(hd) > 4 else "")
        # R48: each one's source record and statement lines on the appendix's source page, as every other checked figure's
        rows.append(["Figure checks", f"{_n(len(hd), 'figure')} failed a check: {said}. " + ("Its" if len(hd) == 1 else "Each one's") + f" source and lines: ⟦{SOURCES_TITLE}⟧.",
                     f"Shown as –; left out of every median and ranking ({ANOMALY_WHY})."])
    for x in cohort_words(ch.get("cohort")):          # q1: a layer's count in its calculations fell against the run before
        rows.append(["Since the run before", x, "The layer's figures are of the companies in its calculations now; each one that left is named with "
                     "its reason."])
    if ch.get("series"):
        rows.append(["Broken series", f"{_n(len(ch['series']), 'company', 'companies')} whose years don't make one series (a merger, demerger or new listing): {names(ch['series'])}.",
                     "Growth figures not worked out for them; left out of growth totals."])
    q = sec.get("quarter") or {}
    if q.get("quarter"):
        late = [x for x in q.get("earlier") or [] if x.get("filed_unread")]
        if q.get("earlier"):
            rows.append(["One quarter", f"The quarter's median is of {_n(len(q.get('companies') or []), 'company', 'companies')} reporting {q['quarter']}; "
                         f"{len(q['earlier'])} still on an earlier quarter" + (f", {len(late)} with newer results filed: {names(late)}" if late else "") + ".",
                         "Earlier quarters listed apart, not in the median."])
        else:
            rows.append(["One quarter", f"Every company's latest quarter is {q['quarter']}.", "One quarter in the median."])
    biz = v.get("business") or {}
    held = biz.get("held") or []
    if held:
        rows.append(["Operating figures", f"{_n(len(held), 'figure')} held for checking: " + "; ".join(f"{x['name']} ({x['why']})" for x in held[:3]) + ".",
                     "The compared figure and its change are not shown; after a move too large to take as filed, neither comparison is."])
    filed = {r["symbol"]: r["name"] for g in (biz.get("layers") or []) + (biz.get("subs") or []) for r in g.get("rows") or []}
    if 0 < len(filed) < MIN_BASE:
        rows.append(["Operating figures filed", f"{_n(len(filed), 'company', 'companies')} filed operating figures between results: {', '.join(filed.values())}.",
                     "Too few to set side by side: no page of their own."])
    old = [r for g in (biz.get("layers") or []) for r in g.get("rows") or [] if biz_stale(r, today)]
    if old:
        rows.append(["Old operating figures", f"{_n(len(old), 'figure')} for a period that ended months ago: " + ", ".join(f"{r['name']} ({_period(r.get('period'), r.get('span') or 'month')})" for r in old[:4]) + ".",
                     "Marked (old) in red."])
    fxs = ch.get("currency") or []
    if fxs:                        # R22: every money figure in one currency, the rates said
        done = [x for x in fxs if x.get("rate")]
        none = [x for x in fxs if not x.get("rate")]
        home = "US dollars" if v.get("region") == "US" else "rupees"
        said = "; ".join(f"{x['name']} reports in {x['currency']}, converted at {fx_words(x['currency'], x['rate'], v.get('region'))}"
                         + (f" (rate of {_day(x['at'])})" if x.get("at") else "") for x in done[:4]) + (f"; and {len(done) - 4} more" if len(done) > 4 else "")
        rows.append(["Currency", (said + "." if done else "") + (f" No rate for {names5(none)}: their revenue and other money figures are left out." if none else ""),
                     f"Every money figure in {home}; the app keeps today's rate, not each period's, so a year's figures use it too. Margins, growth and returns "
                     "don't depend on the currency."])
    if mostly_whole(ch.get("whole_points"), ch.get("with_ebitda")):          # LIVE7A-009: most of them, not only every one
        filed = ("EBITDA margins are filed in whole points." if ch.get("whole_points") == ch.get("with_ebitda") else
                 f"{ch.get('whole_points')} of the {ch.get('with_ebitda')} EBITDA margins are filed in whole points.")
        rows.append(["Precision", filed, "Printed as filed; medians and gaps built on them are printed in whole points; a gap of a point or less "
                     "between medians is not called a difference."])
    n = ch.get("n") or {}
    keys = (("ebitda", "EBITDA margin"), ("net", "net margin"), ("roce", "ROCE")) + ((("roe", "ROE"),) if ch.get("lenders") else ())
    counts = ", ".join(f"{label} {n[k]}" for k, label in keys if n.get(k))
    rows.append(["Bases and counts", ("P/E is on the last four quarters, P/B on the latest book value, margins and returns on the latest full year." if lender else
                                      "P/E is on the last four quarters, EV/EBITDA and margins on the latest full year.")
                 + (f" Medians are of: {counts} companies." if counts else "") + (f" {_n(val['losses'], 'loss-maker')} with no P/E." if val.get("losses") else ""),
                 "Each slide says its period and count."])
    return rows


def cohort_words(drops) -> list[str]:
    """Each layer whose count in its calculations fell against the run before (theme_data.cohort_drops, q1), in one sentence: the two counts,
    the run's day, and every company that left with its reason."""
    out = []
    for x in drops or []:
        if not isinstance(x, dict) or not x.get("layer"):
            continue
        left = x.get("left") or []
        named = "; ".join(f"{clean_name(str(c.get('name') or c.get('symbol')))} ({c.get('why') or 'reason not kept'})" for c in left[:8])
        more = f"; and {len(left) - 8} more" if len(left) > 8 else ""
        on = f" at the run of {_day(x['on'])}" if x.get("on") else " at the run before"
        out.append(f"{x['layer']}: {x['from']} in its calculations{on}, {x['to']} now" + (f"; left: {named}{more}." if left else "."))
    return out


HELD_WORDS = {"net": "net margin", "ebitda": "EBITDA margin", "roe": "return on equity", "pb": "price to book", "roce": "ROCE"}
STATE_WORDS = {"verified_extreme": "verified", "unverified_extreme": "not reconciled", "invalid": "invalid"}      # R44: theme_data's states
COVERAGE_HEAD = ["Coverage", "Covered", "Of what"]
COVERAGE_KINDS = ("Companies, by count", "Market value", "Each figure", "Each layer", "Partly read", "Not in the sources", "In informative layers",
                  "Screened out: another business", "From other industries", "Screening", "Coverage flag", "Moved by what its layer is",
                  "Since the previous version")
# R31 (the owner's review of the live R30 Insurance and Real estate decks): the model-specific figures the app's sources don't hold, and why,
# by business-model family (theme_check.MODELS); said once, on the coverage table (an insurer's, when the sector table doesn't say it)
NOT_IN_SOURCES = {
    "development": ("Property developers", "pre-sales (bookings), collections and land bank aren't elements of the annual or quarterly results "
                                           "formats the app reads"),
    "property": ("Property and leasing", "occupancy, leased area and rent per square foot aren't elements of the annual or quarterly results "
                                         "formats the app reads"),
    "insurer": ("Insurers", "VNB, APE and embedded value aren't elements of the insurance results formats"),
}
INSURER_FAMILIES = ("underwriting", "life_insurance", "general_insurance", "reinsurance")
# R31: the figures whose reads the coverage table counts as partial: (label, the company row's key)
PARTIAL_FIGURES = (("EBITDA margin", "ebitda"), ("net margin", "net"), ("revenue growth", "sales_1y"), ("latest quarter", "quarter"))


def _partial(row: dict) -> bool:
    """Whether a company's stored years were read only in part (R31): a year with no revenue, a non-lender's year with no margin, a gap
    between years, or a part year as its latest."""
    from .intel.theme_data import _next_year
    ys = [y for y in row.get("years") or [] if isinstance(y, dict)]
    if not ys:
        return False
    if any(y.get("sales") is None or (not row.get("bank") and y.get("opm") is None) for y in ys):
        return True
    if any(not _next_year(str(a.get("year")), str(b.get("year"))) for a, b in zip(ys, ys[1:])):
        return True
    return bool(re.search(r"\s\d+m$", str(row.get("year") or "")))


def partial_line(v: dict) -> str:
    """Each figure read for N of M confirmed companies with figures, and K of the missing whose stored years were read only in part (R31:
    a figure missing because the reading was partial is said so); "" when no figure is missing for that reason."""
    cos = {c.get("symbol"): c for b in v.get("layers") or [] for c in b.get("companies") or []
           if c.get("status") != "unverified" and (c.get("revenue") is not None or c.get("profit") is not None)}
    m = len(cos)
    out = []
    for label, k in PARTIAL_FIGURES:
        have = sum(1 for c in cos.values() if c.get(k) is not None)
        part = sum(1 for c in cos.values() if c.get(k) is None and _partial(c))
        if part:
            out.append(f"{label} read for {have:,} of {m:,}; {part:,} partial")
    return " · ".join(out)


def not_in_sources(v: dict) -> str:
    """The model-specific figures the app's sources don't hold for the deck's business models, and why (R31), once each; an insurer's only when
    no sector table says it already."""
    fams = {(b.get("model") or {}).get("family") for b in v.get("layers") or [] if isinstance(b.get("model"), dict)}
    fams |= {"insurer" for b in v.get("layers") or [] for c in b.get("companies") or [] if c.get("profile") == "insurer"}
    fams |= {"insurer" for f_ in fams & set(INSURER_FAMILIES)}
    said = ((v.get("sections") or {}).get("sector") or {}).get("families") or {}
    out = []
    for k, (who, why) in NOT_IN_SOURCES.items():
        if k in fams and not (k == "insurer" and (said.get("insurer") or {}).get("not_filed")):
            out.append(f"{who}: {why}")
    return "; ".join(out) + "." if out else ""


def coverage_table(v: dict, cov: dict) -> list[list[str]]:
    """R30 (the owner's review: "97% of market value" read as companies): coverage in one compact table on the data-confidence page, each
    kind on its own row: (a) companies by count, (b) market value (a share of value, never of companies), (c) each figure's count, (d) each
    layer's companies with figures against those it lists."""
    total, n = cov.get("total") or 0, v.get("members_with_figures") if v.get("members_with_figures") is not None else cov.get("n") or 0
    rows = [screening_row(v, cov), [COVERAGE_KINDS[0], f"{n:,} of {total:,}", "companies: confirmed, with figures, of every company the deck lists"]]
    if cov.get("share") is not None:
        rows.append([COVERAGE_KINDS[1], f"{cov['share']}%", f"of {cov['of_what']}, held by the companies with figures (a share of value, not of companies)"])
    each = next((r[2] for r in coverage_rows(v, cov) if r[0] == "In each median and total"), "")
    if each:
        rows.append([COVERAGE_KINDS[2], "", each])
    lay = []
    for b in v.get("layers") or []:
        cos = [c for c in b.get("companies") or [] if c.get("status") != "unverified"]
        if cos:
            lay.append(f"{b.get('layer')} {sum(1 for c in cos if c.get('revenue') is not None or c.get('profit') is not None)} of {len(cos)}")
    if lay:
        rows.append([COVERAGE_KINDS[3], "", "companies with figures: " + " · ".join(lay)])
    part = partial_line(v)
    if part:                       # R31: a figure missing because its years or quarters were read only in part
        rows.append([COVERAGE_KINDS[4], "", part])
    gone = not_in_sources(v)
    if gone:                       # R31: model-specific figures the sources don't hold, and why
        rows.append([COVERAGE_KINDS[5], "", gone])
    c = v.get("coverage") or {}
    # R44: the map's one count (theme_routes.map_coverage), as the dive says it; a view kept before it, from its members (rest_count)
    rest = (c["other"], c["placed"], c.get("other_name") or "", c.get("unread") or 0) if c.get("other") and c.get("placed") else rest_count(v)
    if rest:                       # R44: how many of the companies placed are in a layer the map names, said once; then "Other" (R40, d1)
        inf = rest[1] - rest[0]
        rows.append([COVERAGE_KINDS[6], f"{inf:,} of {rest[1]:,} ({informative_share(inf, rest[1])}%)", rest_words(rest, v)])
    elif c.get("placed"):          # R44: no "Other" group: every company placed is in a layer the map names
        rows.append([COVERAGE_KINDS[6], f"{c['placed']:,} of {c['placed']:,} (100%)", "every company in a layer the map names"])
    from .intel.theme_changes import control_line
    flagged = control_line(c)
    if flagged:                    # cl48 (R47): under 60% in informative layers, or 8 points or more fewer than the previous live placement
        rows.append([COVERAGE_KINDS[10], f"{c.get('share')}%", flagged])
    off = off_industry_line(v)
    if off:                        # R40: companies of the theme's industries in another business, left out of the theme
        # tx2 (R46, the outside review of the live R45 Consumer retail and Semiconductors decks): said plainly to be screened-out candidates
        rows.append([COVERAGE_KINDS[7], str(screened_out(v)), f"{SCREENED_SAID} {off}"])
    n_other, other = other_industry_line(v)
    if other:                      # c1 (R44): companies the map names from other industries, why each is in the theme, apart from its figures
        rows.append([COVERAGE_KINDS[8], str(n_other), other])
    n_moved, moved = refit_line(v)
    if moved:                      # gl50 (R50): companies moved because their words and industry fit neither what their layer is
        rows.append([COVERAGE_KINDS[11], str(n_moved), moved])
    cohort = cohort_row(v)
    if cohort:                     # rv51 (R51): the companies added, removed or moved into "Other" since the previous version, with why
        rows.append(cohort)
    return rows


# rv51 (R51): why a theme's figures were stored again (theme_changes.cause_of), as the cohort row says it
CHANGE_CAUSE = {"rules": "a re-check under new placement rules", "map": "a new AI map", "refresh": "a Refresh",
                "figures": "the companies' own figures moving"}
COHORT_SHOWN = 6


def cohort_row(v: dict) -> list[str] | None:
    """rv51 (R51, the outside review of the live Release 49 decks, P2: a cross-version cohort diff in every deck): the companies with figures
    added, removed or moved into “Other” since the theme's previous stored version, from its change log's latest entry (theme_changes, the
    deck's `changes`), each list with its reason: the cause the theme's figures were stored again and, for one removed, the read's own reason.
    None when the deck carries no log (a view made without it); a log with no entry yet says there is no earlier version to compare."""
    ch = v.get("changes")
    if not isinstance(ch, dict):
        return None
    if not ch.get("entries"):
        # gl52 (R52, the rotating review of Release 51: Cement and Hospitals, each with a deck the day before, said "No earlier stored
        # version"): a log keeps an entry only when something changed; its first version's day (`since`) says one was stored
        if ch.get("since"):
            return [COVERAGE_KINDS[12], "0", f"Against the versions stored since {_day(ch['since'])}: no company with figures added, removed or "
                                              "moved into “Other”."]
        return [COVERAGE_KINDS[12], "–", "No earlier stored version of this theme's figures to compare with."]
    e = ch["entries"][0]
    other = (v.get("coverage") or {}).get("other_name") or ""
    names = lambda xs: ", ".join(clean_name(x.get("name") or x.get("symbol") or "") for x in xs[:COHORT_SHOWN]) + (     # noqa: E731
        f" and {len(xs) - COHORT_SHOWN} more" if len(xs) > COHORT_SHOWN else "")
    why = CHANGE_CAUSE.get(e.get("cause"), "the theme's figures stored again")
    added, removed = list(e.get("added") or []), list(e.get("removed") or [])
    into = [x for x in e.get("moved") or [] if other and x.get("to") == other]
    counts = e.get("counts") or {}
    n_add, n_rem = counts.get("added", len(added)), counts.get("removed", len(removed))
    parts = []
    if n_add:
        # d53 (R53, the owner's review of the live R52 Consumer retail deck: "added 6" with no reason, a propane distributor among them): each
        # addition with why it is in the theme, as the log keeps it
        bywhy_a: dict[str, list] = {}
        for x in added:
            bywhy_a.setdefault(x.get("why") or "", []).append(x)
        parts.append(f"added {n_add}: " + "; ".join(f"{names(xs)}" + (f" ({w})" if w else "") for w, xs in bywhy_a.items()))
    if n_rem:
        bywhy: dict[str, list] = {}
        for x in removed:
            bywhy.setdefault(x.get("why") or "not stated", []).append(x)
        parts.append(f"removed {n_rem}: " + "; ".join(f"{names(xs)} ({w})" for w, xs in bywhy.items()))
    if into:
        parts.append(f"moved into “{other}” {len(into)}: " + ", ".join(f"{clean_name(x.get('name') or x.get('symbol') or '')} (from “{x.get('from')}”)"
                                                                        for x in into[:COHORT_SHOWN]) + (f" and {len(into) - COHORT_SHOWN} more" if len(into) > COHORT_SHOWN else ""))
    # d53 (R53, our deck reviewer: moves between layers and new or lost layers were never logged, Retail's 11 companies out of "Other" and
    # Utilities' 44 re-grouped): every move between two of the map's layers, and every layer renamed, split, merged, added or removed
    between = [x for x in e.get("moved") or [] if not (other and x.get("to") == other)]
    if between:
        parts.append(f"moved between layers {len(between)}: " + ", ".join(f"{clean_name(x.get('name') or x.get('symbol') or '')} (from “{x.get('from')}” to “{x.get('to')}”)"
                                                                          for x in between[:COHORT_SHOWN]) + (f" and {len(between) - COHORT_SHOWN} more" if len(between) > COHORT_SHOWN else ""))
    lay = [x for x in e.get("layers") or [] if isinstance(x, dict) and x.get("kind")]
    if lay:
        said = {"renamed": lambda x: f"“{x['from'][0]}” renamed “{x['to'][0]}”", "split": lambda x: f"“{x['from'][0]}” split into " + ", ".join(f"“{t}”" for t in x["to"]),
                "merged": lambda x: ", ".join(f"“{f}”" for f in x["from"]) + f" merged into “{x['to'][0]}”",
                "removed": lambda x: f"“{x['from'][0]}” removed ({x.get('n', 0)} companies)", "added": lambda x: f"“{x['to'][0]}” added ({x.get('n', 0)} companies)"}
        parts.append(f"layers changed {len(lay)}: " + "; ".join(said[x["kind"]](x) for x in lay[:COHORT_SHOWN] if x["kind"] in said)
                     + (f"; and {len(lay) - COHORT_SHOWN} more" if len(lay) > COHORT_SHOWN else ""))
    day = _day(e.get("d")) if e.get("d") else "its last change"
    if not parts:
        return [COVERAGE_KINDS[12], "0", f"Against the version stored before {day}: no company with figures added, removed or moved into “Other”."]
    return [COVERAGE_KINDS[12], str(n_add + n_rem + len(into) + len(between)), f"On {day}, against the version stored before it, after {why}: " + "; ".join(parts) + "."]


def refit_line(v: dict) -> tuple[int, str]:
    """gl50 (R50, the rotating review: a solar module maker in "Rail rolling stock makers", personal care makers in "Branded packaged foods"):
    each company moved because neither its own words nor its official industry fit what its layer is (theme_base.definition_fit), with the
    layer it was in, where it is now and why: (how many, what is said); (0, "") when none was."""
    out = []
    for b in v.get("layers") or []:
        for c in b.get("companies") or []:
            r = c.get("refit") if isinstance(c.get("refit"), dict) else None
            if r and r.get("why"):
                to = "“Other”" if b.get("basis") == "rest" else f"“{b.get('layer')}”"
                out.append(f"{clean_name(c.get('name') or c.get('symbol') or '')}: from “{r.get('from')}” to {to}, as {r['why']}")
    return len(out), ("; ".join(out) + ".") if out else ""


SCREENED_SAID = ("Candidates screened out, not members of the theme: counted only among the companies considered, in no layer, median or "
                 "total of this deck.")


def screening_row(v: dict, cov: dict) -> list[str]:
    """tx2 (R46, the outside review of the live Release 45 decks: "explicit screening populations in every report"): the theme's screening
    in one row, each population with its count, reconciled (considered = screened out as another business + members): "100 considered = 15
    screened out as another business (candidates, never members) + 85 members · confirmed 85 · with figures 80 · in informative layers 66 ·
    eligible for each metric (confirmed, with the figure): EBITDA margin 75, ...". The counts are the deck's one set (reconciled_counts)."""
    c = reconciled_counts(v, cov)
    members, rejected = c["members"], c["rejected"]
    head = (f"{c['considered']:,} considered = {rejected:,} screened out as another business (candidates, never members) + {members:,} members"
            if rejected else f"{c['considered']:,} considered, none screened out as another business: {members:,} members")
    parts = [head]
    if c.get("confirmed") is not None:
        parts.append(f"confirmed {c['confirmed']:,}" + (f" (of {c['checked']:,} checked)" if c.get("checked") and c["checked"] < members else ""))
    parts.append(f"with figures {c['with_figures']:,}")
    cv = v.get("coverage") or {}
    rest = (cv["other"], cv["placed"]) if cv.get("other") and cv.get("placed") else rest_count(v)
    if rest:
        parts.append(f"in informative layers {rest[1] - rest[0]:,}")
    elif cv.get("placed"):
        parts.append(f"in informative layers {cv['placed']:,}")
    if c["each"]:
        parts.append("eligible for each metric (confirmed, with the figure): " + ", ".join(f"{label} {k:,}" for label, k in c["each"]))
    return [COVERAGE_KINDS[9], f"{c['considered']:,} considered", " · ".join(parts)]


def other_industry_line(v: dict) -> tuple[int, str]:
    """(how many, what is said) of the companies in the theme that the theme's map names from industries other than the theme's own (c1, R44:
    the outside review of the live Release 43 Insurance deck, "say explicitly whether insurance distribution belongs in the theme"): by layer,
    each with why it is in the theme (theme_data.theme_record) and, apart from that, whether it is in its layer's figures (theme_data.
    comparison_said); a layer all of whose companies are of other industries says so. (0, "") when there are none."""
    from .intel.theme_base import plain_industry
    out, n = [], 0
    for b in v.get("layers") or []:
        cos = b.get("companies") or []
        mine = [c for c in cos if isinstance(c.get("theme"), dict) and c["theme"].get("by") == "other_industry"]
        if not mine:
            continue
        n += len(mine)
        groups: dict = {}
        for c in mine:
            said = c.get("comparison") or ""
            why = re.sub(r", from another industry \((?:[^()]|\([^()]*\))*\)", ", from another industry", c["theme"].get("why") or "")
            ind = plain_industry(c.get("map_industry")) if c.get("map_industry") else ""      # each company's industry, by its name
            groups.setdefault((why, said or ""), []).append(clean_name(c.get("name") or c.get("symbol") or "") + (f" ({ind})" if ind else ""))
        head = f"In “{b.get('layer')}”" + (", a layer of the theme's map, all its companies of other industries" if len(mine) == len(cos) else "")
        parts = [f"{', '.join(names)}: membership: {why}" + (f"; comparison: {said}" if said else "") for (why, said), names in groups.items()]
        out.append(f"{head}: " + ". ".join(parts) + ".")
    return n, " ".join(out)


def informative_share(n: int, of: int) -> int:
    """The whole per cent of the companies placed that are in an informative layer (R44), rounded half up as the dive's (theme_data.
    layer_coverage)."""
    return int(n * 100 / of + 0.5) if of else 0


def rest_count(v: dict) -> tuple[int, int, str, int] | None:
    """(companies in the "Other" group, companies placed in the map's layers and "Other", its name, how many of the group were not checked
    yet) (R40, the owner: "50 of 100 companies fit none of the map's layers"; d1, the outside review of the live Release 41 IT and Pharma
    decks: "115 of 252" counted 82 companies never checked as fitting none), each company once; None when the map has no "Other" group.
    Every company is in a layer or in "Other" (theme_base.with_sub_only), so the count is of all of them."""
    placed, rest, name, unread = set(), set(), "", set()
    for mb in v.get("members") or []:
        if not mb.get("symbol"):
            continue
        placed.add(mb["symbol"])
        if mb.get("rest"):
            rest.add(mb["symbol"])
            name = name or mb.get("layer") or ""
            if mb.get("unread"):
                unread.add(mb["symbol"])
    return (len(rest), len(placed), name, len(unread)) if rest and placed else None


def rest_words(rest: tuple, v: dict) -> str:
    """What the "Other" count is (d1): those that fit none of the map's layers apart from those not checked yet, and how many of the group the
    deck has figures for (the layer's page and tables count only those): "in “Other IT service companies”, listed, never compared: 33 of 252
    fit none of the map's layers; 82 not checked yet (no description of their own is kept, so nothing placed them); 18 of the 115 among the
    companies with figures"."""
    n, of, name, unread = rest[0], rest[1], rest[2], (rest[3] if len(rest) > 3 else 0)
    # R44: the count of the companies placed is said once, in the row's "In informative layers" figure; here, what the rest are
    parts = [f"{n - unread:,} fit none of the map's layers"]
    if unread:
        parts.append(f"{unread:,} not checked yet (no description of their own is kept, so nothing placed them)")
    shown = next((b for b in v.get("layers") or [] if b.get("basis") == "rest" or b.get("layer") == name), None)
    k = len([c for c in (shown or {}).get("companies") or [] if c.get("revenue") is not None or c.get("profit") is not None])
    if shown is not None and k < n:
        parts.append(f"its page lists the {k:,} of the {n:,} that have figures")
    return f"in a layer the map names; the other {n:,} in “{name}”, listed, never compared: " + "; ".join(parts)


def off_industry_line(v: dict) -> str:
    """"Filed under Retail-Miscellaneous Retail but in another business: Ferrellgas Partners, Suburban Propane Partners." (R40): the companies
    an official industry of the theme files there whose own words describe another business, left out of the theme (theme_base.
    without_off_industry), by the industry they are filed under; "" when there are none."""
    by: dict = {}
    held = []
    for x in (v.get("placements") or {}).get("off_industry") or []:
        if isinstance(x, dict) and x.get("ticker"):
            if x.get("before"):          # d53: out by an earlier version's finding, no words of its own read since
                held.append(clean_name(x.get("name") or x["ticker"]))
                continue
            by.setdefault(x.get("industry") or "the theme's industries", []).append(clean_name(x.get("name") or x["ticker"]))
    # c1: a name ending in a full stop ("Amaze Holdings, Inc.") ends the sentence, never with a second one
    out = " ".join(f"Filed under {ind} but in another business: {', '.join(names).rstrip('.')}." for ind, names in by.items())
    if held:
        out = (out + " " if out else "") + (f"Found to be in another business by an earlier version of the theme, with no words of their own read "
                                            f"since: {', '.join(held).rstrip('.')}.")
    return out


_COV_OF = re.compile(r"(\d[\d,]*) of (\d[\d,]*)")


def coverage_table_flags(rows: list, v: dict, cov: dict) -> list[str]:
    """What breaks the coverage table (R30): a kind missing, a count above what it is of, a share of value that isn't the members' value share or
    is said of companies, a figure's count above the companies with figures. [] when it holds."""
    out, got = [], {r[0]: r for r in rows}
    for k in COVERAGE_KINDS[:1] + ((COVERAGE_KINDS[1],) if cov.get("share") is not None else ()):
        if k not in got:
            out.append(f"no row: {k}")
    for r in rows:
        for a, b in _COV_OF.findall(" ".join(r[1:])):
            if int(a.replace(",", "")) > int(b.replace(",", "")):
                out.append(f"{r[0]}: {a} above {b}")
    mv = got.get(COVERAGE_KINDS[1])
    if mv:
        if mv[1] != f"{value_share(v)['share']}%":
            out.append(f"market value {mv[1]} is not the members' share")
        if "compan" in mv[1]:
            out.append("market value said in companies")
    wf = v.get("members_with_figures") if v.get("members_with_figures") is not None else cov.get("n") or 0
    for lab, k in re.findall(r"([A-Za-z/ ]+?) (\d[\d,]*)(?: ·|$)", (got.get(COVERAGE_KINDS[2]) or ["", "", ""])[2]):
        if int(k.replace(",", "")) > wf:
            out.append(f"{lab.strip()} {k} above with figures {wf}")
    return out


def coverage_rows(v: dict, cov: dict) -> list[list[str]]:
    """How many companies each total and median is of (R17-013: the cover said 60 companies with figures, the size slide's total was of 45 with
    a market value): the list, those with figures, those with a market value, and each aggregate's own count, with the share of market value."""
    sec = v.get("sections") or {}
    size, gm = sec.get("size") or {}, sec.get("growth") or {}
    meds, mg, q, val = sec.get("medians") or {}, sec.get("margins") or {}, sec.get("quarter") or {}, sec.get("valuation") or {}
    rows = [["Companies in the theme's list", f"{cov['total']:,}", ""],
            ["With figures", f"{cov['n']:,}", f"{cov['share']}% of {cov['of_what']}" if cov.get("share") is not None else ""],
            ["Confirmed, with figures (every median and total is of these)", f"{v.get('members_with_figures') or 0:,}", ""],
            ["With a market value (the theme's total market value)", f"{size.get('with_value', 0):,}", ""]]
    lend = bool((v.get("checks") or {}).get("lenders"))
    each = [f"{label} {n:,}" for label, n in (
        ("EBITDA margin", (meds.get("ebitda") or {}).get("n")), ("net margin", (meds.get("net") or {}).get("n")), ("ROCE", (meds.get("roce") or {}).get("n")),
        ("ROE", (meds.get("roe") or {}).get("n") if lend else None),
        ("P/E", (val.get("pe") or {}).get("n")), ("revenue growth together", ((gm.get("aggregate") or {}).get("revenue_1y") or {}).get("n")),
        ("margins over time", mg.get("n")), ("latest quarter", len(q.get("companies") or []) or None)) if n]
    if each:
        rows.append(["In each median and total", "", " · ".join(each)])
    return rows


def dominated(values) -> bool:
    from .intel.metric_registry import dominated as d
    return d(values)


def growth_base_line(rows: list, amt, limit: int = 5) -> str:
    """The companies whose revenue growth is unusual (metric_registry.is_extreme), each with its base as filed: "X +240% (from ₹50 cr to
    ₹170 cr)"; no cause given (R27)."""
    from .intel.metric_registry import GROWTH_EXTREME, SMALL_BASE, is_extreme, year_bases
    based = [(r, year_bases(r)) for r in rows if r.get("sales_1y") is not None]
    froms = sorted(b[0] for _, b in based if b and b[0] is not None)
    mid = froms[len(froms) // 2] if froms else None
    xs = [(r, b) for r, b in based if b and is_extreme(r["sales_1y"], b[0], mid)]
    if not xs:
        return ""
    parts = [f"{r['name']} {_chg(r['sales_1y'])}, from {amt(b[0])} to {amt(b[1])}" for r, b in xs[:limit]]
    return (f"Revenue growth above {GROWTH_EXTREME:.0f}% either way, or from a base under {SMALL_BASE * 100:.0f}% of the median company's, "
            "with its base: " + "; ".join(parts)
            + (f"; {len(xs) - limit} more" if len(xs) > limit else "") + ".")


def _findings(slides: list, v: dict, cov: dict, ebm, cap, eyebrow: str, today: date, chained: bool = True, lender: bool = False) -> None:
    """The findings up front: what the figures show (with page references), the data-confidence page and "Dated company updates". Every sentence is a
    computed fact from the view; no AI writes a figure here, and nothing says what to buy or what is cheap."""
    chain = v.get("chain") or {}
    sec = v.get("sections") or {}
    layers = [x for x in v.get("layers") or [] if any(c.get("status") != "unverified" for c in x.get("companies") or [])]
    from statistics import median as _median
    from .intel.theme_data import HEADLINE_MIN, headline_ok, of_words, period_basis, rank_pair
    cards = []
    # 1. value-chain economics: only when there are layers to set side by side (R18: no card that says it can't be done)
    own = [x for x in layers if not x.get("official") and x.get("revenue")]
    measure, mword = ("roe", "return on equity") if lender else ("ebitda", "EBITDA margin")
    if chained and chain.get("line"):
        lines = [chain["line"]]
        part = partial_map(v, cov)
        if part:                   # d53: a partial map said in the headline it qualifies, before its first word
            lines = [f"A partial map, of the {part.split(': ', 1)[1].split(' companies were checked')[0]} companies checked: {chain['line']}"]
        tot = sum(x["revenue"] for x in own)
        if own and tot and len(own) >= 2:
            big = max(own, key=lambda x: x["revenue"])
            lines.append(f"{big['layer']} brings in the most revenue of the map's own layers, {money(big['revenue'], v.get('unit') or ('$ million' if v.get('region') == 'US' else '₹ crore'))}.")
        cards.append({"title": "Where the return sits" if chain.get("measure") == "roe" else "Where the margin sits", "lines": lines,
                      "note": "⟦The value chain by layer⟧" + (f", ⟦{COMPARE_TITLE}⟧" if chain.get("basis") else "")})
    # 2. growth beside margin (a lender's: beside its return on equity)
    gm = []
    grew = {}                       # R48: who is in each layer's growth median, by name (the comparison basis)
    for x in own if chained else []:
        cos = [c for c in x["companies"] if in_calc(c) and not c.get("company_wide")]
        g = [c["sales_1y"] for c in cos if c.get("sales_1y") is not None]
        e = (x.get("stats") or {}).get(measure)
        # no finding on a base under 3 (R20), one floor (R25), coverage and model (R27); none whose growth is mostly unusual figures (R27)
        if g and e and headline_ok(e["n"], len(cos), x.get("model")) and not dominated(g) and not x.get("scale"):      # d1: a half never ranked alone
            gm.append((x["layer"], _median(g), e["median"], len(g), len(cos), x.get("model"), period_basis(cos), x.get("intensity")))
            grew[x["layer"]] = ([c["name"] for c in cos if c.get("sales_1y") is not None], x.get("intensity_n"), listed_names(x), x.get("intensity_missing") or [])
    f_ = _pc if lender else ebm
    pair = rank_pair(gm, lambda t: t[1], lambda t: t[3], of=lambda t: t[4], model=lambda t: t[5], basis=lambda t: t[6],
                     intensity=lambda t: t[7]) if chained else None
    if pair:
        fast, slow = pair
        note_basis(v, "Key findings", "revenue growth in the latest year (median)", [
            {"layer": t[0], "value": t[1], "n": t[3], "of": t[4], "model": t[5], "basis": t[6], "intensity": t[7], "intensity_n": grew[t[0]][1],
             "names": grew[t[0]][0], "listed": grew[t[0]][2], "intensity_missing": grew[t[0]][3]} for t in comparable_basis_rows(gm, lambda t: t[1], lambda t: t[3], lambda t: t[4], lambda t: t[5], lambda t: t[6], lambda t: t[7])],
            high=fast[0], low=slow[0])
        # m2: one sentence that says which layers it ranks (the headline floor), the fastest and the slowest in it
        kinds = {(t[5] or {}).get("family") for t in gm if isinstance(t[5], dict)} - {None, ""}       # a layer of another family is left out of it
        lines = [f"Among layers of at least {HEADLINE_MIN} companies with the figure{' and one kind of business' if len(kinds) > 1 else ''}, revenue grew fastest in the latest year in {fast[0]} "
                 f"(median {_chg(fast[1])}, median {mword} {f_(fast[2])}, {of_words(fast[3], fast[4])}) and slowest in {slow[0]} "
                 f"(median {_chg(slow[1])}, {f_(slow[2])}, {of_words(slow[3], slow[4])})."]
    else:
        g = (sec.get("growth") or {}).get("median") or {}
        m_ = ((sec.get("medians") or {}).get(measure) or {}).get("median")
        lines = [f"Median company's revenue growth in the latest year: {_med(g.get('revenue_1y'), _chg)}" + (f"; median {mword} {f_(m_)}." if m_ is not None else ".")]
    cards.append({"title": "Growth beside return" if lender else "Growth beside margin", "lines": lines,
                  "note": "⟦Every company's figures⟧" + (f", ⟦{COMPARE_TITLE}⟧" if pair else "")})
    # 3. valuation against companies of similar size, beside growth and ROCE
    peers = dated_peers(v)
    lines = []
    from .intel.theme_data import relative_ok
    val_ = sec.get("valuation") or {}
    if val_.get("pe") and not relative_ok(val_):
        # R29: peers for under half: the theme's own valuation, described, never relative
        lines.append(descriptive_line(val_) + ".")
    elif (peers.get("pe") or {}).get("premium") is not None:
        lines.append(pe_peer_line(peers["pe"]) + ".")
    elif (peers.get("pe") or {}).get("none"):
        lines.append(f"{_n(peers['pe']['none'], 'company', 'companies')} with a P/E and no comparable peer set: no relative P/E is shown.")
    for key, label, f in (("sales_3y", "Revenue growth, 3 years a year", _chg), ("roce", "ROCE", _pc)):
        if (peers.get(key) or {}).get("n") and not (val_.get("pe") and not relative_ok(val_)):        # the population said (R22: a ROCE of the companies with peers beside the theme's own median read as one figure)
            lines.append(f"{label}, the {peers[key]['n']} with such peers: {f(peers[key]['theme'])} against {f(peers[key]['peers'])}.")
    if not lines:
        lines = ["Too few comparable listed companies (same sector, similar market value) have the figures to compare."]
    cards.append({"title": "Price beside growth and returns", "lines": lines, "note": "⟦Valuation⟧"})
    # 4. what changed
    q = sec.get("quarter") or {}
    lines = []
    if q.get("quarter") and (q.get("sales") or {}).get("n", 0) >= MIN_BASE:
        lines.append(quarter_words(q) + ".")
    mg = sec.get("margins") or {}
    pe = [(y, x) for y, x in zip(mg.get("years") or [], mg.get("ebitda") or []) if x is not None]
    if len(pe) >= 2:
        lines.append(f"Aggregate EBITDA margin {_pc(pe[-2][1])} in {pe[-2][0]}, {_pc(pe[-1][1])} in {pe[-1][0]} ({_n(mg.get('n') or 0, 'company', 'companies')}).")
    own_ = sec.get("ownership") or {}
    if own_.get("holdings"):
        lines.append(promoter_words(own_.get("promoter_up", 0), own_.get("promoter_down", 0), len(own_["holdings"])))
    # R48: a card points to a page only when the deck has it (a reference to no page printed nothing, and now fails the gate: provenance_flags)
    cards.append({"title": "What changed", "lines": lines or ["No quarter, margin history or shareholding filing to compare yet."],
                  "note": "⟦The latest quarter⟧" if q.get("companies") else ""})
    sl_ = sector_lines(sec)
    if sl_:                       # R23: the sector's own filed figures
        cards.append({"title": "Sector operating figures", "lines": sl_[:2], "note": f"⟦{SECTOR_TITLE}⟧" if sector_paged(v) else ""})
    watch = watch_list(v, today)
    conf = confidence_rows(v, cov, today, lender)
    cards.append({"title": "How far the figures go", "lines": [f"{counts_words(reconciled_counts(v, cov))}.", f"{len(conf)} checks on every figure, each with what it found."],
                  "note": "⟦Data confidence⟧"})
    cards.append({"title": UPDATES_TITLE, "lines": [f"{_n(len(watch), 'dated update')} at {_n(len({x['name'] for x in watch}), 'company', 'companies')}, "
                                                    "picked by fixed rules, each with its date, status and source." if watch
                                                    else "No company meets the rules today."], "note": f"⟦{UPDATES_TITLE}⟧" if watch else ""})
    if len(cards) > 6:            # two short cards share one so the page keeps two rows of three
        a_, b_ = cards[-2], cards.pop()
        # n1 (the live R33 Private Banks deck: the merged card's updates line gave way to fit, so the deck said nothing of dated updates):
        # one line of each first, so a line that gives way is never the only one of its card
        first = (a_, b_)
        cards[-1] = {"title": f"{a_['title']}; {b_['title'].lower()}", "lines": first[0]["lines"][:1] + first[1]["lines"][:1] + first[0]["lines"][1:] + first[1]["lines"][1:], "note": ", ".join(x for x in (a_["note"], b_["note"]) if x)}
        if b_["title"] == UPDATES_TITLE and not watch:
            # q1 (the live R34 Private Banks deck: the merged card kept only "No company meets the rules today", its coverage line given way):
            # no dated update is said in the card's title, so the card's lines are the coverage summary and none of it gives way for it
            cards[-1] = {**a_, "title": f"{a_['title']}; no dated company update today"}
    s = Slide("Key findings", "What the reported figures show, each with the slide it comes from; findings, not advice", eyebrow=eyebrow)
    ccols = 3 if len(cards) != 4 else 2
    s.add("cards", (M, TOP, CW, BOT - TOP), cols=ccols, items=whole_lines(cards, (M, TOP, CW, BOT - TOP), ccols), fill=True, size=13)
    slides.append(s)

    # data confidence on ONE page (R19, the owner: "just keep the important ones"): the checks, then every count in one line under them; a
    # check of least weight gives way when they don't fit
    head, widths = ["Check", "What it found", "What the deck does"], [1.8, 6.6, 3.7]
    counts = coverage_line(v, cov)
    nh = note_h(counts)
    cov_rows, cov_w = coverage_table(v, cov), [1.8, 1.4, 8.9]
    ch_ = table_height(COVERAGE_HEAD, cov_rows, cov_w, CW) + 0.15 if cov_rows else 0
    room = BOT - TOP - nh - 0.15 - ch_

    def give_way(room_):
        rows_ = list(conf)
        for name in CONF_GIVE_WAY:
            if len(table_pages(head, rows_, widths, CW, room_)) <= 1:
                break
            rows_ = [r for r in rows_ if r[0] != name]
        return rows_

    def named_only(rows_, room_):
        """R46: the verified figures said by name only (each one's record is on the source page) before any check is cut off the page."""
        if len(table_pages(head, rows_, widths, CW, room_)) > 1 and (v.get("checks") or {}).get("verified"):
            return [verified_row(v["checks"]["verified"], short=True) if r[0] == "Verified figures" else r for r in rows_]
        return rows_
    rows = give_way(room)
    # d1 (the live Release 41 Semiconductors, Real estate, Telecom and Utilities decks: the checks' table printed its heading and no row, the
    # coverage table under it taking the page): when the checks don't fit beside the coverage, the coverage has a page of its own after them
    apart = bool(cov_rows) and (bool(rows) and len(table_pages(head, rows, widths, CW, room)) > 1 or ch_ > BOT - TOP - nh - 0.15)
    if apart:
        room = BOT - TOP - nh - 0.15
        rows = give_way(room)
    rows = table_pages(head, named_only(rows, room), widths, CW, room)[0] if rows else rows
    s = Slide("Data confidence", "The checks every figure went through, what each found and what the deck does with it", eyebrow=eyebrow)
    th = min(room, table_height(head, rows, widths, CW))
    s.add("table", (M, TOP, CW, th), head=head, rows=rows, widths=widths, numeric=[False] * 3, tight=True)
    if apart:                      # the counts under the checks, the coverage table on the next page
        s.add("text", (M, TOP + th + 0.15, CW, nh), paras=[counts], size=BODY_MIN, floor=BODY_MIN, color=INK2)
        slides.append(s)
        # tx2 (R46, the live Release 45 Consumer retail deck: the coverage table ran past its page into the footer): a coverage table taller
        # than a page goes on over as many pages as it needs, each row whole
        cov_pages = table_pages(COVERAGE_HEAD, cov_rows, cov_w, CW, BOT - TOP)
        for k, rows_ in enumerate(cov_pages):
            s = Slide(COVERAGE_TITLE if not k else f"{COVERAGE_TITLE}, continued",
                      "How many of the theme's companies, how much of its market value and which figures each total and median covers",
                      eyebrow=eyebrow)
            s.add("table", (M, TOP, CW, min(BOT - TOP, table_height(COVERAGE_HEAD, rows_, cov_w, CW))), head=COVERAGE_HEAD, rows=rows_,
                  widths=cov_w, numeric=[False] * 3, tight=True)
            slides.append(s)
    else:
        if cov_rows:                   # R30: coverage by count, market value, figure and layer, each on its own row
            s.add("table", (M, TOP + th + 0.15, CW, ch_ - 0.15), head=COVERAGE_HEAD, rows=cov_rows, widths=cov_w, numeric=[False] * 3, tight=True)
            th += ch_
        s.add("text", (M, TOP + th + 0.15, CW, nh), paras=[counts], size=BODY_MIN, floor=BODY_MIN, color=INK2)
        slides.append(s)

    # dated company updates (m2; "Worth a watch" before): only when a company meets the rules, on one page, the latest day first (R19)
    if watch:
        dated = sorted(watch, key=lambda x: str(x.get("at") or ""), reverse=True)
        when = lambda at: _day(at) if re.match(r"^\d{4}-\d{2}-\d{2}", str(at)) else _month(at)      # noqa: E731
        src = lambda x: {"text": x["source"], "url": x["url"]} if x.get("url") and x.get("source") else (x.get("source") or "–")     # noqa: E731
        rows = [[x["name"], x["fact"] + (f". {x['context']}" if x.get("context") else ""), when(x["at"]), x.get("status") or "–", src(x),
                 f"⟦{x['ref']}⟧"] for x in dated]         # the source: the filing itself, linked, where its address is held
        note = ("The rules: results filed but not yet in the figures; an auditor's resignation; a promoter stake move of a point or more; results "
                "scheduled in the next week; an operating figure 25% or more above or below a year before. Scheduled: a day the company has given "
                "for an event not yet held. Announced or filed: already made public, in the source named. Each event is as its source states it.")
        nh = note_h(note)
        wh, ww = ["Company", "Update", "Date", "Status", "Source", "Slide"], [2.7, 4.5, 1.35, 1.15, 1.6, 0.7]
        first = table_pages(wh, rows, ww, CW, BOT - TOP - nh - 0.07)[0]
        sub = "Dated events at the theme's companies: what happened or is scheduled, its day, its status and its source; picked by fixed rules, not a view"
        if len(first) < len(rows):
            sub = (f"The {len(first)} latest by date of {len(rows)} dated events at the theme's companies: each with its day, its status and its "
                   "source; picked by fixed rules")
        s = Slide(UPDATES_TITLE, sub, eyebrow=eyebrow)
        s.add("table", (M, TOP, CW, BOT - TOP - nh - 0.07), head=wh, rows=first, widths=ww, numeric=[False] * len(wh))
        s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)


def source_records(ch: dict) -> list[dict]:
    """R46: every checked figure's record (verified, not reconciled, invalid), one list read from theme_data.figure_states; a view kept before
    R44 carries only its verified and † lists."""
    if ch.get("states"):
        return list(ch["states"])
    return [{**x, "key": x.get("key", "net"), "state": x.get("state", "verified_extreme")} for x in ch.get("verified") or []] + \
        [{**x, "key": "net", "value": x.get("net"), "state": "unverified_extreme", "checks": x.get("checks") or []} for x in ch.get("one_off") or []]


SOURCES_HEAD, SOURCES_WIDTHS = ["Company", "Figure, state", "Source, period", "Statement lines, as stored", "What the lines show"], [2.0, 1.4, 2.0, 4.4, 2.4]


def _figure_sources(slides: list, v: dict, eyebrow: str) -> None:
    """R46 (the outside review of the live R45 decks: "verified extremes are kept, but the explanation does not always give a filing reference and
    a traceable extraction record"): one row per checked figure, verified first: the document, period and stored page its year comes from, the
    statement lines it is worked out from with their values in the filing's unit, its state and what the lines show. A part not stored is said
    so, never filled in."""
    recs = source_records(v.get("checks") or {})
    if not recs:
        return
    order = {"verified_extreme": 0, "unverified_extreme": 1, "invalid": 2}
    recs = sorted(recs, key=lambda x: order.get(x.get("state"), 3))
    rows = [[f"{x['name']} ({x['symbol']})" if x.get("symbol") else x["name"], f"{HELD_WORDS.get(x['key'], x['key'])[:1].upper()}{HELD_WORDS.get(x['key'], x['key'])[1:]} "
             + (f"{x['value']}x" if x["key"] == "pb" else _pc(x["value"])) + f", {state_word(x)}",
             source_words(x.get("source"), page=False) + (f"; page built {_day(x['source']['built'])}" if (x.get("source") or {}).get("built") else ""),
             line_words(x.get("lines"), (x.get("source") or {}).get("unit")) or "lines not stored",
             shown_words(x)] for x in recs]
    mk = (v.get("region") or "in").lower()
    note = (f"Each company's year as its stored page holds it (/stocks/{mk}/SYMBOL), in the filing's unit. EBITDA: the operating profit, else "
            "revenue times the EBITDA margin. Items before tax: profit before tax beyond EBITDA, other income, interest and depreciation (exceptional "
            "items); items after tax: net profit beyond profit before tax less its tax (a share of associates' or joint ventures' profit, or another "
            "item after tax). Verified: the calculation, accounting basis and statement lines checked, in every median; arithmetic reproduced: net "
            "profit over revenue worked out again and nothing more, in every median; not reconciled: shown, out of the medians; invalid: shown as –.")
    nh = note_h(note)
    th = BOT - TOP - nh - 0.1
    pages = table_pages(SOURCES_HEAD, rows, SOURCES_WIDTHS, CW, th)
    # d53 (R53, our deck reviewer: "15 checked figures, 15 verified" over rows each "arithmetic reproduced"): the head counts the rows'
    # own states, a figure whose arithmetic alone was worked out again never among the verified
    vn = sum(1 for x in recs if x.get("state") == "verified_extreme" and not only_arithmetic(x))
    an = sum(1 for x in recs if only_arithmetic(x))
    head_ = f"{_n(len(recs), 'checked figure')}, {vn} verified" + (f", {an} arithmetic reproduced only" if an else "")
    for k, chunk in enumerate(pages):
        s = Slide(SOURCES_TITLE + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                  f"{head_}: where each comes from and the stored lines it is worked out from", eyebrow=eyebrow)
        s.add("table", (M, TOP, CW, min(th, table_height(SOURCES_HEAD, chunk, SOURCES_WIDTHS, CW))), head=SOURCES_HEAD, rows=chunk,
              widths=SOURCES_WIDTHS, numeric=[False] * len(SOURCES_HEAD), tight=True)
        s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)


COMPARE_TITLE = "Comparison basis"      # R48: the appendix page of what each highest/lowest claim between layers rests on
# ex49 (R49, the outside review of the live R48 decks: "comparison-basis pages are text-heavy with small type: condense without losing
# evidence (clear hierarchy, one table a page)"): each comparison on its own page, its claim the page's takeaway, its rules one short line
# each in larger type, and one table: a row per compared layer (its figure with its count, its capital proxy, its business model and its
# companies by name)
COMPARE_HEAD, COMPARE_WIDTHS = ["Layer", "Figure (companies)", "Capital, a proxy", "Business model", "Companies in the figure"], [2.4, 1.4, 1.2, 2.5, 4.6]
RULES_SIZE = 12                           # ex49: the rules' lines, a size above the notes'


NAMES_SHOWN = 12           # R48: a compared layer's companies named one by one up to this many; beyond it, by the appendix's rows, all but those named


def listed_names(x: dict) -> list[str]:
    """R48: a layer's confirmed companies with figures by name (theme_data.listed_names), as "Every company's figures" lists them."""
    from .intel.theme_data import listed_names as ln
    return ln(x)


def comparable_basis_rows(rows: list, value, count, of, model, basis, intensity) -> list:
    """R48: the rows a rank_pair or rank_top ranked among (theme_data.comparable_rows, the one rule of every ranking)."""
    from .intel.theme_data import comparable_rows
    return comparable_rows(rows, value, count, of=of, model=model, basis=basis, intensity=intensity)


def note_basis(v: dict, where: str, metric: str, groups: list, high: str | None = None, low: str | None = None, said: str = "") -> None:
    """R48: a highest/lowest claim the deck makes, recorded with its basis (theme_data.comparison_basis) for the "Comparison basis" page: one
    record for each metric and set of layers, where it is first made."""
    from .intel.theme_data import comparison_basis
    if len(groups) < 2 or "comparisons" not in v:
        return
    key = (metric, tuple(sorted(g["layer"] for g in groups)))
    for b in v["comparisons"]:            # the same metric over the same layers: one basis, each place that ranks on it named
        if (b["metric"], tuple(sorted(g["layer"] for g in b["groups"]))) == key:
            if where != b["where"] and where not in b.setdefault("also", []):
                b["also"].append(where)
            return
    v["comparisons"].append({**comparison_basis(where, metric, groups, high=high, low=low), "where": where, **({"said": said} if said else {})})


def basis_claim(b: dict) -> str:
    """ex49: a comparison's claim, as its page's takeaway: the metric, the layers named highest and lowest (or not ranked, and why), and where
    the deck makes it."""
    from .intel.theme_data import HEADLINE_MIN
    hi_lo = (f"highest {b['high']}" + (f", lowest {b['low']}" if b.get("low") else "")) if b.get("high") else ""
    # m2: a sentence that names a highest or lowest says the headline floor in it
    scope = f", among layers with at least {HEADLINE_MIN} companies with the figure" if hi_lo and b.get("made") else ""
    return (f"{b['metric'][:1].upper()}{b['metric'][1:]} by layer{scope}: " + (hi_lo if b.get("made") else f"not ranked, {b.get('why') or 'not comparable'}")
            + (f". In {b['said']}, from ⟦{b['where']}⟧" if b.get("said") else f". ⟦{b['where']}⟧")
            + "".join(f", ⟦{w}⟧" for w in b.get("also") or []))


def basis_rules(b: dict) -> list[str]:
    """ex49: a comparison's eligibility rules, one short line each with whether it is met, then each shown layer left out of the ranking with
    why: the metric, the headline floor and coverage, one way of earning, one business model, one period basis and the capital-intensity proxy
    (each layer's figure is in its own row of the table; the line says the ratio, the threshold and the inputs missing)."""
    out = []
    for r in b.get("rules") or []:
        t = r.get("test")
        name = "Capital intensity, a proxy for capital needs" if r["rule"] == "capital intensity" else f"{r['rule'][:1].upper()}{r['rule'][1:]}"
        if t:
            text = (f"the largest layer figure of capital for each unit of revenue is {t['ratio']:.1f} times the smallest; ranked only at "
                    f"{t['threshold']:g} times or less; passing it alone never makes layers comparable")
            miss = r.get("missing") or []
            if miss:
                text += "; inputs missing: " + "; ".join(f"{nm} ({' and '.join(m_)})" for _, nm, m_ in miss[:6]) + (
                    f" and {len(miss) - 6} more" if len(miss) > 6 else "")
        else:
            text = r["text"]
        out.append(f"{name} ({'met' if r.get('passed') else 'not met'}): {text}.")
    if b.get("left"):
        out.append("Shown, not ranked: " + "; ".join(f"{x['layer']}, {x['why']}" for x in b["left"]) + ".")
    return out


def basis_rows(b: dict, h: float = 99.0, w: float = CW) -> list[list[str]]:
    """R48: one comparison's table rows: a row per compared layer with its figure and count, its capital proxy, its business model and its
    companies by name; a layer whose names don't fit one row of a w x h table goes on in rows of its own, "<layer> (continued)", as the
    roll's (roll_rows). ex49: the claim and the rules are the page's own lines (basis_claim, basis_rules), no longer cells."""
    from .intel.theme_data import gpts, pts
    fmt = _chg if "growth" in b["metric"] else gpts if b["metric"] == "EBITDA margin" else pts
    out = []
    for g in b.get("groups") or []:
        fig = ("–" if g.get("value") is None else fmt(g["value"])) + f" ({_of_n(g.get('n') or 0, g.get('of'))})"
        cap = (f"{g['intensity']:.2f}" + (f" ({g['intensity_n']})" if g.get("intensity_n") else "")) if g.get("intensity") else "not stored"
        m = str(g.get("model") or "")
        biz = str(g.get("business") or "") or m.split(", shown for")[0]
        if ", shown for" in m:
            biz += f"; way of earning{m.split(',', 1)[1]}"
        head = [g["layer"], fig, cap, biz or "not read"]
        names = list(g.get("names") or [])
        listed = list(g.get("listed") or [])
        if len(names) > NAMES_SHOWN and listed and set(names) <= set(listed):
            # a long list said by the appendix's own rows: every company it lists under the layer, all but those named (exact either way)
            gone = [x for x in listed if x not in set(names)]
            names = ["Every company of the layer in the appendix's figures table, ⟦Every company's figures⟧" + (f", but {', '.join(gone)}" if gone else "")]
        fits = lambda r: len(table_layout({"head": COMPARE_HEAD, "rows": [r], "widths": COMPARE_WIDTHS, "numeric": [False] * 5}, w, h)["rows"]) == 1  # noqa: E731
        for n in range(1, max(1, len(names)) + 1):
            per = -(-len(names) // n) if names else 1
            parts = [names[j * per:(j + 1) * per] for j in range(n) if names[j * per:(j + 1) * per]] or [[]]
            got = [head + [", ".join(parts[0]) or "not stored"]] + [[g["layer"] + ROLL_MORE, "", "", "", ", ".join(x)] for x in parts[1:]]
            if all(fits(r) for r in got):
                break
        out += got
    return out


def compare_cols(rows: list) -> tuple[list, list]:
    """ex49: the comparison table's columns: the business model's left out when no layer of it has one read."""
    if rows and all(r[3] in ("not read", "") for r in rows):
        return [h for i, h in enumerate(COMPARE_HEAD) if i != 3], [w_ for i, w_ in enumerate(COMPARE_WIDTHS) if i != 3]
    return COMPARE_HEAD, COMPARE_WIDTHS


def _comparison_basis(slides: list, v: dict, eyebrow: str) -> None:
    """R48 (the outside review of the live R46 decks: "every highest/lowest claim has an auditable metric, company set and eligibility
    rule"): every comparison the deck makes or declines to make between layers (the value chain's, the findings', the economics' and the
    questions'), with its metric, the rules with their figures (headline floor and coverage, one way of earning, one business model, one
    period basis, the capital-intensity proxy with each layer's figure and the threshold) and each compared layer's companies by name.
    ex49 (R49): one comparison a page (continued on the next when its table runs over): its claim the takeaway, its rules a line each at
    RULES_SIZE, one table."""
    recs = v.get("comparisons") or []
    if not recs:
        return
    note = ("Each figure: the layer's median company, its count in brackets. Capital, a proxy for capital needs: book equity (market value over "
            "price to book, else debt over debt to equity) plus debt, over the latest year's revenue, both parts stored for the year. Business "
            "model: the one the map's own name for the layer states, else how its companies earn. Companies in the figure: those in its median.")
    nh = note_h(note)
    made = sum(1 for b in recs if b.get("made", True))
    pages = []                      # (claim, rule lines or None on a page that goes on, table rows)
    for b in recs:
        rules = basis_rules(b)
        rh = sum(len(wrap(x, RULES_SIZE, CW)) * _lh(RULES_SIZE) for x in rules) + 0.06 * (len(rules) - 1) + 0.15
        full = BOT - TOP - nh - 0.1
        first = max(1.0, full - rh)
        rows = basis_rows(b, first)
        head, widths = compare_cols(rows)
        rows = [[c for i, c in enumerate(r) if i != 3] for r in rows] if len(head) < len(COMPARE_HEAD) else rows
        chunks = table_pages(head, rows, widths, CW, full, first=(CW, first))
        for k, chunk in enumerate(chunks):
            pages.append((basis_claim(b) + (" (continued)" if k else ""), rules if k == 0 else None, chunk, rh, first if k == 0 else full, head, widths))
    for k, (claim, rules, chunk, rh, th, head, widths) in enumerate(pages):
        s = Slide(COMPARE_TITLE + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""), claim, eyebrow=eyebrow)
        y = TOP
        if rules:
            s.add("text", (M, y, CW, rh), paras=rules, size=RULES_SIZE, floor=BODY_MIN)
            y += rh
        s.add("table", (M, y, CW, min(th, table_height(head, chunk, widths, CW))), head=head, rows=chunk,
              widths=widths, numeric=[False] * len(head), tight=True)
        s.add("text", (M, BOT - nh, CW, nh), paras=[note + f" {_n(len(recs), 'comparison')} between layers, {made} ranked."], size=BODY_MIN,
              floor=BODY_MIN, color=MUTED)
        slides.append(s)


COVERAGE_TITLE = "Coverage"
CHART_MIN = 2.2            # R46: inches a chart keeps when the questions the figures raise share its page
CONF_GIVE_WAY = ("Precision", "Old operating figures", "Bases and counts", "Broken series", "One quarter", "Operating figures")


def coverage_line(v: dict, cov: dict) -> str:
    """How many companies each total and median is of, in one line (R19: the counts under the checks, never a page of their own)."""
    parts = []
    for label, n, share in coverage_rows(v, cov):
        if label == "In each median and total":
            parts.append(f"in each median: {share}")
        else:
            parts.append(f"{label[:1].lower() + label[1:]} {n}" + (f" ({share})" if share else ""))
    return f"Counts: {counts_words(reconciled_counts(v, cov))}. {cov['line']}; " + "; ".join(parts[2:-1] if parts[-1:] and parts[-1].startswith("in each median") else parts[2:]) + "."


# ---------- R18: one formatter, one scheme of layers, a short core ----------
THEME_DECK_VERSION = 63                  # d53 (R53): the honest membership row, a partial map said in the headline and on the data-confidence page, the same company twice, core and adjacent, spending ahead of revenue, an adjacent layer said on its page, the figure-sources head counting arithmetic-only figures apart, every addition with its reason, moves between layers and layer changes in the cohort row, exclusions held from an earlier version (updated on purpose); gl52 (R52): exclusion reasons say what happened ("no description found in any source"), no low-confidence model printed, a layer line names a way of earning only for 3 or more, acronyms keep their case, a conglomerate's theme segment or "(whole company)" in Size and shape, halves of a split layer ranked as one, stock pay apart not ranked, the cohort row against the versions stored since (updated on purpose); rv51 (R51): business-model reasons from the layer's own records; principal business keeps a company in the theme; financial companies' other income; gl50 (R50): no layer ranked with no way of earning read, the gate failing a deck that does, "N not checked yet", the coverage's "Moved by what its layer is" row, a parent and listed subsidiary (updated on purpose); ex49 (R49): dive text 19, every exclusion's precise reason on layer pages and rolls, the capital-intensity proxy labelled, the business-model rule in each comparison, one condensed comparison per page (updated on purpose); vr48 (R48): figures reconciled with the year's lines before any is held, the comparison basis (updated on purpose); cl48 (R47): dive text 18, the coverage page's "Coverage flag" row (under 60% in informative layers, or 8 points or more fewer than the previous live placement), layers' lines say who earns another way (updated on purpose); vf46 (R46): dive text 17, each checked figure's source record, net above EBITDA reconciled line by line (updated on purpose); tx2 (R46, the outside review of the live R45 decks): the coverage's "Screening" row (considered = screened out as another business + members, confirmed, with figures, in informative layers, eligible for each metric), the screened-out companies said to be candidates, never members, "Considered" counting them apart from the members, a coverage table taller than a page continued on the next; c1 (R44, the outside review of the live R43 decks): the coverage's "From other industries" row (each company the map names from another industry, why it is in the theme and, apart from that, whether it is in its layer's figures), a layer named by how its companies earn says on its page why it is never ranked, layers of one official industry made from "Other"; R44 (lane v1, the outside review of the live R43 decks): each unusual figure verified against its own filed figures, not reconciled or invalid, one record each, and the data-confidence page's "Verified figures" with the count; the coverage's "In informative layers: N of M (P%)" said once; d1 (the outside review of the live Release 41 decks): the "Other" count split into fit none and not checked yet, one count on every page; every company in a layer or "Other"; no half of a split layer ranked, no comparison on a gap under a point, the peer P/E gap only against named like-for-like peers; layers of two companies or fewer on the "Smaller layers" page, a layer page of at least 5 companies; the coverage on a page of its own when the checks need the room; a company in its layer's figures on its industry said so; LIVE7A (lane t1): the real minus in every range and median, one precision a column, text or chart, layer parts that add up to the change shown, a row's mark its kept reason and a mark's note only with a row that carries it, the tailwinds' contents line in the page's own counts, medians of whole-point margins printed whole; R41: a coloured table cell (the highest and lowest layer, drawn bold) measured bold, so its row holds it whole; a cut paragraph never ends on a joining word; R40: the peer set said as "this theme" (no "the the" on a wrap), a repeated word said once on the finished pages and counted, a layer named only by how its companies earn shown and never ranked, a market-value half with fewer than 3 companies in its figures undone, the coverage table's "In no layer" and "Another business" rows; R38: foreign legal endings left off a label before any of it is cut, no word of a table cell broken inside; LIVE6: calendar price periods, own words only, one market value per company, short charts and empty tables dropped; q1: the appendix counts "with figures" by the dive's rule, a layer's cohort that fell against the run before on the data-confidence page; n1: the appendix roll names every company over continued rows, the completeness gate (no empty table page, declared counts made by the rows), names without filing tokens, unfilled tokens checked, a card line ends on a whole clause, the capital-per-revenue figures behind "not ranked", buy/sell as advice only as a recommendation; R36: ranking headlines say which layers they rank and why a shown layer is not ranked, "Dated company updates" with day, status, source and context, text repaired before the gate; lane m1: a layer's counts from one record of who is in its calculations ("14 of 17" in every table, head and roll), each left-out company's reason before its name, materials suppliers out of equipment layers; R35: a company line never cut at "Inc.", sub-theme members by their whole description, labels said shorter and never cut, the layout gate, a wide table's chart on its own page, the peer P/E's price date on every line, who is in a layer's calculations and why not, the appendix's layer names in full; R34: ranking scope line, shown-companies label; R32: chip designers as fabless, one layer a model-named primary model, an empty market-value half undone; R31: headline floor of 5, commodity sub-basis, metrics not in the sources, partial reads; part of a kept deck's key (theme_routes.DECK_CACHE): a file made before a deploy is made again
# a figure that is a whole number prints whole: "15.0%" is 15%, "43.0x" is 43x, "0.0 pts" is 0 pts; any other keeps its one decimal. Only a
# figure followed by its unit, a separator or the end, so a name like "Web 3.0 Ltd" is left as written
_WHOLE = re.compile(r"(?<![\w.,])(\d[\d,]*)\.0(?![\d.])(?=%|x\b| ?(?:pts|points|bn|m|cr|lakh|crore|billion|million|units)\b|\s*$|[,;:)\]](?!\d)|\s(?![A-Za-z]))")


# one money format (R23: "$1,947.2 bn" beside "$4,498 bn"): an amount of 1,000 bn or more prints with no decimal
_BIG_BN = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+)\.(\d+)(?= (?:bn|billion)\b)")


def _big_bn(m) -> str:
    from decimal import ROUND_HALF_UP, Decimal
    v = Decimal(m.group(1).replace(",", "") + "." + m.group(2)).quantize(Decimal("1"), ROUND_HALF_UP)
    return f"{int(v):,}"


# LIVE7A-014 (the live Automotive deck: "36%" beside "35.9%", "27x" beside "27.8x"): a whole figure keeps its ".0" where a figure of the same
# unit beside it (in the same text, the same table column or the same chart) has a decimal, so one place never mixes the two precisions
_DECIMAL = re.compile(r"(?<![\w.,])\d[\d,]*\.(?:[1-9]\d*|0\d*[1-9]\d*)(%|x\b| ?(?:pts|points)\b)")


def _unit(u: str) -> str:
    u = u.strip()
    return "pts" if u in ("pts", "points") else u


def decimal_units(*texts) -> set:
    """The units ("%", "x", "pts") that some figure of these texts prints with a decimal other than ".0"."""
    out = set()
    for t in texts:
        if isinstance(t, dict):
            t = t.get("text") or t.get("group") or ""
        if isinstance(t, str):
            out |= {_unit(m.group(1)) for m in _DECIMAL.finditer(t)}
    return out


def whole_figures(text, keep=None):
    """A text with every whole figure printed whole (the owner, 7 Nov: 149 "15.0%"-like figures in one deck) and every amount of 1,000 bn or
    more with no decimal; anything else as it is. LIVE7A-014: not a figure whose unit (%, x, pts) has a figure with a decimal in the same text
    or in `keep` (the units its table column or chart print with one), so "19.6% to 20.0%" stays as it is."""
    if not isinstance(text, str):
        return text
    text = _BIG_BN.sub(_big_bn, text)
    held = decimal_units(text) | set(keep or ())

    def one(m):
        tail = text[m.end():m.end() + 7].lstrip()
        u = "%" if tail.startswith("%") else "x" if re.match(r"x\b", tail) else "pts" if re.match(r"(?:pts|points)\b", tail) else ""
        return m.group(0) if u and u in held else m.group(1)
    return _WHOLE.sub(one, text)


CHART_FMT = {"pct": "pct1", "chg": "chg1", "x": "x1", "num1": "num1t"}
CHART_FMT_DEC = {"pct": "pctk1", "chg": "chgk1", "x": "xk1", "num1": "numk1"}      # LIVE7A-014: a chart with a decimal value keeps every value's


def _whole_cell(x, keep=None):
    if isinstance(x, dict):
        return {**x, **({"text": whole_figures(x["text"], keep)} if "text" in x else {}), **({"group": whole_figures(x["group"])} if "group" in x else {})}
    return whole_figures(x, keep)


def _whole_rows(rows: list) -> list:
    """A table's rows through whole_figures, each column printing its figures with one precision (LIVE7A-014)."""
    lists = [r for r in rows if isinstance(r, list)]
    cols = max((len(r) for r in lists), default=0)
    keep = [decimal_units(*[r[j] for r in lists if j < len(r)]) for j in range(cols)]
    return [_whole_cell(r) if isinstance(r, dict) else [_whole_cell(x, keep[j] if j < len(keep) else None) for j, x in enumerate(r)] for r in rows]


def _round1(xs):
    return [round(x, 1) if isinstance(x, float) else x for x in xs or []]


def whole_deck(slides: list) -> None:
    """Every figure on every slide through the one formatter (whole_figures): titles, lines, tables, cards, tiles and charts (a chart's values
    rounded to one decimal and printed with the matching format)."""
    for s in slides:
        s.title, s.subtitle = whole_figures(s.title), whole_figures(s.subtitle)
        s.contents = [(whole_figures(t), p) for t, p in s.contents]
        for b in s.blocks:
            if b.get("paras"):
                b["paras"] = [whole_figures(x) for x in b["paras"]]
            if b.get("rows"):
                b["rows"] = _whole_rows(b["rows"])
            if b.get("head"):
                b["head"] = [whole_figures(x) for x in b["head"]]
            if b["kind"] == "stats":
                b["items"] = [tuple(whole_figures(x) for x in it) for it in b["items"]]
            elif b.get("items") and isinstance(b["items"][0], dict):
                b["items"] = [{k: ([whole_figures(x) for x in val] if k == "lines" else whole_figures(val) if isinstance(val, str) else val)
                               for k, val in it.items()} for it in b["items"]]
            if b["kind"] in ("hbars", "columns", "lines"):
                if b.get("vals"):
                    b["vals"] = _round1(b["vals"])
                if b.get("series"):
                    b["series"] = [(x[0], _round1(x[1]), *x[2:]) for x in b["series"]]
                vals = list(b.get("vals") or []) + [v for x in b.get("series") or [] for v in (x[1] or [])]
                dec = any(isinstance(v, float) and not float(v).is_integer() for v in vals)
                b["fmt"] = (CHART_FMT_DEC if dec else CHART_FMT).get(b.get("fmt") or ("pct" if b["kind"] != "columns" else ""), b.get("fmt"))
                if b.get("title"):
                    b["title"] = whole_figures(b["title"])


def precision_problems(slides: list) -> list[str]:
    """The texts of finished slides with a whole figure printed with ".0" where nothing beside it (in the same text, table column or chart)
    has a decimal of that unit: what whole_deck prints whole (R18, LIVE7A-014). [] when there is none."""
    out = []

    def one(t, keep=None):
        if isinstance(t, dict):
            t = t.get("text")
        if isinstance(t, str) and whole_figures(t, keep) != t:
            out.append(t)
    for s in slides:
        for t in [s.title, s.subtitle] + [x for x, _ in s.contents]:
            one(t)
        for b in s.blocks:
            for t in (b.get("paras") or []) + (b.get("head") or []) + [b.get("title")]:
                one(t)
            lists = [r for r in b.get("rows") or [] if isinstance(r, list)]
            cols = max((len(r) for r in lists), default=0)
            keep = [decimal_units(*[r[j] for r in lists if j < len(r)]) for j in range(cols)]
            for r in lists:
                for j, x in enumerate(r):
                    one(x, keep[j])
            for it in b.get("items") or []:
                for x in (it if isinstance(it, tuple) else [v for k, v in it.items() if k != "lines"] + list(it.get("lines") or []) if isinstance(it, dict) else []):
                    one(x)
    return out


STATS_SHOWN = ("ebitda", "roce", "net", "roe", "nii_assets", "gnpa", "pb")
MIN_BASE = 3                     # companies a median needs to be shown as one (R20: "median of 2" is two values, shown as they are)


def _medn(st, of: int | None = None, f=lambda v: _pc(v), n: int | None = None, value=None) -> str:
    """A median with its base (R20): "–" when no company has the figure; "– (2 of 6)" when fewer than MIN_BASE do (the companies' own values
    are beside it); the median with "(5 of 6)" when it is of fewer companies than the `of` it stands for (R25: "N of M" wherever a count is
    shown beside the group's own, never "6" beside "15% (5)")."""
    if st is not None:
        n, value = st.get("n") or 0, st.get("median")
    if value is None or not n:
        return "–"
    base = f" ({n} of {of})" if of and n < of else f" ({n})"
    if n < MIN_BASE:
        return "–" + base
    return f(value) + (base if of and n < of else "")


def drop_empty(head: list, rows: list, widths: list, numeric: list | None = None, keep=(0,)) -> tuple:
    """(head, rows, widths, numeric) without the columns that are empty or "–" in every row (the owner: "Never a column that is '–' for
    every row: drop it"); the columns in `keep` always stay. Heading rows ({"group"}) pass as they are."""
    plain = [r for r in rows if not isinstance(r, dict)]
    cols = [i for i in range(len(head)) if i in keep or any(_cell_text(r[i]).strip() not in ("", "–") for r in plain)]
    pick = lambda xs: [xs[i] for i in cols]       # noqa: E731
    return (pick(head), [r if isinstance(r, dict) else pick(r) for r in rows], pick(widths), pick(numeric) if numeric else None)


LENDER_ONLY = ("roe", "nii_assets", "gnpa", "nnpa", "deposit_growth")
# R23: each family's filed figures in its layer tables, only where a company of the family is among them (and drop_empty keeps the filled ones);
# a bank's filed gross and net NPA and deposit growth take the place of the page tables' own in the lender's columns (no column more: its table is
# full), its other filed figures are on its sector page
FAMILY_COLS = {"solvency": "insurer", "combined_ratio": "insurer", "sbc_share": "us", "fcf_margin": "us"}
# a company's figure columns, the lender's own after the rest: each table keeps the ones its companies have (drop_empty)
CO_COLS = [("revenue", "Revenue", 1.25), ("ebitda", "EBITDA margin", 1.3), ("net", "Net margin", 1.25), ("roce", "ROCE", 1.0),
           ("roe", "ROE", 1.0), ("nii_assets", "NII / assets", 1.2), ("gnpa", "Gross NPA", 1.1), ("nnpa", "Net NPA", 1.0),
           ("deposit_growth", "Deposit growth", 1.1),
           ("solvency", "Solvency", 1.0), ("combined_ratio", "Combined ratio", 1.1), ("sbc_share", "SBC / revenue", 1.1), ("fcf_margin", "FCF margin", 1.0)]


def is_lender_set(cos: list) -> bool:
    """Whether most of these companies are banks, lenders or insurers (their figures are read on lenders' measures)."""
    cos = [c for c in cos or [] if c.get("status") != "unverified"]
    return bool(cos) and sum(1 for c in cos if c.get("bank")) * 2 >= len(cos)


def co_cols(cos: list) -> list[tuple]:
    """The figure columns for a table of these companies: lenders' own measures only where a lender is among them."""
    bank = any(c.get("bank") and c.get("profile") != "insurer" for c in cos or [])        # R25: an insurer is no bank
    have = {k for k in FAMILY_COLS if any(c.get(k) is not None for c in cos or [])}
    return [c for c in CO_COLS if (bank or c[0] not in LENDER_ONLY) and (c[0] not in FAMILY_COLS or c[0] in have)]


def col_fmt(key: str, rng: bool = False):
    """How a figure column's median (or range) prints: a solvency ratio in times, every other share or change in %."""
    return (lambda x: _times(x, 2)) if key == "solvency" else _pc          # LIVE7A-014: a range's figures with the real minus too


def co_cell(c: dict, key: str, amt) -> str:
    if key in (c.get("nc") or ()):            # R27: on another basis than its table's (metric_registry: not comparable)
        return "n.c."
    if key == "revenue":
        return amt(c.get("revenue"))
    if key == "ebitda":
        return _pcw(c.get("ebitda"), c.get("ebitda_dp") == 0)
    if key == "net":
        return _pc(c.get("net")) + (ONE_OFF if c.get("one_off") else "")
    if key in ("deposit_growth", "sales_1y", "advances_growth"):
        return _chg(c.get(key))
    if key == "solvency":
        return _times(c.get(key), 2)
    if key == "official_industry":
        from .intel.theme_base import plain_industry
        return plain_industry(c.get(key)) or "–"
    return _pc(c.get(key))


def promoter_words(up: int, down: int, n: int) -> str:
    """The quarter's promoter-stake moves in plain words (R21: "rose at 0 and fell at 8 of 32" read awkwardly): the larger count first."""
    if not up and not down:
        return f"Promoters' stake was unchanged at all {n} companies with a filing last quarter."
    first, second = (("fell", down), ("rose", up)) if down >= up else (("rose", up), ("fell", down))
    rest = "none" if not second[1] else f"{second[1]}"
    return f"Promoters' stake {first[0]} at {first[1]} of {n} companies last quarter and {second[0]} at {rest}."


def quarter_words(q: dict) -> str:
    """The quarter's medians, each with its own count, the same counts its slide's tiles show (R20: "net profit +217.1% (3 companies)" beside
    "2 up, 0 down")."""
    sales, profit = q.get("sales") or {}, q.get("profit") or {}
    out = f"Quarter to {q['quarter']}: median revenue {_chg(sales['median'])} on a year before ({_n(sales['n'], 'company', 'companies')})"
    if profit.get("n", 0) >= MIN_BASE:
        out += f", net profit {_chg(profit['median'])} ({_n(profit['n'], 'company', 'companies')})"
    return out


def fx_words(cur: str, rate: float, region: str | None = None) -> str:
    """A rate as people read it: "1 USD = 31.25 TWD" for a currency worth less than a dollar, else "1 EUR = 1.0800 USD"."""
    home = "USD" if region != "IN" else "INR"
    return f"1 {cur} = {rate:.4f} {home}" if rate >= 0.5 else f"1 {home} = {1 / rate:,.2f} {cur}"


def names5(cos: list) -> str:
    """Up to five companies by name, and how many more (R19: a list of companies beyond a count and five names is no page of its own)."""
    names = [c.get("name") or c.get("symbol") or "" for c in cos or []]
    return ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")


def cover_line(v: dict, sector: str, total: int, cap, us: bool) -> str:
    """The cover's sentence when the AI wrote no overview (R18: "Every listed company in the theme, by layer..." isn't a sentence about the
    theme): how many listed companies, where, what they are worth together and the largest, all from the figures."""
    size = (v.get("sections") or {}).get("size") or {}
    big = [x["name"] for x in size.get("biggest") or []][:3]
    where = "listed in the US" if us else "listed in India"
    wv = size.get("with_value") or 0
    # one denominator for the theme's market value (R20: "worth ₹37.4 lakh cr" over 20 beside "18 with a market value")
    adj = len(v.get("adjacent") or [])
    core = f" core members (the {adj:,} adjacent participants apart)" if adj else ""         # d53: the theme's size is of its core members
    worth = ((f", worth {cap(size['total_cap'])} together" if wv >= total else
              f"; the {wv:,}{core} with figures and a market value are worth {cap(size['total_cap'])} together") if size.get("total_cap") else "")
    lead = (f"; the largest are {', '.join(big[:-1])} and {big[-1]}" if len(big) > 1 else f"; the largest is {big[0]}") if big else ""
    return f"{sector}: {_n(total, 'company', 'companies')} {where}{worth}{lead}."


# ---------- R25 (the owner's outside review of the R23 decks): one floor for comparisons, "N of M", every sentence checked, how figures are built ----------
def companies_cell(n: int, listed: int | None) -> str:
    """A layer's "Companies" cell in a table of layers (lane m1, the live R32 Semiconductors deck: "15" here, "14 of 17" on the layer's page
    and in the appendix): the companies in its calculations, "of" those its page lists where that is more, so the two scopes are named
    wherever they differ; each median beside it is "of" the first."""
    return f"{n} of {listed}" if listed and listed > n else str(n)


COMPANIES_NOTE = "Companies: those in the layer's calculations, “of” those the layer lists where some are left out (who and why: the layer's page)."


def _of_n(n: int, of: int | None) -> str:
    """A count beside its group's own: "5 of 6" when the figure is of fewer companies than the group has, else "5" (R25)."""
    return f"{n} of {of}" if of and n < of else str(n)


CHAIN_FAMILY_COLS = (("cet1", "CET1", 0.95), ("solvency", "Solvency", 1.0), ("combined_ratio", "Combined ratio", 1.15),
                     ("sbc_share", "SBC / revenue", 1.15), ("fcf_margin", "FCF margin", 1.05))


def chain_family_cols(rows: list) -> list[tuple]:
    """The value chain's columns of the families' filed figures that some layer has a median of (R25: a layer's columns follow its family;
    drop_empty takes away the rest)."""
    return [c for c in CHAIN_FAMILY_COLS if any(r.get(c[0]) is not None for r in rows)]


def unranked_words(chain: dict) -> str:
    """"Shown, not ranked: A, a different kind of business; B and C, fewer than 5 companies with the figure." (m2: each layer a table or
    chart shows a median of beside a ranking that leaves it out, with why, theme_data.unranked_rows); "" when every shown layer is ranked."""
    by: dict = {}
    for r in chain.get("unranked") or []:
        by.setdefault(r["why"], []).append(r["layer"])
    join = lambda xs: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]      # noqa: E731
    return ("Shown, not ranked: " + "; ".join(f"{join(xs)}, {why}" for why, xs in by.items()) + ".") if by else ""


def intensity_note(chain: dict) -> str:
    """Why the value chain's layers are not ranked when their capital for each unit of revenue differs (n1, the outside review of the live
    R33 Chemicals deck: "more than threefold", the figures nowhere): each such layer's median company's capital (book equity plus debt)
    over its revenue, how many times the lowest the highest is, and the threshold (theme_data.INTENSITY_FACTOR); "" when that is not why."""
    from .intel.theme_data import CAPITAL_PROXY, INTENSITY_FACTOR, INTENSITY_WORD
    if INTENSITY_WORD not in str(chain.get("line") or ""):
        return ""
    names = set(chain.get("not_ranked") or [])
    rows = [r for r in chain.get("rows") or [] if r.get("layer") in names and (r.get("intensity") or 0) > 0]
    if len(rows) < 2:
        return ""
    lo, hi = min(rows, key=lambda r: r["intensity"]), max(rows, key=lambda r: r["intensity"])
    each = "; ".join(f"{r['layer']} {r['intensity']:.2f}" for r in rows)
    # ex49 (R48): labelled as the proxy it is, never as proof that layers are comparable
    return (f"Capital for each unit of revenue ({CAPITAL_PROXY}; over the latest year's revenue, the layer's median company): {each}. "
            f"{hi['layer']}'s is {hi['intensity'] / lo['intensity']:.1f} times {lo['layer']}'s; layers are ranked only where the highest is "
            f"at most {INTENSITY_FACTOR:g} times the lowest, and only when they also share a way of earning and a business model.")


def compare_note(chain: dict, key: str) -> str:
    """The value chain's footnote on how layers are compared: the one floor of a ranking (theme_data.HEADLINE_MIN: the headline's and the
    marks', m2: the footnote said 3 while the headline ranked on 5), each shown layer that is not ranked with why, and the floor a median
    is shown on (theme_data.COMPARE_MIN)."""
    from .intel.theme_data import COMPARE_MIN, HEADLINE_MIN
    what = "return on equity" if key == "roe" else "EBITDA margin"
    shown = f" A median is shown for {COMPARE_MIN} companies or more."
    un = unranked_words(chain)
    if chain.get("highest"):
        return (f"Highest median {what} in green, lowest in red, among the layers ranked: those with at least {HEADLINE_MIN} companies with the figure"
                + (" and one kind of business" if "one kind of business" in str(chain.get("line") or "") else "")
                + (f". {un}" if un else "; any other layer is shown, not ranked.") + shown)
    return f"A layer is ranked only on a median of at least {HEADLINE_MIN} companies with the figure; a layer with fewer is shown, not ranked." + shown


def bar_marks(chain: dict, charted: list, key: str) -> tuple[list, list]:
    """(labels, colours) of the value chain's bars (m2: the chart marks what the headline does not rank): each layer with its count, an
    unranked one with "not ranked" in its label and a grey bar; the highest green, the lowest red, the other ranked layers blue."""
    mark = {chain.get("highest"): UP, chain.get("lowest"): DOWN}
    out = {r["layer"] for r in chain.get("unranked") or []} if chain.get("highest") else set()
    cats = [f"{r['layer']} ({_of_n(r.get(key + '_n') or 0, r.get('n'))}{', not ranked' if r['layer'] in out else ''})" for r in charted]
    return cats, [MUTED if r["layer"] in out else mark.get(r["layer"], BLUE) for r in charted]


def top_of(rows: list, value, count):
    """The one row with the highest `value(row)` among those whose figure is of at least HEADLINE_MIN companies, when two or more qualify and no
    other ties it; else None (R25: a highest is said only against another layer on the same floor; m2: the one floor of every ranking)."""
    from .intel.theme_data import HEADLINE_MIN
    have = sorted((r for r in rows if value(r) is not None and (count(r) or 0) >= HEADLINE_MIN), key=value)
    return have[-1] if len(have) >= 2 and value(have[-1]) != value(have[-2]) else None


NOTES_TITLE = "How the figures are built"
# each figure a theme deck can show: (its name, what it measures and how it is worked out, its period and source, its limitation); facts about
# the figure only, nothing on what a level of it means for a company (R25). Short, so a deck's figures fit one page.
# R27: read from the one registry of figures (intel/metric_registry.py: definition, period and source, limitation), never written twice
def _registry_notes() -> dict:
    from .intel.metric_registry import METRICS
    return {m.id: (m.label, m.definition, m.source, m.limit) for m in METRICS if not m.group}


METRIC_NOTES = _registry_notes()
_NOTE_LABELS = {"Revenue": "revenue", "Growth": "sales_1y", "Revenue growth, 1 year": "sales_1y", "EBITDA margin": "ebitda", "EBITDA": "ebitda",
                "Net margin": "net", "Net": "net", "ROCE": "roce", "ROE": "roe", "NII / assets": "nii_assets", "Gross NPA": "gnpa", "GNPA": "gnpa",
                "Net NPA": "nnpa", "Deposit growth": "deposit_growth", "P/E": "pe", "P/B": "pb", "EV/EBITDA": "ev_ebitda", "Market value": "cap",
                "Solvency": "solvency", "Combined ratio": "combined_ratio", "SBC / revenue": "sbc_share", "FCF margin": "fcf_margin",
                "Capex / revenue": "capex_share", "Inventory days": "inventory_days", "R&D / revenue": "rd_share"}
_NOTE_ORDER = ("revenue", "sales_1y", "ebitda", "net", "roce", "roe", "nii_assets", "gnpa", "nnpa", "deposit_growth", "pe", "pb", "ev_ebitda", "cap")


def shown_metrics(slides: list) -> list[str]:
    """The figures a deck shows, by key, in one order: from its tables' headings and first column (a measure's row), its charts' titles and its
    tiles (R25: the notes page explains only these). A sector page's columns are its family's filed figures; a filed figure takes the place of the
    page's own of the same name (one number per metric)."""
    from .intel.metric_registry import METRICS
    BY_KEY = {m.id: (m.id, m.label) for m in METRICS if m.group}
    by_label = {m[1]: k for k, m in BY_KEY.items()}
    got = []

    def add(k):
        if k and k not in got:
            got.append(k)

    def label_key(text):
        t = str(text or "").strip()
        if t in _NOTE_LABELS:
            return _NOTE_LABELS[t]
        m = re.match(r"(?:Median )?([A-Za-z/ ]+?)(?:,| \(| by | and |$)", t)
        return _NOTE_LABELS.get(m.group(1).strip()) if m else None
    for s in slides:
        sector = s.title.startswith(SECTOR_TITLE)
        for b in s.blocks:
            if b["kind"] == "table":
                for h in b.get("head") or []:
                    add(by_label.get(h) if sector else label_key(h))
                if (b.get("head") or [""])[0] in ("Median", "Measure"):
                    for r in b.get("rows") or []:
                        if not isinstance(r, dict):
                            add(label_key(r[0]))
            elif b["kind"] in ("hbars", "columns", "lines"):
                for part in re.split(r" and |, ", re.sub(r"^Median ", "", str(b.get("title") or ""))):
                    add(label_key(part))
            elif b["kind"] == "stats":
                for it in b.get("items") or []:
                    if isinstance(it, (tuple, list)):
                        add(label_key(it[0]))
    filed = {BY_KEY[k][1] for k in got if k in BY_KEY}
    page = [k for k in _NOTE_ORDER if k in got and METRIC_NOTES[k][0] not in filed]
    return page + [k for k in got if k in BY_KEY]


# a figure's limitation in a deck with no bank, lender or insurer: no word on families the deck doesn't have (R25)
_NO_FINANCIALS = {"ebitda": "Some companies file whole points", "roce": "Latest reported; its year can differ from the margins'",
                  "roe": "Debt raises it", "ev_ebitda": "n/a where debt, cash or EBITDA isn't stored"}


def metric_note_rows(keys: list[str], financials: bool = True) -> list[list[str]]:
    """The notes page's rows for these figures: name, what it measures and how it is worked out, its period and source, its limitation (R25),
    each read from the registry of figures (R27: metric_registry, one source of truth); `financials`: whether the deck has a bank, lender or
    insurer (else no limitation names them)."""
    from .intel.metric_registry import BY_ID, note_row
    return [note_row(k, financials, _NO_FINANCIALS) for k in keys if k in BY_ID]


def notes_slides(slides: list, eyebrow: str, financials: bool = True) -> list[Slide]:
    """One compact page (two at most) on how the figures the deck shows are built (R25): each figure's measure, arithmetic, period and source,
    and limitation, in one table; nothing about what a level of a figure means."""
    rows = metric_note_rows(shown_metrics(slides), financials)
    if not rows:
        return []
    if any(b["kind"] == "table" and any(not isinstance(r, dict) and r and str(r[0]).startswith(("P/E, companies with", "ROCE, companies with",
                                                                                            "Revenue growth, 3 years a year, companies with"))
                                        for r in b.get("rows") or []) for s in slides for b in s.blocks):
        rows.append(list(PEERS_ROW))            # R27 (P2): who the peers are, said once here, not on the valuation page
    head, widths = ["Figure", "What it measures, how it is worked out", "Period and source", "Limitation"], [1.6, 5.1, 2.6, 2.8]
    pages = table_pages(head, rows, widths, CW, BOT - TOP, most=26)          # every word shown: wrapped, never cut
    out = []
    for k, chunk in enumerate(pages):
        s = Slide(NOTES_TITLE + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                  "Each figure this deck shows: what it measures, how it is worked out, its period and source, and its limits", eyebrow=eyebrow)
        s.add("table", (M, TOP, CW, min(BOT - TOP, table_height(head, chunk, widths, CW))), head=head, rows=chunk, widths=widths,
              numeric=[False] * 4, tight=True)
        out.append(s)
    return out


def aggregate_margin_rows(mg: dict) -> list[list[str]]:
    """The aggregate EBITDA margin (all the companies' operating profit over their revenue) of the last two years, as rows of the margins table, so
    the figures the findings and the questions state are in a table (R25)."""
    pe = [(y, x) for y, x in zip(mg.get("years") or [], mg.get("ebitda") or []) if x is not None]
    return [[f"EBITDA margin, all together, {pe[-2][0]} to {pe[-1][0]}", f"{_pc(pe[-2][1])} → {_pc(pe[-1][1])}", str(mg.get("n") or "–"), "–"]] if len(pe) >= 2 else []


CLAIM_CARDS = ("Key findings",)                  # the slides whose cards are findings; the questions card is checked wherever it sits
# m2: a ranking's own scope ("Among the 2 layers with at least 5 companies with the figure", "fewer than 5 companies with the figure") is the
# rule and how many layers passed it, not a figure a table shows
_CHECK_SKIP = re.compile(r"within \d+% of|\d+% or more|\b\d+% (?:above|below) or|\(\d+% of (?:the (?:combined )?market value of [^)]*|value)\)|"
                         r"\bAmong (?:the \d+ )?layers (?:with|of) at least \d+ companies with the figure|"
                         r"\b(?:at least|fewer than) \d+ companies with the figure")


def _deck_figures(slides: list) -> dict:
    """Every figure the deck's tables, charts and tiles show (theme_data.shown_numbers), with each table's count of rows."""
    from .intel.theme_data import shown_numbers
    texts = []
    for s in slides:
        if s.title == "Contents":            # the contents repeat the parts' headlines: a sentence never vouches for itself
            continue
        for b in s.blocks:
            if b["kind"] == "table":
                rows = [r for r in b.get("rows") or [] if not isinstance(r, dict)]
                texts += [x if not isinstance(x, dict) else x.get("text") for r in rows for x in r] + [len(rows)]
            elif b["kind"] == "stats":
                texts += [x for it in b.get("items") or [] for x in (it if isinstance(it, (tuple, list)) else [])]
            elif b["kind"] in ("hbars", "columns", "lines"):
                texts += list(b.get("vals") or []) + list(b.get("cats") or []) + [b.get("title")] + [len(b.get("cats") or [])]
                texts += [x for ser in b.get("series") or [] for x in (ser[1] if isinstance(ser, (tuple, list)) else [])]
            elif b["kind"] == "flow":
                texts += [len(b.get("items") or [])]
    out = shown_numbers(texts)
    for s in slides:                         # a gap between two figures of one column ("within 1 point of each other")
        for b in s.blocks:
            if b["kind"] == "table" and s.title != "Contents":
                rows = [r for r in b.get("rows") or [] if not isinstance(r, dict)]
                for c in range(1, len(b.get("head") or [])):
                    col = sorted(shown_numbers([r[c] for r in rows if c < len(r) and not isinstance(r[c], dict)])["pct"])
                    out["gaps"] |= {round(abs(a - b_), 2) for i, a in enumerate(col) for b_ in col[i + 1:]}
    return out


PLACEHOLDER = re.compile(r"\{[a-z_]+\}|(?<![A-Za-z] )\bNone\b(?! of| is| has| shows| was| were| are)|\bnan\b|\bundefined\b|\bshown for [a-z]{1,2}\.")


# ---------- m2 (outside review of the live R32 decks): the text itself is checked before a deck is stored ----------
# a doubled word ("outside the the theme"), doubled punctuation ("Inc.. Revenue"), a space before punctuation ("metals , alloys") and a
# hyphen broken off its word ("aero -engines") are repaired on every slide, whatever wrote the sentence (a template, a company's own
# description, a headline), and each repair is logged and counted in the gate. Generic: fixed patterns, no list of sentences.
# n1 (the outside review of the live R33 decks: "Diodes Inc /del/" on a slide): a filer's state or editing token ("/DE/", "/del/", "/NEW/",
# "\\MD\\"), a double space and a trailing comma are taken out of every name, and so of every text a slide shows (tidy_text, clean_name)
NAME_FIXES = (
    (re.compile(r"\s*[/\\][A-Za-z]{2,5}[/\\](?=[\s,.;:)]|$)|^[/\\][A-Za-z]{2,5}[/\\]\s*"), "", "filing token in a name"),
    (re.compile(r"(?<=\S) {2,}(?=\S)"), " ", "double space"),
    (re.compile(r"\s*,\s*$"), "", "trailing comma"),
)


def clean_name(name) -> str:
    """A company's name as a slide shows it: no filer's state or editing token, double space or trailing comma (NAME_FIXES)."""
    t = str(name or "").strip()
    for rx, to, _ in NAME_FIXES:
        t = rx.sub(to, t)
    return t.strip()


_JOIN_WORDS = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "with", "by", "from", "is", "are", "was", "were", "its",
               "their", "this", "these", "than", "as", "be", "it"}
_DOUBLE_OK = {"had", "that", "very", "so", "no", "bye", "more", "many", "much", "far", "long"}       # doubled in ordinary English
_DOUBLED = re.compile(r"\b([A-Za-z]{2,})(\s+)\1\b", re.I)
_TEXT_FIXES = (
    (re.compile(r"\b([A-Z][A-Za-z]{0,5})\.\.(?=\s|$)"), r"\1.", "doubled full stop"),            # "Qualys, Inc..": an abbreviation's stop and the sentence's
    (re.compile(r"(?<=[A-Za-z)])\.\.(?=\s+[A-Z(])"), ".", "doubled full stop"),                 # "Inc.. Revenue": the sentence's own stop
    (re.compile(r"(?<![.])\.\.(?![.])(?=\s|$)"), "…", "two dots for an ellipsis"),             # a headline cut by its source: "say.."
    (re.compile(r"([,;:!?])(?:\s*\1)+"), r"\1", "doubled punctuation"),                         # ",,", "; ;"
    (re.compile(r"[,;:](?=\.(?:\s|$))"), "", "punctuation before a full stop"),                 # ",." and ";."
    (re.compile(r"(?<=[A-Za-z)%’'\"]) +(?=[,;:!?](?:\s|$))|(?<=[0-9]) +(?=[,;!?](?:\s|$))"), "", "space before punctuation"),   # "1 : 2" stays
    (re.compile(r"(?<=[A-Za-z)%]) +(?=\.(?:\s|$))"), "", "space before a full stop"),
    (re.compile(r"\( +"), "(", "space inside a bracket"),
    (re.compile(r"(?<=\S) +\)"), ")", "space inside a bracket"),
    (re.compile(r"(?<=[a-z]) -(?=[a-z])"), "-", "hyphen broken off its word"),                  # "aero -engines"
    (re.compile(r"(?<=[a-z])- (?=[a-z])(?!(?:and|or|to|as|than|but|nor)\b)"), "-", "hyphen broken off its word"),   # "aero- engines"; "pre- and post" stays
) + NAME_FIXES


def _undouble(m) -> str:
    word, rest = m.group(1), m.group(0)[len(m.group(1)) + len(m.group(2)):]
    low = word.lower()
    if low in _JOIN_WORDS or (rest.islower() and len(word) >= 3 and low not in _DOUBLE_OK):
        return word                      # "the the", "The the", "companies companies"; a name ("Bora Bora") and "had had" stay
    return m.group(0)


def tidy_text(text) -> tuple[str, list[str]]:
    """(the text with its mechanical defects repaired, what was repaired) (m2): a doubled word, doubled punctuation, a space before
    punctuation or inside a bracket, a hyphen broken off its word. A text with none is given back as it is; a figure, a date, a name and
    a three-dot ellipsis are never touched."""
    if not isinstance(text, str) or len(text) < 3:
        return text, []
    out, why = text, []
    got = _DOUBLED.sub(_undouble, out)
    if got != out:
        out, why = got, ["doubled word"]
    for rx, to, name in _TEXT_FIXES:
        got = rx.sub(to, out)
        if got != out:
            out = got
            why.append(name)
    return out, why


def text_flags(text) -> list[str]:
    """The mechanical defects a text holds (tidy_text's names); [] for a clean one."""
    return tidy_text(text)[1]


def untwin(text) -> tuple[str, list[str]]:
    """(the text with an immediately repeated word said once, ["repeated word"] or []) (R40, the owner's review of the live Release 39
    decks: "outside the the theme"): "the the", "Of of", "companies companies", whatever the case; a name ("Bora Bora", "R R Kabel") and
    "had had" stay (tidy_text's own rule for a doubled word). Run again on the finished pages, after the last text is fitted (layout_gate)."""
    if not isinstance(text, str) or len(text) < 3:
        return text, []
    got = _DOUBLED.sub(_undouble, text)
    return (got, ["repeated word"]) if got != text else (text, [])


_TOKENS = (
    (re.compile(r"(?:^|(?<=\s))[/\\][A-Za-z]{2,5}[/\\](?=[\s,.;:)]|$)"), "a filing token"),
    (re.compile(r"\{[^{}\n]{0,40}\}"), "a template field"),
    (re.compile(r"^\s*(?:None|none|null|nan|NaN|undefined)\s*$|(?<![.!?]\s)(?<!^)\bNone\b(?! of| is| has| shows| was| were| are)|\bnan\b|\bNaN\b"), "a missing value printed as a word"),
    (re.compile(r"\bTBD\b|\blorem\b", re.I), "placeholder text"),
)


def token_flags(text) -> list[str]:
    """What a slide's text holds that was never filled in (n1): a filing token ("/DE/"), a template field ("{name}"), a missing value
    printed as a word ("None", "nan"; "None of them…" opening a sentence is English) or placeholder text ("TBD", "lorem")."""
    t = str(text or "")
    return [why for rx, why in _TOKENS if rx.search(t)]


def slide_texts(s) -> list[str]:
    """Every text one slide prints: its title, headline, paragraphs, table cells and headings, card titles, values and lines, tiles, chart
    labels."""
    out = [s.title, s.subtitle]
    for b in s.blocks:
        out += list(b.get("paras") or []) + list(b.get("head") or []) + list(b.get("cats") or [])
        out += [r["group"] if isinstance(r, dict) else _cell_text(c) for r in b.get("rows") or [] for c in ([r] if isinstance(r, dict) else r)]
        if isinstance(b.get("title"), str):
            out.append(b["title"])
        for it in b.get("items") or []:
            if isinstance(it, (tuple, list)):
                out += [str(x) for x in it]
            elif isinstance(it, dict):
                out += [it.get(k) for k in ("title", "value", "note", "text", "sub")] + list(it.get("lines") or [])
    return [str(x) for x in out if isinstance(x, str) and x]


def tidy_deck(slides: list, repair=None) -> list[dict]:
    """Every sentence, label and cell of every slide through tidy_text (m2), as whole_deck sends every figure through one formatter; the
    repairs made: [{"slide", "text" (as it was), "fixed", "why"}], logged. `repair`: another repair of the same shape (R40: untwin)."""
    import logging
    log = logging.getLogger("stratlab.deck")
    done: list[dict] = []
    repair = repair or tidy_text

    def fix(x, where):
        got, why = repair(x)
        if why:
            done.append({"slide": where, "text": x, "fixed": got, "why": ", ".join(why)})
        return got

    def cell(x, where):
        return {**x, "text": fix(x["text"], where)} if isinstance(x, dict) and isinstance(x.get("text"), str) else fix(x, where)
    for s in slides:
        t = s.title
        s.title, s.subtitle = fix(s.title, t), fix(s.subtitle, t)
        for b in s.blocks:
            if b.get("paras"):
                b["paras"] = [fix(x, t) for x in b["paras"]]
            if b.get("rows"):
                b["rows"] = [({**r, "group": fix(r["group"], t)} if "group" in r else r) if isinstance(r, dict) else [cell(x, t) for x in r]
                             for r in b["rows"]]
            if b.get("head"):
                b["head"] = [fix(x, t) for x in b["head"]]
            if b.get("cats"):
                b["cats"] = [fix(x, t) for x in b["cats"]]
            if isinstance(b.get("title"), str):
                b["title"] = fix(b["title"], t)
            if b["kind"] == "stats":
                b["items"] = [tuple(fix(x, t) for x in it) if isinstance(it, tuple) else it for it in b.get("items") or []]
            elif b.get("items") and isinstance(b["items"][0], dict):
                b["items"] = [{k: ([fix(x, t) for x in val] if k == "lines" and isinstance(val, list) else fix(val, t) if isinstance(val, str) else val)
                               for k, val in it.items()} for it in b["items"]]
    for d in done:
        log.warning("deck text: repaired on %r (%s): %s", d["slide"], d["why"], d["text"])
    return done


def check_deck(slides: list) -> list[dict]:
    """The consistency check before a deck is stored (R25): every percentage, multiple, gap in points and count that a headline (a slide's
    subtitle), a finding or a question states is looked for among the figures the deck's own tables, charts and tiles show, the rows they all
    come from. A headline part or a card line with a figure that isn't there is dropped (never shipped wrong) and logged. The dropped ones."""
    import logging
    from .intel.theme_data import claim_mismatches
    if slides:
        slides[0].tidied = tidy_deck(slides)          # m2: the text's own defects repaired first, so every later check reads the repaired text
    shown = _deck_figures(slides)
    log = logging.getLogger("stratlab.deck")
    dropped = []

    def bad(text):
        return claim_mismatches(_CHECK_SKIP.sub("", text), shown)
    for s in slides[1:]:
        if s.subtitle and s.kind == "content":
            keep = []
            for part in s.subtitle.split("; "):
                miss = bad(part)
                if miss:
                    dropped.append({"slide": s.title, "text": part, "figures": miss})
                else:
                    keep.append(part)
            s.subtitle = "; ".join(keep) if keep and keep[0] == s.subtitle.split("; ")[0] else ""
        for b in s.blocks:
            if b["kind"] != "cards" or not (s.title in CLAIM_CARDS or any(it.get("title") == "Questions the figures raise" for it in b.get("items") or [])):
                continue
            for it in b["items"]:
                lines = []
                for ln in it.get("lines") or []:
                    miss = bad(ln) if isinstance(ln, str) else []
                    if miss:
                        dropped.append({"slide": s.title, "text": ln, "figures": miss})
                    else:
                        lines.append(ln)
                it["lines"] = lines
            b["items"] = [it for it in b["items"] if it.get("lines")]
    # R34 (GPT review of R31.7: "No listed company is shown for x."): a sentence that still holds a placeholder (a one-letter name, an
    # unfilled {field}, None, nan) is dropped, never shipped
    for s in slides[1:]:
        if s.subtitle and PLACEHOLDER.search(s.subtitle):
            dropped.append({"slide": s.title, "text": s.subtitle, "figures": ["placeholder"]})
            s.subtitle = ""
        for b in s.blocks:
            if b["kind"] == "text" and b.get("paras"):
                keep = [p for p in b["paras"] if not (isinstance(p, str) and PLACEHOLDER.search(p))]
                dropped += [{"slide": s.title, "text": p, "figures": ["placeholder"]} for p in b["paras"] if p not in keep]
                b["paras"] = keep
    gone = {d["text"] for d in dropped}
    for s in slides:                         # the contents repeat a part's headline: a dropped one goes there too
        for b in s.blocks:
            if s.title == "Contents" and b["kind"] == "table":
                b["rows"] = [r if isinstance(r, dict) else [r[0], "; ".join(p for p in str(r[1]).split("; ") if p not in gone) or r[0], *r[2:]]
                             for r in b["rows"]]
    for d in dropped:
        log.warning("deck check: dropped a sentence on %r whose figures %s no table shows: %s", d["slide"], d["figures"], d["text"])
    return dropped


# ---------- R27: the publication gate ----------
# before a deck is stored, a checklist runs over its slides; a failing sentence or figure is dropped (never shipped) and logged, and the result
# (pass or fail per item, what was dropped) is stored with the deck and shown in Admin -> Library (the owner's outside review of the R26 decks)
CAUSE_WORDS = re.compile(r"\b(?:because|driven by|due to|owing to|thanks to|as a result of|caused by|on the back of|led by|attributable to|"
                         r"explained by|reflects?|reflecting|one-off gains?|boosted by|dragged by|weighed (?:on|down) by)\b", re.I)
# a business that buys or sells goods is a fact, not advice. n1 (the outside review of the live R33 Metals deck: "turning metal they buy into
# pipes" dropped as advice): "buy", "sell" and "accumulate" are advice only as a recommendation ("buy the stock", "a buy", "should sell",
# "accumulate on dips", "buy now"); every other use of them is a company's own trade and is read past
_TRADE_ADVICE = re.compile(
    r"\b(?:should|must|to consider|consider|a|strong|rated|rating|upgraded to|downgraded to|time to)"
    r"\s+(?:not\s+)?(?:buy|sell|accumulate)\b(?!-)"
    r"|\b(?:buy|sell|accumulate)\s+(?:(?:the|its|this|these|their|more|some|our)\s+)?(?:shares?|stocks?|stakes?|positions?|rating|calls?|signals?|"
    r"now|on (?:dips|weakness|strength|declines)|the dips?|the rally|for the long term)\b"
    r"|^\W*(?:buy|sell|accumulate)\b(?!-|s\b)", re.I)
_TRADE_VERBS = re.compile(r"\b(?:buy|sell)(?:s|ing|ers?|-?backs?)?\b|\bsold\b|\baccumulat\w*", re.I)
_BARE_SHARE = re.compile(r"\b\d+(?:\.\d+)?% of (?:the (?:theme's )?)?(?:market |combined )?value\b(?! of)", re.I)
_PERIOD = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}\b")
_RANKING = re.compile(r"\b(?:highest|lowest|fastest|slowest)\b", re.I)
_OF_COS = re.compile(r"\b(\d[\d,]*) of (\d[\d,]*) (?:compan(?:y|ies)|banks|insurers)\b")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9⟦(†–])")
MISSING_MARKS = {"None", "none", "nan", "NaN", "N/A", "NA", "-", "—", "null"}     # printed as "–" (missing); "n/a" and "not comparable" are their own
MARKS_LINE = ("Three marks, never one: – not filed or not stored; n/a the measure doesn't apply to that kind of business; not comparable no "
              "comparable peer set.")
PEERS_ROW = ["Comparable peers", f"Same sector and accounts, then half to twice the market value, outside this theme; under {PEER_MIN}, no set",
             "Last close", "Only the company's own sector"]
NOTES_POINTER = "⟦How the figures are built⟧"
GATE_ITEMS = (("sourced", "Figures have a period, source and formula"), ("reproduce", "Headlines reproduce from the tables"),
              ("reconcile", "Counts, periods, shares and rounding reconcile"), ("classified", "Every company has a primary classification"),
              ("applicable", "Metrics pass applicability"), ("peers", "Peers pass comparability"),
              ("headline", "Headline findings pass sample and coverage"), ("marks", "Missing, n/a and not comparable are distinct"),
              ("prose", "No advice words, forecasts or unsupported causes"), ("layout", "No headline, label or sentence is cut short"))
GATE_KEEP = 20                    # dropped sentences kept with the stored result (the log has every one)


def prose_flag(text: str) -> str | None:
    """Why a line of prose can't ship (R27): an inferred cause ("because", "driven by", "one-off gain") or a word that turns a fact into advice
    or a forecast (blog_research.advice_words, the newsletters' list); None when it can. "Sells", "buyback" describe a business, not advice."""
    m = CAUSE_WORDS.search(text or "")
    if m:
        return f"cause: {m.group(0)}"
    from .blog_research import advice_words
    m = _TRADE_ADVICE.search(text or "")
    if m:
        return f"advice or forecast: {m.group(0).strip()}"
    bad = advice_words({"title": _TRADE_VERBS.sub("", text or "")})
    return f"advice or forecast: {bad}" if bad else None


def _deck_periods(slides: list) -> set:
    """Every period ("Sep 2026") the deck's tables, charts and tiles print: a sentence's period is one of these (R27)."""
    got = set()
    for s in slides:
        for b in s.blocks:
            vals = []
            if b["kind"] == "table":
                vals = list(b.get("head") or []) + [x if not isinstance(x, dict) else x.get("text") for r in b.get("rows") or [] if not isinstance(r, dict) for x in r]
            elif b["kind"] in ("hbars", "columns", "lines"):
                vals = list(b.get("cats") or []) + [b.get("title")]
            elif b["kind"] == "stats":
                vals = [x for it in b.get("items") or [] for x in (it if isinstance(it, (tuple, list)) else [])]
            for x in vals:
                got |= set(_PERIOD.findall(str(x or "")))
    return got


def reconcile_flag(text: str, counts: dict, periods: set) -> str | None:
    """Why a sentence doesn't reconcile with the deck (R27, P0): a share of value with no denominator; a count of companies considered,
    confirmed or with figures that isn't the deck's one count; a period no table, chart or tile shows. None when it reconciles."""
    if _BARE_SHARE.search(text):
        return "a share of value with no denominator"
    for pat, key in ((r"\b(\d[\d,]*) with figures\b", "with_figures"), (r"\bwith figures (\d[\d,]*)\b", "with_figures"),
                     (r"\bConsidered (\d[\d,]*)\b", "considered"), (r"\bconfirmed (\d[\d,]*)\b(?! of)", "confirmed")):
        for m in re.finditer(pat, text):
            want = counts.get(key)
            if want is not None and int(m.group(1).replace(",", "")) != want:
                return f"{key.replace('_', ' ')} {m.group(1)}, the deck's count is {want}"
    def year_on(p):                  # the period a year after: "Sep 2025" is the year-ago base of "Sep 2026"
        mon, yr = p.split()
        return f"{mon} {int(yr) + 1}"
    found = _PERIOD.findall(text)
    miss = [p for p in found if p not in periods and not (year_on(p) in periods and year_on(p) in found)]
    return f"period {miss[0]} is in no table" if miss else None


_LAYER_PAGE = re.compile(r"^Layer \d+ · (.+)$")
_HEAD_BOTH = re.compile(r"^(\d[\d,]*) compan(?:y|ies) \((\d[\d,]*) in the layer's calculations\)")
_HEAD_ONE = re.compile(r"^(\d[\d,]*) compan(?:y|ies), revenue")
_ROLL_OF = re.compile(r"In the layer's calculations \((\d[\d,]*) of (\d[\d,]*)\)")
_CELL_OF = re.compile(r"^(\d[\d,]*)(?: of (\d[\d,]*))?\b")


def layer_count_statements(slides: list) -> dict:
    """Every count of a layer's companies the deck states, as {layer: [((in its calculations, listed), slide title)]} (lane m1): the
    "Companies" cell of a table of layers ("14 of 17", or "15" alone: 15 listed and every one counted), a layer page's head ("17 companies
    (14 in the layer's calculations)", or "15 companies, revenue ..."), its roll ("In the layer's calculations (14 of 17)") and the
    appendix's roll ("14 of 17: ...")."""
    num = lambda x: int(str(x).replace(",", ""))          # noqa: E731
    got: dict = {}

    def say(layer, n, listed, where):
        got.setdefault(str(layer), []).append(((num(n), num(listed if listed else n)), where))
    for s in slides:
        page = _LAYER_PAGE.match(str(s.title or ""))
        if page:
            for rx in (_HEAD_BOTH, _HEAD_ONE):
                m = rx.match(str(s.subtitle or ""))
                if m:
                    say(page.group(1), m.group(2) if rx is _HEAD_BOTH else m.group(1), m.group(1), s.title)
                    break
        for b in s.blocks:
            if b["kind"] == "text" and page:
                for p in b.get("paras") or []:
                    for m in _ROLL_OF.finditer(p if isinstance(p, str) else ""):
                        say(page.group(1), m.group(1), m.group(2), s.title)
            if b["kind"] != "table" or not b.get("head") or b["head"][0] != "Layer":
                continue
            at = next((i for i, h in enumerate(b["head"]) if h in ("Companies", "In its calculations")), None)
            if at is None:
                continue
            for r in b.get("rows") or []:
                if isinstance(r, dict) or len(r) <= at:
                    continue
                cell = lambda x: str(x.get("text") if isinstance(x, dict) else x)          # noqa: E731
                m = _CELL_OF.match(cell(r[at]).strip())
                if m:
                    say(cell(r[0]), m.group(1), m.group(2), s.title)
    return got


def layer_count_flags(slides: list) -> list[dict]:
    """What breaks "one set of records behind every count" (lane m1, the live R32 Semiconductors deck: 15 equipment companies in the
    value-chain table, 14 of 17 on the layer's page and in the appendix): a layer whose pages state two different counts without naming
    the scope. Every statement of a layer gives the same pair (in its calculations, listed); a count alone says both are that number.
    [{"layer", "slide", "text"}], [] when they agree."""
    out = []
    for layer, said in layer_count_statements(slides).items():
        pairs = {p for p, _ in said}
        if len(pairs) > 1:
            first = said[0]
            other = next(x for x in said if x[0] != first[0])
            words = lambda x: (f"{x[0][0]} of {x[0][1]}" if x[0][0] != x[0][1] else f"{x[0][0]}") + f" on “{x[1]}”"        # noqa: E731
            out.append({"layer": layer, "slide": other[1], "text": f"{layer}: {words(first)}, {words(other)}"})
    return out


def counts_flags(counts: dict) -> list[str]:
    """What breaks the order of the deck's four counts (R28, the owner's review: "confirmed 59 (of 60 checked) · with figures 60"): each is a
    subset of the one before, so with figures <= confirmed <= considered, and every calculation's count <= with figures. [] when they hold."""
    out = []
    considered, wf = counts.get("considered") or 0, counts.get("with_figures") or 0
    confirmed = counts.get("confirmed") if counts.get("confirmed") is not None else counts.get("counted")
    if confirmed is not None and confirmed > considered:
        out.append(f"confirmed {confirmed:,} above considered {considered:,}")
    if confirmed is not None and wf > confirmed:
        out.append(f"with figures {wf:,} above confirmed {confirmed:,}")
    elif wf > considered:
        out.append(f"with figures {wf:,} above considered {considered:,}")
    out += [f"{label} {k:,} above with figures {wf:,}" for label, k in counts.get("each") or [] if k > wf]
    return out


def headline_flag(text: str) -> str | None:
    """Why a ranking sentence can't headline (R27): a highest, lowest, fastest or slowest on a figure of fewer than COMPARE_MIN companies or
    under COVERAGE_MIN of its group ("N of M companies")."""
    from .intel.theme_data import COVERAGE_MIN, HEADLINE_MIN
    if not _RANKING.search(text):
        return None
    for a, b in _OF_COS.findall(text):
        n, of = int(a.replace(",", "")), int(b.replace(",", ""))
        if n < HEADLINE_MIN or n < of * COVERAGE_MIN:           # R31: one headline floor
            return f"ranked on {n} of {of}"
    return None


def layer_families(v: dict) -> dict:
    """{layer: its business-model family, "" when it has none} for the map's own layers (theme_base.by_model's `model`)."""
    return {str(x.get("layer")): ((x.get("model") or {}).get("family") or "") if isinstance(x.get("model"), dict) else ""
            for x in v.get("layers") or [] if isinstance(x, dict) and x.get("layer") and not x.get("official")}


def layers_named(text: str, names) -> list[str]:
    """The layers a sentence names, the longest names first so "Power generation" is never read inside "Renewable power generation"."""
    found, rest = [], str(text or "")
    for nm in sorted(names, key=len, reverse=True):
        rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(nm) + r"(?![A-Za-z0-9])")
        if rx.search(rest):
            found.append(nm)
            rest = rx.sub(" ", rest)
    return found


_NOT_RANKED = re.compile(r"Shown, not ranked:.*?(?:\.(?=\s|$)|$)")          # to the sentence's end ("20.0%" is no end)


def ranked_part(text: str) -> str:
    """A sentence without its "Shown, not ranked: ..." clause (R36): the layers named there are said to be outside the ranking, so they
    never count as ranked against the others."""
    return _NOT_RANKED.sub("", text or "")


def family_flag(text: str, families: dict) -> str | None:
    """Why a ranking sentence can't ship (lane m1, the live R32 Real estate and Utilities decks: contractors ranked against developers,
    equipment makers against generators): its highest, lowest, fastest or slowest names layers of different kinds of business (their
    business-model families; a layer with none beside one that has). None when it names one layer, or layers of one family."""
    text = ranked_part(text)
    if not _RANKING.search(text or ""):
        return None
    named = layers_named(text, families)
    if len(named) >= 2 and len({families[n] for n in named}) > 1:
        return "ranks layers of different kinds of business: " + ", ".join(named)
    return None


def family_sweep(slides: list, v: dict) -> list[dict]:
    """Drop every ranking that sets layers of different kinds of business against each other (family_flag): a sentence, a card line, or the
    ranking parts of a headline whose parts together name such layers (each part of "highest ROCE in A; fastest growth in B" names one)."""
    fams = layer_families(v)
    if len(set(fams.values())) < 2:
        return []
    whole = {}
    for s in slides[1:]:
        why = family_flag(s.subtitle, fams) if s.subtitle and s.kind == "content" else None
        if why:
            whole.update({part: why for part in s.subtitle.split("; ") if _RANKING.search(part)})
    return _sweep(slides, lambda t: whole.get(t) or family_flag(t, fams), "headline", claims_only=True)


UNREAD_RANK = "a ranking of layers whose companies' ways of earning were never read"
UNREAD_KIND = "says how it earns is shown and of the layer's kind, where no way of earning was read"
_KIND_SAID = re.compile(r"how (?:it|they) earns? (?:is |are )?shown and (?:is |are )?of the layer's kind|of the layer's kind", re.I)


def unread_sweep(slides: list, v: dict) -> list[dict]:
    """gl50 (R50, the rotating review: the Biotech and Capital goods decks ranked their layers in the headline, and Capital goods said of every
    company "how it earns shown and of the layer's kind", beside the comparison basis's "no way of earning read for these companies"): when
    no layer of the map has a way of earning read, every ranking sentence naming a layer is dropped, and any text saying a company is of the
    layer's kind is listed: both fail the classification item (the pages contradict each other)."""
    fams = layer_families(v)
    if len(fams) < 2 or any(fams.values()):
        return []
    out = _sweep(slides, lambda t: UNREAD_RANK if _RANKING.search(ranked_part(t) or "") and layers_named(t, fams) else None, "classified",
                 claims_only=True)
    for s_ in slides:
        for txt in slide_texts(s_):
            if _KIND_SAID.search(txt):
                out.append({"slide": s_.title, "text": txt, "why": UNREAD_KIND, "rule": "classified"})
    return out


def _sweep(slides: list, judge, rule: str, claims_only: bool = False, text: bool = False) -> list[dict]:
    """Drop every headline part, card line (and, `text`, sentence of a text block) that `judge(text)` faults; the dropped, with the rule. A
    headline that loses its lead part says nothing (check_deck's rule); a card left with no line goes; the contents follow."""
    out = []
    for s in slides[1:]:
        if s.title == "Contents":
            continue
        if s.subtitle and s.kind == "content":
            parts, keep = s.subtitle.split("; "), []
            for part in parts:
                why = judge(part)
                (out.append({"slide": s.title, "text": part, "why": why, "rule": rule}) if why else keep.append(part))
            s.subtitle = "; ".join(keep) if keep and keep[0] == parts[0] else ""
        for b in s.blocks:
            if b["kind"] == "cards":
                if s.title == "Tailwinds and risks":          # the AI's claims, each checked against a dated source of its own
                    continue
                if claims_only and not (s.title in CLAIM_CARDS or any(it.get("title") == "Questions the figures raise" for it in b.get("items") or [])):
                    continue
                for it in b["items"]:
                    lines = []
                    for ln in it.get("lines") or []:
                        why = judge(ln) if isinstance(ln, str) else None
                        (out.append({"slide": s.title, "text": ln, "why": why, "rule": rule}) if why else lines.append(ln))
                    it["lines"] = lines
                b["items"] = [it for it in b["items"] if it.get("lines")]
            elif b["kind"] == "text" and text:
                paras = []
                for para in b.get("paras") or []:
                    keep = []
                    for sent in _SENT.split(para):
                        why = judge(sent)
                        (out.append({"slide": s.title, "text": sent, "why": why, "rule": rule}) if why else keep.append(sent))
                    if keep:
                        paras.append(" ".join(keep))
                b["paras"] = paras
    gone = {d["text"] for d in out}
    for s in slides:
        if s.title == "Contents":
            for b in s.blocks:
                if b["kind"] == "table":
                    b["rows"] = [r if isinstance(r, dict) else [r[0], "; ".join(p for p in str(r[1]).split("; ") if p not in gone) or r[0], *r[2:]]
                                 for r in b["rows"]]
    return out


def _marks(slides: list) -> list[dict]:
    """Every missing figure printed as "–" (R27): a cell that says "None", "N/A", "-" is made "–"; "n/a" (doesn't apply) and "not comparable"
    stay their own. The cells changed."""
    out = []
    for s in slides:
        for b in s.blocks:
            if b["kind"] != "table":
                continue
            for r in b.get("rows") or []:
                if isinstance(r, dict):
                    continue
                for i, x in enumerate(r):
                    if isinstance(x, str) and x.strip() in MISSING_MARKS:
                        out.append({"slide": s.title, "text": f"{r[0]}: {x!r} printed as –", "why": "an unclear mark", "rule": "marks"})
                        r[i] = "–"
    return out


def provenance_flags(slides: list, v: dict) -> list[dict]:
    """R48 (the outside review of the live R46 decks, P2: "every provenance reference resolves, every required appendix row renders"): what
    the finished pages leave out of the figures' provenance. Each checked figure (theme_data.figure_states: verified, not reconciled,
    invalid) has its row on the "Figure sources" pages, once; each data-confidence row that names checked figures points to those pages; each
    comparison the deck records (the "Comparison basis" page) has a row for every layer it compares, with its companies. Each {"slide",
    "text", "why", "rule": "sourced"}."""
    out = []
    recs = source_records(v.get("checks") or {})
    tabs = lambda title: [r for s_ in slides if s_.title == title or s_.title.startswith(title + " (") for b in s_.blocks if b["kind"] == "table"   # noqa: E731
                          for r in b.get("rows") or [] if not isinstance(r, dict)]
    src = tabs(SOURCES_TITLE)
    for x in recs:
        word = HELD_WORDS.get(x["key"], x["key"])
        hits = [r for r in src if f"({x.get('symbol')})" in _cell_text(r[0]) and _cell_text(r[1]).lower().startswith(word.lower())]
        if len(hits) != 1:
            out.append({"slide": SOURCES_TITLE, "text": f"{x.get('name')} ({x.get('symbol')}), {word}",
                        "why": "a checked figure with no source row" if not hits else "a checked figure's source row printed twice", "rule": "sourced"})
    conf = [r for s_ in slides if s_.title == "Data confidence" for b in s_.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)]
    at = next((f"p. {i}" for i, s_ in enumerate(slides, 1) if s_.title.startswith(SOURCES_TITLE)), None)      # once the references are set
    for r in conf:
        said = _cell_text(r[1])
        if _cell_text(r[0]) in ("Verified figures", "Net above EBITDA margin", "Net margin not reconciled", "Figure checks") and \
                f"⟦{SOURCES_TITLE}⟧" not in said and not (at and re.search(rf"\b{re.escape(at)}\b", said)):
            out.append({"slide": "Data confidence", "text": _cell_text(r[0]), "why": "checked figures named with no reference to their source rows", "rule": "sourced"})
    cmp_ = tabs(COMPARE_TITLE)
    for b in v.get("comparisons") or []:
        for g in b.get("groups") or []:
            if not any(_cell_text(r[0]) == g["layer"] and _cell_text(r[-1]) not in ("", "not stored") for r in cmp_):      # ex49: one table a comparison
                out.append({"slide": COMPARE_TITLE, "text": f"{b.get('metric')}: {g['layer']}", "why": "a compared layer with no row of its companies",
                            "rule": "sourced"})
    return out


def _unsourced(slides: list) -> list[dict]:
    """Every figure the deck shows has its period, source and formula on the notes page (R27): a figure with no full note has its table column
    dropped, never shipped bare. The columns dropped."""
    keys = shown_metrics(slides)
    noted = {}
    for k in keys:
        rows = metric_note_rows([k])
        noted[k] = bool(rows) and all(str(x or "").strip() for x in rows[0][:3])
    bad = {k for k, ok in noted.items() if not ok}
    out = []
    if not bad:
        return out
    for s in slides:
        for b in s.blocks:
            if b["kind"] != "table":
                continue
            cols = [i for i, h in enumerate(b.get("head") or []) if i and _NOTE_LABELS.get(str(h)) in bad]
            for i in reversed(cols):
                out.append({"slide": s.title, "text": f"column {b['head'][i]}", "why": "no period, source or formula on the notes page", "rule": "sourced"})
                b["head"] = b["head"][:i] + b["head"][i + 1:]
                b["widths"] = b["widths"][:i] + b["widths"][i + 1:]
                if b.get("numeric"):
                    b["numeric"] = b["numeric"][:i] + b["numeric"][i + 1:]
                b["rows"] = [r if isinstance(r, dict) else r[:i] + r[i + 1:] for r in b.get("rows") or []]
    return out


def _shorter(text: str) -> str | None:
    """The text one whole part shorter: without its last sentence, else without its last "; " clause. None when it is one clause."""
    t = str(text).rstrip("… ").rstrip()
    parts = _SENT.split(t)
    if len(parts) > 1:
        return " ".join(parts[:-1])
    if "; " in t:
        head = t[:t.rfind("; ")].rstrip(" ,;:")
        return head + ("." if t.endswith(".") and not head.endswith(".") else "")
    # n1 (the outside review of the live R33 decks: three findings cards still ended "…, 7…"): one clause still too long loses its last
    # part, joined by ", " or " and " right after a bracket or a figure ("(13.5%) and slowest in…", "4.1%, a gap of…"), outside any
    # bracket and before a small word (never inside a name: "Chlor-alkali, soda ash and bulk inorganics"), keeping at least half of itself
    depth, cut = 0, None
    for i, ch in enumerate(t):
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and i >= len(t) // 2 and i and (t[i - 1] in ")%x" or t[i - 1].isdigit()) and (t.startswith(", ", i) or t.startswith(" and ", i)):
            nxt = t[i:].lstrip(", ").removeprefix("and ").lstrip()
            if nxt[:1].islower():
                cut = i
    if cut is not None and cut >= 24:
        head = t[:cut].rstrip(" ,;:")
        return head + ("." if t.endswith(".") and not head.endswith(".") else "")
    return None


def _origin(sl, text: str) -> tuple:
    """Where on the slide a text the layout check names was planned: ("headline",), ("para", block, i), ("line", block, card, i),
    ("cell", block, row, column), ("label",) (a title, a name on a chart, a tile's label, a table's heading), or ("other",)."""
    if text == sl.subtitle and sl.kind == "content":
        return ("headline",)
    if text == sl.title:
        return ("label",)
    for b in sl.blocks:
        if b["kind"] == "text":
            for i, para in enumerate(b.get("paras") or []):
                if str(para) == text:
                    return ("para", b, i)
        elif b["kind"] == "cards":
            for it in b.get("items") or []:
                for i, ln in enumerate(it.get("lines") or []):
                    if text in (str(ln), "• " + str(ln)):
                        return ("line", b, it, i)
                if text in (it.get("title"), it.get("value")):
                    return ("label",)
        elif b["kind"] == "table":
            for i, r in enumerate(b.get("rows") or []):
                for c, x in enumerate(() if isinstance(r, dict) else r):
                    if isinstance(x, str) and x == text:
                        return ("cell", b, i, c)
            if any(text == _cell_text(x) for r in b.get("rows") or [] for x in ([r["group"]] if isinstance(r, dict) else r)) or text in map(str, b.get("head") or []):
                return ("label",)
        elif b["kind"] == "stats":
            if any(text == str(x) for it in b.get("items") or [] for x in it[:2]):
                return ("label",)
        if text in map(str, b.get("cats") or []) or text == b.get("title"):
            return ("label",)
    return ("other",)


def fit_slide(sl) -> tuple[list[dict], list[dict]]:
    """One slide re-fitted so nothing on it is cut (R35): the layout check (probe) is run, and what it finds is put right the mildest way
    that works. A headline is set smaller by the page itself (headline_size); one still too long, a note or a card's line loses whole
    parts from its end (a sentence, then a "; " clause, then a card's last line), never part of a word or a sentence. What was changed,
    and what could not be put right (a label no shorter form of which fits, a word broken across lines, rows left off): (refit, failed),
    each {"slide", "text", "why", "rule": "layout"}."""
    refit, failed, done = [], [], set()

    def said(why, text, to):
        to.append({"slide": sl.title, "text": str(text), "why": why, "rule": "layout"})

    def still(text):                                 # whether the page still cuts this text
        return any(f["kind"] == "cut" and f["text"] in (text, "• " + text) for f in probe(sl))

    def whole(get, put, why):                        # the text one part shorter at a time until the page shows all of it
        first = cur = get()
        while True:
            cur = _shorter(cur)
            if cur is None:
                put(first)
                return False
            put(cur)
            if not still(cur):
                said(why, first, refit)
                return True
    if sl.subtitle and sl.kind == "content" and headline_size(sl.subtitle) < 14:
        said(f"headline set at {headline_size(sl.subtitle):g} pt to fit its lines", sl.subtitle, refit)
    for _ in range(40):
        f = next((x for x in probe(sl) if (x["kind"], x["text"]) not in done), None)
        if f is None:
            break
        kind, text, shown = f["kind"], f["text"], f["shown"]
        done.add((kind, text))
        o = _origin(sl, text)
        if kind == "rows":
            said("rows left off the slide", text, failed)
        elif kind == "broken":
            said("a word broken across two lines", text, failed)
        elif kind == "source":                       # cut before it reached the page (a long description): only a joining word at its end is put right
            fixed = _no_joiner(text[:-1]) + "…"
            if fixed != text and o[0] == "para":
                o[1]["paras"][o[2]] = fixed
                said("ended on a joining word", text, refit)
            elif fixed != text and o[0] == "line":
                o[2]["lines"][o[3]] = fixed
                said("ended on a joining word", text, refit)
            elif fixed != text and o[0] == "cell":
                o[1]["rows"][o[2]][o[3]] = fixed
                said("ended on a joining word", text, refit)
            elif o[0] == "headline" and not whole(lambda: sl.subtitle, lambda t: setattr(sl, "subtitle", t), "a headline's cut clause left off"):
                said("a headline ending in an ellipsis", text, failed)
        elif o[0] == "headline":
            if kind == "trimmed" and shown:
                sl.subtitle = shown
                said("a headline's last sentence left off to fit", text, refit)
            elif not whole(lambda: sl.subtitle, lambda t: setattr(sl, "subtitle", t), "a headline's last clause left off to fit"):
                said("a headline cut with an ellipsis", text, failed)
        elif o[0] == "para":
            b, i = o[1], o[2]
            if kind == "trimmed":
                b["paras"] = b["paras"][:i] + ([shown] if shown else []) + b["paras"][i + 1:]
                said("its last sentences left off to fit" if shown else "a paragraph left off to fit", text, refit)
            elif not whole(lambda: b["paras"][i], lambda t: b["paras"].__setitem__(i, t), "its last part left off to fit"):
                said("a sentence cut with an ellipsis", text, failed)
        elif o[0] == "line":
            it, i = o[2], o[3]
            if kind == "trimmed":
                keep = shown[2:] if shown.startswith("• ") and not str(it["lines"][i]).startswith("• ") else shown
                it["lines"] = it["lines"][:i] + ([keep] if keep else []) + it["lines"][i + 1:]
                said("its last sentences left off to fit" if keep else "a card's line left off to fit", text, refit)
            elif whole(lambda: it["lines"][i], lambda t: it["lines"].__setitem__(i, t), "its last part left off to fit"):
                pass
            elif len(it["lines"]) > 1:               # R21's rule: a card's last line gives way, whole
                gone = it["lines"].pop()
                done.discard((kind, text))
                said("a card's last line left off to fit", gone, refit)
            else:
                said("a sentence cut with an ellipsis", text, failed)
        elif kind == "cut":
            said("cut with an ellipsis" + (f": {shown}" if shown else ""), text, failed)
        # a title or a label "trimmed" to its whole sentences, and a footer or a legend: nothing is cut mid-sentence, nothing to list
    return refit, failed


_PAGED = re.compile(r"^(.*) \((\d+) of (\d+)\)$")
_DECLARED = re.compile(r"^(\d[\d,]*) (?:[a-z]+ )?(layers?|compan(?:y|ies)|banks?|insurers?)\b")


def _block_shows(b: dict) -> bool:
    """Whether a block puts anything on its page (a table a data row, a text a sentence, a chart a bar)."""
    k = b["kind"]
    if k == "table":
        return any(not isinstance(r, dict) for r in b.get("rows") or [])
    if k == "text":
        return any(str(p).strip() for p in b.get("paras") or [])
    if k in ("cards", "stats", "flow"):
        return bool(b.get("items"))
    if k in ("hbars", "columns", "lines", "stack"):
        return bool(b.get("cats")) or bool(b.get("series"))
    return True


MIN_POINTS = 4                 # LIVE6-008: a line chart needs this many points (the live p.19 drew a "weekly" trend through 2)
_DASHY = re.compile(r"^(?:–|-|n/a|not comparable)?(?: \(\d[\d,]*(?: of \d[\d,]*)?\))?$")
MOSTLY_EMPTY = 0.75           # a table this share of whose figure cells are dashes says too little to keep


def _dashy(v) -> bool:
    return bool(_DASHY.match(_cell_text(v).strip()))


def _points(b: dict) -> int:
    """How many points a line chart draws: the categories where any series has a value."""
    series = b.get("series") or []
    return sum(1 for i in range(len(b.get("cats") or [])) if any(i < len(x[1]) and x[1][i] is not None for x in series))


def _lists(b: dict) -> bool:
    """Whether a table is a list of companies or layers (its rows are what a page's counts are made of: never thinned here)."""
    return bool(b.get("head")) and _cell_text(b["head"][0]).split(":")[0] in ("Company", "Layer", "Part", "Kind", "Date", "Filed", "Ex-date")


def tidy_tables(slides: list) -> list[dict]:
    """LIVE6-008 (the live R34 Cybersecurity deck: a table cut off its card beside a "weekly" line through 2 points, rows of "– (2)", a
    table mostly dashes): on every content page a line chart through fewer than MIN_POINTS points is dropped and the table or cards beside
    it take the page's width; a measure table's row with no figure is dropped; a measure table MOSTLY_EMPTY dashes is replaced by a line
    that says so. Tables that list companies or layers keep every row (the page's counts are made of them). Returns what was changed."""
    done = []
    for s in slides:
        if s.kind != "content":
            continue
        for b in [b for b in s.blocks if b["kind"] == "lines" and _points(b) < MIN_POINTS]:
            s.blocks.remove(b)
            done.append({"slide": s.title, "why": f"a line through {_points(b)} points dropped"})
            for o in s.blocks:
                x, y, w, h = o["box"]
                if o["kind"] in ("table", "cards", "text") and x + w <= b["box"][0] + 0.01 and abs(x - M) < 0.01:
                    o["box"] = (M, y, CW, h)
        for i, b in enumerate(list(s.blocks)):
            if b["kind"] != "table" or _lists(b) or "Slide" in (b.get("head") or []):
                continue
            rows = [r for r in b.get("rows") or [] if isinstance(r, dict) or not all(_dashy(c) for c in r[1:])]
            if len(rows) < len(b.get("rows") or []):
                done.append({"slide": s.title, "why": f"{len(b['rows']) - len(rows)} row(s) with no figure dropped"})
                b["rows"] = rows
            cells = [c for r in rows if not isinstance(r, dict) for c in r[1:] if _cell_text(c).strip()]
            if len([r for r in rows if not isinstance(r, dict)]) >= 2 and cells and sum(map(_dashy, cells)) / len(cells) >= MOSTLY_EMPTY:
                x, y, w, h = b["box"]
                names = ", ".join(_cell_text(r[0]) for r in rows if not isinstance(r, dict))
                s.blocks[s.blocks.index(b)] = {"kind": "text", "box": (x, y, w, 0.6), "size": BODY_MIN, "floor": BODY_MIN, "color": MUTED,
                                               "paras": [clip(f"Left out here, as most of their figures aren't stored yet: {names}.", BODY_MIN, w, 2)]}
                done.append({"slide": s.title, "why": "a table mostly dashes replaced by a line"})
    return done


def complete_flags(slides: list) -> list[dict]:
    """What the finished pages leave out (n1, the outside review of the live R33 decks: Retail's appendix said 3 layers had companies left
    out and its pages named 2 over a table with no row; Real Estate's first roll page was an empty table): a table page that prints no data
    row, a content page with nothing on it, a run of pages "(k of n)" with a page missing, a heading's count ("3 layers with…", "97
    confirmed companies with figures, one row each") that the rows across its pages don't make, and a row printed twice. Each
    {"slide", "text", "why", "rule"}: "layout" for a page, "reconcile" for a count."""
    out = []

    def flag(s, text, why, rule="layout"):
        out.append({"slide": s.title, "text": text, "why": why, "rule": rule})
    runs: dict = {}
    for s in slides:
        if s.kind != "content":
            continue
        if s.blocks and not any(_block_shows(b) for b in s.blocks):          # its blocks all empty (a headline alone is a page's own choice)
            flag(s, s.title, "a page with nothing on it")
        for b in s.blocks:
            if b["kind"] == "lines" and _points(b) < MIN_POINTS:        # LIVE6-008
                flag(s, b.get("title") or s.title, f"a line chart through {_points(b)} points")
            if b["kind"] != "table":
                continue
            x, y, w, h = b["box"]
            lay = table_layout(b, w, h)
            if not any(not isinstance(r, dict) for r in lay["rows"]):
                flag(s, s.title, "a table page that prints no data row")
            data = [r for r in b.get("rows") or [] if not isinstance(r, dict)]
            if not _lists(b) and len(data) >= 2 and sum(_dashy(c) for r in data for c in r[1:]) >= MOSTLY_EMPTY * sum(len(r) - 1 for r in data):
                flag(s, s.title, "a table mostly dashes")
        tabs_ = [b for b in s.blocks if b["kind"] == "table"]
        if len(tabs_) == 1 and not [b for b in s.blocks if b["kind"] not in ("table", "text")] and not _PAGED.match(s.title or "") and "Appendix" not in (s.eyebrow or "") \
                and len([r for r in tabs_[0].get("rows") or [] if not isinstance(r, dict)]) == 1:
            flag(s, s.title, "a page for a table of one row")           # LIVE6-008: one row joins another page
        m = _PAGED.match(s.title or "")
        base, k, n = (m.group(1), int(m.group(2)), int(m.group(3))) if m else (s.title, 1, 1)
        if any(b["kind"] == "table" for b in s.blocks):
            runs.setdefault(base, []).append((k, n, s))
    for base, pages in runs.items():
        ks, ns = [k for k, _, _ in pages], {n for _, n, _ in pages}
        if len(ns) > 1 or sorted(ks) != list(range(1, max(ns) + 1)):
            flag(pages[0][2], base, f"its pages run {', '.join(f'{k} of {n}' for k, n, _ in pages)}")
        tabs = [b for _, _, s in pages for b in s.blocks if b["kind"] == "table"]
        if len(tabs) != len(pages):              # a run's count is of its one table across its pages
            continue
        data = [r for b in tabs for r in b.get("rows") or [] if not isinstance(r, dict)]
        seen = set()
        for r in data:
            key = tuple(_cell_text(c) for c in r)
            if key in seen and len(key) > 2:
                flag(pages[0][2], " | ".join(key)[:160], "a row printed twice", "reconcile")
            seen.add(key)
        said = pages[0][2].subtitle or ""
        d = _DECLARED.match(said)
        if not d:
            continue
        want, what = int(d.group(1).replace(",", "")), d.group(2)
        head = tabs[0].get("head") or []
        if what.startswith("layer") and head and head[0] == "Layer":
            got = len({_cell_text(r[0]).removesuffix(ROLL_MORE) for r in data} - {""})        # d1: a layer said on its first row only
        elif "one row each" in said:
            got = len(data)
        else:
            continue
        if got != want:
            flag(pages[0][2], said, f"says {want} {what}, its pages show {got}", "reconcile")
    return out


def prose_note(tidied: list[dict]) -> str:
    """The prose item's note: how many texts were repaired, and how many of them held a repeated word (R40)."""
    twins = sum(1 for d in tidied if "doubled word" in d.get("why", "") or "repeated word" in d.get("why", ""))
    return f"{_n(len(tidied), 'text repair')} (doubled words, punctuation, hyphens)" + (f"; {_n(twins, 'repeated word')} said once" if twins else "")


def layout_gate(slides: list) -> dict:
    """The publication gate's layout item (R35), run on the finished pages (after the page references and whole figures are set, so each
    text is as long as it will print): every slide is re-fitted (fit_slide), each change logged, and what could not be put right fails
    the item. {"refit": [...], "failed": [...]}."""
    import logging
    log = logging.getLogger("stratlab.deck")
    refit, failed = [], []
    for sl in slides:
        a, b = fit_slide(sl)
        refit += a
        failed += b
    # R40: a word repeated by a text fitted or filled in since the text was repaired is said once before the deck is stored
    twins = tidy_deck(slides, untwin) if slides else []
    if twins:
        slides[0].tidied = list(getattr(slides[0], "tidied", None) or []) + twins
    failed += complete_flags(slides)          # n1: and nothing the pages declare is missing from them
    for d in refit:
        log.info("deck layout: re-fitted on %r (%s): %s", d["slide"], d["why"], d["text"][:200])
    for d in failed:
        log.warning("deck gate: %s: on %r (%s): %s", d["rule"], d["slide"], d["why"], d["text"][:200])
    return {"refit": refit, "failed": failed, "twins": twins}


def with_layout(gate: dict, lay: dict) -> dict:
    """The gate's result with its layout item filled from the finished pages (layout_gate): what failed counts as dropped, what was
    re-fitted is kept beside it ("refit", "refit_n")."""
    cut = lambda d: {"rule": d["rule"], "slide": d["slide"], "text": str(d["text"])[:200], "why": str(d.get("why") or "")[:120]}      # noqa: E731
    of = lambda key: [d for d in lay["failed"] if d["rule"] == key or (key == "layout" and d["rule"] not in ids)]      # noqa: E731
    ids = {x["id"] for x in gate["items"]}
    items = [({**x, "ok": not of("layout"), "dropped": len(of("layout")),
               "note": f"{_n(len(lay['refit']), 'text')} re-fitted to show whole" if lay["refit"] else ""} if x["id"] == "layout"
              else {**x, "ok": False, "dropped": x["dropped"] + len(of(x["id"]))} if of(x["id"]) else x) for x in gate["items"]]
    if lay.get("twins"):          # R40: the repeated words said once on the finished pages counted with the text's other repairs
        items = [{**x, "note": prose_note(lay["all_tidied"])} if x["id"] == "prose" else x for x in items]
    dropped = (list(gate.get("dropped") or []) + [cut(d) for d in lay["failed"]])[:GATE_KEEP]
    return {**gate, "items": items, "passed": sum(1 for x in items if x["ok"]), "dropped": dropped,
            "dropped_n": (gate.get("dropped_n") or 0) + len(lay["failed"]), "refit": [cut(d) for d in lay["refit"][:GATE_KEEP]], "refit_n": len(lay["refit"])}


def publication_gate(slides: list, v: dict, reproduced: list | None = None) -> dict:
    """The checklist run before a deck is stored (R27): each item passes or fails, and what failed is dropped from the deck (a sentence, a card
    line, a table column), logged and listed here. `reproduced`: check_deck's dropped (R25). Items that need a later release's data (a primary
    classification per company, metric applicability) pass with a note until the data is there. {"passed", "items": [...], "dropped": [...]}."""
    import logging
    log = logging.getLogger("stratlab.deck")
    cov = coverage(v)
    counts = reconciled_counts(v, cov)
    periods = _deck_periods(slides)
    fixed = {"considered": counts["considered"], "with_figures": counts["with_figures"], "confirmed": counts["confirmed"]}
    dropped = {k: [] for k, _ in GATE_ITEMS}
    dropped["sourced"] = _unsourced(slides)
    dropped["sourced"] += provenance_flags(slides, v)        # R48: every checked figure's source row and every comparison's rows are there
    dropped["reproduce"] = [{**d, "why": "figures no table shows: " + ", ".join(d.get("figures") or []), "rule": "reproduce"} for d in reproduced or []]
    dropped["reconcile"] = _sweep(slides, lambda t: reconcile_flag(t, fixed, periods), "reconcile", claims_only=True)
    # R28: the four counts nest (with figures within confirmed within considered; each calculation within with figures): a count that
    # doesn't fails the item, whatever the sentences say
    dropped["reconcile"] += [{"slide": "", "text": f"the four counts: {x}", "why": "a count above the one it is part of", "rule": "reconcile"}
                             for x in counts_flags(counts)]
    # lane m1: a layer's counts are one set of records: two pages that state different totals for it, the scope not named, fail the item
    dropped["reconcile"] += [{"slide": x["slide"], "text": f"layer counts: {x['text']}", "why": "two counts of one layer with no scope named",
                              "rule": "reconcile"} for x in layer_count_flags(slides)]
    # R30: the coverage table (count, market value, each figure, each layer) reconciles, on the page and with the members
    for s_ in slides:
        for b in s_.blocks:
            if b["kind"] == "table" and b.get("head") == COVERAGE_HEAD:
                dropped["reconcile"] += [{"slide": s_.title, "text": f"coverage: {x}", "why": "coverage does not reconcile", "rule": "reconcile"}
                                         for x in coverage_table_flags(b.get("rows") or [], v, cov)]
    # R29 (P0): every stated share of market value is reproduced from the members (value_share); one that isn't is dropped, the cover's too
    dropped["reconcile"] += _sweep(slides, lambda t: share_flag(t, v), "reconcile", text=True)
    for b in (slides[0].blocks if slides else []):
        if b["kind"] == "stats":
            items = []
            for it in b.get("items") or []:
                why = share_flag(" ".join(str(x) for x in it[1:]), v) if isinstance(it, tuple) else None
                if why:
                    dropped["reconcile"].append({"slide": slides[0].title, "text": " ".join(str(x) for x in it), "why": why, "rule": "reconcile"})
                    it = (it[0], it[1], "")
                items.append(it)
            b["items"] = items
    dropped["headline"] = _sweep(slides, headline_flag, "headline", claims_only=True)
    dropped["headline"] += family_sweep(slides, v)           # lane m1: no ranking across layers of different kinds of business
    dropped["prose"] = _sweep(slides, prose_flag, "prose", text=True)
    dropped["marks"] = _marks(slides)
    notes = {}
    # every company of a layer that carries revenue models (R27, theme_base.by_model) has one, or is left out of its layer's figures
    # ("model_out"); an unknown model inside the figures is listed. Layers of the theme's own "Other" group are never compared.
    rows = [c for b in v.get("layers") or [] if isinstance(b, dict) and not b.get("official") for c in b.get("companies") or [] if isinstance(c, dict)]
    modelled = [c for c in rows if "model" in c]
    if modelled:
        missing = [c.get("name") or c.get("symbol") for c in modelled if not c.get("model") and not c.get("model_out")]
        if missing:
            dropped["classified"] = [{"slide": "", "text": f"{x}: no primary classification, in its layer's figures", "why": "unclassified", "rule": "classified"}
                                     for x in missing]
        notes["classified"] = f"{len(modelled) - len(missing)} of {len(modelled)} companies with a primary way of earning or left out of figures"
    else:
        notes["classified"] = "No way of earning read for this deck's companies: its layers are shown, never ranked"
    dropped["classified"] = (dropped.get("classified") or []) + unread_sweep(slides, v)
    # each sector figure carries its four states (R27, metric_registry via sector_metrics.section): applies / unavailable / n/a / not comparable
    # R29: the dive's sector figures are at sections.sector (the gate read sections.sector.sector, so it never saw them); a family with none
    # read yet (still being read) has no figure to check
    fams = {k: f for k, f in ((((v.get("sections") or {}).get("sector") or {}).get("families") or {})).items() if isinstance(f, dict) and f.get("keys")}
    if any(f.get("states") for f in fams.values()):
        notes["applicable"] = "Sector figures carry their applicability and four states"
    elif fams:
        dropped["applicable"] = [{"slide": "", "text": "sector figures without applicability states", "why": "no states", "rule": "applicable"}]
    else:
        notes["applicable"] = "No sector figures in this deck"
    peers = dated_peers(v)       # R34 (GPT review of R31.9: a peer median moved between runs a day apart); R35: set before the slides are written
    wide = sum((x.get("sets") or {}).get("market", 0) for x in peers.values() if isinstance(x, dict))
    if wide:
        dropped["peers"] = [{"slide": "Valuation", "text": f"{wide} figures set against the whole market", "why": "not comparable", "rule": "peers"}]
    none = max([(x.get("none") or 0) for x in peers.values() if isinstance(x, dict)] or [0])
    if none:
        notes["peers"] = f"{_n(none, 'company', 'companies')} with no comparable peer set, counted and left out"
    notes["layout"] = "Checked on the finished pages"           # R35: layout_gate, once the page references are set (theme_plan)
    # m2: what tidy_deck repaired (a doubled word, doubled or spaced punctuation, a broken hyphen) is counted here; a defect that is still
    # in a sentence after the repair fails the prose item and the sentence is listed
    tidied = getattr(slides[0], "tidied", None) if slides else None
    if tidied:
        notes["prose"] = prose_note(tidied)
    for s_ in slides:
        said = [s_.title, s_.subtitle] + [p for b in s_.blocks for p in b.get("paras") or []]
        for txt in said:
            why = text_flags(txt)
            if why:
                dropped["prose"].append({"slide": s_.title, "text": txt, "why": "text: " + ", ".join(why), "rule": "prose"})
        for txt in slide_texts(s_):           # n1: and nothing left unfilled anywhere on the page, a table's cell or a card's line too
            why = token_flags(txt)
            if why:
                dropped["prose"].append({"slide": s_.title, "text": txt, "why": "unfilled: " + ", ".join(why), "rule": "prose"})
            if txt not in said and untwin(txt)[1]:          # R40: and no repeated word left in a label or a cell
                dropped["prose"].append({"slide": s_.title, "text": txt, "why": "text: repeated word", "rule": "prose"})
    marks_noted = any(b["kind"] == "cards" and any(MARKS_LINE in (it.get("lines") or []) for it in b.get("items") or []) for s in slides for b in s.blocks)
    if not marks_noted and len(slides) > 2:
        dropped["marks"].append({"slide": "How to read this deck", "text": "the key to the three marks", "why": "not in the deck", "rule": "marks"})
    items = []
    for key, label in GATE_ITEMS:
        got = dropped.get(key) or []
        items.append({"id": key, "label": label, "ok": not got, "dropped": len(got), "note": notes.get(key, "")})
    every = [d for k, _ in GATE_ITEMS for d in dropped.get(k) or []]
    for d in every:
        if d["rule"] != "reproduce":         # check_deck logged its own
            log.warning("deck gate: %s: dropped on %r (%s): %s", d["rule"], d["slide"], d["why"], d["text"])
    cohort = cohort_words((v.get("checks") or {}).get("cohort"))
    for line in cohort:                      # q1: a layer's cohort that fell against the run before, logged with who left and why
        log.warning("deck gate: cohort: %s", line)
    return {"passed": sum(1 for x in items if x["ok"]), "of": len(items), "items": items, **({"cohort": cohort} if cohort else {}),
            "dropped": [{"rule": d["rule"], "slide": d["slide"], "text": str(d["text"])[:200], "why": str(d.get("why") or "")[:120]} for d in every[:GATE_KEEP]],
            "dropped_n": len(every)}


def theme_plan(v: dict, now: datetime | None = None) -> tuple[list[Slide], str]:
    """A theme deep dive's slides, one for each part of the page and in its order (DECK, 5 Nov: "it doesn't contain everything there is on
    the page about the theme"): the cover (the overview and the core), the theme at a glance (how its companies got in, the funds that track
    it), the value chain by layer (a chart and a table), each layer (what it does, its companies' figures with the median and range, its
    margins by year, its operating updates), the sub-themes, every company (in its own words, how it got in) and every company's figures,
    the tailwinds and risks with their checked sources and dates, the latest headlines, the new listings, the theme in numbers (size, growth,
    margins over time, valuation, the latest quarter, the balance sheet, price, ownership, events, management) and how to read it all.
    A part with nothing to show is said once on the last slide, never drawn empty. `v`: see theme_routes.deck_view."""
    us = v.get("region") == "US"
    unit = v.get("unit") or ("$ million" if us else "₹ crore")
    today = (now or datetime.now(timezone.utc)).astimezone(IST).strftime("%d %b %Y")
    sector = v.get("sector") or "Theme"
    footer = f"{sector} · Theme deep dive · {today}"
    asof = v.get("as_of")
    dated_peers(v)              # R35: the peers' P/E knows its price date before the first slide that states it
    # R48: every highest/lowest claim this deck makes between layers, with what it rests on (theme_data.comparison_basis), for the appendix's
    # "Comparison basis" page; the value chain's from the dive, the others added where the deck makes them (note_basis)
    v = {**v, "comparisons": [{**b, "where": "The value chain by layer"} for b in [(v.get("chain") or {}).get("basis")] if b]}
    asof_text = _day(asof) if asof else "–"
    amt = lambda x: "–" if x is None else money(x, unit)      # noqa: E731
    cap = lambda x: "–" if x is None else (money(x, "$ million") if us else cap_inr(x))      # noqa: E731
    p = v.get("placements") or {}
    members = v.get("members") or []
    total = p.get("total") or len({m["symbol"] for m in members})
    added, confirmed, named = p.get("added") or 0, p.get("confirmed") or 0, p.get("named") or 0
    base_n = max(0, (p.get("base") or 0) - named)
    chain = v.get("chain") or {}
    layers = v.get("layers") or []
    # a layer with no confirmed company (every one "not confirmed", or none at all) gets no slide and no operating-figures slide, and the
    # layers are numbered without it (R17-006: "Layer 4 · Tractors | 0 companies, revenue –")
    shown = [x for x in layers if any(c.get("status") != "unverified" for c in x.get("companies") or [])]
    empty = [x["layer"] for x in layers if x not in shown and x.get("layer")]
    # one scheme of layers (R18: "Deposit gathering" beside "Public Sector Bank"): when the map has two or more layers of its own, the companies
    # of the official industries (or the theme's list) it doesn't place are not layers of their own but one list in the appendix
    own_layers = [x for x in shown if not x.get("official")]
    unplaced = [x for x in shown if x.get("official") and not x.get("by_industry") and x.get("basis") != "rest"] if len(own_layers) >= 2 else []
    shown = [x for x in shown if x not in unplaced]
    # one layer, or none: nothing to set side by side, so no value chain, no industry economics and no highest-and-lowest finding (R18)
    chained = len(shown) >= 2
    sec = v.get("sections") or {}
    wide = set(v.get("company_wide") or [])
    med = v.get("median_ebitda")
    left_out: list[tuple] = []               # ("none" | "unread", what): what the page can show that this theme has none of, said once at the end
    slides: list[Slide] = []
    eb = lambda part: f"{sector} · {part}"  # noqa: E731
    size = sec.get("size") or {}

    checks = v.get("checks") or {}
    status = v.get("status") or {}
    whole = mostly_whole(checks.get("whole_points"), checks.get("with_ebitda"))     # EBITDA margins mostly filed in whole points (LIVE7A-009)
    ebm = lambda x: _pcw(x, whole)      # noqa: E731
    parts: list[list] = []                  # [title, line, the part's first slide]: the contents page (R18: no divider slide in the core)

    def section(part: str, title: str, line: str):
        if title == "Appendix":
            s = Slide(title, line, kind="section")
            s.part = "A"
            slides.append(s)
            return
        parts.append([title, line, len(slides)])

    def name_of(sym, nm):
        nm = clean_name(nm)
        return f"{nm} (whole company)" if sym in wide else f"{nm} (not confirmed)" if status.get(sym) == "unverified" else nm

    for m in members:                       # what a company does, as one business sentence (headings, glued words, results lines left off)
        if m.get("what"):
            m["what"] = _what(m["what"], m.get("name") or "")
    cov = coverage(v)
    mem = v.get("membership") or {}

    # a lender theme (most of its confirmed companies banks, lenders or insurers) is read on lenders' measures (R18)
    lender = is_lender_set([c for x in shown for c in x.get("companies") or []] or list(sec.get("leaders") or []))

    # 1. cover: the overview the AI wrote, the core, and the figures that frame the theme
    s = Slide(sector, f"{'US' if us else 'India (NSE and BSE)'} · Theme deep dive", dark=True)
    over = [sentences(v.get("summary") or "", 430) or cover_line(v, sector, total, cap, us)]
    if v.get("core"):
        over.append(f"Everything converges on {v['core']}.")
    s.add("text", (M, 2.75, 9.6, 2.15), paras=over, size=17, floor=12, color=ON_DARK)
    s.add("stats", (M, 4.98, CW, 1.45), dark=True, items=[       # R35: tall enough for a three-line note under its figure
        ("Companies", f"{total:,}", cov["universe"].split(" ", 1)[1] + (f"; {mem['not_confirmed']:,} not confirmed" if mem.get("not_confirmed") else "")), *([("Layers", str(len(shown)))] if chained else []),
        ("With figures", f"{cov['n']:,}", f"{cov['share']}% of the value of the {cov['valued']:,} with one" if cov.get("share") is not None else ""),
        # R29: the total is of the confirmed companies with figures and a market value, said so (the live R27 Semiconductors cover had "58 of
        # 112 with one" beside "the 105 with one")
        ("Their market value", cap(size.get("total_cap")) if size.get("total_cap") is not None else "–", f"{_n(size.get('with_value', 0), 'company', 'companies')} with figures and a market value"),
        ("Median ROE", _med((sec.get("medians") or {}).get("roe"))) if lender else ("Median EBITDA margin", ebm(med)), ("Prices as of", asof_text)])
    written = ""
    if v.get("generated_at"):
        try:
            written = f" The AI's map was written {datetime.fromtimestamp(float(v['generated_at']), timezone.utc).astimezone(IST).strftime('%d %b %Y')}."
        except (TypeError, ValueError, OverflowError):
            written = ""
    s.add("text", (M, 6.55, CW, 0.4), paras=[f"Prepared {today} with StratLab.{written} The overview and each layer's description are written by AI; "
                                              f"every figure is from the companies' reported numbers. {THEME_DISCLAIMER}"], size=10, floor=10, color=DARK_MUTED)
    slides.append(s)

    # 2. the theme at a glance: how its companies got in, its official industries, the funds that track it
    top3 = size.get("top3_share")
    msg = f"{membership_words(v, total)}; {_n(len(shown), 'layer')}; {cov['line']}"
    s = Slide("The theme at a glance", msg, eyebrow=eb("Overview"))
    etfs = v.get("etfs") or []
    lw = CW if not etfs else 7.4
    tiles = [("From the official industry list", f"{base_n:,}", "Kept when their own words show the theme's work")]
    if named:
        tiles.append(("Named in the theme's list", f"{named:,}", "The theme's own named companies"))
    if added or not named:
        tiles.append(("Added by the AI", f"{added:,}", f"{confirmed:,} confirmed by their own description" if added else "From other industries"))
    if mem.get("not_confirmed"):            # the one count of companies not confirmed, as the cover says it (R18: "Still being checked 16" beside "0 not yet")
        tiles.append(("Not yet confirmed", f"{mem['not_confirmed']:,}", "Own words don't show the work yet"))
    if mem.get("placed") and mem["placed"] < total:          # gl50: the companies past the check, said as not checked yet
        tiles.append(("Not checked yet", f"{total - mem['placed']:,}", f"Beyond the {mem['placed']:,} checked, the largest by market value"))
    s.add("stats", (M, TOP, lw, 1.55), items=tiles)
    inds = p.get("industries") or []
    how = []
    if inds:
        by = {"words": ", matched by the theme's own words", "ai": ", picked by AI from the exchange's own list"}.get(p.get("industries_by"), "")
        how.append(f"Official industries{by}: {' · '.join(inds)}. The base is every listed company the exchange's own industry classification "
                   "puts in these industries" + (", and the theme's own named list." if named else "."))
    elif named:
        how.append("No official industry is this theme's core on its own; its companies are the theme's own named list"
                   + (" and the ones the map names." if added else "."))
    else:
        how.append("The theme's official industries are still being picked; until then the companies are the ones the map names." if p.get("industries_by") == "pending"
                   else "No official industry is this theme's core, so every company here is one the map names, checked against its own description.")
    if any(x.get("by_industry") for x in shown):
        how.append("Its layers are the companies' own official industries.")
    elif own_layers:
        how.append("The AI sorts companies into layers" + (" and adds companies from other industries." if added else ".")
                   + (f" {sum(len(x.get('companies') or []) for x in unplaced):,} companies it doesn't place are listed in the appendix." if unplaced else ""))
    how.append("Each company is in one layer. A company whose own words don't show the theme's work is listed as not confirmed and left out of every "
               "median and total.")
    if p.get("unclassified"):
        how.append(f"{p['unclassified']:,} US-listed companies have no industry on file yet, so they can't join a theme by industry until their SEC record is read.")
    s.add("cards", (M, TOP + 1.8, lw, BOT - TOP - 1.8), cols=1, fill=True, size=14, items=[{"title": "How the companies got in", "lines": how}])
    if etfs:
        rows = [[e.get("ticker") or "", e.get("name") or ""] for e in etfs]
        s.add("table", (M + lw + 0.35, TOP + 0.36, CW - lw - 0.35, BOT - TOP - 0.36), head=["Fund", "Name"], rows=rows[:12], widths=[1.2, 3.2], numeric=[False, False])
        s.add("text", (M + lw + 0.35, TOP, CW - lw - 0.35, 0.3), paras=["Funds that track the theme"], size=12, floor=12, bold=True, color=INK2)
    # R19 (the owner: "just keep the important ones"): the cover and the data-confidence page carry these counts, so how the companies got
    # in and the funds that track the theme are lines of the notes, not a page
    overview_how = how + ([f"Funds that track the theme: {', '.join(e.get('ticker') or e.get('name') or '' for e in etfs[:8])}."] if etfs else [])

    contents = Slide("Contents", "The parts of this deck and the page each starts on; the appendix holds every company's figures", eyebrow=eb("Contents"))
    slides.append(contents)

    # 3. the findings (the owner, 7 Nov: about five pages up front, with page references): what the figures show, how far they can be
    # trusted and the companies' dated updates, each from computed facts only (no AI writes a number here)
    names_shown = {x["layer"] for x in shown}
    unplaced_cos = sorted((c for x in unplaced for c in x.get("companies") or [] if c.get("status") != "unverified"), key=lambda c: -(c.get("cap") or 0))
    rows_c = [r for r in chain.get("rows") or [] if r.get("n") and r["layer"] in names_shown]
    section("", "Findings", "What the figures show, how far they can be trusted, and the companies' dated updates.")
    _findings(slides, v, cov, ebm, cap, eb("Findings"), now_d := (now or datetime.now(timezone.utc)).astimezone(IST).date(), chained=chained, lender=lender)

    # 4. the value chain: where the margin sits, a chart and the table (only with two layers or more to set side by side)
    vc_part = "The value chain" if chained else "The companies"
    later_slides: list[Slide] = []           # the layers' full tables and the companies the map doesn't place: the appendix (R18: a short core)
    if chained:
        section("", "The value chain", chain.get("line") or f"{_n(len(shown), 'layer')}, each with its companies' revenue and median margins.")
    if chained and rows_c:
        lend_chain = lender or chain.get("measure") == "roe"
        cols = [("n", "Companies", 1.25), ("revenue", "Revenue", 1.35), ("ebitda", "EBITDA margin", 1.2), ("net", "Net margin", 1.1), ("roce", "ROCE", 1.0)]
        if lend_chain:
            cols += [("roe", "ROE", 1.0), ("nii_assets", "NII / assets", 1.15), ("gnpa", "Gross NPA", 1.1), ("pb", "P/B", 0.9)]
        cols += chain_family_cols(rows_c)            # R25: each family's own filed figures (CET1, solvency, combined ratio, SBC, FCF) where its layers have them
        fmt_ = {"ebitda": ebm, "pb": _times, "solvency": lambda x: _times(x, 2)}

        def cell(r, k):                    # each median with its base: none under 3 companies, a count when under the layer's (R20)
            if k == "n":
                return companies_cell(r["n"], r.get("listed"))
            if k == "revenue":
                return amt(r.get("revenue"))
            return _medn(None, r["n"], fmt_.get(k, _pc), n=r.get(f"{k}_n"), value=r.get(k))
        head, widths = ["Layer"] + [c[1] for c in cols], [2.9] + [c[2] for c in cols]
        rows = [[r["layer"]] + [cell(r, k) for k, _, _ in cols] for r in rows_c]
        head, rows, widths, _ = drop_empty(head, rows, widths)
        mark = {chain.get("highest"): UP, chain.get("lowest"): DOWN}
        key = chain.get("measure") or "ebitda"
        # a chart follows the table's rule (R21): a layer is plotted only on a median of MIN_BASE companies or more, its count in its label
        charted = [r for r in rows_c if r.get(key) is not None and (r.get(f"{key}_n") or 0) >= MIN_BASE]
        chart = 2 <= len(charted) <= 14 and len(head) <= 5         # a wide table keeps the full width (R25; R34, GPT review of R31.5: label columns pressed to a few letters)
        tw = 7.3 if chart else CW
        foot = [f"Each company's latest full year, in {unit}; how each figure is built: ⟦{NOTES_TITLE}⟧.",
                "Layer revenue: its companies added together; margins and returns: its median company."]
        foot.append(compare_note(chain, key))
        if intensity_note(chain):                 # n1: the figures behind "not ranked", so the suppression can be reproduced
            foot.append(intensity_note(chain))
        if chain.get("basis"):                    # R48: the comparison's companies by name, its rules and their figures
            foot.append(f"Each compared layer's companies by name, the rules and the capital figures: ⟦{COMPARE_TITLE}⟧.")
        if any((r.get("listed") or 0) > r["n"] for r in rows_c):          # lane m1: the two scopes named where a layer's counts differ
            foot.append(COMPANIES_NOTE)
        # R34 (GPT review of R31.7, Defence: "No listed company is shown for x."): a layer name with no word in it is no layer to name
        none_ = [x["layer"] for x in layers if not x.get("companies") and re.search(r"[A-Za-z]{3,}", str(x.get("layer") or ""))]
        unsure_ = [x for x in empty if x not in none_ and re.search(r"[A-Za-z]{3,}", str(x or ""))]
        if none_:
            foot.append(f"No listed company is shown for {', '.join(none_)}: none of the companies the map named has a description that shows it does the work.")
        if unsure_:
            foot.append(f"No slide for {', '.join(unsure_)}: none of its companies is confirmed by its own description.")
        if unplaced:
            foot.append(f"{_n(len(unplaced_cos), 'more company', 'more companies')} of the theme's industries the map doesn't place in a layer: {names5(unplaced_cos)}; "
                        "in every median and total, and in the appendix.")
        fh = min(1.6, len(wrap(" ".join(foot), BODY_MIN, CW)) * _lh(BODY_MIN) + 0.05)
        th = BOT - TOP - fh - 0.2
        pages = table_pages(head, rows, widths, tw, th)
        for k, chunk in enumerate(pages):
            s = Slide("The value chain by layer" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      chain.get("line") or f"Each layer's companies, their revenue added together ({unit}), and the layer's median margins",
                      eyebrow=eb("The value chain"))
            s.add("table", (M, TOP, tw, th), head=head, rows=chunk, widths=widths,
                  colors={(i, 0): mark[r[0]] for i, r in enumerate(chunk) if r[0] in mark and r[0]})
            if chart and k == 0:
                bcats, bcols = bar_marks(chain, charted, key)
                s.add("hbars", (M + tw + 0.35, TOP, CW - tw - 0.35, th), title=f"Median {'ROE' if key == 'roe' else 'EBITDA margin'} by layer", cats=bcats,
                      vals=[r[key] for r in charted], colors=bcols, fmt="pctw" if whole and key == "ebitda" else "pct")
            s.add("text", (M, BOT - fh, CW, fh), paras=[" ".join(foot)], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
        if not chart and len(head) > 5 and 2 <= len(charted) <= 14:
            # R35: a table of more than four figure columns keeps the full width, so its chart (R34 left it out) has a page of its own
            # after it: the layers' medians side by side, each name whole, only with two layers or more on a median of MIN_BASE companies
            mname = "ROE" if key == "roe" else "EBITDA margin"
            un_ = unranked_words(chain) if chain.get("highest") else ""
            cnote = (f"Each bar: the layer's median company, latest full year; its count of companies in its label. A layer is drawn on a median of "
                     f"{MIN_BASE} companies or more; every layer is in the table before this page."
                     + (f" Grey bars are not ranked. {un_}" if un_ else "") + f" How the figure is built: ⟦{NOTES_TITLE}⟧.")
            ch_ = note_h(cnote)
            s = Slide(f"Median {mname} by layer", chain.get("line") or f"Each layer's median company's {mname}, the layers side by side", eyebrow=eb("The value chain"))
            bcats, bcols = bar_marks(chain, charted, key)
            s.add("hbars", (M, TOP, CW, min(BOT - TOP - ch_ - 0.2, 1.2 * len(charted) + 0.3)),
                  cats=bcats, vals=[r[key] for r in charted], colors=bcols, fmt="pctw" if whole and key == "ebitda" else "pct")
            s.add("text", (M, BOT - ch_, CW, ch_), paras=[cnote], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
    elif v.get("members_with_figures") == 0 or not shown:
        left_out.append(("none", "the value chain's figures (no company has stored figures)"))

    # 4. each layer on ONE page (R18, the owner: the value chain alone ran 15 pages): what it does, its largest companies by market value with the
    # layer's median and range, its margins by year or by company; the full table is in the appendix, said with its page
    biz = v.get("business") or {}
    # R28 (the owner's review: "only important pages"): a layer with one confirmed company has no page of its own; it stays in the value
    # chain's table, and every such layer is one row of the "Smaller layers" page after the layer pages
    # d1 (the outside review of the live Release 41 decks: IT's and Cybersecurity's 2-company layers, a page each, every median "– (2)"): a
    # layer of SMALL_MAX confirmed companies or fewer has no median and no page of its own; each is rows of the "Smaller layers" page
    paged = [x for x in shown if confirmed_n(x) > SMALL_MAX] if chained else []
    small = [x for x in shown if x not in paged] if chained else []
    rolls: list[tuple] = []             # R35: (layer, in, left out, whether its page left a name off) of each layer with a company left out
    for i, layer in enumerate(paged):     # numbered as shown: a layer with no company leaves no gap (Layer 4, then Layer 6)
        cos = sorted(layer.get("companies") or [], key=lambda c: (c.get("status") == "unverified", bool(c.get("model_out")), -(c.get("cap") or 0), c.get("name") or ""))
        st = layer.get("stats") or {}
        title = f"Layer {i + 1} · {layer['layer']}"
        lwide = set(layer.get("company_wide") or []) | {c["symbol"] for c in cos if c.get("company_wide")}
        lwhole = whole or (bool([c for c in cos if c.get("ebitda") is not None]) and all(c.get("ebitda_dp") == 0 for c in cos if c.get("ebitda") is not None))
        unsure = {c["symbol"] for c in cos if c.get("status") == "unverified"}
        unmodelled = {c["symbol"] for c in cos if c.get("model_out")} - unsure       # R27: how it earns not shown clearly: out of the layer's figures
        from .intel.theme_data import calc_of
        nofig = {c["symbol"] for c in cos if calc_of(c)["why"] == "no revenue figure"}        # lane m1: its row says why it is in no median
        lend = is_lender_set(cos)
        cols = co_cols(cos)
        if not layer.get("official") and len({c.get("official_industry") for c in cos if c.get("official_industry")}) >= 2:
            cols = [("official_industry", "Industry", 1.7)] + cols        # an AI layer: the exchange's industry is a column, not a layer (R20)
        # LIVE7A-005/014: a row's mark is its one reason, in the order of its kept record (theme_data.calc_record: not confirmed, how it earns,
        # no revenue figure), then the whole company's figures, so the deck gives the reason the page gives (the live Automotive deck marked
        # Mahindra & Mahindra "(whole company)" where its page said its evidence doesn't show how it earns); each mark's note is said only
        # when a row carries it
        def tag(c):
            if c["symbol"] in unsure:
                return "not confirmed"
            if c["symbol"] in unmodelled:
                return ROLL_TAG.get(why_kind(calc_of(c)), "insufficient evidence")      # ex49: the reason's kind
            if c["symbol"] in nofig:
                return ROLL_TAG["no figure stored"]
            return "whole company" if c["symbol"] in lwide else "on its industry" if c.get("on_industry") else "own design" if c.get("own_goods") else \
                "on its words" if c.get("by_words") else ""
        tags = {c["symbol"]: tag(c) for c in cos}
        body = [[f"{c['name']} ({tags[c['symbol']]})" if tags[c["symbol"]] else c["name"]]
                + [co_cell(c, k, amt) for k, _, _ in cols] + [c.get("year") or "–"] for c in cos]
        ns = [(st.get(k) or {}).get("n") or 0 for k, _, _ in cols if k not in ("revenue", "official_industry")]
        n_st = max(ns or [0])
        n_lay = layer.get("n") or len([c for c in cos if c["symbol"] not in unsure])
        label = f"Median of {_n(n_st, 'company', 'companies')}" if len(set(x for x in ns if x)) <= 1 and n_st >= MIN_BASE else "Median (companies)"
        med_row = [label + (" (company-wide figures)" if layer.get("stats_over") == "all" else "")] + \
            ["" if k in ("revenue", "official_industry") else _medn(st.get(k), n_lay, (lambda x: _pcw(x, lwhole)) if k == "ebitda" else col_fmt(k)) for k, _, _ in cols] + [""]
        rng_row = ["Range"] + ["" if k in ("revenue", "official_industry") or ((st.get(k) or {}).get("n") or 0) < MIN_BASE else
                               _span(st.get(k), (lambda x: _pcw(x, lwhole)) if k == "ebitda" else col_fmt(k, True)) for k, _, _ in cols] + [""]
        head = ["Company"] + [c[1] for c in cols] + ["Year"]
        widths = [2.6] + [c[2] for c in cols] + [1.1]
        tail = [med_row] + ([rng_row] if n_st >= MIN_BASE else [])
        head, every, widths, _ = drop_empty(head, body + tail, widths)
        body, tail = every[:len(body)], every[len(body):]
        meds_ = [(nm_, _medn(st.get(k_), n_lay, f_)) for k_, nm_, f_ in ((("roe", "ROE", _pc),) if lend else (("ebitda", "EBITDA margin", lambda x: _pcw(x, lwhole)),))
                 + (("net", "net margin", _pc),)]
        meds_ = [f"median {nm_} {t_}" for nm_, t_ in meds_ if not t_.startswith("–")]           # a median under 3 companies isn't said (R20)
        # rv51 (R51, the outside review of the live Release 49 Real estate deck: 20 net margins above EBITDA left out unreconciled): the
        # layer's median net margin with them too, when leaving them out moves it as printed
        dag, alln = layer.get("one_off") or [], (layer.get("net_all") or {}).get("median")
        net_label = next((c[1] for c in cols if c[0] == "net"), None)
        if dag and alln is not None and (st.get("net") or {}).get("median") is not None and _pc(alln) != _pc(st["net"]["median"]) \
                and net_label in head:
            with_ = f"{_pc(alln)} with the {_n(len(dag), '† company', '† companies')}"
            at = head.index(net_label)
            if tail and tail[0][at] and not tail[0][at].startswith("–"):
                tail[0][at] = f"{tail[0][at]}; {with_}"             # the table shows it, so the header may say it (the provenance gate)
                meds_ = [x + f", {with_}" if x.startswith("median net margin") else x for x in meds_]
        msg = layer.get("line") or (layer_head(layer, cos, amt)
                                    + (f"; {', '.join(meds_)}" if meds_ else ""))
        rc_ = rest_count(v) if layer.get("basis") == "rest" else None
        if rc_ and rc_[0] > len(cos):       # d1: one count of "Other" on every page: the group's whole count, and why this page lists fewer
            msg += (f"; {rc_[0]:,} in this group in all" + (f" ({rc_[3]:,} not checked yet)" if rc_[3] else "")
                    + f", the other {rc_[0] - len(cos):,} smaller companies whose figures the deck doesn't work out")
        desc = layer.get("description") or ""
        unread_n = sum(1 for c in cos if c.get("unread"))
        official = (("Companies that fit none of the map's layers, by the AI's answer or their own words"
                     + (f"; {unread_n} of them not checked yet: no description of their own is kept, so nothing placed them." if unread_n else "."))
                    if layer.get("basis") == "rest" else
                    "Companies of the theme's list that the exchange files under this industry." if layer.get("by_industry") else
                    "The theme's own named companies that the layers above don't place." if layer.get("basis") == "list" else
                    "Companies the exchange classifies under this industry that the layers above don't place.") if layer.get("official") else ""
        common = layer_common(layer)
        if layer.get("adjacent"):          # d53 (R53): an adjacent layer said so where its companies are shown
            adj_ = layer["adjacent"]
            common = (f"Adjacent participants: most of its companies' principal business is of {adj_.get('kind')}, not of the theme's "
                      f"{adj_.get('theme')}; shown here, in no total, median or ranking of the theme. " + (common or "")).strip()
        card = {"title": "What this layer does", "lines": [clip(desc, 13, CW - 0.5, 3)] + [x for x in (common, official) if x], "note": AI_NOTE} if desc else \
            {"title": "Who is here", "lines": [x for x in (common, official) if x]} if official or common else None
        hist = layer.get("history") or {}
        mkey, mname = ("roe", "ROE") if lend else ("ebitda", "EBITDA margin")
        bars = [c for c in cos if c.get(mkey) is not None and c["symbol"] not in unsure | unmodelled]
        chart = None
        if len(hist.get("years") or []) >= 2 and not lend and (hist.get("n") or 0) >= MIN_BASE:       # an aggregate of 3 or more (R21)
            chart = {"kind": "lines", "title": f"Margins by year, the same {_n(hist.get('n') or 0, 'company', 'companies')}",
                     "cats": hist["years"], "series": [("EBITDA margin", hist["ebitda"], BLUE), ("Net margin", hist["net"], ORANGE)], "fmt": "pct", "labels": True}
        elif len(bars) >= 2:
            top = sorted(bars, key=lambda c: -(c[mkey] or 0))[:8]
            chart = {"kind": "hbars", "title": f"{mname} by company", "cats": [c["name"] for c in top], "vals": [c[mkey] for c in top],
                     "fmt": "pctw" if whole and mkey == "ebitda" else "pct", "colors": [DOWN if c[mkey] < 0 else BLUE for c in top]}
        fparts = []
        r_in, r_out = layer_roll(layer, cos, ("roe", "net") if lend else ("ebitda", "net"))
        rline = ""             # R35: who the "(4 in the layer's calculations)" are and why each other is not, where the rows can't say it (below)
        shown_tags = set(tags.values())
        if "whole company" in shown_tags:
            fparts.append("(whole company): it runs other businesses too, so its figures are the whole company's and left out of the medians.")
        if "on its industry" in shown_tags:          # d1
            # gl52 (R52): said as it is: its own words don't state how it earns (or there are none), and its official industry is the one most
            # of the layer's companies share, or the one the layer's name names
            fparts.append("(on its industry): its own words don't state how it earns; it is in the layer's figures by its official industry, "
                          "that of most of the layer's companies or the one the layer's name names.")
        if "own design" in shown_tags:      # ex49
            fparts.append("(own design): read as a retailer, its own words say it designs the goods it sells, so it sells products of its own, "
                          "as the layer's companies do, and is in the layer's figures.")
        if "on its words" in shown_tags:    # ex49 (G3)
            fparts.append("(on its words): the map placed it here and its own words say the layer's name and no other way of earning; only the "
                          "AI's read gave it another, so it is in the layer's figures.")
        if unsure:
            fparts.append("(not confirmed): its own words don't show this work, so it is left out of the medians and the revenue total.")
        # ex49 (R48): each left-out mark's note says exactly why, per company where it differs: both ways of earning for a different revenue
        # model, what is missing for insufficient evidence (R34: every company left out carries its reason)
        fparts += kind_notes([c for c in cos if c["symbol"] in unmodelled], shown_tags)
        nf_note = f"({ROLL_TAG['no figure stored']}): no revenue or other figure is stored for it, so it is in none of this layer's medians or totals."
        if nofig:           # lane m1: every company left out of a layer's calculations carries its reason on its row or in the roll's line
            fparts.append(nf_note)
        if any(c.get("one_off") for c in cos):
            fparts.append(f"{ONE_OFF}: {ONE_OFF_NOTE} ({ANOMALY_WHY}); left out of the net margin's median.")
        if any(c.get("nc") for c in cos):
            fparts.append("n.c.: not comparable, the figure is on another basis than the rest of its column (latest full year against filed "
                          "results annualised), so it is left out of the median.")
        chh = min(1.75, card_height(card, CW)) if card else 0.0
        below = TOP + (chh + 0.2 if card else 0)
        rest_h = REST_H if len(body) > 1 else 0
        def foot(parts):            # the page's notes and the room they need: who is in the calculations, then what the marks mean
            ps = [x for x in (rline, " ".join(parts)) if x]
            return ps, (sum(note_h(x) for x in ps) + 0.06 * (len(ps) - 1) + 0.12) if ps else 0
        fnote, fh = foot(fparts)
        room = BOT - fh - below

        def fits(tw_):
            k = len(body)
            while k > 1 and table_height(head, body[:k] + tail, widths, tw_) > room - (rest_h if k < len(body) else 0):
                k -= 1
            return k
        if chart and len(head) > 8:          # a wide table (a lender's own measures and its filed figures, R23) keeps the full width: no words broken
            chart = None
        tw = CW - 3.9 if chart else CW
        k_fit = fits(tw)
        if chart and k_fit < len(body) and fits(CW) > k_fit:      # the companies before the chart: a table that shows more of them goes full width
            chart, tw, k_fit = None, CW, fits(CW)
        if r_out and k_fit < len(body):
            # R35 (GPT reviews of R31.5-R31.9, live IT: "13 companies (4 in the layer's calculations)", three rows shown, nobody named): the
            # page doesn't show every company, so a line of its own names who is in and why each other is not. A page that shows them all
            # says it on their rows ("(insufficient evidence)", "(different model)", "(not confirmed)") and keeps its room for them.
            rline, rcut = roll_line(r_in, r_out)
            rolls.append((layer["layer"], r_in, r_out, rcut))
            fnote, fh = foot(fparts)
            room = BOT - fh - below
            k_fit = fits(tw)
            if chart and fits(CW) > k_fit:
                chart, tw, k_fit = None, CW, fits(CW)
        # d1 (the outside review of the live Release 41 decks: "The largest 1 of 78 by market value", a layer page with one row): a layer's page
        # shows at least LAYER_ROWS_MIN of its companies (all of a smaller layer): first without the chart, then without the industry
        # column (the appendix keeps it), then with the layer's description cut to two lines
        want = min(LAYER_ROWS_MIN, len(body))
        if k_fit < want and chart:
            chart, tw = None, CW
            k_fit = fits(tw)
        if k_fit < want and "Industry" in head:
            j_ = head.index("Industry")
            head, widths = head[:j_] + head[j_ + 1:], widths[:j_] + widths[j_ + 1:]
            body, tail = [r_[:j_] + r_[j_ + 1:] for r_ in body], [r_[:j_] + r_[j_ + 1:] for r_ in tail]
            k_fit = fits(tw)
        intro = []
        if k_fit < want and card:
            # the card's words as a paragraph at the notes' size above the table (what the layer does, in two lines of whole sentences
            # where they fit, who wrote it, and what its companies have in common)
            ai_ = "written by AI from general knowledge, with no figures"
            lead = ""
            for n_l in (1, 2, 3):                 # the fewest lines of whole sentences that say what it does
                lead = clip(f"What this layer does ({ai_}): {desc}", BODY_MIN, CW, n_l) if desc else ""
                if lead and lead[-1:] in ".!?":
                    break
            lead = lead if lead and lead[-1:] in ".!?" else (f"What this layer does ({ai_}): {desc}" if desc else "")
            intro = [x for x in [lead] + [x for x in card["lines"] if x and x != card["lines"][0]] if x] if desc else list(card["lines"])
            card, chh = None, 0.0
            below = TOP + sum(note_h(x) for x in intro) + 0.06 * (len(intro) - 1) + 0.1
            room = BOT - fh - below
            k_fit = fits(tw)
        if k_fit < want and rline:          # the roll's line names fewer of each group (every one is in the appendix)
            for short in (False, True):        # ex49: each reason in full where it fits its lines, else its kind alone (in full in the appendix)
                in_, out_, _ = roll_words(r_in, r_out, max(1, ROLL_NAMES // 3), short)
                rline = roll_said(len(r_in), len(r_in) + len(r_out), len(r_out), in_, out_, True)
                if len(wrap(rline.replace(f"⟦{ROLL_TITLE}⟧", "p. 00"), BODY_MIN, CW)) <= ROLL_LINES:
                    break
            rolls[-1] = (layer["layer"], r_in, r_out, True)
            fnote, fh = foot(fparts)
            room = BOT - fh - below
            k_fit = fits(tw)
        on_page = {c["symbol"] for c in cos[:k_fit]}
        on_tags = {tags[x] for x in on_page}
        # ex49: a left-out mark's note (each kind's, kind_notes) and the own-design note only with a row on the page that carries it
        drop = [p for p in fparts for t_ in ("different model", "another business", "insufficient evidence", "own design", "on its words")
                if p.startswith(f"({t_})") and t_ not in on_tags]
        drop += [p for p in fparts if p.startswith("(whole company)") and "whole company" not in on_tags]
        drop += [p for p in fparts if p.startswith("(on its industry)") and "on its industry" not in on_tags]
        drop += [nf_note] if not nofig & on_page else []
        if rline and not unsure & on_page:          # R35: the roll's line says who isn't confirmed, so the mark's own note goes with its rows
            drop += [p for p in fparts if p.startswith("(not confirmed)")]
        if (unmodelled or rline or nofig or lwide or {"on its industry", "own design", "on its words"} & shown_tags) and any(p in fparts for p in drop):       # no marked row shown: its note isn't either
            fparts = [p for p in fparts if p not in drop]
            fnote, fh2 = foot(fparts)
            if rline and fh2 < fh:          # R35: the roll's line took room from the table: the room the dropped notes leave goes back to its rows,
                room_was, room = room, BOT - fh2 - below        # unless a row that comes back carries a mark whose note was just dropped
                k2 = fits(tw)
                if k2 > k_fit and not {c["symbol"] for c in cos[k_fit:k2]} & (unmodelled | unsure | nofig):
                    k_fit = k2
                else:
                    room = room_was
            fh = fh2
        s = Slide(title, msg, eyebrow=eb("The value chain"))
        if card:
            s.add("cards", (M, TOP, CW, chh), cols=1, fill=True, items=[card])
        elif intro:
            s.add("text", (M, TOP, CW, below - TOP - 0.1), paras=intro, size=BODY_MIN, floor=BODY_MIN)
        th = room - (REST_H if k_fit < len(body) else 0)
        s.add("table", (M, below, tw, th), head=head, rows=body[:k_fit] + tail, widths=widths, strong=list(range(k_fit, k_fit + len(tail))), tight=True)
        if chart:
            c = dict(chart)
            s.add(c.pop("kind"), (M + tw + 0.4, below, CW - tw - 0.4, room), **c)
        if k_fit < len(body):
            s.add("text", (M, below + th + 0.04, CW, REST_H - 0.04), paras=[f"{shown_label(cos, k_fit)}; every one: appendix, ⟦Every company's figures⟧."],
                  size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        if fnote:
            s.add("text", (M, BOT - fh + 0.08, CW, fh - 0.08), paras=fnote, size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

    if sum(confirmed_n(x) for x in small) >= 2:      # LIVE6-008: no page for a table of one row: one such layer is a row of the value chain's
        _smaller_layers(slides, small, amt, eb("The value chain"))         # table and its company a row of the appendix

    # the operating figures of every layer and sub-theme on one or two pages, each company once, grouped by layer (R18: a page for each layer,
    # and HDFC Bank's figures on two layers' pages); the rest of a long list is in the appendix
    if not chained:
        section("", "The companies", f"{cov['line']}.")
    groups_b, seen_b = [], set()
    for g in [{"name": x.get("layer"), "rows": x.get("rows") or []} for x in biz.get("layers") or []] + list(biz.get("subs") or []):
        if g["name"] in {x["layer"] for x in unplaced}:
            g = {**g, "name": "Not placed in a layer"}
        fresh = [r for r in g.get("rows") or [] if r["symbol"] not in seen_b]
        if fresh:
            groups_b.append((g["name"], fresh))
            seen_b |= {r["symbol"] for r in fresh}
    n_biz = sum(len(rows_) for _, rows_ in groups_b)
    if n_biz and n_biz < MIN_BASE:            # one or two companies' figures: no page of their own; data confidence says how many (R21)
        groups_b = []
    if groups_b:
        flat = []
        for name, rows_ in groups_b:
            if len(groups_b) > 1:
                flat.append({"group": name or "–"})
            flat += rows_
        before = len(slides)
        _biz_slides(slides, "Operating figures", flat, eb(vc_part), now_d)
        made = slides[before:]
        if len(made) > 1:              # one page (R19): the rest of the companies' figures are on the theme's page
            del slides[before + 1:]
            kept = sum(1 for b in made[0].blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict))
            made[0].title = "Operating figures"
            made[0].subtitle = (f"Operating figures filed with the exchange between results, as filed: {kept} of "
                                f"{sum(1 for r in flat if 'group' not in r)} companies' figures; the rest are on the theme's page")       # R20: the rows, not the headings

    # 5. sub-themes: one compact page, each sub-theme with up to five of its companies by name (R19: no long per-company list)
    all_subs = v.get("subs") or []
    subs = [sub for sub in all_subs if sub.get("companies")]           # a sub-theme with no confirmed company is a count, not a row
    if subs:
        rows = [[sub["name"], whole_clause(sub.get("detail") or "", 160) or "–", str(len(sub.get("companies") or [])),
                 names5(sorted(sub.get("companies") or [], key=lambda c: -(c.get("cap") or 0))) or "None confirmed by its own description"] for sub in subs]
        head, widths = ["Sub-theme", "What it is", "Companies", "The largest, by market value"], [2.4, 4.6, 1.2, 4.0]
        note = "Each sub-theme's description is written by AI from general knowledge, with no figures; a company is shown only where its own description says it does that work."
        nh = note_h(note)
        first = table_pages(head, rows, widths, CW, BOT - TOP - nh - 0.07)[0]
        s = Slide("Sub-themes", f"{_n(len(all_subs), 'sub-theme')}, {len(subs)} with a listed company" + (f"; {len(first)} shown, the rest on the theme's page" if len(first) < len(rows) else ""),
                  eyebrow=eb(vc_part))
        s.add("table", (M, TOP, CW, BOT - TOP - nh - 0.07), head=head, rows=first, widths=widths, numeric=[False, False, True, False])
        s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

    # 5b. industry economics: the layers side by side, what moved the aggregate margin, and the questions the figures raise (R17-015)
    if chained:
        _economics(slides, v, shown, sec, ebm, eb("Industry economics"), section, lender)

    # 6. the appendix: ONE compact table of every confirmed company's key figures, one row each, so any figure can be checked (R19)
    layer_of = {c["symbol"]: x["layer"] for x in layers for c in x.get("companies") or []}
    prof_of = {c["symbol"]: c.get("profile") for x in layers for c in x.get("companies") or []}          # R25: an insurer has no GNPA column
    from .intel.theme_data import has_figures as figs_of        # q1: the dive's own rule for "with figures", so the appendix counts as page 4 does
    confirmed_ = [x for x in sec.get("leaders") or [] if status.get(x["symbol"]) != "unverified"]
    bare = [x for x in confirmed_ if not figs_of(x)]           # a stored page with no key figure isn't "with figures" (R20)
    lead = sorted((x for x in confirmed_ if figs_of(x)), key=lambda x: -(x.get("cap") or 0))
    # R36 (GPT review of the live R33 Retail deck: "Leslie's, Inc." on two identical rows): one company listed under two symbols is one row
    seen_, once_ = set(), []
    for x in lead:
        key_ = (re.sub(r"[^a-z0-9]+", " ", clean_name(str(x.get("name") or "")).lower()).strip(), x.get("revenue"))
        if key_[0] and key_[1] is not None and key_ in seen_:
            continue
        seen_.add(key_)
        once_.append(x)
    lead = once_
    if lead:
        # short headings on one line, so 20 or more rows fit a page (R20: 8 rows a page)
        lcols = [("revenue", "Revenue", 1.15), ("sales_1y", "Growth", 0.95), ("ebitda", "EBITDA", 0.95), ("net", "Net", 0.9), ("roce", "ROCE", 0.85)]
        if any(x.get("bank") for x in lead):
            lcols += [("roe", "ROE", 0.85)] + ([("gnpa", "GNPA", 0.85)] if any(x.get("bank") and (x.get("profile") or prof_of.get(x["symbol"])) != "insurer" for x in lead) else [])
        lcols += [("pe", "P/E", 0.8), ("pb", "P/B", 0.8)]
        lcell = {"sales_1y": lambda x: _chg(x.get("sales_1y")), "pe": lambda x: _times(x.get("pe")), "pb": lambda x: _times(x.get("pb"))}
        head = ["Company", "Layer", "Market value"] + [c[1] for c in lcols]
        widths = [2.5, 1.9, 1.2] + [c[2] for c in lcols]
        rows = [[name_of(x["symbol"], x["name"]), layer_of.get(x["symbol"]) or "–", cap(x.get("cap"))]
                + [lcell.get(k, lambda x, k=k: co_cell(x, k, amt))(x) for k, _, _ in lcols] for x in lead]
        if len({r[1] for r in rows}) <= 1:              # one layer for every company says nothing: no column (R19)
            head, rows, widths = [head[0]] + head[2:], [[r[0]] + r[2:] for r in rows], [widths[0]] + widths[2:]
        head, rows, widths, _ = drop_empty(head, rows, widths)
        note = ("Latest full year: revenue, its growth, EBITDA and net margins, ROCE; P/E on the last four quarters (none for a loss-maker)."
                + (" (whole company): whole-company figures." if wide else "")
                + (f" {ONE_OFF} {ONE_OFF_NOTE}." if any(x.get("one_off") for x in lead) else "")
                + (f" No reported figures yet: {names5(bare)}." if bare else ""))
        full = {c["symbol"]: c for x in layers for c in x.get("companies") or []}          # the layers' rows carry each company's years
        gb = growth_base_line([{**full.get(x["symbol"], {}), **x} for x in lead], amt)
        if gb:
            note += " " + gb
        cbase = {"compact": True, "full": [head.index("Layer")] if "Layer" in head else []}
        # R35 (GPT reviews of R31.5-R31.9: "Large-scale…", "Digital engineering and…" with the full names nowhere on the page): a page that
        # shows a layer's name cut says each such name in full under its table; every page keeps the room the longest such line needs
        lcol = head.index("Layer") if "Layer" in head else None           # its names get the room the figure columns don't use (table_layout)
        with_key = lambda rows_: note + (" " + short_names(head, rows_, widths, lcol) if short_names(head, rows_, widths, lcol) else "")      # noqa: E731
        nh = note_h(with_key(rows))
        for _ in range(3):              # a page's own columns can cut a name the whole table's don't: paged again with the room its key needs
            th = BOT - TOP - nh - 0.07
            pages = table_pages(head, rows, widths, CW, th, most=26, compact=True)
            tallest = max(note_h(with_key(chunk)) for chunk in pages)
            if tallest <= nh + 1e-6:
                break
            nh = tallest
        for k, chunk in enumerate(pages):
            s = Slide("Every company's figures" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      f"{_n(len(lead), 'confirmed company', 'confirmed companies')} with figures, one row each; {lead[0]['name']} is the largest at {cap(lead[0].get('cap'))}",
                      eyebrow=eb("Appendix"))
            s.add("table", (M, TOP, CW, th), head=head, rows=chunk, widths=widths, **cbase)
            s.add("text", (M, BOT - nh, CW, nh), paras=[with_key(chunk)], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            later_slides.append(s)
    fig_pages = len(later_slides)
    if any(cut for _, _, _, cut in rolls):       # R35: a layer's page left names off: every layer's full roll, one row each, in the appendix
        rhead, rwidths = ROLL_HEAD, ROLL_WIDTHS
        kind_ = ("how it earns shown and of the layer's kind, " if any(layer_families(v).values())
                 else "with no way of earning read for this theme's companies (so no layer is ranked), ")      # gl50: never "of the layer's kind" then
        rnote = (f"In a layer's calculations: confirmed by its own description, {kind_}with a revenue figure. "
                 "(partial: ...): in the calculations in part, the part named: the whole company's figures (revenue only, not its medians), a "
                 "figure not stored, or one not reconciled, invalid or on another period basis (out of its median). Left out, each reason before "
                 "the companies it is of: different revenue model, the company's way of earning and the layer's named; another business than its "
                 "official industry, by its own words; insufficient evidence, what is missing named; not confirmed in the theme, its own words "
                 "don't show this work; no figure stored.")
        rnh = note_h(rnote)
        rth = BOT - TOP - rnh - 0.1
        rrows = [r for name, r_in, r_out, _ in rolls for r in roll_rows(name, r_in, r_out, rth)]
        rpages = table_pages(rhead, rrows, rwidths, CW, rth)
        for k, chunk in enumerate(rpages):
            s = Slide(ROLL_TITLE + (f" ({k + 1} of {len(rpages)})" if len(rpages) > 1 else ""),
                      f"{_n(len(rolls), 'layer')} with a listed company left out of the calculations: who is in, and why each of the others is not",
                      eyebrow=eb("Appendix"))
            s.add("table", (M, TOP, CW, min(rth, table_height(rhead, chunk, rwidths, CW))), head=rhead, rows=chunk, widths=rwidths,
                  numeric=[False, False, False], tight=True)
            s.add("text", (M, BOT - rnh, CW, rnh), paras=[rnote], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            later_slides.append(s)

    roll_end = len(later_slides)
    _figure_sources(later_slides, v, eb("Appendix"))       # R46: every checked figure's source record, after the figures it is of
    sources_end = len(later_slides)
    _comparison_basis(later_slides, v, eb("Appendix"))     # R48: every comparison's metric, companies by name and rule

    # 7. tailwinds and risks, on one page (R19); the headlines and new listings stay on the theme's page
    tw_, rk_ = v.get("tailwinds") or [], v.get("risks") or []
    claims = [("Tailwind", c) for c in tw_] + [("Risk", c) for c in rk_]
    if claims:
        items = []
        dated = lambda c: c.get("status") == "current" and bool(c.get("source"))      # noqa: E731
        # tailwinds and risks evenly (R21): the same number of each at most, those with a dated source first, one of each in turn
        tw_s, rk_s = sorted(tw_, key=lambda c: not dated(c)), sorted(rk_, key=lambda c: not dated(c))
        k_each = min(CLAIMS_EACH, max(len(tw_s), len(rk_s)))
        turn = [x for pair in zip(tw_s[:k_each] + [None] * k_each, rk_s[:k_each] + [None] * k_each) for x in pair][:2 * k_each]
        order = [(kind, c) for kind, c in zip(["Tailwind", "Risk"] * k_each, turn) if c is not None]
        for kind, c in order:
            src = c.get("source") if c.get("status") == "current" else None
            tags = [(kind, UP if kind == "Tailwind" else DOWN, UP_SOFT if kind == "Tailwind" else DOWN_SOFT),
                    ("Dated source", INK2, CHIP) if src else ("General background (AI, no dated source)", MUTED, CHIP)]
            tied = claim_layers(c.get("text") or "", [x["layer"] for x in shown])
            sub = f"{src['headline']} · {_day(src.get('at'))} · {src.get('outlet') or ''}".rstrip(" ·") if src else None
            if tied:
                sub = (sub + " · " if sub else "") + "Layer: " + ", ".join(tied)
            items.append({"tags": tags, "text": c.get("text") or "", "url": (src or {}).get("url") or None, "sub": sub})
        cnote = ("Dated source: a dated headline or filing exists; it is not a check of the claim. General background: written by AI from general "
                 "knowledge, with no dated source. A claim a headline showed had ended is left out.")
        cnh = note_h(cnote)
        box = (M, TOP, CW, BOT - TOP - cnh - 0.1)
        cols, pages = 2, flow_pages(items, box, 2)
        if len(pages) > 1 and len(flow_pages(items, box, 3)) < len(pages):
            cols, pages = 3, flow_pages(items, box, 3)
        first = pages[0]
        nt, nr = sum(1 for x in first if x["tags"][0][0] == "Tailwind"), sum(1 for x in first if x["tags"][0][0] == "Risk")
        # R27: the count is of the claims this page shows (the denominator the page itself has), never of every claim the map holds
        dated_n = sum(1 for x in first if x["tags"][1][0] == "Dated source")
        sub_line = f"{_n(nt, 'tailwind')} and {_n(nr, 'risk')}, {dated_n} of the {len(first)} with a dated source"
        if len(rk_) < len(tw_):
            sub_line += f"; the map names fewer risks ({len(rk_)}) than tailwinds ({len(tw_)})"
        elif len(tw_) < len(rk_):
            sub_line += f"; the map names fewer tailwinds ({len(tw_)}) than risks ({len(rk_)})"
        if len(first) < len(claims):
            sub_line += "; the rest are on the theme's page"
        # LIVE7A-014: the contents line says what this page shows, with the page's own counts and words (the live Automotive deck's contents
        # said "4 tailwinds and 4 risks; 5 with a dated headline ... that shows it is still current" over a page of 2 and 2, "not a check")
        section("", "Tailwinds and risks", f"{_n(nt, 'tailwind')} and {_n(nr, 'risk')} shown, {dated_n} with a dated source"
                + ("; the rest are on the theme's page." if len(first) < len(claims) else "."))
        s = Slide("Tailwinds and risks", sub_line, eyebrow=eb("Tailwinds and risks"))
        s.add("flow", box, cols=cols, items=first)
        s.add("text", (M, BOT - cnh, CW, cnh), paras=[cnote], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)
    left_out.append(("unread", "the latest headlines and new listings"))

    # 8. the theme in numbers
    if sec and (v.get("members_with_figures") or shown):
        section("", "The theme in numbers", f"Reported figures from each company's stored page{', prices to ' + asof_text if asof else ''}; each slide says what it is on.")
        _numbers(slides, v, sec, cap, eb, left_out, name_of)
        _sector_slides(slides, v, amt, eb("The theme in numbers"))

    # 9. the notes, on one page: how the companies got in, who is confirmed, how to read the figures and what isn't in this deck (R19)
    who = [f"{_n(total, 'company', 'companies')} in all, each in one layer: {base_n:,} from the exchange's official industries"
           + (f", {named:,} named in the theme's own list" if named else "") + (f", {added:,} added by the AI from other industries." if added else ".")]
    if added:
        who.append(f"{confirmed:,} of the {added:,} added are confirmed by their own description" + (f"; {added - confirmed:,} not yet." if added > confirmed else "."))
    unv = checks.get("unverified") or []
    if unv:
        who.append(f"{_n(len(unv), 'company', 'companies')} whose own words don't show the work, left out of every median and total: {names5(unv)}.")
    if p.get("timed_out"):
        who.append(f"{p['timed_out']:,} couldn't be checked just now; the check runs again later.")
    figs = v.get("figures") or {}
    read = [f"What each figure measures, how it is worked out, its period, source and limits: ⟦{NOTES_TITLE}⟧.", MARKS_LINE]      # R27: the marks, once
    if figs.get("of") and figs.get("shown") and figs["of"] > figs["shown"]:
        read.append(f"Figures are worked out for {figs['shown']:,} of the theme's {figs['of']:,} companies: every one the map names, then the largest of the rest.")
    if wide:
        read.append("(whole company): a company that runs other businesses too; its figures are the whole company's.")
    none_ = [t for k, t in left_out if k == "none"]
    unread = [t for k, t in left_out if k == "unread"]
    lo_text = ([f"Nothing to show for this theme's companies yet: {'; '.join(none_)}."] if none_ else []) + \
        ([f"On the theme's page: {', '.join(unread)}, ownership, events and every company in its own words."] if unread else []) + \
        ["What the AI wrote: the overview, what each layer and sub-theme does and the general-background claims, from general knowledge with no figures."]
    cards_n = [{"title": "How the companies got in", "lines": overview_how}, {"title": "Who is in it", "lines": who},
               {"title": "Reading the figures", "lines": read}, {"title": "Not in this deck, and what the AI wrote", "lines": lo_text}]
    closing = THEME_DISCLAIMER + " The AI's layers and additions can be wrong: check a company's own description."
    room = BOT - TOP - note_h(closing) - 0.1
    cw2 = (CW - 0.25) / 2

    def notes_h(size):
        return max(card_height(cards_n[0], cw2, True, size), card_height(cards_n[1], cw2, True, size)) + 0.25 + \
            max(card_height(cards_n[2], cw2, True, size), card_height(cards_n[3], cw2, True, size))
    tsize = next((z for z in (13, 12, BODY_MIN) if notes_h(z) <= room), BODY_MIN)
    while notes_h(tsize) > room and any(len(c["lines"]) > 1 for c in cards_n):          # one page whatever: the longest card gives up a line
        big = max(cards_n, key=lambda c: card_height(c, cw2, True, tsize) if len(c["lines"]) > 1 else 0)
        big["lines"] = big["lines"][:-1]
    s = Slide("How to read this deck", "How each company got into the theme, what the figures are, and what the AI wrote", eyebrow=eb("Notes"))
    h1 = max(card_height(cards_n[0], cw2, True, tsize), card_height(cards_n[1], cw2, True, tsize))
    h2 = min(room - h1 - 0.25, max(card_height(cards_n[2], cw2, True, tsize), card_height(cards_n[3], cw2, True, tsize)))
    s.add("cards", (M, TOP, CW, h1), cols=2, bullets=True, items=cards_n[:2], size=tsize)
    s.add("cards", (M, TOP + h1 + 0.25, CW, h2), cols=2, bullets=True, items=cards_n[2:], size=tsize)
    s.add("text", (M, BOT - note_h(closing), CW, note_h(closing)), paras=[closing], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
    notes = s
    slides.append(s)
    fin = any(c.get("bank") for x in layers for c in x.get("companies") or []) or any(x.get("bank") for x in sec.get("leaders") or [])
    built = notes_slides(slides + later_slides, eb("Notes"), fin)         # R25: one page on how the figures shown are built, before the appendix
    slides.extend(built)
    if not members:
        s = Slide("No company yet", "No company has been placed in this theme yet", eyebrow=eb("Notes"))
        s.add("cards", (M, TOP, CW, 1.2), cols=1, fill=True, items=[{"title": "What to do", "lines": ["Try a more specific theme on the Themes page, then download the deck again."]}])
        slides.append(s)
    # the appendix: the one table of every confirmed company's figures, and nothing else
    slides.extend(later_slides)
    ends = [at for _, _, at in parts[1:]] + [len(slides)]
    firsts = [(t, line, next(iter(slides[at:end]), None)) for (t, line, at), end in zip(parts, ends)]
    crow = [[t, line, str(slides.index(first) + 1)] for t, line, first in firsts if first is not None and first.eyebrow and "Appendix" not in first.eyebrow]
    crow.append(["Notes", "How the companies got in, how to read the figures and what isn't in this deck.", str(slides.index(notes) + 1)])
    if built:
        crow.append([NOTES_TITLE, "What each figure shown measures, how it is worked out, its period and source, and its limits.", str(slides.index(built[0]) + 1)])
    if later_slides:
        apx = [x for x in (f"Every confirmed company's key figures, one row each ({_n(fig_pages, 'page')})" if fig_pages else "",
                           "who is in each layer's calculations" if roll_end > fig_pages else "",
                           "each checked figure's source and statement lines" if sources_end > roll_end else "",              # R46
                           "each comparison's companies and rule" if len(later_slides) > sources_end else "") if x]          # R48
        crow.append(["Appendix", "; ".join(apx)[:1].upper() + "; ".join(apx)[1:] + ".", str(slides.index(later_slides[0]) + 1)])
    contents.add("table", (M, TOP, CW, min(BOT - TOP, table_height(["Part", "What it holds", "Page"], crow, [2.6, 8.4, 0.9], CW))),
                 head=["Part", "What it holds", "Page"], rows=crow, widths=[2.6, 8.4, 0.9], numeric=[False, False, True], tight=True)
    slides[0].tidied = tidy_tables(slides)          # LIVE6-008: no line through under 4 points, no row of dashes, no table mostly dashes
    slides[0].checked = check_deck(slides)          # R25: every headline and finding figure found again in the tables, else dropped
    slides[0].gate = publication_gate(slides, v, slides[0].checked)        # R27: the checklist before a deck is stored, its result kept with it
    _sections(sector, slides)
    _refs(slides)
    for x in slides:                  # a "Slide" column whose pages aren't in this deck says nothing: dropped (R19)
        for b in x.blocks:
            if b["kind"] == "table" and "Slide" in b["head"]:
                b["head"], b["rows"], b["widths"], b["numeric"] = drop_empty(b["head"], b["rows"], b["widths"], b.get("numeric"), keep=tuple(range(len(b["head"]) - 1)))
    whole_deck(slides)
    lay = layout_gate(slides)
    # R48: a page reference that found no page (a provenance or comparison reference that would print as nothing) fails the source item
    lay["failed"] += [{"slide": t, "text": f"⟦{ref}⟧", "why": "a page reference that finds no page", "rule": "sourced"}
                      for t, ref in getattr(slides[0], "unresolved", None) or []]
    slides[0].gate = with_layout(slides[0].gate, {**lay, "all_tidied": getattr(slides[0], "tidied", None) or []})       # R35: nothing cut short, checked on the pages as they will print
    return slides, footer


def base_quarter(label: str | None) -> str | None:
    """The quarter a year before one named like "Sep 2026": "Sep 2025"."""
    m = re.match(r"\s*([A-Za-z]{3})\w*\s+(\d{4})", str(label or ""))
    return f"{m.group(1).title()} {int(m.group(2)) - 1}" if m else None


def confirmed_n(layer: dict) -> int:
    """How many of a layer's companies are confirmed members (an unconfirmed one is listed, never in the figures)."""
    return sum(1 for c in layer.get("companies") or [] if c.get("status") != "unverified")


SMALL_TITLE = "Smaller layers"
SMALL_MAX = 2                   # d1: a layer of this many confirmed companies or fewer has no page of its own (a median is of MIN_BASE or more)
LAYER_ROWS_MIN = 5              # d1: a layer's page shows at least this many of its companies (all of a smaller layer)


def _smaller_layers(slides: list, small: list, amt, eyebrow: str) -> None:
    """Every layer with SMALL_MAX confirmed companies or fewer on one compact page (R28; d1: two as well as one): one row a company, in the
    value chain's order (never ranked): the layer (said on its first row), its company, what it does in its own words, and its key figures.
    A table that runs over a page goes on to the next."""
    rows_, cos = [], []
    for x in small:
        sure = sorted((c for c in x.get("companies") or [] if c.get("status") != "unverified"), key=lambda c: -(c.get("cap") or 0))
        others = [o.get("name") or o.get("symbol") for o in x.get("companies") or [] if o.get("status") == "unverified"]
        for i, c in enumerate(sure):
            from .intel.theme_data import calc_of
            why = why_kind(calc_of(c))        # LIVE7A-005: a row's mark is its kept reason first, the whole company's figures after (ex49: its kind)
            mark = ROLL_TAG.get(why) if why else ("whole company" if c.get("company_wide") or c["symbol"] in (x.get("company_wide") or []) else
                                                  "on its industry" if c.get("on_industry") else "own design" if c.get("own_goods") else
                                                  "on its words" if c.get("by_words") else "")
            name = (f"{c['name']} ({mark})" if mark else c["name"]) \
                + (f"; also listed, not confirmed: {', '.join(others)}" if others and i == len(sure) - 1 else "")
            rows_.append(({**x, "layer": x["layer"] if i == 0 else ""}, c, name))
            cos.append(c)
    lend = is_lender_set(cos)
    keys = ("revenue", "roe", "net") if lend else ("revenue", "ebitda", "net", "roce")
    cols = [col for col in co_cols(cos) if col[0] in keys]
    head = ["Layer", "Company", "What it does"] + [col[1] for col in cols] + ["Year"]
    widths = [2.3, 2.3, 3.6] + [col[2] for col in cols] + [1.0]
    body = [[x["layer"], name, whole_clause(_what(c.get("what") or "", c.get("name") or ""), 110) or NO_WORDS]
            + [co_cell(c, k, amt) for k, _, _ in cols] + [c.get("year") or "–"] for x, c, name in rows_]
    head, body, widths, numeric = drop_empty(head, body, widths, [False, False, False] + [True] * len(cols) + [False], keep=(0, 1, 2))
    ones = all(confirmed_n(x) == 1 for x in small)
    marks_ = {re.search(r"\(([^()]+)\)(?:;|$)", nm).group(1) for _, _, nm in rows_ if re.search(r"\(([^()]+)\)(?:;|$)", nm)}
    said_ = {"insufficient evidence": "(insufficient evidence): its evidence doesn't show clearly how it earns, so it is left out of its layer's figures.",
             "different model": "(different model): it earns another way than its layer's other companies, so it is left out of its figures.",
             "another business": "(another business): its own words describe another business than its official industry, so it is left out of its figures.",
             "own design": "(own design): read as a retailer, its own words say it designs the goods it sells; in its layer's figures.",
             "on its words": "(on its words): the map placed it here and its own words say the layer's name and no other way of earning; in its figures.",
             ROLL_TAG["no figure stored"]: f"({ROLL_TAG['no figure stored']}): no revenue figure is stored for it.",
             "whole company": "(whole company): it runs other businesses too, so its figures are the whole company's.",
             "on its industry": "(on its industry): no description of its own; in its layer by its official industry, that of most of the "
                                "layer's companies."}
    note = (("Each of these layers has one confirmed company" if ones else f"Each of these layers has {SMALL_MAX} confirmed companies or fewer")
            + f", so it has no median (a median is of {MIN_BASE} or more) and no page of its own; it is in the value chain's table. "
            "Rows in the value chain's order; each company's latest full year; how each figure is built: ⟦" + NOTES_TITLE + "⟧."
            + "".join(f" {said_[k]}" for k in said_ if k in marks_))
    # d1: what each of these layers does, its description's first sentence (written by AI), since none has a page of its own
    firsts = [(x["layer"], re.split(r"(?<=[.!?])\s", str(x.get("description") or "").strip(), maxsplit=1)[0]) for x in small if x.get("description")]
    if firsts:
        note += (" What each layer does (written by AI from general knowledge, with no figures): "
                 + "; ".join(f"{n_}: {d_[:1].lower() + d_[1:].rstrip('.')}" for n_, d_ in firsts) + ".")
    nh = note_h(note)
    th = BOT - TOP - nh - 0.1
    pages = table_pages(head, body, widths, CW, th)
    for k, chunk in enumerate(pages):
        s = Slide(SMALL_TITLE + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                  (f"{_n(len(small), 'layer')} with one confirmed company each" if ones else
                   f"{_n(len(small), 'layer')} of {SMALL_MAX} confirmed companies or fewer, {len(rows_)} companies")
                  + ": the company, what it does and its key figures, one row each",
                  eyebrow=eyebrow)
        s.add("table", (M, TOP, CW, th), head=head, rows=chunk, widths=widths, numeric=numeric)
        s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)


def economics_questions(v: dict, shown: list, sec: dict, ebm) -> list[str]:
    """Questions the figures raise, each stating the computed facts it rests on (R17-015). Facts and questions only: no answer, no view of
    what to do; a question is asked only when its figures exist."""
    out = []
    chain = v.get("chain") or {}
    rows = {r["layer"]: r for r in chain.get("rows") or []}
    hi, lo = rows.get(chain.get("highest")), rows.get(chain.get("lowest"))
    from .intel.theme_data import HEADLINE_MIN, of_words as ow, period_basis, rank_pair
    # m2: the question says which layers its highest and lowest are of, as the headline it repeats does
    scope_ = f"Among the {len(chain.get('compared') or [])} layers with at least {HEADLINE_MIN} companies with the figure, " if len(chain.get("compared") or []) >= 2 else ""
    if hi and lo and chain.get("measure") == "roe":
        out.append(f"{scope_}{hi['layer']} has the highest median return on equity ({_pc(hi['roe'])}, {ow(hi['roe_n'], hi.get('n'))}) and {lo['layer']} the lowest "
                   f"({_pc(lo['roe'])}, {ow(lo['roe_n'], lo.get('n'))}). What in each layer's business makes that gap? The figures show the gap, not its cause.")
    elif hi and lo:
        out.append(f"{scope_}{hi['layer']} has the highest median EBITDA margin ({ebm(hi['ebitda'])}, {ow(hi['ebitda_n'], hi.get('n'))}) and {lo['layer']} the lowest "
                   f"({ebm(lo['ebitda'])}, {ow(lo['ebitda_n'], lo.get('n'))}). What in each layer's business makes that gap? The figures show the gap, not its cause.")
    q = sec.get("quarter") or {}
    if q.get("quarter") and (q.get("sales") or {}).get("n", 0) >= MIN_BASE:
        base = base_quarter(q["quarter"])
        out.append(f"The quarter to {q['quarter']}: median revenue {_chg(q['sales']['median'])} on the quarter to {base} "
                   f"({_n(q['sales']['n'], 'company', 'companies')}). How much of the change is the base: was the quarter to {base} "
                   "itself unusually high or low? The deck holds only this one comparison.")
    md = sec.get("margin_drivers") or {}
    if md.get("companies"):
        t = md["companies"][0]
        out.append(f"The aggregate EBITDA margin went from {_pc(md['start'])} in {md['from']} to {_pc(md['end'])} in {md['to']} ({_n(md['n'], 'company', 'companies')}). "
                   f"{t['name']} accounts for {_pts(t['part'])} of the move: its own margin went from {_pc(t['margin_from'])} to {_pc(t['margin_to'])} and its "
                   f"share of the group's revenue from {_pc(t['share_from'])} to {_pc(t['share_to'])}. Was it the margin or the weight?")
    peers = dated_peers(v)
    from .intel.theme_data import relative_ok as _rel
    if (peers.get("pe") or {}).get("premium") is not None and (peers.get("sales_3y") or {}).get("n") and _rel(sec.get("valuation") or {}):
        g = peers["sales_3y"]
        out.append(f"{pe_peer_line(peers['pe'])}; their revenue grew {_chg(g['theme'])} a year over 3 years against {_chg(g['peers'])} for their peers. "
                   "What do the prices take into account that past growth doesn't show?")
    gm = []
    for x in shown:
        cos = [c for c in x.get("companies") or [] if in_calc(c) and not c.get("company_wide")]
        g = sorted(c["sales_1y"] for c in cos if c.get("sales_1y") is not None)
        if g and x.get("basis") != "rest" and not x.get("scale"):      # the "Other" group is never compared (R22), nor a half alone (d1)
            from statistics import median as _m
            gm.append((x["layer"], _m(g), len(g), len(cos), x.get("model"), period_basis(cos), x.get("intensity"),
                       [c["name"] for c in cos if c.get("sales_1y") is not None], x.get("intensity_n"), listed_names(x), x.get("intensity_missing") or []))
    pair = rank_pair(gm, lambda t: t[1], lambda t: t[2], of=lambda t: t[3], model=lambda t: t[4], basis=lambda t: t[5], intensity=lambda t: t[6])
    if pair:
        f_, s_ = pair
        note_basis(v, "Layers side by side", "revenue growth in the latest year (median)", [
            {"layer": t[0], "value": t[1], "n": t[2], "of": t[3], "model": t[4], "basis": t[5], "intensity": t[6], "intensity_n": t[8], "names": t[7], "listed": t[9],
             "intensity_missing": t[10]}
            for t in comparable_basis_rows(gm, lambda t: t[1], lambda t: t[2], lambda t: t[3], lambda t: t[4], lambda t: t[5], lambda t: t[6])],
            high=f_[0], low=s_[0], said="the questions the figures raise")
        out.append(f"Median revenue growth in the latest year: {_chg(f_[1])} in {f_[0]} ({ow(f_[2], f_[3])}), {_chg(s_[1])} in {s_[0]} ({ow(s_[2], s_[3])}). "
                   "Is the difference in demand, in prices, or in the products each layer's companies make?")
    return out[:1] + sector_questions(sec) + out[1:]


def _economics(slides: list, v: dict, shown: list, sec: dict, ebm, eyebrow: str, section, lender: bool = False) -> None:
    """Industry economics (R17-015), a short part: each layer's margins, returns, growth and valuation side by side; what moved the aggregate
    EBITDA margin between the last two years (companies and layers, in points that add up to the change); and the questions the figures raise.
    Every number is computed from the stored figures; a page whose figures don't exist is not drawn, and the part is left out when none is."""
    from statistics import median as _m
    lay = []
    for x in shown:
        every = [c for c in x.get("companies") or [] if in_calc(c)]            # the layer's one record of who is in its calculations (lane m1)
        cos = [c for c in every if not c.get("company_wide")] or every
        st = x.get("stats") or {}
        g = [c["sales_1y"] for c in cos if c.get("sales_1y") is not None]
        pe = [c["pe"] for c in cos if c.get("pe") and c["pe"] > 0]
        # a median of fewer than MIN_BASE companies is no median here (R20): no value, its count kept for the cell
        med = lambda k: (st.get(k) or {}).get("median") if ((st.get(k) or {}).get("n") or 0) >= MIN_BASE else None      # noqa: E731
        from .intel.theme_data import period_basis
        lay.append({"layer": x["layer"], "n": len(every), "listed": len(x.get("companies") or []), "rest": x.get("basis") == "rest" or bool(x.get("scale")),
                    "intensity_n": x.get("intensity_n"), "listed_names": listed_names(x), "intensity_missing": x.get("intensity_missing") or [],
                    # R48: who is in each median by name (the comparison basis): the layer's own records, growth from its companies
                    "names": {**{k: list(n) for k, n in (x.get("in_stats") or {}).items()}, "growth": [c["name"] for c in cos if c.get("sales_1y") is not None]},
                    "model": x.get("model"), "basis": period_basis(cos), "intensity": x.get("intensity"), "ebitda": med("ebitda"), "roce": med("roce"),
                    "growth": _m(g) if len(g) >= MIN_BASE else None, "growth_n": len(g), "pe": _m(pe) if len(pe) >= MIN_BASE else None, "pe_n": len(pe),
                    **{k: med(k) for k in ("net", "roe", "nii_assets", "gnpa", "pb")}, **{f"{k}_n": (st.get(k) or {}).get("n") or 0 for k in STATS_SHOWN}})
    lay = [x for x in lay if x["n"]]
    if len(lay) < 2:          # one layer: its own slide already shows its medians, so no page that sets it beside nothing
        lay = []
    md = sec.get("margin_drivers") or {}
    qs = economics_questions(v, shown, sec, ebm)
    if not lay and not md and not qs:
        return
    section("", "Industry economics", "Each layer's margins, returns, growth and valuation side by side, what moved the aggregate margin, and the questions "
                                      "the figures raise, each computed from the reported figures.")
    room = []              # (slide, x, y, w, h): the space a page leaves under its table, where the questions go when they fit
    shrink = []            # R46: (slide, chart block): a chart page of this part whose chart can give the questions room under it
    if lay:
        # a lender's layers on lenders' measures (R18): net margin, ROE, net interest income over assets, gross NPA and P/B beside growth and P/E
        cellm = lambda x, k, f: _medn(None, x["n"], f, n=x[f"{k}_n"], value=x[k] if x[f"{k}_n"] >= MIN_BASE else (x[k] or 0) or 1)   # noqa: E731
        rows = [[x["layer"], companies_cell(x["n"], x["listed"]), cellm(x, "ebitda", ebm), cellm(x, "roce", _pc)]
                + ([cellm(x, "net", _pc), cellm(x, "roe", _pc), cellm(x, "nii_assets", _pc), cellm(x, "gnpa", _pc)] if lender else [])
                + [_medn(None, x["n"], _chg, n=x["growth_n"], value=x["growth"] if x["growth"] is not None else (1 if x["growth_n"] else None)),
                   _medn(None, x["n"], _times, n=x["pe_n"], value=x["pe"] if x["pe"] is not None else (1 if x["pe_n"] else None))]
                + ([cellm(x, "pb", _times)] if lender else []) for x in lay]
        head = ["Layer", "Companies", "EBITDA margin", "ROCE"] + (["Net margin", "ROE", "NII / assets", "Gross NPA"] if lender else []) + ["Revenue growth, 1 year", "P/E"] + (["P/B"] if lender else [])
        widths = [3.0, 1.1, 1.3, 1.0] + ([1.1, 1.0, 1.2, 1.1] if lender else []) + [1.7, 1.2] + ([0.9] if lender else [])
        head, rows, widths, _ = drop_empty(head, rows, widths)
        a_, b_ = ("roe", "net") if lender else ("ebitda", "roce")
        both = [{**x, "ebitda": x[a_], "roce": x[b_]} for x in lay if x[a_] is not None and x[b_] is not None]
        chart = 2 <= len(both) <= 10
        # R35: a chart sits beside a table of four figure columns at most. A wider table keeps the full width, and its chart has a page of
        # its own after it unless the value chain's page already charts the layers' medians (one such page a deck, not two)
        beside = chart and len(head) <= 5
        charted_ = any(b["kind"] == "hbars" for s_ in slides if s_.title.startswith(("The value chain by layer", "Median ")) for b in s_.blocks)
        tw = 7.6 if beside else CW
        rk, rname = ("roe", "ROE") if lender else ("roce", "ROCE")
        cmp_ = [x for x in lay if not x.get("rest")]            # the "Other" group is never called highest or fastest (R22)
        # lane m1 (the live R32 Real estate and Utilities decks: contractors ranked against developers, equipment makers against generators
        # and distributors): a highest or a fastest is said only among layers of one kind of business, by the rule of every other ranking
        # (theme_data.comparable_rows: one business-model family and sub-basis, the headline floor and coverage, one period basis, alike
        # in asset intensity); the headline says how many layers that is when it isn't all of them
        from .intel.theme_data import rank_top
        same = dict(of=lambda x: x["n"], model=lambda x: x["model"], basis=lambda x: x["basis"], intensity=lambda x: x["intensity"])
        got_r = rank_top(cmp_, lambda x: x[rk], lambda x: x[f"{rk}_n"], **same)
        got_g = rank_top(cmp_, lambda x: x["growth"], lambda x: x["growth_n"], **same)
        best_r, fast = (got_r[0] if got_r else None), (got_g[0] if got_g else None)
        for got, key, what in ((got_r, rk, f"median {rname}"), (got_g, "growth", "revenue growth in the latest year (median)")):
            if got:                       # R48: the layers each "highest" is among, their companies by name and the rule
                note_basis(v, "Layers side by side", what, [{"layer": x["layer"], "value": x[key], "n": x[f"{key}_n"], "of": x["n"], "model": x["model"],
                                                            "basis": x["basis"], "intensity": x["intensity"], "intensity_n": x.get("intensity_n"),
                                                            "intensity_missing": x.get("intensity_missing") or [],
                                                            "names": x["names"].get(key) or [], "listed": x["listed_names"]} for x in got[1]],
                           high=got[0]["layer"])
        sizes = {len(g[1]) for g in (got_r, got_g) if g}
        scope = lambda g: f" among the {len(g[1])} layers of one kind of business" if len(sizes) > 1 and len(g[1]) < len(cmp_) else ""      # noqa: E731
        bits = []
        if best_r:
            bits.append(f"highest median {rname} in {best_r['layer']} ({_pc(best_r[rk])})" + scope(got_r))
        if fast:
            bits.append(f"fastest median revenue growth in {fast['layer']} ({_chg(fast['growth'])})" + scope(got_g))
        from .intel.theme_data import HEADLINE_MIN
        if len(sizes) == 1 and min(sizes) < len(cmp_):
            bits.append(f"among the {min(sizes)} layers of one kind of business")
        msg = (f"Medians by layer, among the layers with at least {HEADLINE_MIN} companies with the figure: " + "; ".join(bits)
               + ("; the \"Other\" group left out" if len(cmp_) < len(lay) else "")) if bits else \
            f"{_n(len(lay), 'layer')}: its median company's margins, returns, growth and P/E"
        note = ("Medians of each layer's confirmed companies (whole-company figures left out where the layer has its own); a median of fewer companies "
                f"than the layer has shows its count, as N of M. Periods: ⟦{NOTES_TITLE}⟧."
                + (f" Each ranking's layers, companies and rule: ⟦{COMPARE_TITLE}⟧." if bits else ""))
        nh = note_h(note)
        for k, chunk in enumerate(pages := table_pages(head, rows, widths, tw, BOT - TOP - nh - 0.07)):
            s = Slide("Layers side by side" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=eyebrow)
            th = min(BOT - TOP - nh - 0.07, table_height(head, chunk, widths, tw))
            s.add("table", (M, TOP, tw, th), head=head, rows=chunk, widths=widths, tight=True)
            room.append((s, M, TOP + th + 0.25, tw, BOT - nh - 0.15 - (TOP + th + 0.25)))
            n1, n2 = ("ROE", "Net margin") if lender else ("EBITDA margin", "ROCE")
            series = [(n1, [x["ebitda"] for x in both], BLUE), (n2, [x["roce"] for x in both], ORANGE)]
            if beside and k == 0:
                s.add("columns", (M + tw + 0.4, TOP, CW - tw - 0.4, BOT - TOP - nh - 0.07), title=f"Median {n1} and {n2}", fmt="pct",
                      cats=[x["layer"] for x in both], series=series)
            s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
        if chart and not beside and not charted_:
            cnote = (f"Each pair of columns: the layer's median company, latest full year. A layer is drawn when both figures are medians of {MIN_BASE} "
                     f"companies or more; every layer is in the table before this page. Periods: ⟦{NOTES_TITLE}⟧.")
            ch_ = note_h(cnote)
            s = Slide(f"Median {n1} and {n2} by layer", f"Each layer's median company: {n1} beside {n2}, the layers side by side", eyebrow=eyebrow)
            s.add("columns", (M, TOP, CW, BOT - TOP - ch_ - 0.2), fmt="pct", cats=[x["layer"] for x in both], series=series)
            s.add("text", (M, BOT - ch_, CW, ch_), paras=[cnote], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
            shrink.append((s, s.blocks[0]))
    if md.get("companies"):
        lead = md["layers"][0] if md.get("layers") else None
        msg = (f"The aggregate EBITDA margin went from {_pc(md['start'])} in {md['from']} to {_pc(md['end'])} in {md['to']} ({_pts(md['change'])}, "
               f"{_n(md['n'], 'company', 'companies')})" + (f"; {lead['layer']} accounts for {_pts(lead['part'])} of it" if lead and len(md["layers"]) > 1 else ""))
        rows = [[x["name"], x.get("layer") or "–", f"{ebm(x['margin_from'])} → {ebm(x['margin_to'])}", f"{_pc(x['share_from'])} → {_pc(x['share_to'])}", _pts(x["part"])]
                for x in md["companies"]]
        rows.append([f"All {md['n']} companies", "", f"{_pc(md['start'])} → {_pc(md['end'])}", "", _pts(md["change"])])      # the headline's figures (R25)
        head, widths = ["Company", "Layer", "EBITDA margin", "Share of revenue", "Part of the move"], [2.6, 2.2, 1.6, 1.6, 1.3]
        lw = 8.6 if len(md.get("layers") or []) > 1 else CW
        note = (f"Each company's part: its EBITDA as a share of all {md['n']} companies' revenue in {md['to']}, less the same in {md['from']}; the parts "
                "add up to the change. A part moves with the company's own margin and with its weight in the group's revenue. The companies that moved it most.")
        nh = note_h(note)
        while len(rows) > 2 and table_height(head, rows, widths, lw) > BOT - TOP - nh - 0.07:
            rows.pop(-2)          # R35: long names made the table taller than its page and the total's row was left off; a company's row gives way
        s = Slide("What moved the aggregate margin", msg, eyebrow=eyebrow)
        th = min(BOT - TOP - nh - 0.07, table_height(head, rows, widths, lw))
        s.add("table", (M, TOP, lw, th), head=head, rows=rows, widths=widths, tight=True, strong=[len(rows) - 1])
        room.append((s, M, TOP + th + 0.25, lw, BOT - nh - 0.15 - (TOP + th + 0.25)))
        if lw < CW:
            s.add("table", (M + lw + 0.3, TOP, CW - lw - 0.3, BOT - TOP - nh - 0.07), head=["Layer", "Part"],
                  rows=[[x["layer"], _pts(x["part"])] for x in md["layers"]], widths=[2.0, 1.0])
        s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)
    if qs:
        # under a table of this part where they fit (no half-empty page), else on a page of their own
        card = {"title": "Questions the figures raise", "lines": qs[:5]}
        spot = next((r for r in room if card_height(card, r[3], True, 12) + 0.1 <= r[4]), None)
        # R46 (the outside review of the live R45 Insurance deck: one question alone on a page, a large blank under it): else under this part's
        # chart, the chart made shorter, when the chart keeps at least CHART_MIN of height; a page of their own only when neither has room
        fit = next(((sl, b) for sl, b in shrink if b["box"][3] - (card_height(card, b["box"][2], True, 12) + 0.1 + 0.25) >= CHART_MIN), None)
        if spot:
            sl, x, y, w, _ = spot
            sl.add("cards", (x, y, w, card_height(card, w, True, 12) + 0.1), cols=1, fill=True, bullets=True, size=12, items=[card])
        elif fit:
            sl, b = fit
            x, y, w, h = b["box"]
            ch = card_height(card, w, True, 12) + 0.1
            b["box"] = (x, y, w, h - ch - 0.25)
            sl.add("cards", (x, y + h - ch, w, ch), cols=1, fill=True, bullets=True, size=12, items=[card])
            sl.subtitle += "; the questions the figures raise under it"
        else:
            s = Slide("Questions the figures raise", "Each question with the computed figures it rests on; the figures don't answer them", eyebrow=eyebrow)
            s.add("cards", (M, TOP, CW, min(BOT - TOP, card_height(card, CW, True, 13) + 0.1)), cols=1, fill=True, bullets=True, size=13, items=[card])
            slides.append(s)


# ---------- R23: each sector's own operating figures, as filed; R27: whom each applies to (metric_registry) ----------
SECTOR_TITLE = "Sector operating figures"
SECTOR_LEAD = {"bank": ("gnpa_f", "cet1", "advances_growth", "credit_cost"), "insurer": ("solvency", "combined_ratio", "claims_ratio", "persistency_13"),
               "us": ("sbc_share", "fcf_margin", "capex_share", "rd_share", "inventory_days", "rpo_growth", "deferred_growth")}
SECTOR_PAGE = {"bank": "banks", "insurer": "insurers", "us": "US companies", "orders": "order books"}
SECTOR_WHO = {"bank": ("bank", "banks"), "insurer": ("insurer", "insurers"), "us": ("company", "companies"), "orders": ("company", "companies")}
_SHORT = {"npa": "NPA", "cet1": "CET1", "sbc": "SBC", "rpo": "RPO", "fcf": "FCF", "r&d": "R&D", "nii": "NII", "vnb": "VNB"}


def sector_fmt(key: str, amt=None):
    """How one filed sector figure prints: a share in %, a change signed, a ratio in times, days whole, an amount in the theme's money."""
    from .intel.metric_registry import BY_ID
    kind = BY_ID[key].unit
    if kind == "chg":
        return _chg
    if kind == "x":
        return lambda x: _times(x, 2)
    if kind == "days":
        return lambda x: f"{x:,.0f} days"
    if kind == "amt":
        return amt or (lambda x: f"{x:,.0f}")
    return _pc


def _low(label: str) -> str:
    # gl52 (R52): an acronym keeps its case ("IT services", never "it services")
    return " ".join(_SHORT.get(w.lower(), w if sum(ch.isupper() for ch in w) >= 2 else w.lower()) for w in label.split())


def _med_of(st: dict, fmt) -> str:
    """A headline median with its base: "4.6% (52 of 53)" (R27: M is those it applies to; R29: every sector figure states its own sample
    wherever it appears, "(19 of 19)" too, so a smaller sample is never silent)."""
    return fmt(st["median"]) + (f" ({st['n']} of {st['of']})" if st.get("of") else "")


def _medn_of(st: dict, of: int | None, fmt) -> str:
    """_medn with the base always "N of M" (R29: a sector figure states its own sample everywhere): "1.2% (7 of 19)", "1.2% (19 of 19)"."""
    got = _medn(st, of, fmt)
    n = (st or {}).get("n") or 0
    return got[:-len(f" ({n})")] + f" ({n} of {of})" if of and n and got.endswith(f" ({n})") else got


def read_so_far(f: dict, one: str, many: str) -> str:
    """R29: a family whose filed figures are still being read says so, with the count read: "Filed figures read for 7 of 19 banks so far; 12
    still being read." (the live R27 Banks deck showed a median of 7 as if it were the theme's); "" when none is waiting."""
    if not f.get("pending"):
        return ""
    of = f.get("of") or 0
    return f"Filed figures read for {f.get('read', of - f['pending'])} of {of} {one if of == 1 else many} so far; {f['pending']} still being read."


def _lead_keys(fam: str, f: dict) -> list[str]:
    """The figures a family's findings line may state: those the registry lets headline (metric_registry.headline_ok), lead figures first;
    a family summary made before R27 (no "headline") its lead figures."""
    if "headline" not in f:
        return list(SECTOR_LEAD.get(fam, ()))
    ok = set(f.get("headline") or ())
    return [k for k in SECTOR_LEAD.get(fam, ()) if k in ok] + [k for k in f.get("keys") or () if k in ok and k not in SECTOR_LEAD.get(fam, ())]


def sector_lines(sec: dict, waiting: bool = True) -> list[str]:
    """The findings' lines for the sector figures: for each family, the medians of its headline figures over at least MIN_BASE companies (R20),
    each "N of M" of the companies it applies to and covering at least half of them (R27); insurers by type, never one median across types.
    R29: a family still being read says how many are read so far (`waiting`: its own line first)."""
    from .intel.metric_registry import BY_ID
    from .intel.sector_metrics import TYPE_NAMES
    from .intel.theme_data import headline_ok
    out = []
    for fam, f in ((sec.get("sector") or {}).get("families") or {}).items():
        if waiting and read_so_far(f, *SECTOR_WHO[fam]):
            out.append(read_so_far(f, *SECTOR_WHO[fam]))
        groups = [(fam, f, SECTOR_WHO[fam])]
        if fam == "insurer" and len(f.get("types") or {}) > 1:
            groups = [(fam, t, TYPE_NAMES[k]) for k, t in f["types"].items()]
        for fam_, g, (one, many) in groups:
            parts = []
            for k in _lead_keys(fam_, g):
                st = (g.get("medians") or {}).get(k)
                if st and st.get("median") is not None and headline_ok(st.get("n", 0), st.get("of") or g.get("n"), floor=MIN_BASE):
                    st = {**st, "of": st.get("of") or g.get("n")}
                    parts.append(f"{_low(BY_ID[k].label)} {_med_of(st, sector_fmt(k))}")
            if parts:
                out.append(f"Median of the {_n(g['n'], one, many)} with filed figures: {', '.join(parts[:4])}.")
    return out


def sector_questions(sec: dict) -> list[str]:
    """Questions the filed sector figures raise, each with its computed medians (facts and questions only; asked only when the figures exist
    and may headline: R27, never RPO for chip makers)."""
    fams = (sec.get("sector") or {}).get("families") or {}
    from .intel.theme_data import headline_ok

    def med(f, k):
        st = (f.get("medians") or {}).get(k) or {}
        if not headline_ok(st.get("n", 0), st.get("of") or f.get("n"), floor=MIN_BASE) or ("headline" in f and k not in (f.get("headline") or ())):
            return None
        return st
    out = []
    b = fams.get("bank") or {}
    a, d = med(b, "advances_growth"), med(b, "deposit_growth_f")
    if a and d:
        out.append(f"Median advances growth {_chg(a['median'])} ({a['n']} banks) against median deposit growth {_chg(d['median'])} ({d['n']}), each on a "
                   "year before. Where does the rest of the lending's funding come from, or go? The figures show the two rates, not the funding mix.")
    i = fams.get("insurer") or {}
    i = ((i.get("types") or {}).get("general") or i) if len(i.get("types") or {}) > 1 else i
    c, cl = med(i, "combined_ratio"), med(i, "claims_ratio")
    if c and cl:
        out.append(f"Median combined ratio {_pc(c['median'])} and claims ratio {_pc(cl['median'])} ({c['n']} general insurers). How much of the "
                   "underwriting result does investment income make up? The filings give the ratios, not the split.")
    u = fams.get("us") or {}
    r, dg = med(u, "rpo_growth"), med(u, "deferred_growth")
    if r and dg:
        out.append(f"Median RPO growth {_chg(r['median'])} ({r['n']} companies) against median deferred revenue growth {_chg(dg['median'])} ({dg['n']}). "
                   "How much of the contracted revenue is billed ahead? The figures show both rates, not the contracts' terms.")
    return out


def _state_cell(r: dict, k: str, state: str | None, fmt) -> str:
    """A company's cell for one figure in its state (metric_registry): the value, "–" unavailable, "n/a" not applicable, "n.c." not comparable."""
    from .intel.metric_registry import MARK, VALUE
    if state is None:
        return fmt(r[k]) if r.get(k) is not None else "–"
    return fmt(r[k]) if state == VALUE else MARK[state]


def _amount(v, unit) -> str:
    """A base amount as filed, in its unit: "₹1,234 cr", "USD 5,600 million"."""
    if v is None:
        return "–"
    if unit == "₹ crore":
        return f"₹{v:,.0f} cr"
    if str(unit or "").endswith(" million"):
        cur = unit.split()[0]
        return f"{'$' if cur == 'USD' else cur + ' '}{v:,.0f} m"
    return f"{v:,.0f}" + (f" {unit}" if unit else "")


def extreme_line(f: dict, limit: int = 4) -> str:
    """The unusual growth figures of a family, each with its base said as filed ("from ₹X cr to ₹Y cr"); no cause given (R27)."""
    from .intel.metric_registry import GROWTH_EXTREME
    from .intel.metric_registry import BY_ID
    xs = f.get("extreme") or []
    if not xs:
        return ""
    parts = [f"{x['name']}, {_low(BY_ID[x['key']].label)} {_chg(x['v'])}" + (f", from {_amount(x['base'][0], x.get('unit'))} to {_amount(x['base'][1], x.get('unit'))}"
                                                                           if x.get("base") else "") for x in xs[:limit]]
    more = f"; {len(xs) - limit} more in the table" if len(xs) > limit else ""
    return (f"Unusual growth (above {GROWTH_EXTREME:.0f}% either way, or from a small base), with its base: " + "; ".join(parts) + more
            + ". Kept out of the headline when it makes up a third of a figure's values.")


def order_family(v: dict) -> dict | None:
    """India defence and capital goods: the order book and order inflow, only where a company's own business update the app read states them
    (metric_registry.orders_from_business), with their periods; never a forecast from them. None when no company's update states one."""
    from .intel import metric_registry as R
    from .intel.theme_data import stat
    if v.get("region") != "IN":
        return None
    got = R.orders_from_business(v.get("business"))
    cos = {c["symbol"]: c for x in v.get("layers") or [] for c in x.get("companies") or [] if c.get("status") != "unverified"}
    rows, tagsets = [], []
    for sym, figs in got.items():
        c = cos.get(sym)
        if c is None:
            continue
        t = R.tags("IN", c, ((next((x for x in v["layers"] if any(y["symbol"] == sym for y in x.get("companies") or [])), {}).get("model") or {}).get("family")))
        if not any(R.applies(k, "IN", t) for k in figs):
            continue
        rows.append({"symbol": sym, "name": c.get("name") or sym, "as_of": next(iter(figs.values()))["period"], **{k: x["v"] for k, x in figs.items()},
                     "src": {k: {"period": x["period"], "source": x["source"]} for k, x in figs.items()}})
        tagsets.append(t)
    keys = [k for k in ("order_book", "order_inflow") if any(r.get(k) is not None for r in rows)]
    if not rows or not keys:
        return None
    sts = {k: R.states(k, "IN", rows, tagsets) for k in keys}
    return {"keys": keys, "rows": rows, "n": len(rows), "of": len(rows), "states": sts, "headline": [],
            "medians": {k: R.coverage([r.get(k) for r in rows], sts[k], stat) for k in keys},
            "checked": "the business updates the companies file with the exchange, as the app read them",
            "not_filed": "a company whose update doesn't state its order book or inflow has none here; no figure is worked out from another"}


def sector_paged(v: dict) -> bool:
    """R48: whether the deck has a page of filed operating figures (_sector_slides draws one for each family with figures and rows)."""
    fams = dict(((v.get("sections") or {}).get("sector") or {}).get("families") or {})
    return bool(order_family(v)) or any(isinstance(f, dict) and f.get("keys") and f.get("rows") for f in fams.values())


def _sector_slides(slides: list, v: dict, amt, eyebrow: str) -> None:
    """A page for each family's filed operating figures (R23): every company's figures in their state (R27: value, "–", "n/a", "n.c.", one
    legend line), the median of each over the companies that have it with "N of M" the companies it applies to (none under MIN_BASE), insurers'
    medians by type, unusual growth with its base, and how each is worked out, where it is from and what the filings don't state."""
    from .intel.metric_registry import LEGEND
    from .intel.metric_registry import BY_ID
    from .intel.sector_metrics import TYPE_NAMES
    sec = (v.get("sections") or {}).get("sector") or {}
    fams = dict(sec.get("families") or {})
    orders = order_family(v)
    if orders:
        fams["orders"] = orders
    for fam, f in fams.items():
        keys = list(f.get("keys") or [])
        if not keys or not f.get("rows"):
            continue
        fmts = {k: sector_fmt(k, amt) for k in keys}
        sts = f.get("states") or {}
        order = sorted(range(len(f["rows"])), key=lambda i: (f["rows"][i].get("type") or "", f["rows"][i].get("name") or ""))
        typed = fam == "insurer" and len(f.get("types") or {}) > 1
        head = ["Company"] + (["Type"] if typed else []) + [BY_ID[k].label for k in keys] + ["Period"]
        widths = [2.6 if len(keys) < 8 else 2.3] + ([1.1] if typed else []) + [1.05 if len(keys) < 8 else 0.95] * len(keys) + [1.15 if len(keys) < 8 else 1.35]
        body = [[f["rows"][i]["name"]] + ([f["rows"][i].get("type", "").capitalize()] if typed else [])
                + [_state_cell(f["rows"][i], k, (sts.get(k) or [None] * len(f["rows"]))[i], fmts[k]) for k in keys] + [f["rows"][i].get("as_of") or "–"]
                for i in order]

        def med_row(label, g, gkeys):
            meds = g.get("medians") or {}
            # R29: "N of M" in every median cell, M the companies the figure applies to (those still being read included)
            cells = [_medn_of(meds.get(k), (meds.get(k) or {}).get("of") or g.get("n"), fmts[k]) if k in gkeys and meds.get(k) else "" for k in keys]
            return [label] + ([""] if typed else []) + cells + [""]
        if typed:
            tail = [med_row(f"Median, {TYPE_NAMES[t][1]} (companies)", g, g.get("keys") or ()) for t, g in f["types"].items()]
        elif fam == "orders":       # each company's own stated amount: no median across companies of different sizes
            tail = []
        else:
            tail = [med_row("Median (companies)", f, keys)]
        head, every, widths, _ = drop_empty(head, body + tail, widths)
        body, tail = every[:len(body)], every[len(body):]
        one, many = SECTOR_WHO[fam]
        lead = sector_lines({"sector": {"families": {fam: f}}}, waiting=False)
        if fam == "orders":
            msg = f"{_n(f['n'], one, many)} whose own business update states an order figure, each with its period"
        else:
            # R29: still being read is said with the count read so far; companies read with none filed are said apart
            late = f.get("pending") or 0
            none_filed = max(0, f.get("of", 0) - f["n"] - late)
            msg = ((lead[0].rstrip(".") if len(lead) == 1 else f"{_n(f['n'], one, many)} with filed figures, each type's medians apart") if lead
                   else f"{_n(f['n'], one, many)} with filed figures") + (
                f"; filed figures read for {f.get('read', f['of'] - late)} of {f['of']} so far, {late} still being read" if late else "") + (
                f"; {none_filed} more without" if none_filed else "")
        shown = {c for r in body for c in r[1:] if isinstance(c, str)}
        legend = LEGEND if shown & {"n/a", "n.c."} else ""
        ext = extreme_line(f)
        note = (f"From {f['checked']}, each company's latest; the period is the latest it covers; how each figure is worked out: ⟦{NOTES_TITLE}⟧."
                + (f" Not shown: {f['not_filed']}." if f.get("not_filed") else "")
                + ((" Medians: the companies that have the figure, the count in brackets when fewer than those it applies to"
                    + (", each type of insurer on its own" if typed else "") + f"; none under {MIN_BASE}.") if tail else "")
                + (f" {legend}" if legend else "") + (f" {ext}" if ext else ""))
        nh = note_h(note)
        room = BOT - TOP - nh - 0.15
        compact = len(body) > 10    # a long family: one line a company, so a page holds them (no half-empty second page)
        pages = table_pages(head, body + tail, widths, CW, room, most=26, compact=compact)
        if len(pages) > 1:          # the median rows stay together at the foot of the last page, every other page full
            fits = lambda rows_: sum(table_layout({"head": head, "rows": rows_, "widths": widths, "tight": True, "compact": compact}, CW, 99)["heights"]) <= room  # noqa: E731
            pages = table_pages(head, body, widths, CW, room, most=26, compact=compact)
            last = pages[-1]
            if fits(last + tail):
                pages[-1] = last + tail
            else:                   # the fewest rows carried over with the medians, so the page before stays full
                m_ = next((m_ for m_ in range(1, len(last)) if fits(last[-m_:] + tail)), max(1, len(last) - 1))
                pages[-1:] = [last[:-m_], last[-m_:] + tail]
        for k_, chunk in enumerate(pages):
            s = Slide(f"{SECTOR_TITLE}: {SECTOR_PAGE[fam]}" + (f" ({k_ + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=eyebrow)
            th = min(room, sum(table_layout({"head": head, "rows": chunk, "widths": widths, "tight": True, "compact": compact}, CW, 99)["heights"]))
            s.add("table", (M, TOP, CW, th), head=head, rows=chunk, widths=widths, tight=True, compact=compact,
                  strong=[i for i, r in enumerate(chunk) if any(r is t for t in tail)])
            s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)


CLAIMS_EACH = 4                 # tailwinds and risks shown at most, each (R21: the same number of each)
REST_H = 0.32           # the room the first page of a long table keeps for the line that says where the rest of it is
# long tables whose first page stays in the core and the rest goes to the appendix (R17-008: the core ran 51 pages)
SPILL = ("Operating figures", "Latest on this theme")
APPENDIX_TABLES = ("The latest quarter against a year earlier", "Ownership", "Events", "Management report cards")       # wholly in the appendix
SPILL_KEEP = {"Operating figures": 2}          # pages a table keeps in the core (the owner: operating figures for all layers on one or two pages)


def _rest_line(s, base: str, rest: int, y: float) -> None:
    """The line under the first page of a long table: how many more rows and the appendix page they are on."""
    s.add("text", (M, y, CW, REST_H - 0.04), paras=[f"The rest of this table, {_n(rest, 'more row')}: appendix, ⟦{base}, continued⟧."],
          size=BODY_MIN, floor=BODY_MIN, color=MUTED)


def _spill(slides: list) -> None:
    """Pages 2 onwards of the SPILL tables move to the start of the appendix, titled "<table>, continued (k of n)"; the first page keeps the
    table's own title and says where the rest is (_rest_line). The core keeps each table's summary line and its top rows."""
    at = next((i for i, s in enumerate(slides) if s.kind == "section" and s.title == "Appendix"), None)
    if at is None:
        return
    moved = []
    for base in SPILL:
        group = [s for s in slides if re.fullmatch(re.escape(base) + r" \(\d+ of \d+\)", s.title)]
        keep = SPILL_KEEP.get(base, 1)
        if len(group) <= keep:
            continue
        for k, s in enumerate(group[:keep], 1):
            s.title = base + (f" ({k} of {keep})" if keep > 1 else "")
        rest = group[keep:]
        for k, s in enumerate(rest, 1):
            s.title = f"{base}, continued" + (f" ({k} of {len(rest)})" if len(rest) > 1 else "")
        moved += rest
        last = group[keep - 1]
        if not any(p_.startswith("The rest of this table") for b in last.blocks for p_ in b.get("paras") or []):
            last.subtitle = f"{last.subtitle}; the rest: appendix, ⟦{base}, continued⟧"      # where the rest is, on the core's last page of it
    if not moved:
        return
    keep = [s for s in slides if s not in moved]
    at = next(i for i, s in enumerate(keep) if s.kind == "section" and s.title == "Appendix")
    slides[:] = keep[:at + 1] + moved + keep[at + 1:]


def _group_keys(chunk: list, tint: dict) -> dict:
    """`colors` keys count every row of a table, heading rows too: a tint keyed by plain rows, moved onto the full count."""
    out, k = {}, 0
    for j, r in enumerate(chunk):
        if isinstance(r, dict):
            continue
        for (pj, c), col in tint.items():
            if pj == k:
                out[(j, c)] = col
        k += 1
    return out


def _bizval(v, unit) -> str:
    """2,36,013 units, ₹33,275 billion, 34.2%: the unit as filed, Indian digit grouping (lib/biz.ts bizValue)."""
    if v is None:
        return "–"
    whole, _, frac = f"{abs(v):.2f}".partition(".")
    text = _cr(float(whole)) + ("." + frac.rstrip("0") if frac.rstrip("0") else "")
    text = ("−" if v < 0 else "") + text
    u = (unit or "").strip()
    if u == "%":
        return f"{text}%"
    if u.startswith("₹"):
        return f"₹{text} {u[1:].strip()}".strip()
    return f"{text} {u}".strip()


def _bizchg(c, unit) -> str:
    if c is None:
        return "–"
    s = "+" if c > 0 else "−" if c < 0 else ""
    return f"{s}{abs(c):.2f} pts" if "%" in (unit or "") else f"{s}{abs(c):.1f}%"


def _period(p: str, span: str = "month") -> str:
    try:
        y, m = (int(x) for x in str(p).split("-")[:2])
    except ValueError:
        return str(p)
    if span == "quarter" and m in (6, 9, 12, 3):
        return f"Q{ {6: 1, 9: 2, 12: 3, 3: 4}[m]} FY{(y + 1 if m >= 4 else y) % 100:02d}"
    return f"{date(2000, m, 1).strftime('%b')} {y}"


STALE_MONTHS = {"month": 3, "quarter": 6}       # an operating figure for a period this many months before the deck's day is marked old


def biz_stale(r: dict, today: date) -> bool:
    """Whether an operating figure's period ended long before the deck was made (Bharat Forge's Q1 FY26 in a November 2026 deck)."""
    try:
        y, m = (int(x) for x in str(r.get("period")).split("-")[:2])
    except ValueError:
        return False
    return (today.year - y) * 12 + today.month - m > STALE_MONTHS.get(r.get("span") or "month", 3)


def _biz_slides(slides: list, title: str, rows: list, eyebrow: str, today: date | None = None) -> None:
    """The operating figures companies file between results (the page's business-update tables), each with its filing's day (linked). A figure
    for an old period is marked "(old)" in red; a figure held for checking (theme_data.hold_suspect) shows "held" for what it was compared with,
    and for both comparisons when the latest figure itself is in doubt (R18). A row {"group": name} heads a layer's figures."""
    today = today or datetime.now(IST).date()
    head = ["Company", "Period", "Latest", "Previous", "Year ago", "On previous", "On the year", "Filed"]
    widths = [3.2, 1.35, 1.6, 1.5, 1.5, 1.15, 1.15, 1.3]
    out, held = [], False
    for r in rows:
        if isinstance(r, dict) and "group" in r:
            out.append(r)
            continue
        old = biz_stale(r, today)
        hold = r.get("held") or ""
        held = held or bool(hold)

        def cmp_(k, r=r, hold=hold):
            if r.get(k) is None and (r.get("held_latest") or ("previous" in hold if k == "prev" else "year" in hold)):
                return "held"
            return _bizval(r.get(k), r.get("unit"))
        out.append([f"{r['name']}: {r.get('metric') or ''}".rstrip(": "), _period(r.get("period"), r.get("span") or "month") + (" (old)" if old else ""),
                    _bizval(r.get("value"), r.get("unit")), cmp_("prev"), cmp_("year_ago"),
                    _bizchg(r.get("change_prev"), r.get("unit")), _bizchg(r.get("change_year"), r.get("unit")),
                    {"text": _day(r.get("filed")), "url": r["url"]} if r.get("url") else _day(r.get("filed"))])
    note = ("Monthly or quarterly figures the companies filed with the exchange between results, as filed; changes are plain changes, not a view. "
            "(old): a period that ended months before this deck." + (" held: the compared figure is held for checking (the same figure as another "
                                                                     "company's, or a move too large to take as filed, when neither comparison is shown)." if held else ""))
    nh = note_h(note)
    pages = table_pages(head, out, widths, CW, BOT - TOP - nh - 0.1)
    for k, chunk in enumerate(pages):
        s = Slide(title + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                  "Operating figures filed with the exchange between results, as filed", eyebrow=eyebrow)
        s.add("table", (M, TOP, CW, BOT - TOP - nh - 0.1), head=head, rows=chunk, widths=widths,
              colors={(j, 1): DOWN for j, r in enumerate(chunk) if not isinstance(r, dict) and str(r[1]).endswith("(old)")})
        s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)


def size_mark(x: dict) -> str:
    """gl52 (R52): a largest company's mark when it runs other businesses too: the theme's segment counted, or its whole market value."""
    if x.get("segment"):
        return f" (its {x['segment']} segment, {x['segment_pct']:.1f}% of revenue)"
    return " (whole company)" if x.get("whole") else ""


def size_note(size: dict) -> str:
    """gl52: how a company that runs other businesses too is counted in the theme's market value."""
    parts = []
    if size.get("segment_counted"):
        parts.append("a company that runs other businesses too counts the share of its market value of its segment that is the theme's, by that "
                     "segment's share of its revenue")
    if size.get("whole_counted"):
        parts.append(f"{_n(size['whole_counted'], 'company that runs', 'companies that run')} other businesses too with no such segment stored "
                     "count their whole market value, marked “(whole company)”")
    return (" " + "; ".join(parts)[:1].upper() + "; ".join(parts)[1:] + ".") if parts else ""


def _numbers(slides: list, v: dict, sec: dict, cap, eb, left_out: list, name_of) -> None:
    """The theme in numbers, a slide for each of the page's cards (NumbersCards): a chart where figures compare, the table beside it."""
    E = lambda: eb("The theme in numbers")  # noqa: E731
    size = sec.get("size") or {}
    big = size.get("biggest") or []
    if big:
        nv = size.get("with_value", 0)
        msg = (f"The three largest make up {_pc(size['top3_share'])} of the theme's market value of {cap(size.get('total_cap'))} ({_n(nv, 'company', 'companies')} with figures and a market value)"
               if size.get("top3_share") is not None else f"The theme's {_n(nv, 'company', 'companies')} with figures and a market value are worth {cap(size.get('total_cap'))} together")
        s = Slide("Size and shape", msg, eyebrow=E())
        rows = [[name_of(x["symbol"], x["name"]) + size_mark(x), cap(x.get("cap")), _pc(x.get("share"))] for x in big]
        if size.get("top3_share") is not None:          # the headline's share is a row of the table (R25)
            rows.append(["The three largest together", cap(sum(x.get("cap") or 0 for x in big[:3])), _pc(size["top3_share"])])
        rows.append([f"All {size.get('with_value', 0):,} companies with figures and a market value", cap(size.get("total_cap")), "100.0%"])
        lw = 6.2
        s.add("table", (M, TOP, lw, BOT - TOP - 0.3), head=["Company", "Market value", "Share of the theme"], rows=rows, widths=[3.2, 1.5, 1.5], strong=list(range(len(big), len(rows))))
        top = big[:10]
        s.add("hbars", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP - 0.3), title="Share of the theme's market value", cats=[x["name"] for x in top],
              vals=[x.get("share") or 0 for x in top], fmt="pct")
        s.add("text", (M, BOT - 0.25, CW, 0.25), paras=["Market value: price times shares in issue, as each company's page shows it." + size_note(size)],
              size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

    gm = sec.get("growth") or {}
    agg, gmed = gm.get("aggregate") or {}, gm.get("median") or {}
    mk = sec.get("market") or {}
    meds = sec.get("medians") or {}
    if agg or gmed or meds:
        grow = [[label, _chg((agg.get(f"{k}_1y") or {}).get("value")), _chg((agg.get(f"{k}_3y") or {}).get("value")),
                 _chg((gmed.get(f"{k}_1y") or {}).get("median")), _chg((gmed.get(f"{k}_3y") or {}).get("median"))] for k, label in (("revenue", "Revenue"), ("profit", "Net profit"))]
        whole = mostly_whole((v.get("checks") or {}).get("whole_points"), (v.get("checks") or {}).get("with_ebitda"))
        vs = [["EBITDA margin", _pcw((meds.get("ebitda") or {}).get("median"), bool(whole)), str((meds.get("ebitda") or {}).get("n", "–")), _pcw((mk.get("opm") or {}).get("median"), bool(whole))],
              ["Net margin", _med(meds.get("net")), str((meds.get("net") or {}).get("n", "–")), _med(mk.get("net_margin"))],
              ["ROCE", _med(meds.get("roce")), str((meds.get("roce") or {}).get("n", "–")), _med(mk.get("roce"))],
              ["ROE", _med(meds.get("roe")) if (v.get("checks") or {}).get("lenders") else "–", str((meds.get("roe") or {}).get("n", "–")), "–"],
              ["Revenue growth, 3 years a year", _med(gmed.get("revenue_3y"), _chg), str((gmed.get("revenue_3y") or {}).get("n", "–")), _med(mk.get("sales_cagr_3y"), _chg)]]
        vs = [r_ for r_ in vs if r_[1] != "–"]          # a median no company has (lenders' EBITDA margin) is no row (R18)
        vs += aggregate_margin_rows(sec.get("margins") or {})
        vh_, vs, vw_, _ = drop_empty(["Median", "Theme", "Companies", "All listed"], vs, [2.8, 1.3, 1.3, 1.3], keep=(0, 1))
        r1 = (agg.get("revenue_1y") or {}).get("value")
        msg = (f"Revenue together grew {_chg(r1)} in the latest year ({_n((agg.get('revenue_1y') or {}).get('n') or 0, 'company', 'companies')})" if r1 is not None
               else "Growth and margins of the theme's companies")
        if meds.get("ebitda") and mk.get("opm"):
            msg += (f"; the median company's EBITDA margin is {_pcw(meds['ebitda']['median'], bool(whole))} ({meds['ebitda']['n']}) against {_pcw(mk['opm']['median'], bool(whole))} "
                    "for all listed companies")
        s = Slide("Growth and profitability", msg, eyebrow=E())
        lw = 7.0
        gh_ = ["Measure", "Together, 1 year", "Together, 3 years a year", "Median company, 1 year", "Median company, 3 years a year"]
        gw = [1.5, 1.3, 1.5, 1.4, 1.6]
        g_h = table_height(gh_, grow, gw, lw)
        s.add("text", (M, TOP, lw, 0.3), paras=["Revenue and profit growth"], size=12, floor=12, bold=True, color=INK2)
        s.add("table", (M, TOP + 0.36, lw, g_h), head=gh_, rows=grow, widths=gw, tight=True)
        y2 = TOP + 0.36 + g_h + 0.22
        s.add("text", (M, y2, lw, 0.3), paras=["Margins and returns: the theme against all listed companies"], size=12, floor=12, bold=True, color=INK2)
        note = ("Together: the companies' figures added up, for those that report both ends of the period. Median: the middle company's own rate. "
                "Companies that run other businesses too, and net margins not reconciled with their own filed figures, are left out.")
        if gmed.get("revenue_5y") or gmed.get("profit_5y"):
            note += f" Median company, 5 years a year: revenue {_med(gmed.get('revenue_5y'), _chg)}, profit {_med(gmed.get('profit_5y'), _chg)}."
        cats, th, al = [], [], []
        for label, a, bm in (("EBITDA margin", meds.get("ebitda"), mk.get("opm")), ("Net margin", meds.get("net"), mk.get("net_margin")),
                             ("ROCE", meds.get("roce"), mk.get("roce")), ("Revenue growth, 3y", gmed.get("revenue_3y"), mk.get("sales_cagr_3y"))):
            if a and bm:
                cats.append(label)
                th.append(a["median"])
                al.append(bm["median"])
        # R25: the note sits under the chart, so the margins table has room for the aggregate margin the findings state
        rw = CW - lw - 0.4
        nh = note_h(note, rw)
        s.add("table", (M, y2 + 0.36, lw, BOT - y2 - 0.36 - 0.1), head=vh_, rows=vs, widths=vw_)
        if cats:
            s.add("columns", (M + lw + 0.4, TOP, rw, BOT - TOP - nh - 0.15), title="Median company: the theme against all listed", cats=cats, fmt="pct",
                  series=[("Theme", th, BLUE), ("All listed", al, LINE2)])
        s.add("text", (M + lw + 0.4, BOT - nh, rw, nh) if cats else (M + lw + 0.4, TOP + 0.36, rw, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

    # margins over time: the findings and "What moved the aggregate margin" carry the change, so no page of its own (R19)
    val = sec.get("valuation") or {}
    if val.get("pe") or val.get("pb") or val.get("ev_ebitda"):
        peers = dated_peers(v)
        pp = peers.get("pe") or {}
        # who the P/E is of (R20): the profitable companies, with how many loss-makers have none and the profitable share
        pe_n, losses = (val.get("pe") or {}).get("n", 0), val.get("losses") or 0
        pop = val.get("n") or (pe_n + losses)
        pe_label = (f"P/E, the {pe_n} companies with one ({round(pe_n / pop * 100)}% of {pop}; {_n(losses, 'loss-maker')} with none)"
                    if losses and pe_n else "P/E (last four quarters)")
        rows = [[pe_label, _medn(val.get("pe"), None, _times), _span(val.get("pe"), _times), str((val.get("pe") or {}).get("n", "–")),
                 "–", _med(val.get("market_pe"), _times)]]
        if pp.get("n"):     # the same basis as the headline: the companies with comparable peers, against their peers' median (R17-010)
            rows.append([f"P/E, companies with comparable peers {peer_set_words(pp)}", _times(pp.get("theme")), f"{premium_words(pp['premium'])} peers"
                         if pp.get("premium") is not None else "", str(pp.get("n", "–")), _times(pp.get("peers")), "–"])
        if (pp.get("none") or 0) and pe_n:     # R27: counted as such, never set against the whole market
            rows.append(["P/E, companies with no comparable peer set", "not comparable", "", str(pp["none"]), "not comparable", "–"])
        rows += [r_ for r_ in (
                ["P/B", _med(val.get("pb"), _times), _span(val.get("pb"), _times), str((val.get("pb") or {}).get("n", "–")), "–", _med(val.get("market_pb"), _times)],
                ["EV/EBITDA (latest year)", _med(val.get("ev_ebitda"), _times), _span(val.get("ev_ebitda"), _times), str((val.get("ev_ebitda") or {}).get("n", "–")), "n/a", "n/a"])
                 if r_[1] != "–"]           # a measure no company has (EV/EBITDA for lenders) is no row (R18)
        for key, label, f in (("sales_3y", "Revenue growth, 3 years a year", _chg), ("roce", "ROCE", _pc)):
            if (peers.get(key) or {}).get("n"):
                rows.append([f"{label}, companies with comparable peers {peer_set_words(peers[key])}", f(peers[key]["theme"]), "", str(peers[key]["n"]),
                             f(peers[key]["peers"]), "–"])
        from .intel.theme_data import relative_ok
        descriptive = not relative_ok(val)
        if descriptive:
            # R29 (P1): comparable peers for under half of the companies with a P/E: the theme's own medians and spread, by layer and over
            # time, each with its count; no column or sentence sets them against peers or the whole market
            rows = [r_ for r_ in (
                [pe_label, _medn(val.get("pe"), None, _times), _span(val.get("pe"), _times), str((val.get("pe") or {}).get("n", "–"))],
                ["P/B", _med(val.get("pb"), _times), _span(val.get("pb"), _times), str((val.get("pb") or {}).get("n", "–"))],
                ["EV/EBITDA (latest year)", _med(val.get("ev_ebitda"), _times), _span(val.get("ev_ebitda"), _times), str((val.get("ev_ebitda") or {}).get("n", "–"))])
                if r_[1] != "–"]
        if descriptive:
            msg = descriptive_line(val)
        elif pp.get("premium") is not None:
            msg = pe_peer_line(pp)
        elif val.get("pe") and val.get("market_pe"):
            msg = f"The theme's median P/E is {_times(val['pe']['median'])} against {_times(val['market_pe']['median'])} for all {val.get('market_n', 0):,} listed companies with one"
        else:
            msg = "Price against earnings, book value and EBITDA, the theme against companies of similar market value"
        if losses and pe_n:
            msg += f"; P/E of {pe_n} of the {pop} companies, {_n(losses, 'loss-maker')} with none"
        s = Slide("Valuation", msg, eyebrow=E())
        hist = val.get("history") or []
        lw = 7.0 if len(hist) >= MIN_POINTS else CW         # LIVE6-008: no "weekly" line through 2 points; the table keeps the page's width
        # R27 (P2): how each is worked out, and who the peers are, live on the notes page; this page says only what its figures are of
        notes = []
        if val.get("losses"):
            notes.append(f"A loss-maker has no P/E: {_n(val['losses'], 'company', 'companies')} left out of the P/E median.")
        if val.get("ev_missing"):
            notes.append(f"EV/EBITDA is n/a for {_n(val['ev_missing'], 'company', 'companies')} where debt, cash or EBITDA isn't stored; the market's debt and "
                         "cash aren't kept, so it has no comparison.")
        if len(hist) < MIN_POINTS:
            notes.append("The theme's own P/E history builds forward from its page: it keeps the median once a week"
                         + (f" ({_n(len(hist), 'week')} so far; a line is drawn from {MIN_POINTS})." if hist else "."))
        if descriptive:
            notes.append(peer_cover_words(val) + " Each figure is the theme's own: no peer or market comparison is made.")
        elif peer_moved_line(pp):          # R35: the stored run before this one, when the peers' median is more than 5% away from it
            notes.insert(0, peer_moved_line(pp))
        notes.append(f"How each is worked out, and who the comparable peers are: {NOTES_POINTER}.")
        if descriptive:
            vhead, rows, vw, _ = drop_empty(["Measure", "Theme median", "Range", "Companies"], rows, [2.6, 1.3, 1.8, 1.2], keep=(0, 1))
        else:
            vhead, rows, vw, _ = drop_empty(["Measure", "Theme median", "Range", "Companies", "Comparable peers", "All listed"], rows,
                                            [2.3, 1.2, 1.7, 1.1, 1.4, 1.1], keep=(0, 1))
        vh = table_height(vhead, rows, vw, lw)
        s.add("table", (M, TOP, lw, vh), head=vhead, rows=rows, widths=vw, tight=True)
        y_ = TOP + vh + 0.25
        lay = layer_valuation_rows(val) if descriptive else None
        if lay:
            lh_, lr_, lwd, _ = drop_empty(*lay, keep=(0,))
            lt = table_height(lh_, lr_, lwd, lw)
            if BOT - y_ - lt - 0.25 >= 1.0:          # the notes keep room for their lines
                s.add("table", (M, y_, lw, lt), head=lh_, rows=lr_, widths=lwd, tight=True)
                y_ += lt + 0.25
        s.add("cards", (M, y_, lw, BOT - y_), cols=1, fill=True, size=12, items=[{"title": "What the figures are of", "lines": notes}])
        if len(hist) >= MIN_POINTS:
            h = hist[-26:]
            s.add("lines", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP), title=f"The theme's median P/E, weekly ({_day(h[0]['d'])} to {_day(h[-1]['d'])})",
                  cats=[_day(x["d"])[:6] for x in h], series=[("Median P/E", [x["pe"] for x in h], BLUE)], fmt="x", labels=len(h) <= 8)
        slides.append(s)

    # the latest quarter against a year earlier: the summary only, the median and how many rose or fell, with each company's change in a chart
    # (R19: no per-company table; each company's figures are in the appendix)
    qt = sec.get("quarter") or {}
    qc = qt.get("companies") or []
    if qc:
        bars = [x for x in qc if x.get("sales") is not None]
        later = qt.get("earlier") or []
        # d1: a median of fewer than MIN_BASE companies is never said (the tile shows "– (2)")
        med_q = (qt.get("sales") or {}) if ((qt.get("sales") or {}).get("n") or 0) >= MIN_BASE else {}
        msg = (f"In the quarter to {qt.get('quarter') or 'the latest'}, {qt.get('sales_up', 0)} of {len(bars)} companies reported higher revenue than a year "
               "before" + (f"; the median change is {_chg(med_q.get('median'))}" if med_q.get("median") is not None else ""))
        s = Slide("The latest quarter against a year earlier", msg, eyebrow=E())
        sn = (qt.get("sales") or {}).get("n") or (qt.get("sales_up", 0) + qt.get("sales_down", 0))
        pn = (qt.get("profit") or {}).get("n") or (qt.get("profit_up", 0) + qt.get("profit_down", 0))
        tiles = [("Quarter", qt.get("quarter") or "–", f"{_n(len(qc), 'company', 'companies')} reporting it"),
                 ("Median revenue change", _medn(qt.get("sales"), None, _chg), f"{qt.get('sales_up', 0)} up, {qt.get('sales_down', 0)} down, of {sn}"),
                 ("Median net profit change", _medn(qt.get("profit"), None, _chg), f"{qt.get('profit_up', 0)} up, {qt.get('profit_down', 0)} down, of {pn}")]
        lw = 6.4 if len(bars) >= 2 else CW
        s.add("stats", (M, TOP, lw, 1.5), items=tiles)
        lines = [f"Each company against its own quarter a year before; a median of the {_n(len(qc), 'company', 'companies')} reporting {qt.get('quarter') or 'it'}."]
        if later:
            late = [x for x in later if x.get("filed_unread")]
            lines.append(f"{_n(len(later), 'company', 'companies')} still on an earlier quarter, left out of the median: {names5(later)}.")
            if late:
                lines.append(f"Newer results filed but not yet in the figures: {names5(late)}.")
        s.add("cards", (M, TOP + 1.75, lw, BOT - TOP - 1.75), cols=1, fill=True, size=13, items=[{"title": "What the median is of", "lines": lines}])
        if len(bars) >= 2:
            srt = sorted(bars, key=lambda x: -x["sales"])[:14]
            s.add("hbars", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP), title="Revenue against the same quarter a year before" + (", the 14 largest moves" if len(bars) > 14 else ""),
                  cats=[x["name"] for x in srt], vals=[x["sales"] for x in srt], fmt="chg", colors=[UP if x["sales"] >= 0 else DOWN for x in srt])
        slides.append(s)
    else:
        left_out.append(("none", "a latest quarter against a year before"))

    bal = sec.get("balance") or {}
    lend_ = is_lender_set(sec.get("leaders") or [])
    # only when it shows something (R19): a quarter or more of the companies borrowing above their equity, or two or more covering their interest
    # less than twice
    finding = bool(bal.get("with_debt_equity")) and bal.get("above_1", 0) * 4 >= bal["with_debt_equity"] or bal.get("cover_under_2", 0) >= 2
    if not lend_ and finding and (bal.get("debt_equity") or bal.get("interest_cover") or bal.get("cfo_to_profit")):
        de, ic, cf = bal.get("debt_equity"), bal.get("interest_cover"), bal.get("cfo_to_profit")
        def tile(label, st, f, n):                # a figure no company has is said in words, never "0 companies"
            return (label, _med(st, f), f"Range {_span(st, f)} · {_n(n, 'company', 'companies')}" if st and n else "No company has the figures it needs")
        tiles = [tile("Debt to equity, median", de, lambda x: _times(x, 2), bal.get("with_debt_equity") or 0),
                 tile("Interest cover, median", ic, _times, (ic or {}).get("n") or 0),
                 tile("Cash from operations over net profit, median", cf, lambda x: _times(x, 2), bal.get("cfo_n") or 0)]
        tiles = [t_ for t_ in tiles if t_[1] != "–"] or tiles          # a figure no company has is no tile (R18)
        said = []
        if bal.get("with_debt_equity"):
            said.append(f"{bal.get('above_1', 0)} of {bal['with_debt_equity']} companies have borrowings above their equity.")
        if ic:
            said.append(f"{bal.get('cover_under_2', 0)} of {ic['n']} cover their interest less than twice.")
        s = Slide("Balance sheet and cash", " ".join(said) or "Borrowings, interest cover and cash from operations of the theme's companies", eyebrow=E())
        s.add("stats", (M, TOP, CW, 2.1), items=tiles)
        s.add("cards", (M, TOP + 2.4, CW, BOT - TOP - 2.4), cols=1, fill=True, size=14, items=[{"title": "How to read these", "lines": said + [
            "Debt to equity: borrowings over shareholders' equity (not for lenders).",
            "Interest cover: profit before interest and tax over interest. A company with no interest cost has no interest cover.",
            "Cash from operations over profit: the latest year's cash from operations as a multiple of its net profit."]}])
        slides.append(s)

    pr = sec.get("price") or {}
    prices = v.get("prices") or {}
    # d1 (the outside review of the live R41 decks: "Stage 2 / Supertrend" unexplained): each row says what it measures in plain words
    breadth = [(lbl, pr.get(k) or {}) for k, lbl in (("stage2", "Above a rising 150-day average"), ("supertrend_up", "Above their trend-following stop line"),
                                                       ("near_high", "Within 5% of the 52-week high"), ("near_low", "Within 10% of the 52-week low"))]
    if prices.get("above200"):
        breadth.append(("Above the 200-day average", prices["above200"]))
    breadth = [(lbl, x) for lbl, x in breadth if x.get("n")]
    ret = prices.get("returns") or {}
    # only when it shows something (R19): the theme 5 points or more above or below its index over a year, or 70% or more (30% or less) of its
    # companies in Stage 2
    y1 = ret.get("1Y") or {}
    st_ = pr.get("stage2") or {}
    finding = (y1.get("theme") is not None and y1.get("bench") is not None and abs(y1["theme"] - y1["bench"]) >= 5) or \
        (bool(st_.get("n")) and st_.get("n", 0) >= 4 and (st_.get("share") or 0) >= 70 or (st_.get("n") or 0) >= 4 and (st_.get("share") if st_.get("share") is not None else 50) <= 30)
    if finding and (breadth or ret):
        st2 = pr.get("stage2") or {}
        nh = pr.get("near_high") or {}
        msg = (f"{st2.get('count', 0)} of {st2.get('n', 0)} companies trade above a rising 150-day average; {nh.get('count', 0)} are within 5% of their 52-week high"
               if st2.get("n") else "Price change and breadth inside the theme")
        s = Slide("Price", msg, eyebrow=E())
        if ret:
            bench = prices.get("benchmark") or "Index"
            rows = [[lbl, _chg(((prices.get("median") or {}).get(k) or {}).get("median")), _chg((ret.get(k) or {}).get("theme")), _chg((ret.get(k) or {}).get("bench")),
                     str(((prices.get("median") or {}).get(k) or {}).get("n", "–"))] for k, lbl in (("1M", "1 month"), ("3M", "3 months"), ("1Y", "1 year"), ("3Y", "3 years"))]
            lw = 6.6
            # LIVE6-002: calendar periods to one last close, said in the table's head
            over = f"Over, to {_day(prices['returns_to'])}" if prices.get("returns_to") else "Over"
            s.add("table", (M, TOP, lw, 2.3), head=[over, "Median company", "Average company", bench, "Companies"], rows=rows, widths=[1.2, 1.4, 1.6, 1.3, 1.1])
            if breadth:
                s.add("table", (M, TOP + 2.55, lw, BOT - TOP - 2.55), head=["Companies that are", "Count", "Share"],
                      rows=[[lbl, f"{x['count']} of {x['n']}", f"{x['share']}%" if x.get("share") is not None else "–"] for lbl, x in breadth], widths=[3.6, 1.3, 1.0])
            line = prices.get("line")
            if line:
                s.add("lines", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP), title=f"The theme against {bench}, weekly, rebased to 100",
                      cats=[_day(w)[3:] for w in line["weeks"]], fmt="num1",        # "Nov 2026": the axis says the year (LIVE6-002)
                      series=[("Theme", line["theme"], BLUE), (bench, line["bench"], MUTED), ("Relative strength", line["rs"], ORANGE, True)])
        else:
            lw = 6.6
            s.add("table", (M, TOP, lw, BOT - TOP - 0.5), head=["Companies that are", "Count", "Share"],
                  rows=[[lbl, f"{x['count']} of {x['n']}", f"{x['share']}%" if x.get("share") is not None else "–"] for lbl, x in breadth], widths=[3.6, 1.3, 1.0])
            s.add("hbars", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP - 0.5), title="Share of the theme's companies", cats=[lbl for lbl, _ in breadth],
                  vals=[x.get("share") or 0 for _, x in breadth], fmt="pct0")
            s.add("text", (M, BOT - 0.36, CW, 0.36), paras=["Price changes against the index, from daily closes, are on the theme's page."],
                  size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

    # ownership, events and management report cards are per-company lists: on the theme's page, and their dated facts in "Dated company updates" (R19; m2: its name)


def build_theme(v: dict, pdf: bool = False) -> bytes:
    """A theme's deck, PowerPoint or (`pdf`) the same slides as a PDF."""
    return build_theme_gated(v, pdf)[0]


def build_theme_gated(v: dict, pdf: bool = False) -> tuple[bytes, dict]:
    """A theme's deck and its publication gate's result (R27: stored with the deck, shown in Admin -> Library)."""
    slides, footer = theme_plan(v)
    return _render(slides, footer, f"{v.get('sector') or 'Theme'}: theme deep dive", pdf=pdf), getattr(slides[0], "gate", None) or {}
