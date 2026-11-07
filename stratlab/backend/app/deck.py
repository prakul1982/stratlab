"""A company deck from the deep dive, and a theme's deck from the theme deep dive, as PowerPoint or PDF: every figure from the
view passed in, each slide saying where it came from. Built from what the page already has; no extra AI.

Each slide is described once (a title, a takeaway line and positioned blocks: text, stat tiles, cards, flowing notes, tables,
charts) and drawn twice: by python-pptx for PowerPoint and by reportlab for PDF, so the two files show the same slides. The
look is the app's own (DECK, 5 Nov: "this is shite can you make it better; all the decks we are giving are not so good
looking"): the paper and ink colours of frontend/src/styles.css, its serif headings (Fraunces) over a sans body (IBM Plex
Sans), and the green and red candles of the StratLab mark (frontend/src/lib/brand.ts). Text is measured with the PDF fonts
(wider than PowerPoint's Calibri and Georgia), so what fits in the PDF fits in PowerPoint too; every text box is cut to its
box with an ellipsis, never left to overflow."""
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


def _width(text: str, size: float, bold: bool = False, head: bool = False) -> float:
    """Width in inches of one line of text (headings in the widest serif, so a fitted heading fits in either file)."""
    from reportlab.pdfbase import pdfmetrics
    return pdfmetrics.stringWidth(str(text), "Head" if head else _face(text, bold), size) / 72


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
        got = wrap(text, size, width, bold, head)[:n]
        last = got[-1]
        while last and _width(last + "…", size, bold, head) > width:
            last = last[:last.rfind(" ")] if " " in last else last[:-1]
        return " ".join(got[:-1] + [last.rstrip(",;:. ") + "…"])

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
    return cut[:end + 1] if end > limit * 0.4 else cut[:cut.rfind(" ")].rstrip(",;:") + "…"


def clip(text: str, size: float, width: float, lines: int, bold=False, head=False) -> str:
    """At most `lines` lines of text at this size and width, ending in an ellipsis when cut."""
    got = wrap(text, size, width, bold, head)
    if len(got) <= lines:
        return str(text)
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
    return ("-" if v < 0 and digits.strip("0,") else "") + digits      # a tiny loss rounds to 0, never "-0"


# a spreadsheet number format for Indian grouping: 1,23,45,678 from a crore, 1,23,456 from a lakh (DD-053)
INDIAN_FORMAT = "[>=10000000]##\\,##\\,##\\,##0;[>=100000]##\\,##\\,##0;##,##0"


def _plain(x, k: int, dp: int) -> str:
    """A figure divided by `k` to `dp` decimals with Western grouping; one that rounds to zero never prints as "-0"."""
    if x is None:
        return "–"
    text = f"{x / k:,.{dp}f}"
    return text.lstrip("-") if float(text.replace(",", "")) == 0 else text


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
    return "–" if v is None else f"{v:.{dp}f}x".replace("-", MINUS)


def _pts(v) -> str:
    """A change in points, the sign from the rounded figure: a change that rounds to zero is "0.0 pts", never "+0.0" or "−0.0"."""
    if v is None:
        return "–"
    text = f"{abs(v):.1f}"
    return f"{'' if float(text) == 0 else '+' if v > 0 else MINUS}{text} pts"


def _med(s, f=lambda v: f"{v:.1f}%") -> str:
    return f(s["median"]) if s else "–"


def _span(s, f=lambda v: f"{v:.1f}%") -> str:
    return "–" if not s else f(s["min"]) if s["min"] == s["max"] else f"{f(s['min'])} to {f(s['max'])}"


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
    return isinstance(s, str) and bool(re.match(r"^[+\-–−₹$]?\s?[\d.,]+", s.strip())) or s == "–"


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
    return items


def fit_chars(text: str, size: float, width: float) -> str:
    """One line no wider than `width`: characters dropped from the end, with an ellipsis."""
    if _width(text, size) <= width:
        return text
    while text and _width(text + "…", size) > width:
        text = text[:-1]
    return text + "…"


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


def table_layout(b: dict, w: float, h: float) -> dict:
    """Column widths, the font size (13 down to 11 pt, never smaller) and each row's height so the table fits its box; rows that still
    don't fit are left out (callers page their rows with table_pages, so none is). A row {"group": text} is a full-width heading row."""
    total = sum(b["widths"])
    widths = [w * x / total for x in b["widths"]]
    plain = [r for r in b["rows"] if not isinstance(r, dict)]
    numeric = b.get("numeric") or [all(_numeric(r[c]) or r[c] == "" for r in plain if not isinstance(r[c], dict)) for c in range(len(b["head"]))]
    strong = set(b.get("strong") or ())

    widths = _whole_words(b, widths, numeric)
    compact = bool(b.get("compact"))
    if compact:
        # a reference table (R20: the appendix ran 8 rows a page): every cell on one line at the smallest body size, cut with an ellipsis,
        # and rows only as tall as their line
        b = {**b, "rows": [r if isinstance(r, dict) else [({**v, "text": fit_chars(_cell_text(v), BODY_MIN, cw - 0.2)} if isinstance(v, dict)
                                                          else fit_chars(_cell_text(v), BODY_MIN, cw - 0.2)) for v, cw in zip(r, widths)] for r in b["rows"]]}
    pad, floor_h = (0.022, 0.22) if compact else (0.12, 0.32)

    def heights_at(size):
        line = size * 1.3 / 72
        hs = [max(len(wrap(hd, size, cw - 0.2, True)) for hd, cw in zip(b["head"], widths)) * line + pad + 0.02]
        for i, r in enumerate(b["rows"]):
            if isinstance(r, dict):
                hs.append(len(wrap(r["group"], size, w - 0.2, True)) * line + pad + 0.04)
            else:
                hs.append(max(len(wrap(_cell_text(v), size, cw - 0.2, i in strong)) for v, cw in zip(r, widths)) * line + pad)
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
class Canvas:
    """The slide frame and every block but tables and charts, drawn with rect, text, line and poly (each file implements those)."""

    # primitives: rect(x, y, w, h, fill, line=None, radius=0.08), text(...), line(x1, y1, x2, y2, color, width), poly(points, fill)

    def mark(self, x, y, h):
        bx, by, bw, bh = MARK_BOX
        k = h / bh
        for fill, pts in _mark_polys():
            self.poly([(x + (px - bx) * k, y + (py - by) * k) for px, py in pts], fill)

    def frame(self, sl: Slide, n: int, total: int, footer: str):
        dark = sl.kind in ("cover", "section")
        self.page(DARK if dark else PAPER)
        if sl.kind == "cover":
            size = fit([sl.title], CW - 1.0, 0.75, 42, 28, head=True)
            self.text(M, 1.72, CW - 1.0, 0.8, [clip(sl.title, size, CW - 1.0, 1, head=True)], size, color=ON_DARK, head=True, name="Title")
            self.text(M, 1.36, CW, 0.3, [(sl.subtitle or "").upper()], 12, color=GREEN_WICK, bold=True)
            self.mark(M, 0.5, 0.62)
            self.text(M + 0.38, 0.62, 3, 0.4, ["StratLab"], 19, color=ON_DARK, head=True)
            return
        if sl.kind == "section":
            self.text(M, 2.6, 5.7, 1.3, fit_paras([sl.title], 38, 5.7, 1.3, head=True), 38, color=ON_DARK, head=True, name="Title")
            self.text(M, 1.25, 3, 1.2, [sl.part], 66, color=GREEN_WICK, head=True)
            if sl.subtitle:
                size = fit([sl.subtitle], 5.5, 2.4, 17, 13)
                self.text(M, 4.05, 5.5, 2.4, [sl.subtitle], size, color=DARK_MUTED)
            self._contents(sl)
            self._footer(footer, n, total, dark=True)
            return
        size = fit([sl.title], CW - 0.6, 0.55, 28, 22, head=True)
        self.text(M, 0.5, CW - 0.6, 0.6, [clip(sl.title, size, CW - 0.6, 1, head=True)], size, color=INK, head=True, name="Title")
        if sl.subtitle:
            self.text(M, 1.08, CW, 0.56, fit_paras([sl.subtitle], 14, CW, 0.56), 14, color=INK2)
        if sl.eyebrow:
            self.text(M, 0.3, CW - 0.6, 0.22, [clip(sl.eyebrow.upper(), 10, CW - 0.6, 1, bold=True)], 10, color=MUTED, bold=True)
        self.mark(W_IN - M - 0.17, 0.32, 0.44)
        self._footer(footer, n, total, dark=False)

    def _footer(self, footer, n, total, dark):
        self.line(M, 7.0, W_IN - M, 7.0, DARK_LINE if dark else LINE2, 0.75)
        col = DARK_MUTED if dark else MUTED
        self.text(M, 7.08, 8.4, 0.24, [clip(f"StratLab · {footer}", 9.5, 8.4, 1)], 9.5, color=col)
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
            self.text(x, yy + (step - fs * 1.25 / 72) / 2, w - 0.7, fs * 1.3 / 72, [clip(title, fs, w - 0.7, 1)], fs, color=ON_DARK)
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
        self.text(x, y, w, h, fit_paras(b["paras"], size, w, h, b.get("bold", False), b.get("head", False)), size, color=b.get("color", INK),
                  bold=b.get("bold", False), head=b.get("head", False))

    def b_stats(self, b):
        x, y, w, h = b["box"]
        items, gap, dark = b["items"], 0.18, b.get("dark")
        cw = (w - gap * (len(items) - 1)) / len(items)
        for i, it in enumerate(items):
            label, value, note = it[0], str(it[1]), (it[2] if len(it) > 2 else None)
            cx = x + i * (cw + gap)
            self.rect(cx, y, cw, h, DARK2 if dark else CARD, line=DARK_LINE if dark else LINE)
            iw = cw - 0.36
            lab = clip(label, BODY_MIN, iw, 2)
            lh = len(wrap(lab, BODY_MIN, iw)) * _lh(BODY_MIN)
            self.text(cx + 0.18, y + 0.13, iw, lh, [lab], BODY_MIN, color=DARK_MUTED if dark else MUTED)
            nh = min(0.6, len(wrap(note, BODY_MIN, iw)) * _lh(BODY_MIN)) if note else 0
            vy = y + 0.13 + lh + 0.06
            vh = y + h - vy - nh - (0.14 if note else 0.08)
            vs = fit([value], iw, min(vh, 26 * 1.3 / 72), 26, 15, head=True)       # one line where a size from 26 down to 15 allows
            if len(wrap(value, vs, iw, head=True)) > 1:
                vs = fit([value], iw, vh, 26, 13, head=True)
            self.text(cx + 0.18, vy, iw, vh, fit_paras([value], vs, iw, vh, head=True), vs, color=it[3] if len(it) > 3 else (ON_DARK if dark else INK), head=True)
            if note:
                self.text(cx + 0.18, y + h - 0.12 - nh, iw, nh, fit_paras([note], BODY_MIN, iw, nh), BODY_MIN, color=DARK_MUTED if dark else MUTED)

    def b_stack(self, b):
        x, y, w, h = b["box"]
        step = h / len(b["items"])
        for i, (label, value) in enumerate(b["items"]):
            yy = y + i * step
            self.line(x, yy, x + w, yy, LINE2, 0.75)
            self.text(x, yy + 0.1, w, 0.3, [clip(label, 12, w, 1)], 12, color=MUTED)
            self.text(x, yy + 0.42, w, 0.6, [value], 28, color=DOWN if value[:1] in "-−" else INK, head=True)

    def b_cards(self, b):
        for it, (cx, cy, cw, ch) in zip(b["items"], card_boxes(b)):
            self.rect(cx, cy, cw, ch, CARD, line=LINE)
            iw, yy = cw - 0.5, cy + 0.22
            tw = iw - (1.3 if it.get("pill") else 0)
            title = clip(it["title"], 13, tw, 2, bold=True)
            self.text(cx + 0.25, yy, tw, 0.6, [title], 13, color=INK, bold=True)
            if it.get("pill"):
                label, color = it["pill"]
                self.rect(cx + cw - 1.45, yy - 0.02, 1.2, 0.3, color, radius=0.15)
                self.text(cx + cw - 1.45, yy + 0.02, 1.2, 0.26, [clip(label, BODY_MIN, 1.1, 1, bold=True)], BODY_MIN, color=WHITE, bold=True, align="center")
            yy += 0.3 * len(wrap(title, 13, tw, True)) + 0.12
            if it.get("value"):
                vs = fit([it["value"]], iw, 0.75, 22, 14, head=True)
                vp = fit_paras([it["value"]], vs, iw, 0.75, head=True)
                self.text(cx + 0.25, yy, iw, 0.75, vp, vs, color=it.get("value_color", INK), head=True)
                yy += len(wrap(vp[0] if vp else "", vs, iw, head=True)) * _lh(vs) + 0.12
            note_h = (0.12 + min(3, len(wrap(it["note"], BODY_MIN, iw))) * _lh(BODY_MIN)) if it.get("note") else 0
            lines = [str(x) for x in it.get("lines") or [] if x]
            if lines:
                room = cy + ch - 0.18 - yy - note_h
                paras = [("• " if b.get("bullets") else "") + x for x in lines]
                ls = fit(paras, iw, room, b.get("size", 13), BODY_MIN)
                self.text(cx + 0.25, yy, iw, room, fit_paras(paras, ls, iw, room), ls, color=INK2)
            if it.get("note"):
                self.text(cx + 0.25, cy + ch - 0.16 - note_h + 0.12, iw, note_h - 0.12, fit_paras([it["note"]], BODY_MIN, iw, note_h - 0.12), BODY_MIN, color=MUTED)

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
            "x1": (lambda v: whole_figures(f"{v:.1f}x"), 'General"x"'), "num1t": (lambda v: whole_figures(f"{v:,.1f}"), "General")}.get(kind, (lambda v: f"{v:,.0f}", "#,##0"))


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

    def _title_box(self, b):
        x, y, w, h = b["box"]
        if b.get("title"):
            self.text(x, y, w, 0.3, [clip(b["title"], 12, w, 1, bold=True)], 12, color=INK2, bold=True)
            return x, y + 0.36, w, h - 0.36
        return x, y, w, h

    def b_columns(self, b):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
        from pptx.util import Inches, Pt
        x, y, w, h = self._title_box(b)
        cd = CategoryChartData()
        cd.categories = b["cats"]
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
        cd.categories = [clip(c, BODY_MIN, w * 0.42, 2) for c in b["cats"]]
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
        ch.category_axis.tick_labels.font.size = Pt(11)

    def b_lines(self, b):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_MARKER_STYLE
        from pptx.enum.dml import MSO_LINE_DASH_STYLE
        from pptx.util import Inches, Pt
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

    def b_table(self, b):
        x, y, w, h = b["box"]
        lay = table_layout(b, w, h)
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

    def _title_box(self, b):
        x, y, w, h = b["box"]
        if b.get("title"):
            self.text(x, y, w, 0.3, [clip(b["title"], 12, w, 1, bold=True)], 12, color=INK2, bold=True)
            return x, y + 0.36, w, h - 0.36
        return x, y, w, h

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
        self._axes(ch, b["cats"], 11 if len(b["cats"]) <= 8 else 10)
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
        lw = min(w * 0.42, max(_width(c, BODY_MIN) for c in b["cats"]) + 0.15)
        cats = ["\n".join(wrap(clip(c, BODY_MIN, lw - 0.12, 2), BODY_MIN, lw - 0.12)) for c in b["cats"]]
        f = _fmt(b.get("fmt", "pct"))[0]
        vals = [v for v in b["vals"] if v is not None]
        rw = max((_width(f(v), BODY_MIN) for v in vals), default=0.4) + 0.12
        ch.x, ch.y, ch.width, ch.height = lw * 72, 4, (w - lw) * 72 - 4, h * 72 - 8
        data = list(reversed(b["vals"]))
        ch.data = [data]
        self._axes(ch, list(reversed(cats)), BODY_MIN)
        ch.categoryAxis.labels.fillColor = self.col(INK)
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
        for j, v in enumerate(data):
            ch.barLabels[(0, j)].boxAnchor, ch.barLabels[(0, j)].dx = ("e", -4) if v is not None and v < 0 else ("w", 4)
        d.add(ch)
        renderPDF.draw(d, self.c, x * 72, self._y(y + h))

    def b_lines(self, b):
        from reportlab.graphics import renderPDF
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.shapes import Drawing
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
ONE_OFF = "†"                             # marks a net margin above the EBITDA margin: a one-off gain is in it
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


def note_h(text: str, w: float = CW) -> float:
    """The height a muted note under a table needs at 11 pt, so it is never cut (the owner, 7 Nov: the closing disclaimer was clipped)."""
    return len(wrap(text, BODY_MIN, w)) * _lh(BODY_MIN) + 0.04


def _what(text: str) -> str:
    """What a company does, as the page shows it, cleaned as a new read would be (theme_base.one_line): a "**Company Overview **" heading,
    "Incorporatedin1994" or a month's sales line never reaches a slide."""
    from .intel.theme_base import one_line
    return one_line(text) if text else ""


def coverage(v: dict) -> dict:
    """How many companies are in the theme and how many have their key figures, with those figures' share of the theme's market value, in ONE
    wording used everywhere (R20, the owner: the universe against the figures, prominent and the same on every page): "182 in the exchange's
    industries · 60 with figures (97% of value)". "With figures" counts companies whose key figures exist (revenue or profit)."""
    members = v.get("members") or []
    p = v.get("placements") or {}
    total = p.get("total") or len({m["symbol"] for m in members})
    n = v.get("with_figures")
    if n is None:
        n = (v.get("figures") or {}).get("shown") or v.get("members_with_figures") or 0
    with_f = {m["symbol"] for m in members if m.get("revenue") is not None or m.get("net") is not None or m.get("ebitda") is not None}
    caps = {m["symbol"]: m.get("cap") or 0 for m in members}
    every = sum(caps.values())
    share = round(sum(caps[s_] for s_ in with_f) / every * 100) if every and with_f else None
    base_n = max(0, (p.get("base") or 0) - (p.get("named") or 0))
    where = ("in the exchange's industries" if base_n and base_n >= total else "in the theme's list" if p.get("named") and not base_n and not p.get("added")
             else "in the theme")
    universe = f"{total:,} {where}"
    figs = f"{n:,} with figures" + (f" ({share}% of value)" if share is not None else "")
    line = f"{universe} · {figs}"
    return {"n": n, "total": total, "share": share, "text": line, "line": line, "universe": universe, "figs": figs}


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
    if mem.get("placed"):
        checked = "" if mem["placed"] >= total else f" of the {mem['placed']:,} checked"
        head += f"; {mem.get('confirmed', 0):,}{checked} confirmed by their own description, {mem.get('not_confirmed', 0):,} not yet"
    return head


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


def pe_peer_line(pp: dict) -> str:
    """The one P/E comparison the deck makes (R17-010: the findings said 8.2% above while the table's medians were 3.4% apart): the median P/E
    of the companies that have similar-size peers against the median of their peers' medians, both over the same companies, and the gap is
    the ratio of those two medians, the two numbers the valuation table shows."""
    return (f"Median P/E {_times(pp['theme'])} for the {_n(pp['n'], 'company', 'companies')} with peers of similar market value {peer_set_words(pp)}, "
            f"{premium_words(pp['premium'])} their peers' median of {_times(pp['peers'])}")


def peer_set_words(pp: dict) -> str:
    """Which companies the peers are (R23, the owner's reviews: "listed peers of similar market value" are not economically comparable): their
    own sector outside the theme, the sector with the theme's other companies counted, or the whole market where a sector has too few."""
    sets = pp.get("sets") or {}
    sec_n, th_n, mk_n = sets.get("sector", 0), sets.get("sector_theme", 0), sets.get("market", 0)
    if not sets:
        return "in the whole market"
    if not mk_n:
        return "in their own sector" + (" outside the theme" if not th_n else ", the theme's other companies counted" if not sec_n else
                                       f" (for {th_n}, the theme's other companies counted)")
    if not sec_n and not th_n:
        return f"in the whole market (fewer than {PEER_MIN} in their own sector)"
    return f"in their own sector for {sec_n + th_n} and the whole market for {mk_n} (fewer than {PEER_MIN} in their sector)"


PEER_MIN = 10                     # theme_data.PEER_MIN: peers of a company's own sector its own-sector set needs


def _refs(slides: list) -> None:
    """Page references: "⟦Valuation⟧" in a finding becomes "p. 31", the first slide whose title starts with it ("" when there's none)."""
    first = {}
    for i, s in enumerate(slides, 1):
        first.setdefault(re.sub(r" \(\d+ of \d+\)$", "", s.title), i)

    def page(m):
        hit = next((p for t, p in first.items() if t.startswith(m.group(1))), None)
        return f"p. {hit}" if hit else ""

    def fix(x):
        return REF.sub(page, x).replace(" ()", "").replace("()", "").rstrip() if isinstance(x, str) else x
    for s in slides:
        s.subtitle = fix(s.subtitle)
        for b in s.blocks:
            if b.get("paras"):
                b["paras"] = [fix(x) for x in b["paras"]]
            if b.get("rows"):
                b["rows"] = [r if isinstance(r, dict) else [fix(x) for x in r] for r in b["rows"]]
            if b.get("items") and isinstance(b["items"][0], dict):
                b["items"] = [{**it, "lines": [fix(x) for x in it.get("lines") or []], "value": fix(it.get("value")), "title": fix(it.get("title")),
                               "note": fix(it.get("note"))} for it in b["items"]]


def watch_list(v: dict, today: date) -> list[dict]:
    """"Worth a watch" (the owner, 7 Nov: a list only, rule-based, each company with its factual trigger; no view of what to do): results filed but
    not yet in the figures, an auditor's resignation, a promoter stake move of a point or more, results due in the next week, a net margin with a
    one-off gain in it, an operating figure a quarter or more above or below a year before (not held), and a stale operating figure. Each row
    is a fact with its day and the slide it is on."""
    sec = v.get("sections") or {}
    own, ev, q = sec.get("ownership") or {}, sec.get("events") or {}, sec.get("quarter") or {}
    out = []
    for x in q.get("earlier") or []:
        if x.get("filed_unread"):
            out.append({"name": x["name"], "fact": f"Results filed on {_day(x['filed_unread'])}; the figures here are still {x.get('of') or 'an earlier quarter'}",
                        "at": x["filed_unread"], "ref": "The latest quarter"})
    for x in own.get("red_flags") or []:
        if "auditor" in str(x.get("label")).lower():
            out.append({"name": x["name"], "fact": str(x["label"]), "at": x.get("at"), "ref": "Events"})
    for x in own.get("holdings") or []:
        if changed(x.get("promoter_change"), 1.0):
            out.append({"name": x["name"], "fact": f"Promoters' stake {_pts(x['promoter_change'])} to {_pc(x.get('promoter'))} in the quarter to {_month(x.get('quarter'))}",
                        "at": x.get("quarter"), "ref": "Ownership"})
    soon = (today + timedelta(days=7)).isoformat()
    for x in ev.get("results_due") or []:
        if str(x.get("date")) <= soon:
            out.append({"name": x["name"], "fact": f"Results due ({x.get('purpose') or 'financial results'})", "at": x.get("date"), "ref": "Events"})
    for x in (v.get("checks") or {}).get("one_off") or []:
        out.append({"name": x["name"], "fact": f"Net margin {_pc(x.get('net'))} above its EBITDA margin {_pc(x.get('ebitda')).replace('.0%', '%')}: a one-off gain is in the year's profit",
                    "at": None, "ref": "Data confidence"})
    biz = v.get("business") or {}
    for g in (biz.get("layers") or []) + (biz.get("subs") or []):
        for r in g.get("rows") or []:
            if r.get("held") or biz_stale(r, today) or any(o["name"] == r["name"] and o["ref"] == "Operating" for o in out):
                continue
            if changed(r.get("change_year"), 25.0) and "%" not in (r.get("unit") or ""):
                out.append({"name": r["name"], "fact": f"{r.get('metric') or 'Operating figure'} {_bizchg(r['change_year'], r.get('unit'))} on a year before "
                                                         f"({_period(r.get('period'), r.get('span') or 'month')})", "at": r.get("filed"), "ref": "Operating"})
    seen, uniq = set(), []
    for x in out:
        k = (x["name"], x["fact"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq[:WATCH_MAX]


WATCH_MAX = 16


def confidence_rows(v: dict, cov: dict, today: date, lender: bool = False) -> list[list[str]]:
    """The data-confidence page (the owner, 7 Nov): each check the figures went through, what it found and what the deck does about it."""
    ch = v.get("checks") or {}
    sec = v.get("sections") or {}
    val = sec.get("valuation") or {}
    rows = []                      # coverage: the table of counts under the checks (coverage_rows)
    names = lambda xs, k=4: ", ".join(x["name"] for x in xs[:k]) + (f" and {len(xs) - k} more" if len(xs) > k else "")  # noqa: E731
    if (v.get("membership") or {}).get("placed"):
        rows.append(["Universe", membership_words(v, cov["total"]) + ".", "Only confirmed companies count in a median or total."])
    if ch.get("unverified"):
        rows.append(["Membership", f"{_n(len(ch['unverified']), 'company', 'companies')} with figures whose own words describe other work: {names(ch['unverified'])}.",
                     "Listed as not confirmed; left out of every median and total."])
    else:
        rows.append(["Membership", "Every company with figures has words of its own, or a checked quote, that show the theme's work.", "Nothing held back."])
    if ch.get("one_off"):
        oo = ", ".join(f"{x['name']} ({_pc(x['net'])} net, {_pc(x['ebitda']).replace('.0%', '%')} EBITDA)" for x in ch["one_off"][:4])
        with_, without = ch.get("net_with"), ch.get("net_without")
        moved = with_ is not None and without is not None and _pc(with_) != _pc(without)      # said only when leaving them out changes it (R18)
        rows.append(["One-off earnings", f"Net margin above the EBITDA margin at {_n(len(ch['one_off']), 'company', 'companies')}: {oo}.",
                     "Marked † and left out of net-margin medians" + (f": the median net margin is {_pc(without)} without them, {_pc(with_)} with them." if moved else ".")])
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
    if ch.get("with_ebitda") and ch.get("whole_points") == ch.get("with_ebitda"):
        rows.append(["Precision", "EBITDA margins are filed in whole points.", "Printed as whole points; a gap of a point or less between medians is not called a difference."])
    n = ch.get("n") or {}
    keys = (("ebitda", "EBITDA margin"), ("net", "net margin"), ("roce", "ROCE")) + ((("roe", "ROE"),) if ch.get("lenders") else ())
    counts = ", ".join(f"{label} {n[k]}" for k, label in keys if n.get(k))
    rows.append(["Bases and counts", ("P/E is on the last four quarters, P/B on the latest book value, margins and returns on the latest full year." if lender else
                                      "P/E is on the last four quarters, EV/EBITDA and margins on the latest full year.")
                 + (f" Medians are of: {counts} companies." if counts else "") + (f" {_n(val['losses'], 'loss-maker')} with no P/E." if val.get("losses") else ""),
                 "Each slide says its period and count."])
    return rows


def coverage_rows(v: dict, cov: dict) -> list[list[str]]:
    """How many companies each total and median is of (R17-013: the cover said 60 companies with figures, the size slide's total was of 45 with
    a market value): the list, those with figures, those with a market value, and each aggregate's own count, with the share of market value."""
    sec = v.get("sections") or {}
    size, gm = sec.get("size") or {}, sec.get("growth") or {}
    meds, mg, q, val = sec.get("medians") or {}, sec.get("margins") or {}, sec.get("quarter") or {}, sec.get("valuation") or {}
    rows = [["Companies in the theme's list", f"{cov['total']:,}", ""],
            ["With figures", f"{cov['n']:,}", f"{cov['share']}% of the theme's market value" if cov.get("share") is not None else ""],
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


def _findings(slides: list, v: dict, cov: dict, ebm, cap, eyebrow: str, today: date, chained: bool = True, lender: bool = False) -> None:
    """The findings up front: what the figures show (with page references), the data-confidence page and "Worth a watch". Every sentence is a
    computed fact from the view; no AI writes a figure here, and nothing says what to buy or what is cheap."""
    chain = v.get("chain") or {}
    sec = v.get("sections") or {}
    layers = [x for x in v.get("layers") or [] if any(c.get("status") != "unverified" for c in x.get("companies") or [])]
    from statistics import median as _median
    cards = []
    # 1. value-chain economics: only when there are layers to set side by side (R18: no card that says it can't be done)
    own = [x for x in layers if not x.get("official") and x.get("revenue")]
    measure, mword = ("roe", "return on equity") if lender else ("ebitda", "EBITDA margin")
    if chained and chain.get("line"):
        lines = [chain["line"]]
        tot = sum(x["revenue"] for x in own)
        if own and tot and len(own) >= 2:
            big = max(own, key=lambda x: x["revenue"])
            lines.append(f"{big['layer']} brings in {round(big['revenue'] / tot * 100)}% of the revenue of the map's own layers.")
        cards.append({"title": "Where the return sits" if chain.get("measure") == "roe" else "Where the margin sits", "lines": lines,
                      "note": "⟦The value chain by layer⟧"})
    # 2. growth beside margin (a lender's: beside its return on equity)
    gm = []
    for x in own if chained else []:
        cos = [c for c in x["companies"] if c.get("status") != "unverified" and not c.get("company_wide")]
        g = [c["sales_1y"] for c in cos if c.get("sales_1y") is not None]
        e = (x.get("stats") or {}).get(measure)
        if len(g) >= MIN_BASE and e and e["n"] >= MIN_BASE:            # no finding on a base under 3 (R20)
            gm.append((x["layer"], _median(g), e["median"], len(g)))
    f_ = _pc if lender else ebm
    if len(gm) >= 2:
        fast, slow = max(gm, key=lambda t: t[1]), min(gm, key=lambda t: t[1])
        lines = [f"Fastest revenue growth in the latest year: {fast[0]}, median {_chg(fast[1])} at a median {mword} of {f_(fast[2])} ({fast[3]} companies).",
                 f"Slowest: {slow[0]}, median {_chg(slow[1])} at {f_(slow[2])} ({slow[3]} companies)."]
    else:
        g = (sec.get("growth") or {}).get("median") or {}
        m_ = ((sec.get("medians") or {}).get(measure) or {}).get("median")
        lines = [f"Median company's revenue growth in the latest year: {_med(g.get('revenue_1y'), _chg)}" + (f"; median {mword} {f_(m_)}." if m_ is not None else ".")]
    cards.append({"title": "Growth beside return" if lender else "Growth beside margin", "lines": lines, "note": "⟦Every company's figures⟧"})
    # 3. valuation against companies of similar size, beside growth and ROCE
    peers = (sec.get("valuation") or {}).get("peers") or {}
    lines = []
    if (peers.get("pe") or {}).get("premium") is not None:
        lines.append(pe_peer_line(peers["pe"]) + ".")
    for key, label, f in (("sales_3y", "Revenue growth, 3 years a year", _chg), ("roce", "ROCE", _pc)):
        if peers.get(key):        # the population said (R22: a ROCE of the companies with peers beside the theme's own median read as one figure)
            lines.append(f"{label}, the {peers[key]['n']} with such peers: {f(peers[key]['theme'])} against {f(peers[key]['peers'])}.")
    if not lines:
        lines = ["Too few listed companies of similar market value have the figures to compare."]
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
    cards.append({"title": "What changed", "lines": lines or ["No quarter, margin history or shareholding filing to compare yet."], "note": "⟦The latest quarter⟧"})
    sl_ = sector_lines(sec)
    if sl_:                       # R23: the sector's own filed figures
        cards.append({"title": "Sector operating figures", "lines": sl_[:2], "note": f"⟦{SECTOR_TITLE}⟧"})
    watch = watch_list(v, today)
    conf = confidence_rows(v, cov, today, lender)
    cards.append({"title": "How far the figures go", "lines": [f"{cov['line']}.", f"{len(conf)} checks on every figure, each with what it found."],
                  "note": "⟦Data confidence⟧"})
    cards.append({"title": "Worth a watch", "lines": [f"{_n(len(watch), 'company', 'companies')} with a dated fact, picked by fixed rules, each with its trigger." if watch
                                                      else "No company meets the rules today."], "note": "⟦Worth a watch⟧" if watch else ""})
    if len(cards) > 6:            # two short cards share one so the page keeps two rows of three
        a_, b_ = cards[-2], cards.pop()
        cards[-1] = {"title": f"{a_['title']}; {b_['title'].lower()}", "lines": a_["lines"] + b_["lines"], "note": ", ".join(x for x in (a_["note"], b_["note"]) if x)}
    s = Slide("Key findings", "What the reported figures show, each with the slide it comes from; findings, not advice", eyebrow=eyebrow)
    ccols = 3 if len(cards) != 4 else 2
    s.add("cards", (M, TOP, CW, BOT - TOP), cols=ccols, items=whole_lines(cards, (M, TOP, CW, BOT - TOP), ccols), fill=True, size=13)
    slides.append(s)

    # data confidence on ONE page (R19, the owner: "just keep the important ones"): the checks, then every count in one line under them; a
    # check of least weight gives way when they don't fit
    head, widths = ["Check", "What it found", "What the deck does"], [1.8, 6.6, 3.7]
    counts = coverage_line(v, cov)
    nh = note_h(counts)
    room = BOT - TOP - nh - 0.15
    rows = list(conf)
    for name in CONF_GIVE_WAY:
        if len(table_pages(head, rows, widths, CW, room)) <= 1:
            break
        rows = [r for r in rows if r[0] != name]
    rows = table_pages(head, rows, widths, CW, room)[0] if rows else rows
    s = Slide("Data confidence", "The checks every figure went through, what each found and what the deck does with it", eyebrow=eyebrow)
    th = min(room, table_height(head, rows, widths, CW))
    s.add("table", (M, TOP, CW, th), head=head, rows=rows, widths=widths, numeric=[False] * 3, tight=True)
    s.add("text", (M, TOP + th + 0.15, CW, nh), paras=[counts], size=BODY_MIN, floor=BODY_MIN, color=INK2)
    slides.append(s)

    # worth a watch: only when a company meets the rules, on one page, the most recent first (R19)
    if watch:
        dated = sorted(watch, key=lambda x: str(x.get("at") or ""), reverse=True)
        rows = [[x["name"], x["fact"], _day(x["at"]) if x.get("at") and re.match(r"^\d{4}-\d{2}-\d{2}", str(x["at"])) else _month(x["at"]) if x.get("at") else "–",
                 f"⟦{x['ref']}⟧"] for x in dated]
        note = ("The rules: results filed but not yet in the figures; an auditor's resignation; a promoter stake move of a point or more; results due in "
                "the next week; a net margin with a one-off gain; an operating figure 25% or more above or below a year before.")
        nh = note_h(note)
        wh, ww = ["Company", "Trigger", "Date", "Slide"], [3.0, 6.6, 1.4, 1.0]
        first = table_pages(wh, rows, ww, CW, BOT - TOP - nh - 0.07)[0]
        sub = "Companies with a dated fact that changes, or may change, their figures; picked by fixed rules, not a view"
        if len(first) < len(rows):
            sub = f"The {len(first)} most recent of {len(rows)} companies with a dated fact that changes, or may change, their figures; picked by fixed rules"
        s = Slide("Worth a watch", sub, eyebrow=eyebrow)
        s.add("table", (M, TOP, CW, BOT - TOP - nh - 0.07), head=wh, rows=first, widths=ww, numeric=[False] * 4)
        s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)


CONF_GIVE_WAY = ("Precision", "Old operating figures", "Bases and counts", "Broken series", "One quarter", "Operating figures")


def coverage_line(v: dict, cov: dict) -> str:
    """How many companies each total and median is of, in one line (R19: the counts under the checks, never a page of their own)."""
    parts = []
    for label, n, share in coverage_rows(v, cov):
        if label == "In each median and total":
            parts.append(f"in each median: {share}")
        else:
            parts.append(f"{label[:1].lower() + label[1:]} {n}" + (f" ({share})" if share else ""))
    return f"Counts: {cov['line']}; " + "; ".join(parts[2:]) + "."


# ---------- R18: one formatter, one scheme of layers, a short core ----------
THEME_DECK_VERSION = 23                  # part of a kept deck's key (theme_routes.DECK_CACHE): a file made before a deploy is made again
# a figure that is a whole number prints whole: "15.0%" is 15%, "43.0x" is 43x, "0.0 pts" is 0 pts; any other keeps its one decimal. Only a
# figure followed by its unit, a separator or the end, so a name like "Web 3.0 Ltd" is left as written
_WHOLE = re.compile(r"(?<![\w.,])(\d[\d,]*)\.0(?![\d.])(?=%|x\b| ?(?:pts|points|bn|m|cr|lakh|crore|billion|million|units)\b|\s*$|[,;:)\]](?!\d)|\s(?![A-Za-z]))")


# one money format (R23: "$1,947.2 bn" beside "$4,498 bn"): an amount of 1,000 bn or more prints with no decimal
_BIG_BN = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+)\.(\d+)(?= (?:bn|billion)\b)")


def _big_bn(m) -> str:
    from decimal import ROUND_HALF_UP, Decimal
    v = Decimal(m.group(1).replace(",", "") + "." + m.group(2)).quantize(Decimal("1"), ROUND_HALF_UP)
    return f"{int(v):,}"


def whole_figures(text):
    """A text with every whole figure printed whole (the owner, 7 Nov: 149 "15.0%"-like figures in one deck) and every amount of 1,000 bn or
    more with no decimal; anything else as it is."""
    return _WHOLE.sub(r"\1", _BIG_BN.sub(_big_bn, text)) if isinstance(text, str) else text


CHART_FMT = {"pct": "pct1", "chg": "chg1", "x": "x1", "num1": "num1t"}


def _whole_cell(x):
    if isinstance(x, dict):
        return {**x, **({"text": whole_figures(x["text"])} if "text" in x else {}), **({"group": whole_figures(x["group"])} if "group" in x else {})}
    return whole_figures(x)


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
                b["rows"] = [_whole_cell(r) if isinstance(r, dict) else [_whole_cell(x) for x in r] for r in b["rows"]]
            if b.get("head"):
                b["head"] = [whole_figures(x) for x in b["head"]]
            if b["kind"] == "stats":
                b["items"] = [tuple(whole_figures(x) for x in it) for it in b["items"]]
            elif b.get("items") and isinstance(b["items"][0], dict):
                b["items"] = [{k: ([whole_figures(x) for x in val] if k == "lines" else whole_figures(val) if isinstance(val, str) else val)
                               for k, val in it.items()} for it in b["items"]]
            if b["kind"] in ("hbars", "columns", "lines"):
                b["fmt"] = CHART_FMT.get(b.get("fmt") or ("pct" if b["kind"] != "columns" else ""), b.get("fmt"))
                if b.get("vals"):
                    b["vals"] = _round1(b["vals"])
                if b.get("series"):
                    b["series"] = [(x[0], _round1(x[1]), *x[2:]) for x in b["series"]]
                if b.get("title"):
                    b["title"] = whole_figures(b["title"])


STATS_SHOWN = ("ebitda", "roce", "net", "roe", "nii_assets", "gnpa", "pb")
MIN_BASE = 3                     # companies a median needs to be shown as one (R20: "median of 2" is two values, shown as they are)


def _medn(st, of: int | None = None, f=lambda v: f"{v:.1f}%", n: int | None = None, value=None) -> str:
    """A median with its base (R20): "–" when no company has the figure; "– (2)" when fewer than MIN_BASE do (the companies' own values are
    beside it); the median with "(n)" when it is of fewer companies than the `of` it stands for."""
    if st is not None:
        n, value = st.get("n") or 0, st.get("median")
    if value is None or not n:
        return "–"
    if n < MIN_BASE:
        return f"– ({n})"
    return f(value) + (f" ({n})" if of and n < of else "")


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
LENDER_NOTE = ("Lenders: ROE is net profit over shareholders' equity; NII / assets is interest earned less interest paid over average total "
               "assets (not the bank's own net interest margin); gross and net NPA are of the latest quarter that gives them.")


def is_lender_set(cos: list) -> bool:
    """Whether most of these companies are banks, lenders or insurers (their figures are read on lenders' measures)."""
    cos = [c for c in cos or [] if c.get("status") != "unverified"]
    return bool(cos) and sum(1 for c in cos if c.get("bank")) * 2 >= len(cos)


def co_cols(cos: list) -> list[tuple]:
    """The figure columns for a table of these companies: lenders' own measures only where a lender is among them."""
    bank = any(c.get("bank") for c in cos or [])
    have = {k for k in FAMILY_COLS if any(c.get(k) is not None for c in cos or [])}
    return [c for c in CO_COLS if (bank or c[0] not in LENDER_ONLY) and (c[0] not in FAMILY_COLS or c[0] in have)]


def col_fmt(key: str, rng: bool = False):
    """How a figure column's median (or range) prints: a solvency ratio in times, every other share or change in %."""
    return (lambda x: _times(x, 2)) if key == "solvency" else (lambda x: f"{x:.1f}%") if rng else _pc


def co_cell(c: dict, key: str, amt) -> str:
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
    worth = ((f", worth {cap(size['total_cap'])} together" if wv >= total else
              f"; the {wv:,} with figures and a market value are worth {cap(size['total_cap'])} together") if size.get("total_cap") else "")
    lead = (f"; the largest are {', '.join(big[:-1])} and {big[-1]}" if len(big) > 1 else f"; the largest is {big[0]}") if big else ""
    return f"{sector}: {_n(total, 'company', 'companies')} {where}{worth}{lead}."


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
    whole = bool(checks.get("with_ebitda")) and checks.get("whole_points") == checks.get("with_ebitda")     # every EBITDA margin filed in whole points
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
        return f"{nm} (whole company)" if sym in wide else f"{nm} (not confirmed)" if status.get(sym) == "unverified" else nm

    for m in members:                       # what a company does, as one business sentence (headings, glued words, results lines left off)
        if m.get("what"):
            m["what"] = _what(m["what"])
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
    s.add("stats", (M, 5.12, CW, 1.25), dark=True, items=[
        ("Companies", f"{total:,}", cov["universe"].split(" ", 1)[1] + (f"; {mem['not_confirmed']:,} not confirmed" if mem.get("not_confirmed") else "")), *([("Layers", str(len(shown)))] if chained else []),
        ("With figures", f"{cov['n']:,}", f"{cov['share']}% of value" if cov.get("share") is not None else ""),
        ("Their market value", cap(size.get("total_cap")) if size.get("total_cap") is not None else "–", f"{size.get('with_value', 0):,} of {total:,} with one"),
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
    # trusted and what is worth a watch, each from computed facts only (no AI writes a number here)
    names_shown = {x["layer"] for x in shown}
    unplaced_cos = sorted((c for x in unplaced for c in x.get("companies") or [] if c.get("status") != "unverified"), key=lambda c: -(c.get("cap") or 0))
    rows_c = [r for r in chain.get("rows") or [] if r.get("n") and r["layer"] in names_shown]
    section("", "Findings", "What the figures show, how far they can be trusted, and the companies with a dated fact worth a watch.")
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
        fmt_ = {"ebitda": ebm, "pb": _times}

        def cell(r, k):                    # each median with its base: none under 3 companies, a count when under the layer's (R20)
            if k == "n":
                return str(r["n"])
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
        chart = 2 <= len(charted) <= 14
        tw = 7.3 if chart else CW
        foot = [v.get("basis") or f"Each company's latest full year, in {unit}.", "Layer revenue: its companies added together; margins and returns: its median company."]
        if lend_chain:
            foot.append(LENDER_NOTE)
        if chain.get("highest"):
            foot.append(f"Highest median {'return on equity' if key == 'roe' else 'EBITDA margin'} in green, lowest in red, among the layers with at least two companies.")
        none_ = [x["layer"] for x in layers if not x.get("companies") and x.get("layer")]
        unsure_ = [x for x in empty if x not in none_]
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
                s.add("hbars", (M + tw + 0.35, TOP, CW - tw - 0.35, th), title=f"Median {'ROE' if key == 'roe' else 'EBITDA margin'} by layer", cats=[f"{r['layer']} ({r.get(key + '_n') or 0})" for r in charted],
                      vals=[r[key] for r in charted], colors=[mark.get(r["layer"], BLUE) for r in charted], fmt="pctw" if whole and key == "ebitda" else "pct")
            s.add("text", (M, BOT - fh, CW, fh), paras=[" ".join(foot)], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
    elif v.get("members_with_figures") == 0 or not shown:
        left_out.append(("none", "the value chain's figures (no company has stored figures)"))

    # 4. each layer on ONE page (R18, the owner: the value chain alone ran 15 pages): what it does, its largest companies by market value with the
    # layer's median and range, its margins by year or by company; the full table is in the appendix, said with its page
    biz = v.get("business") or {}
    for i, layer in enumerate(shown if chained else []):     # numbered as shown: a layer with no company leaves no gap (Layer 4, then Layer 6)
        cos = sorted(layer.get("companies") or [], key=lambda c: (c.get("status") == "unverified", -(c.get("cap") or 0), c.get("name") or ""))
        st = layer.get("stats") or {}
        title = f"Layer {i + 1} · {layer['layer']}"
        lwide = set(layer.get("company_wide") or []) | {c["symbol"] for c in cos if c.get("company_wide")}
        lwhole = whole or (bool([c for c in cos if c.get("ebitda") is not None]) and all(c.get("ebitda_dp") == 0 for c in cos if c.get("ebitda") is not None))
        unsure = {c["symbol"] for c in cos if c.get("status") == "unverified"}
        lend = is_lender_set(cos)
        cols = co_cols(cos)
        if not layer.get("official") and len({c.get("official_industry") for c in cos if c.get("official_industry")}) >= 2:
            cols = [("official_industry", "Industry", 1.7)] + cols        # an AI layer: the exchange's industry is a column, not a layer (R20)
        body = [[(f"{c['name']} (whole company)" if c["symbol"] in lwide else f"{c['name']} (not confirmed)" if c["symbol"] in unsure else c["name"])]
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
        msg = layer.get("line") or (f"{_n(layer.get('n', len(cos)), 'company', 'companies')}, revenue {amt(layer.get('revenue'))} together"
                                    + (f"; {', '.join(meds_)}" if meds_ else ""))
        desc = layer.get("description") or ""
        official = ("Companies of the theme's industries whose own words fit none of the map's layers." if layer.get("basis") == "rest" else
                    "Companies of the theme's list that the exchange files under this industry." if layer.get("by_industry") else
                    "The theme's own named companies that the layers above don't place." if layer.get("basis") == "list" else
                    "Companies the exchange classifies under this industry that the layers above don't place.") if layer.get("official") else ""
        card = {"title": "What this layer does", "lines": [clip(desc, 13, CW - 0.5, 3)] + ([official] if official else []), "note": AI_NOTE} if desc else \
            {"title": "Who is here", "lines": [official]} if official else None
        hist = layer.get("history") or {}
        mkey, mname = ("roe", "ROE") if lend else ("ebitda", "EBITDA margin")
        bars = [c for c in cos if c.get(mkey) is not None and c["symbol"] not in unsure]
        chart = None
        if len(hist.get("years") or []) >= 2 and not lend and (hist.get("n") or 0) >= MIN_BASE:       # an aggregate of 3 or more (R21)
            chart = {"kind": "lines", "title": f"Margins by year, the same {_n(hist.get('n') or 0, 'company', 'companies')}",
                     "cats": hist["years"], "series": [("EBITDA margin", hist["ebitda"], BLUE), ("Net margin", hist["net"], ORANGE)], "fmt": "pct", "labels": True}
        elif len(bars) >= 2:
            top = sorted(bars, key=lambda c: -(c[mkey] or 0))[:8]
            chart = {"kind": "hbars", "title": f"{mname} by company", "cats": [c["name"] for c in top], "vals": [c[mkey] for c in top],
                     "fmt": "pctw" if whole and mkey == "ebitda" else "pct", "colors": [DOWN if c[mkey] < 0 else BLUE for c in top]}
        fparts = []
        if any(c["symbol"] in lwide for c in cos):
            fparts.append("(whole company): it runs other businesses too, so its figures are the whole company's and left out of the medians.")
        if unsure:
            fparts.append("(not confirmed): its own words don't show this work, so it is left out of the medians and the revenue total.")
        if any(c.get("one_off") for c in cos):
            fparts.append(f"{ONE_OFF}: net margin above the EBITDA margin, so a one-off gain is in it; left out of the net margin's median.")
        if lend:
            fparts.append(LENDER_NOTE)
        chh = min(1.75, card_height(card, CW)) if card else 0.0
        below = TOP + (chh + 0.2 if card else 0)
        rest_h = REST_H if len(body) > 1 else 0
        fnote = " ".join(fparts)
        fh = (note_h(fnote) + 0.12) if fnote else 0
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
        s = Slide(title, msg, eyebrow=eb("The value chain"))
        if card:
            s.add("cards", (M, TOP, CW, chh), cols=1, fill=True, items=[card])
        th = room - (REST_H if k_fit < len(body) else 0)
        s.add("table", (M, below, tw, th), head=head, rows=body[:k_fit] + tail, widths=widths, strong=list(range(k_fit, k_fit + len(tail))), tight=True)
        if chart:
            c = dict(chart)
            s.add(c.pop("kind"), (M + tw + 0.4, below, CW - tw - 0.4, room), **c)
        if k_fit < len(body):
            s.add("text", (M, below + th + 0.04, CW, REST_H - 0.04), paras=[f"The largest {k_fit} of {len(body)} by market value; every one: appendix, ⟦Every company's figures⟧."],
                  size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        if fnote:
            s.add("text", (M, BOT - fh + 0.08, CW, fh - 0.08), paras=[fnote], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

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
        rows = [[sub["name"], sentences(sub.get("detail") or "", 160) or "–", str(len(sub.get("companies") or [])),
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
    figs_of = lambda x: x.get("revenue") is not None or x.get("profit") is not None or x.get("net") is not None      # noqa: E731
    confirmed_ = [x for x in sec.get("leaders") or [] if status.get(x["symbol"]) != "unverified"]
    bare = [x for x in confirmed_ if not figs_of(x)]           # a stored page with no key figure isn't "with figures" (R20)
    lead = sorted((x for x in confirmed_ if figs_of(x)), key=lambda x: -(x.get("cap") or 0))
    if lead:
        # short headings on one line, so 20 or more rows fit a page (R20: 8 rows a page)
        lcols = [("revenue", "Revenue", 1.15), ("sales_1y", "Growth", 0.95), ("ebitda", "EBITDA", 0.95), ("net", "Net", 0.9), ("roce", "ROCE", 0.85)]
        if any(x.get("bank") for x in lead):
            lcols += [("roe", "ROE", 0.85), ("gnpa", "GNPA", 0.85)]
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
                + (f" {ONE_OFF} a one-off gain in the net margin." if any(x.get("one_off") for x in lead) else "")
                + (f" No reported figures yet: {names5(bare)}." if bare else ""))
        nh = note_h(note)
        th = BOT - TOP - nh - 0.07
        cbase = {"compact": True}
        pages = table_pages(head, rows, widths, CW, th, most=26, compact=True)
        for k, chunk in enumerate(pages):
            s = Slide("Every company's figures" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      f"{_n(len(lead), 'confirmed company', 'confirmed companies')} with figures, one row each; {lead[0]['name']} is the largest at {cap(lead[0].get('cap'))}",
                      eyebrow=eb("Appendix"))
            s.add("table", (M, TOP, CW, th), head=head, rows=chunk, widths=widths, **cbase)
            s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            later_slides.append(s)

    # 7. tailwinds and risks, on one page (R19); the headlines and new listings stay on the theme's page
    tw_, rk_ = v.get("tailwinds") or [], v.get("risks") or []
    claims = [("Tailwind", c) for c in tw_] + [("Risk", c) for c in rk_]
    n_checked = sum(1 for _, c in claims if c.get("status") == "current" and c.get("source"))
    if claims:
        section("", "Tailwinds and risks", f"{_n(len(tw_), 'tailwind')} and {_n(len(rk_), 'risk')}; {n_checked} with a dated headline from the last 18 months "
                "that shows it is still current.")
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
        sub_line = f"{_n(nt, 'tailwind')} and {_n(nr, 'risk')}, {n_checked} of {len(claims)} with a dated source"
        if len(rk_) < len(tw_):
            sub_line += f"; the map names fewer risks ({len(rk_)}) than tailwinds ({len(tw_)})"
        elif len(tw_) < len(rk_):
            sub_line += f"; the map names fewer tailwinds ({len(tw_)}) than risks ({len(rk_)})"
        if len(first) < len(claims):
            sub_line += "; the rest are on the theme's page"
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
    read = ["Every figure's year and basis are said under the value chain by layer; market value is price times shares in issue at the last close."]
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
    if later_slides:
        crow.append(["Appendix", f"Every confirmed company's key figures, one row each ({_n(len(later_slides), 'page')}).", str(slides.index(later_slides[0]) + 1)])
    contents.add("table", (M, TOP, CW, min(BOT - TOP, table_height(["Part", "What it holds", "Page"], crow, [2.6, 8.4, 0.9], CW))),
                 head=["Part", "What it holds", "Page"], rows=crow, widths=[2.6, 8.4, 0.9], numeric=[False, False, True], tight=True)
    _sections(sector, slides)
    _refs(slides)
    for x in slides:                  # a "Slide" column whose pages aren't in this deck says nothing: dropped (R19)
        for b in x.blocks:
            if b["kind"] == "table" and "Slide" in b["head"]:
                b["head"], b["rows"], b["widths"], b["numeric"] = drop_empty(b["head"], b["rows"], b["widths"], b.get("numeric"), keep=tuple(range(len(b["head"]) - 1)))
    whole_deck(slides)
    return slides, footer


def base_quarter(label: str | None) -> str | None:
    """The quarter a year before one named like "Sep 2026": "Sep 2025"."""
    m = re.match(r"\s*([A-Za-z]{3})\w*\s+(\d{4})", str(label or ""))
    return f"{m.group(1).title()} {int(m.group(2)) - 1}" if m else None


def economics_questions(v: dict, shown: list, sec: dict, ebm) -> list[str]:
    """Questions the figures raise, each stating the computed facts it rests on (R17-015). Facts and questions only: no answer, no view of
    what to do; a question is asked only when its figures exist."""
    out = []
    chain = v.get("chain") or {}
    rows = {r["layer"]: r for r in chain.get("rows") or []}
    hi, lo = rows.get(chain.get("highest")), rows.get(chain.get("lowest"))
    if hi and lo and chain.get("measure") == "roe":
        out.append(f"{hi['layer']} has the highest median return on equity ({_pc(hi['roe'])}, {hi['roe_n']} companies) and {lo['layer']} the lowest "
                   f"({_pc(lo['roe'])}, {lo['roe_n']}). What in each layer's business makes that gap? The figures show the gap, not its cause.")
    elif hi and lo:
        out.append(f"{hi['layer']} has the highest median EBITDA margin ({ebm(hi['ebitda'])}, {hi['ebitda_n']} companies) and {lo['layer']} the lowest "
                   f"({ebm(lo['ebitda'])}, {lo['ebitda_n']}). What in each layer's business makes that gap? The figures show the gap, not its cause.")
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
    peers = (sec.get("valuation") or {}).get("peers") or {}
    if (peers.get("pe") or {}).get("premium") is not None and peers.get("sales_3y"):
        g = peers["sales_3y"]
        out.append(f"{pe_peer_line(peers['pe'])}; their revenue grew {_chg(g['theme'])} a year over 3 years against {_chg(g['peers'])} for their peers. "
                   "What do the prices take into account that past growth doesn't show?")
    gm = []
    for x in shown:
        cos = [c for c in x.get("companies") or [] if c.get("status") != "unverified" and not c.get("company_wide")]
        g = sorted(c["sales_1y"] for c in cos if c.get("sales_1y") is not None)
        if len(g) >= MIN_BASE:
            from statistics import median as _m
            gm.append((x["layer"], _m(g), len(g)))
    if len(gm) >= 2:
        f_, s_ = max(gm, key=lambda t: t[1]), min(gm, key=lambda t: t[1])
        if f_[0] != s_[0]:
            out.append(f"Median revenue growth in the latest year: {_chg(f_[1])} in {f_[0]} ({f_[2]} companies), {_chg(s_[1])} in {s_[0]} ({s_[2]}). "
                       "Is the difference in demand, in prices, or in the products each layer's companies make?")
    return out[:1] + sector_questions(sec) + out[1:]


def _economics(slides: list, v: dict, shown: list, sec: dict, ebm, eyebrow: str, section, lender: bool = False) -> None:
    """Industry economics (R17-015), a short part: each layer's margins, returns, growth and valuation side by side; what moved the aggregate
    EBITDA margin between the last two years (companies and layers, in points that add up to the change); and the questions the figures raise.
    Every number is computed from the stored figures; a page whose figures don't exist is not drawn, and the part is left out when none is."""
    from statistics import median as _m
    lay = []
    for x in shown:
        cos = [c for c in x.get("companies") or [] if c.get("status") != "unverified" and not c.get("company_wide")] or \
              [c for c in x.get("companies") or [] if c.get("status") != "unverified"]
        st = x.get("stats") or {}
        g = [c["sales_1y"] for c in cos if c.get("sales_1y") is not None]
        pe = [c["pe"] for c in cos if c.get("pe") and c["pe"] > 0]
        # a median of fewer than MIN_BASE companies is no median here (R20): no value, its count kept for the cell
        med = lambda k: (st.get(k) or {}).get("median") if ((st.get(k) or {}).get("n") or 0) >= MIN_BASE else None      # noqa: E731
        lay.append({"layer": x["layer"], "n": len(cos), "rest": x.get("basis") == "rest", "ebitda": med("ebitda"), "roce": med("roce"),
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
    if lay:
        # a lender's layers on lenders' measures (R18): net margin, ROE, net interest income over assets, gross NPA and P/B beside growth and P/E
        cellm = lambda x, k, f: _medn(None, x["n"], f, n=x[f"{k}_n"], value=x[k] if x[f"{k}_n"] >= MIN_BASE else (x[k] or 0) or 1)   # noqa: E731
        rows = [[x["layer"], str(x["n"]), cellm(x, "ebitda", ebm), cellm(x, "roce", _pc)]
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
        tw = 7.6 if chart else CW
        rk, rname = ("roe", "ROE") if lender else ("roce", "ROCE")
        cmp_ = [x for x in lay if not x.get("rest")]            # the "Other" group is never called highest or fastest (R22)
        best_r = max((x for x in cmp_ if x[rk] is not None), key=lambda x: x[rk], default=None)
        fast = max((x for x in cmp_ if x["growth"] is not None), key=lambda x: x["growth"], default=None)
        bits = []
        if best_r and len(lay) > 1:
            bits.append(f"highest median {rname} in {best_r['layer']} ({_pc(best_r[rk])})")
        if fast and len(lay) > 1:
            bits.append(f"fastest median revenue growth in {fast['layer']} ({_chg(fast['growth'])})")
        msg = ("Medians by layer: " + "; ".join(bits) + ("; the \"Other\" group left out" if len(cmp_) < len(lay) else "")) if bits else \
            f"{_n(len(lay), 'layer')}: its median company's margins, returns, growth and P/E"
        note = ("Medians of each layer's confirmed companies (whole-company figures left out where the layer has its own); growth and P/E show their "
                "count in brackets. EBITDA margin and ROCE: the latest full year; P/E: the last four quarters.")
        nh = note_h(note)
        for k, chunk in enumerate(pages := table_pages(head, rows, widths, tw, BOT - TOP - nh - 0.07)):
            s = Slide("Layers side by side" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=eyebrow)
            th = min(BOT - TOP - nh - 0.07, table_height(head, chunk, widths, tw))
            s.add("table", (M, TOP, tw, th), head=head, rows=chunk, widths=widths, tight=True)
            room.append((s, M, TOP + th + 0.25, tw, BOT - nh - 0.15 - (TOP + th + 0.25)))
            if chart and k == 0:
                n1, n2 = ("ROE", "Net margin") if lender else ("EBITDA margin", "ROCE")
                s.add("columns", (M + tw + 0.4, TOP, CW - tw - 0.4, BOT - TOP - nh - 0.07), title=f"Median {n1} and {n2}", fmt="pct",
                      cats=[clip(x["layer"], 10, 1.2, 1) for x in both], series=[(n1, [x["ebitda"] for x in both], BLUE), (n2, [x["roce"] for x in both], ORANGE)])
            s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
    if md.get("companies"):
        lead = md["layers"][0] if md.get("layers") else None
        msg = (f"The aggregate EBITDA margin went from {_pc(md['start'])} in {md['from']} to {_pc(md['end'])} in {md['to']} ({_pts(md['change'])}, "
               f"{_n(md['n'], 'company', 'companies')})" + (f"; {lead['layer']} accounts for {_pts(lead['part'])} of it" if lead and len(md["layers"]) > 1 else ""))
        rows = [[x["name"], x.get("layer") or "–", f"{ebm(x['margin_from'])} → {ebm(x['margin_to'])}", f"{_pc(x['share_from'])} → {_pc(x['share_to'])}", _pts(x["part"])]
                for x in md["companies"]]
        head, widths = ["Company", "Layer", "EBITDA margin", "Share of revenue", "Part of the move"], [2.6, 2.2, 1.6, 1.6, 1.3]
        lw = 8.6 if len(md.get("layers") or []) > 1 else CW
        note = (f"Each company's part: its EBITDA as a share of all {md['n']} companies' revenue in {md['to']}, less the same in {md['from']}; the parts "
                "add up to the change. A part moves with the company's own margin and with its weight in the group's revenue. The companies that moved it most.")
        nh = note_h(note)
        s = Slide("What moved the aggregate margin", msg, eyebrow=eyebrow)
        th = min(BOT - TOP - nh - 0.07, table_height(head, rows, widths, lw))
        s.add("table", (M, TOP, lw, th), head=head, rows=rows, widths=widths, tight=True)
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
        if spot:
            sl, x, y, w, _ = spot
            sl.add("cards", (x, y, w, card_height(card, w, True, 12) + 0.1), cols=1, fill=True, bullets=True, size=12, items=[card])
        else:
            s = Slide("Questions the figures raise", "Each question with the computed figures it rests on; the figures don't answer them", eyebrow=eyebrow)
            s.add("cards", (M, TOP, CW, min(BOT - TOP, card_height(card, CW, True, 13) + 0.1)), cols=1, fill=True, bullets=True, size=13, items=[card])
            slides.append(s)


# ---------- R23: each sector's own operating figures, as filed ----------
SECTOR_TITLE = "Sector operating figures"
SECTOR_LEAD = {"bank": ("gnpa_f", "cet1", "advances_growth", "credit_cost"), "insurer": ("solvency", "combined_ratio", "claims_ratio", "persistency_13"),
               "us": ("sbc_share", "fcf_margin", "rpo_growth", "deferred_growth")}
SECTOR_PAGE = {"bank": "banks", "insurer": "insurers", "us": "US companies"}
SECTOR_WHO = {"bank": ("bank", "banks"), "insurer": ("insurer", "insurers"), "us": ("company", "companies")}


def sector_fmt(key: str, amt=None):
    """How one filed sector figure prints: a share in %, a change signed, a ratio in times, an amount in the theme's money."""
    from .intel.sector_metrics import BY_KEY
    kind = BY_KEY[key][3]
    if kind == "chg":
        return _chg
    if kind == "x":
        return lambda x: _times(x, 2)
    if kind == "amt":
        return amt or (lambda x: f"{x:,.0f}")
    return _pc


def sector_lines(sec: dict) -> list[str]:
    """The findings' lines for the sector figures: for each family, the medians of its lead figures over at least MIN_BASE companies (R20)."""
    from .intel.sector_metrics import BY_KEY
    out = []
    for fam, f in ((sec.get("sector") or {}).get("families") or {}).items():
        parts = []
        for k in SECTOR_LEAD.get(fam, ()):
            st = (f.get("medians") or {}).get(k)
            if st and st.get("n", 0) >= MIN_BASE:
                parts.append(f"{BY_KEY[k][1].lower().replace('npa', 'NPA').replace('cet1', 'CET1').replace('sbc', 'SBC').replace('rpo', 'RPO').replace('fcf', 'FCF')} "
                             f"{sector_fmt(k)(st['median'])}" + (f" ({st['n']})" if st["n"] < f["n"] else ""))
        if parts:
            one, many = SECTOR_WHO[fam]
            out.append(f"Median of the {_n(f['n'], one, many)} with filed figures: {', '.join(parts[:4])}.")
    return out


def sector_questions(sec: dict) -> list[str]:
    """Questions the filed sector figures raise, each with its computed medians (facts and questions only; asked only when the figures exist)."""
    fams = (sec.get("sector") or {}).get("families") or {}
    med = lambda f, k: (f.get("medians") or {}).get(k) if ((f.get("medians") or {}).get(k) or {}).get("n", 0) >= MIN_BASE else None    # noqa: E731
    out = []
    b = fams.get("bank") or {}
    a, d = med(b, "advances_growth"), med(b, "deposit_growth_f")
    if a and d:
        out.append(f"Median advances growth {_chg(a['median'])} ({a['n']} banks) against median deposit growth {_chg(d['median'])} ({d['n']}), each on a "
                   "year before. Where does the rest of the lending's funding come from, or go? The figures show the two rates, not the funding mix.")
    i = fams.get("insurer") or {}
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


def _sector_slides(slides: list, v: dict, amt, eyebrow: str) -> None:
    """A page for each family's filed operating figures (R23): every company's figures with the period they are for, the median of each over
    the companies that have it (none under MIN_BASE), and how each is worked out, where it is from and what the filings don't state."""
    from .intel.sector_metrics import BY_KEY
    sec = (v.get("sections") or {}).get("sector") or {}
    defs = []                     # (figure, how it is worked out) for every figure shown, on one page after the families' own (each says its source)
    for fam, f in (sec.get("families") or {}).items():
        keys = list(f.get("keys") or [])
        if not keys or not f.get("rows"):
            continue
        fmts = {k: sector_fmt(k, amt) for k in keys}
        head = ["Company"] + [BY_KEY[k][1] for k in keys] + ["Period"]
        widths = [2.6] + [1.05] * len(keys) + [1.15]
        body = [[r["name"]] + [fmts[k](r[k]) if r.get(k) is not None else "–" for k in keys] + [r.get("as_of") or "–"]
                for r in sorted(f["rows"], key=lambda r: r.get("name") or "")]
        meds = f.get("medians") or {}
        med_row = ["Median (companies)"] + [_medn(meds.get(k), f["n"], fmts[k]) for k in keys] + [""]
        head, every, widths, _ = drop_empty(head, body + [med_row], widths)
        body, tail = every[:-1], every[-1:]
        one, many = SECTOR_WHO[fam]
        lead = sector_lines({"sector": {"families": {fam: f}}})
        msg = (lead[0].rstrip(".") if lead else f"{_n(f['n'], one, many)} with filed figures") + (f"; {f['of'] - f['n']} more without" if f.get("of", 0) > f["n"] else "")
        defs += [[BY_KEY[k][1], BY_KEY[k][4]] for k in keys if BY_KEY[k][1] in head]
        note = (f"From {f['checked']}, each company's latest; the period is the latest it covers, and the next page says how each figure is worked out."
                + (f" Not shown: {f['not_filed']}." if f.get("not_filed") else "")
                + f" Medians: the companies that have the figure, the count in brackets when fewer than the {f['n']}; none under {MIN_BASE}.")
        nh = note_h(note)
        room = BOT - TOP - nh - 0.15
        compact = len(body) > 10    # a long family: one line a company, so a page holds them (no half-empty second page)
        pages = table_pages(head, body + tail, widths, CW, room, most=26, compact=compact)
        if len(pages) > 1:          # the median row stays at the foot of the last page
            pages = table_pages(head, body, widths, CW, room - 0.45, most=26, compact=compact)
            pages[-1] = pages[-1] + tail
        for k_, chunk in enumerate(pages):
            s = Slide(f"{SECTOR_TITLE}: {SECTOR_PAGE[fam]}" + (f" ({k_ + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=eyebrow)
            th = min(room, sum(table_layout({"head": head, "rows": chunk, "widths": widths, "tight": True, "compact": compact}, CW, 99)["heights"]))
            s.add("table", (M, TOP, CW, th), head=head, rows=chunk, widths=widths, tight=True, compact=compact,
                  strong=[i for i, r in enumerate(chunk) if r is tail[0]])
            s.add("text", (M, BOT - nh, CW, nh), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
    if defs:
        head, widths = ["Figure", "How it is worked out"], [2.2, 9.9]
        for k_, chunk in enumerate(pages := table_pages(head, defs, widths, CW, BOT - TOP)):
            s = Slide(f"{SECTOR_TITLE}: how each is worked out" + (f" ({k_ + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      "Each figure as the filing states it, or the arithmetic on filed figures that gives it; nothing estimated", eyebrow=eyebrow)
            s.add("table", (M, TOP, CW, min(BOT - TOP, table_height(head, chunk, widths, CW))), head=head, rows=chunk, widths=widths, tight=True)
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
        rows = [[name_of(x["symbol"], x["name"]), cap(x.get("cap")), _pc(x.get("share"))] for x in big]
        rows.append([f"All {size.get('with_value', 0):,} companies with figures and a market value", cap(size.get("total_cap")), "100.0%"])
        lw = 6.2
        s.add("table", (M, TOP, lw, BOT - TOP - 0.3), head=["Company", "Market value", "Share of the theme"], rows=rows, widths=[3.2, 1.5, 1.5], strong=[len(rows) - 1])
        top = big[:10]
        s.add("hbars", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP - 0.3), title="Share of the theme's market value", cats=[x["name"] for x in top],
              vals=[x.get("share") or 0 for x in top], fmt="pct")
        s.add("text", (M, BOT - 0.25, CW, 0.25), paras=["Market value: price times shares in issue, as each company's page shows it."], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

    gm = sec.get("growth") or {}
    agg, gmed = gm.get("aggregate") or {}, gm.get("median") or {}
    mk = sec.get("market") or {}
    meds = sec.get("medians") or {}
    if agg or gmed or meds:
        grow = [[label, _chg((agg.get(f"{k}_1y") or {}).get("value")), _chg((agg.get(f"{k}_3y") or {}).get("value")),
                 _chg((gmed.get(f"{k}_1y") or {}).get("median")), _chg((gmed.get(f"{k}_3y") or {}).get("median"))] for k, label in (("revenue", "Revenue"), ("profit", "Net profit"))]
        whole = (v.get("checks") or {}).get("whole_points") and (v.get("checks") or {}).get("whole_points") == (v.get("checks") or {}).get("with_ebitda")
        vs = [["EBITDA margin", _pcw((meds.get("ebitda") or {}).get("median"), bool(whole)), str((meds.get("ebitda") or {}).get("n", "–")), _pcw((mk.get("opm") or {}).get("median"), bool(whole))],
              ["Net margin", _med(meds.get("net")), str((meds.get("net") or {}).get("n", "–")), _med(mk.get("net_margin"))],
              ["ROCE", _med(meds.get("roce")), str((meds.get("roce") or {}).get("n", "–")), _med(mk.get("roce"))],
              ["ROE", _med(meds.get("roe")) if (v.get("checks") or {}).get("lenders") else "–", str((meds.get("roe") or {}).get("n", "–")), "–"],
              ["Revenue growth, 3 years a year", _med(gmed.get("revenue_3y"), _chg), str((gmed.get("revenue_3y") or {}).get("n", "–")), _med(mk.get("sales_cagr_3y"), _chg)]]
        vs = [r_ for r_ in vs if r_[1] != "–"]          # a median no company has (lenders' EBITDA margin) is no row (R18)
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
        s.add("table", (M, y2 + 0.36, lw, BOT - y2 - 0.36 - 0.85), head=vh_, rows=vs, widths=vw_)
        note = ("Together: the companies' figures added up, for those that report both ends of the period. Median: the middle company's own rate. "
                "Companies that run other businesses too, and net margins with a one-off gain, are left out.")
        if gmed.get("revenue_5y") or gmed.get("profit_5y"):
            note += f" Median company, 5 years a year: revenue {_med(gmed.get('revenue_5y'), _chg)}, profit {_med(gmed.get('profit_5y'), _chg)}."
        s.add("text", (M, BOT - 0.72, lw, 0.72), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        cats, th, al = [], [], []
        for label, a, bm in (("EBITDA margin", meds.get("ebitda"), mk.get("opm")), ("Net margin", meds.get("net"), mk.get("net_margin")),
                             ("ROCE", meds.get("roce"), mk.get("roce")), ("Revenue growth, 3y", gmed.get("revenue_3y"), mk.get("sales_cagr_3y"))):
            if a and bm:
                cats.append(label)
                th.append(a["median"])
                al.append(bm["median"])
        if cats:
            s.add("columns", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP), title="Median company: the theme against all listed", cats=cats, fmt="pct",
                  series=[("Theme", th, BLUE), ("All listed", al, LINE2)])
        slides.append(s)

    # margins over time: the findings and "What moved the aggregate margin" carry the change, so no page of its own (R19)
    val = sec.get("valuation") or {}
    if val.get("pe") or val.get("pb") or val.get("ev_ebitda"):
        peers = val.get("peers") or {}
        pp = peers.get("pe") or {}
        # who the P/E is of (R20): the profitable companies, with how many loss-makers have none and the profitable share
        pe_n, losses = (val.get("pe") or {}).get("n", 0), val.get("losses") or 0
        pop = val.get("n") or (pe_n + losses)
        pe_label = (f"P/E, the {pe_n} companies with one ({round(pe_n / pop * 100)}% of {pop}; {_n(losses, 'loss-maker')} with none)"
                    if losses and pe_n else "P/E (last four quarters)")
        rows = [[pe_label, _medn(val.get("pe"), None, _times), _span(val.get("pe"), _times), str((val.get("pe") or {}).get("n", "–")),
                 "–", _med(val.get("market_pe"), _times)]]
        if pp:          # the same basis as the headline: the companies with similar-size peers, against their peers' median (R17-010)
            rows.append(["P/E, companies with similar-size peers", _times(pp.get("theme")), f"{premium_words(pp['premium'])} peers"
                         if pp.get("premium") is not None else "", str(pp.get("n", "–")), _times(pp.get("peers")), "–"])
        rows += [r_ for r_ in (
                ["P/B", _med(val.get("pb"), _times), _span(val.get("pb"), _times), str((val.get("pb") or {}).get("n", "–")), "–", _med(val.get("market_pb"), _times)],
                ["EV/EBITDA (latest year)", _med(val.get("ev_ebitda"), _times), _span(val.get("ev_ebitda"), _times), str((val.get("ev_ebitda") or {}).get("n", "–")), "n/a", "n/a"])
                 if r_[1] != "–"]           # a measure no company has (EV/EBITDA for lenders) is no row (R18)
        for key, label, f in (("sales_3y", "Revenue growth, 3 years a year", _chg), ("roce", "ROCE", _pc)):
            if peers.get(key):
                rows.append([f"{label}, companies with similar-size peers", f(peers[key]["theme"]), "", str(peers[key]["n"]), f(peers[key]["peers"]), "–"])
        if pp.get("premium") is not None:
            msg = pe_peer_line(pp)
        elif val.get("pe") and val.get("market_pe"):
            msg = f"The theme's median P/E is {_times(val['pe']['median'])} against {_times(val['market_pe']['median'])} for all {val.get('market_n', 0):,} listed companies with one"
        else:
            msg = "Price against earnings, book value and EBITDA, the theme against companies of similar market value"
        if losses and pe_n:
            msg += f"; P/E of {pe_n} of the {pop} companies, {_n(losses, 'loss-maker')} with none"
        s = Slide("Valuation", msg, eyebrow=E())
        hist = val.get("history") or []
        lw = 7.0 if len(hist) >= 2 else CW
        notes = ["P/E: the price over the last four reported quarters' earnings per share. EV/EBITDA: market value plus debt less cash, over the latest "
                 "full year's EBITDA, so the two are on different periods. P/B: the price over book value per share.",
                 "Similar market value: listed companies worth between half and twice each company, in its own sector and outside the theme; where "
                 f"fewer than {PEER_MIN} have the figure, the theme's other companies of that sector count too, and with fewer still the whole market's. "
                 "The P/E set against them is the median P/E of the companies that have such peers beside the median of their peers' medians, and the gap "
                 "is the ratio of the two."]
        if val.get("losses"):
            notes.append(f"A loss-maker has no P/E: {_n(val['losses'], 'company', 'companies')} left out of the P/E median.")
        if val.get("ev_missing"):
            notes.append(f"EV/EBITDA is n/a for {_n(val['ev_missing'], 'company', 'companies')} where debt, cash or EBITDA isn't stored; the market's debt and "
                         "cash aren't kept, so it has no comparison.")
        if len(hist) < 2:
            notes.append("The theme's own P/E history builds forward from its page: it keeps the median once a week.")
        vhead, rows, vw, _ = drop_empty(["Measure", "Theme median", "Range", "Companies", "Similar market value", "All listed"], rows,
                                        [2.3, 1.2, 1.7, 1.1, 1.4, 1.1], keep=(0, 1))
        vh = table_height(vhead, rows, vw, lw)
        s.add("table", (M, TOP, lw, vh), head=vhead, rows=rows, widths=vw, tight=True)
        s.add("cards", (M, TOP + vh + 0.25, lw, BOT - TOP - vh - 0.25), cols=1, fill=True, size=12, items=[{"title": "How each is worked out", "lines": notes}])
        if len(hist) >= 2:
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
        msg = (f"In the quarter to {qt.get('quarter') or 'the latest'}, {qt.get('sales_up', 0)} of {len(bars)} companies reported higher revenue than a year "
               f"before; the median change is {_chg((qt.get('sales') or {}).get('median'))}")
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
        tiles = [tile("Debt to equity, median", de, lambda x: f"{x:.2f}x", bal.get("with_debt_equity") or 0),
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
    breadth = [(lbl, pr.get(k) or {}) for k, lbl in (("stage2", "In Stage 2 (advancing)"), ("supertrend_up", "Supertrend is up"),
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
        msg = (f"{st2.get('count', 0)} of {st2.get('n', 0)} companies are in Stage 2 (advancing); {nh.get('count', 0)} are within 5% of their 52-week high"
               if st2.get("n") else "Price change and breadth inside the theme")
        s = Slide("Price", msg, eyebrow=E())
        if ret:
            bench = prices.get("benchmark") or "Index"
            rows = [[lbl, _chg(((prices.get("median") or {}).get(k) or {}).get("median")), _chg((ret.get(k) or {}).get("theme")), _chg((ret.get(k) or {}).get("bench")),
                     str(((prices.get("median") or {}).get(k) or {}).get("n", "–"))] for k, lbl in (("1M", "1 month"), ("3M", "3 months"), ("1Y", "1 year"), ("3Y", "3 years"))]
            lw = 6.6
            s.add("table", (M, TOP, lw, 2.3), head=["Over", "Median company", "Theme, equal-weighted", bench, "Companies"], rows=rows, widths=[1.2, 1.4, 1.6, 1.3, 1.1])
            if breadth:
                s.add("table", (M, TOP + 2.55, lw, BOT - TOP - 2.55), head=["Companies that are", "Count", "Share"],
                      rows=[[lbl, f"{x['count']} of {x['n']}", f"{x['share']}%" if x.get("share") is not None else "–"] for lbl, x in breadth], widths=[3.6, 1.3, 1.0])
            line = prices.get("line")
            if line:
                s.add("lines", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP), title=f"The theme against {bench}, weekly, rebased to 100",
                      cats=[_day(w)[:6] for w in line["weeks"]], fmt="num1",
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

    # ownership, events and management report cards are per-company lists: on the theme's page, and their dated facts in "Worth a watch" (R19)


def build_theme(v: dict, pdf: bool = False) -> bytes:
    """A theme's deck, PowerPoint or (`pdf`) the same slides as a PDF."""
    slides, footer = theme_plan(v)
    return _render(slides, footer, f"{v.get('sector') or 'Theme'}: theme deep dive", pdf=pdf)
