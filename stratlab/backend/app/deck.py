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


def _pc(v, signed=False) -> str:
    return "–" if v is None else (f"{v:+.1f}%" if signed else f"{v:.1f}%")


def _chg(v) -> str:
    """A change as the theme page writes it: +12.3%, −4.0% (the real minus)."""
    return "–" if v is None else f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.1f}%"


def _times(v, dp: int = 1) -> str:
    return "–" if v is None else f"{v:.{dp}f}x"


def _pts(v) -> str:
    return "–" if v is None else f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.1f} pts"


def _med(s, f=lambda v: f"{v:.1f}%") -> str:
    return f(s["median"]) if s else "–"


def _span(s, f=lambda v: f"{v:.1f}%") -> str:
    return "–" if not s else f(s["min"]) if s["min"] == s["max"] else f"{f(s['min'])} to {f(s['max'])}"


def _day(iso) -> str:
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return str(iso or "–")


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


def fit_chars(text: str, size: float, width: float) -> str:
    """One line no wider than `width`: characters dropped from the end, with an ellipsis."""
    if _width(text, size) <= width:
        return text
    while text and _width(text + "…", size) > width:
        text = text[:-1]
    return text + "…"


ROW_MAX = 0.7                     # a table stretches its rows up to this to fill its box, so a short table doesn't sit in a half-empty slide


def _cell_text(v) -> str:
    return v["text"] if isinstance(v, dict) and "text" in v else ("" if v is None else str(v))


def table_layout(b: dict, w: float, h: float) -> dict:
    """Column widths, the font size (13 down to 11 pt, never smaller) and each row's height so the table fits its box; rows that still
    don't fit are left out (callers page their rows with table_pages, so none is). A row {"group": text} is a full-width heading row."""
    total = sum(b["widths"])
    widths = [w * x / total for x in b["widths"]]
    plain = [r for r in b["rows"] if not isinstance(r, dict)]
    numeric = b.get("numeric") or [all(_numeric(r[c]) for r in plain if not isinstance(r[c], dict)) for c in range(len(b["head"]))]
    strong = set(b.get("strong") or ())

    def heights_at(size):
        line = size * 1.3 / 72
        hs = [max(len(wrap(hd, size, cw - 0.2, True)) for hd, cw in zip(b["head"], widths)) * line + 0.14]
        for i, r in enumerate(b["rows"]):
            if isinstance(r, dict):
                hs.append(len(wrap(r["group"], size, w - 0.2, True)) * line + 0.16)
            else:
                hs.append(max(len(wrap(_cell_text(v), size, cw - 0.2, i in strong)) for v, cw in zip(r, widths)) * line + 0.12)
        return [max(0.32, x) for x in hs]

    def lines_at(size):
        return [round((x - 0.12) / (size * 1.3 / 72)) for x in heights_at(size)[1:]]

    base = lines_at(BODY_MIN)
    for size in (13, 12, 11):
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


def table_pages(head: list, rows: list, widths: list, w: float, h: float, most: int = 14, first: tuple | None = None, strong=()) -> list[list]:
    """`rows` cut into pages a table of `head` shows in full in a w x h box (the first page in `first`, (w, h), when it is smaller): as
    many rows a page as fit (at most `most`), so no row is ever left off a slide. A page that starts inside a group repeats the group's
    heading, "(continued)"; a page never ends on a heading."""
    pages, i, group = [], 0, None
    while i < len(rows):
        pw, ph = first if (first and not pages) else (w, h)
        lead = [{"group": f"{group} (continued)"}] if group and not isinstance(rows[i], dict) else []
        n = min(most, len(rows) - i)
        while n > 1 and len(table_layout({"head": head, "rows": lead + rows[i:i + n], "widths": widths, "numeric": [False] * len(head), "strong": strong},
                                         pw, ph)["rows"]) < n + len(lead):
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
        again = table_pages(head, rows, widths, w, h, even, first, strong)
        if len(again) == len(pages):
            return again
    return pages


FLOW_TEXT, FLOW_SUB, FLOW_PAD, FLOW_SEP = 12, BODY_MIN, 0.24, 0.28


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
        rows = sl.contents[:12]
        step = min(0.46, 5.2 / max(1, len(rows)))
        for i, (title, page) in enumerate(rows):
            yy = 1.72 + i * step
            self.line(x, yy, x + w, yy, DARK_LINE, 0.75)
            self.text(x, yy + (step - 0.26) / 2, w - 0.7, 0.28, [clip(title, 14, w - 0.7, 1)], 14, color=ON_DARK)
            self.text(x + w - 0.6, yy + (step - 0.26) / 2, 0.6, 0.28, [str(page)], 14, color=DARK_MUTED, align="right")
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
    return {"pct": (lambda v: f"{v:.1f}%", '0.0"%"'), "pct0": (lambda v: f"{v:g}%", '0"%"'),
            "chg": (lambda v: f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.1f}%", '+0.0"%";-0.0"%";0.0"%"'),
            "x": (lambda v: f"{v:.1f}x", '0.0"x"'), "num1": (lambda v: f"{v:,.1f}", "#,##0.0")}.get(kind, (lambda v: f"{v:,.0f}", "#,##0"))


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
MEMBER_SLIDES = 20                        # at most this many slides of companies; the page's CSV has every one (the deck says so)
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
            if base not in [t for t, _ in seen]:
                seen.append((base, j + 1))
        s.contents = seen


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
    shown = [x for x in layers if x.get("companies")]
    empty = [x["layer"] for x in layers if not x.get("companies")]
    sec = v.get("sections") or {}
    wide = set(v.get("company_wide") or [])
    med = v.get("median_ebitda")
    left_out: list[tuple] = []               # ("none" | "unread", what): what the page can show that this theme has none of, said once at the end
    slides: list[Slide] = []
    eb = lambda part: f"{sector} · {part}"  # noqa: E731
    size = sec.get("size") or {}

    def section(part: str, title: str, line: str):
        s = Slide(title, line, kind="section")
        s.part = part
        slides.append(s)

    def name_of(sym, nm):
        return f"{nm} (whole company)" if sym in wide else nm

    # 1. cover: the overview the AI wrote, the core, and the figures that frame the theme
    s = Slide(sector, f"{'US' if us else 'India (NSE and BSE)'} · Theme deep dive", dark=True)
    over = [sentences(v.get("summary") or "", 430) or "Every listed company in the theme, by layer, with the figures they report."]
    if v.get("core"):
        over.append(f"Everything converges on {v['core']}.")
    s.add("text", (M, 2.75, 9.6, 2.15), paras=over, size=17, floor=12, color=ON_DARK)
    s.add("stats", (M, 5.12, CW, 1.25), dark=True, items=[
        ("Companies", f"{total:,}"), ("Layers", str(len(shown))), ("Market value", cap(size.get("total_cap")) if size.get("total_cap") is not None else "–"),
        ("Median EBITDA margin", _pc(med)), ("AI additions confirmed", f"{confirmed} of {added}" if added else "None added"), ("Prices as of", asof_text)])
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
    msg = f"{_n(total, 'company', 'companies')} in {_n(len(shown), 'layer')}"
    if top3 is not None and size.get("total_cap") is not None:
        msg += f"; the three largest make up {_pc(top3)} of the theme's {cap(size['total_cap'])} market value"
    s = Slide("The theme at a glance", msg, eyebrow=eb("Overview"))
    etfs = v.get("etfs") or []
    lw = CW if not etfs else 7.4
    tiles = [("From the official industry list", f"{base_n:,}", "In the theme whatever the AI says")]
    if named:
        tiles.append(("Named in the theme's list", f"{named:,}", "The theme's own named companies"))
    tiles.append(("Added by the AI", f"{added:,}", f"{confirmed:,} confirmed by their own description" if added else "From other industries"))
    if p.get("pending"):
        tiles.append(("Still being checked", f"{p['pending']:,}", "Against their own description"))
    s.add("stats", (M, TOP, lw, 1.55), items=tiles)
    inds = p.get("industries") or []
    how = []
    if inds:
        by = {"words": ", matched by the theme's own words", "ai": ", picked by AI from the exchange's own list"}.get(p.get("industries_by"), "")
        how.append(f"Official industries{by}: {' · '.join(inds)}.")
    elif named:
        how.append("No official industry is this theme's core on its own, so its companies are the theme's named list and the ones the map names.")
    else:
        how.append("The theme's official industries are still being picked; until then the companies are the ones the map names." if p.get("industries_by") == "pending"
                   else "No official industry is this theme's core, so every company here is one the map names, checked against its own description.")
    how.append("The base is every listed company the exchange's own industry classification puts in the theme's industries. The AI sorts companies into "
               "layers and adds companies from other industries; an added company stays only while its own description doesn't show otherwise, marked "
               "confirmed when its words show the work.")
    if p.get("unclassified"):
        how.append(f"{p['unclassified']:,} US-listed companies have no industry on file yet, so they can't join a theme by industry until their SEC record is read.")
    s.add("cards", (M, TOP + 1.8, lw, BOT - TOP - 1.8), cols=1, fill=True, size=14, items=[{"title": "How the companies got in", "lines": how}])
    if etfs:
        rows = [[e.get("ticker") or "", e.get("name") or ""] for e in etfs]
        s.add("table", (M + lw + 0.35, TOP + 0.36, CW - lw - 0.35, BOT - TOP - 0.36), head=["Fund", "Name"], rows=rows[:12], widths=[1.2, 3.2], numeric=[False, False])
        s.add("text", (M + lw + 0.35, TOP, CW - lw - 0.35, 0.3), paras=["Funds that track the theme"], size=12, floor=12, bold=True, color=INK2)
    slides.append(s)

    # 3. the value chain: where the margin sits, a chart and the table
    rows_c = [r for r in chain.get("rows") or [] if r.get("n")]
    section("01", "The value chain", chain.get("line") or f"{_n(len(shown), 'layer')}, each with its companies' revenue and median margins.")
    if rows_c:
        head, widths = ["Layer", "Companies", "Revenue", "EBITDA margin", "Net margin", "ROCE"], [2.9, 1.25, 1.35, 1.2, 1.1, 1.0]
        rows = [[r["layer"], str(r["n"]), amt(r.get("revenue")), _pc(r.get("ebitda")), _pc(r.get("net")), _pc(r.get("roce"))] for r in rows_c]
        mark = {chain.get("highest"): UP, chain.get("lowest"): DOWN}
        charted = [r for r in rows_c if r.get("ebitda") is not None]
        chart = 2 <= len(charted) <= 14
        tw = 7.3 if chart else CW
        foot = [v.get("basis") or f"Each company's latest full year, in {unit}.", "Layer revenue: its companies added together; margins and ROCE: its median company."]
        if chain.get("highest"):
            foot.append("Highest median EBITDA margin in green, lowest in red.")
        if empty:
            foot.append(f"No listed company is shown for {', '.join(empty)}: none of the companies the map named has a description that shows it does the work.")
        fh = min(1.3, len(wrap(" ".join(foot), BODY_MIN, CW)) * _lh(BODY_MIN) + 0.05)
        th = BOT - TOP - fh - 0.2
        pages = table_pages(head, rows, widths, tw, th)
        for k, chunk in enumerate(pages):
            s = Slide("The value chain by layer" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      chain.get("line") or f"Each layer's companies, their revenue added together ({unit}), and the layer's median margins",
                      eyebrow=eb("The value chain"))
            s.add("table", (M, TOP, tw, th), head=head, rows=chunk, widths=widths,
                  colors={(i, 0): mark[r[0]] for i, r in enumerate(chunk) if r[0] in mark and r[0]})
            if chart and k == 0:
                s.add("hbars", (M + tw + 0.35, TOP, CW - tw - 0.35, th), title="Median EBITDA margin by layer", cats=[r["layer"] for r in charted],
                      vals=[r["ebitda"] for r in charted], colors=[mark.get(r["layer"], BLUE) for r in charted], fmt="pct")
            s.add("text", (M, BOT - fh, CW, fh), paras=[" ".join(foot)], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
    elif v.get("members_with_figures") == 0 or not shown:
        left_out.append(("none", "the value chain's figures (no company has stored figures)"))

    # 4. each layer: what it does, its companies' figures with the median and range, its margins by year, its operating updates
    biz = v.get("business") or {}
    biz_layers = {x.get("layer"): x.get("rows") or [] for x in biz.get("layers") or []}
    for i, layer in enumerate(layers):
        cos = layer.get("companies") or []
        if not cos:
            continue
        st = layer.get("stats") or {}
        title = f"Layer {i + 1} · {layer['layer']}"
        rows, strong = [], []
        lwide = set(layer.get("company_wide") or []) | {c["symbol"] for c in cos if c.get("company_wide")}
        for c in cos:
            rows.append([f"{c['name']} (whole company)" if c["symbol"] in lwide else c["name"], amt(c.get("revenue")), _pc(c.get("ebitda")), _pc(c.get("net")), _pc(c.get("roce")), c.get("year") or "–"])
        n_st = (st.get("ebitda") or st.get("net") or {}).get("n") or 0
        strong.append(len(rows))
        rows.append([f"Median of {_n(n_st, 'company', 'companies')}" + (" (company-wide figures)" if layer.get("stats_over") == "all" else ""), "",
                     _med(st.get("ebitda")), _med(st.get("net")), _med(st.get("roce")), ""])
        if n_st > 1:
            strong.append(len(rows))
            rows.append(["Range", "", _span(st.get("ebitda")), _span(st.get("net")), _span(st.get("roce")), ""])
        head, widths = ["Company", "Revenue", "EBITDA margin", "Net margin", "ROCE", "Year"], [2.6, 1.2, 1.55, 1.55, 1.45, 1.15]
        msg = layer.get("line") or (f"{_n(len(cos), 'company', 'companies')}, revenue {amt(layer.get('revenue'))} together; median EBITDA margin "
                                    f"{_med(st.get('ebitda'))}, net margin {_med(st.get('net'))}")
        desc = layer.get("description") or ""
        official = ("The theme's own named companies that the layers above don't place." if layer.get("basis") == "list" else
                    "Companies the exchange classifies under this industry that the layers above don't place.") if layer.get("official") else ""
        hist = layer.get("history") or {}
        bars = [c for c in cos if c.get("ebitda") is not None]
        chart = None
        if len(hist.get("years") or []) >= 2:
            chart = {"kind": "lines", "title": f"Margins by year, the {_n(hist.get('n') or 0, 'company', 'companies')} reporting every year",
                     "cats": hist["years"], "series": [("EBITDA margin", hist["ebitda"], BLUE), ("Net margin", hist["net"], ORANGE)], "fmt": "pct", "labels": True}
        elif len(bars) >= 2 or len([r for r in rows_c if r.get("ebitda") is not None]) < 2:
            top = sorted(bars, key=lambda c: -(c["ebitda"] or 0))[:8]
            chart = {"kind": "hbars", "title": "EBITDA margin by company", "cats": [c["name"] for c in top], "vals": [c["ebitda"] for c in top], "fmt": "pct",
                     "colors": [DOWN if c["ebitda"] < 0 else BLUE for c in top]} if len(bars) >= 2 else None
        else:                                    # one company: where the layer sits in the chain
            ch_rows = [r for r in rows_c if r.get("ebitda") is not None]
            chart = {"kind": "hbars", "title": "Median EBITDA margin: this layer against the others", "cats": [r["layer"] for r in ch_rows],
                     "vals": [r["ebitda"] for r in ch_rows], "fmt": "pct", "colors": [BLUE if r["layer"] == layer["layer"] else LINE2 for r in ch_rows]}
        card = {"title": "What this layer does", "lines": [desc] + ([official] if official else []), "note": AI_NOTE} if desc else \
            {"title": "Who is here", "lines": [official]} if official else None
        fnote = "(whole company): the company runs other businesses too, so its figures are the whole company's, not this layer's own business." \
            if any(c["symbol"] in lwide for c in cos) else ""
        fh = 0.48 if fnote else 0
        # the layout: what the layer does across the top, its table and its chart side by side below (a long table runs on; the chart goes
        # beside the last part when the table takes two slides, so neither slide is half empty)
        chh = min(1.75, card_height(card, CW)) if card else 0.0
        below = TOP + (chh + 0.25 if card else 0)
        tw = CW - 4.6 if chart else CW
        hA = BOT - fh - below
        pages = table_pages(head, rows, widths, CW, BOT - TOP - fh, first=(tw, hA), strong=strong)
        chart_on = 0
        if chart and len(pages) > 1:
            two = table_pages(head, rows, widths, tw, BOT - TOP - fh, first=(CW, hA), strong=strong)
            if len(two) == 2:
                pages, chart_on = two, 1
        done = 0
        for k, chunk in enumerate(pages):
            s = Slide(title + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=eb("The value chain"))
            idx = [j - done for j in strong if done <= j < done + len(chunk)]
            y0 = below if k == 0 else TOP
            if k == 0 and card:
                s.add("cards", (M, TOP, CW, chh), cols=1, fill=True, items=[card])
            with_chart = chart is not None and k == chart_on
            w0 = tw if (with_chart or (k == 0 and chart_on == 0 and chart)) else CW
            s.add("table", (M, y0, w0, BOT - fh - y0), head=head, rows=chunk, widths=widths, strong=idx)
            if with_chart:
                c = dict(chart)
                s.add(c.pop("kind"), (M + tw + 0.4, y0, CW - tw - 0.4, BOT - fh - y0), **c)
            if fnote:
                s.add("text", (M, BOT - 0.3, CW, 0.3), paras=[fnote], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            done += len(chunk) - sum(1 for r in chunk if isinstance(r, dict))
            slides.append(s)
        brows = biz_layers.get(layer["layer"]) or []
        if brows:
            _biz_slides(slides, f"{title}: operating figures", brows, eb("The value chain"))

    # 5. sub-themes and the companies that do them
    subs = v.get("subs") or []
    if subs:
        rows = []
        for sub in subs:
            rows.append({"group": f"{sub['name']}: {sub['detail']}" if sub.get("detail") else sub["name"]})
            if not sub.get("companies"):
                rows.append(["No listed company is shown for this sub-theme.", "", "", "", ""])
            for c in sub.get("companies") or []:
                rows.append([name_of(c["symbol"], c["name"]) if not c.get("company_wide") else f"{c['name']} (whole company)", f"“{c['what']}”" if c.get("what") else "Not yet confirmed from its own description",
                             cap(c.get("cap")), _chg(c.get("sales_1y")), _pc(c.get("ebitda"))])
        head, widths = ["Company", "What it does here, in its own words", "Market value", "Revenue growth", "EBITDA margin"], [2.7, 4.8, 1.4, 1.4, 1.3]
        pages = table_pages(head, rows, widths, CW, BOT - TOP - 0.4, most=16)
        with_co = sum(1 for sub in subs if sub.get("companies"))
        for k, chunk in enumerate(pages):
            s = Slide("Sub-themes and the companies that do them" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      f"{_n(len(subs), 'sub-theme')}, {with_co} with a listed company; each company is shown only where its own description says it does that work",
                      eyebrow=eb("The value chain"))
            s.add("table", (M, TOP, CW, BOT - TOP - 0.4), head=head, rows=chunk, widths=widths, numeric=[False, False, True, True, True])
            s.add("text", (M, BOT - 0.32, CW, 0.32), paras=["Each sub-theme's description is written by AI from general knowledge, with no figures. Revenue growth: "
                                                            "the latest full year against the year before."], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
        for sub in subs:
            rows_b = (biz.get("subs") or [])
            hit = next((x for x in rows_b if x.get("name") == sub["name"]), None)
            if hit and hit.get("rows"):
                _biz_slides(slides, f"{sub['name']}: operating figures", hit["rows"], eb("The value chain"))

    # 6. the companies: every one in its own words and how it got in, then every one's figures
    count_line = (f"{_n(total, 'company', 'companies')}: {base_n:,} from the official industry list, " + (f"{named:,} named in the theme's list, " if named else "")
                  + f"{added:,} added" + (f" ({confirmed:,} confirmed from {'its' if added == 1 else 'their'} own description)" if added else "") + ".")
    section("02", "The companies", count_line)
    rows, grp = [], None
    for m in members:
        if m.get("layer") != grp:
            grp = m.get("layer")
            rows.append({"group": (grp or "–") + (" · official industry" if m.get("official") else "")})
        rows.append([f"{m['name']} ({m['symbol']})", m.get("industry") or "–", cap(m.get("cap")),
                     f"“{m['what']}”" if m.get("what") else "Not yet confirmed from its own description", m["by"]])
    pages = table_pages(MEMBER_HEAD, rows, MEMBER_WIDTHS, CW, BOT - TOP - 0.35, most=16)
    shown_p = pages[:MEMBER_SLIDES]
    left = sum(1 for pg in pages[MEMBER_SLIDES:] for r in pg if not isinstance(r, dict))
    for k, chunk in enumerate(shown_p):
        s = Slide("Every company in this theme" + (f" ({k + 1} of {len(shown_p)})" if len(shown_p) > 1 else ""), count_line, eyebrow=eb("The companies"))
        tint = {}
        plain = [r for r in chunk if not isinstance(r, dict)]
        for j, r in enumerate(plain):
            if r[4].startswith("Added"):
                tint[(j, 4)] = UP if r[4].startswith("Added, confirmed") else ORANGE
        s.add("table", (M, TOP, CW, BOT - TOP - 0.35), head=MEMBER_HEAD, rows=chunk, widths=MEMBER_WIDTHS, colors=_group_keys(chunk, tint),
              numeric=[False, False, True, False, False])
        note = "Market value at the last close. Grouped by layer, as the page lists them."
        if k == len(shown_p) - 1 and left:
            note = f"{left:,} more companies are in the CSV on the theme's page (Download, then CSV). " + note
        s.add("text", (M, BOT - 0.28, CW, 0.28), paras=[note], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)
    if not members:
        s = Slide("Every company in this theme", "No company has been placed in this theme yet", eyebrow=eb("The companies"))
        s.add("text", (M, TOP, CW, 0.8), paras=["Try a more specific theme on the Themes page, then download the deck again."], size=16, floor=12, color=MUTED)
        slides.append(s)

    lead = sorted(sec.get("leaders") or [], key=lambda x: -(x.get("cap") or 0))
    if lead:
        prices = v.get("prices") or {}
        r1y = {c["symbol"]: (c.get("ret") or {}).get("1Y") for c in prices.get("companies") or []}
        head = ["Company", "Market value", "Revenue growth", "EBITDA margin", "Net margin", "ROCE", "P/E", "P/B", "EV/EBITDA"] + (["Price, 1 year"] if r1y else [])
        widths = [2.9, 1.4, 1.3, 1.2, 1.1, 0.9, 0.9, 0.9, 1.1] + ([1.1] if r1y else [])
        rows = [[name_of(x["symbol"], x["name"]), cap(x.get("cap")), _chg(x.get("sales_1y")), _pc(x.get("ebitda")), _pc(x.get("net")), _pc(x.get("roce")),
                 _times(x.get("pe")), _times(x.get("pb")), _times(x.get("ev_ebitda"))] + ([_chg(r1y.get(x["symbol"]))] if r1y else []) for x in lead]
        em = [x["ebitda"] for x in lead if x.get("ebitda") is not None]
        msg = f"{lead[0]['name']} is the largest at {cap(lead[0].get('cap'))}" + (f"; EBITDA margins run from {_pc(min(em))} to {_pc(max(em))}" if len(em) > 1 else "")
        pages = table_pages(head, rows, widths, CW, BOT - TOP - 0.35, most=16)
        for k, chunk in enumerate(pages[:MEMBER_SLIDES]):
            s = Slide("Every company's figures" + (f" ({k + 1} of {len(pages[:MEMBER_SLIDES])})" if len(pages) > 1 else ""), msg, eyebrow=eb("The companies"))
            s.add("table", (M, TOP, CW, BOT - TOP - 0.35), head=head, rows=chunk, widths=widths)
            s.add("text", (M, BOT - 0.28, CW, 0.28), paras=[f"Largest first. Revenue growth and margins: each company's latest full year; P/E on the last four quarters' "
                                                            f"earnings.{' (whole company): whole-company figures.' if wide else ''}"], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)

    # 7. tailwinds and risks with their checked sources, the latest headlines, the new listings
    tw_, rk_ = v.get("tailwinds") or [], v.get("risks") or []
    claims = [("Tailwind", c) for c in tw_] + [("Risk", c) for c in rk_]
    news, listings = v.get("news"), v.get("listings")
    n_checked = sum(1 for _, c in claims if c.get("status") == "current" and c.get("source"))
    section("03", "Tailwinds, risks and news", f"{_n(len(tw_), 'tailwind')} and {_n(len(rk_), 'risk')}; {n_checked} checked against a dated headline from the "
            f"last 18 months." if claims else "The latest headlines and new listings for the theme's companies.")
    if claims:
        items = []
        for kind, c in claims:
            src = c.get("source") if c.get("status") == "current" else None
            tags = [(kind, UP if kind == "Tailwind" else DOWN, UP_SOFT if kind == "Tailwind" else DOWN_SOFT),
                    ("Checked", INK2, CHIP) if src else ("General background", MUTED, CHIP)]
            items.append({"tags": tags, "text": c.get("text") or "", "url": (src or {}).get("url") or None,
                          "sub": f"{src['headline']} · {_day(src.get('at'))} · {src.get('outlet') or ''}".rstrip(" ·") if src else None})
        box = (M, TOP, CW, BOT - TOP - 0.4)
        cols = 2
        pages = flow_pages(items, box, 2)
        if len(pages) > 1 and len(flow_pages(items, box, 3)) < len(pages):
            cols, pages = 3, flow_pages(items, box, 3)
        for k, chunk in enumerate(pages):
            s = Slide("Tailwinds and risks" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      f"{n_checked} of {len(claims)} checked: a headline dated within the last 18 months shows it is still current", eyebrow=eb("Tailwinds and risks"))
            s.add("flow", box, cols=cols, items=chunk)
            s.add("text", (M, BOT - 0.3, CW, 0.3), paras=["General background: written by AI from general knowledge, with no figures; no dated headline shows it is "
                                                          "still current. A claim a headline showed had ended is left out."], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
            slides.append(s)
    else:
        left_out.append(("none", "tailwinds and risks"))
    if news:
        rows = [[_day(x.get("at")), {"text": x.get("headline") or "", "url": x.get("url")} if x.get("url") else x.get("headline") or "",
                 x.get("company") or "The theme", x.get("source") or ""] for x in news]
        pages = table_pages(["Date", "Headline", "Company", "Source"], rows, [1.3, 6.6, 2.4, 1.8], CW, BOT - TOP, most=12)
        for k, chunk in enumerate(pages):
            s = Slide("Latest on this theme" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      f"The {len(news)} most recent dated headlines and exchange filings for the theme's companies, as published; no view is added",
                      eyebrow=eb("Latest"))
            s.add("table", (M, TOP, CW, BOT - TOP), head=["Date", "Headline", "Company", "Source"], rows=chunk, widths=[1.3, 6.6, 2.4, 1.8], numeric=[False] * 4)
            slides.append(s)
    elif news is None:
        left_out.append(("unread", "the latest headlines"))
    else:
        left_out.append(("none", "recent headlines or filings"))
    if listings:
        stage = {"upcoming": "Coming", "open": "Open for bids", "closed": "Awaiting listing", "listed": "Listed"}
        rows = [[x.get("name") or "", stage.get(x.get("stage"), x.get("stage") or ""),
                 _day(x.get("listing") or x.get("close")) if x.get("stage") in ("listed", "closed") and (x.get("listing") or x.get("close")) else _day(x["open"]) if x.get("open") else "–",
                 ", ".join(x.get("groups") or []), f"“{x.get('what') or ''}”"] for x in listings]
        head, widths = ["Company", "Stage", "Date", "In the theme as", "In its own words"], [2.6, 1.5, 1.3, 2.6, 4.2]
        for k, chunk in enumerate(pages := table_pages(head, rows, widths, CW, BOT - TOP)):
            s = Slide("New listings in the theme" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                      f"{_n(len(listings), 'issue')} open, coming or listed in the last year whose own offer says it does a layer's or sub-theme's work",
                      eyebrow=eb("New listings"))
            s.add("table", (M, TOP, CW, BOT - TOP), head=head, rows=chunk, widths=widths, numeric=[False] * 5)
            slides.append(s)
    elif listings is None:
        left_out.append(("unread", "new listings"))
    else:
        left_out.append(("none", "new listings that do the theme's work"))

    # 8. the theme in numbers
    if sec and (v.get("members_with_figures") or shown):
        section("04", "The theme in numbers", f"Reported figures from each company's stored page{', prices to ' + asof_text if asof else ''}; each slide says what it is on.")
        _numbers(slides, v, sec, cap, eb, left_out, name_of)

    # 9. how to read it, and what this theme has none of
    who = [f"{_n(total, 'company', 'companies')} in all.", f"{base_n:,} from the exchange's official industries: in the theme whatever the AI says."]
    if named:
        who.append(f"{named:,} named in the theme's own list.")
    who.append(f"{added:,} added by the AI from other industries." if added else "None added by the AI from other industries.")
    sure = [f"{confirmed:,} of the {added:,} added are confirmed: their own description shows they do the work." if added else
            "Nothing to confirm: every company is from the official industries or the theme's list."]
    if added - confirmed > 0:
        sure.append(f"{added - confirmed:,} not yet confirmed: kept while their own description doesn't show otherwise.")
    if p.get("pending"):
        sure.append(f"{p['pending']:,} still being checked against their own description when this deck was made.")
    if p.get("timed_out"):
        sure.append(f"{p['timed_out']:,} couldn't be checked just now; the check runs again later.")
    figs = v.get("figures") or {}
    read = ["Every figure's year and basis are said under the value chain by layer.", "Market value: price times shares in issue at the last close."]
    if figs.get("of") and figs.get("shown") and figs["of"] > figs["shown"]:
        read.append(f"Figures are worked out for {figs['shown']:,} of the theme's {figs['of']:,} companies: every one the map names, then the largest of the rest.")
    if wide:
        read.append("(whole company): a company that runs other businesses too; its figures are the whole company's.")
    none_ = [t for k, t in left_out if k == "none"]
    unread = [t for k, t in left_out if k == "unread"]
    lo_text = ([f"Nothing to show for this theme's companies yet: {'; '.join(none_)}."] if none_ else []) + \
        ([f"Not read when this deck was made, so on the theme's page only: {', '.join(unread)}."] if unread else []) + ["What the AI wrote: the overview, what each layer and sub-theme does and the general-background claims, from general knowledge "
                          "with no figures."]
    groups = [[{"title": "Who is in it", "lines": who}, {"title": "Confirmed or not yet", "lines": sure}, {"title": "Reading the figures", "lines": [x for x in read if x]}],
              [{"title": "Not in this deck, and what the AI wrote", "lines": lo_text}]]
    room = BOT - TOP - 0.38
    for tsize in (13, 12, BODY_MIN):
        pages, cur, used = [], [], 0.0
        for g in groups:
            cw = (CW - 0.25 * (len(g) - 1)) / len(g)
            gh = max(card_height(it, cw, True, tsize) for it in g)
            if cur and used + gh > room:
                pages.append(cur)
                cur, used = [], 0.0
            cur.append((g, min(gh, room)))
            used += min(gh, room) + 0.25
        pages.append(cur)
        if len(pages) == 1:
            break
    for k, rows_ in enumerate(pages):
        s = Slide("How to read this deck" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                  "Who is in the theme and how each company got there, what the figures are, and what the AI wrote", eyebrow=eb("Notes"))
        y = TOP
        for g, gh in rows_:
            s.add("cards", (M, y, CW, gh), cols=len(g), bullets=True, items=g, size=tsize)
            y += gh + 0.25
        s.add("text", (M, BOT - 0.3, CW, 0.3), paras=[THEME_DISCLAIMER + " The AI's layers and additions can be wrong: check a company's own description "
                                                      "before relying on a placement."], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)
    _sections(sector, slides)
    return slides, footer


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


def _biz_slides(slides: list, title: str, rows: list, eyebrow: str) -> None:
    """The operating figures companies file between results (the page's business-update tables), each with its filing."""
    head = ["Company", "Period", "Latest", "Previous", "Year ago", "On previous", "On the year", "Filing"]
    widths = [3.0, 1.2, 1.5, 1.5, 1.5, 1.2, 1.2, 1.6]
    out = [[f"{r['name']}: {r.get('metric') or ''}".rstrip(": "), _period(r.get("period"), r.get("span") or "month"), _bizval(r.get("value"), r.get("unit")),
            _bizval(r.get("prev"), r.get("unit")), _bizval(r.get("year_ago"), r.get("unit")), _bizchg(r.get("change_prev"), r.get("unit")),
            _bizchg(r.get("change_year"), r.get("unit")),
            {"text": _day(r.get("filed")) + (f" · {r['exchange']}" if r.get("exchange") else ""), "url": r["url"]} if r.get("url") else _day(r.get("filed"))] for r in rows]
    pages = table_pages(head, out, widths, CW, BOT - TOP)
    for k, chunk in enumerate(pages):
        s = Slide(title + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""),
                  "Monthly or quarterly figures the companies filed with the exchange between results, as filed; changes are plain changes, not a view",
                  eyebrow=eyebrow)
        s.add("table", (M, TOP, CW, BOT - TOP), head=head, rows=chunk, widths=widths)
        slides.append(s)


def _numbers(slides: list, v: dict, sec: dict, cap, eb, left_out: list, name_of) -> None:
    """The theme in numbers, a slide for each of the page's cards (NumbersCards): a chart where figures compare, the table beside it."""
    E = lambda: eb("The theme in numbers")  # noqa: E731
    size = sec.get("size") or {}
    big = size.get("biggest") or []
    if big:
        msg = (f"The three largest make up {_pc(size['top3_share'])} of the theme's market value of {cap(size.get('total_cap'))}" if size.get("top3_share") is not None
               else f"The theme's companies are worth {cap(size.get('total_cap'))} together")
        s = Slide("Size and shape", msg, eyebrow=E())
        rows = [[name_of(x["symbol"], x["name"]), cap(x.get("cap")), _pc(x.get("share"))] for x in big]
        rows.append([f"All {size.get('companies', 0):,} listed companies ({size.get('with_value', 0):,} with a market value)", cap(size.get("total_cap")), "100.0%"])
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
        vs = [["EBITDA margin", _med(meds.get("ebitda")), str((meds.get("ebitda") or {}).get("n", "–")), _med(mk.get("opm"))],
              ["Net margin", _med(meds.get("net")), str((meds.get("net") or {}).get("n", "–")), _med(mk.get("net_margin"))],
              ["ROCE", _med(meds.get("roce")), str((meds.get("roce") or {}).get("n", "–")), _med(mk.get("roce"))],
              ["Revenue growth, 3 years a year", _med(gmed.get("revenue_3y"), _chg), str((gmed.get("revenue_3y") or {}).get("n", "–")), _med(mk.get("sales_cagr_3y"), _chg)]]
        r1 = (agg.get("revenue_1y") or {}).get("value")
        msg = (f"Revenue together grew {_chg(r1)} in the latest year" if r1 is not None else "Growth and margins of the theme's companies")
        if meds.get("ebitda") and mk.get("opm"):
            msg += f"; the median company's EBITDA margin is {_med(meds['ebitda'])} against {_med(mk['opm'])} for all listed companies"
        s = Slide("Growth and profitability", msg, eyebrow=E())
        lw = 7.0
        gh_ = ["Measure", "Together, 1 year", "Together, 3 years a year", "Median company, 1 year", "Median company, 3 years a year"]
        gw = [1.5, 1.3, 1.5, 1.4, 1.6]
        g_h = table_height(gh_, grow, gw, lw)
        s.add("text", (M, TOP, lw, 0.3), paras=["Revenue and profit growth"], size=12, floor=12, bold=True, color=INK2)
        s.add("table", (M, TOP + 0.36, lw, g_h), head=gh_, rows=grow, widths=gw, tight=True)
        y2 = TOP + 0.36 + g_h + 0.22
        s.add("text", (M, y2, lw, 0.3), paras=["Margins and returns: the theme against all listed companies"], size=12, floor=12, bold=True, color=INK2)
        s.add("table", (M, y2 + 0.36, lw, BOT - y2 - 0.36 - 0.85), head=["Median", "Theme", "Companies", "All listed"], rows=vs, widths=[2.8, 1.3, 1.3, 1.3])
        note = ("Together: the companies' figures added up, for those that report both ends of the period. Median: the middle company's own rate. "
                "Companies that run other businesses too are left out.")
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

    mg = sec.get("margins")
    if mg and len(mg.get("years") or []) >= 2:
        ys, e, nt = mg["years"], mg.get("ebitda") or [], mg.get("net") or []
        pe = [(y, x) for y, x in zip(ys, e) if x is not None]
        msg = (f"The aggregate EBITDA margin of the {_n(mg.get('n') or 0, 'company', 'companies')} reporting every year went from {_pc(pe[0][1])} in {pe[0][0]} "
               f"to {_pc(pe[-1][1])} in {pe[-1][0]}" if len(pe) >= 2 else "Margins of the companies that report every year")
        s = Slide("Margins over time", msg, eyebrow=E())
        lw = 7.6
        s.add("lines", (M, TOP, lw, BOT - TOP), cats=ys, series=[("EBITDA margin", e, BLUE), ("Net margin", nt, ORANGE)], fmt="pct", labels=len(ys) <= 8)
        s.add("table", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP), head=["Year", "EBITDA margin", "Net margin"],
              rows=[[y, _pc(a), _pc(b_)] for y, a, b_ in zip(ys, e, nt)], widths=[1.4, 1.5, 1.4])
        slides.append(s)
    else:
        left_out.append(("none", "margins over time (too few companies report the same years)"))

    val = sec.get("valuation") or {}
    if val.get("pe") or val.get("pb") or val.get("ev_ebitda"):
        rows = [["P/E", _med(val.get("pe"), _times), _span(val.get("pe"), _times), str((val.get("pe") or {}).get("n", "–")), _med(val.get("market_pe"), _times)],
                ["P/B", _med(val.get("pb"), _times), _span(val.get("pb"), _times), str((val.get("pb") or {}).get("n", "–")), _med(val.get("market_pb"), _times)],
                ["EV/EBITDA", _med(val.get("ev_ebitda"), _times), _span(val.get("ev_ebitda"), _times), str((val.get("ev_ebitda") or {}).get("n", "–")), "–"]]
        msg = (f"The theme's median P/E is {_times(val['pe']['median'])} against {_times(val['market_pe']['median'])} for all {val.get('market_n', 0):,} listed companies with one"
               if val.get("pe") and val.get("market_pe") else "Price against earnings, book value and EBITDA, the theme against all listed companies")
        s = Slide("Valuation", msg, eyebrow=E())
        hist = val.get("history") or []
        lw = 7.0 if len(hist) >= 2 else CW
        notes = ["P/E: the price over the last four reported quarters' earnings per share. P/B: the price over book value per share. EV/EBITDA: market value "
                 "plus debt less cash, over the latest year's EBITDA. Each is left out for a company where a figure it needs is missing, and for a loss."]
        if val.get("ev_missing"):
            notes.append(f"EV/EBITDA is n/a for {_n(val['ev_missing'], 'company', 'companies')} where debt, cash or EBITDA isn't stored; the all-listed comparison is not worked out for it.")
        if len(hist) < 2:
            notes.append("The theme's own P/E history builds forward from its page: it keeps the median once a week.")
        s.add("table", (M, TOP, lw, 2.2), head=["Measure", "Theme median", "Range", "Companies", "All listed, median"], rows=rows, widths=[1.3, 1.3, 1.9, 1.1, 1.5])
        s.add("cards", (M, TOP + 2.45, lw, BOT - TOP - 2.45), cols=1, fill=True, size=13, items=[{"title": "How each is worked out", "lines": notes}])
        if len(hist) >= 2:
            h = hist[-26:]
            s.add("lines", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP), title=f"The theme's median P/E, weekly ({_day(h[0]['d'])} to {_day(h[-1]['d'])})",
                  cats=[_day(x["d"])[:6] for x in h], series=[("Median P/E", [x["pe"] for x in h], BLUE)], fmt="x", labels=len(h) <= 8)
        slides.append(s)

    qt = sec.get("quarter") or {}
    qc = qt.get("companies") or []
    if qc:
        rows = [[name_of(x["symbol"], x["name"]), x.get("of") or "–", _chg(x.get("sales")), _chg(x.get("profit"))] for x in qc]
        foot = [f"{qt.get('sales_up', 0)} up, {qt.get('sales_down', 0)} down on revenue; {qt.get('profit_up', 0)} up, {qt.get('profit_down', 0)} down on profit",
                "Median", _chg((qt.get("sales") or {}).get("median")), _chg((qt.get("profit") or {}).get("median"))]
        head, widths = ["Company", "Quarter", "Revenue", "Net profit"], [3.4, 1.2, 1.2, 1.2]
        bars = [x for x in qc if x.get("sales") is not None]
        chart = 2 <= len(bars) and len(qc) <= 14
        tw = 7.0 if chart else CW
        pages = table_pages(head, rows + [foot], widths, tw, BOT - TOP, most=15, strong=[len(rows)])
        msg = (f"{qt.get('sales_up', 0)} of {len(bars)} companies reported higher revenue than in the same quarter a year before; the median change is "
               f"{_chg((qt.get('sales') or {}).get('median'))}")
        done = 0
        for k, chunk in enumerate(pages):
            s = Slide("The latest quarter against a year earlier" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=E())
            s.add("table", (M, TOP, tw, BOT - TOP), head=head, rows=chunk, widths=widths, strong=[len(rows) - done] if done + len(chunk) > len(rows) else [])
            if chart and k == 0:
                srt = sorted(bars, key=lambda x: -x["sales"])
                s.add("hbars", (M + tw + 0.4, TOP, CW - tw - 0.4, BOT - TOP), title="Revenue against the same quarter a year before", cats=[x["name"] for x in srt],
                      vals=[x["sales"] for x in srt], fmt="chg", colors=[UP if x["sales"] >= 0 else DOWN for x in srt])
            done += len(chunk)
            slides.append(s)
    else:
        left_out.append(("none", "a latest quarter against a year before"))

    bal = sec.get("balance") or {}
    if bal.get("debt_equity") or bal.get("interest_cover") or bal.get("cfo_to_profit"):
        de, ic, cf = bal.get("debt_equity"), bal.get("interest_cover"), bal.get("cfo_to_profit")
        def tile(label, st, f, n):                # a figure no company has is said in words, never "0 companies"
            return (label, _med(st, f), f"Range {_span(st, f)} · {_n(n, 'company', 'companies')}" if st and n else "No company has the figures it needs")
        tiles = [tile("Debt to equity, median", de, lambda x: f"{x:.2f}x", bal.get("with_debt_equity") or 0),
                 tile("Interest cover, median", ic, _times, (ic or {}).get("n") or 0),
                 tile("Cash from operations over net profit, median", cf, lambda x: _times(x, 2), bal.get("cfo_n") or 0)]
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
    if breadth or ret:
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
            s.add("text", (M, BOT - 0.36, CW, 0.36), paras=["Price changes against the index are worked out from daily closes on the theme's page; they weren't read when "
                                                            "this deck was made."], size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)

    own = sec.get("ownership") or {}
    hold = own.get("holdings") or []
    buys = [["Promoter or insider bought", name_of(x["symbol"], x["name"]), _day(x.get("at")), "–"] for x in own.get("insider_buys") or []]
    buys += [[x.get("label") or "", x["name"], _day(x.get("at")), {"text": "Open", "url": x["url"]} if x.get("url") else "–"] for x in own.get("pledges") or []]
    if hold or buys:
        msg = (f"Promoters' stake rose at {own.get('promoter_up', 0)} and fell at {own.get('promoter_down', 0)} of the {len(hold)} companies with a filing stored"
               if hold else "Promoter and insider purchases and pledges in the last 90 days")
        rows = [[name_of(x["symbol"], x["name"]), _pc(x.get("promoter")), _pts(x.get("promoter_change")), _pc(x.get("institutions")), _pts(x.get("institutions_change")),
                 x.get("quarter") or "–"] for x in hold]
        head, widths = ["Company", "Promoters", "Change", "Named institutions", "Change", "Quarter"], [3.2, 1.3, 1.2, 1.6, 1.2, 1.2]
        pages = table_pages(head, rows, widths, CW, BOT - TOP - (2.0 if buys else 0)) if rows else [[]]
        for k, chunk in enumerate(pages):
            s = Slide("Ownership" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=E())
            y = TOP
            if chunk:
                s.add("table", (M, TOP, CW, BOT - TOP - (2.0 if buys and k == len(pages) - 1 else 0)), head=head, rows=chunk, widths=widths)
                y = BOT - 1.75
            if buys and k == len(pages) - 1:
                s.add("table", (M, y, CW, BOT - y), head=["What", "Company", "Filed", "Filing"], rows=buys[:6], widths=[4.0, 4.0, 1.6, 1.4], numeric=[False] * 4)
            slides.append(s)
    else:
        left_out.append(("none", "shareholding filings, promoter purchases or pledges"))

    ev = sec.get("events") or {}
    rows = [[_day(x.get("date")), name_of(x["symbol"], x["name"]), "Results due", x.get("purpose") or "–", "–"] for x in ev.get("results_due") or []]
    rows += [[_day(x.get("date")), name_of(x["symbol"], x["name"]), "Results filed", " · ".join(f"{n['label']} {n['value']}" for n in x.get("numbers") or []) or "–",
              {"text": "Open", "url": x["url"]} if x.get("url") else "–"] for x in ev.get("results_filed") or []]
    rows += [[_day(x.get("date")), name_of(x["symbol"], x["name"]), "Ex-date", f"{x.get('label')}: {x['text']}" if x.get("text") else x.get("label") or "", "–"]
             for x in ev.get("actions") or []]
    rows += [[_day(x.get("at")), name_of(x["symbol"], x["name"]), "Red-flag filing", x.get("label") or "", {"text": "Open", "url": x["url"]} if x.get("url") else "–"]
             for x in own.get("red_flags") or []]
    if rows:
        msg = (f"{len(ev.get('results_due') or [])} results due in the next four weeks, {len(ev.get('results_filed') or [])} filed in the last 30 days, "
               f"{_n(len(ev.get('actions') or []), 'corporate action')} and {_n(len(own.get('red_flags') or []), 'red-flag filing')} in the last 90 days")
        head, widths = ["Date", "Company", "Event", "Detail", "Filing"], [1.3, 3.0, 1.6, 5.0, 1.0]
        pages = table_pages(head, rows, widths, CW, BOT - TOP)
        for k, chunk in enumerate(pages):
            s = Slide("Events" + (f" ({k + 1} of {len(pages)})" if len(pages) > 1 else ""), msg, eyebrow=E())
            s.add("table", (M, TOP, CW, BOT - TOP), head=head, rows=chunk, widths=widths, numeric=[False] * 5)
            slides.append(s)
    else:
        left_out.append(("none", "results dates, results filings, corporate actions or red-flag filings in the windows the page covers"))

    mgm = sec.get("management") or {}
    mc = mgm.get("companies") or []
    if mc:
        rows = [[name_of(x["symbol"], x["name"]), str(x.get("met", 0)), str(x.get("missed", 0))] for x in mc]
        rows.append([f"{_n(mgm.get('with_card', 0), 'company', 'companies')} with a stored report card", str(mgm.get("met", 0)), str(mgm.get("missed", 0))])
        s = Slide("Management report cards", f"{mgm.get('met', 0)} targets met and {mgm.get('missed', 0)} missed across the theme's stored report cards", eyebrow=E())
        lw = 6.4
        pages = table_pages(["Company", "Targets met", "Missed"], rows, [3.6, 1.4, 1.4], lw, BOT - TOP - 0.3, strong=[len(rows) - 1])
        s.add("table", (M, TOP, lw, BOT - TOP - 0.3), head=["Company", "Targets met", "Missed"], rows=pages[0], widths=[3.6, 1.4, 1.4],
              strong=[len(rows) - 1] if len(pages) == 1 else [])
        top = mc[:10]
        s.add("columns", (M + lw + 0.4, TOP, CW - lw - 0.4, BOT - TOP - 0.3), cats=[clip(x["name"], 10, 1.2, 1) for x in top], fmt="num",
              series=[("Met", [x.get("met", 0) for x in top], UP), ("Missed", [x.get("missed", 0) for x in top], DOWN)])
        s.add("text", (M, BOT - 0.25, CW, 0.25), paras=["What management said it would deliver on earnings calls, set against the reported years; only annual targets are settled."],
              size=BODY_MIN, floor=BODY_MIN, color=MUTED)
        slides.append(s)
    else:
        left_out.append(("none", "management report cards"))


def build_theme(v: dict, pdf: bool = False) -> bytes:
    """A theme's deck, PowerPoint or (`pdf`) the same slides as a PDF."""
    slides, footer = theme_plan(v)
    return _render(slides, footer, f"{v.get('sector') or 'Theme'}: theme deep dive", pdf=pdf)
