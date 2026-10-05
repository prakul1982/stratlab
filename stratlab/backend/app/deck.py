"""A company deck from the deep dive, as PowerPoint or PDF: numbers, business model, plans, the management report card
and the investor checklist, each slide citing where it came from. Built from what the page already has; no extra AI.

Each slide is described once (a title, a subtitle and positioned blocks: text, stat tiles, charts, tables, cards) and
drawn twice: by python-pptx for PowerPoint and by reportlab for PDF, so the two files show the same slides. Text is
measured with the PDF font (wider than the PowerPoint one), so what fits in the PDF fits in PowerPoint too."""
import io
import os
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from .deepdive import money, scale_for

# Palette: deep navy carries the deck, teal is the one accent, amber marks what went wrong.
NAVY, NAVY2, TEAL, AMBER = "0F1E3D", "1C2F57", "0E7C7B", "B45309"
INK, SLATE, MIST, RULE, WHITE, ICE = "111827", "5B6475", "F1F4F8", "DDE3EA", "FFFFFF", "C9D6EA"
W_IN, H_IN = 13.333, 7.5
M = 0.6                                   # side margin, inches
DISCLAIMER = "Reported figures and the company's own words. Not investment advice."
STATE = {"pass": ("Pass", TEAL), "watch": ("Watch", SLATE), "fail": ("Fail", AMBER), "na": ("No data", SLATE),
         "met": ("Met", TEAL), "missed": ("Missed", AMBER), "pending": ("Not due yet", SLATE), "unchecked": ("Can't check", SLATE)}

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_fonts_ready = False


def _fonts():
    """The PDF fonts (DejaVu: has the rupee sign), registered once."""
    global _fonts_ready
    if _fonts_ready:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont("Body", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("Body-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Head", os.path.join(FONT_DIR, "DejaVuSerif.ttf")))
    _fonts_ready = True


def _width(text: str, size: float, bold: bool = False, head: bool = False) -> float:
    """Width in inches of one line of text in the PDF font."""
    from reportlab.pdfbase import pdfmetrics
    _fonts()
    return pdfmetrics.stringWidth(text, "Head" if head else "Body-Bold" if bold else "Body", size) / 72


def wrap(text: str, size: float, width: float, bold: bool = False, head: bool = False) -> list[str]:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        nxt = f"{cur} {w}".strip()
        if cur and _width(nxt, size, bold, head) > width:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines or [""]


def fit(paras: list[str], width: float, height: float, size: float, floor: float, bold=False, gap=0.35) -> float:
    """The largest size, from `size` down to `floor`, at which the paragraphs fit the box (line height 1.25)."""
    s = size
    while s > floor:
        lines = sum(len(wrap(p, s, width, bold)) for p in paras)
        if lines * s * 1.25 / 72 + (len(paras) - 1) * gap * s / 72 <= height:
            return s
        s -= 0.5
    return floor


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


def clip(text: str, size: float, width: float, lines: int, bold=False) -> str:
    """At most `lines` lines of text at this size and width, ending in an ellipsis when cut."""
    got = wrap(text, size, width, bold)
    if len(got) <= lines:
        return str(text)
    out = " ".join(got[:lines])
    while out and _width(out.split(" ")[-1] + "…", size, bold) > 0 and len(wrap(out + "…", size, width, bold)) > lines:
        out = out[:out.rfind(" ")]
    return out.rstrip(",;: ") + "…"


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
    return ("-" if v < 0 else "") + digits


def _pc(v, signed=False) -> str:
    return "–" if v is None else (f"{v:+.1f}%" if signed else f"{v:.1f}%")


def _numeric(s) -> bool:
    return isinstance(s, str) and bool(re.match(r"^[+\-–−₹$]?\s?[\d.,]+", s.strip())) or s == "–"


def _short_link(url: str) -> str:
    try:
        u = urlparse(url)
        name = u.path.rstrip("/").split("/")[-1]
        return f"{(u.hostname or '').replace('www.', '')}/…/{name[:22]}" if name else (u.hostname or url)
    except ValueError:
        return url[:50]


# ---------- the slides, described once ----------
class Slide:
    def __init__(self, title: str, subtitle: str | None = None, dark: bool = False):
        self.title, self.subtitle, self.dark, self.blocks = title, subtitle, dark, []

    def add(self, kind: str, box: tuple, **kw):
        self.blocks.append({"kind": kind, "box": box, **kw})
        return self


def plan(v: dict) -> tuple[list[Slide], str]:
    """The deck's slides for one deep-dive view, and the footer line."""
    name, sym = v["name"], v["symbol"]
    n = v["numbers"]
    years = [y for y in n["years"] if y.get("sales") is not None]
    us = v.get("region") == "US" or (n.get("unit") or "").startswith("$")
    unit = n.get("unit") or ("$ million" if us else "₹ crore")      # a foreign filer's own currency: "CAD million"
    bank = bool(n.get("bank"))
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    footer = f"{name} ({sym}) · Deep dive · {today}"
    month = date(2000, int(n.get("fye") or 3), 1).strftime("%B")
    amt = lambda x: "–" if x is None else money(x, unit)  # noqa: E731

    def fig_for(values):                     # each chart and table picks its unit, exact to within 1% (see scale_for)
        k, label, dp = scale_for(values, us, unit)
        if k == 1 and not us:
            return k, label, _cr
        return k, label, (lambda x: "–" if x is None else f"{x / k:,.{dp}f}")

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
    tiles = [("Market cap", "–" if cap is None else money(cap, "$ million") if us else amt(cap)), val, ret, lev,
             ("Sales growth, 3y", _pc(n["growth"].get("sales_cagr_3y"), True)),
             ("Profit growth, 3y", _pc(n["growth"].get("profit_cagr_3y"), True))]
    slides: list[Slide] = []

    # 1. title
    s = Slide(name, f"{'US' if us else 'NSE'}: {sym} · Company deep dive", dark=True)
    s.add("text", (M, 2.55, 8.6, 2.1), paras=[sentences(v.get("about") or "", 430)], size=15, floor=11, color=ICE)
    s.add("stats", (M, 5.15, W_IN - 2 * M, 1.25), items=tiles, dark=True)
    s.add("text", (M, 6.62, W_IN - 2 * M, 0.3), paras=[f"Prepared {today} with StratLab. {DISCLAIMER}"], size=10, floor=9, color=ICE)
    slides.append(s)

    # 2. at a glance
    cl = v.get("checklist") or {}
    card = v.get("card") or {}
    s = Slide("At a glance", "The numbers that frame everything after this slide")
    s.add("stats", (M, 1.65, W_IN - 2 * M, 1.25), items=tiles)
    left = []
    if cl.get("counts"):
        c = cl["counts"]
        left.append(("Investor checklist", f"{c['pass']} pass · {c['watch']} watch · {c['fail']} fail",
                     [x["label"] for x in cl.get("checks", []) if x["state"] == "fail"][:3]))
    if card.get("rows"):
        checked = card["met"] + card["missed"]
        left.append(("Management report card", f"{card['met']} of {checked} targets met" if checked else "Nothing to settle yet",
                     [f"{card.get('unchecked', 0)} targets can't be checked from the numbers"] if card.get("unchecked") else []))
    why = vv.get("why") or "Most businesses are compared on price to earnings."
    left.append((f"How it's valued: {val[0]}", val[1], [sentences(why, 230)]))
    s.add("cards", (M, 3.3, W_IN - 2 * M, 2.9), items=[{"title": t, "value": x, "lines": ls} for t, x, ls in left], cols=len(left))
    slides.append(s)

    # 3. sales and profit
    if years:
        k, word, _ = fig_for([y["sales"] for y in years] + [y["profit"] for y in years])
        s = Slide("Revenue and net profit" if bank else "Sales and net profit", f"{word}, financial years ending {month}")
        s.add("columns", (M, 1.6, 8.7, 5.1), cats=[y["year"].replace("Mar ", "FY") for y in years],
              series=[("Revenue" if bank else "Sales", [y["sales"] / k for y in years], NAVY),
                      ("Net profit", [(y["profit"] or 0) / k for y in years], TEAL)])
        g = n["growth"]
        s.add("stack", (9.75, 1.75, W_IN - M - 9.75, 4.9), items=[
            ("Sales growth a year, 3 years", _pc(g.get("sales_cagr_3y"), True)), ("Sales growth a year, 5 years", _pc(g.get("sales_cagr_5y"), True)),
            ("Profit growth a year, 3 years", _pc(g.get("profit_cagr_3y"), True)), ("Profit growth a year, 5 years", _pc(g.get("profit_cagr_5y"), True))])
        slides.append(s)

    # 4. the last eight quarters
    q = n.get("quarters") or []
    if q:
        _, word, figq = fig_for([x for r in q[-8:] for x in (r["sales"], r["profit"])])
        s = Slide("The last eight quarters", f"Sales and profit in {word}; growth on the same quarter a year before")
        rows = [[r["quarter"], figq(r["sales"]), _pc(r["sales_yoy"], True), _pc(r["opm"]), figq(r["profit"])] for r in q[-8:]]
        tint = {(i, 2): AMBER for i, r in enumerate(q[-8:]) if (r.get("sales_yoy") or 0) < 0}
        s.add("table", (M, 1.65, W_IN - 2 * M, 5.0), head=["Quarter", "Revenue" if bank else "Sales", "vs a year ago",
                                                          "Financing margin" if bank else "Operating margin", "Net profit"],
              rows=rows, widths=[2, 2, 1.6, 1.8, 2], colors=tint)
        slides.append(s)

    # 5. capex and cash (not for lenders: capex and free cash flow don't describe a bank)
    if years and not bank:
        recent = list(reversed(years))[:8]
        _, word, figc = fig_for([x for y in recent for x in (y["sales"], y["capex"], y["cfo"], y["fcf"], y["debt"])])
        s = Slide("Capex and cash", ("Capex as reported in the cash flow statement" if n.get("capex_reported") else
                                     "Capex estimated from the balance sheet: the rise in fixed assets and work in progress, plus depreciation")
                  + f". {word}.")
        rows = [[y["year"], figc(y["sales"]), figc(y["capex"]), _pc(y["capex_pct_sales"]), figc(y["cfo"]), figc(y["fcf"]), figc(y["debt"])]
                for y in recent]
        tint = {(i, 5): AMBER for i, y in enumerate(recent) if (y.get("fcf") or 0) < 0}
        s.add("table", (M, 1.65, W_IN - 2 * M, 5.0), head=["Year", "Sales", "Capex", "Capex / sales", "Cash from operations",
                                                          "Free cash flow", "Debt"], rows=rows, widths=[1.4, 1.6, 1.6, 1.4, 2, 1.8, 1.6], colors=tint)
        slides.append(s)

    reads = v.get("reads") or {}
    b, p = reads.get("business"), reads.get("plans")
    # 6. business model
    if b:
        s = Slide("Business model", "From the company's investor presentation and annual report")
        segs = [x for x in b.get("segments") or [] if x.get("share_pct") is not None]
        tw = 6.6 if segs else W_IN - 2 * M
        s.add("text", (M, 1.6, tw, 2.15), paras=[sentences(b.get("summary") or "", 600)], size=15, floor=11)
        if segs:
            s.add("hbars", (7.6, 1.55, W_IN - M - 7.6, 2.3), cats=[x["name"] for x in segs[:6]], vals=[x["share_pct"] for x in segs[:6]],
                  title="Share of revenue, %")
        cols = [("Customers", [b["customers"]] if b.get("customers") else []), ("What drives revenue", b.get("drivers", [])[:4]),
                ("Risks it names", b.get("risks", [])[:4])]
        s.add("cards", (M, 4.05, W_IN - 2 * M, 2.65), items=[{"title": t, "lines": ls} for t, ls in cols if ls], cols=3, bullets=True)
        slides.append(s)

    # 7. the industry's own operating measures
    ms = (b or {}).get("measures") or []
    if ms:
        s = Slide(f"{b.get('industry') or 'Operating'} measures", "As the company states them, with the period and the change")
        s.add("cards", (M, 1.65, W_IN - 2 * M, 5.0), cols=3, items=[
            {"title": m["name"], "value": m["value"],
             "lines": [" · ".join(x for x in (m.get("period"), m.get("change")) if x)]
             + ([f"{m['source']['title'][:40]}, {m['source']['at'][:10]}"] if m.get("source") else [])} for m in ms[:6]])
        slides.append(s)

    # 8. capex and growth plans
    if p and (p.get("capex") or p.get("outlook")):
        s = Slide("Capex and growth plans", "In management's own words, from the presentations and calls")
        items = [{"title": c["what"], "value": " · ".join(x for x in (c.get("amount"), c.get("size")) if x) or None,
                  "pill": (c["status"], TEAL if c["status"] in ("done", "under way") else SLATE),
                  "lines": [x for x in (c.get("timeline") and f"When: {c['timeline']}",
                                        c.get("source") and f"{c['source']['title'][:40]}, {c['source']['at'][:10]}") if x]}
                 for c in (p.get("capex") or [])[:6]]
        items += [{"title": "Outlook", "lines": [f"“{(o.get('quote') or o['statement'])}”"]} for o in (p.get("outlook") or [])[:6 - len(items)]]
        s.add("cards", (M, 1.65, W_IN - 2 * M, 5.0), items=items, cols=3 if len(items) > 4 else 2)
        slides.append(s)

    # 9. management report card
    if card.get("rows"):
        checked = card["met"] + card["missed"]
        s = Slide("Management report card", (f"{card['met']} of {checked} targets that the numbers can settle were met" if checked
                                             else "What management said on past calls, and whether the numbers can settle it"))
        s.add("stats", (M, 1.6, W_IN - 2 * M, 1.05), items=[("Met", str(card["met"])), ("Missed", str(card["missed"])),
                                                           ("Not due yet", str(card.get("pending", 0))), ("Can't check", str(card.get("unchecked", 0)))])
        rows, tint = [], {}
        for i, r in enumerate(card["rows"][:8]):
            fmt = amt if r["metric"] == "capex" else (lambda x: f"{x:g}%")
            tgt = "–" if r["low"] is None else fmt(r["low"]) + (f"–{fmt(r['high'])}" if r.get("high") is not None else "")
            label, color = STATE[r["result"]]
            rows.append([r["what"], r.get("period") or "–", tgt, "–" if r["actual"] is None else fmt(r["actual"]), label, r["said_at"][:10]])
            tint[(i, 4)] = color
        s.add("table", (M, 2.9, W_IN - 2 * M, 3.85), head=["What they said", "For", "Target", "Actual", "Result", "Said on"],
              rows=rows, widths=[5, 1, 1.5, 1.4, 1.4, 1.5], colors=tint)
        slides.append(s)

    # 10. investor checklist
    if cl.get("checks"):
        c = cl["counts"]
        ind = (cl.get("industry") or {}).get("label")
        s = Slide("Investor checklist", f"{c['pass']} pass · {c['watch']} watch · {c['fail']} fail"
                  + (f" · rules for: {ind}" if ind and ind != "General" else ""))
        rows, tint = [], {}
        for i, x in enumerate(cl["checks"][:14]):
            label, color = STATE[x["state"]]
            rows.append([x["group"], x["label"], x["value"], label])
            tint[(i, 3)] = color
        s.add("table", (M, 1.6, W_IN - 2 * M, 5.15), head=["Area", "Check", "Value", "Result"], rows=rows, widths=[1.6, 4.2, 3.6, 1.2],
              colors=tint, numeric=[False, False, False, False])
        slides.append(s)

    # 11. say what's missing, so a deck without document reads isn't mistaken for a complete one
    if not b or not card.get("rows"):
        missing = []
        if not b:
            missing.append("The business model, the industry's own measures and the capex plans: press Read the documents.")
        if not card.get("rows"):
            missing.append("The management report card: press Check past calls.")
        s = Slide("Not in this deck yet", "These come from the company's own presentations and calls, not read yet for this company")
        s.add("cards", (M, 1.7, W_IN - 2 * M, 2.4), items=[{"title": "Still to read", "lines": missing}], cols=1, bullets=True)
        s.add("text", (M, 4.4, W_IN - 2 * M, 0.6), paras=["Press those buttons on the company's deep dive page, then download the deck again."],
              size=14, floor=12, color=SLATE)
        slides.append(s)

    # 12. sources
    docs = v.get("documents") or []
    s = Slide("Sources", "Numbers: the company's reported annual and quarterly results. "
              + ("Filings: the company's reports to the SEC (10-K, 10-Q and 8-K)." if us else "Filings, presentations and call transcripts: the exchange (NSE)."))
    if docs:
        s.add("table", (M, 1.65, W_IN - 2 * M, 4.5), head=["Filed", "Document", "Link"],
              rows=[[x["at"][:10], x["title"], {"text": _short_link(x["url"]), "url": x["url"]}] for x in docs[:9]],
              widths=[1.3, 6.2, 4.6], numeric=[False, False, False])
    s.add("text", (M, 6.35, W_IN - 2 * M, 0.45), paras=[DISCLAIMER + " The AI reads can miss or misread things: check the source "
                                                      "document before relying on a point."], size=11, floor=9, color=SLATE)
    slides.append(s)
    return slides, footer


# ---------- PowerPoint ----------
class PptxRenderer:
    def __init__(self):
        from pptx import Presentation
        from pptx.util import Inches
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W_IN), Inches(H_IN)

    @staticmethod
    def rgb(h):
        from pptx.dml.color import RGBColor
        return RGBColor.from_string(h)

    def _text(self, s, x, y, w, h, runs, size, color=INK, bold=False, head=False, align=None, anchor=None, name=None):
        """A text box; `runs` is a list of paragraphs, each a string or a list of (text, options) pieces."""
        from pptx.enum.text import MSO_ANCHOR
        from pptx.util import Inches, Pt
        tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        if name:
            tb.name = name
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        if anchor:
            tf.vertical_anchor = {"middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[anchor]
        for i, para in enumerate(runs):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            if align:
                p.alignment = align
            p.space_after = Pt(size * 0.45)
            for piece in (para if isinstance(para, list) else [(para, {})]):
                text, o = piece
                r = p.add_run()
                r.text = str(text)
                f = r.font
                f.size = Pt(o.get("size", size))
                f.bold = o.get("bold", bold)
                f.name = "Cambria" if o.get("head", head) else "Calibri"
                f.color.rgb = self.rgb(o.get("color", color))
                if o.get("url"):
                    r.hyperlink.address = o["url"]
        return tb

    def _box(self, s, x, y, w, h, fill, line=None, round_=True):
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Pt
        shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        if round_:
            shp.adjustments[0] = min(0.12, 0.08 / max(h, 0.5) * 2)
        shp.fill.solid()
        shp.fill.fore_color.rgb = self.rgb(fill)
        if line:
            shp.line.color.rgb = self.rgb(line)
            shp.line.width = Pt(0.75)
        else:
            shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def slide(self, sl: Slide, n: int, total: int, footer: str):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = self.rgb(NAVY if sl.dark else WHITE)
        if sl.dark:
            self._text(s, M, 1.0, W_IN - 2 * M, 1.0, [sl.title], 40, color=WHITE, head=True, name="Title")
            self._text(s, M, 1.95, W_IN - 2 * M, 0.4, [sl.subtitle.upper()], 13, color="7FD1C7", bold=True)
        else:
            self._text(s, M, 0.45, W_IN - 2 * M, 0.7, [sl.title], 30, color=NAVY, head=True, name="Title")
            if sl.subtitle:
                self._text(s, M, 1.08, W_IN - 2 * M, 0.4, [clip(sl.subtitle, 13, W_IN - 2 * M, 1)], 13, color=SLATE)
            self._text(s, M, 7.02, 9, 0.25, [footer], 9, color=SLATE)
            from pptx.enum.text import PP_ALIGN
            self._text(s, W_IN - M - 1.5, 7.02, 1.5, 0.25, [f"{n} / {total}"], 9, color=SLATE, align=PP_ALIGN.RIGHT)
        for b in sl.blocks:
            getattr(self, "b_" + b["kind"])(s, b, sl.dark)

    def b_text(self, s, b, dark):
        x, y, w, h = b["box"]
        size = fit(b["paras"], w, h, b.get("size", 14), b.get("floor", 11))
        self._text(s, x, y, w, h, b["paras"], size, color=b.get("color", INK))

    def b_stats(self, s, b, dark):
        x, y, w, h = b["box"]
        items, gap = b["items"], 0.2
        cw = (w - gap * (len(items) - 1)) / len(items)
        for i, (label, value) in enumerate(items):
            cx = x + i * (cw + gap)
            self._box(s, cx, y, cw, h, NAVY2 if dark else MIST)
            self._text(s, cx + 0.18, y + 0.14, cw - 0.36, 0.3, [label], 11, color=ICE if dark else SLATE)
            vs = fit([value], cw - 0.36, h - 0.55, 24, 14, bold=True)
            self._text(s, cx + 0.18, y + 0.45, cw - 0.36, h - 0.55, [value], vs, color=WHITE if dark else NAVY, bold=True)

    def b_stack(self, s, b, dark):
        x, y, w, h = b["box"]
        step = h / len(b["items"])
        for i, (label, value) in enumerate(b["items"]):
            yy = y + i * step
            self._text(s, x, yy, w, 0.3, [label], 11, color=SLATE)
            color = AMBER if value.startswith("-") or value.startswith("−") else NAVY
            self._text(s, x, yy + 0.3, w, 0.6, [value], 26, color=color, bold=True)

    def b_cards(self, s, b, dark):
        items = b["items"]
        for it, (cx, cy, cw, ch) in zip(items, card_boxes(b)):
            self._box(s, cx, cy, cw, ch, MIST)
            iw, yy = cw - 0.5, cy + 0.22
            title = clip(it["title"], 13, iw - (1.3 if it.get("pill") else 0), 2, bold=True)
            self._text(s, cx + 0.25, yy, iw - (1.3 if it.get("pill") else 0), 0.5, [title], 13, color=NAVY, bold=True)
            if it.get("pill"):
                label, color = it["pill"]
                self._box(s, cx + cw - 1.45, yy - 0.02, 1.2, 0.3, color)
                from pptx.enum.text import PP_ALIGN
                self._text(s, cx + cw - 1.45, yy - 0.02, 1.2, 0.3, [label], 10, color=WHITE, bold=True, align=PP_ALIGN.CENTER, anchor="middle")
            yy += 0.3 * len(wrap(title, 13, iw, True)) + 0.12
            if it.get("value"):
                vs = fit([it["value"]], iw, 0.6, 24, 14, bold=True)
                self._text(s, cx + 0.25, yy, iw, 0.6, [it["value"]], vs, color=TEAL, bold=True)
                yy += vs / 72 * 1.35 + 0.08
            lines = [str(x) for x in it.get("lines") or [] if x]
            if lines:
                room = cy + ch - 0.18 - yy
                paras = [("• " if b.get("bullets") else "") + x for x in lines]
                ls = fit(paras, iw, room, 13, 9)
                self._text(s, cx + 0.25, yy, iw, room, paras, ls, color=INK if b.get("bullets") else SLATE)

    def b_table(self, s, b, dark):
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.oxml.ns import qn
        from pptx.util import Emu, Inches, Pt
        x, y, w, h = b["box"]
        lay = table_layout(b, w, h)
        shape = s.shapes.add_table(len(lay["rows"]) + 1, len(b["head"]), Inches(x), Inches(y), Inches(w), Inches(sum(lay["heights"])))
        t = shape.table
        t._tbl.tblPr.find(qn("a:tableStyleId")).text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"   # no style, no grid
        for i, cw in enumerate(lay["widths"]):
            t.columns[i].width = Emu(int(Inches(cw)))
        for r, hh in enumerate(lay["heights"]):
            t.rows[r].height = Emu(int(Inches(hh)))
        for r, vals in enumerate([b["head"]] + lay["rows"]):
            for c, v in enumerate(vals):
                cell = t.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = self.rgb(NAVY if r == 0 else (MIST if r % 2 == 0 else WHITE))
                cell.margin_left = cell.margin_right = Inches(0.1)
                cell.margin_top = cell.margin_bottom = Inches(0.04)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = cell.text_frame.paragraphs[0]
                link = v if isinstance(v, dict) else None
                run = p.add_run()
                run.text = fit_chars(link["text"], lay["size"], lay["widths"][c] - 0.25) if link else ("" if v is None else str(v))
                f = run.font
                f.size, f.name = Pt(lay["size"]), "Calibri"
                f.bold = r == 0 or (r > 0 and (r - 1, c) in (b.get("colors") or {}))
                f.color.rgb = self.rgb(WHITE if r == 0 else (b.get("colors") or {}).get((r - 1, c), TEAL if link else INK))
                if link:
                    run.hyperlink.address = link["url"]
                if lay["numeric"][c] and c > 0:
                    p.alignment = PP_ALIGN.RIGHT

    def b_columns(self, s, b, dark):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
        from pptx.util import Inches, Pt
        x, y, w, h = b["box"]
        cd = CategoryChartData()
        cd.categories = b["cats"]
        for name, vals, _ in b["series"]:
            cd.add_series(name, vals)
        ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
        ch.font.name, ch.font.size = "Calibri", Pt(10)
        ch.has_legend = True
        ch.legend.position, ch.legend.include_in_layout = XL_LEGEND_POSITION.TOP, False
        ch.legend.font.size = Pt(11)
        plot = ch.plots[0]
        plot.gap_width, plot.overlap = 55, -10
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.font.size, dl.font.color.rgb = Pt(8), self.rgb(SLATE)
        dl.number_format, dl.number_format_is_linked = "#,##0.0;-#,##0.0" if max(abs(v) for _, vs, _ in b["series"] for v in vs) < 100 else "#,##0", False
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        for series, (_, _, color) in zip(ch.series, b["series"]):
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = self.rgb(color)
            series.invert_if_negative = False
        va = ch.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = self.rgb(RULE)
        va.format.line.fill.background()
        va.tick_labels.font.size, va.tick_labels.font.color.rgb = Pt(9), self.rgb(SLATE)
        ca = ch.category_axis
        ca.tick_labels.font.size, ca.tick_labels.font.color.rgb = Pt(10), self.rgb(SLATE)
        ca.format.line.color.rgb = self.rgb(RULE)

    def b_hbars(self, s, b, dark):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
        from pptx.util import Inches, Pt
        x, y, w, h = b["box"]
        cd = CategoryChartData()
        cd.categories = [clip(c, 10, 2.2, 1) for c in b["cats"]]
        cd.add_series(b.get("title") or "", b["vals"])
        ch = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
        ch.font.name, ch.font.size = "Calibri", Pt(10)
        ch.has_legend = False
        ch.has_title = True
        ch.chart_title.text_frame.text = b.get("title") or ""
        ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(11)
        ch.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = self.rgb(SLATE)
        plot = ch.plots[0]
        plot.gap_width = 45
        plot.has_data_labels = True
        plot.data_labels.number_format, plot.data_labels.number_format_is_linked = '0"%"', False
        plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
        plot.data_labels.font.size = Pt(10)
        ch.series[0].format.fill.solid()
        ch.series[0].format.fill.fore_color.rgb = self.rgb(TEAL)
        ch.value_axis.visible = False
        ch.value_axis.has_major_gridlines = False
        ch.category_axis.reverse_order = True
        ch.category_axis.format.line.color.rgb = self.rgb(RULE)
        ch.category_axis.tick_labels.font.color.rgb = self.rgb(INK)

    def bytes(self) -> bytes:
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


def card_boxes(b: dict) -> list[tuple]:
    """(x, y, w, h) of each card: rows only as tall as their fullest card needs, within the block's box."""
    x, y, w, h = b["box"]
    items, gap = b["items"], 0.25
    if not items:
        return []
    cols = max(1, min(b.get("cols", 3), len(items)))
    rows = (len(items) + cols - 1) // cols
    cw, room = (w - gap * (cols - 1)) / cols, (h - gap * (rows - 1)) / rows
    iw = cw - 0.5

    def need(it):
        tw = iw - (1.3 if it.get("pill") else 0)
        hh = 0.22 + 0.3 * len(wrap(clip(it["title"], 13, tw, 2, True), 13, iw, True)) + 0.12
        if it.get("value"):
            hh += 24 / 72 * 1.35 + 0.08
        lines = [("• " if b.get("bullets") else "") + str(x) for x in it.get("lines") or [] if x]
        if lines:
            hh += sum(len(wrap(t, 13, iw)) for t in lines) * 13 * 1.25 / 72 + (len(lines) - 1) * 0.35 * 13 / 72
        return hh + 0.3

    out, yy = [], y
    for r in range(rows):
        row = items[r * cols:(r + 1) * cols]
        rh = min(room, max(max(need(it) for it in row), 1.0))
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


def table_layout(b: dict, w: float, h: float) -> dict:
    """Column widths, the font size and each row's height so the table fits its box; rows that still don't fit are
    left out (the caller passes few enough that this is rare)."""
    total = sum(b["widths"])
    widths = [w * x / total for x in b["widths"]]
    numeric = b.get("numeric") or [all(_numeric(r[c]) for r in b["rows"] if not isinstance(r[c], dict)) for c in range(len(b["head"]))]

    def text(v):
        return v["text"] if isinstance(v, dict) else ("" if v is None else str(v))

    for size in (12, 11, 10, 9):
        line = size * 1.3 / 72
        heights = [max(len(wrap(hd, size, cw - 0.2, True)) for hd, cw in zip(b["head"], widths)) * line + 0.14]
        heights += [max(len(wrap(text(v), size, cw - 0.2)) for v, cw in zip(r, widths)) * line + 0.14 for r in b["rows"]]
        heights = [max(0.34, x) for x in heights]
        if sum(heights) <= h:
            return {"widths": widths, "size": size, "heights": heights, "rows": b["rows"], "numeric": numeric}
    keep, used = [], heights[0]
    for r, hh in zip(b["rows"], heights[1:]):
        if used + hh > h:
            break
        keep.append(r)
        used += hh
    return {"widths": widths, "size": 9, "heights": heights[:len(keep) + 1], "rows": keep, "numeric": numeric}


# ---------- PDF ----------
class PdfRenderer:
    def __init__(self, title: str):
        from reportlab.pdfgen import canvas
        _fonts()
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=(W_IN * 72, H_IN * 72))
        self.c.setTitle(title)
        self.c.setAuthor("StratLab")

    @staticmethod
    def col(h):
        from reportlab.lib.colors import HexColor
        return HexColor("#" + h)

    def _y(self, y):                 # inches from the top to points from the bottom
        return (H_IN - y) * 72

    def _rect(self, x, y, w, h, fill, round_=True):
        self.c.setFillColor(self.col(fill))
        self.c.setStrokeColor(self.col(fill))
        if round_:
            self.c.roundRect(x * 72, self._y(y + h), w * 72, h * 72, 7, stroke=0, fill=1)
        else:
            self.c.rect(x * 72, self._y(y + h), w * 72, h * 72, stroke=0, fill=1)

    def _text(self, x, y, w, h, paras, size, color=INK, bold=False, head=False, align="left", gap=0.35, url=None):
        font = "Head" if head else "Body-Bold" if bold else "Body"
        self.c.setFillColor(self.col(color))
        self.c.setFont(font, size)
        yy = y
        for para in paras:
            for line in wrap(para, size, w, bold, head):
                yy += size * 1.25 / 72
                if yy > y + h + 0.02:
                    return
                tx = x * 72 if align == "left" else (x + w) * 72 - _width(line, size, bold, head) * 72 if align == "right" \
                    else (x + (w - _width(line, size, bold, head)) / 2) * 72
                self.c.drawString(tx, self._y(yy - size * 0.28 / 72), line)
                if url:
                    self.c.linkURL(url, (tx, self._y(yy), tx + _width(line, size, bold) * 72, self._y(yy - size * 1.25 / 72)), relative=0)
            yy += gap * size / 72

    def slide(self, sl: Slide, n: int, total: int, footer: str):
        self._rect(0, 0, W_IN, H_IN, NAVY if sl.dark else WHITE, round_=False)
        if sl.dark:
            self._text(M, 1.0, W_IN - 2 * M, 1.0, [sl.title], 40, color=WHITE, head=True)
            self._text(M, 1.95, W_IN - 2 * M, 0.4, [sl.subtitle.upper()], 13, color="7FD1C7", bold=True)
        else:
            self._text(M, 0.45, W_IN - 2 * M, 0.7, [sl.title], 30, color=NAVY, head=True)
            if sl.subtitle:
                self._text(M, 1.08, W_IN - 2 * M, 0.4, [clip(sl.subtitle, 13, W_IN - 2 * M, 1)], 13, color=SLATE)
            self._text(M, 7.02, 9, 0.25, [footer], 9, color=SLATE)
            self._text(W_IN - M - 1.5, 7.02, 1.5, 0.25, [f"{n} / {total}"], 9, color=SLATE, align="right")
        for b in sl.blocks:
            getattr(self, "b_" + b["kind"])(b, sl.dark)
        self.c.showPage()

    def b_text(self, b, dark):
        x, y, w, h = b["box"]
        size = fit(b["paras"], w, h, b.get("size", 14), b.get("floor", 11))
        self._text(x, y, w, h, b["paras"], size, color=b.get("color", INK))

    def b_stats(self, b, dark):
        x, y, w, h = b["box"]
        items, gap = b["items"], 0.2
        cw = (w - gap * (len(items) - 1)) / len(items)
        for i, (label, value) in enumerate(items):
            cx = x + i * (cw + gap)
            self._rect(cx, y, cw, h, NAVY2 if dark else MIST)
            self._text(cx + 0.18, y + 0.14, cw - 0.36, 0.3, [label], 11, color=ICE if dark else SLATE)
            vs = fit([value], cw - 0.36, h - 0.55, 24, 14, bold=True)
            self._text(cx + 0.18, y + 0.45, cw - 0.36, h - 0.5, [value], vs, color=WHITE if dark else NAVY, bold=True)

    def b_stack(self, b, dark):
        x, y, w, h = b["box"]
        step = h / len(b["items"])
        for i, (label, value) in enumerate(b["items"]):
            yy = y + i * step
            self._text(x, yy, w, 0.3, [label], 11, color=SLATE)
            self._text(x, yy + 0.3, w, 0.6, [value], 26, color=AMBER if value[:1] in "-−" else NAVY, bold=True)

    def b_cards(self, b, dark):
        items = b["items"]
        for it, (cx, cy, cw, ch) in zip(items, card_boxes(b)):
            self._rect(cx, cy, cw, ch, MIST)
            iw, yy = cw - 0.5, cy + 0.22
            tw = iw - (1.3 if it.get("pill") else 0)
            title = clip(it["title"], 13, tw, 2, bold=True)
            self._text(cx + 0.25, yy, tw, 0.5, [title], 13, color=NAVY, bold=True)
            if it.get("pill"):
                label, color = it["pill"]
                self._rect(cx + cw - 1.45, yy - 0.02, 1.2, 0.3, color)
                self._text(cx + cw - 1.45, yy + 0.02, 1.2, 0.3, [label], 10, color=WHITE, bold=True, align="center")
            yy += 0.3 * len(wrap(title, 13, iw, True)) + 0.12
            if it.get("value"):
                vs = fit([it["value"]], iw, 0.6, 24, 14, bold=True)
                self._text(cx + 0.25, yy, iw, 0.6, [it["value"]], vs, color=TEAL, bold=True)
                yy += vs / 72 * 1.35 + 0.08
            lines = [str(x) for x in it.get("lines") or [] if x]
            if lines:
                room = cy + ch - 0.18 - yy
                paras = [("• " if b.get("bullets") else "") + x for x in lines]
                ls = fit(paras, iw, room, 13, 9)
                self._text(cx + 0.25, yy, iw, room, paras, ls, color=INK if b.get("bullets") else SLATE)

    def b_table(self, b, dark):
        x, y, w, h = b["box"]
        lay = table_layout(b, w, h)
        yy = y
        for r, (vals, hh) in enumerate(zip([b["head"]] + lay["rows"], lay["heights"])):
            self._rect(x, yy, w, hh, NAVY if r == 0 else (MIST if r % 2 == 0 else WHITE), round_=False)
            cx = x
            for c, (v, cw) in enumerate(zip(vals, lay["widths"])):
                link = v if isinstance(v, dict) else None
                text = fit_chars(link["text"], lay["size"], cw - 0.25) if link else ("" if v is None else str(v))
                color = WHITE if r == 0 else (b.get("colors") or {}).get((r - 1, c), TEAL if link else INK)
                bold = r == 0 or (r > 0 and (r - 1, c) in (b.get("colors") or {}))
                lines = len(wrap(text, lay["size"], cw - 0.2, bold))
                top = yy + (hh - lines * lay["size"] * 1.25 / 72) / 2
                self._text(cx + 0.1, top, cw - 0.2, hh, [text], lay["size"], color=color, bold=bold,
                           align="right" if lay["numeric"][c] and c > 0 else "left", url=link["url"] if link else None)
                cx += cw
            yy += hh

    def _chart_axes(self, chart, cats):
        from reportlab.lib.colors import HexColor
        chart.categoryAxis.categoryNames = cats
        chart.categoryAxis.labels.fontName, chart.categoryAxis.labels.fontSize = "Body", 9
        chart.categoryAxis.labels.fillColor = HexColor("#" + SLATE)
        chart.categoryAxis.strokeColor = HexColor("#" + RULE)
        chart.valueAxis.labels.fontName, chart.valueAxis.labels.fontSize = "Body", 8
        chart.valueAxis.labels.fillColor = HexColor("#" + SLATE)
        chart.valueAxis.strokeColor = HexColor("#FFFFFF")
        chart.valueAxis.gridStrokeColor = HexColor("#" + RULE)
        chart.valueAxis.visibleGrid = True

    def b_columns(self, b, dark):
        from reportlab.graphics import renderPDF
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.legends import Legend
        from reportlab.graphics.shapes import Drawing
        x, y, w, h = b["box"]
        d = Drawing(w * 72, h * 72)
        ch = VerticalBarChart()
        ch.x, ch.y, ch.width, ch.height = 40, 26, w * 72 - 52, h * 72 - 64
        ch.data = [list(vs) for _, vs, _ in b["series"]]
        small = max(abs(v) for _, vs, _ in b["series"] for v in vs) < 100
        self._chart_axes(ch, b["cats"])
        ch.valueAxis.labelTextFormat = (lambda v: f"{v:,.1f}") if small else (lambda v: f"{v:,.0f}")
        if min(v for _, vs, _ in b["series"] for v in vs) >= 0:
            ch.valueAxis.valueMin = 0
        ch.groupSpacing, ch.barSpacing = 8, 1
        for i, (_, _, color) in enumerate(b["series"]):
            ch.bars[i].fillColor = self.col(color)
            ch.bars[i].strokeColor = None
        ch.barLabelFormat = (lambda v: f"{v:,.1f}") if small else (lambda v: f"{v:,.0f}")
        ch.barLabels.fontName, ch.barLabels.fontSize = "Body", 6.5
        ch.barLabels.fillColor = self.col(SLATE)
        ch.barLabels.nudge = 7
        d.add(ch)
        lg = Legend()
        lg.x, lg.y = ch.x, h * 72 - 12
        lg.alignment, lg.columnMaximum, lg.deltax = "right", 1, 90
        lg.fontName, lg.fontSize = "Body", 10
        lg.colorNamePairs = [(self.col(c), n) for n, _, c in b["series"]]
        d.add(lg)
        renderPDF.draw(d, self.c, x * 72, self._y(y + h))

    def b_hbars(self, b, dark):
        from reportlab.graphics import renderPDF
        from reportlab.graphics.charts.barcharts import HorizontalBarChart
        from reportlab.graphics.shapes import Drawing, String
        x, y, w, h = b["box"]
        d = Drawing(w * 72, h * 72)
        ch = HorizontalBarChart()
        cats = [clip(c, 9, 1.9, 1) for c in b["cats"]]
        ch.x, ch.y, ch.width, ch.height = 150, 6, w * 72 - 190, h * 72 - 30
        ch.data = [list(reversed(b["vals"]))]
        self._chart_axes(ch, list(reversed(cats)))
        ch.valueAxis.visible = False
        ch.valueAxis.visibleGrid = False
        ch.valueAxis.valueMin = 0
        ch.categoryAxis.labels.fillColor = self.col(INK)
        ch.bars[0].fillColor, ch.bars[0].strokeColor = self.col(TEAL), None
        ch.barLabelFormat = lambda v: f"{v:g}%"
        ch.barLabels.fontName, ch.barLabels.fontSize, ch.barLabels.nudge = "Body", 9, 12
        d.add(ch)
        d.add(String(ch.x, h * 72 - 14, b.get("title") or "", fontName="Body", fontSize=10, fillColor=self.col(SLATE)))
        renderPDF.draw(d, self.c, x * 72, self._y(y + h))

    def bytes(self) -> bytes:
        self.c.save()
        return self.buf.getvalue()


def build(v: dict) -> bytes:
    """The deck as PowerPoint."""
    slides, footer = plan(v)
    r = PptxRenderer()
    for i, sl in enumerate(slides, 1):
        r.slide(sl, i, len(slides), footer)
    r.prs.core_properties.title = f"{v['name']} ({v['symbol']}): company deep dive"
    r.prs.core_properties.author = "StratLab"
    return r.bytes()


def build_pdf(v: dict) -> bytes:
    """The same deck as a PDF."""
    slides, footer = plan(v)
    r = PdfRenderer(f"{v['name']} ({v['symbol']}): company deep dive")
    for i, sl in enumerate(slides, 1):
        r.slide(sl, i, len(slides), footer)
    return r.bytes()
