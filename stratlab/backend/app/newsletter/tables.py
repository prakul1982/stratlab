"""A brief as tables (O5, 29 Oct): every section of an issue that lists figures becomes a table with a header row, short labels,
numbers on the right, and ▲ or ▼ with a sign for a change. One spec, drawn four ways: the Briefs page, the email, the public
blog post and the PDF.

The spec comes from the stored issue's own sections, so a brief written before tables existed is drawn as tables too (its
sections' texts are read back into columns; a column that none of its rows can fill is left out, never half empty). Prose
(a holiday, "no change") stays prose. Facts only.

A table: {"title", "kind": "table", "head": [...], "align": "lrr", "rows": [[cell, ...]], "note": str | None, "link": {"a", "href"} | None}
or a text section {"title", "kind": "text", "items": [{"a": text, "href": ...} | str]}. A cell is a string, or
{"t": text, "href": address, "tone": "up" | "down" | "flat", "sub": small line, "lines": [{"t", "href"}], "ext": True for an outside link}."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import email_kit as kit

UP, DOWN, FLAT = "▲", "▼", "–"
TZ = {"IN": ("Asia/Kolkata", "IST"), "US": ("America/New_York", "ET")}
_STAGE = {1: "Stage 1 (basing)", 2: "Stage 2 (advancing)", 3: "Stage 3 (topping)", 4: "Stage 4 (declining)"}
_SYM = r"[A-Z0-9][A-Z0-9&.\-]*"


def _num(s) -> float | None:
    try:
        return float(str(s).replace("−", "-").replace("–", "-").replace("+", "").replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def change_cell(x, dp: int = 2, tone: str = "updown") -> dict | str:
    """▲ +0.62% or ▼ −0.22%: the arrow and the sign both say the direction; a move that rounds to nothing is "– 0.00%"."""
    if x is None:
        return "–"
    r = round(float(x), dp)
    if r == 0:
        return {"t": f"{FLAT} {kit.pct_plain(0, dp)}", "tone": "flat"}
    return {"t": f"{UP if r > 0 else DOWN} {kit.pct(r, dp)}", "tone": "flat" if tone == "neutral" else ("up" if r > 0 else "down")}


def _link(text: str, href: str | None, ext: bool = False) -> dict | str:
    return {"t": text, "href": href, **({"ext": True} if ext else {})} if href else text


def _drop_empty(head: list[str], rows: list[list], keep: tuple[int, ...] = (0,)) -> tuple[list[str], list[list], str]:
    """The columns that none of the rows fills are left out (a brief from before the figures were kept has no closes to show)."""
    empty = lambda c: c in (None, "", "–") or (isinstance(c, dict) and not c.get("t") and not c.get("lines"))      # noqa: E731
    cols = [i for i in range(len(head)) if i in keep or any(not empty(r[i]) for r in rows)]
    return [head[i] for i in cols], [[r[i] for i in cols] for r in rows], cols


def _table(title: str, head: list[str], align: str, rows: list[list], note: str | None = None, link: dict | None = None, keep=(0,)) -> dict:
    h, r, cols = _drop_empty(head, rows, keep)
    return {"title": title, "kind": "table", "head": h, "align": "".join(align[i] for i in cols), "rows": r, "note": note, "link": link}


def _text(title: str, items: list) -> dict:
    return {"title": title, "kind": "text", "items": items}


# ---------- one section ----------
def _from_high(x) -> str:
    """How far an index is under its 52-week high: "14.6% below", "At the high"; empty when not known."""
    if x is None:
        return ""
    return f"{kit.pct_plain(x, 1)} below" if x < -0.05 else "At the high"


def indices(sec: dict, weekly: bool, high: dict | None = None) -> dict:
    rows = []
    for it in sec["items"]:
        m = re.match(r"^(.+?): ([\d,.]+)(?:, ([+−\-–]?[\d.]+)%(?: (?:on the day|over the week))?)?\s*$", str(it.get("text") or ""))
        if not m:
            rows.append([str(it.get("text") or ""), "", "", ""])
            continue
        rows.append([m.group(1), m.group(2), change_cell(_num(m.group(3)), tone="neutral" if "VIX" in m.group(1).upper() else "updown") if m.group(3) else "–",
                     _from_high((high or {}).get(m.group(1)))])
    return _table(sec["title"], ["Index", "Close", "Week %" if weekly else "Day %", "From 52-week high"], "lrrr", rows)


def rotation(sec: dict) -> dict:
    rows, basis, url = [], None, None
    for it in sec["items"]:
        m = re.match(r"^(.+?) moved from (.+?) to (.+?)(?: on the rotation chart (\(.*\)))?\s*$", str(it.get("text") or ""))
        url = url or it.get("url")
        if not m:
            rows.append([str(it.get("text") or ""), ""])
            continue
        basis = basis or m.group(4)
        rows.append([m.group(1), f"{m.group(2)} → {m.group(3)}"])
    note = f"Sector rotation chart {basis}" if basis else None
    return _table(sec["title"], ["Sector", "From → To"], "ll", rows, note=note.replace("(weekly", "on weekly candles").rstrip(")") + "." if note else None,
                  link={"a": "Open the rotation chart", "href": url} if url else None)


def _since(item: dict) -> str:
    d = item.get("since_day")
    return kit.fmt_date(d, year=False, weekday=True) if d else ""


def scan(sec: dict, region: str) -> dict:
    both = str(sec["title"]).startswith("Newly matched Stage 2")
    rows = []
    for it in sec["items"]:
        m = re.match(rf"^({_SYM}) ", str(it.get("text") or ""))
        sym = m.group(1) if m else str(it.get("text") or "")
        price = it.get("price")
        cur = it.get("currency") or ("USD" if region == "US" else "INR")
        stage = it.get("stage") or 2
        days = it.get("stage_days")
        up = it.get("st_up", True if both else False)
        rows.append([_link(sym, it.get("url")),
                     kit.money(price, cur, 2) if price is not None else "",
                     change_cell(it.get("change_pct")) if it.get("change_pct") is not None else "",
                     _STAGE.get(stage, f"Stage {stage}") + (f", {days} day{'s' if days != 1 else ''}" if days else ""),
                     "Up" + (f" since {kit.fmt_date(it['st_since'], year=False, weekday=True)}" if it.get("st_since") else "") if up else "Not up",
                     kit.fmt_date(it["matched_on"], year=False, weekday=True) if it.get("matched_on") else ""])
    return _table(sec["title"], ["Stock", "Close", "Day %", "Stage", "Supertrend", "Since"], "lrrlll", rows)


def headlines(sec: dict, region: str, weekly: bool) -> dict:
    tz, label = TZ.get(region, TZ["IN"])
    rows = []
    for it in sec["items"]:
        when = ""
        if it.get("at"):
            try:
                at = datetime.fromisoformat(str(it["at"]).replace("Z", "+00:00"))
                at = at.astimezone(ZoneInfo(tz)) if at.tzinfo else at
                when = f"{it['day'] + ', ' if it.get('day') else ''}{at:%H:%M} {label}"
            except ValueError:
                when = it.get("day") or ""
        else:
            when = it.get("day") or ""
        src = it.get("source") or ""
        lines = [{"t": ln.get("text"), **({"href": ln["url"]} if ln.get("url") else {})} for ln in it.get("lines") or []]
        text = str(it.get("text") or "")
        rows.append([when, {"t": text, "lines": lines} if lines else text, _link(src or "Source", it.get("url"), ext=True) if it.get("url") else src])
    return _table(sec["title"], ["Time", "Headline", "Source"], "lll", rows, keep=(1,))


def stock_changes(sec: dict, region: str) -> dict:
    rows = []
    for it in sec["items"]:
        reg = it.get("region") or region
        cur = it.get("currency") or ("USD" if reg == "US" else "INR")
        lines = [{"t": ln.get("text"), **({"href": ln["url"]} if ln.get("url") else {})} for ln in it.get("lines") or []]
        rows.append([_link(str(it.get("text") or ""), it.get("url")),
                     kit.money(it["price"], cur, 2) if it.get("price") is not None else "",
                     {**change_cell(it["change_pct"]), **({"sub": str(it["since"])} if it.get("since") else {})} if it.get("change_pct") is not None else "",
                     {"lines": lines} if lines else ""])
    return _table(sec["title"], ["Stock", "Close", "Change", "What changed"], "lrrl", rows)


def results(sec: dict) -> dict:
    rows = []
    for it in sec["items"]:
        text = str(it.get("text") or "")
        lines = [{"t": ln.get("text"), **({"href": ln["url"]} if ln.get("url") else {})} for ln in it.get("lines") or []]
        m = re.match(rf"^({_SYM}): (.+?) on (\w{{3}} \d{{1,2}} \w{{3}})(?:, (.+))?$", text)
        f = re.match(rf"^({_SYM}): results filed (\w{{3}} \d{{1,2}} \w{{3}})\. ?(.*)$", text)
        if f:
            rows.append([_link(f.group(1), it.get("url")), "Results filed", f.group(2), {"t": f.group(3), "lines": lines} if (f.group(3) or lines) else ""])
        elif m:
            rows.append([_link(m.group(1), it.get("url")), m.group(2), m.group(3), m.group(4) or ""])
        else:
            rows.append([_link(text, it.get("url")), "", "", ""])
    return _table(sec["title"], ["Stock", "Event", "Date", "Detail"], "llll", rows)


def actions(sec: dict) -> dict:
    rows = []
    for it in sec["items"]:
        m = re.match(rf"^({_SYM}): (.+?), ex-date (\w{{3}} \d{{1,2}} \w{{3}})(?:, record date (\w{{3}} \d{{1,2}} \w{{3}}))?$", str(it.get("text") or ""))
        rows.append([_link(m.group(1), it.get("url")), m.group(2), m.group(3), m.group(4) or ""] if m else [_link(str(it.get("text") or ""), it.get("url")), "", "", ""])
    return _table(sec["title"], ["Stock", "Action", "Ex-date", "Record date"], "llll", rows)


def paper(sec: dict) -> dict:
    rows = []
    for it in sec["items"]:
        m = re.match(r"^(.+?): (\d+) trades? closed today \(([^)]*)\), (.+?) since start(?: \(([^)]*)\))?$", str(it.get("text") or ""))
        if m:
            rows.append([_link(m.group(1), it.get("url")), m.group(2), m.group(3), m.group(4) + (f" ({m.group(5)})" if m.group(5) else "")])
        else:
            rows.append([_link(str(it.get("text") or ""), it.get("url")), "", "", ""])
    return _table(sec["title"], ["Session", "Closed today", "Profit or loss today", "Since the start"], "lrrr", rows)


# ---------- an issue ----------
def of(issue: dict) -> list[dict]:
    """The issue's sections as tables (and prose sections), in order. The Indices section of an issue is drawn by the email as tiles
    as well; here it is the table."""
    region, weekly = issue.get("region") or "IN", bool(issue.get("weekly"))
    out = []
    for sec in issue.get("sections") or []:
        if not isinstance(sec, dict) or not sec.get("items"):
            continue
        title = str(sec.get("title") or "")
        try:
            if title == "Indices":
                out.append(indices(sec, weekly, {i.get("name"): i.get("from_high_pct") for i in issue.get("indices") or [] if isinstance(i, dict)}))
            elif title == "Sector rotation":
                out.append(rotation(sec))
            elif title.startswith(("Newly matched Stage 2", "Newly in Stage 2")):
                out.append(scan(sec, region))
            elif title == "Headlines":
                out.append(headlines(sec, region, weekly))
            elif title == "What changed for your stocks":
                out.append(stock_changes(sec, region))
            elif title == "Results this week":
                out.append(results(sec))
            elif title == "Corporate actions":
                out.append(actions(sec))
            elif title == "Your paper trading":
                out.append(paper(sec))
            else:
                out.append(_text(title, [_link(str(i.get("text") or ""), i.get("url")) for i in sec["items"]]))
        except Exception:                          # a section that can't be read into columns is shown as it was written
            out.append(_text(title, [_link(str(i.get("text") or ""), i.get("url")) for i in sec["items"]]))
    return out


def plain(cell) -> str:
    """A cell as text (for the plain-text email, the PDF's search text and the tests)."""
    if isinstance(cell, dict):
        parts = [str(cell.get("t") or "")] + [str(ln.get("t") or "") for ln in cell.get("lines") or []]
        return " ".join(p for p in parts if p) + (f" ({cell['sub']})" if cell.get("sub") else "")
    return str(cell or "")
