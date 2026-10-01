"""A company deck (PowerPoint) from the deep dive: numbers, business model, plans, the management report card and the
investor checklist, each slide citing where it came from. Built from what the page already has; no extra AI call."""
import io
from datetime import datetime, timezone

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

INK, MUTED, PAPER, CARD = RGBColor(0x1D, 0x1B, 0x17), RGBColor(0x6B, 0x66, 0x5C), RGBColor(0xF5, 0xF1, 0xE8), RGBColor(0xFF, 0xFD, 0xF8)
BLUE, ORANGE, LINE = RGBColor(0x1F, 0x4F, 0xB5), RGBColor(0xB4, 0x50, 0x0F), RGBColor(0xE2, 0xDC, 0xCF)
STATE = {"pass": ("Pass", BLUE), "watch": ("Watch", MUTED), "fail": ("Fail", ORANGE), "na": ("No data", MUTED),
         "met": ("Met", BLUE), "missed": ("Missed", ORANGE), "pending": ("Not due yet", MUTED), "unchecked": ("Can't check", MUTED)}
W, H = Inches(13.333), Inches(7.5)
DISCLAIMER = "Reported figures and the company's own words. Not investment advice."


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


class Deck:
    def __init__(self, title: str, footer: str):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.footer = footer
        self.title = title

    def slide(self, heading: str, sub: str | None = None):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = PAPER
        self.text(s, heading, Inches(0.6), Inches(0.4), Inches(12), Inches(0.7), 28, bold=False, serif=True)
        if sub:
            self.text(s, sub, Inches(0.6), Inches(1.05), Inches(12), Inches(0.5), 14, color=MUTED)
        self.text(s, f"{self.title} · {self.footer}", Inches(0.6), Inches(7.0), Inches(12), Inches(0.3), 10, color=MUTED)
        return s

    @staticmethod
    def text(s, value, x, y, w, h, size, bold=False, color=INK, serif=False, align=None):
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        lines = value if isinstance(value, list) else [value]
        for i, line in enumerate(lines):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            run = para.add_run()
            run.text = str(line)
            run.font.size, run.font.bold, run.font.color.rgb = Pt(size), bold, color
            run.font.name = "Georgia" if serif else "Calibri"
            if align:
                para.alignment = align
            para.space_after = Pt(6)
        return tb

    def table(self, s, head: list[str], rows: list[list], x, y, w, col_w: list[float] | None = None, size=12, colors=None):
        row_h = min(Inches(0.4), int((Inches(6.9) - y) / (len(rows) + 1)))     # tall tables shrink to stay on the slide
        shape = s.shapes.add_table(len(rows) + 1, len(head), x, y, w, row_h * (len(rows) + 1))
        t = shape.table
        for r in t.rows:
            r.height = row_h
        if col_w:
            total = sum(col_w)
            for i, cw in enumerate(col_w):
                t.columns[i].width = Emu(int(w * cw / total))
        for r, vals in enumerate([head] + rows):
            for c, v in enumerate(vals):
                cell = t.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = LINE if r == 0 else CARD
                cell.text = "" if v is None else str(v)
                cell.margin_top = cell.margin_bottom = Inches(0.03)
                p = cell.text_frame.paragraphs[0]
                p.font.size, p.font.bold = Pt(size), r == 0
                p.font.color.rgb = (colors or {}).get((r - 1, c), INK) if r else INK
                if c > 0 and r >= 0 and isinstance(v, str) and (v[:1].isdigit() or v[:1] in "+-–₹"):
                    p.alignment = PP_ALIGN.RIGHT
        return t

    def bytes(self) -> bytes:
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


def build(v: dict) -> bytes:
    name, sym = v["name"], v["symbol"]
    n = v["numbers"]
    years = [y for y in n["years"] if y.get("sales") is not None]
    d = Deck(f"{name} ({sym})", datetime.now(timezone.utc).strftime("%d %b %Y"))

    # 1. title
    s = d.slide(f"{name}", f"NSE: {sym} · Company deep dive")
    d.text(s, (v.get("about") or "")[:600], Inches(0.6), Inches(1.8), Inches(11.5), Inches(2.5), 16)
    snap = v.get("snapshot") or {}
    ret = ("ROE", _pc(snap.get("roe"))) if n.get("bank") else ("ROCE", _pc(snap.get("roce")))
    lev = (("Dividend yield", _pc(snap.get("div_yield"))) if n.get("bank")
           else ("Debt / equity", "–" if snap.get("debt_equity") is None else f"{snap['debt_equity']:.2f}"))
    tiles = [("Market cap", f"₹{_cr(snap.get('market_cap_cr'))} cr"), ("P/E", "–" if snap.get("pe") is None else f"{snap['pe']:.1f}"), ret, lev,
             ("Sales growth, 3y", _pc(n["growth"].get("sales_cagr_3y"), True)), ("Profit growth, 3y", _pc(n["growth"].get("profit_cagr_3y"), True))]
    for i, (label, val) in enumerate(tiles):
        x = Inches(0.6 + i * 2.05)
        box = s.shapes.add_shape(1, x, Inches(4.6), Inches(1.9), Inches(1.3))
        box.fill.solid()
        box.fill.fore_color.rgb = CARD
        box.line.color.rgb = LINE
        d.text(s, label, x + Inches(0.15), Inches(4.7), Inches(1.7), Inches(0.4), 11, color=MUTED)
        d.text(s, val, x + Inches(0.15), Inches(5.1), Inches(1.7), Inches(0.6), 20, bold=True)
    d.text(s, DISCLAIMER, Inches(0.6), Inches(6.3), Inches(12), Inches(0.4), 12, color=MUTED)

    # 2. sales and profit
    if years:
        s = d.slide("Revenue and net profit" if n.get("bank") else "Sales and net profit", f"{n['unit']}, financial years ending March")
        cd = CategoryChartData()
        cd.categories = [y["year"].replace("Mar ", "FY") for y in years]
        cd.add_series("Revenue" if n.get("bank") else "Sales", [y["sales"] for y in years])
        cd.add_series("Net profit", [y["profit"] or 0 for y in years])
        ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.6), Inches(12), Inches(5.2), cd).chart
        ch.has_legend, ch.legend.position, ch.legend.include_in_layout = True, XL_LEGEND_POSITION.TOP, False
        for series, color in zip(ch.series, (BLUE, ORANGE)):
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = color
        ch.value_axis.has_major_gridlines = True
        ch.value_axis.major_gridlines.format.line.color.rgb = LINE
        ch.font.size = Pt(11)

    # 3. margins and quarters
    q = n.get("quarters") or []
    if q:
        s = d.slide("The last eight quarters", "Sales and profit in ₹ crore; growth on the same quarter a year before")
        rows = [[x["quarter"], _cr(x["sales"]), _pc(x["sales_yoy"], True), _pc(x["opm"]), _cr(x["profit"])] for x in q[-8:]]
        d.table(s, ["Quarter", "Revenue" if n.get("bank") else "Sales", "vs a year ago", "Financing margin" if n.get("bank") else "Operating margin",
                    "Net profit"], rows, Inches(0.6), Inches(1.7), Inches(12))

    # 4. capex and cash (not for lenders: capex and free cash flow don't describe a bank)
    if years and not n.get("bank"):
        s = d.slide("Capex and cash", "Capex estimated from the balance sheet: rise in fixed assets and work in progress, plus depreciation. ₹ crore.")
        rows = [[y["year"], _cr(y["sales"]), _cr(y["capex"]), _pc(y["capex_pct_sales"]), _cr(y["cfo"]), _cr(y["fcf"]), _cr(y["debt"])]
                for y in list(reversed(years))[:8]]
        d.table(s, ["Year", "Sales", "Capex", "Capex / sales", "Cash from operations", "Free cash flow", "Debt"], rows,
                Inches(0.6), Inches(1.7), Inches(12))

    reads = v.get("reads") or {}
    b, p = reads.get("business"), reads.get("plans")
    # 5. business model
    if b:
        s = d.slide("Business model", "From the company's investor presentation")
        d.text(s, b["summary"], Inches(0.6), Inches(1.6), Inches(6.2), Inches(2.4), 15)
        segs = [x for x in b["segments"] if x.get("share_pct") is not None]
        if segs:
            cd = CategoryChartData()
            cd.categories = [x["name"] for x in segs]
            cd.add_series("Share of revenue, %", [x["share_pct"] for x in segs])
            ch = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(7.1), Inches(1.6), Inches(5.6), Inches(3.4), cd).chart
            ch.has_legend = False
            ch.plots[0].has_data_labels = True
            ch.plots[0].data_labels.number_format, ch.plots[0].data_labels.number_format_is_linked = '0"%"', False
            ch.series[0].format.fill.solid()
            ch.series[0].format.fill.fore_color.rgb = BLUE
            ch.value_axis.visible = False
            ch.value_axis.has_major_gridlines = False
            ch.category_axis.reverse_order = True
            ch.font.size = Pt(11)
        bullets = [f"Customers: {b['customers']}"] if b.get("customers") else []
        bullets += [f"Drives revenue: {x}" for x in b.get("drivers", [])[:3]] + [f"Risk it names: {x}" for x in b.get("risks", [])[:3]]
        d.text(s, bullets, Inches(0.6), Inches(4.2), Inches(6.2), Inches(2.6), 12)

    # 6. capex plans
    if p and (p.get("capex") or p.get("outlook")):
        s = d.slide("Capex and growth plans, in management's words", "From the latest investor presentation and earnings calls")
        rows = [[c["what"], c.get("amount") or "–", c.get("timeline") or "–", c["status"],
                 f"{c['source']['title'][:40]}, {c['source']['at'][:10]}" if c.get("source") else "–"] for c in p.get("capex", [])[:7]]
        if rows:
            d.table(s, ["Plan", "Amount", "When", "Status", "Source"], rows, Inches(0.6), Inches(1.6), Inches(12), [4, 1.6, 1.4, 1.2, 3], size=11)
        if p.get("outlook"):
            d.text(s, [f"“{o['quote'] or o['statement']}”" for o in p["outlook"][:3]], Inches(0.6), Inches(1.9 + 0.42 * (len(rows) + 1)),
                   Inches(12), Inches(1.6), 12, color=MUTED)

    # 7. report card
    card = v.get("card")
    if card and card.get("rows"):
        checked = card["met"] + card["missed"]
        sub = (f"{card['met']} of {checked} checkable targets from past earnings calls were met" if checked
               else "No targets can be settled by the reported numbers yet")
        s = d.slide("Management report card", sub)
        rows, colors = [], {}
        for i, r in enumerate(card["rows"][:9]):
            unit = "crore" if r["metric"] == "capex" else "%"
            fmt = (lambda x: f"₹{_cr(x)} cr") if unit == "crore" else (lambda x: f"{x:g}%")
            tgt = "–" if r["low"] is None else fmt(r["low"]) + (f"–{fmt(r['high'])}" if r.get("high") is not None else "")
            label, color = STATE[r["result"]]
            rows.append([r["what"], r.get("period") or "–", tgt, "–" if r["actual"] is None else fmt(r["actual"]), label, r["said_at"][:10]])
            colors[(i, 4)] = color
        d.table(s, ["What they said", "For", "Target", "Actual", "Result", "Said on"], rows, Inches(0.6), Inches(1.6), Inches(12),
                [4.5, 1, 1.4, 1.4, 1.3, 1.4], size=11, colors=colors)

    # 8. checklist
    cl = v.get("checklist")
    if cl and cl.get("checks"):
        c = cl["counts"]
        s = d.slide("Investor checklist", f"{c['pass']} pass · {c['watch']} watch · {c['fail']} fail, on fixed rules written below each check")
        rows, colors = [], {}
        for i, x in enumerate(cl["checks"][:16]):
            label, color = STATE[x["state"]]
            rows.append([x["group"], x["label"], x["value"], label])
            colors[(i, 3)] = color
        d.table(s, ["Area", "Check", "Value", "Result"], rows, Inches(0.6), Inches(1.5), Inches(12), [1.6, 4, 3.4, 1.2], size=10, colors=colors)

    # 9. sources
    docs = v.get("documents") or []
    s = d.slide("Sources")
    lines = ["Numbers: the company's reported annual and quarterly results.",
             "Filings, presentations and call transcripts: the exchange (NSE)."]
    lines += [f"{x['at'][:10]} · {x['title'][:90]} · {x['url']}" for x in docs[:8]]
    lines += ["", DISCLAIMER + " The AI reads can miss or misread things: check the source document before relying on a point."]
    d.text(s, lines, Inches(0.6), Inches(1.4), Inches(12), Inches(5.4), 12)
    return d.bytes()
