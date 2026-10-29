"""A brief as a PDF (O6): the same tables as the Briefs page and the email (tables.py), the brief's date and its "Prices and numbers as
of" line, StratLab's name, the disclaimer, page numbers, and headline sources as links that open in the PDF reader. Made when it is asked
for, in memory, with the PDF code the tax report uses (reportlab, the app's own fonts): nothing is stored."""
import io
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from .. import email_kit as kit
from . import tables, write

INK, MUTED, LINE, UP, DOWN, BLUE = "#1D1B17", "#5C574D", "#E2DAC8", "#138A62", "#B23B3B", "#1F4FB5"
SITE = "stratlab.studio"


def _safe(url) -> str | None:
    return kit.safe_url(url)


def _cell_xml(c, size: float = 8.5) -> str:
    """One table cell as reportlab paragraph markup: its text (a link when it has an address), its tone, its small lines."""
    if not isinstance(c, dict):
        return escape(str(c or ""))
    t = escape(str(c.get("t") or ""))
    href = _safe(c.get("href")) if c.get("href") else None
    if t and href:
        t = f'<a href="{escape(href, {chr(34): "&quot;"})}"><font color="{BLUE}">{t}</font></a>'
    color = {"up": UP, "down": DOWN, "flat": MUTED}.get(c.get("tone") or "")
    if t and color:
        t = f'<font color="{color}">{t}</font>'
    out = t
    if c.get("sub"):
        out += f'<br/><font color="{MUTED}" size="{size - 1.5}">{escape(str(c["sub"]))}</font>'
    for ln in c.get("lines") or []:
        lt, lh = escape(str(ln.get("t") or "")), _safe(ln.get("href"))
        out += f'<br/><font color="{MUTED}" size="{size - 1}">{f"""<a href="{escape(lh)}">{lt}</a>""" if lh else lt}</font>'
    return out


def build(issue: dict, now: datetime | None = None) -> bytes:
    """The issue as a PDF: a title block, the facts line, every section of figures as a table, the footer line and page numbers."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from ..deck import _fonts
    _fonts()
    issue = write.regional_links(issue)
    region, kind = issue.get("region"), issue.get("kind") or "market"
    body = ParagraphStyle("b", fontName="Body", fontSize=9.5, leading=13, textColor=HexColor(INK))
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=11, textColor=HexColor(MUTED))
    head = ParagraphStyle("h", fontName="Head", fontSize=17, leading=21, spaceAfter=3, textColor=HexColor(INK))
    h2 = ParagraphStyle("h2", fontName="Body-Bold", fontSize=11, leading=14, spaceBefore=11, spaceAfter=4, textColor=HexColor(INK))
    cellp = ParagraphStyle("c", parent=body, fontSize=8.5, leading=11)
    cellr = ParagraphStyle("cr", parent=cellp, alignment=2)
    th = ParagraphStyle("th", parent=cellp, fontName="Body-Bold", fontSize=7.5, leading=10, textColor=HexColor(MUTED))
    thr = ParagraphStyle("thr", parent=th, alignment=2)
    label = write.TYPE_LABEL.get(kind, "Newsletter") + (f" · {write.REGION_NAME[region]}" if region in write.REGION_NAME else "")
    weekly = bool(issue.get("weekly"))
    day = (f"Week to {write._day(write._week_end(issue['day'], region or 'IN'))}" if weekly else write._day(issue["day"])) if issue.get("day") else ""
    title = issue.get("subject") or "Brief"
    when = write.close_stamp({**issue, "kind": kind}) or write.as_of(issue.get("at"), region)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=title, author="StratLab", subject=f"{label}, {day}")
    story = [Paragraph(f"{escape(label)} · {escape(day)}", small), Paragraph(escape(title), head)]
    if when:
        story.append(Paragraph(f"Prices and numbers as of {escape(when)}", small))
    story.append(Spacer(1, 4))
    if issue.get("summary"):
        story.append(Paragraph(escape(str(issue["summary"])), body))
    if issue.get("ai_summary"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(escape(write.house_numbers(issue["ai_summary"], issue.get("indices"))), body))
    secs = [s for s in issue.get("sections") or [] if isinstance(s, dict)]
    indices = issue.get("indices") or []
    if indices and not any(s.get("title") == "Indices" for s in secs):
        secs = write.market_sections({"region": region or "IN", "weekly": weekly, "indices": indices})[:1] + secs
    avail = A4[0] - 32 * mm
    for t in tables.of({**issue, "sections": secs}):
        parts = [Paragraph(escape(t["title"]), h2)]
        if t["kind"] == "text":
            parts += [Paragraph("• " + _cell_xml(i), body) for i in t["items"]]
            story.append(KeepTogether(parts[:2]))
            story += parts[2:]
            continue
        n = len(t["head"])
        right = [a == "r" for a in t["align"]]
        data = [[Paragraph(escape(h), thr if right[i] else th) for i, h in enumerate(t["head"])]]
        for r in t["rows"]:
            data.append([Paragraph(_cell_xml(c) or "&nbsp;", cellr if right[i] else cellp) for i, c in enumerate(r)])
        # a column as wide as its longest cell needs, the headline-like text column taking what is left
        wide = max(range(n), key=lambda i: max(len(tables.plain(r[i])) for r in t["rows"]) if not right[i] else -1)
        weights = [1.0 if i != wide else 3.4 for i in range(n)]
        widths = [avail * w / sum(weights) for w in weights]
        tbl = Table(data, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.6, HexColor(MUTED)),
                                 ("LINEBELOW", (0, 1), (-1, -1), 0.4, HexColor(LINE)), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
        story += [KeepTogether([parts[0], tbl]) if len(data) < 14 else parts[0], *( [] if len(data) < 14 else [tbl])]
        if t.get("note"):
            story.append(Paragraph(escape(t["note"]), small))
        if t.get("link") and _safe(t["link"]["href"]):
            story.append(Paragraph(f'<a href="{escape(_safe(t["link"]["href"]))}"><font color="{BLUE}">{escape(t["link"]["a"])}</font></a>', small))
    story += [Spacer(1, 10), Paragraph(escape(write.FOOTER), small)]

    def pages(canvas, d):
        canvas.setFont("Body", 7)
        canvas.setFillColor(HexColor(MUTED))
        canvas.drawString(16 * mm, 9 * mm, f"StratLab · {label} · {day}")
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {d.page}")
        canvas.drawCentredString(A4[0] / 2, 9 * mm, SITE)
    doc.build(story, onFirstPage=pages, onLaterPages=pages)
    return buf.getvalue()


def filename(issue: dict) -> str:
    kind = issue.get("kind") or "market"
    region = (issue.get("region") or "").lower()
    base = "my-stocks" if kind == "my_stocks" else f"market-brief-{'india' if region == 'in' else region or 'market'}"
    return f"stratlab-{base}-{str(issue.get('day') or '')[:10]}{'-weekly' if issue.get('weekly') else ''}.pdf"
