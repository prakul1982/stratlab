"""The tax report for one financial year as files to keep: a CSV of every realised line with the year's summary
(and the total tax estimate, with how it was worked out) above it, and a short PDF summary. Both carry the same
disclaimer as the page."""
import csv
import io
from datetime import datetime, timezone

from .tax_lots import DISCLAIMER, SETOFF_RULES, money
from .tax_total import AGE_NAMES


def _name(names: dict, key: str) -> str:
    n = names.get(key) or {}
    return n.get("symbol") or key


def _safe(v: str) -> str:
    """A cell a spreadsheet won't run as a formula (names come from the user's file)."""
    v = str(v or "")
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def _pct(rate: float | None) -> str:
    return "slab rate" if rate is None else f"{rate * 100:g}%"


def summary_lines(y: dict) -> list[tuple[str, str]]:
    """The year's numbers as (label, value) pairs, in the order the page shows them."""
    out = [("Short-term gains", money(y["stcg"]["gains"])), ("Short-term losses", money(y["stcg"]["losses"])),
           ("Long-term gains", money(y["ltcg"]["gains"])), ("Long-term losses", money(y["ltcg"]["losses"])),
           ("Long-term exemption used", f"{money(y['exemption']['used'])} of {money(y['exemption']['limit'])}")]
    for b in y["buckets"]:
        out.append((f"{b['label']} at {_pct(None if b.get('slab') else b['rate'])}: taxable", f"{money(b['taxable'])} (tax {money(b['tax'])})"))
    out += [("Estimated tax (before cess and surcharge)", money(y["tax"])), ("With 4% cess", money(y["tax_with_cess"])),
            ("Short-term loss to carry forward", money(y["carry_forward"]["st"])), ("Long-term loss to carry forward", money(y["carry_forward"]["lt"])),
            ("Intraday (speculative) profit or loss, not in the above", money(y["intraday"]["pnl"]))]
    for seg in (y.get("business") or {}).get("segments") or []:
        out.append((f"{seg['label']}: profit or loss before charges ({seg['trades']} trades)", money(seg["pnl"])))
        out.append((f"{seg['label']}: charges", money(seg["charges"])))
        out.append((f"{seg['label']}: turnover, trade by trade (netted per contract)",
                    f"{money(seg['turnover'])} ({money(seg['turnover_contract'])})"))
    return out


REGIMES = {"new": "New regime", "old": "Old regime"}


def total_lines(y: dict) -> list[tuple[str, str]]:
    """The total tax estimate as (label, value) pairs: the inputs, the breakdown and the total."""
    t = y.get("total")
    if not t:
        return []
    if not t.get("available"):
        return [("Total tax estimate", t.get("reason") or "Not available for this year.")]
    v = t["inputs"]
    out = [("Regime", REGIMES[t["regime"]]), ("Age band", AGE_NAMES.get(v.get("age"), "below 60")),
           ("Resident in India", "No" if v.get("resident") is False else "Yes"), ("Other income you entered", money(v["other"]))]
    if v["salary"] is not None:
        out.append(("Of which salary or pension", money(v["salary"])))
    if t["regime"] == "old":
        out.append(("Deductions you entered", money(v["deductions"])))
    out += [(ln["label"], money(ln["amount"])) for ln in t["lines"]]
    p = t["parts"]
    out += [("Share of the total: capital gains", money(p["capital_gains"])), ("Share of the total: intraday", money(p["intraday"])),
            ("Share of the total: F&O, commodity and currency", money(p["fno"])), ("Share of the total: other income", money(p["other"]))]
    cf = t["carry_forward"]
    if cf["speculative"]:
        out.append(("Speculative loss to carry forward", money(cf["speculative"])))
    if cf["business"]:
        out.append(("Business loss to carry forward", money(cf["business"])))
    return out


def to_csv(y: dict, rows: list[dict], names: dict) -> str:
    """A spreadsheet-friendly file: the summary, then one line per matched sale."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow([f"StratLab tax report, {y['label']}"])
    w.writerow([DISCLAIMER])
    w.writerow([])
    for label, value in summary_lines(y):
        w.writerow([label, value])
    if y.get("total"):
        w.writerow([])
        w.writerow(["Total tax estimate"])
        for label, value in total_lines(y):
            w.writerow([_safe(label), value])
        w.writerow([])
        w.writerow(["How we got here"])
        for i, step in enumerate((y["total"].get("steps") or []), 1):
            w.writerow([i, _safe(step)])
        for note in y["total"].get("notes") or []:
            w.writerow(["Note", _safe(note)])
        for fact in y.get("filing") or []:
            w.writerow(["Note", _safe(fact)])
    w.writerow([])
    w.writerow(["Stock", "ISIN", "Bought", "Sold", "Quantity", "Cost (with charges)", "Sale (after charges)", "Gain or loss",
                "Term", "Rate", "Note"])
    for r in rows:
        n = names.get(r["key"]) or {}
        note = "; ".join(x for x in ("bonus shares (cost nil)" if r["bonus"] else "",
                                       "grandfathered at 31 Jan 2018 price" if r["gf"] == "applied" else "",
                                       "bought before 1 Feb 2018: 31 Jan 2018 price not known, actual cost used" if r["gf"] == "missing" else "") if x)
        w.writerow([_safe(_name(names, r["key"])), _safe(n.get("isin") or ""), r["bought"], r["sold"], f"{r['qty']:g}", f"{r['cost']:.2f}",
                    f"{r['sale']:.2f}", f"{r['gain']:.2f}", "Long-term" if r["term"] == "LT" else "Short-term", _pct(r["rate"]), note])
    return out.getvalue()


def to_pdf(y: dict, names: dict, below: dict | None = None) -> bytes:
    """A one or two page summary: the year's numbers, the set-off steps, the rules and the disclaimer."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from .deck import _fonts
    from xml.sax.saxutils import escape
    _fonts()
    body = ParagraphStyle("b", fontName="Body", fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=11, textColor=HexColor("#5B6475"))
    head = ParagraphStyle("h", fontName="Head", fontSize=18, leading=22, spaceAfter=4)
    h2 = ParagraphStyle("h2", fontName="Body-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Tax report {y['label']}", author="StratLab")
    grid = TableStyle([("FONT", (0, 0), (-1, -1), "Body", 9), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                       ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor("#DDE3EA")), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    story = [Paragraph(f"Tax estimate, {escape(y['label'])}", head),
             Paragraph(escape(DISCLAIMER), small), Spacer(1, 6)]
    if total_lines(y):
        story += [Paragraph("Total tax estimate", h2),
                  Table([[escape(a), escape(b)] for a, b in total_lines(y)], colWidths=[110 * mm, 66 * mm], style=grid)]
        if y["total"].get("steps"):
            story += [Paragraph("How we got here", h2)] + [Paragraph(f"{i}. " + escape(s), body) for i, s in enumerate(y["total"]["steps"], 1)]
        story += [Paragraph("<b>Note:</b> " + escape(n), body) for n in y["total"].get("notes") or []]
    story += [Paragraph("Capital gains and other results", h2),
              Table([[escape(a), escape(b)] for a, b in summary_lines(y)], colWidths=[110 * mm, 66 * mm], style=grid)]
    if y["steps"]:
        story += [Paragraph("How the losses and exemption were applied", h2)] + [Paragraph("• " + escape(s), body) for s in y["steps"]]
    if y["gf_missing"]:
        story.append(Paragraph(f"{y['gf_missing']} sale(s) of shares bought before 1 Feb 2018 used the actual cost because "
                               "the 31 Jan 2018 price isn't known. Grandfathering could lower that gain.", body))
    story += [Paragraph("Set-off rules", h2)] + [Paragraph("• " + escape(s), body) for s in SETOFF_RULES]
    if y.get("filing"):
        story += [Paragraph("Returns and tax audit", h2)] + [Paragraph("• " + escape(s), body) for s in y["filing"]]
    top = sorted(y["rows"], key=lambda r: -abs(r["gain"] or 0))[:25]
    if top:
        story += [Paragraph("Largest realised lines", h2),
                  Table([["Stock", "Bought", "Sold", "Qty", "Gain or loss", "Term"]] +
                        [[escape(_name(names, r["key"]))[:24], r["bought"], r["sold"], f"{r['qty']:g}", money(r["gain"]),
                          "Long" if r["term"] == "LT" else "Short"] for r in top],
                        colWidths=[46 * mm, 25 * mm, 25 * mm, 20 * mm, 32 * mm, 18 * mm],
                        style=TableStyle(list(grid.getCommands()) + [("FONT", (0, 0), (-1, 0), "Body-Bold", 9)]))]
        if y["count"] > len(top):
            story.append(Paragraph(f"{y['count']} lines in all; the CSV has every one.", small))
    if below and below.get("rows"):
        story += [Paragraph("Open lots below cost today", h2),
                  Paragraph(f"Short-term: {money(below['st'] or 0)} · Long-term: {money(below['lt'] or 0)} "
                            f"across {len(below['rows'])} lot(s), at today's prices.", body)]
    story += [Spacer(1, 10), Paragraph(f"Made by StratLab on {datetime.now(timezone.utc):%d %b %Y} from your uploaded files. "
                                        + escape(DISCLAIMER), small)]
    doc.build(story)
    return buf.getvalue()
